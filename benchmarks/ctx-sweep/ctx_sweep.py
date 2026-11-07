#!/usr/bin/env python3
"""ctx_sweep.py — MATCHED context sweep for llmbench on the R9700 Vulkan host.

For every model x rung in {4096, 32768, 65536, 131072, 262144}:
  1. lock the prod unit, free :8080/:8091, start llama-server with -c <ctx>
  2. wait for /health, kill any orphaned llama-server
  3. calibrate ONE prompt with /tokenize to (ctx - 512) tokens
  4. send ONE cold /v1/chat/completions (temp 0, cache_prompt false, no stream),
     max_tokens 64, asking for a continuation long enough to time decode
  5. record server ctx, prompt tokens, prefill t/s + s, decode t/s + n,
     finish_reason, peak VRAM, exact server argv
  6. failures are recorded, never substituted

State is checkpointed to state.json after every cell.

usage:
  ctx_sweep.py --models a,b [--rungs 4096,32768]   # run (resumable)
  ctx_sweep.py --report                            # rebuild sweep.json + RESULTS.md
"""
import json, os, re, shlex, subprocess, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
SWEEP = os.path.join(HERE, "sweep.json")
RESULTS = os.path.join(HERE, "RESULTS.md")

SSH_HOST = os.environ.get("SSH_HOST", "ubuntu@192.168.1.148")
BASE = "http://127.0.0.1"
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"
PACK = "/home/ubuntu/llmbench/suite/packs/ctx_filler.txt"
SLOTFILE = os.path.join(HERE, "slot.state")

B11517 = "/home/ubuntu/llama-vulkan/llama-b11517/llama-server"
B11874 = "/home/ubuntu/llama-vulkan/llama-b11874/llama-server"
B12110 = "/home/ubuntu/llama-vulkan/llama-b12110/llama-server"   # llama.cpp v0.9.0
M = "/home/ubuntu/models"
LOCK = "~/.config/systemd/user/qwen-longctx.service.d/zz-ctxsweep-lock.conf"

STD = ["-ngl", "99", "-fa", "on", "-b", "16384", "-ub", "2048",
       "-ctk", "q8_0", "-ctv", "q4_0", "--cache-reuse", "256", "--metrics"]

GEN_TOKENS = 64
HEADROOM = 512
MIN_GEN_OK = 32                     # fewer generated tokens => decode t/s is noise
REQ_TIMEOUT_S = int(os.environ.get("REQ_TIMEOUT_S", "5400"))

# The chat models here end a turn after ~2 tokens ("stop"); decode t/s over 2 tokens is
# meaningless. The probe therefore asks for a fixed, long artifact and disables EOS so
# exactly GEN_TOKENS tokens are generated, identically on every model and rung.
PROBE = ("\n\nIgnore all of the text above this line. Write out the multiplication "
         "table from 1x1 to 12x12, one row per line, in the form 1x1=1.")
GEN_KWARGS = {"temperature": 0, "top_k": 1, "top_p": 1.0, "repeat_penalty": 1.0,
              "cache_prompt": False, "stream": False, "ignore_eos": True}

MODELS = {
    "qwen3-6-35b-a3b-ud-q4km": dict(
        name="Qwen3.6-35B-A3B", quant="Q4_K_M",
        file=f"{M}/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
        mmproj=f"{M}/qwen36/mmproj-Qwen3.6-35B-A3B-F16.gguf",
        bin=B11517, port=8080, extra=["--jinja"], native_ctx=262144),
    "qwen3-8-27b-q4km": dict(
        name="Qwen3.8-27B", quant="Q4_K_M",
        file=f"{M}/Qwen3.8-27B-Q4_K_M.gguf", mmproj=f"{M}/mmproj-Qwen3.8-27B-F16.gguf",
        bin=B11517, port=8080, extra=["--jinja", "--reasoning", "off"],
        native_ctx=131072),
    "qwen3-8-27b-q4-0": dict(
        name="Qwen3.8-27B", quant="Q4_0",
        file=f"{M}/Qwen3.8-27B-Q4_0.gguf", mmproj=f"{M}/mmproj-Qwen3.8-27B-F16.gguf",
        bin=B11517, port=8080, extra=["--jinja", "--reasoning", "off"],
        native_ctx=131072),
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": dict(
        name="DavidAU Qwen3.8-27B NEO-MAX MTP", quant="Q4_K_M",
        file=f"{M}/DavidAU-Qwen3.8-27B-NEO-MAX-MTP-Q4_K_M.gguf",
        mmproj=f"{M}/mmproj-Qwen3.8-27B-F16.gguf",
        bin=B11517, port=8080, extra=["--jinja", "--reasoning", "off"],
        native_ctx=131072),
    "huihui-abl-q4-k-m": dict(
        name="Huihui abliterated 27B", quant="Q4_K_M",
        file=f"{M}/Huihui-abl-Q4_K_M.gguf", mmproj=f"{M}/mmproj-Qwen3.8-27B-F16.gguf",
        bin=B11517, port=8080, extra=["--jinja", "--reasoning", "off"],
        native_ctx=131072),
    "ornith-1-5-35b-a3b-q4-k-m": dict(
        name="Ornith-1.5-35B-A3B", quant="Q4_K_M",
        file=f"{M}/bench-new/ornith35a3b/Ornith-1.5-35B-Q4_K_M.gguf", mmproj="",
        bin=B11517, port=8080, extra=["--jinja", "--reasoning", "off"],
        native_ctx=131072),
    "lfm3-1-7b-q4-k-m": dict(
        name="LFM3-1.7B", quant="Q4_K_M",
        file="/home/ubuntu/llmbench/tune/dl4/LFM3-1.7B-Q4_K_M.gguf", mmproj="",
        bin=B11874, port=8091, extra=["--jinja", "-np", "1"], native_ctx=32768),
    # v0.9.0-only architectures (gemma4 / nanbeige landed after b11517)
    "gemma-4-26b-a4b-ud-q4-k-m": dict(
        name="Gemma 4 26B-A4B", quant="UD-Q4_K_M",
        file=f"{M}/qwen38fn/gemma4/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf", mmproj="",
        bin=B12110, port=8080, extra=["--jinja"], native_ctx=262144),   # GGUF context_length
    "nanbeige-4-3-33b-q4-k": dict(
        name="Nanbeige 4.3-33B", quant="Q4_K",
        file=f"{M}/qwen38fn/nanbeige/Nanbeige4.3-33B-Q4_K.gguf", mmproj="",
        bin=B12110, port=8080, extra=["--jinja"], native_ctx=524288),   # GGUF context_length,
}
RUNGS = [4096, 32768, 65536, 131072, 262144]

LOCAL = os.path.exists("/home/ubuntu/models")


# ------------------------------------------------------------------ plumbing
def sh(cmd, timeout=180):
    if LOCAL:
        return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                              timeout=timeout)
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                           SSH_HOST, cmd], capture_output=True, text=True,
                          timeout=timeout)


def slot(state, detail=""):
    try:
        with open(SLOTFILE + ".tmp", "w") as f:
            f.write(f"{state} {time.strftime('%H:%M:%S')} {detail}\n")
        os.replace(SLOTFILE + ".tmp", SLOTFILE)
    except Exception:
        pass


def vram():
    try:
        return int(open(VRAM).read().strip())
    except Exception:
        return None


def http(path, payload=None, timeout=REQ_TIMEOUT_S, port=8080):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{BASE}:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()), time.time() - t0


def port_pid(port):
    out = sh(f"ss -ltnp 'sport = :{port}' 2>/dev/null | grep -o 'pid=[0-9]*' | head -1").stdout
    m = re.search(r"pid=(\d+)", out or "")
    return int(m.group(1)) if m else None


def port_busy(port):
    return port_pid(port) is not None


def kill_port(port, timeout=45):
    pid = port_pid(port)
    if not pid:
        return
    sh(f"kill {pid} 2>/dev/null || true")       # never pkill -f (self-match kills ssh)
    t0 = time.time()
    while port_busy(port) and time.time() - t0 < timeout:
        time.sleep(1)
    if port_busy(port):
        sh(f"kill -9 {pid} 2>/dev/null || true")
        t0 = time.time()
        while port_busy(port) and time.time() - t0 < 15:
            time.sleep(1)
    time.sleep(2)


def reclaim(keep_pid=None):
    """Kill every llama-server except ours: orphans that lost their listener keep VRAM."""
    out = sh("ps -eo pid=,cmd= | grep '[l]lama-vulkan/.*llama-server --\\|"
             "[l]lama-vulkan/.*llama-server -m' | awk '{print $1}'").stdout or ""
    killed = []
    for tok in out.split():
        pid = int(tok)
        if pid == keep_pid:
            continue
        sh(f"kill -9 {pid} 2>/dev/null || true")
        killed.append(pid)
    return killed


def start_server(slug, ctx):
    cfg = MODELS[slug]
    argv = [cfg["bin"], "-m", cfg["file"], "--host", "0.0.0.0",
            "--port", str(cfg["port"]), "-c", str(ctx)] + STD + cfg["extra"]
    if cfg["mmproj"]:
        argv += ["--mmproj", cfg["mmproj"]]
    log = f"/home/ubuntu/ctx-sweep/{slug}-{ctx}.log"
    sh("mkdir -p /home/ubuntu/ctx-sweep")
    r = sh("nohup " + " ".join(shlex.quote(a) for a in argv) +
           f" > {log} 2>&1 & echo STARTED $!")
    m = re.search(r"STARTED (\d+)", (r.stdout or "") + (r.stderr or ""))
    return argv, log, (int(m.group(1)) if m else None)


FATAL = re.compile(
    r"error while handling argument|failed to load model|failed to allocate|"
    r"out of memory|error loading model|exiting due to model loading error|"
    r"unsupported model architecture|unknown model architecture|"
    r"failed to create context|VK_ERROR_OUT_OF_DEVICE_MEMORY|alloc_tensor_range.*failed|"
    r"couldn't bind HTTP server socket|exiting due to HTTP server error|"
    r"failed to initialize", re.I)


def wait_ready(port, log, pid=None, max_wait=420):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        tail = sh(f"tail -c 3000 {log} 2>/dev/null").stdout or ""
        if FATAL.search(tail):
            return False, tail
        if pid:
            alive = sh(f"ps -o stat= -p {pid} 2>/dev/null").stdout.strip()
            if not alive or alive.upper().startswith("Z"):
                return False, tail
        try:
            b, _ = http("/health", port=port, timeout=5)
            if b.get("status") == "ok" and (pid is None or port_pid(port) == pid):
                return True, tail
        except Exception:
            pass
        time.sleep(4)
    return False, (sh(f"tail -c 3000 {log}").stdout or "")


class Calibrator:
    def __init__(self, port):
        self.port = port

    def ntok(self, text):
        b, _ = http("/tokenize", {"content": text}, port=self.port)
        return len(b["tokens"])

    def build(self, target):
        full = sh(f"head -c 60000 {PACK}").stdout
        cpt = 6000 / max(1, self.ntok(full[:6000]))
        unit_chars = max(1000, min(30000, int(2000 * cpt)))
        unit = full[:unit_chars]
        u_tok = self.ntok(unit)
        k = max(1, target // u_tok)
        tail = max(0, min(len(unit) - 1, int((target - k * u_tok) * cpt * 0.97)))
        best = None
        for _ in range(20):
            tail = max(0, min(len(unit) - 1, tail))
            text = unit * k + unit[:tail] + PROBE
            n = self.ntok(text)
            err = abs(n - target) / target
            if best is None or err < best[0]:
                best = (err, text, n, k, tail)
            if err <= 0.005:
                break
            delta = target - n
            if delta > u_tok // 2:
                k += max(1, int(delta / u_tok))
                tail = 0
            elif tail == 0 and delta > 0:
                tail = max(1, min(len(unit) - 1, int(delta * cpt)))
            else:
                tail += max(1, int(abs(delta) * cpt * 0.95)) * (1 if delta > 0 else -1)
        return best[1], best[2], {"units": best[3], "tail_chars": best[4],
                                  "unit_tokens": u_tok, "unit_chars": unit_chars,
                                  "chars_per_token": round(cpt, 3),
                                  "err": round(best[0], 5),
                                  "fit": "ok" if best[0] <= 0.005 else "best_effort"}


def harvest_from_log(log, want_tokens=None):
    txt = sh(f"tail -c 300000 {log} 2>/dev/null").stdout or ""
    tasks, cur = {}, None
    for line in txt.splitlines():
        m = re.search(r"task (\d+) \|.*prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens"
                      r" \([^)]*,\s*([\d.]+) tokens per second", line)
        if m:
            cur = int(m.group(1))
            tasks[cur] = {"prefill_ms": float(m.group(2)), "prompt_n": int(m.group(3)),
                          "prefill_tps": round(float(m.group(4)), 1)}
            continue
        m = re.search(r"task (\d+) \|\s+eval time =\s*([\d.]+) ms /\s*(\d+) tokens"
                      r" \([^)]*,\s*([\d.]+) tokens per second", line)
        if m and int(m.group(1)) in tasks:
            tasks[int(m.group(1))].update(
                {"decode_ms": float(m.group(2)), "predicted_n": int(m.group(3)),
                 "decode_tps": round(float(m.group(4)), 2)})
    done = {t: v for t, v in tasks.items() if "decode_tps" in v}
    if not done:
        return {}
    pick = None
    if want_tokens:
        for t, v in done.items():
            if abs(v["prompt_n"] - want_tokens) / max(1, want_tokens) < 0.01:
                pick = t
    if pick is None:
        good = [t for t, v in done.items() if v["predicted_n"] >= MIN_GEN_OK]
        pick = (good or list(done))[-1]
    v = dict(done[pick])
    v["prefill_s"] = round(v["prefill_ms"] / 1000, 1)
    v["task_id"] = pick
    v["harvested"] = True
    return v


# ------------------------------------------------------------------ one cell
def run_cell(slug, ctx):
    cfg = MODELS[slug]
    port = cfg["port"]
    cell = {"model": slug, "server_ctx": ctx,
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    t0 = time.time()

    sh(f"mkdir -p ~/.config/systemd/user/qwen-longctx.service.d && touch {LOCK} && "
       "systemctl --user daemon-reload && systemctl --user stop qwen-longctx 2>/dev/null; "
       "systemctl --user reset-failed qwen-longctx 2>/dev/null || true")
    for p in {8080, 8091} - {port}:
        kill_port(p, timeout=20)
    kill_port(port)
    w = time.time()
    while port_busy(port) and time.time() - w < 30:
        time.sleep(1)
    cell["vram_baseline_gib"] = round(vram() / 2**30, 2) if vram() else None

    argv, log, pid = start_server(slug, ctx)
    cell["server_argv_str"] = " ".join(shlex.quote(a) for a in argv)
    cell["log"] = log
    if pid is None:
        cell["status"] = "start_failed"
        cell["error"] = "no pid returned by launcher"
        return cell
    orphan = reclaim(keep_pid=pid)
    if orphan:
        cell["killed_orphan_pids"] = orphan
    ok, tail = wait_ready(port, log, pid=pid)
    cell["load_s"] = round(time.time() - t0, 1)
    if not ok:
        cell["status"] = "does_not_fit"
        cell["error"] = (tail or "")[-1200:]
        return cell

    m = re.search(r"-c (\d+)", (sh(f"tr '\\0' ' ' < /proc/{pid}/cmdline").stdout or ""))
    cell["ctx_arg_matches"] = bool(m) and int(m.group(1)) == ctx
    try:
        props, _ = http("/props", port=port, timeout=60)
        cell["n_ctx_server"] = (props.get("default_generation_settings") or {}).get("n_ctx")
        cell["total_slots"] = props.get("total_slots")
    except Exception:
        pass
    cell["vram_after_load_gib"] = round(vram() / 2**30, 2) if vram() else None

    target = ctx - HEADROOM
    cal = Calibrator(port)
    samples, stop = [], threading.Event()

    def sampler():
        while not stop.is_set():
            v = vram()
            if v is not None:
                samples.append(v)
            stop.wait(1.0)

    threading.Thread(target=sampler, daemon=True).start()
    try:
        prompt, n, cinfo = cal.build(target)
        cell["target_tokens"] = target
        cell["prompt_tokens_client"] = n
        cell["calibration"] = cinfo
        body, wall = http("/v1/chat/completions", dict(
            messages=[{"role": "user", "content": prompt}], max_tokens=GEN_TOKENS,
            **GEN_KWARGS), port=port)
        tim = body.get("timings") or {}
        ch = (body.get("choices") or [{}])[0]
        cell.update({
            "status": "ok", "wall_s": round(wall, 1),
            "prompt_n": tim.get("prompt_n"), "predicted_n": tim.get("predicted_n"),
            "prefill_ms": tim.get("prompt_ms"),
            "prefill_s": round((tim.get("prompt_ms") or 0) / 1000, 1),
            "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
            "decode_ms": tim.get("predicted_ms"),
            "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
            "finish_reason": ch.get("finish_reason"),
            "content_head": ((ch.get("message") or {}).get("content") or "")[:60]})
    except Exception as e:
        rec = harvest_from_log(log, cell.get("prompt_tokens_client"))
        cell.update(rec)
        cell["status"] = "ok_from_server_log" if rec.get("prefill_tps") else "request_failed"
        cell["error"] = repr(e)[:400]
    stop.set()
    time.sleep(1.1)
    cell["vram_peak_gib"] = round(max(samples) / 2**30, 2) if samples else None
    a, p_ = cell.get("vram_after_load_gib"), cell.get("vram_peak_gib")
    if a and p_ and p_ < a - 0.05:
        cell["vram_peak_gib"] = a
        cell["vram_peak_source"] = "after_load (sampler caught pre-release reading)"
    cell["cell_wall_s"] = round(time.time() - t0, 1)
    return cell


def measured(c):
    return bool(c) and c.get("prefill_tps") is not None and c.get("decode_tps") is not None


def cell_key(slug, ctx):
    return f"{slug}|{ctx}"


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"campaign": "llmbench ctx-sweep",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cells": {}}


def save_state(st):
    st["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def write_model_json(slug, st):
    rows = {str(c): st["cells"][cell_key(slug, c)] for c in RUNGS
            if cell_key(slug, c) in st["cells"]}
    json.dump({"model": slug, "name": MODELS[slug]["name"], "quant": MODELS[slug]["quant"],
               "file": MODELS[slug]["file"], "server_bin": MODELS[slug]["bin"],
               "port": MODELS[slug]["port"],
               "flags": STD + MODELS[slug]["extra"], "gen_tokens": GEN_TOKENS,
               "headroom": HEADROOM, "probe": PROBE.strip(),
               "method": "server restarted per cell with -c <ctx>; one cold "
                         "/v1/chat/completions (temp 0, cache_prompt false, no stream, "
                         "ignore_eos, max_tokens 64); prompt calibrated via /tokenize "
                         "to ctx-512 so server ctx == client prompt length",
               "cells": rows},
              open(os.path.join(HERE, f"{slug}.json"), "w"), indent=1)


# ------------------------------------------------------------------ report
def fmt_cell(c):
    if c is None:
        return "—"
    if measured(c):
        mark = "" if c.get("status") == "ok" else "*"
        return f"{c.get('prefill_tps')} / {c.get('decode_tps')}{mark}"
    return "does not fit" if c.get("status") == "does_not_fit" else (c.get("status") or "failed")


def write_results(models):
    L = ["# Matched-context sweep — R9700 32 GiB, llama.cpp Vulkan", "",
         f"Generated: {time.strftime('%Y-%m-%d %H:%M %z')}", "",
         "## What this fixes", "",
         "In the existing speed rows, \"context\" sometimes meant the *server* `-c` flag and",
         "sometimes the *client prompt* length (a ~30 K-token prompt was sent to a server",
         "started at 256 K). Here the server context and the client prompt length **match on",
         "every cell**: the server is restarted with `-c <ctx>` and the single cold request's",
         "prompt is calibrated with `/tokenize` to `ctx - 512` tokens.", "",
         "## Method", "",
         "* Per cell: lock the prod unit → free :8080/:8091 → start `llama-server -c <ctx>`"]
    L += ["  with the standard flags `" + " ".join(STD) + "`"]
    L += ["  (+ `--jinja` / `--reasoning off` where the model needs it) → wait for `/health`",
          "  → calibrate one prompt → ONE cold request.",
          "* Request: `/v1/chat/completions`, `temperature 0`, `top_k 1`, `cache_prompt false`,",
          "  `stream false`, `ignore_eos true`, `max_tokens 64`. The reply is a fixed",
          "  continuation request (multiplication table) because these models otherwise end the",
          "  turn after ~2 tokens, which cannot measure decode rate.",
          "* Metrics: server `timings.prompt_per_second` (prefill), `prompt_ms`,",
          "  `predicted_per_second` (decode), `predicted_n`, `finish_reason`.",
          "* VRAM: `mem_info_vram_used` sampled at 1 Hz; peak = max over the cell.",
          "* Failures are recorded, never substituted.", "",
          "## Results (prefill t/s / decode t/s per rung)", "",
          "| model | 4K | 32K | 64K | 128K | 256K | largest ctx that loaded | notes |",
          "|---|---|---|---|---|---|---|---|"]
    for slug, cells in models.items():
        row = [f"{MODELS[slug]['name']} ({MODELS[slug]['quant']})"]
        loaded = []
        for c in RUNGS:
            cc = cells.get(str(c))
            row.append(fmt_cell(cc))
            if measured(cc):
                loaded.append(c)
        row.append(f"{max(loaded)//1024}K" if loaded else "none")
        notes = []
        nf = [f"{c//1024}K" for c in RUNGS
              if (cells.get(str(c)) or {}).get("status") == "does_not_fit"]
        if nf:
            notes.append("no fit: " + ", ".join(nf))
        bad = [f"{c//1024}K" for c in RUNGS
               if (cells.get(str(c)) or {}).get("status") == "request_failed"]
        if bad:
            notes.append("request failed: " + ", ".join(bad))
        slow = [f"{c//1024}K" for c in RUNGS
                if (cells.get(str(c)) or {}).get("status") == "ok_from_server_log"]
        if slow:
            notes.append("from server log (client timeout): " + ", ".join(slow))
        row.append("; ".join(notes))
        L.append("| " + " | ".join(row) + " |")
    L += ["", "## Per-cell detail", "",
          "| model | rung | prompt tok | prefill t/s | prefill s | decode t/s | gen tok "
          "| finish | peak VRAM GiB |", "|---|---|---|---|---|---|---|---|---|"]
    for slug, cells in models.items():
        for c in RUNGS:
            cc = cells.get(str(c))
            if not cc:
                continue
            if not measured(cc):
                L.append(f"| {slug} | {c} | — | — | — | — | — | {cc.get('status')} | — |")
                continue
            L.append(f"| {slug} | {c} | {cc.get('prompt_n')} | {cc.get('prefill_tps')} | "
                     f"{cc.get('prefill_s')} | {cc.get('decode_tps')} | "
                     f"{cc.get('predicted_n')} | {cc.get('finish_reason')} | "
                     f"{cc.get('vram_peak_gib')} |")
    L += ["", "## Failures", ""]
    any_f = False
    for slug, cells in models.items():
        for c in RUNGS:
            cc = cells.get(str(c))
            if cc and not measured(cc):
                any_f = True
                L += [f"### {slug} @ {c} — {cc.get('status')}", "", "```",
                      (cc.get("error") or "")[-800:], "```", ""]
    if not any_f:
        L.append("None — every cell measured.")
    L += ["", "## Artifacts", "",
          "* `sweep.json` — full machine-readable sweep",
          "* `<slug>.json` — one file per model",
          "* `state.json` — resumable state (checkpointed per cell)", ""]
    open(RESULTS, "w").write("\n".join(L) + "\n")


def report():
    st = load_state()
    models, sweep = {}, {}
    for slug in MODELS:
        if any(cell_key(slug, c) in st["cells"] for c in RUNGS):
            write_model_json(slug, st)
            models[slug] = json.load(open(os.path.join(HERE, f"{slug}.json")))["cells"]
            sweep[slug] = models[slug]
    json.dump({"campaign": "llmbench ctx-sweep", "rungs": RUNGS,
               "models": {s: MODELS[s]["name"] for s in MODELS},
               "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "data": sweep}, open(SWEEP, "w"), indent=1)
    write_results(models)
    print(f"wrote {SWEEP} and {RESULTS}")
    return 0


# ------------------------------------------------------------------ main
def main():
    if not LOCAL:
        sys.stderr.write("REFUSING: run this ON the GPU host (needs the prompt pack "
                         "and the VRAM counter).\n")
        return 2
    args = sys.argv[1:]
    if "--report" in args:
        return report()
    slugs = list(MODELS)
    if "--models" in args:
        slugs = args[args.index("--models") + 1].split(",")
    rungs = RUNGS
    if "--rungs" in args:
        rungs = [int(x) for x in args[args.index("--rungs") + 1].split(",")]
    st = load_state()
    for slug in slugs:
        for ctx in rungs:
            k = cell_key(slug, ctx)
            prev = st["cells"].get(k)
            if prev and measured(prev) and (prev.get("predicted_n") or 0) >= MIN_GEN_OK:
                print(f"SKIP {k} (done)", flush=True)
                continue
            slot("BUSY", k)
            print(f"RUN  {k} @ {time.strftime('%H:%M:%S')}", flush=True)
            t0 = time.time()
            cell = run_cell(slug, ctx)
            st["cells"][k] = cell
            save_state(st)
            slot("IDLE", f"after {k}")
            print(f"DONE {k} status={cell.get('status')} "
                  f"prefill={cell.get('prefill_tps')} decode={cell.get('decode_tps')} "
                  f"gen={cell.get('predicted_n')} vram={cell.get('vram_peak_gib')} "
                  f"took={round(time.time()-t0)}s", flush=True)
            write_model_json(slug, st)
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
