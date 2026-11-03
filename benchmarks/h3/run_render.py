#!/usr/bin/env python3
"""Submit the H3 baseline payload to MSI ComfyUI and record wall time + peak VRAM.

Sampling loop runs on the gateway, polling /queue + /system_stats (torch_vram_*).
"""
import json, subprocess, sys, time, datetime

import os
MSI = os.environ.get("RENDER_HOST", "")  # set to user@host of the render box before running
def sh(cmd, timeout=60):
    return subprocess.run(["ssh", "-o", "ConnectTimeout=8", MSI, cmd],
                          capture_output=True, text=True, timeout=timeout)

payload = open("/tmp/h3_bench_payload.json").read()
p = subprocess.run(["ssh", "-o", "ConnectTimeout=8", MSI,
                    "curl -s -m 20 -X POST http://127.0.0.1:8188/prompt -H 'Content-Type: application/json' -d @-"],
                   input=payload, capture_output=True, text=True, timeout=90)
print("submit:", p.stdout[:500], "ERR:", p.stderr[:300])
res = json.loads(p.stdout)
pid = res.get("prompt_id")
if not pid:
    sys.exit("submit failed: " + p.stdout)
print("prompt_id:", pid)

t0 = time.time()
peak = 0
last_pct = -1
state = {"pid": pid, "t0": t0, "t0_iso": datetime.datetime.now().astimezone().isoformat()}
json.dump(state, open("/tmp/h3_bench_state.json", "w"))

while True:
    el = time.time() - t0
    q = sh("curl -s -m 5 http://127.0.0.1:8188/queue")
    st = sh("curl -s -m 5 http://127.0.0.1:8188/system_stats")
    try:
        vram = json.loads(st.stdout)["devices"][0].get("torch_vram_total", 0)
        peak = max(peak, vram)
    except Exception as e:
        print("stats parse:", e, st.stdout[:100])
    try:
        qj = json.loads(q.stdout)
        run = [x for x in qj.get("queue_running", [])]
        pend = qj.get("queue_pending", [])
    except Exception:
        run, pend = ["?"], []
    print(f"[{el:7.1f}s] queue run={len(run)} pend={len(pend)} vram={vram/2**20:.0f}MiB", flush=True)
    if not run and not pend and el > 20:
        break
    time.sleep(15)

# confirm history entry
h = sh(f"curl -s -m 10 http://127.0.0.1:8188/history/{pid}")
try:
    hj = json.loads(h.stdout)
    entry = hj.get(pid, {})
    outs = entry.get("outputs", {})
    print("status_ok:", entry.get("status", {}).get("status_str"))
    print("outputs:", json.dumps(outs)[:800])
except Exception as e:
    print("history parse err:", e, h.stdout[:300])

wall = time.time() - t0
res = {"prompt_id": pid, "wall_s": round(wall, 1), "peak_vram_mib": round(peak / 2**20) if peak else None}
json.dump(res, open("/tmp/h3_bench_result.json", "w"), indent=1)
print(json.dumps(res))
