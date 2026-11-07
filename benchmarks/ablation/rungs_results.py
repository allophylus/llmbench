#!/usr/bin/env python3
"""rungs_results.py — RESULTS.md for the rung-matched ablation, from the cell JSONs.

Every number is read from benchmarks/ablation/arms-rungs/<slug>/<arm>-<rung>.json.
A cell that did not produce a request result stays blank (or says why), never a guess.
"""
import glob, json, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "arms-rungs")
RUNG_ORDER = [4096, 32768, 65536, 131072, 262144]
LAB = {4096: "4K", 32768: "32K", 65536: "64K", 131072: "128K", 262144: "256K"}
ARMS = ["A-baseline", "B-fa-off", "C-draft-mtp", "D-draft-dflash"]
ARM_LABEL = {"A-baseline": "baseline", "B-fa-off": "FA off (f16 KV)",
             "C-draft-mtp": "MTP n-max 7", "D-draft-dflash": "DFlash n-max 7"}


def load():
    cells = {}
    for f in glob.glob(os.path.join(ROOT, "*", "*.json")):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cells[(j["model"], j["arm"], int(j["rung"]))] = j
    return cells


def cell(c, base):
    if not c:
        return "—"
    if c.get("status") == "does_not_fit":
        return "does not fit"
    if c.get("status") != "ok":
        return c.get("status") or "failed"
    s = "%.1f / %.0f" % (c["decode_tps"], c["prefill_tps"])
    if base and base.get("status") == "ok" and base is not c:
        d = 100.0 * (c["decode_tps"] - base["decode_tps"]) / base["decode_tps"]
        p = 100.0 * (c["prefill_tps"] - base["prefill_tps"]) / base["prefill_tps"]
        fm = lambda x: "no change" if abs(x) < 0.5 else "%+.0f%%" % x
        s += " (%s / %s)" % (fm(d), fm(p))
    return s


def main():
    cells = load()
    models = {}
    for (slug, arm, rung) in cells:
        models.setdefault(slug, set()).add(arm)
    L = ["# Accelerator ablation at the matched context rungs", "",
         "Generated: " + time.strftime("%Y-%m-%d %H:%M %z"), "",
         "Same probe as the matched-context sweep: server restarted with `-c <rung>`, one",
         "prompt calibrated with `/tokenize` to `rung - 512` tokens, ONE cold",
         "`/v1/chat/completions` (temperature 0, `cache_prompt:false`, `ignore_eos`, 64",
         "generated tokens). Cells are **decode t/s / prefill t/s** and, for non-baseline",
         "arms, the change against that model's baseline at the same rung.", "",
         "| model | arm | " + " | ".join(LAB[r] for r in RUNG_ORDER) + " |",
         "|---|---|" + "---|" * len(RUNG_ORDER)]
    for slug in sorted(models):
        arms = [a for a in ARMS if a in models[slug]]
        j0 = next(cells[(slug, a, r)] for a in arms for r in RUNG_ORDER
                  if (slug, a, r) in cells)
        name = "%s (%s)" % (j0.get("name") or slug, j0.get("quant") or "")
        for arm in arms:
            row = [name if arm == arms[0] else "",
                   ARM_LABEL.get(arm, arm)]
            for r in RUNG_ORDER:
                row.append(cell(cells.get((slug, arm, r)),
                                cells.get((slug, "A-baseline", r))))
            L.append("| " + " | ".join(row) + " |")
    L += ["", "Cells marked `does not fit` are configurations whose server refused to "
          "start at that window; they are recorded, not substituted.", "",
          "A dash is a cell that was not run. The FA-off arms stop at 64K on both models:",
          "non-FA prefill had already collapsed there (24 t/s dense, 66 t/s MoE), so the",
          "next rung is a multi-hour cell, and on the dense model the 256K f16 KV window",
          "does not allocate at all.", ""]
    open(os.path.join(ROOT, "RESULTS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("wrote", os.path.join(ROOT, "RESULTS.md"))


if __name__ == "__main__":
    main()
