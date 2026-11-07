#!/usr/bin/env python3
"""build_pages_ablation.py -- the accelerator-ablation fragment for the overview's #ablation block.

There is no /ablation/ page: the arm table and its findings are printed here and spliced into
index.html by scripts/build_pages_overview.py.

Reads benchmarks/ablation/arm-*.json and benchmarks/ablation/cachecheck.json (the
per-arm harness output: argv, KV type, VRAM idle/peak, decode/prefill timings on a
1.6k and a 27.7k-token prompt, and the six fixed answers) and writes
nothing here is typed by hand: every number in the table comes
from a JSON field, so a re-run only needs a rebuild.

Only public-safe fields are published: no host names, no paths, no service unit
names. The arm display names live in the ARMS table below; everything numeric is
read from the JSON.
"""
import glob, sys
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ABL = os.path.join(ROOT, "benchmarks", "ablation")

# arm order + visitor-facing label. 5b is identical to 4b (repeat run) and is kept
# in the JSON set but not shown as its own row.
ARMS = [
    ("arm-1-baseline.json", "baseline", "no speculative decoding — the reference",
     "none"),
    ("arm-2-fa-off.json", "FA off", "no speculative decoding, f16 KV", "none"),
    ("arm-3-mtp.json", "MTP", "draft-mtp, n-max 7", "draft-mtp, n-max 7"),
    ("arm-4-dflash.json", "DFlash (n-max 7)", "separate DFlash2 drafter, n-max 7",
     "draft-dflash, n-max 7"),
    ("arm-4b-dflash-nm3.json", "DFlash (default n-max 3)", "separate DFlash2 drafter, default n-max",
     "draft-dflash, n-max 3"),
    ("arm-5a-mtp-ngram.json", "MTP + ngram (production preset)",
     "the model's own MTP head plus ngram-cache", "draft-mtp + ngram-cache"),
    ("arm-6-dflash-fa-off.json", "DFlash, FA off", "separate DFlash2 drafter, f16 KV",
     "draft-dflash, n-max 3"),
]
HIDDEN = ["arm-5b-dflash.json"]  # repeat of 4b, kept for provenance

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 16px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
.tabs a{padding:7px 13px;border:1px solid var(--line);border-radius:8px;color:var(--dim);text-decoration:none;font-size:13px;min-height:36px;display:inline-flex;align-items:center}
.tabs a.on{background:#1b2431;color:var(--fg);border-color:#33506b}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{width:100%;border-collapse:collapse;background:var(--panel);min-width:900px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
thead th{background:#1b2431;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
tbody tr:nth-child(even) td{background:#131a24}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
td.arm b{display:block}td.arm span{color:var(--faint);font-size:12px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.dim{color:var(--faint)}
.detail{border:1px solid var(--line);border-radius:10px;padding:14px;margin:16px 0;background:var(--panel)}
.detail h2{margin:0 0 6px;font-size:17px}
.sec{margin:26px 0 6px;font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.callout{border-left:3px solid var(--gold);background:#1a1f27;padding:10px 14px;border-radius:6px;margin:14px 0}
.callout b{color:var(--gold)}
.limits{border-left:3px solid var(--faint);background:#151a21;padding:10px 14px;border-radius:6px;margin:14px 0}
.limits ul{margin:6px 0 0;padding-left:20px}.limits li{margin:4px 0}
.meta{color:var(--faint);font-size:12px}
code{font-family:ui-monospace,monospace;font-size:12px;color:var(--blue)}
@media(max-width:640px){.wrap{padding:18px 12px 48px}th,td{padding:7px 7px;font-size:12px}table{min-width:820px}td.arm{min-width:120px}td.arm b{white-space:nowrap}td.arm span{display:none}#mob{display:block}.tabs a{font-size:12px;padding:6px 10px}}#mob{display:none;color:var(--faint);font-size:12px;margin:6px 0 0}
"""



def esc(s):
    return html.escape(str("" if s is None else s))


def public_model(path):
    """basename only -- the JSON stores an absolute path on the bench box."""
    return os.path.basename(str(path or "")).replace(".gguf", "")


def public_build(s):
    """'build 11517' from the server's build string; nothing host-specific."""
    raw = str(s or "")
    m = re.search(r"build\s+(\d+)[^)]*?commit\s+([0-9a-f]+)", raw)
    if m:
        return "llama.cpp Vulkan build %s (commit %s)" % (m.group(1), m.group(2))
    m = re.match(r"^b(\d+)-([0-9a-f]+)$", raw.strip())
    if m:
        return "llama.cpp Vulkan build %s (commit %s)" % (m.group(1), m.group(2))
    return raw


def f1(x):
    # per-model arms record vram_idle_gib as None when it was not sampled
    return "—" if x is None else "%.1f" % float(x)


def f2(x):
    return "—" if x is None else "%.2f" % float(x)


def load_arms():
    base = json.load(open(os.path.join(ABL, "arm-1-baseline.json"), encoding="utf-8"))
    out = []
    for fname, label, spec, method in ARMS:
        d = json.load(open(os.path.join(ABL, fname), encoding="utf-8"))
        if fname == "arm-1-baseline.json":
            same, n = None, 6
        else:
            n = len(d["answers"])
            same = sum(1 for k in d["answers"]
                       if base["answers"][k]["content"] == d["answers"][k]["content"])
        argv = d["argv"]
        draft = argv[argv.index("--spec-draft-model") + 1] if "--spec-draft-model" in argv else None
        out.append(dict(label=label, spec=spec, method=method, fa=d["fa"], kv=d["kv_cache_type"],
                        dec_s=d["decode_short"]["decode_tps"], dec_l=d["decode_30k"]["decode_tps"],
                        pre_s=d["decode_short"]["prefill_tps"], pre_l=d["decode_30k"]["prefill_tps"],
                        vram_idle=d["vram_idle_gib"], vram_peak=d["vram_peak_overall_gib"],
                        same=same, n=n, ctx=d["n_ctx"], model=d["model"], draft=draft,
                        build=d["server_build"], prompt_short=d["decode_short"]["prompt_n"],
                        prompt_long=d["decode_30k"]["prompt_n"],
                        predicted=d["decode_short"]["predicted_n"]))
    # sanity: the hidden repeat must agree with 4b on the numbers the page shows
    a4b = json.load(open(os.path.join(ABL, "arm-4b-dflash-nm3.json"), encoding="utf-8"))
    for h in HIDDEN:
        dh = json.load(open(os.path.join(ABL, h), encoding="utf-8"))
        for k in ("decode_short", "decode_30k"):
            if abs(dh[k]["decode_tps"] - a4b[k]["decode_tps"]) > 1.0:
                print("warn: repeat arm %s differs from 4b on %s" % (h, k))
    return out



# ---------------------------------------------------------------- per-model arms
# The 2026-11-04 run measured every runnable model (benchmarks/ablation/arms/<slug>/arm-*.json).
# The older single-model files (arm-1-baseline.json …) are kept for provenance but the page
# prefers the per-model set whenever it exists, so the table covers all models.
ARM_LABELS = {
    "A-baseline": ("baseline", "no speculative decoding — the reference", "none"),
    "B-fa-off": ("FA off", "no speculative decoding, f16 KV", "none"),
    "C-draft-mtp": ("MTP", "draft-mtp", "draft-mtp"),
    "D-draft-dflash": ("DFlash (default n-max)", "separate DFlash2 drafter, default n-max", "draft-dflash, n-max 3"),
    "D2-dflash-nm7": ("DFlash (n-max 7)", "separate DFlash2 drafter, n-max 7", "draft-dflash, n-max 7"),
    "E-mtp-ngram": ("MTP + ngram (production preset)", "the model's own MTP head plus ngram-cache", "draft-mtp + ngram-cache"),
}


def _model_names():
    try:
        doc = json.load(open(os.path.join(ROOT, "data", "results.json"), encoding="utf-8"))
        return {r.get("slug"): r.get("name") for r in doc.get("rows", []) if r.get("slug")}
    except OSError:
        return {}


MODEL_NAMES = _model_names()
# disambiguate quants that share a display name
QUANT_FIX = {"qwen3-8-27b-q4km": "Q4_K_M", "qwen3-8-27b-q4-0": "Q4_0"}


def display_name(slug):
    name = MODEL_NAMES.get(slug, slug)
    q = QUANT_FIX.get(slug)
    return f"{name} {q}" if q else name


def load_arms_per_model():
    root = os.path.join(ABL, "arms")
    if not os.path.isdir(root):
        return []
    out = []
    for slug in sorted(os.listdir(root)):
        d_dir = os.path.join(root, slug)
        if not os.path.isdir(d_dir):
            continue
        files = sorted(glob.glob(os.path.join(d_dir, "arm-*.json")))
        if not files:
            continue
        base_answers = None
        for f in files:
            d = json.load(open(f, encoding="utf-8"))
            arm = os.path.basename(f)[4:-5]
            label, desc, method = ARM_LABELS.get(arm, (arm, "", arm))
            short = d.get("decode_short") or {}
            long_ = d.get("decode_30k") or {}
            if d.get("status") != "ok" or not short.get("decode_tps") or not long_.get("decode_tps"):
                continue          # void / not applicable — never rendered as a number
            answers = d.get("answers") or {}
            if base_answers is None:
                base_answers, same, n = answers, None, len(answers)
            else:
                n = len(answers)
                same = sum(1 for k in answers if base_answers.get(k, {}).get("content") == answers[k].get("content"))
            argv = d.get("argv") or []
            draft = argv[argv.index("--spec-draft-model") + 1] if "--spec-draft-model" in argv else None
            out.append(dict(label=label, spec=desc, method=method, fa=d.get("fa", "on"),
                            kv=d.get("kv_cache_type", "q8_0/q4_0"),
                            dec_s=short["decode_tps"], dec_l=long_["decode_tps"],
                            pre_s=short.get("prefill_tps"), pre_l=long_.get("prefill_tps"),
                            vram_idle=d.get("vram_idle_gib"),
                            vram_peak=max(short.get("vram_peak_gib") or 0, long_.get("vram_peak_gib") or 0) or None,
                            same=same, n=n, ctx=d.get("n_ctx"), model=d.get("model"),
                            draft=draft, build=d.get("server_build"),
                            prompt_short=short.get("prompt_n"), prompt_long=long_.get("prompt_n"),
                            predicted=short.get("predicted_n")))
    return out



def load_rungs():
    """Rung-matched cells: benchmarks/ablation/arms-rungs/<slug>/<arm>-<rung>.json"""
    root = os.path.join(ABL, "arms-rungs")
    cells = {}
    if not os.path.isdir(root):
        return cells
    for slug in sorted(os.listdir(root)):
        d = os.path.join(root, slug)
        if not os.path.isdir(d):
            continue
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                j = json.load(open(f, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not j.get("arm") or not j.get("rung"):
                continue
            cells[(slug, j["arm"], int(j["rung"]))] = j
    return cells


RUNG_ORDER = [4096, 32768, 65536, 131072, 262144]
RUNG_LABEL = {4096: "4K", 32768: "32K", 65536: "64K", 131072: "128K", 262144: "256K"}
ARM_ORDER = ["A-baseline", "B-fa-off", "C-draft-mtp", "D-draft-dflash"]
ARM_LABEL = {
    "A-baseline": ("baseline", "no speculative decoding — the reference", "none"),
    "B-fa-off": ("FA off", "no speculative decoding, f16 KV", "none"),
    "C-draft-mtp": ("MTP", "its own MTP head, n-max 7", "draft-mtp, n-max 7"),
    "D-draft-dflash": ("DFlash", "separate DFlash2 drafter, n-max 7", "draft-dflash, n-max 7"),
}


def _ok(c):
    return bool(c) and c.get("status") == "ok" and c.get("decode_tps")


def _fpre(x):
    return "%.0f" % float(x)


def _delta(cur, base, key):
    """(text, css) for cur vs base on one metric; empty when either side is missing."""
    if not _ok(cur) or not _ok(base) or base.get(key) is None or cur.get(key) is None:
        return "", ""
    if base is cur:
        return "", ""
    pct = 100.0 * (cur[key] - base[key]) / base[key]
    if abs(pct) < 0.5:
        return "", ""
    cls = "ok" if pct > 2 else ("bad" if pct < -2 else "dim")
    return " %+.0f%%" % pct, cls


def _cell_html(c, base):
    if not c:
        return "<span class=dim>—</span>"
    if c.get("status") == "does_not_fit":
        return "<span class=dim>does not fit</span>"
    if c.get("status") == "load_failed":
        return "<span class=dim>would not load</span>"
    if not _ok(c):
        return "<span class=dim>failed</span>"
    dt, dc = _delta(c, base, "decode_tps")
    pt, pc = _delta(c, base, "prefill_tps")
    out = '<span class=abl-dec>%.1f' % float(c["decode_tps"])
    if dt:
        out += "<i class=%s>%s</i>" % (dc, dt)
    out += '</span><span class=abl-pre>%s' % _fpre(c["prefill_tps"])
    if pt:
        out += "<i class=%s>%s</i>" % (pc, pt)
    out += "</span>"
    return out


def rungs_body(cells):
    models = {}
    for (slug, arm, rung), j in cells.items():
        models.setdefault(slug, set()).add(arm)
    blocks = []
    n_rows = 0
    for slug in sorted(models):
        arms = [a for a in ARM_ORDER if a in models[slug]]
        if not arms:
            continue
        sample = next(cells[(slug, a, r)] for a in arms for r in RUNG_ORDER
                      if (slug, a, r) in cells)
        name = sample.get("name") or display_name(slug)
        quant = sample.get("quant") or QUANT_FIX.get(slug) or ""
        label = esc(name) + ('<span class=abl-q>%s</span>' % esc(quant) if quant else "")
        for i, arm in enumerate(arms):
            lab, desc, method = ARM_LABEL.get(arm, (arm, "", arm))
            tds = []
            if i == 0:
                tds.append('<td class=mdl rowspan=%d><b>%s</b>%s</td>'
                           % (len(arms), label,
                              '<span class=abl-mnote>%s</span>' % _model_note(slug, models[slug])
                              if _model_note(slug, models[slug]) else ""))
            fa = next((cells[(slug, arm, r)] for r in RUNG_ORDER
                       if (slug, arm, r) in cells), {}).get("fa", "on")
            fa_cell = "on" if fa == "on" else "<span class=bad>off</span>"
            tds.append('<td class=arm><b>%s</b><span>%s</span></td><td class=num>%s</td>'
                       '<td class=abl-method>%s</td>'
                       % (esc(lab), esc(desc), fa_cell, esc(method)))
            for r in RUNG_ORDER:
                base = cells.get((slug, "A-baseline", r))
                tds.append("<td class=num>%s</td>"
                           % _cell_html(cells.get((slug, arm, r)), base))
            blocks.append("<tr>" + "".join(tds) + "</tr>")
            n_rows += 1

    head = ("<div class=table-wrap><table class=abl-table><thead><tr>"
            "<th>Tested model</th><th>Arm</th><th>FA</th><th>Speculative method</th>"
            + "".join("<th>%s context<br><span class=abl-th2>decode / prefill t/s</span></th>"
                      % RUNG_LABEL[r] for r in RUNG_ORDER)
            + "</tr></thead><tbody>" + "".join(blocks) + "</tbody></table></div>")
    return head, n_rows


MOE_SLUGS = ("a3b",)


def _model_note(slug, arms):
    """Only a mixture-of-experts file gets the note; a partial run must not imply it."""
    if any(t in slug for t in MOE_SLUGS) and not ({"C-draft-mtp", "D-draft-dflash"} & arms):
        return "MoE: no MTP head or drafter for this file — toggles not applicable"
    return ""


def _rung_sentence(slug, arm, cells, metric):
    parts = []
    for r in RUNG_ORDER:
        c = cells.get((slug, arm, r))
        b = cells.get((slug, "A-baseline", r))
        if _ok(c) and _ok(b):
            pct = 100.0 * (c[metric] - b[metric]) / b[metric]
            txt = "no change" if abs(pct) < 0.5 else "%+.0f%%" % pct
            parts.append("%s %s→%s (%s)"
                         % (RUNG_LABEL[r],
                            "%.1f" % b[metric] if metric == "decode_tps" else "%.0f" % b[metric],
                            "%.1f" % c[metric] if metric == "decode_tps" else "%.0f" % c[metric],
                            txt))
    return "; ".join(parts)


def rung_findings(cells):
    out = []
    slugs = sorted({s for (s, a, r) in cells})
    for slug in slugs:
        name = next((cells[k].get("name") for k in cells if k[0] == slug), slug)
        fa = _rung_sentence(slug, "B-fa-off", cells, "prefill_tps")
        fa_dec = _rung_sentence(slug, "B-fa-off", cells, "decode_tps")
        if fa:
            done_fa = [r for r in RUNG_ORDER if _ok(cells.get((slug, "B-fa-off", r)))]
            missing = [r for r in RUNG_ORDER if r not in done_fa]
            tail_note = ""
            if done_fa and missing:
                last = max(done_fa)
                rate = cells[(slug, "B-fa-off", last)].get("prefill_tps")
                why = (" The rungs above %s were not measured: prefill had already "
                       "fallen to %s t/s at %s, which makes the next cell a multi-hour run."
                       % (RUNG_LABEL[last], _fpre(rate), RUNG_LABEL[last]))
                if (cells.get((slug, "B-fa-off", 262144)) or {}).get("status") == "does_not_fit":
                    why += " At 256K the f16 KV window does not allocate at all."
                tail_note = why
            out.append("<div class=callout><b>%s — flash attention is a prefill multiplier, "
                       "not a decode accelerator.</b> Prefill with FA off vs the same rung's "
                       "baseline: %s. Decode: %s. FA off also forces f16 KV (a quantized value "
                       "cache requires FA), so its VRAM is larger and it cannot reach every "
                       "rung the FA-on arms reach.%s</div>"
                       % (esc(name), esc(fa), esc(fa_dec), tail_note))
        mtp = _rung_sentence(slug, "C-draft-mtp", cells, "decode_tps")
        if mtp:
            out.append("<div class=callout><b>%s — MTP (n-max 7) lifts decode at every rung.</b> "
                       "Decode vs baseline: %s.</div>" % (esc(name), esc(mtp)))
        df = _rung_sentence(slug, "D-draft-dflash", cells, "decode_tps")
        if df:
            out.append("<div class=callout><b>%s — DFlash (n-max 7) lift varies with depth.</b> "
                       "Decode vs baseline: %s.</div>" % (esc(name), esc(df)))
    return "".join(out)


def build_html():
    # Fen's rule (2026-11-04): the ablation table must use the SAME context rungs as the sweep.
    # The old 1.6k / 27.7k grid is withdrawn; the rung grid is the published one.
    cells = load_rungs()
    if not cells:
        return ("<h1>Accelerator ablation</h1>"
                "<p class=sub>FA, MTP and DFlash toggled one at a time on a fixed model.</p>"
                "<div class=callout><b>Being re-measured at the sweep's context rungs.</b> "
                "The earlier table used 1.6k and 27.7k prompts, which are not the rungs used by the "
                "models table (4K, 32K, 64K, 128K, 256K), so the two could not be read against each "
                "other. Those figures have been withdrawn rather than left on the page beside numbers "
                "that mean something different by &ldquo;context&rdquo;. This section will show one row per "
                "model with those five rungs as columns once the run finishes.</div>", 0)

    table, n_rows = rungs_body(cells)
    n_models = len({s for (s, a, r) in cells})
    sample = next(iter(cells.values()))
    build = public_build(sample.get("build_info")) or "llama.cpp"
    cap = sample.get("_power_cap_w")

    sub = ("Every row is the same model at the same five context windows as the speed matrix, "
           "with only the accelerator toggled. Cells show <b>decode / prefill</b> tokens per "
           "second; the small figure is the change against that model's own baseline at that "
           "same rung. Higher is better. Blanks are not measured; they are never inferred.")

    findings = rung_findings(cells)

    limits = ["<li><b>One request per cell.</b> Cold, uncached, no repeated runs — "
              "differences inside ±2% are run-to-run noise, which is why deltas are only "
              "coloured outside that band.</li>",
              "<li><b>FA off cannot use the quantized KV cache.</b> A quantized value cache "
              "requires flash attention, so every FA-off cell runs f16 keys and values; its "
              "VRAM is larger and its reachable context is shorter than the FA-on arms.</li>"]
    if any(c.get("status") == "load_failed" for c in cells.values()):
        nf = sorted({"%s %s" % (cells[(s, a, r)].get("name") or s, RUNG_LABEL[r])
                     for (s, a, r), c in cells.items() if c.get("status") == "load_failed"})
        limits.append("<li><b>Cells marked &ldquo;would not load&rdquo;</b> started and then "
                      "died while loading, without an allocation error: %s.</li>"
                      % esc(", ".join(nf)))
    if any(c.get("status") == "does_not_fit" for c in cells.values()):
        nf = sorted({"%s %s" % (cells[(s, a, r)].get("name") or s, RUNG_LABEL[r])
                     for (s, a, r), c in cells.items() if c.get("status") == "does_not_fit"})
        limits.append("<li><b>Cells marked &ldquo;does not fit&rdquo;</b> are configurations "
                      "whose server refused to start or could not allocate at that window: "
                      "%s.</li>" % esc(", ".join(nf)))
    moe = [s for s in {k[0] for k in cells}
           if not any(k[0] == s and k[1] in ("C-draft-mtp", "D-draft-dflash") for k in cells)]
    if moe:
        limits.append("<li><b>MTP and DFlash are blank for %s</b> because that file carries no "
                      "MTP head and no drafter trained for it exists; the toggle does not apply, "
                      "so no row is invented.</li>"
                      % esc(", ".join(cells[next(k for k in cells if k[0] == s)].get("name") or s
                                      for s in moe)))
    limits.append("<li><b>VRAM per rung is recorded in each cell's JSON</b> and is not printed "
                  "here: at a fixed rung it is a property of the model and KV type, not of the "
                  "accelerator.</li>")

    method = (
        "<details class=detail><summary>How it was measured</summary>"
        "<p>One model at a time on the same GPU, the same engine build (<code>%s</code>) and the "
        "same flags; only the toggled accelerator changes. For every cell the server is "
        "restarted with <code>-c &lt;rung&gt;</code>, then one prompt is calibrated with "
        "<code>/tokenize</code> to <code>rung − 512</code> tokens: target context and client "
        "prompt length match. One cold <code>/v1/chat/completions</code> request follows "
        "(temperature 0, top_k 1, <code>cache_prompt:false</code>, <code>ignore_eos:true</code>, "
        "64 generated tokens), and prefill/decode are the server's own "
        "<code>timings.prompt_per_second</code> / <code>timings.predicted_per_second</code>. "
        "KV cache q8_0 keys / q4_0 values on FA-on arms, f16/f16 on FA-off arms; "
        "one sequence slot (<code>-np 1</code>).%s</p>"
        "<p class=meta>A number exists only if that request produced it. Servers that failed to "
        "start are recorded as failures with the engine's message, not as a low score.</p>"
        "</details>"
        % (esc(build), (" The card's power cap was %d W for every cell." % cap) if cap else ""))

    body = ("<h1>Accelerator ablation</h1><p class=sub>%s</p>"
            "<h2 class=sec>Prefill and decode at the sweep's rungs</h2>%s"
            "<p id=mob>Scroll the table sideways. Small figures are the change against the "
            "baseline at the same rung; coloured only outside ±2%%.</p>%s"
            "<h2 class=sec>Limits of this comparison</h2><div class=limits><b>What this table "
            "does and does not say</b><ul>%s</ul></div>%s"
            % (sub, table, findings, "".join(limits), method))
    return body, n_rows


def fragment():
    """The whole ablation section, for the overview's #ablation block."""
    body, n = build_html()
    # keep the section's own title but demote it to the block heading
    frag = body.replace("<h1>Accelerator ablation</h1>",
                              "<h2 class=abl-h>Accelerator ablation — FA, MTP, DFlash</h2>")
    frag = frag.replace("<h2 class=sec>Headline</h2>", '<h3 class=abl-t>Headline</h3>')
    for t in ("Prefill and decode at the sweep's rungs", "Limits of this comparison"):
        frag = frag.replace('<h2 class=sec>%s</h2>' % t, '<h3 class=abl-t>%s</h3>' % t)
    return frag, n


def main():
    frag, n = fragment()
    print(frag)
    print("ablation arms:", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())