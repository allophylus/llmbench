#!/usr/bin/env bash
# logic10_clean.sh -- run every logic10 pair from scratch with a served-model guard.
#
# Card is idle (ctx-sweep finished 21:20; prod preset stock38mtp restored). One config at
# a time. Before every run the harness is told which model file it expects; if the server
# came up with different weights the run aborts without sending a request. Old result
# files are moved to logic10-out/invalid/, never deleted, so a mis-attributed run stays
# on record without being scored.
set -uo pipefail
cd /home/ubuntu
OUT=/home/ubuntu/logic10-out
LOG=$OUT/clean.log
H=/home/ubuntu/bench-work/logic10.py
CAP=${CAP:-8192}
mkdir -p "$OUT/invalid"
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# preset | slug | substring of the served path that must be present
ROWS=(
 "qwen36|qwen3-6-35b-a3b-ud-q4km|Qwen3.6-35B-A3B-UD-Q4_K_M"
 "stock38|qwen3-8-27b-q4km|Qwen3.8-27B-Q4_K_M"
 "q4_0|qwen3-8-27b-q4-0|Qwen3.8-27B-Q4_0"
 "davidau|davidau-qwen3-8-27b-neo-max-mtp-q4-k-m|DavidAU-Qwen3.8-27B-NEO-MAX"
 "huihui|huihui-abl-q4-k-m|Huihui-abl"
 "ornith|ornith-1-5-35b-a3b-q4-k-m|Ornith-1.5-35B"
)

say "clean run: ${#ROWS[@]} pairs, cap $CAP"
for row in "${ROWS[@]}"; do
  IFS='|' read -r preset slug expect <<< "$row"
  if [ -e "$OUT/$slug.json" ]; then
    ts=$(date +%H%M%S)
    mv "$OUT/$slug.json" "$OUT/invalid/$slug.json.pre-clean-$ts"
    say "moved old $slug.json -> invalid/"
  fi
  ok=0
  for attempt in 1 2 3; do
    systemctl --user is-active --quiet qwen-longctx && { systemctl --user stop qwen-longctx; sleep 3; }
    systemctl --user reset-failed qwen-longctx 2>/dev/null || true
    sleep 2
    if ~/bin/srv.sh "$preset" >> "$OUT/switch.log" 2>&1; then
      ok=1
      # record the weights this run will use, AS LOADED (srv.sh has just swapped the link)
      readlink -f /home/ubuntu/models/active.gguf > "$OUT/$slug.loaded"
      break
    fi
    say "switch attempt $attempt failed for $preset; retry in 20s"; sleep 20
  done
  if [ "$ok" != 1 ]; then say "SWITCH-FAILED $preset"; continue; fi
  served=$(curl -s -m 10 http://127.0.0.1:8080/props | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("model_path") or "")')
  real=$(readlink -f /home/ubuntu/models/active.gguf)
  say "served: $served | active.gguf -> $real"
  if ! case "$real" in *"$expect"*) true;; *) false;; esac; then
    say "SWITCH-MISMATCH $preset: active.gguf points at $real, not $expect"
    continue
  fi
  say "logic10 $slug"
  python3 "$H" http://127.0.0.1:8080 "$OUT/$slug.json" --slug "$slug" \
      --max-tokens "$CAP" --expect "$expect" >> "$OUT/$slug.log" 2>&1
  rc=$?
  say "done $slug rc=$rc"
  if [ "$rc" = 3 ]; then
    mv "$OUT/$slug.json" "$OUT/invalid/$slug.json.wrong-model" 2>/dev/null || true
    say "GUARD TRIPPED for $slug (server had the wrong weights); result moved to invalid/"
  fi
done

~/bin/srv.sh stock38mtp | tee -a "$LOG"
say "RESTORED stock38mtp"
touch "$OUT/CLEAN_DONE"
say "ALL DONE"
