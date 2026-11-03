#!/usr/bin/env bash
# gapclose_thinking.sh -- STEP 4 thinking on/off for the 5 runnable models WITHOUT a
# thinking result yet (A3B already measured in benchmarks/a3b-thinking: 22/25 off vs 18/25 on).
set -uo pipefail
# Environment (set these before running; generic placeholders, no host specifics):
: "${BENCHWORK:?set BENCHWORK to the remote bench-work dir}"
: "${OUTROOT:?set OUTROOT to the remote output dir}"
: "${LLAMA:?set LLAMA to the llama.cpp build tree}"
: "${MODELS:?set MODELS to the model dir on the GPU host}"
: "${UNITDIR:=$HOME}"
: "${SERVED:?set SERVED to the served model file name}"
: "${PROJ:?set PROJ to the served projector file name}"

cd $HOME
OUT=$OUTROOT/thinking
mkdir -p "$OUT"
LOG=$OUT/run.log
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

for pair in "stock38 qwen3-8-27b-q4km" "huihui huihui-abl-q4-k-m" "davidau davidau-qwen3-8-27b-neo-max-mtp-q4-k-m" "q4_0 qwen3-8-27b-q4-0" "ornith ornith-1-5-35b-a3b-q4-k-m"; do
  preset=${pair%% *}; slug=${pair#* }
  say "switch $preset"
  ~/bin/srv.sh "$preset" || { say "SWITCH-FAILED $preset"; continue; }
  say "think_pair $slug"
  python3 $BENCHWORK/think_pair.py http://127.0.0.1:8080 "$OUT/$slug-pair.json" --n 25 \
    --max-tokens-off 16384 --max-tokens-think 16384 > "$OUT/$slug.log" 2>&1
  python3 -c "
import json
d=json.load(open('$OUT/$slug-pair.json'))
for m in ('off','on'):
    x=d.get(m,{})
    print(m, 'correct', x.get('correct'), '/', x.get('n'), 'tokens', x.get('tokens'), 'lenstop', x.get('length_stops'), 'wall', x.get('wall_s'))
" >> "$OUT/$slug.log" 2>&1
  say "done $slug"
done

~/bin/srv.sh stock38mtp >> "$LOG" 2>&1
say "RESTORED stock38mtp"
touch "$OUT/ALLDONE"
say "ALL DONE"
