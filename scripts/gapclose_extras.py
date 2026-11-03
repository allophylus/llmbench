#!/usr/bin/env python3
"""gapclose_extras.py -- publish the 2026-11-03 gap-close campaign on top of a3b_extras.py.

Sources (all committed in this repo, never the GPU host):
  benchmarks/gapclose/*x3.json            repeated standard-30K probes -> error bars
  benchmarks/gapclose/qwen38-27b-decode-note.json  real decode via /completion ignore_eos
  data/chat/*.json                        the 10-question chat suite (7 models, one legacy)

Writes into data/results.json:
  doc["error_bars"]   {a3b_32k: {prefill: {...}, decode: {...}, wall_s, ...}, ...}
  doc["chat"]         {suite: ..., saturated: true, models: [...]}

Idempotent: both blocks are replaced wholesale on every run.
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GC = os.path.join(ROOT, "benchmarks", "gapclose")
CHAT = os.path.join(ROOT, "data", "chat")


def _sum(d, n_ctx, note=None):
    s = d["summary"]
    out = {
        "n_ctx": n_ctx,
        "prompt_tokens": d["runs"][0]["prompt_n"],
        "calibrated_tokens": d.get("tokens_calibrated"),
        "measured_at": d.get("when"),
        "n": s["prefill_tps"]["n"],
        "prefill": {k: s["prefill_tps"][k] for k in ("mean", "min", "max", "spread_pct")},
        "decode": {k: s["decode_tps"][k] for k in ("mean", "min", "max", "spread_pct")},
        "wall_s": {k: s["wall_s"][k] for k in ("mean", "min", "max", "spread_pct")},
    }
    if note:
        out["note"] = note
    return out


def error_bars():
    a32 = json.load(open(os.path.join(GC, "a3b-ctx32k-x3.json")))
    a256 = json.load(open(os.path.join(GC, "a3b-ctx256k-x3.json")))
    q27 = json.load(open(os.path.join(GC, "qwen38-27b-ctx32k-x3.json")))
    qnote = json.load(open(os.path.join(GC, "qwen38-27b-decode-note.json")))
    q27_decode = {
        "mean": qnote["decode_tps_valid"],
        "n": 1,
        "spread_pct": None,
        "min": qnote["decode_tps_valid"],
        "max": qnote["decode_tps_valid"],
        "method": qnote["method"],
        "note": "1 valid rep; reps 2-3 hung on /completion. Chat-probe 'decode' (25.9 at "
                "predicted_n=2) is EOS noise, not a decode measurement.",
    }
    # the sum of every spread that is a real measurement (never the 2-token chat figure)
    spreads = [a32["summary"]["prefill_tps"]["spread_pct"],
               a32["summary"]["decode_tps"]["spread_pct"],
               a32["summary"]["wall_s"]["spread_pct"],
               a256["summary"]["prefill_tps"]["spread_pct"],
               a256["summary"]["decode_tps"]["spread_pct"],
               a256["summary"]["wall_s"]["spread_pct"],
               q27["summary"]["prefill_tps"]["spread_pct"],
               q27["summary"]["wall_s"]["spread_pct"]]
    return {
        "measured_at": "2026-11-03",
        "policy": "3 cold reps per point (temp 0, cache_prompt false, calibrated 29,953-token prompt); "
                  "spread = (max-min)/mean over those reps",
        "all_under_5pct": all(x < 5.0 for x in spreads),
        "max_spread_pct": max(spreads),
        "a3b_32k": _sum(a32, 32768),
        "a3b_256k": _sum(a256, 262144),
        "qwen38_27b_32k": dict(_sum(q27, 131072, note="server window 131072; prompt 29,965 tokens"),
                               decode=q27_decode),
    }


def chat():
    files = sorted(glob.glob(os.path.join(CHAT, "*.json")))
    models = []
    for p in files:
        d = json.load(open(p))
        qs = d.get("questions") or []
        if not qs:
            continue
        corr = sum(1 for q in qs if q.get("verdict") == "correct")
        part = sum(1 for q in qs if q.get("verdict") == "partial")
        wrong = len(qs) - corr - part
        tps = [q.get("decode_tps") for q in qs if isinstance(q.get("decode_tps"), (int, float))]
        mean_tps = round(sum(tps) / len(tps), 1) if tps else None
        models.append({
            "slug": d.get("model"),
            "n": len(qs),
            "correct": corr,
            "partial": part,
            "wrong": wrong,
            "accuracy": round(100.0 * corr / len(qs), 1),
            "decode_tps": mean_tps,
            "decode_tps_kind": "mean of per-question server decode rates (short answers, includes warm-up)",
            "median_decode_tps": round(sorted(tps)[len(tps) // 2], 1) if tps else None,
            "total_tokens": sum(q.get("tokens") or 0 for q in qs),
            "wall_s": (d.get("summary") or {}).get("wall_s"),
            "ran_at": d.get("ran_at"),
            "source": "data/chat/" + os.path.basename(p),
        })
    # quality is not what this suite can order (it is saturated); publish by speed
    models.sort(key=lambda m: -(m["decode_tps"] or 0))
    for m in models:
        m["decode_tps_median"] = m.pop("median_decode_tps")
    # an older one-off file (a legacy 8/10 run, different prompts/pipeline) is not part of
    # the campaign suite; keep it out of the 7-model set rather than let it look like a loser
    campaign = [m for m in models if m["slug"] != "27b"]
    scores = sorted(set(m["accuracy"] for m in campaign))
    return {
        "suite": "10 fixed general-knowledge questions, temperature 0, thinking off, "
                 "scored strictly (correct / partial / wrong) against a fixed expected answer",
        "measured_at": models[0]["ran_at"] if models else None,
        "n_models": len(campaign),
        "saturated": len(campaign) >= 3 and len(scores) == 1,
        "excluded": [{"slug": m["slug"], "reason": "legacy single run (older prompt set and "
                      "pipeline, not re-run on this suite)", "accuracy": m["accuracy"]}
                     for m in models if m["slug"] == "27b"],
        "statement": "Every model measured scores %.1f%% (%d/%d correct plus 1 partial). "
                     "The suite is SATURATED and cannot discriminate between these models — "
                     "the order below is by decode speed, not by quality."
                     % (campaign[0]["accuracy"], campaign[0]["correct"], campaign[0]["n"])
                     if campaign else "",
        "models": campaign,
    }


def main():
    p = os.path.join(ROOT, "data", "results.json")
    doc = json.load(open(p))
    doc["error_bars"] = error_bars()
    doc["chat"] = chat()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    js = os.path.splitext(p)[0] + ".js"
    with open(js, "w", encoding="utf-8") as f:
        f.write("// generated by scripts/update_data.py -- do not hand-edit\n")
        f.write("window.LLMBENCH_DATA = " + json.dumps(doc, ensure_ascii=False) + ";\n")
    eb = doc["error_bars"]
    print("gapclose_extras: error bars max spread %.2f%% (all<5%%: %s), chat %d models saturated=%s"
          % (eb["max_spread_pct"], eb["all_under_5pct"], len(doc["chat"]["models"]),
             doc["chat"]["saturated"]))


if __name__ == "__main__":
    main()
