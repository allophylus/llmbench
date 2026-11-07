#!/usr/bin/env python3
"""rungs_ablate.py — accelerator ablation at the matched context rungs.

Same probe as benchmarks/ctx-sweep/ctx_sweep.py (that is the point: the ablation
columns must be readable against the speed matrix):

  * server restarted per cell with `-c <rung>` and identical flags except the
    toggled accelerator;
  * ONE prompt calibrated with `/tokenize` to (rung - 512) tokens;
  * ONE cold /v1/chat/completions, temperature 0, cache_prompt false, ignore_eos,
    max_tokens 64;
  * prefill / decode taken from the server's own timings block;
  * VRAM peak sampled at 1 Hz.

Writes benchmarks/ablation/arms-rungs/<slug>/<arm>-<rung>.json, one file per cell,
so a re-run of a single cell is `--only <slug>,<arm> --rungs <rung>`.

usage: rungs_ablate.py [--plan primary|secondary|all] [--only slug,arm] [--rungs 4096,...]
                       [--force] [--max-cells N]
"""
import argparse, glob, json, os, re, shlex, subprocess, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("ABL_OUT") or os.path.join(HERE, "arms-rungs")
STATE = os.path.join(OUT, "_state.json")

BASE = "http://127.0.0.1"
VRAM = "/sys/class/drm/card1/device/mem_info_vram_used"
PACK = "/home/ubuntu/llmbench/suite/packs/ctx_filler.txt"
SLOTFILE = "/home/ubuntu/ctx-sweep/slot.state"
LOCK = os.path.expanduser("~/.config/systemd/user/qwen-longctx.service.d/zz-ablation-rungs-lock.conf")
RUNMARK = "/home/ubuntu/ctx-sweep/ABLATION-RUN"

B11517 = "/home/ubuntu/llama-vulkan/llama-b11517/llama-server"
M = "/home/ubuntu/models"

GEN_TOKENS = 64
HEADROOM = 512
MIN_GEN_OK = 32
REQ_TIMEOUT_S = int(os.environ.get("REQ_TIMEOUT_S", "7200"))

STD = ["-ngl", "99", "-b", "16384", "-ub", "2048",
       "--cache-reuse", "256", "--metrics"]
KVQ8 = ["-ctk", "q8_0", "-ctv", "q4_0"]

PROBE = ("\n\nIgnore all of the text above this line. Write out the multiplication "
         "table from 1x1 to 12x12, one row per line, in the form 1x1=1.")
GEN_KWARGS = {"temperature": 0, "top_k": 1, "top_p": 1.0, "repeat_penalty": 1.0,
              "cache_prompt": False, "stream": False, "ignore_eos": True}

MODELS = {
    "qwen3-8-27b-q4km": dict(
        name="Qwen3.8-27B", quant="Q4_K_M",
        file=f"{M}/Qwen3.8-27B-Q4_K_M.gguf", mmproj=f"{M}/mmproj-Qwen3.8-27B-F16.gguf",
        extra=["--jinja", "--reasoning", "off"], native_ctx=131072),
    "qwen3-6-35b-a3b-ud-q4km": dict(
        name="Qwen3.6-35B-A3B", quant="Q4_K_M",
        file=f"{M}/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
        mmproj=f"{M}/qwen36/mmproj-Qwen3.6-35B-A3B-F16.gguf",
        extra=["--jinja"], native_ctx=262144),
    "qwen3-8-27b-q4-0": dict(
        name="Qwen3.8-27B", quant="Q4_0",
        file=f"{M}/Qwen3.8-27B-Q4_0.gguf", mmproj=f"{M}/mmproj-Qwen3.8-27B-F16.gguf",
        extra=["--jinja", "--reasoning", "off"], native_ctx=131072),
}

DFLASH = f"{M}/Qwen3.8-27B-DFlash2-Q4_K_M.gguf"
KVF16 = ["-ctk", "f16", "-ctv", "f16"]
MTP = ["--spec-type", "draft-mtp", "--spec-draft-n-max", "7", "--spec-draft-n-min", "1"]
DFLASH_FLAGS = ["--spec-type", "draft-dflash", "--spec-draft-model", DFLASH,
                "--spec-draft-n-max", "7", "--spec-draft-n-min", "1"]

# Every arm starts from STD; `fa` and `kv` replace the accelerator/KV defaults.
# Every arm runs -np 1. (DFlash loads were seen to die silently while loading the
# drafter in two runs and then load fine on an identical argv, so a load failure is
# retried once in main(); np=None would leave the engine default.)
ARMS = {
    "A-baseline": dict(label="baseline", fa="on", kv=[], extra=[], np=1),
    "B-fa-off": dict(label="FA off", fa="off", kv=KVF16, extra=[], np=1),
    "C-draft-mtp": dict(label="MTP", fa="on", kv=[], extra=MTP, np=1),
    "D-draft-dflash": dict(label="DFlash", fa="on", kv=[], extra=DFLASH_FLAGS, np=1),
}

# MoE note: MTP needs an MTP head in the target file and DFlash needs a drafter
# trained for that model; neither is declared applicable for the A3B, so its plan
# is baseline + FA off only rather than a fabricated row.
RUNGS = [4096, 32768, 65536, 131072, 262144]

PLANS = {
    # order = cheapest-first evidence: baseline, MTP, the two DFlash rungs that are
    # required, then the slow FA-off grid, then the remaining DFlash rungs.
    "primary": [("qwen3-8-27b-q4km", [
        ("A-baseline", RUNGS),
        ("C-draft-mtp", RUNGS),
        ("D-draft-dflash", [4096, 131072]),
        ("B-fa-off", RUNGS)])],
    "extend": [("qwen3-8-27b-q4km", [("D-draft-dflash", [32768, 65536, 262144])])],
    "secondary": [("qwen3-6-35b-a3b-ud-q4km",
                   [("A-baseline", RUNGS), ("B-fa-off", RUNGS)])],
}


# ------------------------------------------------------------------ plumbing
def sh(cmd, timeout=300):
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)


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


def slot(state, detail=""):
    try:
        os.makedirs(os.path.dirname(SLOTFILE), exist_ok=True)
        with open(SLOTFILE + ".tmp", "w") as f:
            f.write(f"{state} {time.strftime('%H:%M:%S')} {detail}\n")
        os.replace(SLOTFILE + ".tmp", SLOTFILE)
    except Exception:
        pass


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)


def port_pid(port):
    out = sh(f"ss -ltnp 'sport = :{port}' 2>/dev/null | grep -o 'pid=[0-9]*' | head -1").stdout
    m = re.search(r"pid=(\d+)", out or "")
    return int(m.group(1)) if m else None


def port_busy(port):
    return port_pid(port) is not None


def metric_snapshot(port):
    try:
        txt = urllib.request.urlopen(f"{BASE}:{port}/metrics", timeout=5).read().decode()
    except Exception:
        return None
    out = {}
    for k in ("llamacpp:requests_processing", "llamacpp:prompt_tokens_total",
              "llamacpp:predicted_tokens_total"):
        m = re.search(r"^%s\s+([0-9.eE+]+)" % re.escape(k), txt, re.M)
        if m:
            out[k] = float(m.group(1))
    return out


def traffic_active(port):
    """Two samples ~5 s apart: active if a counter moved or a request is in flight."""
    a = metric_snapshot(port)
    time.sleep(5)
    b = metric_snapshot(port)
    if not a or not b:
        return False
    keys = ("llamacpp:prompt_tokens_total", "llamacpp:predicted_tokens_total")
    moved = any(b.get(k, 0) > a.get(k, 0) for k in keys)
    busy = (a.get("llamacpp:requests_processing", 0) > 0
            or b.get("llamacpp:requests_processing", 0) > 0)
    return moved or busy


def free_port(port, wait_s=300):
    """Polite eviction: sample traffic first; only a quiet server is killed."""
    pid = port_pid(port)
    if not pid:
        return
    t0 = time.time()
    while time.time() - t0 < wait_s:
        if not traffic_active(port):
            sh(f"kill {pid} 2>/dev/null || true")
            w = time.time()
            while port_busy(port) and time.time() - w < 45:
                time.sleep(1)
            if port_busy(port):
                sh(f"kill -9 {pid} 2>/dev/null || true")
                w = time.time()
                while port_busy(port) and time.time() - w < 15:
                    time.sleep(1)
            log(f"freed :{port} (was pid {pid}, quiet)")
            time.sleep(2)
            return
        log(f":{port} pid {pid} has active traffic — waiting (etiquette)")
        time.sleep(20)
    raise RuntimeError(f":{port} stayed busy for {wait_s}s — not killing a live benchmark")


def reclaim(keep_pid=None):
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


FATAL = re.compile(
    r"error while handling argument|failed to load model|failed to allocate|"
    r"out of memory|error loading model|exiting due to model loading error|"
    r"unsupported model architecture|unknown model architecture|"
    r"failed to create context|VK_ERROR_OUT_OF_DEVICE_MEMORY|alloc_tensor_range.*failed|"
    r"couldn't bind HTTP server socket|exiting due to HTTP server error|"
    r"failed to initialize", re.I)


def _fatal_text(tail):
    """Drop the lines llama.cpp prints while it probes memory fitting; they say
    'failed to initialize the context' on a healthy DFlash launch."""
    return "\n".join(l for l in (tail or "").splitlines()
                     if "memory fitting" not in l and "fitting without it" not in l)


def wait_ready(port, logpath, pid=None, max_wait=420):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        tail = sh(f"tail -c 4000 {logpath} 2>/dev/null").stdout or ""
        if FATAL.search(_fatal_text(tail)):
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
    return False, (sh(f"tail -c 4000 {logpath}").stdout or "")


class Calibrator:
    """Verbatim from ctx_sweep.py: same filler, same /tokenize loop, same tolerance."""

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


# ------------------------------------------------------------------ lock + prod
def acquire_card():
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    open(LOCK, "w").close()
    sh("systemctl --user daemon-reload && systemctl --user stop qwen-longctx 2>/dev/null; "
       "systemctl --user reset-failed qwen-longctx 2>/dev/null || true")
    t0 = time.time()
    while port_busy(8080) and time.time() - t0 < 60:
        time.sleep(1)
    if port_busy(8080):
        free_port(8080)
    open(RUNMARK, "w").write(time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n")
    slot("BUSY", "ablation-rungs start")


def release_card():
    for p in (8080, 8081, 8091):
        pid = port_pid(p)
        if pid:
            sh(f"kill {pid} 2>/dev/null || true")
    for p in (8080, 8081, 8091):
        w = time.time()
        while port_busy(p) and time.time() - w < 40:
            time.sleep(1)
    try:
        os.remove(LOCK)
    except OSError:
        pass
    try:
        os.remove(RUNMARK)
    except OSError:
        pass
    sh("systemctl --user daemon-reload")
    r = sh("cd /home/ubuntu && ./bin/srv.sh stock38mtp", timeout=400)
    log("prod restore: " + (r.stdout or r.stderr or "").strip()[-400:])
    slot("IDLE", "ablation-rungs done")


# ------------------------------------------------------------------ one cell
def cell_path(slug, arm, rung):
    return os.path.join(OUT, slug, f"{arm}-{rung}.json")


def run_cell(slug, arm, rung):
    cfg = MODELS[slug]
    a = ARMS[arm]
    cell = {"model": slug, "name": cfg["name"], "quant": cfg["quant"], "arm": arm,
            "arm_label": a["label"], "fa": a["fa"], "rung": rung,
            "kv_cache_type": "f16/f16" if a["kv"] else "q8_0/q4_0",
            "n_parallel": a.get("np"),
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    t0 = time.time()
    slot("BUSY", f"{slug}|{arm}|{rung}")

    argv = [B11517, "-m", cfg["file"], "--host", "0.0.0.0", "--port", "8080",
            "-c", str(rung)]
    argv += STD + ["-fa", a["fa"]] + (a["kv"] or KVQ8) + cfg["extra"] + a["extra"]
    if a.get("np"):
        argv += ["-np", str(a["np"])]
    if cfg["mmproj"]:
        argv += ["--mmproj", cfg["mmproj"]]
    cell["argv"] = argv
    cell["_power_cap_w"] = None
    try:
        cell["_power_cap_w"] = int(open("/sys/class/hwmon/hwmon0/power1_cap").read().strip()) // 1000000
    except Exception:
        pass

    for p in (8081, 8091):
        free_port(p, wait_s=60)
    free_port(8080)
    cell["vram_baseline_gib"] = round(vram() / 2**30, 2) if vram() else None

    logpath = f"/home/ubuntu/ctx-sweep/abl-{slug}-{arm}-{rung}.log"
    r = sh("nohup " + " ".join(shlex.quote(x) for x in argv) + f" > {logpath} 2>&1 & echo STARTED $!")
    m = re.search(r"STARTED (\d+)", (r.stdout or "") + (r.stderr or ""))
    pid = int(m.group(1)) if m else None
    cell["log"] = logpath
    if pid is None:
        cell["status"] = "start_failed"
        cell["error"] = (r.stdout or r.stderr)[-500:]
        return cell
    orphan = reclaim(keep_pid=pid)
    if orphan:
        cell["killed_orphan_pids"] = orphan

    ok, tail = wait_ready(8080, logpath, pid=pid)
    cell["load_s"] = round(time.time() - t0, 1)
    if not ok:
        # a refused allocation is a fit problem; a silent exit while loading a drafter
        # is a load failure, and the page must not call that "does not fit".
        cell["status"] = "does_not_fit" if FATAL.search(_fatal_text(tail)) else "load_failed"
        cell["error"] = (tail or "")[-1500:]
        return cell

    try:
        props, _ = http("/props", timeout=60)
        cell["n_ctx_server"] = (props.get("default_generation_settings") or {}).get("n_ctx")
        cell["build_info"] = props.get("build_info")
        cell["total_slots"] = props.get("total_slots")
    except Exception as e:
        cell["error_props"] = repr(e)[:200]
    cell["vram_after_load_gib"] = round(vram() / 2**30, 2) if vram() else None

    target = rung - HEADROOM
    cal = Calibrator(8080)
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
        cell.update({"target_tokens": target, "prompt_tokens_client": n,
                     "calibration": cinfo})
        body, wall = http("/v1/chat/completions", dict(
            messages=[{"role": "user", "content": prompt}], max_tokens=GEN_TOKENS,
            **GEN_KWARGS))
        tim = body.get("timings") or {}
        ch = (body.get("choices") or [{}])[0]
        cell.update({
            "status": "ok" if (tim.get("predicted_n") or 0) >= MIN_GEN_OK else "short_generation",
            "wall_s": round(wall, 1),
            "prompt_n": tim.get("prompt_n"), "predicted_n": tim.get("predicted_n"),
            "prefill_ms": tim.get("prompt_ms"),
            "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
            "decode_ms": tim.get("predicted_ms"),
            "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
            "finish_reason": ch.get("finish_reason"),
            "content_head": ((ch.get("message") or {}).get("content") or "")[:60]})
    except Exception as e:
        cell["status"] = "request_failed"
        cell["error"] = repr(e)[:400]
    stop.set()
    time.sleep(1.1)
    cell["vram_peak_gib"] = round(max(samples) / 2**30, 2) if samples else None
    if cell.get("vram_after_load_gib") and cell["vram_peak_gib"] and \
            cell["vram_peak_gib"] < cell["vram_after_load_gib"] - 0.05:
        cell["vram_peak_gib"] = cell["vram_after_load_gib"]
        cell["vram_peak_source"] = "after_load"
    cell["cell_wall_s"] = round(time.time() - t0, 1)

    # spec acceptance line, if the arm drafted anything
    if pid:
        txt = sh(f"grep -a 'draft acceptance' {logpath} | tail -2").stdout or ""
        if txt.strip():
            cell["spec_lines"] = txt.strip().splitlines()
    return cell


def stop_server():
    pid = port_pid(8080)
    if pid:
        sh(f"kill {pid} 2>/dev/null || true")
        w = time.time()
        while port_busy(8080) and time.time() - w < 45:
            time.sleep(1)
        if port_busy(8080):
            sh(f"kill -9 {pid} 2>/dev/null || true")
    time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="primary", choices=list(PLANS) + ["all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--rungs", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-cells", type=int, default=0)
    ap.add_argument("--no-restore", action="store_true")
    args = ap.parse_args()

    rungs = [int(x) for x in args.rungs.split(",") if x] or RUNGS
    plans = list(PLANS.values()) if args.plan == "all" else [PLANS[args.plan]]
    todo = []
    for entries in plans:
        for slug, arms in entries:
            for arm, arm_rungs in arms:
                for rung in (rungs if args.rungs else arm_rungs):
                    if args.only and f"{slug},{arm}" != args.only:
                        continue
                    p = cell_path(slug, arm, rung)
                    if os.path.exists(p) and not args.force:
                        j = json.load(open(p))
                        if j.get("status") == "ok":
                            continue
                    todo.append((slug, arm, rung))
    if not todo:
        log("nothing to do")
        return 0
    if args.max_cells:
        todo = todo[:args.max_cells]
    log(f"{len(todo)} cells: " + ", ".join(f"{s}/{a}/{r//1024}K" for s, a, r in todo))

    os.makedirs(OUT, exist_ok=True)
    acquire_card()
    done = 0
    try:
        for slug, arm, rung in todo:
            log(f"cell {slug} {arm} {rung}: starting")
            cell = run_cell(slug, arm, rung)
            stop_server()
            if cell.get("status") == "load_failed":
                log(f"cell {slug} {arm} {rung}: load failed — one retry")
                time.sleep(5)
                cell = run_cell(slug, arm, rung)
                stop_server()
            os.makedirs(os.path.dirname(cell_path(slug, arm, rung)), exist_ok=True)
            tmp = cell_path(slug, arm, rung) + ".tmp"
            json.dump(cell, open(tmp, "w"), indent=1)
            os.replace(tmp, cell_path(slug, arm, rung))
            done += 1
            log(f"cell {slug} {arm} {rung}: {cell.get('status')} "
                f"prefill={cell.get('prefill_tps')} decode={cell.get('decode_tps')} "
                f"({cell.get('cell_wall_s')}s)")
            slot("IDLE", f"after {slug}|{arm}|{rung}")
    finally:
        try:
            stop_server()
        finally:
            if not args.no_restore:
                release_card()
            else:
                os.remove(LOCK) if os.path.exists(LOCK) else None
        st = {}
        if os.path.exists(STATE):
            try:
                st = json.load(open(STATE))
            except Exception:
                st = {}
        st.update({"updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "cells_done": st.get("cells_done", 0) + done})
        json.dump(st, open(STATE, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
