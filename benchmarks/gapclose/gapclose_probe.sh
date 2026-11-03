#!/usr/bin/env bash
# gapclose_probe.sh — STEP 1 + STEP 2 probe runs. Runs INSIDE screen on the GPU host.
# Each block: switch preset -> wait -> probe -> leave server as-is for next block.
set -uo pipefail
# Environment (set these before running; generic placeholders, no host specifics):
: "${BENCHWORK:?set BENCHWORK to the remote bench-work dir}"
: "${OUTROOT:?set OUTROOT to the remote output dir}"
: "${LLAMA:?set LLAMA to the llama.cpp build tree}"
: "${MODELS:?set MODELS to the model dir on the GPU host}"
: "${UNITDIR:=$HOME}"
: "${SERVED:?set SERVED to the served model file name}"
: "${PROJ:?set PROJ to the served projector file name}"

cd "$BENCHWORK"
OUT=$OUTROOT
mkdir -p "$OUT"
LOG="$OUT/run.log"
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

wait_ready() {
  for i in $(seq 1 60); do
    if curl -s -m 4 http://127.0.0.1:8080/v1/models | grep -q "$SERVED"; then say "ready"; return 0; fi
    sleep 5
  done
  say "NOT READY"; return 1
}

# ---------- STEP 2 (short ctx, cheap) ----------
say "=== STEP2 A3B 32K x3 ==="
~/bin/switch-model.sh qwen36 >/dev/null 2>&1 || say "switch qwen36 failed"
# switch-model.sh sets qwen36 to -c 262144; force 32768 via ablation-style drop-in
cat > $UNITDIR/systemd/user/qwen-longctx.service.d/z-gapclose.conf <<'EOF'
[Service]
ExecStart=
ExecStart=$LLAMA/llama-b11517/llama-server -m $MODELS/$SERVED --mmproj $MODELS/$PROJ --host 0.0.0.0 --port 8080 -c 32768 -ngl 99 --jinja -fa on -b 16384 -ub 2048 --cache-type-k q8_0 --cache-type-v q4_0 --cache-reuse 256 --metrics
EOF
systemctl --user daemon-reload
systemctl --user restart qwen-longctx.service
wait_ready && python3 probe_std.py --target 30000 --max-tokens 64 --label a3b-ctx32k-x3 --reps 3 --settle 15 --out "$OUT/a3b-ctx32k-x3.json" >> "$LOG" 2>&1
say "STEP2 A3B done"

# ---------- STEP 1 (the pending cell) ----------
say "=== STEP1 A3B 256K 30K probe ==="
sed -i 's/-c 32768/-c 262144/' $UNITDIR/systemd/user/qwen-longctx.service.d/z-gapclose.conf
systemctl --user daemon-reload
systemctl --user restart qwen-longctx.service
wait_ready && python3 probe_std.py --target 30000 --max-tokens 64 --label a3b-ctx256k-30k --reps 1 --settle 20 --out "$OUT/a3b-ctx256k-30k.json" >> "$LOG" 2>&1
say "STEP1 done"

# ---------- STEP 2 (256K, 3x) ----------
say "=== STEP2 A3B 256K x3 ==="
python3 probe_std.py --target 30000 --max-tokens 64 --label a3b-ctx256k-x3 --reps 3 --settle 20 --out "$OUT/a3b-ctx256k-x3.json" >> "$LOG" 2>&1
say "STEP2 256K done"

# ---------- STEP 2 Qwen3.8-27B Q4_K_M (no spec, 32K) ----------
say "=== STEP2 Qwen3.8-27B x3 ==="
cat > $UNITDIR/systemd/user/qwen-longctx.service.d/z-gapclose.conf <<'EOF'
[Service]
ExecStart=
ExecStart=$LLAMA/llama-b11517/llama-server -m $MODELS/$SERVED --mmproj $MODELS/$PROJ --host 0.0.0.0 --port 8080 -c 32768 -ngl 99 --jinja -fa on -b 16384 -ub 2048 --cache-type-k q8_0 --cache-type-v q4_0 --cache-reuse 256 --metrics --chat-template-kwargs {"enable_thinking":false}
EOF
~/bin/switch-model.sh stock38 >/dev/null 2>&1 || say "switch stock38 failed"
systemctl --user daemon-reload
systemctl --user restart qwen-longctx.service
wait_ready && python3 probe_std.py --target 30000 --max-tokens 64 --label qwen38-27b-ctx32k-x3 --reps 3 --settle 15 --out "$OUT/qwen38-27b-ctx32k-x3.json" >> "$LOG" 2>&1
say "STEP2 Qwen3.8 done"

# ---------- restore prod ----------
rm -f $UNITDIR/systemd/user/qwen-longctx.service.d/z-gapclose.conf
systemctl --user daemon-reload
~/bin/switch-model.sh stock38mtp >> "$LOG" 2>&1
say "RESTORED stock38mtp"
say "ALL DONE"
touch "$OUT/ALLDONE"
