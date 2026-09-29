#!/bin/bash
# Sequential archival footage fetches for 761st recreation (Lawal 2026-09-29:
# representative WWII battle footage from other battles is allowed).
cd ~/workspace/history-video
PROJ=projects/761st-tank-battalion-183-days_script
OUT=$PROJ/yt_clips
REG=$OUT/youtube_used.json
declare -A Q=(
  [3]="sherman tanks advance france 1944"
  [4]="tank battle france 1944 sherman"
  [5]="sherman tanks snow winter 1944"
  [6]="american tanks attack germany 1945"
  [7]="siegfried line dragon teeth tanks"
  [9]="american soviet troops linkup 1945"
  [10]="knocked out tanks 1944"
)
for seg in 3 4 5 6 7 9 10; do
  echo "=== seg $seg: ${Q[$seg]} ==="
  python3 scripts/yt_footage.py --query "${Q[$seg]}" --out "$OUT" \
    --project 761st-tank-battalion-183-days --registry "$REG" \
    > "$OUT/manifest_seg${seg}.json" 2> "$OUT/fetch_seg${seg}.log"
  echo "exit=$? -> $OUT/manifest_seg${seg}.json"
done
echo "ALL DONE"
