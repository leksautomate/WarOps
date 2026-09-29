#!/usr/bin/env python3
"""Fetch real archival footage clips from YouTube (BBC/AP/Pathe preferred).

Footage playbook (modeled on commercial faceless-video pipelines):
  1. search YouTube per narration beat (yt-dlp ytsearch, no API key)
  2. skip Shorts, reaction videos and watermarked stock sellers
  3. rank official archives first: BBC, Associated Press / AP Archive,
     British Pathe
  4. download ONLY the chosen seconds (--download-sections)
  5. snap the trim to genuine cuts (ffmpeg scene detection)
  6. crop black pillarbox/letterbox bars (cropdetect)
  7. strip audio (clips play muted under narration)
  8. cache shot logs per video id; refuse to reuse an overlapping span
     twice (dedup registry)

IMPORTANT - Lawal's YouTube-safety rule: YouTube-sourced clips are NEVER
shown full-screen. The renderer (HistoryDoc.tsx) always frames them over
the looping grid background, fitted not stretched, never edge-to-edge.
This script only FETCHES clips; it changes nothing about how they are
displayed.

Zero AI-generated visuals: every frame here comes from a real uploaded
video. If YouTube is unreachable the script says so honestly and exits
non-zero - it never invents candidate lists.

Usage:
  yt_footage.py --query "..." --out <dir> [--max 6] [--section 83-91]
                [--pick 0] [--registry <path>]

Prints a JSON manifest to stdout:
  {video_id, url, title, channel, preferred, src_start, src_end,
   snapped_start, snapped_end, file}
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- deps

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPS_DIR = os.path.join(PROJECT_DIR, ".deps")
if os.path.isdir(DEPS_DIR) and DEPS_DIR not in sys.path:
    sys.path.insert(0, DEPS_DIR)

CACHE_DIR = os.path.join(PROJECT_DIR, ".cache", "shotlog")


def _sanitize_proxy_env():
    """Drop IPv6 literals from no_proxy.

    The vendored httpx (via huggingface-hub, and some yt-dlp paths) crashes
    parsing bracketed IPv6 entries like [::1] in NO_PROXY
    ("Invalid port: ':1]'"). IPv6 loopbacks are irrelevant for reaching
    YouTube, so they are dropped; everything else is kept.
    """
    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key, "")
        keep = [p.strip() for p in val.split(",") if p.strip() and ":" not in p]
        os.environ[key] = ",".join(keep)


_sanitize_proxy_env()

YTDLP = [
    sys.executable, "-m", "yt_dlp",
    "--compat-options", "no-certifi",  # use the egress proxy's CA bundle
    "--no-warnings",
    "--no-cache-dir",
]

# ---------------------------------------------------------------- filters

# YouTube Shorts: never usable as documentary footage
RE_SHORTS = re.compile(r"/shorts/", re.I)

# reaction / commentary-over-footage videos
RE_REACTION = re.compile(r"\breacts?\b|\breaction\b", re.I)

# stock libraries whose previews carry a watermark across the picture.
# (Deliberately does NOT match AP / BBC / Pathe - those are real archives.)
RE_STOCK = re.compile(
    r"pond5|shutterstock|getty\s?images?|critical\s?past|storyblocks|"
    r"videoblocks|artgrid|filmsupply|envato|videvo|buyout\s?footage|"
    r"stock\s?footage|royalty[\s-]*free|footage\s?for\s?pro",
    re.I,
)

# official archives whose uploads are the original footage - ranked first
RE_ARCHIVE = re.compile(
    r"pathe|path\u00e9|british\s?path|associated\s?press|ap\s?archive|"
    r"\bbbc\b|bbc\s?archive|reuters|nara|national\s?archives",
    re.I,
)

# query bias: nudge plain queries toward archival material
RE_ARCHIVAL_Q = re.compile(r"archiv|footage|newsreel|\breel\b", re.I)

MIN_DURATION_S = 8.0      # shorter than this is a teaser, not footage
SNAP_WINDOW_S = 1.5       # snap trim points to a real cut this close
SCENE_THRESHOLD = 0.35    # ffmpeg select='gt(scene,...)' cut threshold
PAD_S = 3.0               # extra seconds fetched around the section, for snapping


# ---------------------------------------------------------------- youtube

def _run_ytdlp(args, timeout=180):
    env = dict(os.environ)
    # make sure the vendored yt-dlp is importable in the child
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = DEPS_DIR + (os.pathsep + pp if pp else "")
    return subprocess.run(
        YTDLP + args, capture_output=True, text=True, timeout=timeout, env=env)


def search(query, max_n=6):
    """Ranked candidate list for a query. Raises RuntimeError if YouTube
    is unreachable (never returns fabricated results)."""
    biased = query if RE_ARCHIVAL_Q.search(query) else query + " archive footage"
    cache_key = hashlib.sha1(biased.encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(CACHE_DIR, "search", cache_key + ".json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return json.load(fh)

    fetch_n = max_n + 6  # over-fetch: filtering may drop several
    try:
        proc = _run_ytdlp([
            "--flat-playlist", "--dump-json", f"ytsearch{fetch_n}:{biased}"])
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise RuntimeError(f"YouTube search failed to run: {e}")
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        raise RuntimeError(
            "YouTube unreachable: " + (" | ".join(err[-2:]) if err else
                                       f"yt-dlp exited {proc.returncode}"))

    candidates = []
    for line in proc.stdout.splitlines():
        try:
            v = json.loads(line)
        except ValueError:
            continue
        vid = v.get("id")
        if not vid:
            continue
        title = v.get("title") or ""
        channel = v.get("channel") or v.get("uploader") or ""
        url = v.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
        blob = f"{title} | {channel}"
        try:
            duration = float(v.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        if RE_SHORTS.search(url):
            continue  # YouTube Short
        if RE_REACTION.search(title):
            continue  # reaction video
        if RE_STOCK.search(blob):
            continue  # watermarked stock seller
        if duration and duration < MIN_DURATION_S:
            continue
        preferred = bool(RE_ARCHIVE.search(blob))
        candidates.append({
            "video_id": vid,
            "url": url,
            "title": title,
            "channel": channel,
            "duration": duration,
            "preferred": preferred,
        })

    # official archives first, then YouTube's relevance order
    candidates.sort(key=lambda c: (not c["preferred"],))
    ranked = candidates[:max_n]

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(ranked, fh, ensure_ascii=False, indent=1)
    return ranked


# ---------------------------------------------------------------- registry

def load_registry(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
                return data if isinstance(data, list) else []
            except ValueError:
                return []
    return []


def check_overlap(registry, video_id, start, end):
    """Return the conflicting entry if this span overlaps a used one."""
    for e in registry:
        if e.get("video_id") != video_id:
            continue
        s2, e2 = float(e.get("start", 0)), float(e.get("end", 0))
        if start < e2 - 0.5 and s2 < end - 0.5:
            return e
    return None


def record_use(registry_path, entry):
    reg = load_registry(registry_path)
    reg.append(entry)
    with open(registry_path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- ffmpeg

def _ffprobe_start(path):
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=start_time",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60)
        return float(p.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired):
        return 0.0


def detect_cuts(path):
    """Real cut points (seconds, file time) via ffmpeg scene detection."""
    p = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path,
         "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=300)
    cuts = []
    for m in re.finditer(r"pts_time:([\d.]+)", p.stderr):
        try:
            cuts.append(float(m.group(1)))
        except ValueError:
            pass
    # de-duplicate near-identical hits
    uniq = []
    for c in sorted(cuts):
        if not uniq or c - uniq[-1] > 0.2:
            uniq.append(c)
    return uniq


def snap_to_cuts(point, cuts, window=SNAP_WINDOW_S):
    """Nearest real cut within `window` seconds, else the point itself."""
    best, best_d = point, window + 1e-9
    for c in cuts:
        d = abs(c - point)
        if d < best_d:
            best, best_d = c, d
    return round(best, 3)


def detect_crop(path, seek, probe_len=6.0):
    """Most common cropdetect result over a few seconds; None if the
    frame is already full-bleed."""
    p = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{seek:.2f}", "-t", f"{probe_len:.1f}",
         "-i", path, "-vf", "cropdetect=limit=28:round=2:reset=0",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    votes = {}
    for m in re.finditer(r"crop=(\d+):(\d+):(\d+):(\d+)", p.stderr):
        key = tuple(int(x) for x in m.groups())
        votes[key] = votes.get(key, 0) + 1
    if not votes:
        return None
    (cw, ch, cx, cy), _n = max(votes.items(), key=lambda kv: kv[1])
    return (cw, ch, cx, cy)


def ffprobe_dims(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=60)
    try:
        w, h = p.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except (ValueError, IndexError):
        return 0, 0


# ---------------------------------------------------------------- fetch

def _ffprobe_duration(path):
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60)
        return float(p.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired):
        return 0.0


def _tail_ok(path):
    """True if the last seconds of the file actually decode.

    ffprobe trusts the mp4 header, which lies on a truncated download
    (216KB file claiming 480s). Decoding the tail catches that: a cut-off
    mdat cannot produce its final frames.
    """
    try:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-sseof", "-2", "-i", path,
             "-frames:v", "5", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False
    return p.returncode == 0 and "Invalid data found" not in p.stderr


def _run_ytdlp(args, timeout=180):
    env = dict(os.environ)
    # make sure the vendored yt-dlp is importable in the child
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = DEPS_DIR + (os.pathsep + pp if pp else "")
    return subprocess.run(
        YTDLP + args, capture_output=True, text=True, timeout=timeout, env=env)


def _ytdlp_base_args():
    # the android player client is not bot-walled the way the web
    # client is from datacenter/proxied IPs
    return [
        "-f", "bv*[height<=480]+ba/b[height<=480]/b",
        "--merge-output-format", "mp4",
        "--retries", "10",
        "--extractor-args", "youtube:player_client=android",
    ]


def download_full(video_id, dest, attempts=3):
    """Download the whole video (<=480p mp4) with yt-dlp's native HTTP
    downloader, which survives this egress proxy far better than ffmpeg's
    streaming downloader. Retried; raises RuntimeError on failure."""
    args = _ytdlp_base_args() + [
        "-o", dest,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    last_err = ""
    for attempt in range(1, attempts + 1):
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError:
            pass
        proc = _run_ytdlp(args, timeout=1200)
        if proc.returncode == 0 and os.path.exists(dest):
            if _ffprobe_duration(dest) > 1.0 and _tail_ok(dest):
                return dest
            last_err = "downloaded file is truncated (tail does not decode)"
        else:
            err = (proc.stderr or "").strip().splitlines()
            last_err = " | ".join(err[-3:]) if err else "no output file"
        print(f"download attempt {attempt}/{attempts} failed "
              f"({last_err}); retrying...", file=sys.stderr)
    raise RuntimeError(
        f"download failed for {video_id} after {attempts} attempts: "
        f"{last_err}. YouTube is likely rate-limiting this IP - "
        f"wait and retry")


def download_padded(video_id, pad_start, pad_end, dest, attempts=3):
    """Download only the padded span via --download-sections (ffmpeg).

    Fallback for long videos where fetching the whole file is wasteful.
    Less reliable through this proxy than download_full (ffmpeg's
    streaming downloader gets its connection cut); retried, and the
    result's duration is validated so a truncated section can never
    silently produce a short clip.
    """
    args = _ytdlp_base_args() + [
        "--download-sections", f"*{pad_start:.1f}-{pad_end:.1f}",
        # the proxy cuts idle googlevideo streams; let ffmpeg reconnect
        "--downloader-args", "ffmpeg:-reconnect 1 -reconnect_streamed 1 "
                             "-reconnect_delay_max 5",
        "-o", dest,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    last_err = ""
    for attempt in range(1, attempts + 1):
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError:
            pass
        proc = _run_ytdlp(args, timeout=900)
        if proc.returncode == 0 and os.path.exists(dest):
            got = _ffprobe_duration(dest)
            want = pad_end - pad_start
            if got >= want - 1.0 and _tail_ok(dest):
                return dest
            last_err = (f"downloaded section is truncated ({got:.1f}s of "
                        f"{want:.1f}s)")
        else:
            err = (proc.stderr or "").strip().splitlines()
            last_err = " | ".join(err[-3:]) if err else "no output file"
        print(f"download attempt {attempt}/{attempts} failed "
              f"({last_err}); retrying...", file=sys.stderr)
    raise RuntimeError(
        f"download failed for {video_id} after {attempts} attempts: "
        f"{last_err}. YouTube is likely rate-limiting this IP - "
        f"wait and retry")


# full-video downloads stay small (<=480p); beyond this, fetch sections
FULL_DOWNLOAD_MAX_S = 120.0


def fetch_clip(candidate, section, out_dir, registry_path, project=""):
    vid = candidate["video_id"]
    duration = candidate.get("duration") or 0.0
    s_req, e_req = section
    if duration and e_req > duration:
        raise RuntimeError(
            f"section {s_req}-{e_req}s exceeds video duration {duration:.0f}s")
    if e_req <= s_req:
        raise RuntimeError(f"empty section {s_req}-{e_req}")

    conflict = check_overlap(load_registry(registry_path), vid, s_req, e_req)
    if conflict:
        raise RuntimeError(
            f"span {s_req}-{e_req}s of {vid} overlaps an already-used span "
            f"{conflict.get('start')}-{conflict.get('end')}s "
            f"(project '{conflict.get('project', '?')}', "
            f"file {conflict.get('file', '?')}). Pick another span or video.")

    os.makedirs(out_dir, exist_ok=True)
    final_path = os.path.join(
        out_dir, f"{vid}_s{int(s_req)}-e{int(e_req)}.mp4")

    # fetch: whole file for short videos (reliable), sections for long ones
    src_path = os.path.join(out_dir, f"{vid}_src.mp4")
    src_offset = 0.0  # source-time of the file's first frame
    if duration and duration > FULL_DOWNLOAD_MAX_S:
        pad_start = max(0.0, s_req - PAD_S)
        pad_end = e_req + PAD_S
        download_padded(vid, pad_start, pad_end, src_path)
        src_offset = pad_start
    else:
        download_full(vid, src_path)
    t0 = _ffprobe_start(src_path)

    # snap the requested span to genuine cuts (scene detection, file time
    # mapped back to source time)
    cuts = [round(src_offset + (c - t0), 3)
            for c in detect_cuts(src_path)]
    s_snap = snap_to_cuts(s_req, cuts)
    e_snap = snap_to_cuts(e_req, cuts)
    if e_snap <= s_snap:
        e_snap = e_req  # never collapse the clip; keep the request

    # black-bar crop, probed around the snapped span
    seek_src = max(0.0, s_snap - src_offset + t0)
    crop = detect_crop(src_path, seek_src)
    w, h = ffprobe_dims(src_path)
    vf = []
    if crop and w and h:
        cw, ch, cx, cy = crop
        if (cw, ch, cx, cy) != (w, h, 0, 0) and cw > w * 0.5 and ch > h * 0.5:
            vf.append(f"crop={cw}:{ch}:{cx}:{cy}")
    vf.append("setpts=PTS-STARTPTS")
    dur = round(e_snap - s_snap, 3)

    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y",
             "-ss", f"{seek_src:.3f}", "-i", src_path,
             "-t", f"{dur:.3f}",
             "-vf", ",".join(vf),
             "-an",  # clips play muted under narration
             "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
             final_path],
            check=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"final trim failed ({e}); source file may be "
                           f"corrupt - retry")

    # the snapped span must actually be there
    got = _ffprobe_duration(final_path)
    if got < dur - 1.0:
        raise RuntimeError(
            f"final trim is short ({got:.1f}s of {dur:.1f}s) - "
            f"source file may be corrupt; retry")

    try:
        os.remove(src_path)
    except OSError:
        pass

    # shot-log cache per video id
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, vid + ".json"), "w",
              encoding="utf-8") as fh:
        json.dump({
            "video_id": vid, "title": candidate["title"],
            "channel": candidate["channel"], "url": candidate["url"],
            "duration": duration, "preferred": candidate["preferred"],
            "cuts": cuts, "crop": list(crop) if crop else None,
        }, fh, ensure_ascii=False, indent=1)

    record_use(registry_path, {
        "video_id": vid, "start": s_snap, "end": e_snap,
        "project": project, "file": final_path,
        "title": candidate["title"],
    })

    return {
        "video_id": vid,
        "url": candidate["url"],
        "title": candidate["title"],
        "channel": candidate["channel"],
        "preferred": candidate["preferred"],
        "src_start": s_req,
        "src_end": e_req,
        "snapped_start": s_snap,
        "snapped_end": e_snap,
        "file": final_path,
    }


# ---------------------------------------------------------------- cli

def parse_section(text):
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[-:]\s*(\d+(?:\.\d+)?)\s*$", text or "")
    if not m:
        raise ValueError(f"bad --section {text!r}; want like 83-91")
    return float(m.group(1)), float(m.group(2))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fetch a real archival YouTube clip (BBC/AP/Pathe "
                    "preferred). Prints a JSON manifest to stdout.")
    ap.add_argument("--query", required=True,
                    help="footage search query, e.g. 'sherman tanks 1944'")
    ap.add_argument("--out", required=True,
                    help="directory for the clip (never /tmp)")
    ap.add_argument("--max", type=int, default=6,
                    help="candidates to rank (default 6)")
    ap.add_argument("--section", default=None,
                    help="seconds within the video, e.g. 83-91 "
                         "(default: first 8s)")
    ap.add_argument("--pick", type=int, default=0,
                    help="index into the ranked candidates (default 0)")
    ap.add_argument("--registry", default=None,
                    help="dedup registry path "
                         "(default <out>/youtube_used.json)")
    ap.add_argument("--project", default="",
                    help="project name recorded in the registry")
    args = ap.parse_args(argv)

    if os.path.abspath(args.out).startswith("/tmp"):
        print("refusing to download into /tmp (512MB tmpfs); "
              "use a project dir", file=sys.stderr)
        return 2
    registry = args.registry or os.path.join(args.out, "youtube_used.json")

    try:
        candidates = search(args.query, args.max)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not candidates:
        print(f"error: no usable candidates for query {args.query!r} "
              f"(all filtered or YouTube returned nothing)", file=sys.stderr)
        return 2
    if not (0 <= args.pick < len(candidates)):
        print(f"error: --pick {args.pick} out of range "
              f"(0..{len(candidates) - 1})", file=sys.stderr)
        for i, c in enumerate(candidates):
            print(f"  [{i}] {'[ARCHIVE] ' if c['preferred'] else ''}"
                  f"{c['title'][:70]} ({c['channel']})", file=sys.stderr)
        return 2

    candidate = candidates[args.pick]
    section = parse_section(args.section) if args.section else (0.0, 8.0)

    try:
        manifest = fetch_clip(candidate, section, os.path.abspath(args.out),
                              registry, project=args.project)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
