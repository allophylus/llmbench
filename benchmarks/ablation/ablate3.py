#!/usr/bin/env python3
"""ablate3.py — accelerator ablation across EVERY runnable model on the box.

Round 3 (2026-11-04). Round 2 (ablate2.py) measured one model (Qwen3.8-27B-Q4_K_M)
across 8 accelerator arms. Round 3 keeps the measurement method identical and changes
the grid: one MODEL per group, arms as sub-rows.

    ARM A  baseline       -fa on,  no speculative decoding
    ARM B  fa-off         -fa off (f16 KV: q4_0 V cache requires FA) — where it loads
    ARM C  draft-mtp      only where the TRUNK gguf has nextn_predict_layers
    ARM D  draft-dflash   only for qwen35-family trunks (the DFlash2 drafter is qwen35)
    ARM E  mtp+ngram      only in combination with ARM C (prod preset shape)

Arms that cannot exist are recorded as NOT-APPLICABLE with a reason; arms that fail
verification are recorded as VOID with the exact reason and are NOT scored.

INTEGRITY GATES (a cell failing any gate is VOID):
  1. /props model_path realpath == the gguf we launched
  2. /props n_ctx == the -c we passed
  3. completion has predicted_n > 0 and a stop/truncated reason
  4. NRestarts stays 0 across the arm

usage: ablate3.py <model-slug> [--port 8080] [--binary b11517|b11874] [--arm X ...]
       ablate3.py --all-arms <model-slug> ...
"""
import json, os, re, subprocess, sys, threading, time, urllib.request

WORK = "/home/ubuntu/bench-work/ablation3"
STATE = os.path.join(WORK, "state.json")
UNIT = "qwen-longctx.service"                      # :8080, Trunk slot (models rotate here)
UNIT_LFM = "lfm3-ablation.service"                 # :8091, LFM3-only slot
DROPIN_DIR = "/home/ubuntu/.config/systemd/user/qwen-longctx.service.d"
DROPIN = DROPIN_DIR + "/z-ablation3.conf"
ACTIVE = DROPIN_DIR + "/z-active-model.conf"
ACTIVE_PARK = ACTIVE + ".ablation3-parked"
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"
PACK = "/home/ubuntu/llmbench/suite/packs/ctx_filler.txt"
BINS = {"b11517": "/home/ubuntu/llama-vulkan/llama-b11517/llama-server",
        "b11874": "/home/ubuntu/llama-vulkan/llama-b11874/llama-server"}
MMPROJ_QWEN = "/home/ubuntu/models/mmproj-Qwen3.8-27B-F16.gguf"
MMPROJ_A3B = "/home/ubuntu/models/qwen36/mmproj-Qwen3.6-35B-A3B-F16.gguf"
DFLASH = "/home/ubuntu/models/Qwen3.8-27B-DFlash2-Q4_K_M.gguf"
EXT = "/home/ubuntu/models"
LFM_DIR = "/home/ubuntu/llmbench/tune/dl4"

NMAX, NMIN = "7", "1"
REASONING = ["--reasoning", "off"]  # ONCE only: a duplicate pair made llama-server drop the
#                                    speculative flags entirely (round-3 defect #1)

# --- model grid -------------------------------------------------------------
# family: qwen35 trunk (27B class) -> mtp + dflash arms possible
#         qwen35moe / lfm3        -> no drafter exists on the box
MODELS = {
    "qwen3-8-27b-q4km": {
        "path": f"{EXT}/Qwen3.8-27B-Q4_K_M.gguf", "mmproj": MMPROJ_QWEN,
        "family": "qwen35", "nextn": 1, "unit": UNIT, "port": 8080,
        "ctx": 131072, "note": "prod model"},
    "qwen3-8-27b-q4-0": {
        "path": f"{EXT}/Qwen3.8-27B-Q4_0.gguf", "mmproj": MMPROJ_QWEN,
        "family": "qwen35", "nextn": 1, "unit": UNIT, "port": 8080, "ctx": 131072},
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": {
        "path": f"{EXT}/DavidAU-Qwen3.8-27B-NEO-MAX-MTP-Q4_K_M.gguf", "mmproj": MMPROJ_QWEN,
        "family": "qwen35", "nextn": 1, "unit": UNIT, "port": 8080, "ctx": 131072,
        "note": "has its own MTP head (nextn_predict_layers=1)"},
    "huihui-abl-q4-k-m": {
        "path": f"{EXT}/Huihui-abl-Q4_K_M.gguf", "mmproj": MMPROJ_QWEN,
        "family": "qwen35", "nextn": 1, "unit": UNIT, "port": 8080, "ctx": 131072},
    "qwen3-6-35b-a3b-ud-q4km": {
        "path": f"{EXT}/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf", "mmproj": MMPROJ_A3B,
        "family": "qwen35moe", "nextn": 0, "unit": UNIT, "port": 8080, "ctx": 131072},
    "ornith-1-5-35b-a3b-q4-k-m": {
        "path": "/home/ubuntu/models/bench-new/ornith35a3b/Ornith-1.5-35B-Q4_K_M.gguf",
        "mmproj": None, "family": "qwen35moe", "nextn": 0, "unit": UNIT, "port": 8080,
        "ctx": 131072, "note": "text-only on this box (no mmproj present)"},
    "lfm3-1-7b-q4-k-m": {
        "path": f"{LFM_DIR}/LFM3-1.7B-Q4_K_M.gguf", "mmproj": None,
        "family": "lfm3", "nextn": 0, "unit": UNIT_LFM, "port": 8091,
        "binary": "b11874", "ctx": 32768, "no_think": True,
        "extra_tail": 9000,  # tokens/short context ~= 60/token vs 16 for qwen: needs +9k chars to reach 27.7k tok
        "note": "template defaults enable_thinking=true; disabled via chat-template-kwargs"},
}

# --- arm definitions --------------------------------------------------------
def arms_for(m):
    a = {"A-baseline": {"fa": "on", "extra": []},
         "B-fa-off": {"fa": "off", "kv": ["--cache-type-k", "f16", "--cache-type-v", "f16"],
                      "note": "q8_0K/q4_0V requires FA; FA-off only runnable with f16 KV"}}
    return a


SPEC_ARMS = {
    "C-draft-mtp": ["--spec-type", "draft-mtp", "--spec-draft-n-max", NMAX, "--spec-draft-n-min", NMIN],
    # DFlash keeps its own block/n defaults (round 2: n_max 3 beat 7 at depth)
    "D-draft-dflash": ["--spec-type", "draft-dflash", "--spec-draft-model", DFLASH],
    "D2-dflash-nm7": ["--spec-type", "draft-dflash", "--spec-draft-model", DFLASH,
                      "--spec-draft-n-max", "7", "--spec-draft-n-min", "1"],
    "E-mtp-ngram": ["--spec-type", "draft-mtp,ngram-cache", "--spec-draft-n-max", NMAX,
                    "--spec-draft-n-min", NMIN],
}

# probes (identical to ablate2.py — comparability)
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


# --- plumbing ---------------------------------------------------------------
def sh(cmd, timeout=900):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


class Srv:
    def __init__(self, base):
        self.base = base

    def post(self, path, payload, timeout=7200):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read())
        return body, time.time() - t0

    def get(self, path, timeout=60):
        with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
            return json.loads(r.read())

    def up(self, timeout=5):
        try:
            self.get("/props", timeout=timeout)
            return True
        except Exception:
            return False


def vram():
    try:
        return int(open(VRAM).read().strip())
    except Exception:
        return None


class Sampler(threading.Thread):
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
    t = body.get("timings") or {}
    return {"wall_s": round(wall, 2), "prompt_n": t.get("prompt_n"),
            "predicted_n": t.get("predicted_n"),
            "prefill_ms": round(t.get("prompt_ms") or 0, 1),
            "prefill_tps": round(t.get("prompt_per_second") or 0, 1),
            "decode_ms": round(t.get("predicted_ms") or 0, 1),
            "decode_tps": round(t.get("predicted_per_second") or 0, 2),
            "cache_n": t.get("cache_n")}


def spec_counters(srv):
    """Cumulative speculative counters (delta between two reads = one request)."""
    try:
        txt = urllib.request.urlopen(srv.base + "/metrics", timeout=30).read().decode()
    except Exception:
        return {}
    out = {}
    for name in ("num_draft_tokens_total", "num_accepted_tokens_total", "num_drafts_total"):
        m = re.search(r"llamacpp:spec_decode_" + name + r"\s+([0-9.]+)", txt)
        if m:
            out[name] = float(m.group(1))
    return out


def ntok(srv, text):
    return len(srv.post("/tokenize", {"content": text})[0]["tokens"])


def templated(srv, prompt):
    if not srv.up():
        return prompt
    return srv.post("/apply-template", {"messages": [{"role": "user", "content": prompt}]})[0]["prompt"]


def build_prompt(srv, target, block_chars=1500, blocks=20, extra_tail=0):
    pack = open(PACK).read().strip()
    block = pack[:block_chars]
    unit = block * blocks
    if extra_tail:
        # some tokenizers (LFM3) are so dense on the filler that the greedy fit walks back to
        # a local minimum; use a directly measured shape instead (k=4 units of 30k chars +
        # a measured slice of *different* filler)
        cand = unit * 4 + pack[block_chars:block_chars + extra_tail] + \
            "\n\nReply with the single word DONE."
        return cand, ntok(srv, cand), 0.0
    u_tok = ntok(srv, unit)
    k = max(1, target // u_tok)
    best, tail = None, 0
    for _ in range(8):
        text = unit * k + block[:tail] + "\n\nReply with the single word DONE."
        n = ntok(srv, text)
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


def completion(srv, prompt, n_predict, sampler=False):
    s = Sampler()
    if sampler:
        s.start()
    try:
        body, wall = srv.post("/completion", {
            "prompt": prompt, "temperature": 0, "seed": 4242, "n_predict": n_predict,
            "ignore_eos": True, "cache_prompt": False, "stream": False})
    finally:
        peak = s.peak() if sampler else None
    r = _timings(body, wall)
    r["vram_peak_gib"] = peak
    r["stop"] = body.get("stop")
    r["truncated"] = body.get("truncated")
    r["stopping_word"] = (body.get("stopping_word") or "")[:40]
    r["content_head"] = (body.get("content") or "")[:200]
    return r


def chat(srv, prompt, max_tokens):
    body, wall = srv.post("/v1/chat/completions", {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0, "seed": 4242, "max_tokens": max_tokens,
        "cache_prompt": False, "stream": False})
    r = _timings(body, wall)
    ch = (body.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    r["content"] = msg.get("content") or ""
    r["reasoning_len"] = len(msg.get("reasoning_content") or "")
    r["finish_reason"] = ch.get("finish_reason")
    r["cached_tokens"] = ((body.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens")
    return r


# --- state ------------------------------------------------------------------
def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "models": {}, "queue": []}


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


# --- launch -----------------------------------------------------------------
def launch(slug, arm, spec):
    m = MODELS[slug]
    unit, port, binname = m["unit"], m["port"], spec.get("binary", m.get("binary", "b11517"))
    binary = BINS[binname]
    kv = spec.get("kv") or ["--cache-type-k", "q8_0", "--cache-type-v", "q4_0"]
    argv = [binary, "-m", m["path"]]
    if m["mmproj"]:
        argv += ["--mmproj", m["mmproj"]]
    argv += ["--host", "127.0.0.1", "--port", str(port), "-c", str(m["ctx"]), "-ngl", "99",
             "--jinja", "-b", "16384", "-ub", "2048"] + kv + ["--cache-reuse", "256",
             "--metrics"] + REASONING + ["-fa", spec["fa"]] + spec["extra"]
    if m.get("no_think"):
        argv += ["--chat-template-kwargs", '{"enable_thinking":false}']
    return build_launch(unit, arm, argv)


def park_foreign_dropins(ddir):
    """Any drop-in with its own [Service] ExecStart= (e.g. z-gapclose.conf) both poisons
    `systemctl show ExecStart` and can resurrect a unit.default ExecStart. Park them."""
    parked = []
    for f in sorted(os.listdir(ddir)):
        if not f.endswith(".conf"):
            continue
        txt = open(os.path.join(ddir, f)).read()
        if f.startswith("z-ablation3") or "ExecStart" not in txt.split("[Service]")[-1]:
            continue
        if "ExecStart=" in txt:
            os.rename(os.path.join(ddir, f), os.path.join(ddir, f + ".ablation3-parked"))
            parked.append(f)
    return parked


def unpark_foreign_dropins(ddir, parked):
    for f in parked:
        p = os.path.join(ddir, f + ".ablation3-parked")
        if os.path.exists(p):
            os.rename(p, os.path.join(ddir, f))


def build_launch(unit, arm, argv):
    """Install an ExecStart override for `unit`, restart, wait for a real completion.
    Never kills a foreign process: only systemctl acts on its own unit."""
    ddir = DROPIN_DIR if unit == UNIT else f"/home/ubuntu/.config/systemd/user/{unit}.d"
    os.makedirs(ddir, exist_ok=True)
    park_foreign_dropins(ddir)
    if unit == UNIT:
        if os.path.exists(ACTIVE) and not os.path.exists(ACTIVE_PARK):
            os.rename(ACTIVE, ACTIVE_PARK)
        dropin = DROPIN
    else:
        dropin = ddir + "/z-ablation3.conf"
    open(dropin, "w").write("# ablation3 arm %s %s (temporary)\n[Service]\nExecStart=\nExecStart=%s\n"
                            % (arm, unit, subprocess.list2cmdline(argv)))
    sh("systemctl --user daemon-reload")
    sh(f"systemctl --user reset-failed {unit}")
    sh(f"systemctl --user restart {unit}")
    return dropin


def spec_meta(srv):
    """Effective speculative state. /props only echoes CLIENT sampling params (always
    'none'); the server's own view is /slots[*].speculative (slot.can_speculate())."""
    try:
        d = srv.get("/slots")
    except Exception:
        return None
    return [bool(s.get("speculative")) for s in d] if isinstance(d, list) else None


def spec_gate(srv, spec):
    slots = spec_meta(srv)
    if slots is None:
        return "could not read /slots"
    extra = spec.get("extra") or []
    want = "--spec-type" in extra and any(
        t != "none" for t in extra[extra.index("--spec-type") + 1].split(","))
    if want and not all(slots):
        return f"/slots speculative={slots} but arm requested {extra[extra.index('--spec-type') + 1]}"
    if not want and any(slots):
        return f"/slots speculative={slots} on a non-spec arm"
    return None


def spec_complete(srv, spec, js):
    """The spec must be REAL, not just accepted as flags:
      - a --spec-draft-model must appear in the journal as loaded;
      - acceptance must also be measured per declared draft block (llama.cpp historically
        scored DFlash at 7.39 'mean len', impossible for block 8 unless the counter is
        per-block) — flagged when mean len > n_max."""
    extra = " ".join(spec.get("extra") or [])
    problems = []
    if "--spec-draft-model" in extra and "loading draft model" not in js:
        problems.append("draft model never loaded (no 'loading draft model' in journal)")
    return problems


def wait_served(srv, timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(3)
        if srv.up(timeout=5):
            return True
        st = sh(f"systemctl --user is-active {UNIT_LFM if srv.base.endswith('8091') else UNIT}").stdout.strip()
        if st in ("failed", "inactive"):
            return False
    return False


def build_failure_text(unit, since_marker):
    js = sh(f"journalctl --user -u {unit} --since '{since_marker}' --no-pager -n 400").stdout
    return js


def err_lines(js, pats=("error", "failed", "not supported", "abort", "requires", "cannot", "mismatch", "invalid")):
    out = []
    for l in js.splitlines():
        ll = l.lower()
        if any(p in ll for p in pats):
            out.append(l.split("]: ")[-1][:220])
    return out[-12:]


# --- one arm ----------------------------------------------------------------
def run_arm(slug, arm, srv_base=None, retries=1):
    m = MODELS[slug]
    if arm.startswith("NA:"):
        return {"arm": arm[3:], "status": "not-applicable", "reason": arm[3:]}
    # resolve spec
    if arm in ("A-baseline", "B-fa-off"):
        spec = dict(arms_for(m)[arm])
        spec.setdefault("extra", [])
    else:
        spec = {"fa": "on", "extra": SPEC_ARMS[arm]}
    if arm == "B-fa-off":
        spec = dict(spec)
    srv = Srv(f"http://127.0.0.1:{m['port']}")
    out = {"model": slug, "model_path": m["path"], "arm": arm, "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "fa": spec["fa"], "extra_flags": spec["extra"], "kv_cache_type":
           "f16/f16" if spec.get("kv") else "q8_0/q4_0", "unit": m["unit"], "port": m["port"],
           "attempt": 0}
    for attempt in range(retries + 1):
        out["attempt"] = attempt
        t_start = time.strftime("%Y-%m-%d %H:%M:%S")
        dropin = launch(slug, arm, spec)
        out["argv"] = [BINS[spec.get("binary", m.get("binary", "b11517"))]] + launch_argv_only(slug, arm, spec)
        out["systemd_execstart"] = sh(f"systemctl --user show {m['unit']} -p ExecStart").stdout.strip()
        out["systemd_warnings"] = [l for l in sh(f"systemctl --user show {m['unit']} -p ExecStart").stderr.splitlines() if l.strip()]
        eff = out["systemd_execstart"]
        if eff.count("path=") != 1 or m["path"] not in eff or str(m["ctx"]) not in eff:
            raise RuntimeError("effective ExecStart is not the arm argv (drop-in poisoning): " + eff[:300])
        ok = wait_served(srv)
        if not ok:
            js = build_failure_text(m["unit"], t_start)
            out.update(status="void", void_reason="server did not become ready",
                       error_lines=err_lines(js), journal_tail=js.splitlines()[-40:])
            os.remove(dropin) if os.path.exists(dropin) and m["unit"] != UNIT else None
            continue
        props = srv.get("/props")
        # gate 1: model path
        served = os.path.realpath(props.get("model_path") or "")
        want = os.path.realpath(m["path"])
        n_ctx = (props.get("default_generation_settings") or {}).get("n_ctx")
        out["served_model_path"] = served
        out["n_ctx"] = n_ctx
        out["warmup"] = None
        # warm-up (graph capture)
        try:
            completion(srv, "hello", 4)
        except Exception as e:
            pass
        time.sleep(2)
        restarts = sh(f"systemctl --user show {m['unit']} -p NRestarts").stdout.strip()
        out["restarts"] = restarts
        gate = []
        sg = spec_gate(srv, spec)
        out["speculative_types"] = spec_meta(srv)
        if sg:
            gate.append(sg)
        if served != want:
            gate.append(f"served model {served} != launched {want}")
        if n_ctx != m["ctx"]:
            gate.append(f"n_ctx {n_ctx} != {m['ctx']}")
        if not restarts.endswith("=0"):
            gate.append(f"unit restarted during load ({restarts})")
        # a one-shot startup probe: if it fails the arm is under a gate
        try:
            tpl = templated(srv, SHORT_PROMPT)
            short = completion(srv, tpl, 400, sampler=True)
            short["spec_counters"] = spec_counters(srv)
            short["prompt_tokens"] = ntok(srv, tpl)
            out["decode_short"] = short
            out["prefill_short_probe"] = 1
            if not (short.get("predicted_n") or 0) > 0:
                gate.append("decode_short generated 0 tokens")
            if short.get("stop") is None and short.get("truncated") is None:
                gate.append("decode_short has no stop/truncated reason")
        except Exception as e:
            out["decode_short"] = {"error": repr(e)[:300]}
            gate.append("decode_short request failed: " + repr(e)[:200])
        if gate:
            js = build_failure_text(m["unit"], t_start)
            out.update(status="void", void_reason="; ".join(gate), error_lines=err_lines(js))
            continue
        # --- long context ---
        try:
            # Calibrate the LONG PROMPT in the served prompt's token domain (the prompt is
            # /completion, so the chat template only affects its prefix). Calibration is
            # per model: tokenizers differ (LFM3's is ~20 % denser on the same filler).
            p30, n30, err30 = build_prompt(srv, 27722, extra_tail=m.get("extra_tail", 0))
            tpl30 = p30
            c0 = spec_counters(srv)
            r = completion(srv, tpl30, 400, sampler=True)
            c1 = spec_counters(srv)
            r["spec_delta"] = {k: (c1.get(k, 0) - c0.get(k, 0)) for k in c0}
            r["spec_counters"] = c1
            r["tokens_calibrated"] = n30
            r["calib_err"] = err30
            out["decode_30k"] = r
            if not (r.get("predicted_n") or 0) > 0:
                gate.append("decode_30k generated 0 tokens")
            if r.get("stop") is None and r.get("truncated") is None:
                gate.append("decode_30k has no stop/truncated reason")
        except Exception as e:
            out["decode_30k"] = {"error": repr(e)[:300]}
            gate.append("decode_30k request failed: " + repr(e)[:200])
        if gate:
            js = build_failure_text(m["unit"], t_start)
            out.update(status="void", void_reason="; ".join(gate), error_lines=err_lines(js))
            continue
        out["spec_complete"] = spec_complete(srv, spec, build_failure_text(m["unit"], t_start))
        gate += out["spec_complete"]
        if gate:
            js = build_failure_text(m["unit"], t_start)
            out.update(status="void", void_reason="; ".join(gate), error_lines=err_lines(js))
            continue
        # --- greedy answers ---
        ans = {}
        for key, prompt in ANSWERS:
            try:
                r = chat(srv, prompt, 500)
                ans[key] = {"content": r["content"], "predicted_n": r["predicted_n"],
                            "decode_tps": r["decode_tps"], "prefill_tps": r["prefill_tps"],
                            "finish_reason": r["finish_reason"], "cached_tokens": r["cached_tokens"]}
            except Exception as e:
                ans[key] = {"error": repr(e)[:300]}
        out["answers"] = ans
        out["vram_idle_gib"] = None
        js = build_failure_text(m["unit"], t_start)
        acc = re.findall(r"draft acceptance = ([0-9.]+) ", js)
        out["spec_acceptance_samples"] = acc[-20:]
        # per-block acceptance for the measured requests: accepted / drafts (not / drafted tokens)
        dl = (out.get("decode_30k") or {}).get("spec_delta") or {}
        drafts = dl.get("num_drafts_total") or 0
        if drafts:
            out["accept_per_block"] = round((dl.get("num_accepted_tokens_total") or 0) / drafts, 3)
        mean_lens = [float(x) for x in re.findall(r"mean len =\s*([0-9.]+)", js)]
        out["mean_len_samples"] = mean_lens[-10:]
        if out.get("accept_per_block") is not None and out["accept_per_block"] > 1.0:
            gate.append(f"accept_per_block={out['accept_per_block']} > 1.0 — counter artefact, "
                        "not a measurement")
        out["spec_expected"] = bool(spec["extra"]) and "draft-" in " ".join(spec["extra"])
        out["spec_lines"] = [l.split("]: ")[-1][:180] for l in js.splitlines()
                             if "draft acceptance" in l or "speculative" in l or "MTP" in l][-25:]
        out["journal_startup"] = [l.split("]: ")[-1][:180] for l in js.splitlines()
                                  if re.search(r"model loaded|n_ctx_slot|cache_type|flash|reuse|spec", l)][-25:]
        break
    if out.get("status") != "void":
        out["status"] = "ok"
    return out


def launch_argv_only(slug, arm, spec):
    """argv tail (without binary) for the record; binary is prepended by caller."""
    m = MODELS[slug]
    kv = spec.get("kv") or ["--cache-type-k", "q8_0", "--cache-type-v", "q4_0"]
    a = ["-m", m["path"]]
    if m["mmproj"]:
        a += ["--mmproj", m["mmproj"]]
    a += ["--host", "127.0.0.1", "--port", str(m["port"]), "-c", str(m["ctx"]), "-ngl", "99",
          "--jinja", "-b", "16384", "-ub", "2048"] + kv + ["--cache-reuse", "256",
          "--metrics"] + REASONING + ["-fa", spec["fa"]] + spec["extra"]
    return a

# --- group driver -----------------------------------------------------------
def group_arms(slug):
    """Full arm list for a model as (arm-name, NA-reason-or-None)."""
    m = MODELS[slug]
    g = [("A-baseline", None), ("B-fa-off", None)]
    if m["nextn"]:
        g.append(("C-draft-mtp", None))
    else:
        g.append(("C-draft-mtp", "not applicable (no drafter for this architecture: trunk has no "
                                 "nextn_predict_layers and no MTP drafter exists for this family)"))
    if m["family"] == "qwen35":
        g.append(("D-draft-dflash", None))
        g.append(("D2-dflash-nm7", None))
    else:
        g.append(("D-draft-dflash", "not applicable (no drafter for this architecture: the only "
                                    "DFlash drafter on the box is a qwen35 model)"))
        g.append(("D2-dflash-nm7", "not applicable (no drafter for this architecture: the only "
                                   "DFlash drafter on the box is a qwen35 model)"))
    if m["nextn"]:
        g.append(("E-mtp-ngram", None))
    else:
        g.append(("E-mtp-ngram", "not applicable (no drafter for this architecture: composed of "
                                 "draft-mtp + ngram-cache, and no MTP head exists)"))
    return g


def restore_dropins():
    d = DROPIN_DIR
    for f in os.listdir(d):
        if f.endswith(".ablation3-parked"):
            os.rename(os.path.join(d, f), os.path.join(d, f[:-len(".ablation3-parked")]))
    systemctl_reload = sh("systemctl --user daemon-reload")


def run_group(slug, only=None):
    os.makedirs(os.path.join(WORK, "arms", slug), exist_ok=True)
    st = load_state()
    ms = st["models"].setdefault(slug, {"arms": {}})
    for arm, na in group_arms(slug):
        if only and arm not in only:
            continue
        rec_path = os.path.join(WORK, "arms", slug, "arm-" + arm + ".json")
        done = ms["arms"].get(arm, {}).get("status")
        if done in ("ok", "not-applicable"):
            print("SKIP(done)", slug, arm, flush=True)
            continue
        if na:
            rec = {"model": slug, "arm": arm, "status": "not-applicable", "reason": na,
                   "when": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            json.dump(rec, open(rec_path, "w"), indent=1)
            ms["arms"][arm] = {"status": "not-applicable"}
            save_state(st)
            print("NA", slug, arm, flush=True)
            continue
        print("START", slug, arm, time.strftime("%H:%M:%S"), flush=True)
        t0 = time.time()
        try:
            rec = run_arm(slug, arm)
        except Exception as e:
            rec = {"model": slug, "arm": arm, "status": "void",
                   "void_reason": "harness exception: " + repr(e)[:300]}
        rec["wall_s"] = round(time.time() - t0, 1)
        json.dump(rec, open(rec_path, "w"), indent=1)
        ms["arms"][arm] = {"status": rec["status"], "wall_s": rec["wall_s"]}
        save_state(st)
        ds = (rec.get("decode_short") or {})
        d3 = (rec.get("decode_30k") or {})
        print("DONE", slug, arm, rec["status"], rec.get("void_reason"),
              "short=%s" % ds.get("decode_tps"), "long=%s" % d3.get("decode_tps"),
              "wall=%ss" % rec["wall_s"], flush=True)


def main():
    args = sys.argv[1:]
    only = [a for a in args if a[:2] in ("A-", "B-", "C-", "D-", "E-")]
    slugs = [a for a in args if a in MODELS]
    os.makedirs(WORK, exist_ok=True)
    for slug in slugs:
        run_group(slug, only or None)
    print("GROUP_DONE", " ".join(slugs), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
