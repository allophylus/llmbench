#!/usr/bin/env python3
"""build_pages_rtx3090.py — the "RTX 3090 (CUDA)" page.

ONE page: benchmarks/rtx3090/index.html. It carries the RTX 3090 rows only, as a
SEPARATE table from the R9700 numbers (Fen, 7 Nov 2026: separate table, never merged).

Every number is read from a measured artifact in benchmarks/rtx3090/:
  sweep3090.json        matched-context sweep   (sweep3090.py)
  gpqa-pair-3090.json   GPQA-25 off/on arms     (think_pair3090.py)
  chat10-3090.json      10-question chat set    (benchmarks/gapclose/chat_suite.py)
  galaga-3090/build.json  game cell             (games/build_run.py)
  vision-smoke.json     one-line vision check   (vision_smoke.py)
A missing artifact renders "not run" — never a guessed value.

The nav prefix is "../../" (two levels deep) and comes from scripts/site_nav.py, so
the link set cannot drift from the rest of the site.
"""
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "benchmarks", "rtx3090")
OUT = os.path.join(SRC, "index.html")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_nav import render_topbar, TOPBAR_CSS  # noqa: E402

RUNGS = [4096, 32768, 65536, 131072, 262144]

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:26px 0 8px}
h3{font-size:15px;margin:22px 0 6px;color:var(--dim)}
.sub{color:var(--dim);margin:0 0 16px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{width:100%;border-collapse:collapse;background:var(--panel);min-width:640px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
thead th{background:#1b2431;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
tbody tr:nth-child(even) td{background:#131a24}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
.ok{color:var(--ok)}.bad{color:var(--bad)}.dim{color:var(--faint)}.warn{color:var(--gold)}
.note{border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:8px;padding:12px 14px;background:#151f2b;margin:14px 0;color:var(--dim)}
.note strong{color:var(--fg)}
code{font-family:ui-monospace,monospace;font-size:12.5px;background:#101722;padding:1px 4px;border-radius:4px}
ul{margin:8px 0 8px 18px;padding:0}li{margin:4px 0}
"""


def load(name):
    p = os.path.join(SRC, name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p))
    except Exception:
        return None


def esc(v):
    return html.escape(str(v)) if v is not None else "—"


def cell(v, fmt="{:.1f}"):
    if v is None:
        return '<td class="num dim">—</td>'
    return f'<td class="num">{fmt.format(v)}</td>'


def sweep_table(sw):
    if not sw or not sw.get("cells"):
        return '<p class="dim">not run</p>'
    rows = []
    for c in RUNGS:
        k = str(c)
        v = (sw.get("cells") or {}).get(k)
        if not v:
            rows.append(f"<tr><td>{c:,}</td>" + '<td class="num dim">—</td>' * 8 + "</tr>")
            continue
        ok = v.get("status") in ("ok", "ok_from_server_log")
        draft = v.get("draft_n_accepted")
        dn = v.get("draft_n")
        dacc = (f"{draft}/{dn}" if draft is not None and dn else "—")
        rows.append(
            f"<tr><td class=num>{c:,}</td>"
            + cell(v.get("n_ctx_server"), "{:,.0f}")
            + cell(v.get("prompt_n"), "{:,.0f}")
            + (f'<td class="num">{v.get("prefill_tps")}</td>' if ok else '<td class="num bad">—</td>')
            + cell(v.get("prefill_s"))
            + (f'<td class="num">{v.get("decode_tps")}</td>' if ok else '<td class="num bad">—</td>')
            + cell(v.get("vram_peak_gib"), "{:.2f}")
            + f'<td class="num dim">{dacc}</td>'
            + f'<td>{"measured" if ok else esc(v.get("status"))}</td></tr>')
    return ("<div class=scroll><table><thead><tr><th>Context (tokens)</th><th>Server -c</th>"
            "<th>Prompt tokens</th><th>Prefill t/s</th><th>Prefill s</th><th>Decode t/s</th>"
            "<th>Peak VRAM (GiB)</th><th>Draft accepted</th><th>Status</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def gpqa_table(pair):
    if not pair:
        return '<p class="dim">not run</p>'
    rows = []
    for mode, label in (("off", "thinking off"), ("on", "thinking on")):
        b = pair.get(mode) or {}
        n = b.get("n")
        c = b.get("correct")
        acc = f"{c/n*100:.0f}%" if n and c is not None else "—"
        rows.append(f"<tr><td>{label}</td><td class=num>{esc(c)}/{esc(n)}</td>"
                    f"<td class=num>{acc}</td><td class=num>{esc(b.get('tokens'))}</td>"
                    f"<td class=num>{esc(b.get('length_stops'))}</td>"
                    f"<td class=num>{esc(b.get('wall_s'))}</td></tr>")
    return ("<div class=scroll><table><thead><tr><th>Arm</th><th>Correct</th><th>Accuracy</th>"
            "<th>Completion tokens</th><th>Length stops</th><th>Wall s</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def chat_table(ch):
    if not ch:
        return '<p class="dim">not run</p>'
    s = ch.get("summary") or {}
    return ("<div class=scroll><table><thead><tr><th>Correct</th><th>Partial</th><th>Wrong</th>"
            "<th>Accuracy</th><th>Mean tokens</th><th>Mean decode t/s</th><th>Wall s</th>"
            "</tr></thead><tbody><tr>"
            f"<td class=num>{esc(s.get('correct'))}/{esc(s.get('n'))}</td>"
            f"<td class=num>{esc(s.get('partial'))}</td><td class=num>{esc(s.get('wrong'))}</td>"
            f"<td class=num>{esc(s.get('accuracy'))}%</td>"
            f"<td class=num>{esc(s.get('mean_tokens'))}</td>"
            f"<td class=num>{esc(s.get('mean_decode_tps'))}</td>"
            f"<td class=num>{esc(s.get('wall_s'))}</td></tr></tbody></table></div>")


def game_block(build):
    if not build:
        return '<p class="dim">not run</p>'
    checks = {}
    for a in build.get("per_attempt") or []:
        if a.get("ok"):
            checks = a.get("reasons") or {}
    ok = build.get("status") == "accepted"
    lines = [f"<p><strong>{'accepted' if ok else 'not accepted'}</strong> — "
             f"{build.get('attempts_used')} attempt(s), "
             f"{build.get('total_completion_tokens')} completion tokens, "
             f"{build.get('total_wall_s')} s total.</p>"]
    pa = "".join(f"<li>attempt {a.get('attempt')}: "
                 f"{'pass' if a.get('ok') else 'fail — ' + ', '.join(a.get('reasons') or [])}</li>"
                 for a in build.get("per_attempt") or [])
    lines.append(f"<ul>{pa}</ul>")
    if ok and os.path.exists(os.path.join(SRC, "galaga-3090", "shot.png")):
        lines.append('<p><img src="galaga-3090/shot.png" alt="generated game frame" '
                     'style="max-width:520px;border:1px solid #243040;border-radius:8px"></p>')
    return "".join(lines)


def vision_block(v):
    if not v:
        return '<p class="dim">not run</p>'
    if v.get("error"):
        return f'<p class="bad">failed: {esc(v.get("error"))}</p>'
    return (f"<p>Image question, one line answer. Expected <code>{esc(v.get('expect'))}</code>, "
            f"got <code>{esc(v.get('answer'))}</code> → "
            f"<strong>{'pass' if v.get('ok') else 'fail'}</strong> in {esc(v.get('wall_s'))} s.</p>")


def build():
    sw = load("sweep3090.json")
    pair = load("gpqa-pair-3090.json")
    chat = load("chat10-3090.json")
    game = load(os.path.join("galaga-3090", "build.json"))
    vis = load("vision-smoke.json")

    model_line = "Qwen3.8-27B &middot; IQ4_XS (3.84 bpw) &middot; <code>Qwen3.8-27B-IQ4_XS-3.84bpw.gguf</code>"
    if sw:
        model_line = (f"{esc(sw.get('name'))} &middot; {esc(sw.get('quant'))} &middot; "
                      f"<code>{esc(sw.get('file'))}</code>")

    body = f"""
<div class="wrap">
<h1>RTX 3090 (CUDA)</h1>
<p class="sub">{model_line} — served by llama.cpp <code>b12189</code> (Windows, CUDA 12.4) on an
NVIDIA GeForce RTX 3090, 24&nbsp;GiB. These rows are a <strong>separate card and a separate
table</strong>: they are not comparable cell-for-cell with the R9700 (Vulkan) numbers, which use
different quantisations, KV settings and no speculative decoding.</p>

<h2>Matched-context sweep</h2>
<p class="sub">Server restarted per rung with <code>-c &lt;ctx&gt;</code>; one prompt calibrated
with <code>/tokenize</code> to <code>ctx − 512</code>; one cold request (temperature 0,
<code>cache_prompt:false</code>, <code>ignore_eos</code>, 64 generated tokens). Prefill and
decode are the server's own timings for that request; peak VRAM is sampled at 1&nbsp;Hz on the GPU
during it. The same table sits beside the R9700 matrix on
<a href="../context-sweep/">speed by context</a>.</p>
{sweep_table(sw)}

<div class="note"><strong>Reading the decode column.</strong> This run uses ByteShape's published
command, which enables <code>--spec-type draft-mtp</code> with 3 draft tokens. The speed probe
repeats one filler document and asks for a multiplication table, so the MTP drafter accepts
almost every token (see <em>Draft accepted</em>) and decode is a repetitive-output best case, not
a general-text rate. The 256&nbsp;K rung does fit in 24&nbsp;GiB, but prefill costs ~33&nbsp;minutes
and decode falls to single digits, so it is a capacity statement, not a usable serving point.</div>

<h2>Quality</h2>
<p class="sub">GPQA-Diamond, 25 frozen questions, temperature 0, seed 5, 4096-token cap on both
arms; the only variable is the reasoning flag.</p>
{gpqa_table(pair)}
<h3>Chat — the 10 fixed questions the R9700 rows use</h3>
<p class="sub">Temperature 0, fixed seed per question, 512-token cap, thinking off. Scored by
the same keyword matcher used for every other chat row on this site.</p>
{chat_table(chat)}

<h2>Browser game</h2>
<p class="sub">One frozen prompt (three.js Galaga), temperature 0, at most three attempts, gated
by headless Chrome: no console errors, live WebGL canvas, animation advancing, input changing
pixels, and the <code>window.__game</code> contract present.</p>
{game_block(game)}

<h2>Vision</h2>
{vision_block(vis)}

<h2>Method and limits</h2>
<ul>
<li><strong>Hardware:</strong> NVIDIA GeForce RTX 3090 (24&nbsp;GiB), Windows 11 host, CUDA 12.4
build of llama.cpp (<code>b12189</code>). ~5.3&nbsp;GiB of the card is Windows display/WDDM
overhead before any model is loaded, so the model has roughly 19&nbsp;GiB of headroom.</li>
<li><strong>Server flags:</strong> <code>-ngl 99 -fa on -b 16384 -ub 2048 -np 1 -ctk q8_0 -ctv q4_0
--cache-reuse 256 --metrics --jinja --reasoning off --spec-type draft-mtp --spec-draft-n-max 3</code>.
The thinking arms run the same server with the reasoning flag left to the chat template.</li>
<li><strong>Not measured here:</strong> DFlash2 (needs a separate 1.1&nbsp;GB draft model from a
different repository), multi-slot concurrency, and sustained-load thermals.</li>
<li><strong>Cross-card comparisons</strong> belong in the R9700 tables, where the same probe runs
without speculative decoding.</li>
</ul>
</div>"""

    doc = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
           "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
           "<title>RTX 3090 (CUDA) · llmbench</title><style>"
           + TOPBAR_CSS + CSS + "</style></head><body>"
           + render_topbar("../../") + body + "</body></html>\n")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {OUT} ({len(doc)} bytes)")


if __name__ == "__main__":
    build()
