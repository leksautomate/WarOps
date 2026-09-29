# Skill: footage-sourcing

Fetch real archival YouTube clips for scene backgrounds, preferring
official archives (BBC / AP / British Pathé). This is the Frontier 5.1
footage playbook, rewritten for our pipeline. No API key needed.

## Tool

`scripts/yt_footage.py` — CLI:

```bash
python3 scripts/yt_footage.py --query "sherman tanks 1944" \
  --out <project>/yt_clips --section 83-91 \
  --project <project-slug>
```

Prints a JSON manifest to stdout:
`{video_id, url, title, channel, preferred, src_start, src_end,
snapped_start, snapped_end, file}`.

What it does per query:
1. `ytsearchN:` via yt-dlp ("archive footage" auto-appended).
2. Filters: skips YouTube Shorts, reaction videos, and watermarked
   stock sellers (Pond5, Shutterstock, Getty-as-seller, CriticalPast…).
3. Ranks official archive channels first — British Pathé, AP Archive /
   Associated Press, BBC Archive — flagged `"preferred": true`.
4. Downloads ONLY the chosen section (`--download-sections`), snaps the
   span to the nearest real cut (±1.5s, ffmpeg scene detection),
   autocrops black bars, strips audio (our clips play muted under
   narration).
5. Shot-log cache per video id in `.cache/shotlog/` — repeat runs don't
   re-search.
6. Dedup registry `youtube_used.json`: refuses overlapping spans
   across projects, naming the conflicting project/span/file.

## Standing rules (Lawal's — never bend)

- YouTube clips are NEVER shown full-screen. The renderer frames them
  over the looping grid background (HistoryDoc.tsx `ClipBackground`) —
  this script only fetches; the framing rule lives in
  `creative/visual-rules.md`.
- Zero AI visuals. Only real footage.
- Every fetched clip still passes the `verify-visuals` gate before it
  is render-locked.

## Environment notes

- Through this box's egress proxy yt-dlp needs
  `--compat-options no-certifi` and
  `--extractor-args youtube:player_client=android` (web client is
  bot-walled). The script sets both.
- The proxy cuts long googlevideo streams: the script validates each
  file's tail and fails honestly ("wait and retry") instead of handing
  you a truncated clip. Full download for videos ≤120s, sectioned
  download for longer ones.
- Never download to `/tmp` (512MB tmpfs) — use the project dir.

## When to use

Scene-visuals stage, when a segment needs real motion footage and the
licensed stills pool has nothing better. One query per segment, pick
the first `preferred` candidate that passes verify-visuals.
