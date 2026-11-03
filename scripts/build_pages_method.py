#!/usr/bin/env python3
"""build_pages_method.py -- generate the /method/ page and the raw-data download copies.

Nothing here is hand-written HTML: the model list, the prompt sizes, the error-bar points and
the chat counts are read from data/results.json and the benchmark protocol (docs/BENCHMARK.md)
is summarised into fixed sections. Re-run after any data refresh:

    python3 scripts/update_data.py && python3 scripts/a3b_extras.py \
      && python3 scripts/gapclose_extras.py && python3 scripts/build_pages_method.py

Visitor-facing text only: no hostnames, no IPs, no local paths, no internal model symlinks.
"""
import glob, sys
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_nav import render_nav  # noqa: E402  single source of truth for the nav

NAV = render_nav("../", "method")

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
th,td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left;font-size:13px}
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
@media(max-width:640px){.wrap{padding:20px 12px 48px}h1{font-size:20px}th,td{padding:7px 7px;font-size:12.5px}}
"""


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def page(title, body):
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><div class=wrap>"
            f"{NAV}<h1>{esc(title)}</h1>{body}</div></body></html>")


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


def build():
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
        "<li><strong>Engine:</strong> llama.cpp <code>llama-server</code>, Vulkan backend on an "
        "AMD Radeon AI PRO R9700 (32&nbsp;GiB). Models run on a different engine (e.g. a "
        "proprietary container format) are labelled with that engine in the table instead.</li>",
        "<li><strong>Builds:</strong> the build id is printed in the <em>Speed evidence</em> column "
        "of each row. Two builds appear: <code>b11517</code> (the mainline server used for the "
        "suite and the standard speed probe) and <code>b11874</code>, needed for one newer "
        "architecture. A number is only comparable across rows measured on the same build.</li>",
        "<li><strong>Flags</strong> (one server at a time, recorded per row): "
        "<code>-ngl 99 -fa on -c &lt;window&gt; --jinja -np 1 -ctk q8_0 -ctv q4_0</code>, plus "
        "<code>-b 16384 -ub 2048</code> on the serving-shaped probes. <code>-np 1</code> means one "
        "sequence slot: no batching, no concurrency.</li>",
        "<li><strong>KV cache types:</strong> keys q8_0, values q4_0 on most suite runs; a few "
        "earlier runs used f16, and the ablation tab measures what changing the KV type does. "
        "The per-row value is in the evidence column.</li>",
        "<li><strong>Reasoning/thinking</strong> is off unless a tab says otherwise "
        "(<code>enable_thinking:false</code> via the chat template); the thinking tab is the "
        "on/off comparison.</li>",
        "</ul>",

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
        "and power-cap effects are only explored in the ablation tab, not per model.</li>",
        "</ul>",

        "<h2>Check any number yourself</h2>",
        "<p>The machine-readable dataset is the same file this page renders. The per-question chat "
        "JSONs contain every prompt, answer, verdict, token count and timing.</p>",
        '<div class=dl><a href="../data/results.json" download>results.json — every row</a>',
        '<a href="../raw-chat/">chat JSONs — per question</a>',
        '<a href="../benchmarks/gapclose/RESULTS.md">gap-close results (markdown)</a></div>',
        '<p class="note">Generated by <code>scripts/build_pages_method.py</code> from '
        '<code>data/results.json</code>; regenerated with the data, never hand-edited.</p>',
    ])

    os.makedirs(os.path.join(ROOT, "method"), exist_ok=True)
    with open(os.path.join(ROOT, "method", "index.html"), "w", encoding="utf-8") as f:
        f.write(page("method — how each number was measured", body))

    # raw chats: a browsable download set next to the site
    dst = os.path.join(ROOT, "raw-chat")
    os.makedirs(dst, exist_ok=True)
    names = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "chat", "*.json"))):
        b = os.path.basename(p)
        shutil.copyfile(p, os.path.join(dst, b))
        names.append(b)
    idx = ["<h2>Chat JSONs</h2><p>One file per model: every question, expected answer, "
           "model answer, verdict, tokens, milliseconds and decode rate.</p>",
           '<div class=table-wrap><table><thead><tr><th>File</th></tr></thead><tbody>']
    idx += [f'<tr><td><a href="{esc(b)}">{esc(b)}</a></td></tr>' for b in names]
    idx.append("</tbody></table></div>")
    idx.append('<p class="note">Copied from <code>data/chat/</code> by '
               '<code>scripts/build_pages_method.py</code> on every build.</p>')
    raw_page = page("raw chat data", "".join(idx)).replace(
        NAV, render_nav("../", "raw"), 1)
    with open(os.path.join(dst, "index.html"), "w", encoding="utf-8") as f:
        f.write(raw_page)

    print("method page + %d raw chat file(s)" % len(names))


if __name__ == "__main__":
    build()
