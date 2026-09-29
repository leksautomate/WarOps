#!/usr/bin/env python3
"""
render.py — build + render the history documentary with Remotion.

Pipeline:
    narration.json (narrate.py output)
      -> download each segment's image into public/images/
      -> copy each segment's MP3 into public/audio/
      -> vendor @remotion/sfx sounds into public/sfx/
      -> write props (segments with frame timings + orientation)
      -> npx remotion render -> out.mp4 (30fps)

Orientation rule (Lawal, 2026-09-23):
    script < 200 words -> 9:16 vertical  (1080x1920, shorts format)
    script >= 200 words -> 16:9 landscape (1920x1080)
Override with --orientation 16:9 / 9:16; threshold with --word-threshold.

Motion: Ken Burns zoom+pan on every image (alternating direction).
Portrait overlays: when the narration names a person, their licensed
archival portrait slides in as a framed photo, timed to the mention.
SFX (@remotion/sfx, vendored locally):
    shutter-old.wav  when a portrait photo appears (genuine photo reveal)
    whoosh.wav       on scene transitions (non-map segments)
    page-turn.wav    on map/document reveals
Captions: narration text, bottom bar, fade in/out.

Usage:
    python3 render.py narration.json --out midway.mp4
    python3 render.py narration.json --overlays overlays.json --out video.mp4
"""

# NOTE: keep in sync with src/overlays.tsx + OVERLAY_DIRECTOR.md

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

FPS = 30
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
from wordclock import get_word_timings  # noqa: E402  (needs scripts/ on path)

# @remotion/sfx sounds, vendored locally so renders never hit the network.
SFX = {
    "whoosh.wav": "https://remotion.media/whoosh.wav",
    "shutter-old.wav": "https://remotion.media/shutter-old.wav",
    "page-turn.wav": "https://remotion.media/page-turn.wav",
}

MAP_HINTS = ("map", "chart", "diagram", "document", "letter", "treaty",
             "newspaper", "poster", "plan ")


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "history-video/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def rasterize_svg_url(url, width=1920):
    """Wikimedia SVG -> server-rendered PNG thumbnail.

    Neither PIL nor this ffmpeg build rasterizes SVG, so rewrite
    upload.wikimedia.org ... .svg URLs to the equivalent
    /thumb/.../<width>px-....svg.png rendition.
    """
    base = url.split("?", 1)[0]
    if not base.lower().endswith(".svg"):
        return url
    m = re.match(
        r"https://upload\.wikimedia\.org/wikipedia/commons/"
        r"([0-9a-f])/([0-9a-f]{2})/([^/]+)$",
        base,
    )
    if not m:
        return url
    h1, h2, fname = m.groups()
    # Wikimedia only rasterizes SVGs at fixed widths (HTTP 400 otherwise);
    # pick the nearest allowed width (1280 verified working).
    allowed = (320, 640, 800, 1280, 2560)
    w = min(allowed, key=lambda a: (abs(a - width), a))
    return (
        f"https://upload.wikimedia.org/wikipedia/commons/thumb/"
        f"{h1}/{h2}/{fname}/{w}px-{fname}.png"
    )


def normalize_image(src, dest, max_side=1920):
    """Convert any decodable image (incl. SVG/PNG/WebP) to a bounded JPEG."""
    from PIL import Image
    try:
        img = Image.open(src)
        img.draft("RGB", (max_side, max_side))
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        img.save(dest, "JPEG", quality=88)
        return
    except Exception:
        pass  # e.g. SVG: fall through to ffmpeg
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src,
         "-vf", f"scale={max_side}:-2", "-q:v", "3", dest],
        check=True, timeout=300,
    )


def probe_duration(path):
    """Audio/video duration in seconds via ffprobe (0.0 on failure)."""
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(p.stdout.strip())
    except Exception:
        return 0.0


def trim_silence(src):
    """Trim leading/trailing silence from a narration MP3, in place.

    Caption phrases are timed as fractions of the segment, so frame 0 must
    be (nearly) the first spoken word — otherwise every caption runs ahead
    of the voice. Returns the trimmed duration in seconds.
    """
    tmp = src + ".trim.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-af",
         "silenceremove=start_periods=1:start_threshold=-50dB:"
         "start_silence=0.05,areverse,"
         "silenceremove=start_periods=1:start_threshold=-50dB:"
         "start_silence=0.05,areverse",
         "-c:a", "libmp3lame", "-b:a", "128k", tmp],
        check=True, timeout=120)
    orig = probe_duration(src)
    new = probe_duration(tmp)
    if orig > 0 and new > 0.7 * orig:  # sanity: never destroy the audio
        os.replace(tmp, src)
        return new
    if os.path.exists(tmp):
        os.remove(tmp)
    return orig


def placeholder_image(dest, width=1920, height=1080):
    """Dark archival plate for segments with no licensed image.

    The composition's Ken Burns drift, vignette, and film grain play
    over it, so it reads as an intentional interstitial, not a hole.
    """
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), (16, 16, 18))
    d = ImageDraw.Draw(img)
    # faint centered radial lift
    for r in range(340, 0, -4):
        v = 16 + int(14 * (1 - r / 340))
        d.ellipse([width // 2 - r * 2, height // 2 - r,
                   width // 2 + r * 2, height // 2 + r],
                  fill=(v, v, v + 2))
    img.save(dest, "JPEG", quality=88)


MUSIC_DIR = os.path.join(PROJECT_DIR, "bg_music")


def pick_music_track(choice):
    """Resolve --music to a track path, or None for 'off'/empty folder."""
    if choice == "off" or not os.path.isdir(MUSIC_DIR):
        return None
    tracks = sorted(f for f in os.listdir(MUSIC_DIR)
                    if f.lower().endswith((".mp3", ".wav", ".m4a", ".ogg")))
    if not tracks:
        return None
    if choice == "random":
        import random
        return os.path.join(MUSIC_DIR, random.choice(tracks))
    for t in tracks:
        if t == choice or os.path.splitext(t)[0] == choice:
            return os.path.join(MUSIC_DIR, t)
    print(f"music: '{choice}' not found in bg_music/ — skipping",
          file=sys.stderr)
    return None


def mean_volume_db(path):
    """Mean audio level in dB via ffmpeg volumedetect; None if unmeasurable."""
    p = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path,
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=600)
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", p.stderr)
    return float(m.group(1)) if m else None


def mix_bg_music(video_path, track_path):
    """Duck a music bed under the narration and mux it into the video.

    The track loops to the video length, plays at a bed level set
    RELATIVE to the measured narration loudness (music ~6dB under the
    voice — Frontier 5.1's approach), and ducks further whenever the
    narrator speaks (sidechain keyed off the narration) — same approach
    as the reels batch.
    """
    bed = 0.16
    nar_db = mean_volume_db(video_path)
    mus_db = mean_volume_db(track_path)
    if nar_db is not None and mus_db is not None:
        gain_db = (nar_db - 6.0) - mus_db
        bed = min(0.5, max(0.05, 10 ** (gain_db / 20)))
        print(f"music: narration {nar_db:.1f}dB, track {mus_db:.1f}dB "
              f"-> bed volume {bed:.3f} (relative, -6dB under voice)",
              file=sys.stderr)
    else:
        print(f"music: loudness probe failed, bed volume {bed} (fixed "
              f"fallback)", file=sys.stderr)
    tmp = video_path + ".music.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-i", video_path, "-stream_loop", "-1", "-i", track_path,
         "-filter_complex",
         f"[1:a]volume={bed:.4f}[bg];"
         "[0:a]asplit=2[nar][key];"
         "[bg][key]sidechaincompress=threshold=0.02:ratio=8:"
         "attack=250:release=900[duck];"
         "[nar][duck]amix=inputs=2:duration=first:dropout_transition=0[aout]",
         "-map", "0:v:0", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", tmp],
        check=True, timeout=900)
    os.replace(tmp, video_path)


def main():
    ap = argparse.ArgumentParser(description="Render documentary with Remotion")
    ap.add_argument("narration", help="narration.json from narrate.py")
    ap.add_argument("--out", default="out.mp4")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--orientation", default="auto",
                    choices=("auto", "16:9", "9:16"),
                    help="auto: < --word-threshold words -> 9:16, else 16:9")
    ap.add_argument("--word-threshold", type=int, default=200,
                    help="word count below which auto orientation is 9:16")
    ap.add_argument("--skip-install", action="store_true",
                    help="skip npm install (deps already installed)")
    ap.add_argument("--no-render", action="store_true",
                    help="prepare public/ + props.json but skip the render")
    ap.add_argument("--overlays", default=None, metavar="OVERLAYS_JSON",
                    help="overlays.json from the overlay director "
                         "(see OVERLAY_DIRECTOR.md); keys overlay specs "
                         "to segment indexes")
    ap.add_argument("--clips", default=None, metavar="CLIPS_JSON",
                    help="clips.json from clips.py; installs each segment's "
                         "real video clip into public/clips/ and passes "
                         "clipFile to the composition (scene background "
                         "becomes the clip instead of the still image)")
    ap.add_argument("--lambda", dest="use_lambda", action="store_true",
                    help="render on AWS Lambda instead of locally "
                         "(scripts/lambda_render.py): bundles the site, "
                         "uploads to S3, renders in parallel chunks, "
                         "downloads out.mp4. ~6x faster than local.")
    ap.add_argument("--site-name", default=None, metavar="SITE_NAME",
                    help="S3 site prefix for --lambda (default: derived "
                         "from the narration file's directory)")
    ap.add_argument("--music", default="random", metavar="MUSIC",
                    help="'random' (default): pick a track from bg_music/; "
                         "a track filename (or stem) in bg_music/ to force "
                         "one; 'off' = no music")
    ap.add_argument("--no-music", action="store_true",
                    help="skip the background-music mix")
    ap.add_argument("--no-wordclock", action="store_true",
                    help="skip faster-whisper word timing; captions fall back "
                         "to spoken-length estimation")
    args = ap.parse_args()

    with open(args.narration, encoding="utf-8") as fh:
        doc = json.load(fh)
    segments = doc["segments"]
    if not segments:
        sys.exit("error: no segments in narration file")

    # overlay director output: {"overlays": [{"segment": i, "type": ..., ...}]}
    overlay_by_seg = {}
    if args.overlays:
        with open(args.overlays, encoding="utf-8") as fh:
            odoc = json.load(fh)
        for entry in odoc.get("overlays", []):
            idx = entry.get("segment")
            spec = {k: v for k, v in entry.items() if k != "segment"}
            if isinstance(idx, int) and spec.get("type"):
                overlay_by_seg[idx] = spec
        print(f"overlays: {len(overlay_by_seg)} segments with graphic cards",
              file=sys.stderr)

    # clips.py output: {"clips": [{"segment": i, "file": ..., "url": ...}]}
    # The clip becomes the scene's background; the still image stays as
    # fallback and is still downloaded below.
    clip_by_seg = {}
    if args.clips:
        with open(args.clips, encoding="utf-8") as fh:
            cdoc = json.load(fh)
        for entry in cdoc.get("clips", []):
            idx = entry.get("segment")
            if isinstance(idx, int) and entry.get("file"):
                # first clip wins when --max-per-seg kept several
                clip_by_seg.setdefault(idx, entry)
        print(f"clips: {len(clip_by_seg)} segments with video backgrounds",
              file=sys.stderr)

    # orientation from the script's word count
    word_count = sum(len(seg.get("text", "").split()) for seg in segments)
    if args.orientation == "auto":
        portrait = word_count < args.word_threshold
    else:
        portrait = args.orientation == "9:16"
    width, height = (1080, 1920) if portrait else (1920, 1080)
    print(f"script: {word_count} words -> "
          f"{'9:16 vertical' if portrait else '16:9 landscape'} "
          f"({width}x{height})", file=sys.stderr)
    # narrate.py stores audio paths relative to ITS cwd; resolve them
    # against the narration file's directory so render.py works from anywhere
    narration_dir = os.path.dirname(os.path.abspath(args.narration))

    img_dir = os.path.join(PROJECT_DIR, "public", "images")
    aud_dir = os.path.join(PROJECT_DIR, "public", "audio")
    sfx_dir = os.path.join(PROJECT_DIR, "public", "sfx")
    clip_dir = os.path.join(PROJECT_DIR, "public", "clips")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(aud_dir, exist_ok=True)
    os.makedirs(sfx_dir, exist_ok=True)
    os.makedirs(clip_dir, exist_ok=True)

    # 1. vendor SFX
    for name, url in SFX.items():
        dest = os.path.join(sfx_dir, name)
        if not os.path.exists(dest) or os.path.getsize(dest) == 0:
            print(f"sfx: downloading {name} ...", file=sys.stderr)
            download(url, dest)

    # 1b. synthesized SFX (scripts/gen_sfx.py): generated locally from
    # filtered noise (zero licensing), not downloaded — build them if
    # missing so fresh checkouts work.
    for name in ("shutter.wav", "click.wav", "boom.wav", "riser.wav",
                 "stinger.wav"):
        dest = os.path.join(sfx_dir, name)
        if not os.path.exists(dest) or os.path.getsize(dest) == 0:
            print(f"sfx: synthesizing {name} ...", file=sys.stderr)
            subprocess.run(
                [sys.executable,
                 os.path.join(PROJECT_DIR, "scripts", "gen_sfx.py")],
                check=True)

    # 1c. map-callout overlays: fetch the satellite map image via
    # scripts/fetch_map.py (Mapbox, token in .env) into public/maps/.
    # The director only supplies `location`; render.py fills `mapImage`.
    map_dir = os.path.join(PROJECT_DIR, "public", "maps")
    os.makedirs(map_dir, exist_ok=True)
    # list(): the failure path deletes entries, which is a RuntimeError
    # while iterating the live dict view.
    for idx, spec in list(overlay_by_seg.items()):
        if spec.get("type") != "map-callout" or spec.get("mapImage"):
            continue
        location = (spec.get("location") or "").strip()
        if not location:
            print(f"[{idx:02d}] map-callout without location — dropped",
                  file=sys.stderr)
            del overlay_by_seg[idx]
            continue
        slug = "".join(c if c.isalnum() else "_" for c in location.lower())
        slug = "_".join(slug.split("_"))[:48].strip("_") or f"map_{idx}"
        dest = os.path.join(map_dir, f"{slug}.png")
        if not os.path.exists(dest) or os.path.getsize(dest) == 0:
            print(f"[{idx:02d}] fetching map: {location} ...", file=sys.stderr)
            try:
                subprocess.run(
                    [sys.executable,
                     os.path.join(PROJECT_DIR, "scripts", "fetch_map.py"),
                     location, "--out", dest],
                    check=True, capture_output=True, text=True, timeout=180)
            except Exception as e:
                print(f"[{idx:02d}] map fetch failed ({e}) — card dropped",
                      file=sys.stderr)
                del overlay_by_seg[idx]
                continue
        spec["mapImage"] = f"maps/{slug}.png"

    # 1d. wiki-quote overlays: screenshot the Wikipedia article with the
    # highlight phrase via scripts/wiki_shot.py into public/wiki/.
    # The director supplies `article` + `highlight`; render.py fills `image`.
    wiki_dir = os.path.join(PROJECT_DIR, "public", "wiki")
    os.makedirs(wiki_dir, exist_ok=True)
    for idx, spec in list(overlay_by_seg.items()):
        if spec.get("type") != "wiki-quote" or spec.get("image"):
            continue
        article = (spec.get("article") or "").strip()
        highlight = (spec.get("highlight") or "").strip()
        if not article or not highlight:
            print(f"[{idx:02d}] wiki-quote without article/highlight — dropped",
                  file=sys.stderr)
            del overlay_by_seg[idx]
            continue
        slug = "".join(c if c.isalnum() else "_" for c in article.lower())
        slug = "_".join(slug.split("_"))[:40].strip("_") or f"wiki_{idx}"
        fname = f"{slug}_{idx:02d}.png"
        dest = os.path.join(wiki_dir, fname)
        if not os.path.exists(dest) or os.path.getsize(dest) == 0:
            print(f"[{idx:02d}] wiki screenshot: {article} ...",
                  file=sys.stderr)
            try:
                subprocess.run(
                    [sys.executable,
                     os.path.join(PROJECT_DIR, "scripts", "wiki_shot.py"),
                     "--article", article, "--highlight", highlight,
                     "--out", dest],
                    check=True, capture_output=True, text=True, timeout=180)
            except Exception as e:
                print(f"[{idx:02d}] wiki screenshot failed ({e}) — "
                      f"card dropped", file=sys.stderr)
                del overlay_by_seg[idx]
                continue
        spec["image"] = f"wiki/{fname}"

    # 2. images + audio -> public/
    props_segments = []
    total_frames = 0
    # Manifest of which source URL each seg_XX.jpg was built from. The
    # public/ dir is shared across projects, so a stale image from a
    # previous documentary must NOT be reused when the URL changes.
    manifest_path = os.path.join(img_dir, "download_manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        manifest = {}
    manifest_dirty = False
    for seg in segments:
        idx = seg["index"]
        img_url = seg.get("image_url") or ""
        # image: download, normalize to JPEG (handles SVG/PNG/WebP, caps size).
        # No licensed image -> generate a dark archival placeholder plate.
        img_name = f"seg_{idx:02d}.jpg"
        img_dest = os.path.join(img_dir, img_name)
        fresh = (
            os.path.exists(img_dest)
            and os.path.getsize(img_dest) > 0
            and manifest.get(img_name) == img_url
        )
        if not fresh:
            if img_url:
                print(f"[{idx:02d}] downloading image ...", file=sys.stderr)
                tmp = img_dest + ".raw"
                try:
                    download(rasterize_svg_url(img_url, width), tmp)
                    normalize_image(tmp, img_dest)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
            else:
                print(f"[{idx:02d}] no licensed image: placeholder plate",
                      file=sys.stderr)
                placeholder_image(img_dest, width, height)
            manifest[img_name] = img_url
            manifest_dirty = True
        # audio
        aud_name = f"seg_{idx:02d}.mp3"
        aud_dest = os.path.join(aud_dir, aud_name)
        aud_src = seg["audio_file"]
        if not os.path.isabs(aud_src):
            aud_src = os.path.join(narration_dir, aud_src)
        if os.path.abspath(aud_src) != os.path.abspath(aud_dest):
            shutil.copyfile(aud_src, aud_dest)
        # trim leading/trailing silence so frame 0 is (nearly) the first
        # spoken word — caption phrases are timed as fractions of the
        # segment and must track the voice, not dead air.
        seg_dur = trim_silence(aud_dest)
        if seg_dur <= 0:
            seg_dur = seg["duration"]
        frames = max(1, round(seg_dur * args.fps))
        # word-clock: measure real word timings from the trimmed narration
        # audio (faster-whisper). Captions lock to the actual voice instead
        # of the spoken-length estimate; None -> renderer falls back to
        # estimation for this segment.
        word_timings = None
        if not args.no_wordclock:
            try:
                word_timings = get_word_timings(aud_dest, seg["text"])
            except Exception as e:
                print(f"[{idx:02d}] word-clock failed ({e}); "
                      f"using estimated caption timing", file=sys.stderr)
        if word_timings is not None:
            print(f"[{idx:02d}] word-clock: {len(word_timings)} words timed",
                  file=sys.stderr)
        title = (seg.get("image_title") or "").lower()

        # portraits: download each person's photo; timed to the name mention.
        # Uses the same manifest as scene images: a stale portrait from a
        # previous run must be re-downloaded when the person's URL changes.
        portraits = []
        for n, person in enumerate(seg.get("people") or []):
            p_name = f"portrait_{idx:02d}_{n}.jpg"
            p_dest = os.path.join(img_dir, p_name)
            p_url = person.get("image_url") or ""
            p_fresh = (
                os.path.exists(p_dest)
                and os.path.getsize(p_dest) > 0
                and manifest.get(p_name) == p_url
            )
            if not p_fresh and p_url:
                print(f"[{idx:02d}] downloading portrait: "
                      f"{person.get('person_name')} ...", file=sys.stderr)
                tmp = p_dest + ".raw"
                try:
                    download(p_url, tmp)
                    normalize_image(tmp, p_dest, max_side=800)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                manifest[p_name] = p_url
                manifest_dirty = True
            if os.path.exists(p_dest) and os.path.getsize(p_dest) > 0:
                start_f = int(person.get("start_frac", 0) * frames)
                end_f = int(person.get("end_frac", 1) * frames)
                if end_f - start_f >= 15:  # need >=0.5s to be worth showing
                    nat_w, nat_h = 0, 0
                    try:
                        from PIL import Image
                        with Image.open(p_dest) as im:
                            nat_w, nat_h = im.size
                    except Exception:
                        pass
                    portraits.append({
                        "file": f"images/{p_name}",
                        "name": person.get("person_name") or "",
                        "startFrame": max(0, start_f),
                        "endFrame": min(frames, end_f),
                        "naturalW": nat_w,
                        "naturalH": nat_h,
                    })

        # clips: install the segment's real video clip (trimmed ~6s mp4
        # from clips.py) into public/clips/, manifest-aware like images:
        # re-copy when the source URL changes, keep the cached file when
        # it doesn't.
        clip_file = None
        clip_frames = 0
        clip_nat_w, clip_nat_h = 0, 0
        clip_entry = clip_by_seg.get(idx)
        if clip_entry:
            c_name = f"clip_{idx:02d}.mp4"
            c_dest = os.path.join(clip_dir, c_name)
            c_url = clip_entry.get("url") or ""
            c_fresh = (
                os.path.exists(c_dest)
                and os.path.getsize(c_dest) > 0
                and manifest.get(c_name) == c_url
            )
            if not c_fresh:
                print(f"[{idx:02d}] installing clip ...", file=sys.stderr)
                shutil.copyfile(clip_entry["file"], c_dest)
                manifest[c_name] = c_url
                manifest_dirty = True
            if os.path.exists(c_dest) and os.path.getsize(c_dest) > 0:
                clip_file = f"clips/{c_name}"
                # clip length in frames drives the background loop math;
                # natural size is recorded so the composition shows the
                # clip exactly as it is — never upscaled (Lawal's rule).
                clip_nat_w, clip_nat_h = 0, 0
                try:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries",
                         "stream=width,height", "-of",
                         "default=noprint_wrappers=1:nokey=1", c_dest],
                        capture_output=True, text=True, timeout=30)
                    dims = [v for v in probe.stdout.split() if v.strip()]
                    clip_nat_w = int(dims[0])
                    clip_nat_h = int(dims[1])
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries",
                         "format=duration", "-of",
                         "default=noprint_wrappers=1:nokey=1", c_dest],
                        capture_output=True, text=True, timeout=30)
                    clip_frames = max(
                        1, round(float(probe.stdout.strip()) * args.fps))
                except Exception:
                    clip_frames = 0

        props_segments.append({
            "text": seg["text"],
            "imageFile": f"images/{img_name}",
            "clipFile": clip_file,  # null when the segment has no clip
            "clipFrames": clip_frames,
            "clipNaturalW": clip_nat_w,
            "clipNaturalH": clip_nat_h,
            "audioFile": f"audio/{aud_name}",
            "durationInFrames": frames,
            "wordTimings": ([[s, e] for s, e in word_timings]
                            if word_timings else None),
            "isMapOrDoc": any(h in title for h in MAP_HINTS),
            "personName": seg.get("person_name") or None,
            "portraits": portraits,
            "overlay": overlay_by_seg.get(idx),
        })
        total_frames += frames

    if manifest_dirty:
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1)

    props = {"segments": props_segments, "width": width, "height": height}
    # grid background behind natural-size clips (Lawal's asset): its length
    # in frames drives the background loop math in the composition.
    grid_bg = os.path.join(PROJECT_DIR, "public", "grid_bg.mp4")
    if os.path.exists(grid_bg) and os.path.getsize(grid_bg) > 0:
        try:
            gprobe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", grid_bg],
                capture_output=True, text=True, timeout=30)
            props["gridBg"] = "grid_bg.mp4"
            props["gridFrames"] = max(
                1, round(float(gprobe.stdout.strip()) * args.fps))
        except Exception:
            pass
    props_path = os.path.join(PROJECT_DIR, "props.json")
    with open(props_path, "w", encoding="utf-8") as fh:
        json.dump(props, fh, ensure_ascii=False)

    # 3. deps
    if not args.skip_install and not os.path.exists(
            os.path.join(PROJECT_DIR, "node_modules", "remotion")):
        print("npm install ...", file=sys.stderr)
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"],
                       cwd=PROJECT_DIR, check=True)

    if args.no_render:
        print(f"props written to {props_path} (render skipped)",
              file=sys.stderr)
        return

    # 4. render
    out_path = os.path.abspath(args.out)
    if args.use_lambda:
        # Lambda path: bundle site -> S3 -> parallel chunk render -> download.
        # Site name defaults to the narration file's directory, sanitized.
        site_name = args.site_name
        if not site_name:
            base = os.path.basename(narration_dir).lower()
            site_name = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        print(f"lambda render: site '{site_name}', {total_frames} frames ...",
              file=sys.stderr)
        subprocess.run(
            [sys.executable,
             os.path.join(PROJECT_DIR, "scripts", "lambda_render.py"),
             "--props", props_path,
             "--out", out_path,
             "--site-name", site_name],
            cwd=PROJECT_DIR, check=True,
        )
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        cmd = [
            "npx", "remotion", "render",
            "src/index.ts", "HistoryDoc",
            f"--props={props_path}",
            f"--output={out_path}",
        ]
        print("rendering", total_frames, "frames ...", file=sys.stderr)
        subprocess.run(cmd, cwd=PROJECT_DIR, check=True)
        print(f"wrote {out_path}", file=sys.stderr)

    # 5. background music: random ducked bed under the narration
    music_choice = "off" if args.no_music else args.music
    track = pick_music_track(music_choice)
    if track:
        print(f"music: mixing '{os.path.basename(track)}' (ducked bed) ...",
              file=sys.stderr)
        mix_bg_music(out_path, track)
        print(f"music: done -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
