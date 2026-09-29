# history-video — Agent Guide

Start here. This is the complete operating guide and agent contract for
this project. It applies to any AI coding assistant working here
(Claude Code, Codex, Gemini, Cursor, Copilot).

For architecture, key files, and conventions see `PROJECT_CONTEXT.md`.

## Rule Zero — the non-negotiables

These override everything, including clever ideas and user requests that
contradict them. If a request conflicts with Rule Zero, stop and ask.

1. **Zero AI visuals. Only the narration is AI.** Every photo, clip, and
   portrait must be a real archival image: public domain, Creative
   Commons, or otherwise properly licensed. Automatic searches WILL return
   junk (AI-looking B-roll, title cards, modern edits, wrong era/theater,
   heavy watermarks). Reject and re-curate until every visual passes the
   eyeball test. "Make sure it's the real one."
2. **The script is preserved EXACTLY.** No rewriting, reordering,
   substitutions, or omissions. Every segment's text must be an exact
   character-span slice of the script — assert this in code.
3. **Every production runs the stage machine below.** No skipping stages,
   no jumping straight to render.

## The stage machine

```
script → segments → scene visuals → verify visuals → portraits
  → overlay cards → narration/audio → render → review → deliver
```

For EACH stage, **read the stage skill in `skills/` BEFORE doing any work
in that stage.** The intelligence is in the skills, not in improvised
scripts. An agent that reads the skills will produce far better output
than one that calls tools directly with generic judgment.

| Stage | Skill | Gate |
|---|---|---|
| Script intake | `skills/pipelines/documentary-director.md` | script preserved char-for-char |
| Scene visuals | `skills/creative/visual-rules.md` + `clips.py` | every visual eyeballed, none reused |
| Verify visuals | `skills/core/verify-visuals.md` + `scripts/verify_visuals.py` | Gemini verdict per clip before render |
| Portraits | `skills/creative/visual-rules.md` + `portraits.py` | every event manually inspected |
| Overlay cards | `OVERLAY_DIRECTOR.md` | exact 2–8 word cue per card |
| Narration/audio | `skills/pipelines/documentary-director.md` | Fish Audio cloud TTS, music ducked |
| Render | `skills/core/render-reliability.md` | concurrency 2, disk TMPDIR |
| Review | `skills/meta/review-protocol.md` | frame-check before delivery |

## Project organization

Every production lives in its own folder:

```
projects/<video-title>_script/
```

The folder name is ALWAYS asked at kickoff — whether Lawal hands over a
full script or just a topic. Never auto-name a project silently; propose
a slug and confirm before creating anything.

Suggested layout inside:

```
projects/<video-title>_script/
├── script.txt         # the supplied script, verbatim
├── narration.json     # from narrate.py
├── clips.json         # from clips.py (when clips are used)
├── overlays.json      # from the overlay director
├── props.json         # render.py output
└── renders/           # finished MP4s
```

## Decision communication contract

For any consequential production decision, communicate BEFORE acting:

- the exact choice (tool, provider, orientation override, render path),
- the reason it was chosen,
- whether it is a test or the full run.

**Ask before major changes**, including:

- dropping narration, music, or SFX the owner approved,
- switching orientation away from the word-count rule,
- substituting stills where clips were planned (or vice versa),
- changing composition engine or render path,
- any provider/model swap.

Minor refinements inside an already approved path do not need separate
approval unless they materially change the creative direction.

**Lawal works in staged gates.** Stop at defined gates, present what you
have, and wait. Do not run ahead past a gate.

## Escalate blockers explicitly

1. What was attempted.
2. What failed.
3. Whether it is auth, provider access, tool bug, or quality.
4. What options exist next.
5. Which option you recommend, with reasoning.

Do not substitute a different path silently until the owner approves.

## Do NOT

- Generate, fetch, or accept AI-generated visuals of any kind.
- Rewrite, reorder, or "improve" the script.
- Reuse an image, clip, or portrait photo within one documentary.
- Upscale portraits or clips (shrink-only, and 3× natural for low-res
  clips per the visual rules).
- Render at default concurrency on a weak machine.
- Deliver a video you have not frame-checked.
- Write ad-hoc one-off scripts when a pipeline script already covers the
  job — extend the pipeline instead.

## Definition of done

1. Script preserved character-for-character.
2. Every visual eyeballed: real, licensed, correct subject and era,
   no reuse within the documentary, no repeated portrait photos.
3. Every overlay card carries an exact 2–8 word cue from the narration
   and holds 4 seconds.
4. Full render frame-checked (spot-check frames across scenes).
5. Delivered as a download link. Never re-render when re-uploading the
   same file fixes it.
