#!/usr/bin/env python3
"""suite_driver.py — integrity-safe driver for the 4-game suite matrix.

Why this exists: suite_matrix.py trusts the `/v1/models` answer (always `active.gguf`)
as identity, and its served_model_stats makes the same mistake. This driver makes the
per-cell identity assertion real:

  * before a cell, read /props.model_path from the live server, resolve symlinks ON THE
    GPU HOST (readlink -f), and compare with the exact file we launched;
  * after a cell, re-read it — a cell whose server changed underneath is VOID;
  * each attempt must show completion_tokens > 0 AND finish_reason set, else VOID.

State lives in games/suite/state.json (one record per slug) and every cell's own
build.json; re-running resumes. One model config on the card at a time.

  suite_driver.py run [--models a,b] [--specs x,y] [--no-restart]
  suite_driver.py identity --slug S
  suite_driver.py restore            # put stock38mtp back on the card
  suite_driver.py summary
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "suite", "out")
STATE = os.path.join(HERE, "suite", "state.json")
PY = sys.executable
SPEC_ORDER = ["ball-drop-sandbox", "tower-stacker", "tower-defence", "match3-cascades"]
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "ubuntu@192.168.1.148"]

M = "/home/ubuntu/models"
MODELS = {
    # slug: base, host file launched, preset for srv.sh (None = restart prod unit as-is)
    "qwen3-8-27b-q4km":       dict(base="http://192.168.1.148:8080", preset="stock38mtp",
                                   path=M + "/Qwen3.8-27B-Q4_K_M.gguf"),
    "qwen3-8-27b-q4-0":       dict(base="http://192.168.1.148:8080", preset="q4_0",
                                   path=M + "/Qwen3.8-27B-Q4_0.gguf"),
    "qwen3-6-35b-a3b-ud-q4km": dict(base="http://192.168.1.148:8080", preset="qwen36",
                                   path=M + "/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"),
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": dict(base="http://192.168.1.148:8080", preset="davidau",
                                   path=M + "/DavidAU-Qwen3.8-27B-NEO-MAX-MTP-Q4_K_M.gguf"),
    "huihui-abl-q4-k-m":      dict(base="http://192.168.1.148:8080", preset="huihui",
                                   path=M + "/Huihui-abl-Q4_K_M.gguf"),
    "ornith-1-5-35b-a3b-q4-k-m": dict(base="http://192.168.1.148:8080", preset="ornith",
                                   path=M + "/bench-new/ornith35a3b/Ornith-1.5-35B-Q4_K_M.gguf"),
    "lfm3-1-7b-q4-k-m":       dict(base="http://192.168.1.148:8091", preset="lfm3",
                                   path="/home/ubuntu/llmbench/tune/dl4/LFM3-1.7B-Q4_K_M.gguf"),
}
ORDER = ["qwen3-8-27b-q4km", "qwen3-8-27b-q4-0", "qwen3-6-35b-a3b-ud-q4km",
         "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m", "huihui-abl-q4-k-m",
         "ornith-1-5-35b-a3b-q4-k-m", "lfm3-1-7b-q4-k-m"]


def remote(cmd, timeout=1200):
    return subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout)


def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(os.path.join(HERE, "suite", "driver.log"), "a") as f:
        f.write(line + "\n")


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"cells": {}, "runs": []}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(s, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def props(base):
    try:
        p = json.load(urllib.request.urlopen(base.rstrip("/") + "/props", timeout=20))
    except Exception as e:
        return {"error": str(e)[:150]}
    return {"model_path": p.get("model_path") or (p.get("model") or {}).get("path"),
            "n_ctx": (p.get("default_generation_settings") or {}).get("n_ctx")}


def identity(slug):
    """The launched file vs what the server says it serves, resolved on the GPU host."""
    m = MODELS[slug]
    got = props(m["base"])
    if got.get("error"):
        return {"ok": False, "why": "server unreachable: " + got["error"], "props": got}
    served_raw = got["model_path"]
    # resolve the path the SERVER reports, on the host (symlinks -> real file, + size)
    r = remote("readlink -f %s; stat -L -c %%s %s 2>/dev/null" % (served_raw, served_raw))
    served_real = r.stdout.splitlines()[0].strip() if r.stdout.strip() else served_raw
    r2 = remote("readlink -f %s; stat -L -c %%s %s" % (m["path"], m["path"]))
    want_lines = [x.strip() for x in r2.stdout.splitlines() if x.strip()]
    want_real = want_lines[0] if want_lines else m["path"]
    want_size = want_lines[1] if len(want_lines) > 1 else None
    served_size = r.stdout.splitlines()[1].strip() if len(r.stdout.splitlines()) > 1 else None
    ok = (served_real == want_real) and (served_size is None or served_size == want_size)
    return {"ok": ok, "served_raw": served_raw, "served_real": served_real,
            "served_size": served_size, "want_real": want_real, "want_size": want_size,
            "n_ctx": got.get("n_ctx")}


def wait_ready(base, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = props(base)
        if p.get("model_path"):
            return True, p
        time.sleep(5)
    return False, p


def start(slug):
    m = MODELS[slug]
    if m["preset"] == "lfm3":
        r = remote("bash ~/bin/srv_lfm3.sh", timeout=120)
        log("lfm3 launch: " + (r.stdout + r.stderr).strip()[-200:])
    else:
        r = remote("bash ~/bin/srv.sh %s" % m["preset"], timeout=1200)
        log("%s: srv.sh %s -> %s" % (slug, m["preset"], r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]))
        if "READY" not in r.stdout:
            return False, "srv.sh failed: " + (r.stdout + r.stderr)[-300:]
    ok, p = wait_ready(m["base"])
    if not ok:
        return False, "never answered: %s" % json.dumps(p)[:200]
    idn = identity(slug)
    log("%s: identity %s (served %s size %s / want %s size %s)" % (
        slug, "OK" if idn["ok"] else "MISMATCH", idn.get("served_real"), idn.get("served_size"),
        idn.get("want_real"), idn.get("want_size")))
    if not idn["ok"]:
        return False, "identity mismatch after launch: %s" % json.dumps(idn)[:400]
    return True, idn


def stop_extra(slug):
    if MODELS[slug]["base"].endswith(":8091"):
        remote("pkill -f 'port 8091' || true")


def cell_done(slug, spec):
    p = os.path.join(OUT, slug, spec, "build.json")
    if not os.path.isfile(p):
        return False
    try:
        b = json.load(open(p))
    except Exception:
        return False
    return bool(b.get("valid")) and bool(b.get("turns_used"))


def run_cell(slug, spec, attempts=0):
    """Run one cell with an identity assertion before and after; annotate build.json."""
    st = load_state()
    idn0 = identity(slug)
    if not idn0["ok"]:
        log("%s/%s: VOID before start — %s" % (slug, spec, json.dumps(idn0)[:300]))
        st["cells"]["%s/%s" % (slug, spec)] = {"void": True, "why": "identity before: " + json.dumps(idn0)[:300],
                                              "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        save_state(st)
        return
    log("%s/%s: start (served %s, ctx %s) pid-free check done" % (slug, spec, idn0["served_real"], idn0["n_ctx"]))
    t0 = time.time()
    cmd = [PY, os.path.join(HERE, "suite_run.py"), "--base", MODELS[slug]["base"],
           "--model-slug", slug, "--spec", spec, "--out", OUT]
    if attempts:
        # a wall-clock cap the operator sets deliberately; recorded in build.json as
        # turns_allowed so a short run is never mistaken for a full 10-repair sweep
        cmd += ["--attempts", str(attempts)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=8 * 3600)
    idn1 = identity(slug)
    bj = os.path.join(OUT, slug, spec, "build.json")
    try:
        b = json.load(open(bj))
    except Exception as e:
        st["cells"]["%s/%s" % (slug, spec)] = {"void": True, "why": "no build.json: %s" % e,
                                              "stdout": (r.stdout or "")[-1200:], "returncode": r.returncode,
                                              "stderr": (r.stderr or "")[-1200:],
                                              "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        save_state(st)
        log("%s/%s: NO build.json (%s) rc=%s stderr=%s" % (slug, spec, e, r.returncode,
                                                          (r.stderr or "").strip()[-400:]))
        return
    void_turns = [p for p in b.get("per_attempt", []) if p.get("void")]
    real_turns = [p for p in b.get("per_attempt", []) if not p.get("void")
                  and not p.get("error")
                  and (p.get("completion_tokens") or 0) > 0
                  and (p.get("finish_reason") in ("stop", "length", "tool_calls")
                       or p.get("gate_pass") is not None)]  # gate ran => a file was produced
    valid = bool(idn1["ok"]) and len(real_turns) > 0
    b["identity"] = {"before": idn0, "after": idn1,
                     "launched_file": MODELS[slug]["path"], "checked": True}
    b["void_turns"] = len(void_turns)
    b["valid"] = valid
    b["why_invalid"] = (None if valid else
                        ("identity after: " + json.dumps(idn1)[:300]) if not idn1["ok"]
                        else "no attempt produced completion_tokens>0 with finish_reason set")
    b["driver_wall_s"] = round(time.time() - t0, 1)
    json.dump(b, open(bj, "w"), indent=1)
    st["cells"]["%s/%s" % (slug, spec)] = {"valid": valid, "why": b["why_invalid"],
                                          "void_turns": len(void_turns),
                                          "turns_used": b.get("turns_used"),
                                          "accepted": b.get("accepted_attempt"),
                                          "status": b.get("status"),
                                          "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    save_state(st)
    log("%s/%s: %s turns=%s accepted=%s status=%s (%.0fs)%s" % (
        slug, spec, "VALID" if valid else "VOID", b.get("turns_used"), b.get("accepted_attempt"),
        b.get("status"), time.time() - t0, "" if valid else " — " + str(b["why_invalid"])))


def cmd_run(a):
    models = a.models.split(",") if a.models else ORDER
    specs = a.specs.split(",") if a.specs else SPEC_ORDER
    for slug in models:
        todo = [s for s in specs if not cell_done(slug, s)]
        if not todo:
            log("%s: all specs done" % slug)
            continue
        if not a.no_restart:
            ok, why = start(slug)
            if not ok:
                log("%s: NOT STARTED — %s" % (slug, why))
                continue
        else:
            idn = identity(slug)
            if not idn["ok"]:
                log("%s: NOT STARTED (no-restart) — %s" % (slug, json.dumps(idn)[:300]))
                continue
        for spec in todo:
            run_cell(slug, spec, a.attempts)
        stop_extra(slug)


def cmd_restore(a):
    r = remote("bash ~/bin/srv.sh stock38mtp", timeout=1200)
    log("restore stock38mtp -> " + (r.stdout + r.stderr).strip().splitlines()[-1])
    remote("pkill -f 'port 8091' || true")
    ok, p = wait_ready("http://192.168.1.148:8080")
    log("restore: %s %s" % ("ready" if ok else "NOT READY", json.dumps(p)[:200]))


def cmd_identity(a):
    print(json.dumps(identity(a.slug), indent=1))


def cmd_summary(a):
    st = load_state()
    rows = []
    for slug in ORDER:
        for spec in SPEC_ORDER:
            bj = os.path.join(OUT, slug, spec, "build.json")
            b = json.load(open(bj)) if os.path.isfile(bj) else None
            rows.append({"slug": slug, "spec": spec,
                         "valid": (b or {}).get("valid"),
                         "why": (b or {}).get("why_invalid") or st["cells"].get("%s/%s" % (slug, spec), {}).get("why"),
                         "turns": (b or {}).get("turns_used"),
                         "accepted": (b or {}).get("accepted_attempt"),
                         "status": (b or {}).get("status"),
                         "completion_tokens": (b or {}).get("total_completion_tokens"),
                         "wall_s": (b or {}).get("total_wall_s")})
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run"); p.add_argument("--models", default=""); p.add_argument("--specs", default="")
    p.add_argument("--no-restart", action="store_true")
    p.add_argument("--attempts", type=int, default=0)
    sub.add_parser("restore")
    q = sub.add_parser("identity"); q.add_argument("--slug", required=True)
    sub.add_parser("summary")
    a = ap.parse_args()
    {"run": cmd_run, "restore": cmd_restore, "identity": cmd_identity, "summary": cmd_summary}[a.cmd](a)
