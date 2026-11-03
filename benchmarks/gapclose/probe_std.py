#!/usr/bin/env python3
"""probe_std.py — the documented 'standard' speed probe (BENCHMARK.md §4 + a3b 30K cell).

usage: probe_std.py --target 30000 --max-tokens 64 --label ctx30k-256k \
                    --out out.json [--reps 3] [--settle 20]

One cold request per rep: temperature 0, cache_prompt false, stream false, token-calibrated
prompt built by a3b_ctx_run3.build() (repeated unit — /tokenize only linear on repeated
content). VRAM sampled at 1 Hz across all reps; peak/tail reported.

--settle waits N seconds before the first rep so an idle-warmup request's VRAM release is
not blended into the numbers (prefill/decode come from the server timings block, which is
per-request and unaffected; settle only makes VRAM sampling clean).
"""
import json, os, sys, threading, time, urllib.request

sys.path.insert(0, os.path.join(os.environ.get("BENCHWORK","/bench-work")))
import a3b_ctx_run3 as h

BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"


def post(path, payload, timeout=7200):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read())


def vram():
    try:
        return int(open(VRAM).read().strip())
    except Exception:
        return None


def main():
    args = sys.argv[1:]
    target, mt, label, out, reps, settle = 30000, 64, "probe", "out.json", 1, 0
    for i, a in enumerate(args):
        if a == "--target": target = int(args[i + 1])
        if a == "--max-tokens": mt = int(args[i + 1])
        if a == "--label": label = args[i + 1]
        if a == "--out": out = args[i + 1]
        if a == "--reps": reps = int(args[i + 1])
        if a == "--settle": settle = int(args[i + 1])

    time.sleep(settle)
    prompt, n, cal = h.build(target)
    props = get("/props")
    model_path = props.get("model_path")
    res = {"label": label, "base": BASE, "model_path": model_path,
           "build_info": (props.get("build_info") or ""),
           "target_tokens": target, "tokens_calibrated": n, "calibration": cal,
           "max_tokens": mt, "temperature": 0, "cache_prompt": False,
           "n_ctx": (props.get("default_generation_settings") or {}).get("n_ctx"),
           "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "vram_idle_gib": round(vram() / 2**30, 2) if vram() else None, "runs": []}

    samples, stop = [], threading.Event()

    def sampler():
        while not stop.is_set():
            v = vram()
            if v is not None:
                samples.append(v)
            stop.wait(1.0)

    threading.Thread(target=sampler, daemon=True).start()
    try:
        for rep in range(reps):
            body, wall = post("/v1/chat/completions",
                              {"messages": [{"role": "user", "content": prompt}],
                               "temperature": 0, "max_tokens": mt,
                               "cache_prompt": False, "stream": False})
            tim = body.get("timings") or {}
            msg = (body.get("choices") or [{}])[0].get("message") or {}
            res["runs"].append({
                "rep": rep + 1, "wall_s": round(wall, 1),
                "prompt_n": tim.get("prompt_n"), "predicted_n": tim.get("predicted_n"),
                "prefill_ms": round(tim.get("prompt_ms") or 0, 1),
                "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
                "decode_ms": round(tim.get("predicted_ms") or 0, 1),
                "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
                "cached_tokens": ((body.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
                "finish_reason": (body.get("choices") or [{}])[0].get("finish_reason"),
                "content_head": (msg.get("content") or "")[:60]})
            print(json.dumps(res["runs"][-1]), flush=True)
            time.sleep(2)
    except Exception as e:
        res["error"] = str(e)[:400]
    stop.set()
    time.sleep(1.2)
    if samples:
        res["vram_peak_gib"] = round(max(samples) / 2**30, 2)
        res["vram_tail_gib"] = round(samples[-1] / 2**30, 2)
        res["vram_samples"] = len(samples)

    def stats(key):
        v = [r[key] for r in res["runs"] if r.get(key)]
        if not v:
            return None
        m = sum(v) / len(v)
        return {"mean": round(m, 2), "min": round(min(v), 2), "max": round(max(v), 2),
                "spread_pct": round((max(v) - min(v)) / m * 100, 2) if m else None, "n": len(v)}

    res["summary"] = {k: stats(k) for k in ("prefill_tps", "decode_tps", "wall_s")}
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res["summary"], indent=1), flush=True)
    return 0 if "error" not in res else 1


if __name__ == "__main__":
    sys.exit(main())
