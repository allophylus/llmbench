#!/usr/bin/env python3
"""build_pages_sweep.py — /benchmarks/context-sweep/: the matched-context speed matrix, two tables.

Table 1 (unchanged numbers, existing owner): the R9700 (Vulkan) matrix rendered by
scripts/sweep_data.py from benchmarks/ctx-sweep/.

Table 2 (new): the RTX 3090 (CUDA) row for Qwen3.8-27B IQ4_XS, rendered by
scripts/sweep_data_3090.py from benchmarks/rtx3090/sweep3090.json.

The tables are deliberately separate — different card, different quantisation, different
KV types and (on the 3090) MTP speculative decoding — so no cell is a cross-card
comparison. This page used to live at a retirement-listed path; that path is retired in the site nav
checker, so the page is /benchmarks/sweep/ and the overview links to it.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "benchmarks", "context-sweep")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sweep_data  # noqa: E402
import sweep_data_3090  # noqa: E402
from site_nav import render_topbar, TOPBAR_CSS  # noqa: E402

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 16px}
p.note{color:var(--faint);border-left:3px solid var(--line);padding-left:10px;margin:10px 0}
code{font-family:ui-monospace,monospace;font-size:12.5px;background:#101722;padding:1px 4px;border-radius:4px}
.sweep-h{font-size:17px;margin:26px 0 6px}
.sec{font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;margin:26px 0 6px}
"""


def build():
    frag_r97 = sweep_data.section_html()
    frag_r97 = (frag_r97.replace("<section class=sweep id=speed-sweep>", "<div class=sweep>")
                .replace('<section class="sweep" id="speed-sweep">', "<div class=sweep>"))
    if frag_r97.endswith("</section>"):
        frag_r97 = frag_r97[: -len("</section>")] + "</div>"
    frag_3090 = sweep_data_3090.table_html()

    body = f"""
<div class="wrap">
<h1>Speed by context</h1>
<p class="sub">Matched-context sweep: the server is restarted at each context size and the
prompt is calibrated to that size, so prefill and decode are measured at the context they
claim. Two cards, two tables — the numbers are never mixed.</p>
{frag_r97}
{frag_3090}
<h2 class=sweep-h>How to read this</h2>
<p class=sub>Every cell is one cold request per model per context: temperature 0,
<code>cache_prompt:false</code>, no stream, and exactly 64 generated tokens (a fixed
continuation prompt, because these models otherwise end a turn after a couple of tokens,
which cannot measure decode). Prefill and decode t/s are the server's own per-request
timings; peak VRAM is sampled on the GPU at 1&nbsp;Hz during the request.</p>
<p class=sub>The R9700 runs llama.cpp's Vulkan backend on an AMD Radeon AI PRO R9700
(32&nbsp;GiB) without speculative decoding. The RTX 3090 runs the CUDA backend on an NVIDIA
GeForce RTX 3090 (24&nbsp;GiB) with Qwen3.8-27B's MTP drafter enabled, which lifts decode
most on repetitive output and leaves general-text throughput lower than these numbers.</p>
<p class=sub>Full RTX 3090 quality results (GPQA, thinking on/off, chat, a generated browser
game) are on the <a href="../rtx3090/">RTX 3090 (CUDA) page</a>.</p>
</div>"""

    doc = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
           "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
           "<title>Speed by context · llmbench</title><style>"
           + TOPBAR_CSS + sweep_data.hard_css() + CSS + "</style></head><body>"
           + render_topbar("../../") + body + "</body></html>\n")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote benchmarks/context-sweep/index.html ({len(doc)} bytes)")


if __name__ == "__main__":
    build()
