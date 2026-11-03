#!/usr/bin/env python3
"""a3b_ctx_run3.py — long-context probe, repeated-unit prompt (measured-linear).

usage: a3b_ctx_run3.py <n_tokens_target> <max_tokens> <label> <out.json>

Verified prerequisite: POST /tokenize is exactly linear on repeated identical content
(1x/2x/3x of a 40k-char unit -> 9800/19600/29400 tokens). So the prompt is
  unit*K + prefix(unit, tail_chars) + TAIL
and is re-tokenized after each adjustment until within 0.5% of target. One cold
completion (cache_prompt=false, temp 0); timings from the server's timings block;
VRAM from sysfs at 1 Hz.
"""
import json, os, sys, threading, time, urllib.request

BASE = os.environ.get("BASE", "<gate-server>")
PACK = "llmbench/suite/packs/ctx_filler.txt"
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"
TAIL = "\n\nIgnore the text above. Reply with the single word DONE."


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


def ntok(text):
    return len(post("/tokenize", {"content": text})[0]["tokens"])


def build(target, unit_chars=30000):
    unit = open(PACK).read().strip()[:unit_chars]
    u_tok = ntok(unit)
    k = max(1, target // u_tok)
    best, tail = None, 0
    for _ in range(8):
        text = unit * k + unit[:tail] + TAIL
        n = ntok(text)
        err = abs(n - target) / target
        if best is None or err < best[0]:
            best = (err, text, n, k, tail)
        if err <= 0.005:
            break
        delta = target - n
        if abs(delta) > u_tok // 2:
            k += int(delta / u_tok)
        tail = max(0, min(len(unit) - 1, tail + int(delta * unit_chars / u_tok * 1.02)))
    return best[1], best[2], {"units": best[3], "tail_chars": best[4], "unit_tokens": u_tok,
                              "unit_chars": unit_chars, "err": round(best[0], 5)}


def main():
    target, mt, label, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
    prompt, n, cal = build(target)
    res = {"label": label, "target_tokens": target, "tokens_calibrated": n, "calibration": cal,
           "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "n_ctx": (get("/props").get("default_generation_settings") or {}).get("n_ctx"),
           "vram_idle_gib": round(vram() / 2**30, 2) if vram() else None}
    samples, stop = [], threading.Event()

    def sampler():
        while not stop.is_set():
            v = vram()
            if v is not None:
                samples.append(v)
            stop.wait(1.0)

    threading.Thread(target=sampler, daemon=True).start()
    try:
        body, wall = post("/v1/chat/completions",
                          {"messages": [{"role": "user", "content": prompt}],
                           "temperature": 0, "max_tokens": mt,
                           "cache_prompt": False, "stream": False})
        tim = body.get("timings") or {}
        msg = (body.get("choices") or [{}])[0].get("message") or {}
        res.update({"wall_s": round(wall, 1),
                    "prompt_n": tim.get("prompt_n"), "predicted_n": tim.get("predicted_n"),
                    "prefill_ms": round(tim.get("prompt_ms") or 0, 1),
                    "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
                    "decode_ms": round(tim.get("predicted_ms") or 0, 1),
                    "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
                    "usage": body.get("usage"),
                    "content_head": (msg.get("content") or "")[:60]})
    except Exception as e:
        res["error"] = str(e)[:400]
    stop.set()
    time.sleep(1.1)
    res["vram_peak_gib"] = round(max(samples) / 2**30, 2) if samples else None
    res["vram_tail_gib"] = round(samples[-1] / 2**30, 2) if samples else None
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res), flush=True)
    return 0 if "error" not in res else 1


if __name__ == "__main__":
    sys.exit(main())
