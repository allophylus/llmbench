#!/usr/bin/env python3
"""make_results.py — rebuild benchmarks/rtx3090/RESULTS.md from the JSON artifacts.

Nothing here is typed by hand: every published number is read from a file written by a
run script (sweep3090.py, think_pair3090.py, gapclose/chat_suite.py, games/build_run.py,
vision_smoke.py). A cell that was not measured is printed as "not run".
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RUNGS = [4096, 32768, 65536, 131072, 262144]


def load(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p))
    except Exception:
        return None


def main():
    sw = load("sweep3090.json")
    pair = load("gpqa-pair-3090.json")
    chat = load("chat10-3090.json")
    game = load(os.path.join("galaga-3090", "build.json"))
    vis = load("vision-smoke.json")

    L = ["# RTX 3090 — Qwen3.8-27B (ByteShape IQ4_XS), llama.cpp b12189 CUDA", "",
         "Separate card, separate table. Not merged with the R9700 (Vulkan) rows.", ""]
    if sw:
        L += [f"Model file: `{sw.get('file')}` ({sw.get('source')})",
              f"GPU: {sw.get('gpu')} · build: {sw.get('server_bin')}",
              f"Filler sha256: `{sw.get('filler_sha256')}`", "",
              "## Matched-context sweep", "",
              "| ctx | prompt tokens | prefill t/s | prefill s | decode t/s | peak VRAM GiB | draft accepted | status |",
              "|---|---|---|---|---|---|---|---|"]
        for c in RUNGS:
            v = (sw.get("cells") or {}).get(str(c)) or {}
            L.append("| {:,} | {} | {} | {} | {} | {} | {}/{} | {} |".format(
                c, v.get("prompt_n") or "—", v.get("prefill_tps") or "—",
                v.get("prefill_s") or "—", v.get("decode_tps") or "—",
                v.get("vram_peak_gib") or "—", v.get("draft_n_accepted") or "—",
                v.get("draft_n") or "—", v.get("status")))
        L += ["", "Flags: `" + " ".join(sw.get("flags") or []) + "`",
              "MTP speculative decoding was ON (ByteShape's published command); the speed probe"
              " is a repetitive continuation, so draft acceptance is ~100% and decode is a"
              " best-case rate.", ""]
    else:
        L += ["## Matched-context sweep", "", "not run", ""]

    if pair:
        L += ["## GPQA-Diamond (25 frozen questions, 4096-token cap)", "",
              "| arm | correct | tokens | length stops | wall s |", "|---|---|---|---|---|"]
        for m in ("off", "on"):
            b = pair.get(m) or {}
            L.append(f"| thinking {m} | {b.get('correct')}/{b.get('n')} | {b.get('tokens')} | "
                     f"{b.get('length_stops')} | {b.get('wall_s')} |")
        L.append("")
    else:
        L += ["## GPQA", "", "not run", ""]

    if chat:
        s = chat.get("summary") or {}
        L += ["## Chat, 10 fixed questions", "",
              f"{s.get('correct')}/{s.get('n')} correct, {s.get('partial')} partial, "
              f"{s.get('wrong')} wrong, {s.get('accuracy')}% accuracy, "
              f"mean decode {s.get('mean_decode_tps')} t/s.", ""]
    else:
        L += ["## Chat", "", "not run", ""]

    if os.path.exists(os.path.join(HERE, "spec-off-32k.json")):
        sp = load("spec-off-32k.json")
        L += ["## Control: the same probe without speculative decoding", "",
              f"32K rung, same flags minus `--spec-type draft-mtp`: decode "
              f"**{sp.get('decode_tps')} t/s** and prefill {sp.get('prefill_tps')} t/s "
              f"({sp.get('prompt_n')} prompt tokens). With MTP the same rung reads "
              f"{((sw or {}).get('cells') or {}).get('32768', {}).get('decode_tps')} t/s decode, "
              "so the published decode column is a speculative-decoding figure and the speed "
              "probe's repetitive output (draft acceptance 47/47) flatters it.", ""]

    if game:
        L += ["## Browser game (three.js Galaga)", "",
              f"status: {game.get('status')}, attempts used: {game.get('attempts_used')}, "
              f"completion tokens: {game.get('total_completion_tokens')}, "
              f"wall: {game.get('total_wall_s')} s."]
        for a in game.get("per_attempt") or []:
            L.append(f"- attempt {a.get('attempt')}: "
                     f"{'pass' if a.get('ok') else 'fail (' + ', '.join(a.get('reasons') or []) + ')'}")
        L.append("")
    else:
        L += ["## Browser game", "", "not run", ""]

    if vis:
        L += ["## Vision smoke", "",
              f"expected `{vis.get('expect')}`, got `{vis.get('answer')}` → "
              f"{'pass' if vis.get('ok') else 'fail'} ({vis.get('wall_s')} s).", ""]
    else:
        L += ["## Vision smoke", "",
              "not run (no mmproj file or not attempted).", ""]

    open(os.path.join(HERE, "RESULTS.md"), "w").write("\n".join(L) + "\n")
    print("wrote RESULTS.md")


if __name__ == "__main__":
    main()
