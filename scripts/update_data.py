#!/usr/bin/env python3
"""update_data.py — regenerate ../data/results.json from the llmbench results dir.

One object per model (merged across its many per-phase SCHEMA-1 records, following the
same grouping rules as the benchmark suite's own merge_rows.py), plus a per-row map of
benchmark videos that actually exist locally (they are hosted on CloudFront, not in this
repo — a link is only emitted when the local file proves the render exists).

Usage (plain stdlib, no deps):
    python3 scripts/update_data.py
    python3 scripts/update_data.py --results-dir /path/to/llmbench/results \
                                   --videos-dir  /path/to/llmbench/site/videos \
                                   --out         data/results.json

Output shape (data/results.json):
{
  "generated": "2026-11-01T21:30:00+08:00",
  "video_base": "https://d1zqwbb1zduc6n.cloudfront.net/llmbench/videos/",
  "rows": [
    {"slug": "...", "name": "...", "params_total": "27B", "params_active": "27B",
     "quant": "Q4_K_M", "arch": "...", "decode_tps": 31.6, "prefill_tps": 962.0,
     "context_window": 131072, "vram_mib": 25166, "date": "2026-10-30",
     "cells": {"gpqa": 64.0, "aime": 53.3, "livebench": 24.0, "ctx30k": 56.0,
               "ctx110k": 44.0, "tau2": 52.6, "shell": 50.0, "termbench": 75.0,
               "ctx_sweep": {...}},
     "videos": {"c0-ppextended": "https://.../videos/<slug>__c0-ppextended.mp4"},
     "sources": ["results/qwen3-8-27b-q4-k-m.json", ...]}
  ]
}

Rules carried over from the suite (see llmbench/merge_rows.py):
  * group key = .gguf basename with its quant suffix stripped -> one row per model+quant;
  * display block  = richest record in the group;
  * each metric    = best-ranked source for that family, never averaged or max-mixed;
  * cells are per-cent (0-100); null means "not measured" and the site renders a dash;
  * nothing is invented: every value comes from a file in --results-dir.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HOME = os.path.expanduser("~")

DEFAULT_RESULTS = os.path.join(HOME, ".openclaw", "workspace", "llmbench", "results")
DEFAULT_VIDEOS = os.path.join(HOME, ".openclaw", "workspace", "llmbench", "site", "videos")
DEFAULT_RAW = os.path.join(HOME, ".openclaw", "workspace", "llmbench")
DEFAULT_OUT = os.path.join(REPO, "data", "results.json")
VIDEO_BASE = "https://d1zqwbb1zduc6n.cloudfront.net/llmbench/videos/"

# ---------------------------------------------------------------- merge rules

_QUANT_RE = re.compile(r"[-_.](i?q\d[\w]*|q\d[\w]*|f16|f32|bf16|fp16|fp8[\w]*|mxfp4)$", re.I)
_PREFIX_RE = re.compile(r"^(rebench_|tune_|c7_|tetris_|radiance_)")


def quant_suffix(name):
    m = _QUANT_RE.search(name or "")
    return m.group(1) if m else None


def group_key(rec):
    mo = rec.get("model") or {}
    f = (mo.get("file") or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = f[:-5] if f.lower().endswith(".gguf") else ""
    if not stem:
        stem = (mo.get("name") or rec.get("slug") or "unknown")
        suf = quant_suffix(stem)
        if suf:
            stem = stem[: stem.rfind(suf)]
    key = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return key or (rec.get("slug") or "unknown").lower()


def norm_kind(rec):
    k = rec.get("kind")
    if k:
        return k
    slug = (rec.get("slug") or "").lower()
    for pre, kind in (("rebench_", "rebench"), ("tune_", "tune"), ("c7_", "power-sweep"),
                      ("tetris_", "tetris"), ("radiance_", "bench")):
        if slug.startswith(pre):
            return kind
    return "bench"


KIND_RANK = {"rebench": 5, "bench": 3, "intel-agentic": 6, "suite": 5, "tune": 2,
             "power-sweep": 1, "tetris": 4}
PP_IDS = ("llama-bench-ppextended", "llama-bench")
TUNE_PP_ID = "c0-ppextended"

# cell name -> ordered (test id, metric key) candidates. `acc` falls back to correct/total.
CELLS = [
    ("gpqa",        [("pub-gpqa25", "acc")]),
    ("aime",        [("pub-aime10x3", "acc"), ("pub-aime30", "acc")]),
    ("livebench",   [("pub-livebench25", "acc")]),
    ("ctx30k",      [("ctx-gpqa30k", "acc")]),
    ("ctx110k",     [("ctx-gpqa110k", "acc")]),
    ("tau2",        [("agent-tau2-telecom20", "acc")]),
    ("shell",       [("agent-shell10", "acc")]),
    ("termbench",   [("agent-termbench8", "acc")]),
    ("mmlupro",     [("pub-mmlupro15", "acc")]),
    ("arc",         [("pub-arc25", "acc")]),
    ("math",        [("pub-math500-20", "acc"), ("synthetic-math20", "acc")]),
    ("logic",       [("synthetic-logic15", "acc")]),
    ("code",        [("synthetic-code15", "acc")]),
    ("tetris_gen",  [("tetris-gen", "acc")]),
    ("tetris_play", [("tetris-play", "acc")]),
]
CTX_SWEEP_ID = "bench-ctx-sweep"


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def _tests(rec):
    return {t.get("id"): t for t in rec.get("tests") or [] if isinstance(t, dict)}


def _cell(t, key):
    if not t or t.get("n_a"):
        return None
    met = t.get("metrics") or {}
    v = _num(met.get(key))
    if v is not None:
        return v
    if key in met and isinstance(met.get(key), (int, float)) and not isinstance(met.get(key), bool):
        return met[key]
    if key.startswith("pp") or key.startswith("tg"):
        return _num(met.get(key + "_tps"))
    if key == "acc":
        v = _num(t.get("acc"))
        if v is not None:
            return v
        c, tot = _num(met.get("correct")), _num(met.get("total"))
        if c is not None and tot:
            return c / tot
        p, tot = _num(met.get("pass")), _num(met.get("total"))
        if p is not None and tot:
            return p / tot
        for alt in ("pass1_acc", "success_rate", "reward"):
            v = _num(met.get(alt))
            if v is not None:
                return v
    return None


def _ranked(recs):
    return sorted(recs, key=lambda r: (-KIND_RANK.get(norm_kind(r), 0), -len(_tests(r))))


def _first(recs, ids, key):
    for r in recs:
        ts = _tests(r)
        for i in ids:
            v = _cell(ts.get(i), key)
            if v is not None:
                return v
    return None


def _richness(rec):
    mo = rec.get("model") or {}
    return (sum(1 for v in mo.values() if v not in (None, "", [], {})),
            len(rec.get("tests") or []), len(json.dumps(rec)))


def _run_date(rec):
    env = rec.get("env") or {}
    for k in ("run_finished", "run_started", "run_at"):
        v = env.get(k)
        if v:
            return str(v)[:10]
    return ""


def _under(path, root):
    try:
        return not os.path.relpath(path, root).startswith("..")
    except ValueError:
        return False


def _pct(v):
    return None if v is None else round(v * 1000) / 10


def _round(v, d=1):
    return None if v is None else round(v, d)


# ---------------------------------------------------------------- videos

def video_index(videos_dir):
    """{slug_prefix: [(filename, cell)]} for every <slug>__<cell>.mp4 present locally."""
    out = {}
    if not videos_dir or not os.path.isdir(videos_dir):
        return out
    for p in sorted(glob.glob(os.path.join(videos_dir, "*.mp4"))):
        b = os.path.basename(p)
        if b.startswith(".") or "__" not in b:
            continue
        slug, cell = b[:-4].split("__", 1)
        out.setdefault(_PREFIX_RE.sub("", slug), []).append((b, cell))
    return out


def videos_for(key, slug, vidx, base):
    """Videos whose slug stem is the row's group key, else a unique prefix match
    (renders of drifted names, e.g. 'ornith-1-5-35b-q4-k-m' vs '...-a3b-q4-k-m')."""
    out = {}
    for st, alt_stem in ((key, None), (slug, None)):
        for vstem, items in vidx.items():
            if vstem == st or (alt_stem and vstem == alt_stem):
                for b, cell in items:
                    out.setdefault(cell, base + b)
        if out:
            break
    if not out:
        cands = [v for v in vidx if v.startswith(key + "-") or key.startswith(v + "-")]
        if len(cands) == 1:
            for b, cell in vidx[cands[0]]:
                out.setdefault(cell, base + b)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- main

def load_records(results_dir):
    recs, skipped = [], []
    for p in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        if os.path.basename(p).endswith(".detail.json"):
            continue
        try:
            r = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            skipped.append((os.path.basename(p), str(e)))
            continue
        if not isinstance(r, dict) or r.get("schema") != 1:
            continue
        r.setdefault("slug", os.path.splitext(os.path.basename(p))[0])
        r["_path"] = p
        r["_src"] = "results/" + os.path.basename(p)
        if not r.get("tests"):
            r["_no_tests"] = True
        recs.append(r)
    return recs, skipped


def build(records, vidx, base=VIDEO_BASE, raw_dir=DEFAULT_RAW):
    groups = {}
    for r in records:
        groups.setdefault(group_key(r), []).append(r)
    rows = []
    for key, recs in sorted(groups.items()):
        measured = [r for r in recs if not r.get("_no_tests")]
        if not measured:
            continue                       # nothing measured -> no row (never invent)
        # identity: richest model block across the group
        mo = {}
        for r in sorted(recs, key=_richness, reverse=True):
            for k, v in (r.get("model") or {}).items():
                if v not in (None, "", [], {}) and not mo.get(k):
                    mo[k] = v
        slug = (mo.get("slug") or "").strip() or key
        name = (mo.get("name") or key).strip()
        q = mo.get("quant") or quant_suffix(name) or ""
        if q:
            name = re.sub(r"[\s_/]" + re.escape(q) + r"$", "", name, flags=re.I)
        # env: prefer a file with the fullest env block from a measured record
        env = {}
        for r in sorted(measured, key=lambda x: _richness(x), reverse=True):
            for k, v in (r.get("env") or {}).items():
                if v not in (None, "", [], {}) and not env.get(k):
                    env[k] = v
        date = max((_run_date(r) for r in measured if _run_date(r)), default="")

        # throughput: llama-bench family > tune c0-ppextended; *_tps metric spelling handled
        pp_src = [r for r in _ranked(measured) if norm_kind(r) in ("rebench", "bench", "tune", "power-sweep")]
        # the prefill/decode numbers in the speed column come from ONE cell, so the
        # recorded flags/build describe both (mixing cells would mislabel one of them)
        prefill = _first(pp_src, PP_IDS, "pp512")
        decode = _first(pp_src, PP_IDS, "tg128")
        _src_rec = next((r for r in pp_src
                         if _cell(_tests(r).get("llama-bench-ppextended"), "pp512") is not None),
                        None)
        if prefill is None:
            prefill = _first(pp_src, (TUNE_PP_ID,), "pp512")
            decode = _first(pp_src, (TUNE_PP_ID,), "tg128")
            _src_rec = next((r for r in pp_src
                             if _cell(_tests(r).get(TUNE_PP_ID), "pp512") is not None), None)

        # live speed probe (results/speed.<slug>.json) overrides bench-cell values when present
        sp = None
        _rd = os.path.dirname(recs[0]["_path"]) if recs and recs[0].get("_path") else None
        if _rd:
            _sp = os.path.join(_rd, "speed.%s.json" % slug)
            if os.path.exists(_sp):
                try:
                    sp = json.load(open(_sp))
                except Exception:
                    sp = None
        if sp:
            if _num(sp.get("prefill_tps")) is not None:
                prefill = _num(sp["prefill_tps"])
            if _num(sp.get("decode_tps")) is not None:
                decode = _num(sp["decode_tps"])

        cells = {}
        for cname, cands in CELLS:
            v = None
            for tid, mk in cands:
                v = _first(_ranked(measured), (tid,), mk)
                if v is not None:
                    break
            cells[cname] = _pct(v)

        sweep = None
        for r in _ranked(measured):
            t = _tests(r).get(CTX_SWEEP_ID)
            if t:
                sweep = t.get("metrics") or None
                break
        if sweep:
            cells["ctx_sweep"] = {k: v for k, v in sweep.items() if _num(v) is not None}

        vram = _num(env.get("peak_vram_mib"))
        # measurement block: the serve shape the throughput numbers were taken under
        row_status = ("done" if any(r.get("status") == "done" for r in recs) else
                      ("partial" if any(r.get("status") == "partial" for r in recs) else "failed"))
        # identity comes from the record that produced THIS row's speed: the top-ranked
        # measured record. Falling through the whole group would lend one record's build
        # and flags to a row measured by a different one.
        _id = _src_rec or (_ranked(measured) or [{}])[0]
        _ienv = _id.get("env") or {}
        _flags = _ienv.get("flags")
        _kv = _ienv.get("kv_cache")
        _build = _ienv.get("llama_build")
        if sp and sp.get("measured_at"):
            _at, _how = sp.get("measured_at"), sp.get("method")
        elif prefill is not None or decode is not None:
            _at, _how = (date or None), "llama-bench / suite cell (pp512 prefill, tg128 decode)"
        else:
            _at, _how = None, None
        # weights gone from the card, or a run that never loaded: say so in the data,
        # so an old number never reads as something the reader could reproduce today
        if not prefill and not decode:
            _meas = "failed — no speed measured" if row_status == "failed" else "no speed probe recorded (accuracy cells still valid)"
        elif not (_flags or _kv or _build):
            # env has no build/flags: this record came from the pre-rebench era, when the
            # weights were on the card. None of those files are here now (INVENTORY), so the
            # card cannot re-run them without a fresh multi-GB download.
            _meas = "not re-measurable on this host (weights deleted; historical numbers)"
        else:
            _meas = None
        import re as _re
        _name = _re.sub(r"\s*\((?:[^)]*prod[^)]*|[^)]*:\d{2,5}[^)]*)\)", "", name or "").strip()
        row = {
            "slug": slug,
            "name": _name or name,
            "params_total": mo.get("params_total") or None,
            "params_active": mo.get("params_active") or None,
            "quant": q or None,
            "arch": mo.get("arch") or None,
            "engine": mo.get("engine") or env.get("backend") or None,
            "decode_tps": _round(decode, 1),
            "prefill_tps": _round(prefill, 0),
            "context_window": (sp or {}).get("context_window") or mo.get("native_ctx") or None,
            "vram_mib": int(vram) if vram else None,
            "size_gb": round(mo["size_bytes"] / 1e9, 1) if mo.get("size_bytes") else None,
            "date": date,
            "cells": cells,
            "videos": videos_for(key, slug, vidx, base),
            "sources": sorted({
                os.path.relpath(r["_path"], raw_dir).replace(os.sep, "/")
                if _under(r["_path"], raw_dir) else r["_src"]
                for r in recs}),
            "speed_measured_at": _at,
            "filename": (sp or {}).get("filename"),
            "features": (sp or {}).get("features") or None,
            "speed_method": _how,
            "speed_flags": _flags,
            "kv_cache": _kv,
            "engine_build": _build,
            "status": row_status,
        }
        if _meas:
            row["measurement_status"] = _meas
        if not row.get("features"):
            hay = " ".join(str(x or "") for x in
                           (row.get("name"), row.get("arch"), row.get("quant"), row.get("slug"))).lower()
            f = {}
            if "mxfp4" in hay:
                f["mxfp4"] = True
            if "dflash2" in hay:
                f["dflash2"] = True
            elif "dflash" in hay:
                f["dflash"] = True
            if "mtp" in hay or "nextn" in hay:
                f["mtp"] = True
            row["features"] = f
        rows.append(row)
    rows.sort(key=lambda r: (r["name"] or "").lower())
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS)
    ap.add_argument("--videos-dir", default=DEFAULT_VIDEOS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--video-base", default=VIDEO_BASE)
    ap.add_argument("--raw-out", default=None,
                    help="also copy the raw SCHEMA-1 records into this dir (e.g. raw/)")
    ap.add_argument("--raw-dir", default=DEFAULT_RAW,
                    help="source tree the traceability links raw/... are relative to")
    a = ap.parse_args()
    if not os.path.isdir(a.results_dir):
        sys.exit("results dir not found: %s" % a.results_dir)
    recs, skipped = load_records(a.results_dir)
    rows = build(recs, video_index(a.videos_dir), a.video_base, a.raw_dir)

    # merge game-creation stats (attempts, tokens, build time) from the games cells
    _gdir = os.environ.get("GAMES_DIR", os.path.join(REPO, "games"))
    for r in rows:
        _gp = os.path.join(_gdir, r["slug"], "build.json")
        if not os.path.exists(_gp):
            continue
        try:
            b = json.load(open(_gp))
        except Exception:
            continue
        att = b.get("attempts") or b.get("attempts_used")
        if att is None and b.get("per_attempt"):
            att = len(b["per_attempt"])
        tok = (b.get("total_prompt_tokens") or 0) + (b.get("total_completion_tokens") or 0)
        r["game"] = {
            "attempts": att,
            "retries": b.get("retries", (att - 1) if isinstance(att, int) and att else None),
            "tokens": tok or None,
            "build_s": b.get("total_wall_s"),
            "url": "games/%s/" % r["slug"],
        }
        _rp = os.path.join(_gdir, r["slug"], "robot_metrics.json")
        if os.path.exists(_rp):
            try:
                r["game"]["robot_score"] = json.load(open(_rp)).get("final_score")
            except Exception:
                pass

    if a.raw_out:
        os.makedirs(a.raw_out, exist_ok=True)
        for r in recs:
            dst = os.path.join(a.raw_out, os.path.basename(r.pop("_path")))
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=1)
        print("copied %d raw record(s) to %s" % (len(recs), a.raw_out))
    doc = {
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "video_base": a.video_base,
        "rows": rows,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    # same dataset as a classic script, so index.html still works when opened from file://
    js_path = os.path.splitext(a.out)[0] + ".js"
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("// generated by scripts/update_data.py -- do not hand-edit\n")
        f.write("window.LLMBENCH_DATA = " + json.dumps(doc, ensure_ascii=False) + ";\n")
    nvid = sum(len(r["videos"]) for r in rows)
    print("wrote %s: %d records -> %d rows, %d video links" % (a.out, len(recs), len(rows), nvid))
    if skipped:
        print("skipped %d unparseable file(s): %s" % (len(skipped), ", ".join(s for s, _ in skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
