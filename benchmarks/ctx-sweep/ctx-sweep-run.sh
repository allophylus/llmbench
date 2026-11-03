#!/usr/bin/env bash
# ctx-sweep-run.sh — driver for the matched-context sweep (runs under screen).
# Order: cheap models first, so a partial sweep still covers the most models.
set -uo pipefail
cd /home/ubuntu/ctx-sweep
LOG=/home/ubuntu/ctx-sweep/driver.log
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

M1=${M1:-lfm3-1-7b-q4-k-m,qwen3-8-27b-q4km,qwen3-8-27b-q4-0,huihui-abl-q4-k-m,davidau-qwen3-8-27b-neo-max-mtp-q4-k-m,qwen3-6-35b-a3b-ud-q4km,ornith-1-5-35b-a3b-q4-k-m}
M2=${M2:-}
R=${R:-4096,32768,65536,131072,262144}
# Slot-aware pass (peers may run their own work between cells):
#   * default per-request timeout is 30 min; a 256K rung on a 35B can exceed it while a
#     peer shares the card -> the request is abandoned, but the server keeps prefillng and
#     finishes long after we gave up. Wait WAIT_S for RUNNING servers to go idle before the
#     next cell, so we never start a second config on a busy card.
WAIT_S=${WAIT_S:-900}

wait_idle(){
  local t0=$(date +%s)
  while :; do
    local busy=$(ps -eo cmd | grep -c "[l]lama-vulkan/.*llama-server --\|--host 0.0.0.0 --port 80")
    local port=$(ss -ltn 'sport = :8080' | tail -n +2 | wc -l)
    [ "$port" -eq 0 ] && return 0
    local now=$(date +%s); [ $((now-t0)) -ge "$WAIT_S" ] && { say "wait_idle timeout (${WAIT_S}s)"; return 1; }
    sleep 15
  done
}

say "SWEEP START models=$M1 (+${M2:-}) rungs=$R"
python3 ctx_sweep.py --models "$M1" --rungs "$R" >> run1.log 2>&1
say "RUN1 rc=$? $(grep -c '^DONE' run1.log) cells logged"

if [ -n "$M2" ]; then
  say "pass 2: $M2"
  python3 ctx_sweep.py --models "$M2" --rungs "$R" >> run2.log 2>&1
  say "RUN2 rc=$? "
fi

rm -f ~/.config/systemd/user/qwen-longctx.service.d/zz-ctxsweep-lock.conf
systemctl --user daemon-reload
systemctl --user reset-failed qwen-longctx 2>/dev/null || true
say "UNIT UNLOCKED (zz-ctxsweep-lock.conf removed)"
python3 ctx_sweep.py --report >> report.log 2>&1
say "REPORT rc=$?"
~/bin/srv.sh stock38mtp >> "$LOG" 2>&1
say "RESTORED stock38mtp"
touch /home/ubuntu/ctx-sweep/ALLDONE
say "ALL DONE"
