#!/usr/bin/env python3
"""sweep3090.py — matched context sweep for Qwen3.8-27B (ByteShape IQ4_XS) on the
RTX 3090 / Windows CUDA box.

Same method as benchmarks/ctx-sweep/ctx_sweep.py (the R9700 Vulkan sweep): per rung the
server is started with `-c <ctx>`, one prompt is calibrated with /tokenize to `ctx - 512`,
and ONE cold request (temp 0, cache_prompt false, no stream, ignore_eos, max_tokens 64) is
sent. Nothing is substituted: a rung that does not fit is recorded with the server's own
error text.

The server lives on Windows (WSL2 ssh reachable at MSI_HOST). The HTTP endpoint is reached
through an ssh -L tunnel on the gateway (see --port / --base).

usage:
  sweep3090.py --rungs 4096,32768           # run (resumable via state.json)
  sweep3090.py --report                     # rebuild sweep3090.json + RESULTS.md
"""
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
SWEEP = os.path.join(HERE, "sweep3090.json")
RESULTS = os.path.join(HERE, "RESULTS.md")
PACK = os.path.join(HERE, "packs", "ctx_filler.txt")

MSI = os.environ.get("MSI_HOST", "fen@192.168.1.117")
PORT = int(os.environ.get("PORT", "8189"))
BASE = os.environ.get("BASE", f"http://127.0.0.1:{PORT}")

WIN_BIN = r"C:\llama3090\llama-server.exe"
WIN_MODEL = r"C:\llama3090\models\Qwen3.8-27B-IQ4_XS-3.84bpw.gguf"
WIN_MMPROJ = r"C:\llama3090\models\mmproj-bf16.gguf"
LOG_DIR_WIN = r"C:\llama3090\logs"

STD = ["-ngl", "99", "-fa", "on", "-b", "16384", "-ub", "2048",
       "-ctk", "q8_0", "-ctv", "q4_0", "--cache-reuse", "256", "--metrics",
       "--jinja", "-np", "1"]
# reasoning is 'off' for the serving/sweep standard; the thinking pair starts the server
# in 'auto' so the per-request enable_thinking kwarg decides.
REASONING = (["--reasoning", "off"] if os.environ.get("REASONING", "off") == "off"
             else [])
SPEC = ["--spec-type", "draft-mtp", "--spec-draft-n-max", "3"]

GEN_TOKENS = 64
HEADROOM = 512
MIN_GEN_OK = 32
REQ_TIMEOUT_S = int(os.environ.get("REQ_TIMEOUT_S", "5400"))

PROBE = ("\n\nIgnore all of the text above this line. Write out the multiplication "
         "table from 1x1 to 12x12, one row per line, in the form 1x1=1.")
GEN_KWARGS = {"temperature": 0, "top_k": 1, "top_p": 1.0, "repeat_penalty": 1.0,
              "cache_prompt": False, "stream": False, "ignore_eos": True}

RUNGS = [4096, 32768, 65536, 131072, 262144]
USE_MMPROJ = os.environ.get("USE_MMPROJ", "1") == "1"
USE_SPEC = os.environ.get("USE_SPEC", "1") == "1"


# ------------------------------------------------------------------ plumbing
def sh(cmd, timeout=240):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", MSI, cmd],
                          capture_output=True, text=True, timeout=timeout)


def vram_gib():
    r = sh("/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    try:
        return round(int(r.stdout.strip().splitlines()[0]) / 1024, 2)
    except Exception:
        return None


def http(path, payload=None, timeout=REQ_TIMEOUT_S):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def stop_server():
    sh(r'/mnt/c/Windows/System32/cmd.exe /c "taskkill /F /IM llama-server.exe" 2>/dev/null; true')
    t0 = time.time()
    while time.time() - t0 < 40:
        try:
            http("/health", timeout=3)
        except Exception:
            return True
        time.sleep(2)
    return False


def start_server(ctx):
    argv = [WIN_BIN, "-m", WIN_MODEL, "--host", "0.0.0.0", "--port", str(PORT),
            "-c", str(ctx)] + STD + REASONING
    if USE_MMPROJ:
        argv += ["--mmproj", WIN_MMPROJ]
    if USE_SPEC:
        argv += SPEC
    log = f"{LOG_DIR_WIN}\\server-{ctx}.log"
    bat = f"{LOG_DIR_WIN}\\run-{ctx}.bat"
    lines = ["@echo off",
             f'cd /d C:\\llama3090',
             " ".join([WIN_BIN, "-m", f'"{WIN_MODEL}"', "--host", "0.0.0.0",
                       "--port", str(PORT), "-c", str(ctx)]
                      + ([f"--mmproj", f'"{WIN_MMPROJ}"'] if USE_MMPROJ else [])
                      + STD + REASONING + (SPEC if USE_SPEC else []))
             + f" > {log} 2>&1"]
    body = "\r\n".join(lines) + "\r\n"
    sh("mkdir -p /mnt/c/llama3090/logs && cat > /mnt/c/llama3090/logs/run-%d.bat <<'EOF'\n%sEOF"
       % (ctx, body))
    # `cmd /c start "" /min <bat>` is silently a no-op through WSL interop on this box
    # (verified 2026-11-07: bat never executed, no log, no process). PowerShell
    # Start-Process on the same .bat detaches correctly and the bat owns its own redirect.
    sh('/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile '
       '-Command "Start-Process -FilePath %s -WindowStyle Minimized"' % bat)
    return argv, log


FATAL = re.compile(
    r"error while handling argument|failed to load model|failed to allocate|"
    r"out of memory|error loading model|exiting due to model loading error|"
    r"unsupported model architecture|unknown model architecture|"
    r"failed to create context|CUDA error|alloc_tensor_range.*failed|"
    r"couldn't bind HTTP server socket|exiting due to HTTP server error|"
    r"failed to initialize|not enough memory|invalid value", re.I)


def tail_log(log, n=4000):
    win = log.replace("\\", "/").replace("C:/", "/mnt/c/")
    return sh(f"tail -c {n} '{win}' 2>/dev/null").stdout or ""


def wait_ready(ctx, log, max_wait=900):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        t = tail_log(log)
        if FATAL.search(t):
            return False, t
        try:
            b = http("/health", timeout=5)
            if b.get("status") == "ok":
                return True, t
        except Exception:
            pass
        time.sleep(4)
    return False, tail_log(log)


class Calibrator:
    def __init__(self):
        self.src = open(PACK, encoding="utf8").read()

    def ntok(self, text):
        return len(http("/tokenize", {"content": text})["tokens"])

    def build(self, target):
        full = self.src[:60000]
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
    txt = tail_log(log, 400000)
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
        good = [t for t in done if done[t]["predicted_n"] >= MIN_GEN_OK]
        pick = (good or list(done))[-1]
    v = dict(done[pick])
    v["prefill_s"] = round(v["prefill_ms"] / 1000, 1)
    v["task_id"] = pick
    v["harvested"] = True
    return v


# ------------------------------------------------------------------ one cell
SAMPLER = "/tmp/vram3090.sh"


def run_cell(ctx):
    cell = {"server_ctx": ctx, "when": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    t0 = time.time()
    stop_server()
    alive = sh("pgrep -af llama-server || true").stdout.strip()
    if alive:
        cell["wsl_llama_left"] = alive
    cell["vram_baseline_gib"] = vram_gib()

    argv, log = start_server(ctx)
    cell["server_argv_str"] = " ".join(argv)
    cell["log_win"] = log
    ok, tail = wait_ready(ctx, log)
    cell["load_s"] = round(time.time() - t0, 1)
    if not ok:
        cell["status"] = "does_not_fit"
        cell["error"] = (tail or "")[-1500:]
        stop_server()
        return cell

    try:
        props = http("/props", timeout=60)
        cell["n_ctx_server"] = (props.get("default_generation_settings") or {}).get("n_ctx")
        cell["build_info"] = props.get("build_info")
        cell["total_slots"] = props.get("total_slots")
    except Exception as e:
        cell["props_error"] = repr(e)[:200]
    cell["vram_after_load_gib"] = vram_gib()

    samples = []
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            v = vram_gib()
            if v is not None:
                samples.append(v)
            stop.wait(1.0)

    threading.Thread(target=sampler, daemon=True).start()
    try:
        cal = Calibrator()
        prompt, n, cinfo = cal.build(ctx - HEADROOM)
        cell["target_tokens"] = ctx - HEADROOM
        cell["prompt_tokens_client"] = n
        cell["calibration"] = cinfo
        t1 = time.time()
        body = http("/v1/chat/completions", dict(
            messages=[{"role": "user", "content": prompt}], max_tokens=GEN_TOKENS,
            **GEN_KWARGS))
        wall = time.time() - t1
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
        # draft/MTP acceptance, when the build reports it
        cell["draft_n"] = tim.get("draft_n")
        cell["draft_n_accepted"] = tim.get("draft_n_accepted")
    except Exception as e:
        rec = harvest_from_log(log, ctx - HEADROOM)
        cell.update(rec)
        cell["status"] = "ok_from_server_log" if rec.get("prefill_tps") else "request_failed"
        cell["error"] = repr(e)[:600]
    stop.set()
    time.sleep(1.1)
    cell["vram_peak_gib"] = max(samples) if samples else None
    a, p_ = cell.get("vram_after_load_gib"), cell.get("vram_peak_gib")
    if a and p_ and p_ < a - 0.05:
        cell["vram_peak_gib"] = a
        cell["vram_peak_source"] = "after_load"
    cell["cell_wall_s"] = round(time.time() - t0, 1)
    stop_server()
    return cell


def measured(c):
    return bool(c) and c.get("prefill_tps") is not None and c.get("decode_tps") is not None


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"campaign": "llmbench ctx-sweep RTX 3090 (CUDA)",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cells": {}}


def save_state(st):
    st["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def write_sweep(st):
    rows = {str(c): st["cells"][str(c)] for c in RUNGS if str(c) in st["cells"]}
    json.dump({
        "model": "byteshape-qwen3-8-27b-iq4xs",
        "name": "Qwen3.8-27B",
        "quant": "IQ4_XS (3.84 bpw)",
        "file": "Qwen3.8-27B-IQ4_XS-3.84bpw.gguf",
        "source": "huggingface.co/byteshape/Qwen3.8-27B-GGUF",
        "gpu": "NVIDIA GeForce RTX 3090 24 GiB (CUDA, Windows)",
        "server_bin": "llama.cpp b12189 win-cuda-12.4-x64 (llama-server.exe)",
        "flags": STD + REASONING + (SPEC if USE_SPEC else []),
        "mmproj": USE_MMPROJ,
        "gen_tokens": GEN_TOKENS, "headroom": HEADROOM,
        "probe": PROBE.strip(),
        "filler_sha256": __import__("hashlib").sha256(open(PACK, "rb").read()).hexdigest(),
        "method": ("server restarted per rung with -c <ctx>; one cold /v1/chat/completions "
                   "(temp 0, cache_prompt false, no stream, ignore_eos, max_tokens 64); "
                   "prompt calibrated via /tokenize to ctx-512"),
        "cells": rows}, open(SWEEP, "w"), indent=1)


def main():
    args = sys.argv[1:]
    rungs = RUNGS
    if "--rungs" in args:
        rungs = [int(x) for x in args[args.index("--rungs") + 1].split(",")]
    st = load_state()
    if "--report" not in args:
        for ctx in rungs:
            k = str(ctx)
            if k in st["cells"] and (measured(st["cells"][k]) or
                                     st["cells"][k].get("status") == "does_not_fit"):
                print(f"[{ctx}] cached ({st['cells'][k].get('status')})", flush=True)
                continue
            print(f"[{ctx}] running ...", flush=True)
            cell = run_cell(ctx)
            st["cells"][k] = cell
            save_state(st)
            write_sweep(st)
            print(f"[{ctx}] {json.dumps({k: cell.get(k) for k in ('status','prefill_tps','decode_tps','wall_s','vram_peak_gib','error')})}",
                  flush=True)
    write_sweep(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
