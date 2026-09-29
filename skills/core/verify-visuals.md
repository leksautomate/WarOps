# Skill: verify-visuals

Pre-render vision gate for scene visuals. Metadata lies — only looking at
frames tells whether a clip actually matches its scene. This stage runs
AFTER sourcing (`clips.py`) and BEFORE anything is locked into the render.

## The gate

No clip reaches the render queue without a verdict in `verify.json`:
- **accept** → locked for its segment.
- **reject** → try the next candidate for that segment (re-run `clips.py`
  with the rejected `source_id` excluded, or pick the next ranked hit).
- **flag** → human review. Present the check frames + reason to Lawal,
  wait for his call. Do not guess past a flag.
- **unverified** (no API key, API error, quota out) → the manual gate in
  `skills/meta/review-protocol.md` takes over: the driver eyeballs every
  check frame. Never treat "unverified" as "accepted".

## Procedure

1. **Write per-segment briefs first** (`briefs.json`). For each segment,
   one `expect` line and one `reject` line — this is what makes the vision
   check guided instead of guesswork:
   ```json
   {"0": {"expect": "German Panzer III/IV tanks advancing, summer 1941, Eastern Front",
          "reject": "Tiger tanks, winter scenes, modern reenactment, swastika-free replicas"}}
   ```
   Derive them from the segment's narration text. Be specific about the
   era markers that matter (vehicle models, uniforms, season, location).
2. **Run the verifier:**
   ```
   python3 scripts/verify_visuals.py clips.json \
     --narration narration.json --briefs briefs.json --out verify.json
   ```
   The key is read from `~/workspace/history-video/.env` (chmod 600,
   auto-loaded) or the environment — free key from Google AI Studio, no
   billing. For failover across several keys, use one comma-separated
   value:
   ```
   GEMINI_API_KEYS=key_one,key_two,key_three
   ```
   (legacy `GEMINI_API_KEY` still works for a single key). A key that
   hits quota/rate-limit or is rejected is skipped for the rest of the
   run and the next key takes over automatically; if every key is
   exhausted, remaining clips go `unverified` → manual gate.
   It sends each clip's check frames (already extracted by `clips.py`)
   to Gemini with the segment text + briefs and a strict checklist:
   AI-looking, modern objects, title cards, watermarks, wrong subject,
   wrong era. Small corner archive watermarks (Pathe, CriticalPast,
   Periscope) are acceptable — only intrusive/promotional watermarks fail.
3. **Act on verdicts** per the gate above. Re-verify any replacement
   candidate before locking it in.

## What the model is good and bad at

- Good: modern objects in frame, title cards, watermarks, AI-looking
  plastic footage, obviously wrong subject (ships when the scene needs
  tanks).
- Weak: subtle era mistakes (wrong tank variant, wrong year's uniform).
  That's what the `expect`/`reject` briefs are for — spell out what to
  look for so the check isn't guesswork.

## Quota and cost

- Gemini free tier (key from Google AI Studio, no billing): `gemini-flash-latest`
  (stable alias — pinned versions like 2.0/2.5-flash are blocked for new API
  keys). Generous free quota — confirm current limits in AI Studio, they change.
- Cost per clip: 1 request (3 frames). A 30-segment video ≈ 30 requests;
  with re-tries on rejects, budget ~2× segments.
- The script pauses 2s between calls and retries once on 429/5xx. If
  quota runs out mid-batch, remaining clips go `unverified` → manual gate.
  Never hammer through rate limits.

## License is metadata, not vision

The model checks what the footage *shows*. License comes from
`clips.json` (`license`, `url`, `source`) — keep it attached to every
accepted clip; CC BY items need title + creator + source URL + license in
the video description or credits. A CC label is not proof the uploader
owned the rights — the vision check and your judgment still apply.
