#!/usr/bin/env python3
"""ablate2.py — accelerator ablation, round 2 (fixed measurement plan).

Key changes vs ablate.py round 1 (see RESULTS.md "round 1 defects"):
  * decode uses /completion with an explicit chat-template-applied prompt and
    ignore_eos, n_predict=400 -> a real steady-state decode measurement.
  * prompts are built from varied blocks (a fixed 30k-char unit in a loop makes every
    accelerator look useless, incl. ngram): unit = block*20 + block[:tail].
  * reasoning: template kwargs verified effective (reply has no reasoning_content);
    --reasoning off is used anyway as the documented replacement for the deprecated kwarg.
  * VRAM: baseline expectations are sampled before measuring (idle vs peak).

usage: ablate2.py <arm-id> <outdir> [--skip-probes]
"""
import json, os, re, subprocess, sys, threading, time, urllib.request

BASE = "http://127.0.0.1:8080"
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"
BIN = "/home/ubuntu/llama-vulkan/llama-b11517/llama-server"
UNIT = "qwen-longctx.service"
DROPIN_DIR = "/home/ubuntu/.config/systemd/user/qwen-longctx.service.d"
DROPIN = DROPIN_DIR + "/z-ablation.conf"
ACTIVE = DROPIN_DIR + "/z-active-model.conf"
MODEL_DIR = "/home/ubuntu/models"
MODEL_FILE = "Qwen3.8-27B-Q4_K_M.gguf"
MMPROJ_FILE = "mmproj-Qwen3.8-27B-F16.gguf"
MMPROJ_SYM = "/home/ubuntu/models/active-mmproj.gguf"
DFLASH = "/home/ubuntu/models/Qwen3.8-27B-DFlash2-Q4_K_M.gguf"
PACK = "/home/ubuntu/llmbench/suite/packs/ctx_filler.txt"
GLOBAL_FLAGS = ["--host", "0.0.0.0", "--port", "8080", "-c", "131072", "-ngl", "99", "--jinja",
                "-b", "16384", "-ub", "2048", "--cache-type-k", "q8_0", "--cache-type-v", "q4_0",
                "--cache-reuse", "256", "--metrics"]
THINK = r"--chat-template-kwargs {\"enable_thinking\":false}"
REASONING = ["--reasoning", "off"]
# NOTE b11517: --spec-draft-n-max / --spec-draft-n-min are ONE option per server and
# also server-wide; keep one pair per launch. DFlash2 carries its own block_size=8 and
# its n_max comes from the shared option, so DFlash runs use the 7/1 pair.
NMAX, NMIN = "7", "1"
MTP = ["--spec-type", "draft-mtp", "--spec-draft-n-max", NMAX, "--spec-draft-n-min", NMIN]
DFLASH_FLAGS = ["--spec-type", "draft-dflash", "--spec-draft-model", DFLASH]
# arm 5 (MTP + DFlash) needs TWO launches: b11517 cannot create the MTP extra-model
# context once the DFlash draft model is loaded ("context type MTP requested but model
# doesn't contain MTP layers"), and MTP-only does not serve without ngram-cache.
MTP_NGRAM = MTP + ["--spec-type", "ngram-cache"]
KVF16 = ["--cache-type-k", "f16", "--cache-type-v", "f16"]

ARMS = {
    # DFlash pair: n_max 7 (round 1) and n_max 3 (server default) measured; the n_max 7
    # figure is the headline in RESULTS.md and the pair is what arm 5 combines.
    "4b-dflash-nm3":   {"fa": "on",  "extra": ["--spec-type", "draft-dflash",
                                               "--spec-draft-model", DFLASH]},

    "1-baseline":      {"fa": "on",  "extra": []},
    "2-fa-off":        {"fa": "off", "extra": [], "kv": KVF16,
                        "note": "q8_0K/q4_0V requires FA; FA-off only runnable with f16 KV"},
    "3-mtp":           {"fa": "on",  "extra": MTP},
    "4-dflash":        {"fa": "on",  "extra": DFLASH_FLAGS + ["--spec-draft-n-max", "7"]},
    "5a-mtp-ngram":    {"fa": "on",  "extra": MTP_NGRAM,
                        "note": "arm 5 half 1 — MTP as the prod stock38mtp preset runs it"},
    "5b-dflash":       {"fa": "on",  "extra": DFLASH_FLAGS,
                        "note": "arm 5 half 2 — same DFlash config as 4b, n_max 3"},
    "6-dflash-fa-off": {"fa": "off", "extra": DFLASH_FLAGS, "kv": KVF16,
                        "note": "q8_0K/q4_0V requires FA; FA-off only runnable with f16 KV"},
}


def sh(cmd, timeout=600):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def http_post(path, payload, timeout=7200):
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
    return len(http_post("/tokenize", {"content": text})[0]["tokens"])


class VramSampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop = [], threading.Event()

    def run(self):
        while not self.stop.is_set():
            v = vram()
            if v is not None:
                self.samples.append(v)
            self.stop.wait(0.25)

    def peak(self):
        self.stop.set()
        self.join(2)
        return round(max(self.samples) / 2**30, 2) if self.samples else None


def _timings(body, wall):
    tim = body.get("timings") or {}
    return {"wall_s": round(wall, 2), "prompt_n": tim.get("prompt_n"),
            "predicted_n": tim.get("predicted_n"),
            "prefill_ms": round(tim.get("prompt_ms") or 0, 1),
            "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
            "prefill_s": round((tim.get("prompt_ms") or 0) / 1000, 1),
            "decode_ms": round(tim.get("predicted_ms") or 0, 1),
            "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
            "cache_n": tim.get("cache_n")}


def chat(prompt, max_tokens, seed=4242, sampler=False):
    s = VramSampler()
    if sampler:
        s.start()
    try:
        body, wall = http_post("/v1/chat/completions", {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "seed": seed, "max_tokens": max_tokens,
            "cache_prompt": False, "stream": False})
    finally:
        peak = s.peak() if sampler else None
    r = _timings(body, wall)
    r["vram_peak_gib"] = peak
    ch = (body.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    r["content"] = msg.get("content") or ""
    r["reasoning_content"] = (msg.get("reasoning_content") or "")[:200]
    r["finish_reason"] = ch.get("finish_reason")
    r["cached_tokens"] = ((body.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens")
    return r


def completion(prompt, n_predict, sampler=False):
    s = VramSampler()
    if sampler:
        s.start()
    try:
        body, wall = http_post("/completion", {
            "prompt": prompt, "temperature": 0, "seed": 4242, "n_predict": n_predict,
            "ignore_eos": True, "cache_prompt": False, "stream": False})
    finally:
        peak = s.peak() if sampler else None
    r = _timings(body, wall)
    r["vram_peak_gib"] = peak
    r["content"] = (body.get("content") or "")[:200]
    r["stopped"] = {"stop": body.get("stop"), "truncated": body.get("truncated")}
    return r


def templated(prompt):
    """Render the served chat template for a user message (thinking disabled)."""
    body, _ = http_post("/apply-template", {"messages": [{"role": "user", "content": prompt}]})
    return body["prompt"]


def build_prompt(target, block_chars=1500, blocks=20):
    """Varied-but-repeatable long prompt: unit = 20 different blocks, repeated K times."""
    pack = open(PACK).read().strip()
    block = pack[:block_chars]
    unit = block * blocks
    u_tok = ntok(unit)
    k = max(1, target // u_tok)
    best, tail = None, 0
    for _ in range(8):
        text = unit * k + block[:tail] + "\n\nReply with the single word DONE."
        n = ntok(text)
        err = abs(n - target) / target
        if best is None or err < best[0]:
            best = (err, text, n)
        if err <= 0.005:
            break
        delta = target - n
        if abs(delta) > u_tok // 2:
            k += int(delta / u_tok)
        tail = max(0, min(len(block) - 1, tail + int(delta * block_chars / u_tok * 1.02)))
    return best[1], best[2], round(best[0], 5)


def wait_ready(timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(3)
        try:
            return get("/props", timeout=5)
        except Exception:
            st = sh(f"systemctl --user is-active {UNIT}").stdout.strip()
            if st not in ("activating", "active", "reloading"):
                raise RuntimeError(f"unit state={st}")
    raise RuntimeError("model never became ready")


def journal_tail(n=1500):
    return sh(f"journalctl --user -u {UNIT} -n {n} --no-pager").stdout


SHORT_PROMPT = (
    "You are given a routine list of unrelated jottings, then one question.\n" +
    "".join(f"Note {i}: the warehouse team recorded pallet {(i*37) % 997} moved between bays "
            f"{(i*13) % 50} and {(i*7) % 50} during shift {(i % 3)+1}, with no discrepancies noted.\n"
            for i in range(1, 45)) +
    "\n\nQuestion: reply with ONLY the result of 47*13-61, as a bare integer.")

ANSWERS = [
    ("answer-arith", "Reply with only the integer result of 1847 * 29 + 37. No words, just the number."),
    ("answer-list", "Name, in order, the capital of Japan, then the capital of France, then the capital of Kenya. Reply on one line, comma-separated, nothing else."),
    ("answer-code", "Write a Python one-liner that returns the number of vowels in a string s. Reply with the code only, no explanation."),
    ("answer-prose", "In exactly two sentences, state what a KV cache stores in an LLM inference engine. No preamble."),
    ("answer-para", "Write a 120-word product description for a stainless steel travel mug that keeps coffee hot for 8 hours. Plain prose, no lists, no headings."),
    ("answer-para2", "In one paragraph of at least 100 words, explain to a junior engineer why batching requests improves GPU utilisation during LLM inference. Plain prose only."),
]

PREFILL_JSON = "/home/ubuntu/bench-work/ablation/_prefill_30k.txt"


def main():
    arm = sys.argv[1]
    outdir = sys.argv[2]
    spec = ARMS[arm]
    os.makedirs(outdir, exist_ok=True)
    out = {"arm": arm, "phase": "round2", "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "model": os.path.join(MODEL_DIR, MODEL_FILE), "fa": spec["fa"],
           "extra_flags": spec["extra"], "kv_override": spec.get("kv"),
           "arm_note": spec.get("note"),
           "server_build": sh(f"{BIN} --version 2>&1 | head -3").stdout.strip()}

    # fixed model link + mmproj link
    for link, target in (("/home/ubuntu/models/active.gguf", os.path.join(MODEL_DIR, MODEL_FILE)),
                         (MMPROJ_SYM, os.path.join(MODEL_DIR, MMPROJ_FILE))):
        if os.path.islink(link):
            os.remove(link)
        os.symlink(target, link)
    out["model_link"] = os.path.realpath("/home/ubuntu/models/active.gguf")

    gflags = list(GLOBAL_FLAGS)
    if spec.get("kv"):
        i = gflags.index("--cache-type-k")
        gflags[i:i + 4] = spec["kv"]
    out["kv_cache_type"] = "f16/f16" if spec.get("kv") else "q8_0/q4_0"
    argv = ([BIN, "-m", "/home/ubuntu/models/active.gguf", "--mmproj", MMPROJ_SYM]
            + gflags + ["-fa", spec["fa"]] + spec["extra"] + REASONING)
    out["argv"] = argv
    open(DROPIN, "w").write("# ablation arm %s (temporary)\n[Service]\nExecStart=\nExecStart=%s\n"
                            % (arm, subprocess.list2cmdline(argv)))
    if os.path.exists(ACTIVE) and not os.path.exists(ACTIVE + ".ablation-parked"):
        os.rename(ACTIVE, ACTIVE + ".ablation-parked")
    sh("systemctl --user daemon-reload")
    out["systemd_execstart"] = sh(f"systemctl --user show {UNIT} -p ExecStart").stdout.strip()
    if spec.get("kv") and "cache-type-v f16" not in out["systemd_execstart"]:
        raise RuntimeError("kv override not in ExecStart")
    sh(f"systemctl --user restart {UNIT}")
    props = wait_ready()
    time.sleep(5)
    # readiness only confirms the socket is up; a crash-looping unit also answers briefly.
    # Require a real completion and record the restart counter.
    for _ in range(20):
        try:
            b, _w = http_post("/completion", {"prompt": "x", "n_predict": 1,
                                              "cache_prompt": False}, timeout=120)
            if b.get("content") is not None or "timings" in b:
                break
        except Exception:
            time.sleep(3)
    out["restarts_after_launch"] = sh(f"systemctl --user show {UNIT} -p NRestarts").stdout.strip()
    out["n_ctx"] = (props.get("default_generation_settings") or {}).get("n_ctx")
    out["total_slots"] = props.get("total_slots")
    ids = [c.get("id") for c in (props.get("models") or []) if isinstance(c, dict)]
    out["model_alias"] = props.get("model_alias")
    out["vram_idle_gib"] = round((vram() or 0) / 2**30, 2)
    js = journal_tail(1500)
    out["journal_startup_lines"] = [l for l in js.splitlines()
                                    if any(s in l for s in ("speculative", "model loaded",
                                                            "n_ctx_slot", "cache_type",
                                                            "flash", "reuse", "error", "not supported"))][-25:]

    # warm-up (not recorded): graph capture + first-token path
    _, wall = http_post("/completion", {"prompt": "hello", "n_predict": 4, "temperature": 0,
                                        "ignore_eos": True, "cache_prompt": False})
    out["warmup_s"] = round(wall, 2)

    # --- A. decode, short context (steady state, 400 generated tokens) ---
    try:
        tpl = templated(SHORT_PROMPT)
        out["decode_short"] = completion(tpl, 400, sampler=True)
        out["decode_short"]["prompt_tokens"] = ntok(tpl)
    except Exception as e:
        out["decode_short"] = {"error": repr(e)[:300]}
    # --- B. decode, long context (~30k prefill, then 400 generated at depth) ---
    try:
        if os.path.exists(PREFILL_JSON):
            p30 = open(PREFILL_JSON).read()
            n30, err30 = json.load(open(PREFILL_JSON + ".meta"))
        else:
            p30, n30, err30 = build_prompt(30000)
            open(PREFILL_JSON, "w").write(p30)
            json.dump([n30, err30], open(PREFILL_JSON + ".meta", "w"))
        tpl30 = templated(p30)
        r = completion(tpl30, 400, sampler=True)
        r["tokens_calibrated"] = n30
        r["calib_err"] = err30
        out["decode_30k"] = r
    except Exception as e:
        out["decode_30k"] = {"error": repr(e)[:300]}
    # --- C. greedy answer equivalence (chat, temp 0, seed 4242) ---
    ans = {}
    for key, prompt in ANSWERS:
        try:
            r = chat(prompt, 500)
            ans[key] = {"content": r["content"], "predicted_n": r["predicted_n"],
                        "decode_tps": r["decode_tps"], "prefill_tps": r["prefill_tps"],
                        "finish_reason": r["finish_reason"],
                        "cached_tokens": r["cached_tokens"]}
        except Exception as e:
            ans[key] = {"error": repr(e)[:300]}
    out["answers"] = ans
    out["vram_peak_overall_gib"] = round((vram() or 0) / 2**30, 2)
    js = journal_tail(3000)
    acc = re.findall(r"draft acceptance = ([0-9.]+) ", js)
    out["spec_acceptance_samples"] = acc[-20:]
    out["journal_spec_lines"] = [l.split("]: ")[-1] for l in js.splitlines()
                                  if "draft acceptance" in l or "speculative" in l][-25:]
    json.dump(out, open(os.path.join(outdir, f"{arm}.json"), "w"), indent=1)
    ds = out.get("decode_short") or {}
    print("ARM_DONE", arm, json.dumps({"decode_short_tps": ds.get("decode_tps"),
                                       "decode_30k_tps": (out.get("decode_30k") or {}).get("decode_tps"),
                                       "vram_idle": out["vram_idle_gib"]}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
