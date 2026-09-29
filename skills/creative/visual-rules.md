# Skill: visual-rules

Lawal's standing visual rules. These are corrections earned over many
productions — follow them literally.

## Zero AI visuals

Only the narration is AI. Every photo, clip, and portrait must be real
archival material: public domain, Creative Commons, or properly licensed.
"Make sure it's the real one."

## No reuse within one documentary

Every scene gets a unique underlying visual. Different files, sections,
clips, or crops from one source still count as reuse.

## Overlay cards

- **Pop in, hold 4 seconds, vanish.** Pop in with an effect ~0.4s after
  scene start (scale 1.06→1 + fade over 8 frames), hold readable for 4s
  (`OVERLAY_MAX_FRAMES = 120` at 30fps), fade + scale to 0.97 out. Cards
  NEVER remain for the whole scene.
- **Float over a real, relevant archival visual** — dimmed 0.62 while the
  card is up. Never a bare plate, never a generic map or filler.
- **Match the speech.** Every card carries a `cue`: an exact 2–8 word
  phrase from the segment's narration. The card pops in as those words
  are spoken (character-offset time fraction, 6-frame anticipation; falls
  back to 0.4s lead). A card whose content belongs to another segment's
  speech is rewritten or dropped.
- **Counters finish early.** Odometer/slot-machine numerals must settle
  on the final value ~30 frames before the card vanishes so the settled
  number is readable.

## Portraits

- Each portrait appearance uses a DIFFERENT photograph — even repeat
  appearances of the same person.
- The name overlay stands alone: person's name only, no "archival" label.
- Natural size and aspect, always. Shrink if oversized — never upscale.

## Clips

- Play at natural dimensions, centered, never cropped.
- Low-res archival clips play at 3× natural (320×240 → 960×720), capped
  to fit the frame, over the looping grid background (`public/grid_bg.mp4`).
- YouTube-sourced clips NEVER play full-screen. Frame them over the
  looping grid background like low-res clips — centered, fitted not
  stretched, never edge-to-edge. Safety rule: a full-screen YouTube clip
  reads as a re-upload.
- The grid is a graphic pattern, not archival content — cover-cropping it
  is fine.
- **Representative battle footage is allowed** (Lawal 2026-09-29): a
  battle scene may use real archival combat footage from a DIFFERENT
  battle of the same war and era — e.g. a tank-battle scene can use real
  WWII tank combat footage even if it isn't that exact battle, and an air
  campaign scene can use real WWII air-combat footage from another air
  campaign. It must still be genuinely archival, correct era, no AI, no
  reenactments, no modern footage passed off as period.
- **Max 8 seconds per YouTube/Pathé/AP clip** (Lawal 2026-09-29): no
  single YouTube, British Pathé, or AP Archive footage run may exceed 8
  seconds in one scene — even if the scene is 10 or 15 seconds long.
  Fill the rest of the scene with another visual (a second clip or an
  archival still) instead of looping the same footage. Short bursts read
  as documentary; long rips read as re-upload.

## Pinterest-sourced stills

- Pinterest images are CANDIDATES, never auto-locked. Each must pass
  the verify-visuals gate as genuinely archival: correct era, correct
  subject, no AI imagery, no watermarks, no modern edits, no meme text.
- Reject on sight: watermarked colorizations ("COLOURISED BY …" credit
  burned in), modern photos (restorations, museums, reenactors, workshop
  shots), text/meme pins, AI-looking "restorations".
- No reuse within one documentary; keep `pinterest_pins.txt` in the
  project dir for traceability.

## Orientation

- Script < 200 words → 9:16 vertical (1080×1920).
- Script ≥ 200 words → 16:9 landscape (1920×1080).
- Override per render: `--orientation 16:9` / `--orientation 9:16`;
  threshold: `--word-threshold`.

## Scene transitions

- Every scene boundary gets a film burn: a real burn clip from
  `public/transitions/film-burn-N.mp4` (cut from Lawal's sample footage),
  24 frames straddling the cut, composited with screen blend so the
  bright burn washes over the outgoing scene and reveals the incoming
  one. Clips cycle (N = scene index mod 3) for variety. Implemented in
  `HistoryDoc.tsx` (`FilmBurn`) — no per-project work needed.
- The whoosh SFX still plays into each scene; the burn is the visual
  half of the transition.

## When a person is named

Find their picture and use it — a rights-approved portrait, timed to when
the name is spoken.
