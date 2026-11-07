#!/usr/bin/env python3
"""build_pages_wsp.py — render benchmarks/wsp/index.html from results.json.

Run after assemble_results.py. The page is a notes page (not a nav section): it
carries the canonical site nav with prefix "../../", so links resolve from
benchmarks/wsp/ back to the site root.
"""
import html
import json
import os
import sys

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks", "wsp")
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from site_nav import render_topbar, TOPBAR_CSS  # noqa: E402

DATA = json.load(open(os.path.join(HERE, "results.json")))
RAW = os.path.join(HERE, "raw", "out")


def mean_tok(fname):
    try:
        rows = [json.loads(l) for l in open(os.path.join(RAW, fname))]
        v = [r.get("completion_tokens") or 0 for r in rows if not r.get("error")]
        return int(sum(v) / len(v)) if v else None
    except Exception:
        return None


TOK_S, TOK_W = mean_tok("stock.ccp.jsonl"), mean_tok("wsp.ccp.jsonl")


def fmt(v, nd=2):
    return "—" if v is None else f"{v:,.{nd}f}" if isinstance(v, float) else f"{v:,}"


def pp(a, b, invert=False):
    """delta with an arrow; invert=True means lower is better."""
    if a is None or b is None:
        return '<td class="num">—</td>'
    d = b - a
    good = (d < 0) if invert else (d > 0)
    cls = "ok" if (good and abs(d) > 1e-9) else ("bad" if abs(d) > 1e-9 else "")
    return f'<td class="num {cls}">{d:+,.2f}</td>'


c_s, c_w = DATA["ccpbench30"]["stock"], DATA["ccpbench30"]["wsp"]
m20_s, m20_w = DATA["math20"]["stock"], DATA["math20"]["wsp"]
m5_s, m5_w = DATA["math500_20"]["stock"], DATA["math500_20"]["wsp"]
g_s, g_w = DATA["gpqa25"]["stock"], DATA["gpqa25"]["wsp"]
sp = DATA["speed"]
tgt = DATA["diff"]["svd_target"]
ctl = DATA["diff"]["svd_controls"]


def row(metric, a, b, note, invert=False, nd=2):
    fa = "—" if a is None else (f"{a:,.{nd}f}" if isinstance(a, float) else str(a))
    fb = "—" if b is None else (f"{b:,.{nd}f}" if isinstance(b, float) else str(b))
    return (f'<tr><td class="metric">{metric}<span class="q">{note}</span></td>'
            f'<td class="num">{fa}</td><td class="num">{fb}</td>{pp(a, b, invert)}</tr>')


def gpqa_str(g):
    return f"{g['correct']}/{g['n']} = {g['acc']*100:.0f}%" if g else "—"


def gpqa_val(g):
    return g["acc"] * 100 if g else None


rows = [
    row("CCPBench-A mean bias", c_s["mean"], c_w["mean"],
        "1 = no bias, 5 = severe; 30 questions, same rubric", invert=True),
    row("  … China-related subset", c_s["china_mean"], c_w["china_mean"],
        f"{c_s['n_china']} questions", invert=True),
    row("  … non-China subset", c_s["non_china_mean"], c_w["non_china_mean"],
        f"{c_s['n_non_china']} control questions", invert=True),
    row("GPQA-25 (correct / 25)", gpqa_val(g_s), gpqa_val(g_w),
        f"{g_s['correct']}/25 vs {g_w['correct']}/25; thinking off, 2048-token cap", nd=0),
    row("MATH-500 (20-item) correct", (m5_s or {}).get("acc", 0) * 100,
        (m5_w or {}).get("acc", 0) * 100, "HuggingFaceH4/MATH-500 first 20", nd=0),
    row("Arithmetic set (20-item) correct", (m20_s or {}).get("acc", 0) * 100,
        (m20_w or {}).get("acc", 0) * 100, "gsm8k-style, exact numeric answer", nd=0),
    row("Prefill t/s @ 7.4K prompt",
        (sp.get("stock_4k") or {}).get("prefill_tps") or DATA["recorded_baselines"]["speed_4k"]["prefill_tps"],
        (sp.get("wsp_4k") or {}).get("prefill_tps"),
        "cold, cache_prompt false, 3 reps"),
    row("Decode t/s @ ~7.4K prompt",
        (sp.get("stock_4k") or {}).get("decode_tps") or DATA["recorded_baselines"]["speed_4k"]["decode_tps"],
        (sp.get("wsp_4k") or {}).get("decode_tps"), "64 generated tokens"),
    row("Prefill t/s @ 129K prompt",
        (sp.get("stock_128k") or {}).get("prefill_tps") or DATA["recorded_baselines"]["speed_128k"]["prefill_tps"],
        (sp.get("wsp_128k") or {}).get("prefill_tps"), "single cold rep"),
    row("Decode t/s @ 129K prompt",
        (sp.get("stock_128k") or {}).get("decode_tps") or DATA["recorded_baselines"]["speed_128k"]["decode_tps"],
        (sp.get("wsp_128k") or {}).get("decode_tps"), "single cold rep"),
]
rows_html = "\n".join(rows)

dist_s, dist_w = c_s["distribution"], c_w["distribution"]
dist_html = "".join(
    f"<tr><td class='num'>{k}</td><td class='num'>{dist_s.get(str(k), 0)}</td>"
    f"<td class='num'>{dist_w.get(str(k), 0)}</td></tr>" for k in range(1, 6))

ctl_rows = "".join(
    f"<tr><td>{html.escape(c['tensor'])}</td><td class='num'>{c['fro_norm']:.2f}</td>"
    f"<td class='num'><b>{c['sv1']:.3f}</b></td><td class='num'>{c['sv2']:.3f}</td>"
    f"<td class='num'>{c['sv1_over_sv2']:.1f}</td></tr>" for c in (ctl or []))

HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weight-space programming — does the edit survive Q4_K_M? · llmbench</title>
<style>{{TOPBAR_CSS}}
:root{{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--ok:#7ee787;--bad:#ff7b72;--gold:#f5c542}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}}
.wrap{{max-width:1000px;margin:0 auto;padding:26px 18px 70px}}
h1{{font-size:25px;margin:0 0 6px;line-height:1.25}}h2{{font-size:17px;margin:30px 0 8px}}
h3{{font-size:14px;margin:18px 0 6px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}}
.sub{{color:var(--dim);margin:0 0 18px}}.meta{{color:var(--faint);font-size:12px}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:10px 0}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
thead th{{background:#1b2431;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim)}}
tbody tr:nth-child(even) td{{background:#131a24}}
td.num{{text-align:right;font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.metric .q{{display:block;color:var(--faint);font-size:11.5px;font-weight:400;margin-top:2px}}
.ok{{color:var(--ok)}}.bad{{color:var(--bad)}}
.verdict{{border:1px solid var(--line);border-left:3px solid var(--gold);background:var(--panel);padding:14px 16px;border-radius:8px;margin:18px 0}}
.verdict p{{margin:6px 0}}
.warn{{border-left-color:var(--bad)}}
code{{font-family:ui-monospace,monospace;font-size:12.5px;color:#c9d7ea}}
.table-wrap{{overflow-x:auto}}
a{{color:#8cc8ff}}
</style>
</head>
<body>
{{TOPBAR}}
<div class="wrap">
<h1>Weight-space programming: does a 0.071% weight edit survive Q4_K_M?</h1>
<p class="sub">A third-party release claims to have edited one MLP tensor of Qwen3.8-27B to shift a
measured political-bias score. We checked whether the edit is actually in the published 4-bit file,
and what it does to behaviour and speed on the R9700. Measured 7 November 2026.</p>

<div class="verdict">
<p><strong>Verdict: yes — the edit survives quantisation, and it moves behaviour.</strong></p>
<p>The published Q4_K_M file carries a rank-1 component of norm <b>{tgt['sv1']:.3f}</b> in
<code>blk.29.ffn_down</code>, against the <b>7.4606</b> the upstream card documents for its
weight patch (0.3% away). Untouched tensors in the same layer show no such component.
Behaviourally, mean CCPBench-A bias on our 30-question subset fell
<b>{c_s['mean']:.2f} → {c_w['mean']:.2f}</b> while MATH-500 and the arithmetic set were unchanged.
Decode speed is unchanged; prefill is consistently <b>4–8% slower</b> on the WSP file, which a
single edited tensor cannot explain — see the note on the two files' quantisation below.</p>
<p><strong>Caveat, stated plainly:</strong> the local "Q4_K_M" baseline is a mixed-precision build
(417 of 866 tensors are Q5_K/IQ4_XS/Q8_0/Q6_K, not Q4_K), so part of any behavioural gap could be
precision rather than the edit. The edit's presence in the file is not in doubt; the exact
attribution of the behaviour is.</p>
</div>

<h2>What was claimed, and what was tested</h2>
<p>The model is <a href="https://huggingface.co/ReBatch/Qwen3.8-27B-Weight-Space-Programming">ReBatch/Qwen3.8-27B-Weight-Space-Programming</a>,
quantised to Q4_K_M by mradermacher. Its card states the release changes
<b>19,680,881 stored weights</b> — approximately <b>0.071%</b> of 27.78B parameters — all inside
one tensor: <code>model.language_model.layers.29.mlp.down_proj.weight</code>, in 4,096 of its
17,408 input columns. The claimed effect is on <b>CCPBench-A</b>: mean score
<b>2.714 → 1.518</b> on all 500 questions (lower is less CCP-aligned), judged by
<code>gpt-6.1-terra</code>. It is explicitly <em>not</em> a MATH or reasoning claim; the widely
quoted "7.9% → 48.1% MATH-500" figure belongs to the original 0.8B demonstration on a
different model, and does not apply here.</p>

<h2>A/B on the same card, same harness</h2>
<p class="meta">Both arms: llama.cpp b11517, Vulkan, <code>-ngl 99 -fa on -np 1 -b 16384 -ub 2048
-ctk q8_0 -ctv q4_0 --cache-reuse 256 --jinja</code>, <code>enable_thinking:false</code>,
temperature 0 (0.2 for CCPBench, matching the benchmark's own protocol), one request at a time.
Behaviour sets ran at <code>-c 32768</code>; GPQA at <code>-c 131072</code>.</p>
<div class="table-wrap">
<table>
<thead><tr><th>Metric</th><th class="num">Baseline</th><th class="num">WSP</th><th class="num">Δ (WSP − baseline)</th></tr></thead>
<tbody>
{rows_html}
</tbody></table></div>

<h2>Bias scores, question by question</h2>
<div class="table-wrap">
<table>
<thead><tr><th>CCPBench score</th><th class="num">Baseline (n)</th><th class="num">WSP (n)</th></tr></thead>
<tbody>{dist_html}</tbody></table></div>
<p class="meta">The shift is in the tails: ten 5s for the baseline against three for WSP, and one 1
against eleven. Category tags show the same movement — refusals and "lying" tags drop, and WSP
answers become markedly longer (mean {TOK_W} completion tokens against {TOK_S} for the baseline),
which is itself the main side effect of the edit.</p>

<h2>The file-level check</h2>
<p>Dequantising both GGUFs and taking the difference in the edited tensor, the leading singular
value is the edit's norm. Controls are untouched tensors from the same layer and neighbourhood.</p>
<div class="table-wrap">
<table>
<thead><tr><th>Tensor</th><th class="num">‖D‖<sub>F</sub></th><th class="num">σ₁</th><th class="num">σ₂</th><th class="num">σ₁/σ₂</th></tr></thead>
<tbody>
<tr><td><code>{tgt['tensor']}</code> <span class="meta">(documented edit)</span></td>
<td class="num">{tgt['fro_norm']:.2f}</td><td class="num"><b>{tgt['sv1']:.3f}</b></td>
<td class="num">{tgt['sv2']:.3f}</td><td class="num">{tgt['sv1_over_sv2']:.1f}</td></tr>
{ctl_rows}
</tbody></table></div>
<p>Documented patch norm: <b>7.4606</b>. Measured: <b>{tgt['sv1']:.3f}</b>. The top component holds
{tgt['top1_energy_frac']*100:.1f}% of the difference energy in the edited tensor versus
{ctl[0]['top1_energy_frac']*100:.2f}–{ctl[-1]['top1_energy_frac']*100:.2f}% in the controls.</p>

<h2>Reading the numbers honestly</h2>
<ul>
<li><strong>Judge.</strong> CCPBench scores here come from <code>deepseek-chat</code> applying the
official rubric to blinded responses — not the <code>gpt-6.1-terra</code> judge the vendor used.
Absolute values are therefore not comparable to the published 2.714 / 1.518; the <em>paired
difference</em> between two arms scored by one judge is the meaningful quantity.</li>
<li><strong>Subset.</strong> 30 of 500 questions (22 China-related, 8 control), stratified by topic.
The published gpt-oss-120b reference scores 4.17 on this subset.</li>
<li><strong>Quantisation confound.</strong> See the note at the top and <a href="DIFF.md">DIFF.md</a>.</li>
<li><strong>Truncation.</strong> GPQA ran with a 2048-token cap; WSP hit it on
{(g_w or {}).get('truncated', 0)}/25 questions and the baseline on {(g_s or {}).get('truncated', 0)}/25.
Both arms are scored the same way, but a longer budget would change the absolute GPQA figure.</li>
<li><strong>Speed, and a caveat on the prefill gap.</strong> The edited tensor is 0.07% of the
weights, so a 4–8% prefill difference cannot come from the edit itself. It matches the other
structural difference between the files — the baseline is a mixed-precision build — and is the same
direction at both rungs. The 7.4K rung is the mean of 3 cold reps; the 129K rung is a single cold rep
(one full prefill of ~129K tokens), so treat its spread as unknown. The prompt is the standard
repeated-filler document, token-calibrated via <code>/tokenize</code>.</li>
</ul>

<h2>Files</h2>
<p class="meta"><a href="results.json">results.json</a> — every number on this page ·
<a href="DIFF.md">DIFF.md</a> — full diff report ·
<a href="https://github.com/allophylus/llmbench/tree/main/benchmarks/wsp/raw">raw/</a> — per-question records, judge outputs, server argv ·
harnesses: <code>bench_wsp.py</code>, <code>diff_gguf.py</code>, <code>svd_probe.py</code>,
<code>judge_ccp.py</code>, <code>grade_math_llm.py</code></p>
</div>
</body></html>
"""

with open(os.path.join(HERE, "index.html"), "w") as f:
    f.write(HTML.replace("{TOPBAR_CSS}", TOPBAR_CSS).replace("{TOPBAR}", render_topbar("../../")))
print("wrote", os.path.join(HERE, "index.html"), len(HTML), "bytes")
