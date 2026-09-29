# Skill: pinterest-images

Pinterest as an archival-still candidate source for scene visuals.
Images only — Pinterest is good for images, not used for video here.

## Why it works this way

Pinterest's search page is bot-walled from datacenter IPs (captcha /
killed connections), so we never scrape pinterest.com search directly.
But pin PAGES are SEO-friendly and served to plain curl — and Google
indexes them. Discovery goes through web search; downloading is a
script. Verified working 2026-09-29.

## Workflow

1. **Discover (agent, per scene):** web-search
   `site:pinterest.com <scene subject>` (e.g.
   `site:pinterest.com sherman tank normandy`). Collect pin URLs —
   prefer `pinterest.com/pin/<id>/` results whose snippet describes a
   period photo. Board pages (`/user/board/`) are weaker candidates;
   skip them unless the board is clearly archival.
2. **Download (script):** save pin URLs to `<project>/pinterest_pins.txt`
   (one per line), then:

   ```bash
   python3 scripts/pinterest_images.py --pins <project>/pinterest_pins.txt \
     --num 6 --out <project>/pinterest_imgs
   ```

   The script curls each pin page, extracts the full-res
   `i.pinimg.com/originals/…` image URL, and downloads it. No API key,
   no browser. Prints a DONE count; anything under ~20KB is discarded.
3. **Candidates only.** Every downloaded image goes through the
   `verify-visuals` gate like any other candidate. Pinterest is a mixed
   bag — expect to reject most of what comes back.

## Pinterest-specific rejections (in addition to the zero-AI rule)

- **Watermarked colorizations** — "COLOURISED BY …" credit text burned
  into the image. Reject, even if the underlying photo is period.
- **Modern photos** — restored vehicles, museum pieces, reenactors,
  workshop shots. Pinterest mixes these in freely; the verify gate
  must catch them.
- **Text/meme pins** — quote cards, infographics, "history facts" memes.
- **AI-looking "restorations"** — over-smoothed, plastic-skin faces,
  impossible detail. When in doubt, reject.

## Standing rules

- Pinterest images are CANDIDATES, never auto-locked. Each must pass
  visual verification as genuinely archival: correct era, correct
  subject, no AI imagery, no watermarks, no modern edits, no meme text.
- No image reused within one documentary (same rule as every source).
- Keep `pinterest_pins.txt` in the project dir so a rejected candidate
  can be traced back to its pin.
