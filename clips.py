#!/usr/bin/env python3
"""
clips.py — find REAL archival video clips as documentary scene backgrounds.

For each narration segment, derive a search query from the segment text and
hunt genuine footage (never AI, never synthetic) from free sources, in
priority order:

  1. Internet Archive (advancedsearch API, mediatype:movies) — prefers
     public-domain / CC-licensed items.
  2. Wikimedia Commons (API, filetype:video) — license filtered to
     public domain / CC0 / CC-BY / CC-BY-SA via extmetadata.
  3. YouTube via yt-dlp `ytsearch` — prefers known archival channels
     (British Pathe, Periscope Film, US National Archives, ...).
     WARNING: YouTube items may be copyrighted; PD/CC sources are
     preferred and the log says so every run.

Lawal's rules baked in:
  - "zero ai clip or images": only genuine footage; every clip's check
    frames must be eyeballed before the documentary ships.
  - never reuse a visual within one documentary: source ids AND file
    hashes are deduped across segments.
  - narration text is never touched — queries are derived read-only.

Each accepted clip is trimmed to ~6s (H.264 mp4, audio stripped — the
documentary's narration/SFX carry the sound), verified with ffprobe
(video stream, duration >= 3s, width >= 320), and 3 check frames are
extracted into clip_frames/ for human verification.

Output clips.json:
  {"clips": [{"segment": i, "file": abs path, "url": source page,
              "download_url": ..., "license": ..., "duration": ...,
              "source": "internet_archive|wikimedia_commons|youtube",
              "source_id": ..., "query": ...}, ...]}

Usage:
  python3 clips.py narration.json --out clips.json [--max-per-seg 1]
                                  [--workdir clip_work] [--segments 0,1,2]
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

# Same stopword list as history-sourcer/segment.py (kept in sync manually).
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "were", "was",
    "are", "has", "have", "had", "will", "would", "their", "there", "they",
    "them", "then", "than", "when", "which", "what", "into", "over", "under",
    "about", "after", "before", "during", "between", "through", "while",
    "also", "just", "only", "its", "his", "her", "our", "your", "but",
    "not", "all", "can", "one", "two", "who", "how", "out", "off", "its",
    "been", "being", "such", "more", "most", "some", "than", "these",
    "those", "very", "much", "many", "well", "back", "down", "still",
}

UA = {"User-Agent": "history-video/1.0 (documentary clip sourcer)"}
TRIM_SECONDS = 6.0

# YouTube channels whose uploads are most likely genuine archival footage.
ARCHIVAL_CHANNEL_HINTS = (
    "british path", "pathe", "periscope film", "criticalpast",
    "national archives", "ap archive", "associated press",
    "archive film", "public domain", "prelinger",
)

# Internet Archive collections treated as public-domain unless the item
# metadata says otherwise.
PD_COLLECTIONS = {"prelinger", "us_national_archives"}

# YouTube's web player currently demands sign-in from datacenter IPs; the
# android player client still serves files anonymously. If YouTube ever
# closes that too, downloads fail fast (auth error) and the source is
# skipped for the rest of the run instead of retrying every candidate.
YT_PLAYER_ARGS = ["--extractor-args", "youtube:player_client=android"]
YOUTUBE_AUTH_ERRORS = ("sign in", "cookies", "log in", "login")
youtube_dead = False  # set on first auth failure; skip remaining candidates


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def derive_query(text, max_terms=8):
    """Search terms from narration text, read-only (text never modified):
    proper nouns first (original order), then other significant words
    longest-first — long content words ("surrounded") beat filler
    adjectives ("entire") for archive search. Sentence-initial
    capitalized words ("Entire", "Hundreds") are NOT proper nouns — only
    mid-sentence capitals count."""
    # words that start a sentence: the very first token + after [.!?] runs
    sent_starts = set(
        m.group(1).lower()
        for m in re.finditer(r"(?:^|[.!?]\s+)([A-Za-z][A-Za-z0-9'\-]*)", text)
    )
    seen_lows = set()
    seen = []
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text):
        low = tok.lower().strip("'")
        if len(low) < 3 or low in STOPWORDS or low in seen_lows:
            continue
        seen_lows.add(low)
        proper = tok[0].isupper() and low not in sent_starts
        seen.append((proper, low))
    proper, other = [], []
    for i, (p, w) in enumerate(seen):
        (proper if p else other).append((w, i))
    other.sort(key=lambda t: (-len(t[0]), t[1]))
    terms = [w for w, _ in proper] + [w for w, _ in other]
    return " ".join(terms[:max_terms])

def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def download(url, dest, timeout=600):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp, \
            open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def ffprobe_info(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height:format=duration",
         "-of", "json", path],
        capture_output=True, text=True, timeout=60)
    info = json.loads(out.stdout or "{}")
    vstreams = [s for s in info.get("streams", [])
                if s.get("codec_type") == "video"]
    dur = float(info.get("format", {}).get("duration") or 0)
    width = vstreams[0].get("width", 0) if vstreams else 0
    return {"has_video": bool(vstreams), "duration": dur, "width": width}


def file_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Source 1: Internet Archive
# ---------------------------------------------------------------------------

def ia_license_ok(meta):
    md = meta.get("metadata", {})
    lic = (md.get("licenseurl") or "")
    low = lic.lower()
    if "creativecommons.org" in low or "publicdomain" in low:
        # Only commercial-use, derivative-allowing licenses: documentaries
        # get monetized and re-edited, so NC/ND variants are out.
        if "/by-nc" in low or "/by-nd" in low:
            return None
        return lic
    colls = set(md.get("collection", []))
    if isinstance(md.get("collection"), str):
        colls = {md["collection"]}
    if colls & PD_COLLECTIONS:
        return "public domain (Internet Archive %s collection)" % (
            sorted(colls & PD_COLLECTIONS)[0])
    return None


def ia_pick_file(meta):
    files = meta.get("files", [])
    cands = []
    for f in files:
        name = f.get("name", "")
        if not re.search(r"\.(mp4|m4v|mov|ogv|webm)$", name, re.I):
            continue
        if f.get("private"):
            continue
        cands.append(f)
    if not cands:
        return None
    # Prefer the small 512kb derivative; else the smallest file >200KB.
    for f in cands:
        if f["name"].lower().endswith("_512kb.mp4"):
            return f
    small = [f for f in cands if int(f.get("size", 0)) > 200_000]
    pool = small or cands
    return min(pool, key=lambda f: int(f.get("size", 0)))


# Skip items whose titles flag graphic/disturbing content — never the
# right pick for an automatic background clip.
GRAPHIC_HINTS = ("graphic", "execution", "executed", "concentration camp",
                 "holocaust", "autopsy", "corpse")


def relevance(title, terms):
    """Term-overlap score between a candidate title and the query terms."""
    t = (title or "").lower()
    return sum(1 for w in terms if w in t)


def ia_candidates(query, limit=6):
    terms = query.split()[:5]  # distinctive terms only; full 8 is too strict
    docs = []
    # Loosen the AND progressively: 5 terms, then 3, then 2.
    for n in (5, 3, 2):
        t = terms[:n]
        q = "mediatype:movies AND (" + " AND ".join(t) + ")"
        params = urllib.parse.urlencode({
            "q": q, "fl[]": ["identifier", "title"],
            "rows": 30, "output": "json", "sort[]": "downloads desc",
        }, doseq=True)
        try:
            data = http_get_json(
                "https://archive.org/advancedsearch.php?" + params)
        except Exception as e:
            log(f"  [ia] search failed: {e}")
            return []
        docs = data.get("response", {}).get("docs", [])
        if docs:
            terms = t
            break
    # Rank by subject match first (downloads only break ties): the most
    # downloaded WWII item is rarely the one about this segment.
    # NOTE: no title-relevance filter here. IA's search already AND-matches
    # the query against full metadata (title+description); a title like
    # "Nazis War On Russia, 1941/06/23" shares no words with a Barbarossa
    # query yet is a perfect hit. License + graphic filters + human
    # check-frames do the weeding.
    ranked = []
    for d in docs:
        title = d.get("title") or ""
        if isinstance(title, list):
            title = " ".join(str(t) for t in title)
        if any(h in title.lower() for h in GRAPHIC_HINTS):
            continue
        ranked.append((relevance(title, terms), d))
    ranked.sort(key=lambda t: t[0], reverse=True)
    out = []
    for _, d in ranked[:limit * 2]:
        if len(out) >= limit:
            break
        ident = d.get("identifier")
        if not ident:
            continue
        try:
            meta = http_get_json(
                f"https://archive.org/metadata/{ident}", timeout=30)
        except Exception as e:
            log(f"  [ia] metadata failed for {ident}: {e}")
            continue
        lic = ia_license_ok(meta)
        if not lic:
            continue
        f = ia_pick_file(meta)
        if not f:
            continue
        dl = ("https://archive.org/download/%s/%s"
              % (ident, urllib.parse.quote(f["name"])))
        out.append({
            "source": "internet_archive",
            "source_id": f"ia:{ident}",
            "title": d.get("title") or ident,
            "url": f"https://archive.org/details/{ident}",
            "download_url": dl,
            "license": lic,
        })
    return out


# ---------------------------------------------------------------------------
# Source 2: Wikimedia Commons
# ---------------------------------------------------------------------------

def commons_candidates(query, limit=6):
    terms = query.split()[:3]  # Commons search is finicky; keep it broad
    params = urllib.parse.urlencode({
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": "filetype:video " + " ".join(terms),
        "gsrnamespace": 6, "gsrlimit": 30,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime",
        "iiextmetadatafilter": "LicenseShortName",
    })
    try:
        data = http_get_json(
            "https://commons.wikimedia.org/w/api.php?" + params)
    except Exception as e:
        log(f"  [commons] search failed: {e}")
        return []
    pages = (data.get("query") or {}).get("pages", {})
    scored = []
    for pid, p in pages.items():
        ii = (p.get("imageinfo") or [{}])[0]
        lic = ((ii.get("extmetadata") or {}).get("LicenseShortName") or {}
               ).get("value", "")
        ok = ("Public domain" in lic or "CC0" in lic
              or lic.startswith("CC BY"))
        if not ok:
            continue
        mime = ii.get("mime", "")
        if not mime.startswith("video/"):
            continue
        url = ii.get("url", "")
        if not url:
            continue
        title = p.get("title", "")
        if any(h in title.lower() for h in GRAPHIC_HINTS):
            continue
        rel = relevance(title, terms)
        if rel == 0:
            continue  # Commons full-text is weak; title must match
        # subject match first, then smaller files (faster, still real)
        scored.append((rel, -int(ii.get("size", 0)), {
            "source": "wikimedia_commons",
            "source_id": f"commons:{pid}",
            "title": title,
            "url": ii.get("descriptionurl", ""),
            "download_url": url.split("?")[0],
            "license": lic,
        }))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [s for _, _, s in scored[:limit]]


# ---------------------------------------------------------------------------
# Source 3: YouTube (yt-dlp) — last resort; may be copyrighted.
# ---------------------------------------------------------------------------

def youtube_candidates(query, limit=8):
    if youtube_dead:
        return []
    # YouTube's fuzzy search does best with a SHORT query: the most
    # distinctive terms plus "archival footage". The full 8-term query
    # over-constrains it and returns junk.
    short = " ".join(query.split()[:4])
    cmd = (["yt-dlp"] + YT_PLAYER_ARGS +
           [f"ytsearch{limit}:{short} archival footage",
            "--flat-playlist", "--no-warnings",
            "--print", "%(id)s\t%(title)s\t%(channel)s\t%(duration)s"])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        log("  [youtube] yt-dlp not installed, skipping")
        return []
    except subprocess.TimeoutExpired:
        log("  [youtube] search timed out")
        return []
    cands = []
    terms = query.split()
    for line in (out.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        vid, title, channel, dur = parts[0], parts[1], parts[2], parts[3]
        try:
            dur_s = float(dur)
        except ValueError:
            continue
        if dur_s < 20:  # need room to trim a real 6s slice
            continue
        hay = (title + " " + channel).lower()
        if relevance(hay, terms) < 2:
            continue  # title must share 2+ query words: kills junk like
        # modern news clips that happen to match one word ("Ukraine")
        archival = any(h in hay for h in ARCHIVAL_CHANNEL_HINTS)
        # archival channel first, then SHORTER videos first: we only need
        # a 6s slice, and a 2-minute reel downloads far faster than a
        # 3-hour compilation.
        cands.append(((0 if archival else 1, dur_s), {
            "source": "youtube",
            "source_id": f"yt:{vid}",
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "download_url": f"https://www.youtube.com/watch?v={vid}",
            "license": ("unknown — YouTube upload; verify rights before "
                        "publishing"),
            "channel": channel,
        }))
    cands.sort(key=lambda t: t[0])
    return [c for _, c in cands[:limit]]


def youtube_download(page_url, dest_raw):
    global youtube_dead
    # Combined progressive format ("b") instead of bv*+ba: separate DASH
    # streams get throttled/reset for datacenter IPs while the progressive
    # host serves fine. --download-sections fetches only the first 5
    # minutes — the trim takes 6s from at most 10s in, so there is no
    # reason to pull a whole 3-hour compilation. Some videos fail at
    # 720p (bad signature) but work at 480p/360p: walk down the ladder.
    formats = ["b[height<=720]/best", "b[height<=480]/best",
               "b[height<=360]/best", "b/best"]
    last_err = ""
    for fmt in formats:
        for f in (dest_raw, dest_raw + ".mp4"):
            if os.path.exists(f):
                os.remove(f)
        cmd = (["yt-dlp", "--no-warnings"] + YT_PLAYER_ARGS +
               ["-f", fmt,
                "--download-sections", "*00:00-05:00",
                "--force-keyframes-at-cuts",
                "-o", dest_raw, page_url])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        err = (r.stderr or "").lower()
        if r.returncode != 0 and any(h in err for h in YOUTUBE_AUTH_ERRORS):
            youtube_dead = True
            raise RuntimeError(
                "YouTube now requires sign-in for downloads; "
                "skipping YouTube for the rest of this run")
        if os.path.exists(dest_raw) and os.path.getsize(dest_raw) > 0:
            return
        # yt-dlp may append its own extension
        alt = dest_raw + ".mp4"
        if os.path.exists(alt) and os.path.getsize(alt) > 0:
            os.rename(alt, dest_raw)
            return
        last_err = (r.stderr or "")[-300:]
    raise RuntimeError("yt-dlp failed: " + last_err)


# ---------------------------------------------------------------------------
# Trim / verify / check-frames
# ---------------------------------------------------------------------------

def trim_clip(raw, dest, want=TRIM_SECONDS):
    info = ffprobe_info(raw)
    if not info["has_video"]:
        raise RuntimeError("no video stream in download")
    dur = info["duration"]
    # Skip ahead: archival reels and YouTube compilations usually open on
    # leaders, fades or title cards; the meat is a little way in. Skip
    # 5% of the runtime (3s minimum, 10s maximum) — but never so far that
    # we can't take a full 6s slice (section downloads can be short).
    offset = min(10.0, max(3.0, dur * 0.05), max(0.0, dur - 6.0))
    take = min(want, max(0.0, dur - offset))
    if take < 3.0:
        raise RuntimeError(f"source too short ({dur:.1f}s)")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-ss", f"{offset:.2f}", "-t", f"{take:.2f}", "-i", raw,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p",
         # min() needs its comma quoted or the filtergraph splits there
         "-vf", "scale='min(1280,iw)':-2",
         "-an",  # scene backgrounds are silent; narration/SFX carry sound
         dest],
        check=True, timeout=300)
    v = ffprobe_info(dest)
    if not (v["has_video"] and v["duration"] >= 3.0 and v["width"] >= 320):
        raise RuntimeError(f"trimmed clip failed verification: {v}")
    return v["duration"]


def extract_check_frames(clip, frames_dir, seg_idx, duration):
    os.makedirs(frames_dir, exist_ok=True)
    paths = []
    for n, frac in enumerate((0.25, 0.5, 0.75), start=1):
        t = duration * frac
        out = os.path.join(frames_dir, f"clip_{seg_idx:02d}_f{n}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}",
             "-i", clip, "-frames:v", "1", "-q:v", "3", out],
            check=True, timeout=60)
        paths.append(out)
    return paths


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def find_clips_for_segment(idx, text, workdir, frames_dir, used_ids,
                           used_hashes, max_per_seg):
    query = derive_query(text)
    log(f"[{idx:02d}] query: {query!r}")
    found = []

    def try_source(name, cands):
        for c in cands:
            if len(found) >= max_per_seg:
                return
            if c["source_id"] in used_ids:
                log(f"  [{name}] skip duplicate {c['source_id']}")
                continue
            log(f"  [{name}] trying {c['source_id']} — {c['title'][:60]}")
            raw = os.path.join(workdir, f"clip_{idx:02d}_{len(found)}_raw.bin")
            clip = os.path.join(
                workdir, f"clip_{idx:02d}_{len(found)}.mp4")
            try:
                if c["source"] == "youtube":
                    youtube_download(c["download_url"], raw)
                else:
                    download(c["download_url"], raw)
                dur = trim_clip(raw, clip)
                h = file_sha1(clip)
                if h in used_hashes:
                    log(f"  [{name}] duplicate file hash, skipping")
                    continue
                frames = extract_check_frames(clip, frames_dir, idx, dur)
                used_ids.add(c["source_id"])
                used_hashes.add(h)
                found.append({
                    "segment": idx,
                    "file": os.path.abspath(clip),
                    "url": c["url"],
                    "download_url": c["download_url"],
                    "license": c["license"],
                    "duration": round(dur, 2),
                    "source": c["source"],
                    "source_id": c["source_id"],
                    "query": query,
                    "check_frames": [os.path.abspath(p) for p in frames],
                })
                log(f"  [{name}] OK {clip} ({dur:.1f}s, {c['license'][:50]})")
            except Exception as e:
                log(f"  [{name}] failed {c['source_id']}: {e}")
            finally:
                if os.path.exists(raw):
                    os.remove(raw)

    log("  source: Internet Archive ...")
    try_source("ia", ia_candidates(query))
    if len(found) < max_per_seg:
        log("  source: Wikimedia Commons ...")
        try_source("commons", commons_candidates(query))
    if len(found) < max_per_seg:
        log("  source: YouTube (may be copyrighted — PD/CC preferred) ...")
        try_source("youtube", youtube_candidates(query))
    return found


def main():
    ap = argparse.ArgumentParser(
        description="Find real archival video clips for narration segments")
    ap.add_argument("narration", help="narration.json from narrate.py")
    ap.add_argument("--out", required=True, help="output clips.json path")
    ap.add_argument("--max-per-seg", type=int, default=1,
                    help="clips to keep per segment (default 1)")
    ap.add_argument("--workdir", default="clip_work",
                    help="dir for trimmed clips + check frames")
    ap.add_argument("--segments", default=None,
                    help="comma-separated segment indexes to process "
                         "(default: all)")
    args = ap.parse_args()

    with open(args.narration, encoding="utf-8") as fh:
        doc = json.load(fh)
    segments = doc["segments"]
    if args.segments:
        want = {int(x) for x in args.segments.split(",")}
        segments = [s for s in segments if s["index"] in want]
    if not segments:
        sys.exit("error: no segments to process")

    workdir = os.path.abspath(args.workdir)
    frames_dir = os.path.join(workdir, "clip_frames")
    os.makedirs(workdir, exist_ok=True)

    log("NOTE: YouTube results may be copyrighted. Public-domain / CC "
        "sources (Internet Archive, Wikimedia Commons) are always tried "
        "first; verify rights before publishing anything sourced from "
        "YouTube.")

    used_ids, used_hashes = set(), set()
    clips = []
    for seg in segments:
        idx = seg["index"]
        found = find_clips_for_segment(
            idx, seg.get("text", ""), workdir, frames_dir,
            used_ids, used_hashes, args.max_per_seg)
        if not found:
            log(f"[{idx:02d}] NO CLIP FOUND — segment keeps its still image")
        clips.extend(found)

    out = {"clips": clips}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    log(f"wrote {args.out}: {len(clips)} clips for "
        f"{len({c['segment'] for c in clips})} segments")
    log(f"CHECK FRAMES in {frames_dir} — eyeball every clip before shipping.")


if __name__ == "__main__":
    main()
