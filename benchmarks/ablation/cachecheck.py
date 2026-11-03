#!/usr/bin/env python3
"""cachecheck.py — is the existing 260K prefill figure cache-assisted?

Question: benchmarks/a3b-260k/ctx260k_at260k.json reports 566.0 t/s prefill for a
260,115-token cold prompt (cache_prompt=false, cached_tokens=0) on **A3B** with
--cache-reuse 256. Is that number real, or an artefact of a cache-assisted prefill?

Plan (on Qwen3.8-27B to keep the switch count low; the flags question is model-agnostic):
  arm P-256  : same server shape as prod (--cache-reuse 256), ~131k cold prompt  -> t/s
  arm P-0    : --cache-reuse 0, same prompt, cold                                -> t/s
  arm P-256b : --cache-reuse 256 again (repeatability)                           -> t/s
Then, only if the numbers agree, an A3B 260K run (stock28/A3B flags) with the flag
that matters for that arm: -np 1 and --cache-reuse 0 vs 256 as time permits.

usage: cachecheck.py <outdir>
Writes <outdir>/cachecheck.json incrementally after every arm.
"""
import json, os, subprocess, sys, threading, time, urllib.request

BASE = "http://127.0.0.1:8080"
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"
BIN = "/home/ubuntu/llama-vulkan/llama-b11517/llama-server"
UNIT = "qwen-longctx.service"
DROPIN_DIR = "/home/ubuntu/.config/systemd/user/qwen-longctx.service.d"
DROPIN = DROPIN_DIR + "/z-ablation.conf"
ACTIVE = DROPIN_DIR + "/z-active-model.conf"
PACK = "/home/ubuntu/llmbench/suite/packs/ctx_filler.txt"
Q38 = "/home/ubuntu/models/Qwen3.8-27B-Q4_K_M.gguf"
Q38_MM = "/home/ubuntu/models/mmproj-Qwen3.8-27B-F16.gguf"
A3B = "/home/ubuntu/models/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
A3B_MM = "/home/ubuntu/models/qwen36/mmproj-Qwen3.6-35B-A3B-F16.gguf"


def sh(cmd, timeout=600):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def post(path, payload, timeout=14400):
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
    return len(post("/tokenize", {"content": text})[0]["tokens"])


class VramSampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop = [], threading.Event()

    def run(self):
        while not self.stop.is_set():
            v = vram()
            if v is not None:
                self.samples.append(v)
            self.stop.wait(1.0)

    def peak(self):
        self.stop.set()
        return round(max(self.samples) / 2**30, 2) if self.samples else None


def build_prompt(target, unit_chars=8000, units=3):
    """Repeated unit built from DIFFERENT blocks (not one block looped), so a
    reused 8k-unit chunk alone cannot explain a fast prefill."""
    pack = open(PACK).read().strip()
    block = pack[:unit_chars]
    unit = "".join(block[i * 200:(i + 1) * 200 + 7800] for i in range(units))
    u_tok = ntok(unit)
    k = max(1, target // u_tok)
    best, tail = None, 0
    for _ in range(8):
        text = unit * k + block[:tail] + "\n\nIgnore the text above. Reply with the single word DONE."
        n = ntok(text)
        err = abs(n - target) / target
        if best is None or err < best[0]:
            best = (err, text, n)
        if err <= 0.005:
            break
        delta = target - n
        if abs(delta) > u_tok // 2:
            k += int(delta / u_tok)
        tail = max(0, min(len(block) - 1, tail + int(delta * unit_chars / u_tok * 1.02)))
    return best[1], best[2], round(best[0], 5)


def wait_ready(timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(5)
        try:
            return get("/props", timeout=5)
        except Exception:
            st = sh(f"systemctl --user is-active {UNIT}").stdout.strip()
            if st not in ("activating", "active", "reloading"):
                raise RuntimeError(f"unit state={st}")
    raise RuntimeError("model never became ready")


def launch(m, mm, flags, label):
    argv = [BIN, "-m", m, "--mmproj", mm, "--host", "0.0.0.0", "--port", "8080",
            "-ngl", "99", "--jinja", "-b", "16384", "-ub", "2048", "--metrics",
            "--reasoning", "off"] + flags
    open(DROPIN, "w").write("# cachecheck %s\n[Service]\nExecStart=\nExecStart=%s\n"
                            % (label, subprocess.list2cmdline(argv)))
    if os.path.exists(ACTIVE) and not os.path.exists(ACTIVE + ".ablation-parked"):
        os.rename(ACTIVE, ACTIVE + ".ablation-parked")
    sh("systemctl --user daemon-reload")
    execstart = sh(f"systemctl --user show {UNIT} -p ExecStart").stdout.strip()
    sh(f"systemctl --user restart {UNIT}")
    props = wait_ready()
    time.sleep(5)
    return {"argv": argv, "execstart": execstart,
            "n_ctx": (props.get("default_generation_settings") or {}).get("n_ctx"),
            "total_slots": props.get("total_slots"),
            "vram_idle_gib": round((vram() or 0) / 2**30, 2)}


def cold_probe(prompt, max_tokens, keepcache):
    s = VramSampler()
    s.start()
    try:
        body, wall = post("/v1/chat/completions", {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "seed": 4242, "max_tokens": max_tokens,
            "cache_prompt": bool(keepcache), "stream": False})
    finally:
        peak = s.peak()
    tim = body.get("timings") or {}
    msg = (body.get("choices") or [{}])[0].get("message") or {}
    return {"wall_s": round(wall, 1), "prompt_n": tim.get("prompt_n"),
            "prompt_ms": round(tim.get("prompt_ms") or 0, 1),
            "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
            "prefill_s": round((tim.get("prompt_ms") or 0) / 1000, 1),
            "predicted_n": tim.get("predicted_n"),
            "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
            "cache_n": tim.get("cache_n"),
            "cached_tokens": ((body.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
            "vram_peak_gib": peak, "content_head": (msg.get("content") or "")[:40]}


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    out = {"phase": "cachecheck", "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "question": "is the existing 260K prefill figure cache-assisted?",
           "arms": {}}

    def save():
        json.dump(out, open(os.path.join(outdir, "cachecheck.json"), "w"), indent=1)

    # ---------- Qwen3.8 131k, cache-reuse 256 vs 0 ----------
    COMMON = ["-c", "131072", "--cache-type-k", "q8_0", "--cache-type-v", "q4_0"]
    try:
        out["q38_prompt"] = {}
        cfg = launch(Q38, Q38_MM, COMMON + ["--cache-reuse", "256", "-fa", "on"], "q38 reuse256")
        out["arms"]["q38_reuse256"] = {**cfg, "prompt": {}}
        save()
        p, n, err = build_prompt(130000)
        out["q38_prompt"] = {"tokens": n, "err": err}
        out["arms"]["q38_reuse256"]["prompt"] = {"tokens": n, "err": err}
        out["arms"]["q38_reuse256"]["probe"] = cold_probe(p, 64, False)
        save()

        cfg = launch(Q38, Q38_MM, COMMON + ["--cache-reuse", "0", "-fa", "on"], "q38 reuse0")
        out["arms"]["q38_reuse0"] = {**cfg, "prompt": {"tokens": n, "err": err}}
        save()
        out["arms"]["q38_reuse0"]["probe"] = cold_probe(p, 64, False)
        save()

        cfg = launch(Q38, Q38_MM, COMMON + ["--cache-reuse", "256", "-fa", "on"], "q38 reuse256 repeat")
        out["arms"]["q38_reuse256_repeat"] = {**cfg, "prompt": {"tokens": n, "err": err}}
        save()
        out["arms"]["q38_reuse256_repeat"]["probe"] = cold_probe(p, 64, False)
        save()

        # ---------- A3B 260K, the original configuration (512 tok, -np default) ----------
        A3B_FLAGS = ["-c", "262144", "--cache-type-k", "q8_0", "--cache-type-v", "q4_0"]
        cfg = launch(A3B, A3B_MM, A3B_FLAGS + ["--cache-reuse", "256", "-fa", "on"], "a3b reuse256")
        out["arms"]["a3b_reuse256"] = cfg
        save()
        pa, na, erra = build_prompt(260000, unit_chars=8000, units=3)
        out["arms"]["a3b_reuse256"]["prompt"] = {"tokens": na, "err": erra}
        save()
        out["arms"]["a3b_reuse256"]["probe"] = cold_probe(pa, 64, False)
        save()

        cfg = launch(A3B, A3B_MM, A3B_FLAGS + ["--cache-reuse", "0", "-fa", "on"], "a3b reuse0")
        out["arms"]["a3b_reuse0"] = {**cfg, "prompt": {"tokens": na, "err": erra}}
        save()
        out["arms"]["a3b_reuse0"]["probe"] = cold_probe(pa, 64, False)
        save()

        # ---------- A3B 260K with -np 1 (per-slot window) ----------
        for tag, extra in (("a3b_np1_reuse256", ["--cache-reuse", "256", "-np", "1"]),
                           ("a3b_np1_reuse0", ["--cache-reuse", "0", "-np", "1"])):
            cfg = launch(A3B, A3B_MM, A3B_FLAGS + extra + ["-fa", "on"], tag)
            out["arms"][tag] = {**cfg, "prompt": {"tokens": na, "err": erra}}
            save()
            out["arms"][tag]["probe"] = cold_probe(pa, 64, False)
            save()
    except Exception as e:
        out["error"] = repr(e)[:500]
    save()
    print("CACHECHECK_DONE", json.dumps({k: (v.get("probe") or {}).get("prefill_tps")
                                         for k, v in out["arms"].items()}), flush=True)


if __name__ == "__main__":
    main()
