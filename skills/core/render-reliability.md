# Skill: render-reliability

How to render without destroying the machine. Learned the hard way.

## The default: Lambda (`render.py --lambda`)

Lambda is the default render path — verified 2026-09-27 on a 3:47
1080p documentary: **4m 46s on Lambda vs 30m 57s locally** (~6.5x).

```
python3 render.py narration.json --out video.mp4 --lambda
```

What it does (`scripts/lambda_render.py`): `npx remotion bundle` the
site locally, upload to `s3://<bucket>/sites/<site-name>/`, launch the
chunk render, poll `progress.json` until done, download `out.mp4`,
print measured wall time. Site name defaults to the narration file's
directory (sanitized); override with `--site-name`.

Chunking rule (do not improvise): the AWS account allows **10
concurrent Lambdas**. When `framesPerLambda` is set, Remotion launches
ALL chunks at once, so the script keeps chunks <= 9
(`framesPerLambda = ceil(totalFrames/9)` clamped to 500–1500; very long
videos fall back to `concurrency=9` queue mode). **Never set both
`framesPerLambda` and `concurrency` — Remotion rejects the render as
fatal.**

Needs `~/.aws/credentials` (the account's key). The Node launcher runs
with `proxy-preload.cjs` (`NODE_OPTIONS`) so the AWS SDK survives the
egress proxy; S3 work uses vendored boto3 in `.deps/` (the system
python loses site-packages on resets — never rely on a global install).

Proxy-flake recovery (built into `scripts/lambda_render.py`, do not
work around it):
- Launch response lost (ECONNRESET/socket hang up after HTTP 200):
  the render usually started server-side — the script adopts the
  newest `renders/` entry from S3 instead of launching a duplicate.
- `progress.json`'s `done` flag never flips: `out.mp4` appearing in
  `renders/<id>/` is the real completion signal.
- Large downloads flake through the proxy: the script falls back to
  resumable `curl -C -` on a presigned URL.

## The fallback: weak-machine local render (2 vCPU / 7.7 GB RAM)

Use only when Lambda/AWS is unavailable.

1. **Always `--concurrency=2`.** Remotion's default concurrency
   OOM-kills Chromium here (observed: stall, then death at frame ~407
   with "Could not take a screenshot because Google Chrome ran out of
   memory"). `render.py` has no concurrency flag — run
   `render.py --no-render` first, then invoke Remotion directly:
   `npx remotion render <site> <comp> --props=props.json --concurrency=2`.
2. **Disk-backed TMPDIR, never `/tmp`.** `/tmp` is a 512MB tmpfs.
   Point TMPDIR at a real disk directory.
3. **Do not kill long renders.** A 10-minute 1080p video takes roughly
   1.5–2.5 hours on this box. Report concrete frame progress if asked;
   be patient, don't terminate early.
4. **`npx tsc --noEmit` must pass** after any change in `src/`.

## Before a full render

- `render.py --no-render` to prep `public/` + `props.json` without
  rendering.
- Layout check via still: `npx remotion still src/index.ts HistoryDoc
  still.png --props=props.json --frame=N`.

## Timings to expect

- 2-minute 1080p sample: ~18 minutes (local fallback).
- Heavy libass + many overlays at 1080p is slow locally — that is normal.
- Lambda default: 3:47 1080p in 4m 46s (verified 2026-09-27).
