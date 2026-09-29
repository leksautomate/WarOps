# Skill: documentary-director

Stage runbook for a history documentary production. Read the section for
your current stage before working in it.

## 1. Script intake

- **Ask for the project name first.** Whether Lawal hands over a full
  script or just a topic, always ask what to call the project — never
  auto-name it. Create `projects/<video-title>_script/` and save the
  supplied script verbatim as `script.txt` inside it.
- The script is preserved EXACTLY — no rewriting,
  reordering, substitutions, or omissions.
- Every segment's text must be an exact character-span slice of the
  script. Assert this in code; fail loudly on mismatch.
- Word count comes from narration segments: 15 seconds of narration ≈
  30–45 English words. Trim dialogue to fit; note the word count on each
  dialogue block.
- **When the agent writes the script** (Lawal gives a topic, not a
  script): research on Wikipedia too — read the relevant articles for
  dates, figures, names, and sequence of events before drafting. Every
  stat, quote, and claim in the draft must come from a sourced article;
  never invent numbers or quotations. Note the articles used so the
  wiki-quote overlay stage can confirm narration points later.

## 2. Segments (`narration.json`)

- Produced by `~/workspace/history-sourcer/` (`segment.py`, `narrate.py`).
- Each segment: `{index, text, duration, audio file, image/clip
  candidates}`.
- Empty image pool → dark placeholder plate, never a crash.

## 3. Scene visuals

- One licensed archival still or real video clip per segment
  (`skills/creative/visual-rules.md` for the rules, `clips.py` for
  candidate hunting; `skills/core/footage-sourcing.md` +
  `scripts/yt_footage.py` for YouTube archival footage with
  BBC/AP/Pathé preference — still grid-framed, never full-screen;
  `skills/core/pinterest-images.md` +
  `scripts/pinterest_images.py` for Pinterest archival-still
  candidates — candidates only, every image verified genuinely
  archival before locking).
- **Gate:** every visual eyeballed — real, licensed, correct subject and
  era, no AI-looking B-roll, no title cards, no modern edits. No visual
  reused within one documentary.

## 4. Verify scene visuals (Gemini vision gate)

- After sourcing, before anything is locked in:
  `skills/core/verify-visuals.md`, `scripts/verify_visuals.py`
  (needs `GEMINI_API_KEY`; free tier from Google AI Studio).
- Write per-segment `briefs.json` (expect/reject notes) first — the
  vision check is only as good as its briefs.
- **Gate:** every clip has a verdict in `verify.json`. accept → locked;
  reject → next candidate; flag/unverified → human review. Never render
  on an unverified clip.

## 5. Portraits

- `portraits.py` v2 resolves named people via Wikipedia search with
  script context (never blind Commons keyword), verified human via
  Wikidata instance-of Q5.
- Timed overlays (start_frac/end_frac) shown when the name is spoken.
- **Known weaknesses — inspect manually:** misses possessives
  ("Stalin's"), misses lone surnames with no prior full-name mention
  ("Hitler"), may reuse one photo across appearances.
- **Gate:** every portrait event manually inspected; each appearance gets
  its own distinct photo.

## 6. Overlay cards

- An AI overlay director follows `OVERLAY_DIRECTOR.md` (catalog + rules +
  JSON schema): at most one card per segment, script facts only
  (written-out numbers may become digits; never invent).
- `render.py --overlays overlays.json` keys specs to segment indexes.
- **Gate:** every card carries an exact 2–8 word `cue` from the segment's
  narration; card pops as those words are spoken.

## 7. Narration / audio

- Fish Audio cloud TTS for narration. TTS has no word timestamps —
  portrait/card timing uses character-offset fractions.
- Music: Lawal's own royalty-free tracks (rotated across productions),
  ducked under narration via ffmpeg sidechaincompress. Credits live in
  the posting pack, not in the video.
- SFX: shutter on genuine portrait reveals only; whoosh/page-turn on
  overlay cards.

## 8. Render

- `python3 render.py narration.json --out video.mp4 --lambda`
  (default — AWS Lambda, ~6x faster than local; verified 4m46s for
  3:47 1080p). See `skills/core/render-reliability.md` for the
  chunking rules and the local fallback.
- Film grain is a pre-rendered 8-frame PNG loop (`public/grain/`,
  `scripts/gen_grain.mjs`), overlay blend — fast at render time.

## 9. Review → deliver

- `skills/meta/review-protocol.md`. Nothing ships un-frame-checked.
