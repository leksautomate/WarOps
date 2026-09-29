# history-video — Shared Project Context

This is the single source of truth for project architecture and
conventions. All agent entry files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`)
point to `AGENT_GUIDE.md`, which points here. Do not duplicate this
content elsewhere — link to it.

## Identity

Remotion-based renderer that turns a narrated script into a finished
history documentary MP4: Ken Burns motion on archival stills (or real
archival video clips), timed portrait popups when people are named,
data-documentary overlay cards, film grain, captions, music/SFX.

## Architecture: script-driven tools + agent judgment at curation gates

Python scripts do the deterministic work: downloading, normalizing,
assembling `props.json`, driving Remotion. The agent makes the curation
decisions the scripts cannot: is this footage genuinely archival? Does
this portrait match the person? Does this card match the spoken words?

There is no fully-automated "fire and forget" mode — human eyeball gates
are part of the design, not a limitation.

```
Agent reads stage skill (skills/) → runs pipeline script
  → curates at the gate → checkpoints → presents to owner
```

## Pipeline

```
~/workspace/history-sourcer/          →  narration.json
  research, segment.py, portraits.py,      (segments: text + audio +
  narrate.py (Fish Audio cloud TTS)        image/clip candidates)

        ↓

~/workspace/history-video/            →  MP4
  render.py → public/ + props.json → npx remotion render
```

## Key files

| File | Purpose |
|---|---|
| `render.py` | Main driver: downloads/normalizes images, portraits, clips; writes `props.json`; invokes Remotion. Flags: `--no-render`, `--overlays`, `--clips`, `--orientation`, `--word-threshold` |
| `clips.py` | Finds REAL archival video clips (Internet Archive → Wikimedia Commons → YouTube last resort). Candidate finder only — every clip must be eyeballed |
| `src/HistoryDoc.tsx` | Remotion composition: scenes, Ken Burns, portraits, overlay cards, captions, grain |
| `src/Root.tsx` | Registers composition; `calculateMetadata` reads w/h from props (zod schema) |
| `src/overlays.tsx` | Ten overlay card templates (stat, date, timeline, bars, table, portrait, split, quote, list, diagram) |
| `OVERLAY_DIRECTOR.md` | Overlay director playbook: catalog, rules, JSON schema |
| `remotion.config.ts` | JPEG frames, overwrite on, Chromium swiftshader |
| `public/grain/` | Pre-rendered 8-frame film-grain PNG loop (overlay blend — fast) |
| `public/grid_bg.mp4` | Looping grid texture behind natural-size clips (graphic pattern, not archival) |
| `public/images/download_manifest.json` | Re-downloads assets when URLs change — prevents stale images shipping silently |

## Conventions

- **Project folders:** every production gets `projects/<video-title>_script/`
  (see AGENT_GUIDE.md). The name is always asked at kickoff — script or
  just a topic, never auto-named silently.
- **Orientation:** script < 200 words → 9:16 (1080×1920); ≥ 200 words →
  16:9 (1920×1080). `render.py` counts from narration segments.
- **Render reliability (weak machines):** `--concurrency=2`, disk-backed
  TMPDIR (never `/tmp` tmpfs), never kill long renders, `tsc --noEmit`
  clean after touching `src/`. Full rules: `skills/core/render-reliability.md`.
- **Asset hygiene:** manifest-aware downloads for images, portraits, clips;
  `public/images/` is shared across projects — never let stale files ship.
  Full rules: `skills/core/asset-hygiene.md`.
- **Overlay motion language:** hard cuts, slot-machine odometer numerals
  (red rolling, dead-stop to white), staggered rows, constant-speed fills,
  static card photos. Full spec: `skills/creative/overlay-motion.md`.
- **Narration/audio:** Fish Audio cloud TTS (`s2.1-pro-free` tier family).
  Music copyright-safe (e.g. Kevin MacLeod CC-BY — credit on post), ducked
  under narration via ffmpeg sidechaincompress.
- **Communication:** short, direct, no fluff. State uncertainty plainly.
  Never fabricate facts, stats, or sources.

## When extending the pipeline

1. Extend the existing script (`render.py`, `clips.py`) rather than
   writing a parallel one-off.
2. If the change encodes a new standing rule, write it into the relevant
   skill in `skills/` — that is where agent knowledge lives.
3. Update `skills/INDEX.md` if you add a skill.
4. `npx tsc --noEmit` must pass; do a `--no-render` dry run before any
   full render.
