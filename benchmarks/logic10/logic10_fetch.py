#!/usr/bin/env python3
"""logic10_fetch.py — copy logic10 result JSONs from the GPU host into the repo and
regenerate the /logic/ page.

The host-side files live in ~/logic10-out on the benchmark box; they are pulled with
rsync over the operator's existing SSH alias and written to
benchmarks/logic10/results/<slug>.json (checked in, so the page stays reproducible).

usage: logic10_fetch.py [--host ubuntu@<bench host>] [--build-only]
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(ROOT, "benchmarks", "logic10", "results")
HOST = os.environ.get("LOGIC10_HOST", "ubuntu@192.168.1.148")
REMOTE = "/home/ubuntu/logic10-out"


def main():
    global HOST
    os.makedirs(DEST, exist_ok=True)
    if "--host" in sys.argv:
        HOST = sys.argv[sys.argv.index("--host") + 1]
    if "--build-only" not in sys.argv:
        r = subprocess.run(["rsync", "-a", "--include=*.json", "--exclude=*",
                            f"{HOST}:{REMOTE}/", DEST + "/"], capture_output=True, text=True)
        if r.returncode not in (0, 23):
            # 23 = some files vanished mid-copy (writing in progress); harmless
            print(r.stderr.strip()[-400:])
    # drop .bak mirrors and anything that is not a per-model result
    for f in os.listdir(DEST):
        p = os.path.join(DEST, f)
        if f.endswith(".json.bak") or (f.endswith(".json") and f.startswith("run")):
            os.remove(p)
    got = {}
    for f in sorted(os.listdir(DEST)):
        if not f.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(DEST, f), encoding="utf-8"))
        except Exception:
            continue
        modes = d.get("modes") or {}
        got[d.get("slug") or f[:-5]] = {m: len((modes.get(m) or {}).get("rows") or [])
                                        for m in ("off", "on")}
    print(json.dumps(got, indent=1))
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_pages_logic.py")],
                   check=True)


if __name__ == "__main__":
    main()
