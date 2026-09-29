# skills/INDEX.md

The intelligence of this project lives here, organized by layer. Read the
skill for your current stage BEFORE doing any work in that stage.

## pipelines/ — stage runbooks

- `pipelines/documentary-director.md` — the full documentary runbook:
  script intake, segment assembly, narration/audio, music, SFX, and the
  gate checklist for each stage.

## creative/ — visual and motion knowledge

- `creative/visual-rules.md` — Lawal's standing visual rules: zero AI
  visuals, no reuse, overlay card behavior (4s hold, cues), portrait
  rules, clip sizing, orientation rule.
- `creative/overlay-motion.md` — the studied motion language for overlay
  cards: hard cuts, odometer numerals, staggered rows, constant-speed
  fills. (Pairs with `OVERLAY_DIRECTOR.md` at project root.)

## core/ — machine and asset discipline

- `core/footage-sourcing.md` — YouTube archival footage fetcher
  (`scripts/yt_footage.py`): search with Shorts/reaction/stock filters,
  BBC/AP/Pathé preference, section download, snap-to-cut, shot-log
  cache, cross-video dedup. Grid-framing rule still applies.
- `core/pinterest-images.md` — Pinterest archival-still candidates
  (`scripts/pinterest_images.py`): `site:pinterest.com` web-search
  discovery by the agent, curl-based pin-page download, full-res
  pinimg originals. Candidates only — every image must pass the
  verify-visuals gate (reject watermarks, modern photos, memes).
- `core/verify-visuals.md` — the pre-render vision gate: Gemini
  free-tier checks every sourced clip's frames against the scene (subject,
  era, no AI/modern/title-card/watermark) before anything is render-locked.
- `core/render-reliability.md` — how to render without OOM-killing the
  box: concurrency 2, disk TMPDIR, patience, tsc checks.
- `core/asset-hygiene.md` — manifest-aware downloads, shared `public/`
  discipline, SVG rasterization widths.

## meta/ — review and delivery

- `meta/review-protocol.md` — frame-check procedure and the definition
  of done before anything is delivered.
