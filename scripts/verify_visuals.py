#!/usr/bin/env python3
"""
verify_visuals.py — Gemini vision gate for documentary scene visuals.

For each clip in clips.json, sends its check frames (already extracted by
clips.py) to the Gemini free-tier vision API with a strict verification
checklist, and records a verdict per clip.

Lawal's rules baked in:
  - "zero ai clip or images": rejects AI-looking footage, modern objects,
    title cards, intrusive watermarks, wrong subject, wrong era.
  - small corner archive watermarks (Pathe, CriticalPast, ...) are OK.
  - no verdict is final on API failure: marks "unverified" and the human
    gate (skills/meta/review-protocol.md) takes over.

Auth: GEMINI_API_KEY env var (free key from Google AI Studio), or
GEMINI_API_KEYS for several keys comma-separated (failover: a key that
hits quota or is rejected is skipped and the next key takes over).
Without keys the script still runs and marks everything "unverified"
so the pipeline degrades to manual review instead of crashing.

Input clips.json (from clips.py):
  {"clips": [{"segment": i, "file": ..., "check_frames": [...],
              "url": ..., "license": ..., "source": ..., "query": ...}, ...]}

Optional --briefs briefs.json (written by the agent at the scene-visuals
stage — per-segment expect/reject notes that guide the vision check):
  {"0": {"expect": "German Panzer III/IV advancing, summer 1941",
         "reject": "Tiger tanks, winter scenes, modern reenactment"}, ...}

Output verify.json:
  {"model": "gemini-2.0-flash",
   "results": [{"segment": i, "file": ..., "verdict": "accept|reject|flag|unverified",
                "confidence": 0.0-1.0, "checks": {...}, "reason": "..."}, ...]}

Usage:
  GEMINI_API_KEY=... python3 scripts/verify_visuals.py clips.json --out verify.json [--briefs briefs.json] [--narration narration.json]
"""

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

MODEL = "gemini-flash-latest"  # stable alias; pinned versions (2.0/2.5) are blocked for new API keys
API_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{MODEL}:generateContent")
MAX_FRAME_WIDTH = 640
FRAMES_PER_CLIP = 3
PAUSE_BETWEEN_CALLS = 2.0  # stay polite on the free tier

PROMPT_TEMPLATE = """You are verifying candidate footage for a historical documentary. Only real archival footage is acceptable.

NARRATION FOR THIS SCENE: "{text}"
EXPECTED TO SEE: "{expect}"
REJECT IF SEEN: "{reject}"

The attached {n} frames come from one candidate video clip.
Return ONLY a JSON object (no markdown, no commentary):
{{
  "verdict": "accept" | "reject" | "flag",
  "confidence": 0.0-1.0,
  "subject_match": true/false,
  "era_match": true/false,
  "checks": {{
    "ai_generated_look": true/false,
    "modern_objects": true/false,
    "title_card_or_text_slate": true/false,
    "watermark_or_logo": true/false,
    "unrelated_subject": true/false,
    "wrong_era": true/false
  }},
  "reason": "<one sentence>"
}}

Rules:
- "reject" if any check is true, or the subject/era clearly does not match the narration.
- "flag" if you cannot tell (too blurry, ambiguous) — a human will review it.
- "accept" only if the footage plausibly matches the narration's subject and era.
- Watermarks: small corner archive watermarks (e.g. Pathe, CriticalPast, Periscope) are acceptable — set watermark_or_logo false for those; true only for intrusive or promotional watermarks.
"""


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load_dotenv():
    """Project-root .env, stdlib-only (no dependency). Env vars win."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.path.dirname(here), ".env"),
                 os.path.join(here, ".env")):
        if os.path.exists(cand):
            with open(cand) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(),
                                              v.strip().strip('"').strip("'"))
            break


def shrink_frame(path):
    """Downscale a check frame to MAX_FRAME_WIDTH JPEG, return base64."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf",
           f"scale={MAX_FRAME_WIDTH}:-1", "-q:v", "5", "-f", "image2pipe",
           "-vcodec", "mjpeg", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None
    return base64.b64encode(r.stdout).decode("ascii")


def gemini_verify(pool, text, expect, reject, frame_paths):
    parts = [{"text": PROMPT_TEMPLATE.format(
        text=text[:600], expect=expect, reject=reject, n=len(frame_paths))}]
    for p in frame_paths:
        b64 = shrink_frame(p)
        if b64 is None:
            log(f"  WARN: could not read frame {p}")
            continue
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    if len(parts) < 2:
        return {"verdict": "unverified", "confidence": 0.0, "checks": {},
                "reason": "no readable frames"}

    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1,
                             "response_mime_type": "application/json"},
    }).encode()

    attempts = 0
    while attempts < 6:
        attempts += 1
        entry = pool.next_ok()
        if entry is None:
            return {"verdict": "unverified", "confidence": 0.0, "checks": {},
                    "reason": "all API keys exhausted or invalid — "
                              "manual review required"}
        key = entry["key"]
        tag = f"key …{key[-4:]}"
        try:
            req = urllib.request.Request(
                API_URL + "?key=" + key, data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.load(resp)
            txt = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(txt)
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode()[:400].lower()
            except Exception:
                pass
            quota_hit = (e.code == 429 or "quota" in err_body
                         or "rate limit" in err_body or "ratelimit" in err_body)
            if quota_hit:
                pool.mark(entry, "exhausted")
                log(f"  {tag} quota-hit, rotating to next key")
                continue
            if e.code in (400, 401, 403):
                pool.mark(entry, "dead")
                log(f"  {tag} rejected (HTTP {e.code}), rotating to next key")
                continue
            if e.code in (500, 503):  # transient — brief wait, same pool
                time.sleep(10)
                continue
            return {"verdict": "unverified", "confidence": 0.0, "checks": {},
                    "reason": f"API error: HTTP {e.code}"}
        except Exception as e:  # network/parse errors
            entry["errors"] = entry.get("errors", 0) + 1
            if entry["errors"] >= 2:
                pool.mark(entry, "dead")
                log(f"  {tag} repeated network errors, rotating")
                continue
            time.sleep(5)
    return {"verdict": "unverified", "confidence": 0.0, "checks": {},
            "reason": "too many attempts — manual review required"}


class KeyPool:
    """Round-robin over multiple Gemini keys; quota-hit/dead keys are
    skipped for the rest of the run."""

    def __init__(self, keys):
        self.keys = [{"key": k, "state": "ok"} for k in keys]
        self.idx = 0

    def next_ok(self):
        for _ in range(len(self.keys)):
            entry = self.keys[self.idx % len(self.keys)]
            self.idx += 1
            if entry["state"] == "ok":
                return entry
        return None

    def mark(self, entry, state):
        entry["state"] = state

    def summary(self):
        return {s: sum(1 for k in self.keys if k["state"] == s)
                for s in ("ok", "exhausted", "dead")}


def get_api_keys():
    """GEMINI_API_KEYS (comma-separated) or legacy GEMINI_API_KEY."""
    raw = os.environ.get("GEMINI_API_KEYS", "") or \
        os.environ.get("GEMINI_API_KEY", "")
    return list(dict.fromkeys(k.strip() for k in raw.split(",") if k.strip()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips_json")
    ap.add_argument("--out", default="verify.json")
    ap.add_argument("--briefs", default=None,
                    help="briefs.json: per-segment expect/reject notes")
    ap.add_argument("--narration", default=None,
                    help="narration.json: segment index -> text for the prompt")
    ap.add_argument("--segments", default=None,
                    help="comma list of segment indexes to verify (default: all)")
    args = ap.parse_args()

    load_dotenv()  # project .env (chmod 600) before reading the key
    pool = KeyPool(get_api_keys())
    clips = json.load(open(args.clips_json)).get("clips", [])
    briefs = json.load(open(args.briefs)) if args.briefs else {}
    seg_text = {}
    if args.narration:
        narr = json.load(open(args.narration))
        segs = narr.get("segments", narr if isinstance(narr, list) else [])
        for s in segs:
            if isinstance(s, dict) and "index" in s:
                seg_text[s["index"]] = s.get("text", "")
    only = ({int(s) for s in args.segments.split(",")}
            if args.segments else None)

    if not pool.keys:
        log("No GEMINI_API_KEY(S) — marking all clips unverified "
            "(manual review gate takes over).")
    else:
        log(f"{len(pool.keys)} API key(s) loaded with failover.")

    results = []
    for clip in clips:
        seg = clip.get("segment")
        if only is not None and seg not in only:
            continue
        text = (clip.get("segment_text", "") or seg_text.get(seg, "") or "")
        b = briefs.get(str(seg), {}) if isinstance(briefs, dict) else {}
        expect = b.get("expect", "not specified")
        reject = b.get("reject", "not specified")
        frames = (clip.get("check_frames") or [])[:FRAMES_PER_CLIP]
        frames = [f for f in frames if os.path.exists(f)]

        log(f"segment {seg}: {len(frames)} frames "
            f"({os.path.basename(clip.get('file', ''))})")
        if pool.keys and frames:
            v = gemini_verify(pool, text, expect, reject, frames)
            time.sleep(PAUSE_BETWEEN_CALLS)
        else:
            v = {"verdict": "unverified", "confidence": 0.0, "checks": {},
                 "reason": "no API key or no frames — manual review required"}

        results.append({
            "segment": seg,
            "file": clip.get("file"),
            "url": clip.get("url"),
            "license": clip.get("license"),
            "source": clip.get("source"),
            "verdict": v.get("verdict", "unverified"),
            "confidence": v.get("confidence", 0.0),
            "subject_match": v.get("subject_match"),
            "era_match": v.get("era_match"),
            "checks": v.get("checks", {}),
            "reason": v.get("reason", ""),
        })
        log(f"  -> {results[-1]['verdict']} "
            f"({results[-1]['confidence']}) {results[-1]['reason']}")

    out = {"model": MODEL if pool.keys else None,
           "keys": pool.summary(), "results": results}
    json.dump(out, open(args.out, "w"), indent=1)
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    log(f"Wrote {args.out}: " +
        ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
