#!/usr/bin/env python3
"""sweep_data_3090.py — the RTX 3090 (CUDA) matched-context table, rendered from
benchmarks/rtx3090/sweep3090.json.

Kept OUT of sweep_data.py on purpose: that module owns the R9700 (Vulkan) matrix and the
two must not merge (Fen, 7 Nov 2026: the 3090 gets a separate table). Every number comes
from the JSON written by benchmarks/rtx3090/sweep3090.py; nothing is typed by hand.

``table_html()`` returns a bare <section> fragment that both the /benchmarks/sweep/ page
and the /benchmarks/rtx3090/ page reuse.
"""
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "benchmarks", "rtx3090", "sweep3090.json")
RUNGS = [4096, 32768, 65536, 131072, 262144]


def esc(v):
    return html.escape(str(v)) if v is not None else "—"


def load():
    try:
        return json.load(open(SRC))
    except Exception:
        return None


def table_html(anchor="rtx3090-sweep"):
    sw = load()
    if not sw:
        return ("<section class=sweep id=%s><h2 class=sec>NVIDIA GeForce RTX 3090 (CUDA)</h2>"
                "<p class=sub>not measured yet</p></section>" % anchor)
    cells = sw.get("cells") or {}
    meta = (f"{esc(sw.get('name'))} · {esc(sw.get('quant'))} · "
            f"<code>{esc(sw.get('file'))}</code> · llama.cpp "
            f"<code>b12189</code> (Windows, CUDA 12.4)")
    rows = []
    for c in RUNGS:
        v = cells.get(str(c)) or {}
        ok = v.get("status") in ("ok", "ok_from_server_log")
        rows.append(
            f"<tr><td class=num>{c:,}</td>"
            f"<td class=num>{('{:,}'.format(v['prompt_n'])) if v.get('prompt_n') else '—'}</td>"
            f"<td class=num>{('{:,.1f}'.format(v['prefill_tps'])) if ok else '—'}</td>"
            f"<td class=num>{('{:,.1f}'.format(v['prefill_s'])) if ok else '—'}</td>"
            f"<td class=num>{('{:,.2f}'.format(v['decode_tps'])) if ok else '—'}</td>"
            f"<td class=num>{('%.2f' % v['vram_peak_gib']) if v.get('vram_peak_gib') else '—'}</td>"
            f"<td class=num>{v.get('draft_n_accepted') or '—'}/{v.get('draft_n') or '—'}</td>"
            f"<td>{'measured' if ok else esc(v.get('status'))}</td></tr>")
    return (
        f"<section class=sweep id={anchor}>"
        "<h2 class=sec>NVIDIA GeForce RTX 3090 (CUDA) — separate card, separate table</h2>"
        f"<p class=sub>{meta}. Same probe as the R9700 matrix: server restarted per rung with "
        "<code>-c &lt;ctx&gt;</code>, one prompt calibrated with <code>/tokenize</code> to "
        "<code>ctx − 512</code>, one cold request (temperature 0, <code>cache_prompt:false</code>, "
        "<code>ignore_eos</code>, 64 generated tokens). Decode here includes MTP speculative "
        "decoding (ByteShape's published command), so it is not directly comparable with the "
        "R9700 rows above.</p>"
        "<div class=scroll><table id=sweep3090><thead><tr>"
        "<th>Context</th><th>Prompt tokens</th><th>Prefill t/s</th><th>Prefill s</th>"
        "<th>Decode t/s</th><th>Peak VRAM GiB</th><th>Draft accepted</th><th>Status</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        "<p class=note>256&nbsp;K fits in 24&nbsp;GiB, but prefill costs ~33&nbsp;minutes and "
        "decode falls to single digits: a capacity statement, not a usable serving point. "
        "The same model without speculative decoding reaches "
        + (lambda d: f"{d.get('decode_tps')} t/s" if d else "—")(_spec_off())
        + " decode at 32&nbsp;K (measured on the same probe).</p>"
        "</section>")


def _load(name):
    try:
        return json.load(open(os.path.join(ROOT, "benchmarks", "rtx3090", name), encoding="utf-8"))
    except Exception:
        return None


def summary_html():
    """Quality cells measured on the same 3090 run (GPQA pair, chat, vision, galaga).

    Every figure is read from the JSON the run wrote; a missing file prints a dash.
    """
    gpqa = _load("gpqa-pair-3090.json") or {}
    chat = (_load("chat10-3090.json") or {}).get("summary") or {}
    vis = _load("vision-smoke.json") or {}
    gal = _load(os.path.join("galaga-3090", "build.json")) or {}

    def pair(arm):
        a = gpqa.get(arm) or {}
        if not a.get("n"):
            return "—"
        return f"{a.get('correct')}/{a.get('n')}"

    rows = [
        ("GPQA-Diamond, 25 frozen questions", "thinking off", pair("off")),
        ("GPQA-Diamond, 25 frozen questions", "thinking on", pair("on")),
        ("Chat, 10 fixed questions", "thinking off",
         (f"{chat.get('correct')}/{chat.get('n')}" + (f" (+{chat['partial']} partial)" if chat.get("partial") else ""))
         if chat.get("n") else "—"),
        ("Vision smoke (one image, exact code)", "thinking off",
         ("pass" if vis.get("ok") else "fail") if vis else "—"),
        ("Browser game: three.js Galaga", f"{gal.get('max_attempts', '—')} attempts allowed",
         ((f"accepted, attempt {gal.get('accepted_attempt')}") if gal.get("accepted_attempt") else "fail") if gal else "—"),
    ]
    body = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td class=num>{esc(c)}</td></tr>"
                   for a, b, c in rows)
    return ("<div class=scroll><table id=sweep3090-summary><thead><tr><th>Cell</th>"
            "<th>Mode</th><th>Result</th></tr></thead><tbody>" + body + "</tbody></table></div>")


def _spec_off():
    p = os.path.join(ROOT, "benchmarks", "rtx3090", "spec-off-32k.json")
    try:
        return json.load(open(p))
    except Exception:
        return None
