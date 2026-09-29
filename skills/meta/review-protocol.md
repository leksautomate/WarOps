# Skill: review-protocol

Nothing ships without passing this review.

## Frame-check procedure

1. Extract check frames across the full duration
   (`ffmpeg -ss <t> -i out.mp4 -frames:v 1 check_N.jpg`), spaced to hit
   every scene.
2. For each frame, verify:
   - The visual is real archival material matching the segment's
     subject and era — no AI-looking B-roll, no title cards, no modern
     edits, no watermarks.
   - No image is reused from another scene in the same video.
   - Portraits: correct person, distinct photo per appearance, name
     only, natural size.
   - Overlay cards: exact cue words visible in the narration at that
     moment, card holds ~4s, counters settled on final values.
   - Captions legible, no clipping at frame edges.
3. Verify audio: narration present throughout, music ducked under it,
   no silence gaps, no clipping.

## Definition of done

1. Script preserved character-for-character.
2. Every visual eyeballed and licensed-correct.
3. Every overlay card cue-matched with a 4s hold.
4. Full render frame-checked per above.
5. Delivered as a download link. Never re-render when re-uploading the
   same file fixes a delivery problem.

## Reporting

One line per check area: what was verified, what was found. No essays.
