#!/usr/bin/env bash
# setup.sh — first-time installer for the history-video pipeline.
#
# Run once on a fresh machine (or fresh clone):
#     bash setup.sh
#
# What it does:
#   1. Checks system tools (python3, node, npm, ffmpeg, curl)
#   2. npm install            (Remotion renderer + deps)
#   3. pip installs into .deps (boto3, faster-whisper, playwright, yt-dlp)
#   4. Playwright Chromium    (headless browser for wiki screenshots)
#   5. Generates assets       (film grain tiles, synthesized SFX)
#   6. Creates .env from .env.example if missing
#
# Idempotent: safe to re-run; finished steps are skipped.
# If outbound traffic needs a proxy, export EGRESS_PROXY first:
#     export EGRESS_PROXY=http://my-proxy:3128
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPS="$ROOT/.deps"
PIP_TMP="$ROOT/.pip-tmp"

step() { echo; echo "== $1 =="; }
ok()   { echo "   ok: $1"; }
skip() { echo "   skip: $1"; }

# --- 1. system tools -------------------------------------------------------
step "1/6 system tools"
for t in python3 node npm ffmpeg curl; do
  command -v "$t" >/dev/null 2>&1 \
    && ok "$t $(command -v "$t")" \
    || { echo "   MISSING: $t — install it, then re-run setup.sh"; exit 1; }
done

# Proxy for this box's pip/npm if requested.
if [ -n "${EGRESS_PROXY:-}" ]; then
  export http_proxy="$EGRESS_PROXY" https_proxy="$EGRESS_PROXY" \
         HTTP_PROXY="$EGRESS_PROXY" HTTPS_PROXY="$EGRESS_PROXY"
  ok "proxy $EGRESS_PROXY"
fi

# pip unpacks wheels into /tmp — redirect when /tmp is small (512MB tmpfs).
if [ "$(df -m /tmp | awk 'NR==2{print $4}')" -lt 1024 ]; then
  mkdir -p "$PIP_TMP"
  export TMPDIR="$PIP_TMP"
  ok "TMPDIR redirected to .pip-tmp (small /tmp)"
fi

# --- 2. node deps ----------------------------------------------------------
step "2/6 node dependencies"
if [ -d "$ROOT/node_modules/@remotion/cli" ]; then
  skip "node_modules present"
else
  (cd "$ROOT" && npm install --save-exact) || exit 1
  ok "npm install done"
fi

# --- 3. python deps --------------------------------------------------------
step "3/6 python dependencies (.deps)"
PY_DEPS="boto3 faster-whisper playwright yt-dlp"
need=""
for p in $PY_DEPS; do
  [ -d "$DEPS/$p" ] || [ -d "$DEPS/${p//-/_}" ] || need="$need $p"
done
if [ -z "$need" ]; then
  skip "python deps present"
else
  # shellcheck disable=SC2086
  python3 -m pip install --target="$DEPS" --no-cache-dir $need || exit 1
  ok "installed:$need"
fi

# --- 4. playwright chromium ------------------------------------------------
step "4/6 playwright chromium"
if ls ~/.cache/ms-playwright/chromium-* >/dev/null 2>&1; then
  skip "chromium present"
else
  PYTHONPATH="$DEPS" python3 -m playwright install chromium || exit 1
  ok "chromium installed"
fi

# --- 5. generated assets ---------------------------------------------------
step "5/6 generated assets"
[ -f "$ROOT/public/grain/grain-0.png" ] \
  && skip "grain tiles" \
  || { (cd "$ROOT" && node scripts/gen_grain.mjs) && ok "grain tiles"; }
[ -f "$ROOT/public/grain-portrait/grain-0.png" ] \
  && skip "portrait grain tiles" \
  || { (cd "$ROOT" && node scripts/gen_grain.mjs --w 540 --h 960 --dir grain-portrait) \
       && ok "portrait grain tiles"; }
[ -f "$ROOT/public/sfx/shutter.wav" ] \
  && skip "sfx" \
  || { (cd "$ROOT" && PYTHONPATH="$DEPS" python3 scripts/gen_sfx.py) \
       && ok "synthesized sfx"; }

# --- 6. env file -----------------------------------------------------------
step "6/6 .env"
if [ -f "$ROOT/.env" ]; then
  skip ".env exists"
else
  cp "$ROOT/.env.example" "$ROOT/.env"
  chmod 600 "$ROOT/.env"
  echo "   created .env — FILL IN your GEMINI_API_KEYS and MAPBOX_TOKEN"
fi

# --- verify ----------------------------------------------------------------
echo
echo "== verify =="
(cd "$ROOT" && PYTHONPATH="$DEPS" python3 -c \
  "import boto3, faster_whisper, playwright, yt_dlp; print('   ok: python deps import')") \
  || echo "   WARN: a python dep failed to import"
(cd "$ROOT" && node -e "require('@remotion/cli'); console.log('   ok: remotion cli present')") \
  || echo "   WARN: @remotion/cli missing"
command -v ffmpeg >/dev/null && ok "ffmpeg ready"

echo
echo "Setup complete. Next:"
echo "  1. Fill in .env  (GEMINI_API_KEYS, MAPBOX_TOKEN)"
echo "  2. Read AGENT_GUIDE.md, then skills/pipelines/documentary-director.md"
echo "  3. Render:  python3 render.py narration.json --out video.mp4 --lambda"
