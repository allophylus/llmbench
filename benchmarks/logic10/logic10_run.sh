#!/usr/bin/env bash
# logic10_run.sh -- STEP 7: logic10 thinking off/on across every runnable model.
# Runs under screen 'logic10' on the GPU host. The GPU is shared with the gapclose
# thinking pairs, the 4-game suite and an ablation, so this script:
#   * waits until ~/gapclose-out/thinking2/ALLDONE exists (that campaign owns :8080);
#   * switches one model at a time via ~/bin/srv.sh, never two configs at once;
#   * delegates to logic10.py, which is resumable per question from its own state file;
#   * restores the production preset (stock38mtp) when finished.
# lfm3 is text-only and lives on :8091 under a different llama.cpp build, so it does not
# touch :8080 at all and can run at any time (LFMFIRST=1).
set -uo pipefail
cd /home/ubuntu
OUT=/home/ubuntu/logic10-out
mkdir -p "$OUT"
LOG=$OUT/run.log
H=/home/ubuntu/bench-work/logic10.py
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
CAP=${CAP:-8192}
MODELS=${MODELS:-"qwen36:qwen3-6-35b-a3b-ud-q4km stock38:qwen3-8-27b-q4km q4_0:qwen3-8-27b-q4-0 davidau:davidau-qwen3-8-27b-neo-max-mtp-q4-k-m huihui:huihui-abl-q4-k-m ornith:ornith-1-5-35b-a3b-q4-k-m"}

run_pair() {  # $1 base url, $2 slug
  say "logic10 $2 (cap $CAP)"
  python3 "$H" "$1" "$OUT/$2.json" --slug "$2" --max-tokens "$CAP" >> "$OUT/$2.log" 2>&1
  say "done $2 rc=$? $(grep -cE '^(off|on) ' "$OUT/$2.log" 2>/dev/null || echo 0) lines"
  cp "$OUT/$2.json" "$OUT/$2.json.bak" 2>/dev/null || true
}

if [ "${LFMFIRST:-1}" = 1 ]; then
  say "lfm3 first on :8091"
  curl -s -m 5 http://127.0.0.1:8091/v1/models >/dev/null || ~/bin/srv_lfm3.sh
  for i in $(seq 1 60); do curl -s -m 4 http://127.0.0.1:8091/props >/dev/null && break; sleep 2; done
  run_pair http://127.0.0.1:8091 lfm3-1-7b-q4-k-m
fi

say "waiting for thinking2 (gapclose) to finish with :8080"
while [ ! -e /home/ubuntu/gapclose-out/thinking2/ALLDONE ]; do sleep 60; done
say "thinking2 done; waiting 30s for the preset restore to settle"; sleep 30

for pair in $MODELS; do
  preset=${pair%%:*}; slug=${pair#*:}
  [ -s "$OUT/$slug.json" ] && grep -q '"on"' "$OUT/$slug.json" && \
    [ "$(python3 -c "import json;d=json.load(open('$OUT/$slug.json'));print(sum(1 for m in d['modes'] for r in d['modes'][m]['rows'] if r.get('verdict')!='error'))" 2>/dev/null)" = 20 ] && {
      say "skip $slug (complete)"; continue; }
  say "switch $preset"
  ok=0
  for attempt in 1 2 3; do
    if ~/bin/srv.sh "$preset" >> "$OUT/switch.log" 2>&1; then ok=1; break; fi
    say "switch attempt $attempt failed for $preset; retrying in 20s"; sleep 20
  done
  [ "$ok" = 1 ] || { say "SWITCH-FAILED $preset"; continue; }
  run_pair http://127.0.0.1:8080 "$slug"
done

~/bin/srv.sh stock38mtp | tee -a "$LOG"
say "RESTORED stock38mtp"
touch "$OUT/ALLDONE"
say "ALL DONE"
