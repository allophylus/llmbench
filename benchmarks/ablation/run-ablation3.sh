#!/usr/bin/env bash
# run-ablation3.sh — driver for the all-models accelerator ablation.
#   screen -dmS ablate3 bash ~/bench-work/ablation3/run-ablation3.sh [model-slugs...]
# Resumable: ablate3.py skips arms already recorded ok / not-applicable in state.json.
set -uo pipefail
W=/home/ubuntu/bench-work/ablation3
D=/home/ubuntu/.config/systemd/user/qwen-longctx.service.d
mkdir -p "$W/logs"
cd "$W"
SLUGS="${*:-qwen3-8-27b-q4km qwen3-8-27b-q4-0 davidau-qwen3-8-27b-neo-max-mtp-q4-k-m huihui-abl-q4-k-m qwen3-6-35b-a3b-ud-q4km ornith-1-5-35b-a3b-q4-k-m lfm3-1-7b-q4-k-m}"

echo "=== ABLATE3 START $(date -Is) slugs: $SLUGS"
for s in $SLUGS; do
  echo "=== GROUP $s $(date -Is)"
  python3 "$W/ablate3.py" "$s" >> "$W/logs/run-$s.log" 2>&1
  echo "=== GROUP_EXIT $s rc=$? $(date -Is)"
done

# ---- restore: unpark foreign drop-ins, drop ours, bring back the live prod preset ----
rm -f "$D/z-ablation3.conf"
for f in "$D"/*.ablation3-parked; do [ -e "$f" ] && mv "$f" "${f%.ablation3-parked}"; done
[ -f "$D/z-active-model.conf.ablation3-parked" ] && mv "$D/z-active-model.conf.ablation3-parked" "$D/z-active-model.conf"
ln -sfn /home/ubuntu/models/Qwen3.8-27B-Q4_K_M.gguf /home/ubuntu/models/active.gguf
ln -sfn /home/ubuntu/models/mmproj-Qwen3.8-27B-F16.gguf /home/ubuntu/models/active-mmproj.gguf
systemctl --user daemon-reload
systemctl --user restart qwen-longctx.service
systemctl --user stop lfm3-ablation.service 2>/dev/null
for i in $(seq 1 60); do
  sleep 5
  if curl -s -m 5 http://127.0.0.1:8080/props | grep -q '"n_ctx": *131072'; then
    if curl -s -m 20 -X POST http://127.0.0.1:8080/completion -d '{"prompt":"hi","n_predict":2}' \
        | grep -q '"predicted_n": *2'; then echo "RESTORED_SERVING $(date -Is)"; break; fi
  fi
done
systemctl --user show qwen-longctx.service -p ExecStart | tr ' ' '\n' | grep -E 'spec-type|n-max|-m$|active' | tr '\n' ' '; echo
echo "=== ABLATE3 DONE $(date -Is)"
