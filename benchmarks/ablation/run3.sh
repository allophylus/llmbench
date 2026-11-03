#!/usr/bin/env bash
set -uo pipefail
OUT=/home/ubuntu/bench-work/ablation; LOGS=$OUT/logs; mkdir -p "$LOGS"
ARMS="${ARMS:-4b-dflash-nm3 5a-mtp-ngram 5b-dflash 6-dflash-fa-off}"
for a in $ARMS; do
  echo "=== START $a $(date -Is)"
  python3 /home/ubuntu/bench-work/ablate2.py "$a" "$OUT" > "$LOGS/r2-$a.log" 2>&1
  echo "=== EXIT $a rc=$? $(date -Is)"
  [ -f "$OUT/$a.json" ] || echo "MISSING_JSON $a"
done
echo "=== CACHECHECK $(date -Is)"
python3 /home/ubuntu/bench-work/cachecheck.py "$OUT" > "$LOGS/cachecheck.log" 2>&1
echo "=== CACHECHECK rc=$? $(date -Is)"
rm -f /home/ubuntu/.config/systemd/user/qwen-longctx.service.d/z-ablation.conf
if [ -f /home/ubuntu/.config/systemd/user/qwen-longctx.service.d/z-active-model.conf.ablation-parked ]; then
  mv /home/ubuntu/.config/systemd/user/qwen-longctx.service.d/z-active-model.conf.ablation-parked      /home/ubuntu/.config/systemd/user/qwen-longctx.service.d/z-active-model.conf
fi
ln -sfn /home/ubuntu/models/Qwen3.8-27B-Q4_K_M.gguf /home/ubuntu/models/active.gguf
ln -sfn /home/ubuntu/models/mmproj-Qwen3.8-27B-F16.gguf /home/ubuntu/models/active-mmproj.gguf
systemctl --user daemon-reload
systemctl --user restart qwen-longctx.service
for i in $(seq 1 40); do sleep 5; if curl -s -m 5 http://127.0.0.1:8080/v1/models 2>/dev/null | grep -q "active.gguf"; then echo RESTORED_SERVING; break; fi; done
echo "=== RESTORE_DONE $(date -Is)"
echo "ALL_DONE"
