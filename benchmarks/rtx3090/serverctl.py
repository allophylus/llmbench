#!/usr/bin/env python3
"""serverctl.py — start/stop the RTX 3090 (Windows CUDA) llama-server for the quality cells.

The sweep owns its own per-rung server lifecycle (sweep3090.py). The quality cells
(gpqa / thinking pair / chat / vision) need ONE server kept up across several harnesses,
so this script exposes the same start/stop primitives.

usage:
  serverctl.py start --ctx 16384 [--reasoning auto] [--no-spec] [--no-mmproj]
  serverctl.py stop
  serverctl.py status
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep3090 as S  # noqa: E402


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    cmd = args[0]
    if cmd == "stop":
        print("stopped" if S.stop_server() else "still answering")
        return 0
    if cmd == "status":
        try:
            h = S.http("/health", timeout=5)
            print(json.dumps({"health": h, "vram_gib": S.vram_gib()}))
        except Exception as e:
            print(json.dumps({"health": None, "error": str(e)[:120], "vram_gib": S.vram_gib()}))
        return 0
    if cmd != "start":
        print(__doc__)
        return 2

    ctx = 16384
    for i, a in enumerate(args):
        if a == "--ctx":
            ctx = int(args[i + 1])
        if a == "--reasoning" and args[i + 1] != "off":
            S.REASONING = []
        if a == "--no-spec":
            S.USE_SPEC = False
        if a == "--no-mmproj":
            S.USE_MMPROJ = False
    S.stop_server()
    argv, log = S.start_server(ctx)
    ok, tail = S.wait_ready(ctx, log)
    print(json.dumps({"ok": ok, "ctx": ctx, "argv": " ".join(argv), "log": log,
                      "vram_gib": S.vram_gib(),
                      "tail": None if ok else tail[-1200:]}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
