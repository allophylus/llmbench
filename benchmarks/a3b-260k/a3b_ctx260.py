#!/usr/bin/env python3
"""a3b_ctx260.py — 260K-context measurement for A3B on :8080.

Methods (BENCHMARK.md):
  * ctx window      : /props -> default_generation_settings.n_ctx
  * prefill/decode  : POST /v1/chat/completions, cache_prompt=false, temp 0,
                      usage.timings.prompt_per_second / predicted_per_second
  * VRAM            : /sys/class/drm/card1/device/mem_info_vram_used (sampled 1 Hz during call)
Token calibration via POST /tokenize (documented in ctx_embed.py contract).
"""
import json, os, sys, threading, time, urllib.request

BASE = os.environ.get("BASE", "<gate-server>")
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/a3b_ctx260.json"
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"


def post(path, payload, timeout=3600):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


def get(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def vram():
    try:
        return int(open(VRAM).read().strip())
    except Exception:
        return None


def ntok(text):
    d, _ = post("/tokenize", {"content": text})
    return len(d["tokens"])


SAMPLES = []


def sampler(stop):
    while not stop.is_set():
        v = vram()
        if v is not None:
            SAMPLES.append(v)
        stop.wait(1.0)


def chat(label, prompt, max_tokens=256):
    SAMPLES.clear()
    stop = threading.Event()
    th = threading.Thread(target=sampler, args=(stop,), daemon=True)
    th.start()
    body, wall = post("/v1/chat/completions",
                      {"messages": [{"role": "user", "content": prompt}],
                       "temperature": 0, "max_tokens": max_tokens,
                       "cache_prompt": False, "stream": False})
    stop.set()
    th.join(1)
    tim = body.get("timings") or {}
    return {"label": label, "wall_s": round(wall, 1),
            "prompt_n": tim.get("prompt_n"), "predicted_n": tim.get("predicted_n"),
            "prefill_ms": round(tim.get("prompt_ms") or 0, 1),
            "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
            "decode_ms": round(tim.get("predicted_ms") or 0, 1),
            "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
            "usage": body.get("usage"),
            "vram_peak_gib": round(max(SAMPLES) / 2**30, 2) if SAMPLES else None,
            "vram_samples": len(SAMPLES)}


def main():
    res = {"base": BASE, "when": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        p = get("/props")
    except Exception as e:
        res["error"] = "props: %s" % e
        json.dump(res, open(OUT, "w"), indent=1); print(json.dumps(res)); return 1
    res["n_ctx"] = (p.get("default_generation_settings") or {}).get("n_ctx")
    res["model_path"] = p.get("model_path")
    res["build_info"] = p.get("build_info")
    res["vram_idle_gib"] = round(vram() / 2**30, 2) if vram() else None

    units = [("prefill-probe", "The quick brown fox jumps over the lazy dog. " * 60 + "\n\nCount from 1 to 200.", 256)]
    # document-style calibration toward the window
    for target in (131000, 262000):
        # ~3.4 chars/token for this filler; calibrate exactly with /tokenize
        base = units[0][1]
        per = ntok(base)
        reps = max(1, int(target * len(base) / per / len(base)))
        text = base * reps
        n = ntok(text)
        tries = 0
        while n < target * 0.98 and tries < 8:
            reps = int(reps * target / n * 1.01)
            text = base * reps
            n = ntok(text)
            tries += 1
        while n > target and tries < 16:
            reps -= max(1, int(reps * 0.01))
            text = base * reps
            n = ntok(text)
            tries += 1
        units.append((f"ctx-{target//1000}k", text + "\n\nReply with the single word DONE.", 32))
        units[-1] = (units[-1][0], units[-1][1], 32)

    res["runs"] = []
    for label, prompt, mt in units:
        try:
            n = ntok(prompt)
        except Exception:
            n = None
        try:
            r = chat(label, prompt, mt)
            r["tokens_calibrated"] = n
            res["runs"].append(r)
            print(json.dumps(r), flush=True)
        except Exception as e:
            res["runs"].append({"label": label, "tokens_calibrated": n, "error": str(e)[:300]})
            print(label, "ERROR", str(e)[:200], flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
