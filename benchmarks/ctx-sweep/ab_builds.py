#!/usr/bin/env python3
"""ab_builds.py — llama.cpp build A/B on the same GGUF and identical flags.

Runs the exact ctx_sweep.run_cell() cell (same STD flags, same /tokenize-calibrated
prompt, one cold request, 64 generated tokens, 1 Hz VRAM sampling) for each
(build, ctx) pair, `--reps` times, interleaved so both builds see the same thermal
state. Results are written to build-ab.json beside this file; nothing is written to
sweep.json / state.json, so published sweep rows are untouched.

usage (ON the GPU host): ab_builds.py --builds old,new --rungs 4096,131072 --reps 2
"""
import importlib.util, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build-ab.json")
spec = importlib.util.spec_from_file_location("ctx_sweep", os.path.join(HERE, "ctx_sweep.py"))
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

BUILDS = {
    "old": dict(tag="b11517", bin=cs.B11517,
                note="llama.cpp 0.8.0-dev, commit f5222f2-era build previously in prod"),
    "new": dict(tag="b12110", bin="/home/ubuntu/llama-vulkan/llama-b12110/llama-server",
                note="llama.cpp v0.9.0 release tag (ggml 0.29.0), commit cd959ba"),
}

args = sys.argv[1:]
def opt(name, default):
    return args[args.index(name) + 1] if name in args else default

want = opt("--builds", "old,new").split(",")
rungs = [int(x) for x in opt("--rungs", "4096,131072").split(",")]
reps = int(opt("--reps", "2"))

MODEL = dict(name="Qwen3.8-27B", quant="Q4_K_M",
             file=f"{cs.M}/Qwen3.8-27B-Q4_K_M.gguf",
             mmproj=f"{cs.M}/mmproj-Qwen3.8-27B-F16.gguf",
             port=8080, extra=["--jinja", "--reasoning", "off", "-np", "1"],
             native_ctx=131072)

res = {"kind": "build-ab", "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
       "flags_std": cs.STD, "gen_tokens": cs.GEN_TOKENS, "headroom": cs.HEADROOM,
       "probe": cs.PROBE.strip(), "reps": reps, "builds": {}, "cells": []}

for b in want:
    cs.MODELS[f"ab-{b}"] = dict(MODEL, bin=BUILDS[b]["bin"])
    res["builds"][b] = dict(BUILDS[b], bin=BUILDS[b]["bin"])

for rep in range(1, reps + 1):
    for ctx in rungs:
        for b in want:
            slug = f"ab-{b}"
            print(f"RUN rep={rep} build={b} ctx={ctx} @ {time.strftime('%H:%M:%S')}", flush=True)
            t0 = time.time()
            cell = cs.run_cell(slug, ctx)
            cell.update({"rep": rep, "build": b, "build_tag": BUILDS[b]["tag"], "ctx": ctx})
            res["cells"].append(cell)
            json.dump(res, open(OUT + ".part", "w"), indent=1)
            os.replace(OUT + ".part", OUT)
            print(f"DONE rep={rep} {b} {ctx} status={cell.get('status')} "
                  f"prefill={cell.get('prefill_tps')} decode={cell.get('decode_tps')} "
                  f"gen={cell.get('predicted_n')} vram={cell.get('vram_peak_gib')} "
                  f"took={round(time.time() - t0)}s", flush=True)

print("ALLDONE", flush=True)
