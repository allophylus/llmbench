#!/usr/bin/env bash
# gapclose_chat.sh -- STEP 3 chat suite vs every runnable model (fixed). Runs in screen.
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
OUT=$OUTROOT/chat
mkdir -p "$OUT"
LOG=$OUT/run2.log
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

run_one() {
  local preset=$1 slug=$2 base=$3
  say "chat $slug ($preset)"
  python3 $BENCHWORK/chat_suite.py "$base" "$slug" "$OUT/$slug.json" \
    --questions $BENCHWORK/questions.json --max-tokens 512 --thinking false > "$OUT/$slug.log" 2>&1
  s=$(python3 -c "import json;print(json.load(open('$OUT/$slug.json'))['summary'])" 2>/dev/null || echo ERR)
  say "done $slug $s"
}

# models on prod :8080 (switch via srv.sh)
for pair in "q4_0 qwen3-8-27b-q4-0" "davidau davidau-qwen3-8-27b-neo-max-mtp-q4-k-m" "huihui huihui-abl-q4-k-m" "ornith ornith-1-5-35b-a3b-q4-k-m" "stock38 qwen3-8-27b-q4km" "qwen36 qwen3-6-35b-a3b-ud-q4km"; do
  preset=${pair%% *}; slug=${pair#* }
  say "switch $preset"
  ~/bin/srv.sh "$preset" || { say "SWITCH-FAILED $preset"; continue; }
  run_one "$preset" "$slug" http://127.0.0.1:8080
done

# lfm3 on :8091 (b11874 build)
say "start lfm3 on 8091"
~/bin/srv_lfm3.sh
sleep 20
run_one lfm3 lfm3-1-7b-q4-k-m http://127.0.0.1:8091

# restore prod
~/bin/srv.sh stock38mtp >> "$LOG" 2>&1
say "RESTORED stock38mtp"
touch "$OUT/ALLDONE2"
say "ALL DONE"
