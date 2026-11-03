#!/usr/bin/env python3
"""a3b_extras.py -- add the per-context speed rows and the thinking on/off blocks
to data/results.json (the file scripts/update_data.py writes).

It reads the staged SCHEMA-1 records committed next to the measurements
(benchmarks/a3b-260k/records, benchmarks/a3b-thinking/records), appends the extra
rows to `rows`, and adds a `thinking` block to the A3B row. Idempotent: any
previous version of these rows is replaced, never duplicated.

Row contract added here (everything else follows data/results.json):
  row.ctx_label      short server-context label shown in the table (e.g. "256K")
  row.speed          {standard: {prefill_tps, decode_tps, tokens, pending},
                      deep: [{tokens, prefill_tps, decode_tps, ...}], vram_gib}
  row.thinking       {model, caps: [{cap, off:{...}, on:{...}}]}

Usage: python3 scripts/a3b_extras.py [--data data/results.json]
"""
import argparse
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A3B_SLUG = "qwen3-6-35b-a3b-ud-q4km"
SPEED_GLOB = os.path.join(ROOT, "benchmarks", "a3b-260k", "records", "*.json")
THINK_GLOB = os.path.join(ROOT, "benchmarks", "a3b-thinking", "records", "*.json")


def _ctx_label(ctx):
    if ctx >= 1024 * 1024:
        return "%dM" % round(ctx / (1024 * 1024))
    return "%dK" % round(ctx / 1024)


def _base_row(rec):
    """Minimal row for one (model, server ctx) speed record."""
    mo = rec.get("model") or {}
    env = rec.get("env") or {}
    tests = {t.get("id"): t.get("metrics") or {} for t in rec.get("tests") or []}
    std = tests.get("speed-standard-30k") or {}
    deep = [m for t in rec.get("tests") or [] for tid, m in [(t.get("id"), t.get("metrics") or {})]
            if tid.startswith("ctx-")]
    deep.sort(key=lambda m: m.get("prompt_tokens") or 0)
    ctx = mo.get("native_ctx")
    vram = env.get("peak_vram_mib")
    row = {
        "slug": rec["slug"],
        "name": mo.get("name"),
        "params_total": mo.get("params_total"),
        "params_active": mo.get("params_active"),
        "quant": mo.get("quant"),
        "arch": mo.get("arch"),
        "engine": mo.get("engine"),
        "decode_tps": deep[-1].get("decode_tps") if deep else std.get("tg128_tps"),
        "prefill_tps": deep[-1].get("prefill_tps") if deep else std.get("pp512_tps"),
        "context_window": ctx,
        "vram_mib": vram,
        "size_gb": None,
        "date": env.get("run_finished"),
        "cells": {},
        "videos": {},
        "sources": [os.path.relpath(
            os.path.join(ROOT, "benchmarks", "a3b-260k", "records", rec["slug"] + ".json"),
            ROOT).replace(os.sep, "/")],
        "features": {},
        "status": rec.get("status", "done"),
        "ctx_label": _ctx_label(ctx) if ctx else None,
        "speed": {
            "standard": ({
                "tokens": std.get("prompt_tokens"),
                "prefill_tps": std.get("pp512_tps"),
                "decode_tps": std.get("tg128_tps"),
                "pending": False,
            } if std else {"pending": True}),
            "deep": [{
                "tokens": d.get("prompt_tokens"),
                "prefill_tps": d.get("prefill_tps"),
                "decode_tps": d.get("decode_tps"),
                "wall_s": d.get("wall_s"),
            } for d in deep],
            "vram_gib": round(vram / 1024.0, 2) if vram else None,
        },
    }
    # deep probes that are not the deepest are kept too, so the page can show the rungs
    deep_all = [x for x in deep]
    row["speed"]["deep"] = [{
        "tokens": d.get("prompt_tokens"),
        "prefill_tps": d.get("prefill_tps"),
        "decode_tps": d.get("decode_tps"),
        "wall_s": d.get("wall_s"),
    } for d in deep_all]
    return row


def speed_rows():
    out = []
    for p in sorted(glob.glob(SPEED_GLOB)):
        rec = json.load(open(p, encoding="utf-8"))
        # one row per (model, server ctx): a duplicate server ctx is a bug, drop the later
        row = _base_row(rec)
        if any(r["slug"] == row["slug"] for r in out):
            continue
        out.append(row)
    return out


def thinking_block():
    """{model label: {"caps": [{cap, off:{correct,n,tokens,wall_s,length_stops}, on:{...}}],
                       "per_question": {cap: [{id, off, on}, ...]}}}"""
    recs = {}
    for p in sorted(glob.glob(THINK_GLOB)):
        rec = json.load(open(p, encoding="utf-8"))
        recs[rec["slug"]] = rec
    if not recs:
        return None
    caps = {}
    for slug, rec in recs.items():
        mode = "on" if slug.endswith("think1") else "off"
        for t in rec.get("tests") or []:
            m = t.get("metrics") or {}
            cap = m.get("max_tokens")
            if cap is None:
                continue
            caps.setdefault(cap, {})[mode] = {
                "correct": m.get("correct"),
                "n": m.get("total"),
                "tokens": m.get("completion_tokens"),
                "wall_s": m.get("wall_s"),
                "length_stops": m.get("length_stops"),
            }
    caps_rows = []
    for cap in sorted(caps, reverse=True):
        e = caps[cap]
        if "off" not in e or "on" not in e:
            continue
        caps_rows.append({"cap": cap, "off": e["off"], "on": e["on"]})
    if not caps_rows:
        return None
    # per-question comparison, from the pair files (same question order in both modes)
    per_q = []
    for cap in sorted(caps, reverse=True):
        pair = os.path.join(ROOT, "benchmarks", "a3b-thinking", "pair-cap%d.json" % cap)
        if not os.path.exists(pair):
            continue
        d = json.load(open(pair, encoding="utf-8"))
        q = []
        for o, n in zip(d["off"]["rows"], d["on"]["rows"]):
            q.append({"id": o["id"], "off": bool(o["correct"]), "on": bool(n["correct"]),
                      "off_tok": o["completion_tokens"], "on_tok": n["completion_tokens"]})
        per_q.append({"cap": cap, "questions": q})
    return {"model": "Qwen3.6-35B-A3B", "caps": caps_rows, "per_question": per_q}


GAME_TITLE = {"galaga": "galaga-3d", "gta": "gta-3d", "physics": "physics-3d",
              "solar": "solar-system"}


def games_for(slug):
    """Browser-game cells recorded for this model, from games/<slug>-<game>/build.json."""
    out = []
    for d in sorted(glob.glob(os.path.join(ROOT, "games", slug + "-*"))):
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "index.html")):
            continue
        game = os.path.basename(d)[len(slug) + 1:]
        try:
            b = json.load(open(os.path.join(d, "build.json"), encoding="utf-8"))
        except Exception:
            b = {}
        rep = b.get("repair") or {}
        gen_tok = b.get("total_completion_tokens")
        if gen_tok is not None and rep.get("repair_tokens") is not None:
            gen_tok -= rep["repair_tokens"]
        gen_wall = b.get("total_wall_s")
        if gen_wall is not None and rep.get("repair_wall_s") is not None:
            gen_wall -= rep["repair_wall_s"]
        turns = rep.get("turns_used") or len(rep.get("turns") or []) or None
        rep_tok = rep.get("repair_tokens")
        accepted = bool(b.get("accepted_attempt")) or rep.get("status") == "accepted"
        vids = sorted(glob.glob(os.path.join(d, "video", "*.webm")))
        out.append({
            "game": GAME_TITLE.get(game, game),
            "attempts": b.get("attempts_used") or b.get("attempts"),
            "tokens": gen_tok,
            "wall_s": round(gen_wall, 1) if gen_wall is not None else None,
            "repair_turns": turns,
            "repair_status": rep.get("status"),
            "repair_tokens": rep_tok,
            "repair_wall_s": rep.get("repair_wall_s"),
            "extra_attempts": turns if rep_tok is not None else None,
            "extra_tokens": rep_tok,
            "outcome": "pass" if accepted else ("fail" if (b or rep) else "in progress"),
            "shot": "shot.png" if os.path.exists(os.path.join(d, "shot.png")) else None,
            "video": ("video/" + os.path.basename(vids[0])) if vids else None,
            "robot_score": ((b.get("playtest") or {}).get("game_after_input") or {}).get("score"),
            "url": "games/%s/index.html" % os.path.basename(d),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "results.json"))
    a = ap.parse_args()
    doc = json.load(open(a.data, encoding="utf-8"))
    rows = doc.get("rows") or []

    extra = speed_rows()
    extra_slugs = {r["slug"] for r in extra}
    # replace any earlier copy of these rows; keep every other row untouched
    rows = [r for r in rows if r.get("slug") not in extra_slugs
            and not (r.get("slug") or "").startswith(A3B_SLUG + "-ctx")]
    rows.extend(extra)

    tb = thinking_block()
    for r in rows:
        slug = r.get("slug") or ""
        if not slug.startswith(A3B_SLUG):
            r.pop("thinking", None)
            r.pop("games", None)
            continue
        if tb:
            r["thinking"] = tb
            r["thinking_from"] = "GPQA-diamond, 25 frozen questions"
        g = games_for(slug)
        if g:
            r["games"] = g
        else:
            r.pop("games", None)

    # the multi-context rows right after the model they belong to
    base_i = next((i for i, r in enumerate(rows) if r.get("slug") == A3B_SLUG), None)
    if base_i is not None:
        base = rows.pop(base_i)
        extra = [base] + [r for r in rows if r.get("slug") in extra_slugs]
        rows = [r for r in rows if r.get("slug") not in extra_slugs]
        pos = next((i for i, r in enumerate(rows)
                    if (r.get("name") or "").lower() > (base.get("name") or "").lower()), len(rows))
        rows[pos:pos] = extra

    doc["rows"] = rows
    with open(a.data, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    js_path = os.path.splitext(a.data)[0] + ".js"
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("// generated by scripts/update_data.py -- do not hand-edit\n")
        f.write("window.LLMBENCH_DATA = " + json.dumps(doc, ensure_ascii=False) + ";\n")
    print("a3b_extras: %d speed row(s), thinking caps %s" %
          (len(extra_slugs), [c["cap"] for c in (tb or {}).get("caps", [])]))


if __name__ == "__main__":
    main()
