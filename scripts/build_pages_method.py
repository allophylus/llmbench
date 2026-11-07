#!/usr/bin/env python3
"""build_pages_method.py -- the methodology fragment that the overview publishes at #method.

There is no /method/ page: the text, the model set, the error bars and the raw-download links
are printed here and spliced into index.html by scripts/build_pages_overview.py.

Nothing here is hand-written HTML: the model list, the prompt sizes, the error-bar points and
the chat counts are read from data/results.json and the benchmark protocol (docs/BENCHMARK.md)
is summarised into fixed sections. Re-run after any data refresh:

    python3 scripts/update_data.py && python3 scripts/a3b_extras.py \
      && python3 scripts/gapclose_extras.py && python3 scripts/build_pages_overview.py

Visitor-facing text only: no hostnames, no IPs, no local paths, no internal model symlinks.
"""
import glob
import sys
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:16px;margin:30px 0 8px;color:var(--fg)}h2::before{content:"§ ";color:var(--faint)}
.sub{color:var(--dim);margin:0 0 16px;max-width:80ch}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}
.tabs a{padding:6px 12px;border:1px solid var(--line);border-radius:8px;color:var(--dim);text-decoration:none;font-size:13px}
.tabs a.on{background:#1b2431;color:var(--fg);border-color:#33506b}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:8px 0 14px}
table{width:100%;min-width:560px;border-collapse:collapse;background:var(--panel)}
/* the method page embeds the real stylesheet (for the sticky bar), so its own tables are
   pinned against style.css's <=760px card rules — otherwise every table cell becomes a block */
.method-tbl table,.method-tbl thead,.method-tbl tbody,.method-tbl tr{display:revert}
.method-tbl table{display:table;table-layout:auto}
.method-tbl thead{display:table-header-group}.method-tbl tbody{display:table-row-group}
.method-tbl tr{display:table-row}
.method-tbl th,.method-tbl td{display:table-cell;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left;font-size:13px}
.method-tbl td.num,.method-tbl td.mode{white-space:nowrap}
thead th{background:#1b2431;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
code{font:12px/1.45 ui-monospace,monospace;color:var(--fg);background:#111821;padding:1px 4px;border-radius:4px}
p,li{color:var(--dim);max-width:88ch}
ul{padding-left:1.2rem}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;border:1px solid var(--line);font-size:11px;color:var(--dim)}
.note{border:1px solid var(--line);border-left:3px solid #1f6b4c;background:var(--panel);border-radius:8px;padding:.7rem .9rem;margin:10px 0}
.dl{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.dl a{border:1px solid var(--line);border-radius:8px;padding:6px 11px;color:var(--blue);text-decoration:none;font:12.5px ui-monospace,monospace}
.dl a:hover{border-color:var(--blue)}
h3.rawh{font-size:14px;margin:20px 0 6px;color:var(--fg)}
@media(max-width:640px){.wrap{padding:20px 12px 48px}h1{font-size:20px}
.method-tbl table{min-width:0;font-size:12px}
.method-tbl th,.method-tbl td{display:table-cell;padding:6px 6px;font-size:12px;overflow-wrap:anywhere}
td.num{word-break:keep-all}}
"""


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def load():
    p = os.path.join(ROOT, "data", "results.json")
    return json.load(open(p, encoding="utf-8"))


def _model_key(r):
    """one model = its slug with any -ctxNNk suffix removed (A3B is measured at two windows)"""
    import re
    return re.sub(r"-ctx\d+k$", "", r.get("slug") or "")


def models_table(doc):
    rows, seen = [], set()
    by_key = {}
    for r in doc.get("rows", []):
        by_key.setdefault(_model_key(r), []).append(r)
    for r in doc.get("rows", []):
        key = _model_key(r)
        if key in seen:
            continue
        seen.add(key)
        name = r.get("name") or r.get("slug")
        ctxs = sorted({x.get("context_window") for x in by_key[key] if x.get("context_window")})
        rows.append(
            "<tr>"
            f"<td>{esc(name)}</td>"
            f"<td>{esc(r.get('params_total') or '—')}"
            + (f" / {esc(r['params_active'])} active" if r.get("params_active") and
               r.get("params_active") != r.get("params_total") else "") + "</td>"
            f"<td>{esc(r.get('quant') or '—')}</td>"
            f"<td>{esc(r.get('engine') or '—')}</td>"
            f"<td class=num>{', '.join(str(c) for c in ctxs) or '—'}</td>"
            f"<td>{esc(r.get('status') or '')}</td>"
            "</tr>")
    return ('<div class=table-wrap><table><thead><tr><th>Model</th><th>Params</th>'
            '<th>Quant</th><th>Engine</th><th>Context (tokens)</th><th>Status</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def build_ab_table():
    """Build comparison, every number read from benchmarks/ctx-sweep/build-ab.json.

    Two builds of the same engine, same GGUF, same flags, same probe; two cold reps per
    window, interleaved build-by-build so both see the same thermal state. Cells and
    spreads are computed here, never typed.
    """
    p = os.path.join(ROOT, "benchmarks", "ctx-sweep", "build-ab.json")
    try:
        ab = json.load(open(p, encoding="utf-8"))
    except Exception:
        return ""
    cells = ab.get("cells") or []
    if not cells:
        return ""
    rungs = sorted({c.get("ctx") for c in cells if c.get("ctx")})
    builds = []
    for c in cells:
        if c.get("build") not in builds:
            builds.append(c.get("build"))

    def agg(b, ctx, key):
        vals = [c.get(key) for c in cells
                if c.get("build") == b and c.get("ctx") == ctx and c.get(key)]
        if not vals:
            return None, None
        mean = sum(vals) / len(vals)
        spread = (max(vals) - min(vals)) / mean * 100 if len(vals) > 1 and mean else 0.0
        return mean, spread

    gpqa = ab.get("gpqa") or {}
    head = ("<tr><th>Build</th><th>Engine</th>" + "".join(
        f"<th>{esc(f'{r//1024}K')} prefill / decode</th>" for r in rungs)
        + "<th>Peak VRAM</th><th>GPQA-25 (thinking off)</th></tr>")
    rows = []
    for b in builds:
        meta = (ab.get("builds") or {}).get(b) or {}
        tds = []
        for r in rungs:
            pf, sp = agg(b, r, "prefill_tps")
            dc, sd = agg(b, r, "decode_tps")
            if pf is None:
                tds.append("<td class=num>not measured</td>")
            else:
                worst = max([x for x in (sp, sd) if x is not None] or [0])
                tds.append(f"<td class=num>{pf:,.0f} / {dc:,.1f}"
                           + (f" <span class=pill>±{worst:.1f}%</span>" if worst else "")
                           + "</td>")
        vram, _ = agg(b, max(rungs), "vram_peak_gib")
        g = gpqa.get(b) or {}
        gtxt = f"{g.get('correct')}/{g.get('n')}" if g.get("n") else "—"
        rows.append("<tr>" + f"<td><code>{esc(meta.get('tag') or b)}</code></td>"
                    f"<td>{esc(meta.get('engine') or meta.get('note') or '')}</td>"
                    + "".join(tds)
                    + f"<td class=num>{(f'{vram:,.1f} GiB' if vram else '—')}</td>"
                    f"<td class=num>{gtxt}</td></tr>")
    return (
        "<h3>Build A/B</h3>"
        f"<p>Measured {esc(ab.get('when') or '')}: the same model file and identical flags "
        "(<code>" + esc(" ".join(ab.get("flags_std") or [])) + "</code>) on two engine builds, "
        f"{ab.get('reps', 1)} cold repetitions per window, interleaved. The percentage beside "
        "a cell is the spread (max−min)/mean across those repetitions; VRAM is the peak at "
        "the largest window.</p>"
        '<div class=table-wrap><table><thead>' + head + "</thead><tbody>"
        + "".join(rows) + "</tbody></table></div>")


def error_table(doc):
    eb = doc.get("error_bars") or {}
    pts = [("A3B — 32K window", eb.get("a3b_32k")),
           ("A3B — 256K window", eb.get("a3b_256k")),
           ("Qwen3.8-27B — 131K window", eb.get("qwen38_27b_32k"))]
    out = []
    for name, k in pts:
        if not k:
            continue
        d = k.get("decode") or {}
        dec = ("%s (%s)" % (round(d["mean"], 2), ("±%.2f%%" % d["spread_pct"]) if d.get("spread_pct") is not None
                            else "%d rep" % d.get("n", 0)))
        out.append(f"<tr><td>{esc(name)}</td><td class=num>{k['prompt_tokens']:,}</td>"
                   f"<td class=num>{k['prefill']['mean']:.1f} (±{k['prefill']['spread_pct']:.2f}%)</td>"
                   f"<td class=num>{dec}</td>"
                   f"<td class=num>{k['n'] if d.get('n') is None else d.get('n')}</td></tr>")
    return ('<div class=table-wrap><table><thead><tr><th>Point</th><th>Prompt tokens</th>'
            '<th>Prefill t/s (spread)</th><th>Decode t/s (spread)</th><th>Reps</th>'
            "</tr></thead><tbody>" + "".join(out) + "</tbody></table></div>")


def chat_table(doc):
    ch = doc.get("chat") or {}
    out = []
    for m in ch.get("models", []):
        out.append(f"<tr><td>{esc(m['slug'])}</td><td class=num>{m['accuracy']}%</td>"
                   f"<td class=num>{m['correct']}/{m['n']}</td><td class=num>{m['partial']}</td>"
                   f"<td class=num>{m['decode_tps']}</td></tr>")
    return ('<div class=table-wrap><table><thead><tr><th>Model</th><th>Accuracy</th>'
            "<th>Correct</th><th>Partial</th><th>Decode t/s</th></tr></thead><tbody>"
            + "".join(out) + "</tbody></table></div>"), ch


def raw_files_html():
    """The downloadable per-question chat records, one row per model file."""
    LABEL = {
        "qwen3-8-27b-q4km": "Qwen3.8-27B (Q4_K_M)",
        "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B (Q4_K_M)",
        "qwen3-8-27b-q4-0": "Qwen3.8-27B (Q4_0)",
        "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": "NEO-MAX MTP 27B (Q4_K_M)",
        "huihui-abl-q4-k-m": "Huihui abliterated 27B (Q4_K_M)",
        "ornith-1-5-35b-a3b-q4-k-m": "Ornith-1.5-35B-A3B (Q4_K_M)",
        "lfm3-1-7b-q4-k-m": "LFM3-1.7B (Q4_K_M)",
        "27b": "Qwen3.8-27B (early one-off set)",
    }
    rows = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "chat", "*.json"))):
        b = os.path.basename(p)
        slug = b[: -len(".json")]
        try:
            d = json.load(open(p, encoding="utf-8"))
            n = len(d.get("questions") or [])
            think = "thinking on" if d.get("thinking") else "thinking off"
        except Exception:
            n, think = None, "—"
        rows.append('<tr><td><a href="data/chat/%s" download>%s</a></td><td>%s</td><td>%s</td>'
                    '<td class=num>%s</td></tr>'
                    % (esc(b), esc(b), esc(LABEL.get(slug, slug)), "<span class=mode>" + esc(think) + "</span>",
                       "—" if n is None else n))
    return ('<h3 id=raw-files class=rawh>Chat JSONs — one file per model</h3>'
            "<p>Each file holds every question, the expected answer, the model's answer, "
            "the verdict, tokens, milliseconds and decode rate for that run. "
            "Built by <code>scripts/build_pages_method.py</code> from <code>data/chat/</code>.</p>"
            '<div class=\"table-wrap method-tbl\"><table><thead><tr><th>File</th><th>Model</th>'
            "<th>Mode</th><th>Questions</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")

def body_html():
    """The methodology content, headed for H2s, ready to drop into the overview's #method section."""
    doc = load()
    eb = doc.get("error_bars") or {}
    chat_body, ch = chat_table(doc)

    body = "".join([
        "<p class=sub>How every number on this site is produced, and what is deliberately not "
        "measured. Nothing here is inferred: if a request did not produce a value, the cell is blank.</p>",

        "<h2>Model set</h2>",
        "<p>Local open-weight models in GGUF form, quantised so each one fits a single 32&nbsp;GiB "
        "GPU. One model per card at a time; a model's throughput is never measured while another "
        "is loaded.</p>",
        models_table(doc),

        "<h2>Engine and build</h2>",
        "<ul>",
        "<li><strong>Engine:</strong> llama.cpp <code>llama-server</code>: Vulkan backend on an "
        "AMD Radeon AI PRO R9700 (32&nbsp;GiB), and a CUDA (Windows) build on an NVIDIA GeForce "
        "RTX 3090 (24&nbsp;GiB) for the one model measured on that card, whose rows are kept in "
        "their own table. Models run on a different engine (e.g. a "
        "proprietary container format) are labelled with that engine in the table instead.</li>",
        "<li><strong>Builds:</strong> the build id is printed in the <em>Speed evidence</em> column "
        "of each row. Three builds appear: <code>b11517</code>, the mainline server that measured "
        "every early row; <code>b11874</code>, needed for one newer architecture; and "
        "<code>b12110</code> (engine release v0.9.0), used for the <code>gemma4</code> and "
        "<code>nanbeige</code> architectures and, after it matched <code>b11517</code> in the "
        "build A/B below, for the serving configuration. A number is only comparable across "
        "rows measured on the same build.</li>",
        "<li><strong>Flags</strong> (one server at a time, recorded per row): "
        "<code>-ngl 99 -fa on -c &lt;window&gt; --jinja -np 1 -ctk q8_0 -ctv q4_0</code>, plus "
        "<code>-b 16384 -ub 2048</code> on the serving-shaped probes. <code>-np 1</code> means one "
        "sequence slot: no batching, no concurrency.</li>",
        "<li><strong>KV cache types:</strong> keys q8_0, values q4_0 on most suite runs; a few "
        "earlier runs used f16; the <a href=\"#ablation\">ablation block</a> measures what changing the KV type does. "
        "The per-row value is in the evidence column.</li>",
        "<li><strong>Reasoning/thinking</strong> is off unless a tab says otherwise "
        "(<code>enable_thinking:false</code> via the chat template); the thinking tab is the "
        "on/off comparison.</li>",
        "</ul>",
        build_ab_table(),

        "<h2>Throughput: the standard probe</h2>",
        "<ul>",
        "<li><strong>Prompt calibration.</strong> The probe uses a fixed filler document repeated "
        "and then trimmed so that <code>/tokenize</code> reports ~30,000 tokens (calibrated "
        "29,953, actual 29,963–29,965 after templating). The same calibrated prompt is reused at "
        "every server window, so prefill at 32K and at 256K compare like with like.</li>",
        "<li><strong>Cold-probe policy.</strong> Temperature 0, <code>cache_prompt:false</code>, no "
        "warm-up reuse: every measured request pays the full prefill. A discarded warm-up request "
        "runs first when the server needs graph capture.</li>",
        "<li><strong>Decode.</strong> The server's own <code>predicted_per_second</code> over a "
        "64-token generation that ends on the length limit, not on an end-of-answer token. "
        "<code>/completion</code> with <code>ignore_eos</code> is used where a model stops early.</li>",
        "<li><strong>Prefill</strong> is the server's <code>prompt_per_second</code> for the same "
        "request; VRAM is the GPU's peak used memory sampled during it.</li>",
        "</ul>",
        "<p>The table's Decode / Prefill columns are a different measurement: "
        "<code>llama-bench</code> <code>tg128</code>/<code>pp512</code> with the model loaded "
        "directly, no HTTP layer. That is why the two columns differ for the same model.</p>",

        "<h2>Error bars</h2>",
        "<p>Three identical cold repetitions per point. Spread is (max−min)/mean. ",
        (f"Every measured spread was under 5% (largest {eb.get('max_spread_pct')}%), so the "
         "single-run numbers elsewhere are trustworthy at that level." if eb.get("all_under_5pct")
         else "See the values below."),
        "</p>", error_table(doc),
        "<p>A short chat answer that stops after two tokens is not a decode measurement; that "
        "figure is discarded, not published.</p>",

        "<h2>Browser games: how they are gated</h2>",
        "<ul>",
        "<li>One frozen prompt per game, temperature 0, max 8,000 tokens, up to three attempts; "
        "only a passing attempt is published.</li>",
        "<li>A headless browser loads the page over http and file:// and checks: no console "
        "errors, canvas and a live WebGL context, three.js actually used at runtime, animation "
        "advancing between screenshots, keyboard input changing the scene, and a "
        "<code>window.__game</code> contract object being present and ready.</li>",
        "<li>A robot then plays for 60&nbsp;s with real keyboard events and records score, lives, "
        "survival and console errors. A score of zero with aligned aim means the game's collision "
        "geometry is broken — reported as a defect, not fixed.</li>",
        "</ul>",

        "<h2>Chat: how it is scored</h2>",
        "<p>" + esc(ch.get("suite") or "") + " " + esc(ch.get("statement") or "") + "</p>",
        chat_body,
        "<p>The decode t/s column is the mean of the server's per-question decode rate for short "
        "answers; it includes the first (warm-up) question and is therefore slightly below the "
        "steady-state number in the main table.</p>",

        "<h2>What is NOT measured</h2>",
        "<ul>",
        "<li><strong>Concurrency and batching.</strong> Everything runs one sequence per server "
        "(<code>-np 1</code>). No multi-user throughput, no batch-size sweep, no queueing latency.</li>",
        "<li><strong>Vision.</strong> Multimodal projector files are present for some models, but "
        "no image task is scored; vision is not benchmarked here.</li>",
        "<li><strong>Regression over time.</strong> Each row is a point-in-time measurement; there "
        "is no nightly re-run tracking drift, so a row from October is not a statement about "
        "today's speed on newer builds.</li>",
        "<li><strong>Memory over long sessions</strong>, thermal throttling at sustained load, "
        "and power-cap effects are only explored in the <a href=\"#ablation\">ablation block</a>, "
        "not per model.</li>",
        "</ul>",

        "<h2 id=raw>Download the raw records</h2>",
        "<p>The machine-readable dataset is the same file this page renders. The per-question chat "
        "JSONs contain every prompt, answer, verdict, token count and timing, one file per model.</p>",
        '<div class=dl><a href="data/results.json" download>results.json — every row</a>',
        '<a href="#raw-files">chat JSONs — per question</a>',
        '<a href="benchmarks/gapclose/RESULTS.md">gap-close results (markdown)</a></div>',
        '<p class="note">results.json and the chat JSONs are built into this page\'s own directory by '
        '<code>scripts/build_pages_method.py</code> from <code>data/results.json</code> and '
        '<code>data/chat/</code>; regenerated with the data, never hand-edited.</p>',
        raw_files_html(),
    ])

    return body


def copy_raw():
    """Publish the raw records beside the data they describe: /data/results.json and
    /data/chat/<model>.json. These are the URL targets of the #method download section."""
    dst = os.path.join(ROOT, "data", "chat")
    os.makedirs(dst, exist_ok=True)
    names = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "chat", "*.json"))):
        names.append(os.path.basename(p))
    return names


def build():
    """Print the methodology fragment. The overview splices it in at #method."""
    body = body_html()
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
