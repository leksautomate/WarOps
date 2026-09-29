# Skill: overlay-motion

The motion language for overlay cards in `src/overlays.tsx`, studied
frame-by-frame from reference footage (SinceWWII "Why the Soviets Should
Have Collapsed in 1941"). Deviating from this language makes cards look
generic.

## Principles

- Elements snap in with **hard cuts**, staged a beat apart — nothing
  fades in lazily, nothing bounces or eases.
- Hero numbers roll like a **slot machine**: red digits at constant
  speed, then a dead stop on the final white number. Use a 4-cell rolling
  window with reassigned digits (a 40-cell strip translated thousands of
  px mis-rasterizes in Chromium).
- Rows and list items appear **one by one, top to bottom**, staggered.
- Bars, rulers, and timeline blocks **fill left to right at constant
  speed**.
- Photos on cards stay **static**.
- Text never types in letter by letter.

## Templates (`src/overlays.tsx`)

Near-black plates, giant numerals, mono kickers, red accents. Separate
9:16 and 16:9 layouts.

| type | use when the segment… |
|---|---|
| `stat` | centers on one headline figure (odometer number) |
| `date` | is about a date/moment ("22 JUNE 1941") |
| `timeline` | spans a time range ending in a total (filling bar) |
| `bars` | lists 2+ percentages (animated red bars) |
| `table` | lists 2+ name→figure pairs (ledger with total) |
| `portrait` | names a commander + rank/role/fate (dossier card) |
| `split` | contrasts two figures side by side |
| `quote` | has a striking line worth a full-screen pull-quote |
| `list` | runs a numbered set of items (armies, waves…) |
| `diagram` | centers on a figure + a scale (distances, ranges) |

## Layout notes

- Diagram ruler end-labels anchored (first left, middle center, last
  right) so they never clip.
- Cards composite over the segment's archival visual (Ken Burns, dimmed
  0.62) — never bare full-screen plates.
- Narration + whoosh SFX still play on card segments; the caption bar is
  skipped. At most one overlay per segment; most segments get none.
