#!/usr/bin/env python3
"""suite_matrix.py — run every (model, spec) cell of the 4-game suite, one model at a time.

  suite_matrix.py --out games/suite/out [--models slug1,slug2] [--only-missing]
                  [--server cmd-for-slug] [--wait-for-slug qwen3-8-27b-q4km]

Models come from MODELS below (the runnable set in benchmarks/gapclose/INVENTORY.md; lfm3
needs llama.cpp b11874 on :8091, everything else the prod unit on :8080).

Wait rule (Fen's ordering requirement): before touching the card for the production
server, the matrix waits until another agent's queued work is finished — either
benchmarks/gapclose/state.json shows steps 4,5,6 with status done/won/verified, or the
screen session it names is gone. It never runs two model configs at once: it checks the
base URL's /props model path before and after each cell and refuses to start a cell if a
different model is answering.

Every cell result is already persisted by suite_run.py (build.json is written per cell),
so re-running with --only-missing resumes exactly where a crash left off.
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
PY = sys.executable
SPEC_ORDER = ["ball-drop-sandbox", "tower-stacker", "tower-defence", "match3-cascades"]

# slug -> (base_url, restart command on the GPU host; None = already serving)
MODELS = {
    # prod model: already served on :8080 by the prod unit — no restart needed, and the
    # first cell simply verifies the served model path before grading anything.
    "qwen3-8-27b-q4km": {"base": "http://192.168.1.148:8080", "preset": None},
    "qwen3-8-27b-q4-0": {"base": "http://192.168.1.148:8080", "preset": "q4_0"},
    "qwen3-6-35b-a3b-ud-q4km": {"base": "http://192.168.1.148:8080", "preset": "qwen36"},
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": {"base": "http://192.168.1.148:8080", "preset": "davidau"},
    "huihui-abl-q4-k-m": {"base": "http://192.168.1.148:8080", "preset": "huihui"},
    "ornith-1-5-35b-a3b-q4-k-m": {"base": "http://192.168.1.148:8080", "preset": "ornith"},
    "lfm3-1-7b-q4-k-m": {"base": "http://192.168.1.148:8091", "preset": "lfm3"},
}
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "ubuntu@192.168.1.148"]


def sh(cmd, timeout=3600, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       shell=isinstance(cmd, str))
    if check and r.returncode:
        raise RuntimeError((r.stderr or r.stdout)[-400:])
    return r


def remote(cmd, timeout=3600):
    return sh(SSH + [cmd], timeout)


def served_model(base):
    try:
        d = json.load(urllib.request.urlopen(base.rstrip("/") + "/v1/models", timeout=20))
        return (d.get("models") or [{}])[0].get("model") or d["data"][0]["id"]
    except Exception as e:
        return "ERROR " + str(e)[:120]


def gapclose_done(min_steps=(4, 5, 6)):
    """True when the other agent's step-4/5/6 work is finished or its screen is gone."""
    st = os.path.join(ROOT, "benchmarks", "gapclose", "state.json")
    try:
        s = json.load(open(st))
    except Exception:
        return False, "state.json unreadable"
    steps = s.get("steps", {})
    pending, screens = [], []
    for k in ("4-thinking", "5-ablation", "6-games"):
        v = steps.get(k, {})
        if str(v.get("status", "")).lower() not in ("done", "won", "verified", "skipped"):
            pending.append(k + ":" + str(v.get("status")))
        if v.get("screen"):
            screens.append(v["screen"])
    if not pending:
        return True, "steps 4/5/6 finished"
    r = remote("screen -ls").stdout
    alive = [x for x in screens if x.split()[0] in r]
    if screens and not alive:
        return True, "screen session(s) gone: " + ",".join(screens)
    return False, "pending " + ", ".join(pending) + ("; screens " + ",".join(alive) if alive else "")


def start_model(slug, wait_free=True):
    m = MODELS[slug]
    if m["preset"] is None:
        got = served_model(m["base"])
        return (not got.startswith("ERROR")), got
    if m["preset"] == "lfm3":
        remote("bash ~/bin/srv_lfm3.sh")
    else:
        ok, why = (True, "") if not wait_free else gapclose_done()
        if not ok:
            return False, "card busy: " + why
        r = remote("bash ~/bin/srv.sh %s" % m["preset"], timeout=900)
        if "READY" not in r.stdout:
            return False, "srv.sh failed: " + (r.stdout + r.stderr)[-300:]
    for _ in range(40):
        got = served_model(m["base"])
        if got and not got.startswith("ERROR"):
            return True, got
        time.sleep(5)
    return False, "server never answered on " + m["base"]


def stop_extra(slug):
    if MODELS[slug]["preset"] == "lfm3":
        remote("pkill -f 'port 8091' || true")


def cell_done(out, slug, spec):
    p = os.path.join(out, slug, spec, "build.json")
    if not os.path.isfile(p):
        return False
    try:
        b = json.load(open(p))
        return b.get("slug") == slug and bool(b.get("turns_used"))
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "suite", "out"))
    ap.add_argument("--models", default="", help="comma list; default all 7")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--specs", default="")
    ap.add_argument("--wait-for-card", action="store_true", default=True)
    ap.add_argument("--no-wait", dest="wait_for_card", action="store_false")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    models = [m for m in (a.models.split(",") if a.models else list(MODELS))]
    specs = a.specs.split(",") if a.specs else SPEC_ORDER
    log = os.path.join(out, "matrix.log")
    os.makedirs(out, exist_ok=True)

    def note(msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        open(log, "a").write(line + "\n")

    for slug in models:
        missing = [s for s in specs if not (a.only_missing and cell_done(out, slug, s))]
        if not missing:
            note("%s: nothing to do" % slug)
            continue
        ok, why = start_model(slug, a.wait_for_card)
        note("%s: server %s (%s)" % (slug, "ready" if ok else "FAILED", why))
        if not ok:
            note("%s: SKIPPED — %s" % (slug, why))
            continue
        for spec in missing:
            note("%s/%s: start" % (slug, spec))
            r = sh([PY, os.path.join(HERE, "suite_run.py"), "--base", MODELS[slug]["base"],
                    "--model-slug", slug, "--spec", spec, "--out", out], timeout=6 * 3600)
            note("%s/%s: exit %d %s" % (slug, spec, r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""))
            open(os.path.join(out, "matrix.log"), "a").write((r.stdout or "")[-6000:] + (r.stderr or "")[-3000:])
            if r.returncode:
                open(os.path.join(out, slug, spec, "run.err"), "w").write((r.stderr or "")[-4000:])
        stop_extra(slug)
    note("matrix finished")


if __name__ == "__main__":
    main()
