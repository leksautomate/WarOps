# Skill: asset-hygiene

How downloaded assets are kept honest across projects.

## Manifest-aware downloads

`public/images/download_manifest.json` records every downloaded asset's
source URL. On re-run, assets re-download **only when the URL changed**.
This prevents the classic silent failure: `public/images/` is shared
across projects, so without the manifest a new video ships with STALE
images from the previous project (observed: an entire documentary
rendered with the previous project's backgrounds because `render.py`
skipped existing `seg_XX.jpg` files).

The same manifest discipline applies to portraits and clips
(`render.py --clips` re-copies only on source URL change).

## Rules

- Never hand-delete or hand-place files in `public/images/` to "fix" a
  visual — change the URL and let the manifest re-download.
- Segments with no licensed image get a dark placeholder plate, never a
  crash and never a borrowed image from another project.

## SVG maps

Rasterize via Wikimedia server-side PNG thumbnails. Allowed widths:
320 / 640 / 800 / 1280 / 2560. Note: 1024 returns HTTP 400 — use the
nearest allowed width.
