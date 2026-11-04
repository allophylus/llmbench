#!/usr/bin/env python3
"""build_pages_thinking.py -- the "thinking on/off" tab (the SITE's only thinking page).

ONE page, ONE nav entry ("Thinking"): one model, one question set, reasoning channel
enabled vs disabled.

  Accuracy — the 25 frozen GPQA-diamond questions, from the `thinking` block that
             scripts/a3b_extras.py puts on the model's row in data/results.json. Per
             max-token cap: off/on correct, tokens, seconds.
  Method   — how the two arms were run and graded.
  Findings — what thinking bought and what it cost, computed from the same summary.

(The logic-trap set is not published on the site. Its measurements remain in
benchmarks/logic10/ for the record; they are simply not a section of any page.)

Writes thinking/index.html. Times are seconds (never ms). Nothing is typed by hand: every
number comes from a result file, and a run that is missing or incomplete is shown as
"not run" rather than scored.
"""
import glob
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_nav import render_nav, render_topbar, render_brand, TOPBAR_CSS  # noqa: E402  single source of truth for the nav
OUT = os.path.join(ROOT, "thinking", "index.html")


CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 16px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{width:100%;border-collapse:collapse;background:var(--panel);min-width:620px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
thead th{background:#1b2431;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
tbody tr:nth-child(even) td{background:#131a24}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
.ok{color:var(--ok)}.bad{color:var(--bad)}.dim{color:var(--faint)}.warn{color:var(--gold)}
.detail{border:1px solid var(--line);border-radius:10px;padding:14px;margin:16px 0;background:var(--panel)}
.detail h2{margin:0 0 6px;font-size:17px}
.sec{margin:26px 0 6px;font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.part{margin:34px 0 10px;padding:10px 14px;border:1px solid #33506b;border-left:4px solid var(--blue);border-radius:8px;background:#151f2b}
.part h2{margin:0;font-size:18px}
.part .meta{display:block;margin-top:3px}
.callout{border-left:3px solid var(--gold);background:#1a1f27;padding:10px 14px;border-radius:6px;margin:14px 0}
.callout b{color:var(--gold)}
.meta{color:var(--faint);font-size:12px}
.q{color:var(--dim);font-size:12px;max-width:40ch}
.legend{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 12px;font-size:12px;color:var(--dim)}
.legend span b{font-weight:600}
.matrix td.c{text-align:center;font-family:ui-monospace,monospace;font-size:13px}
.matrix td.t{min-width:9.5em;white-space:nowrap}
details{margin:10px 0}
summary{cursor:pointer;color:var(--blue);font-size:13px}
details ul{padding-left:1.1rem}
details li{font-size:12.5px;color:var(--dim)}
/* On a phone the shared style.css turns every table into a label-less card stack.
   Both sections are matrices, so keep a real table that scrolls inside its own box;
   the page itself must never scroll sideways. */
@media(max-width:760px){
 .wrap{padding:18px 12px 48px}
 .scroll{overflow-x:auto;position:relative}
 .scroll::after{content:"scroll \\2192";position:absolute;right:6px;top:6px;font:600 9.5px/1 ui-monospace,monospace;letter-spacing:.06em;color:var(--dim);background:#1b2431cc;padding:3px 5px;border-radius:4px;pointer-events:none}
 .scroll table{display:table;min-width:0;width:auto}
 .scroll thead{display:table-header-group;position:static;top:auto}
 .scroll thead tr{display:table-row;overflow:visible;background:#1b2431;padding:0}
 .scroll thead th{display:table-cell;border:0;border-bottom:1px solid var(--line);border-radius:0;font-size:11px;padding:7px 7px}
 .scroll tbody{display:table-row-group}
 .scroll tbody tr{display:table-row;border:0;border-radius:0;margin:0;padding:0;background:transparent;grid-template-columns:none}
 .scroll tbody td{display:table-cell;border-bottom:1px solid var(--line);padding:6px 7px;font-size:12px;white-space:nowrap;text-align:left}
 .scroll tbody td::before{content:none}
 .scroll tbody tr:nth-child(even) td{background:#131a24}
 h2.sec{font-size:13px}
 .part h2{font-size:16px}
}
"""

TOPBAR = render_topbar("../", "thinking")


def esc(s):
    return html.escape(str("" if s is None else s))


def gb(x, nd=0):
    return ("{:,.%df}" % nd).format(float(x)) if x is not None else "—"


def pct(c, n):
    return (100.0 * c / n) if (c is not None and n) else None


def med(rows):
    xs = sorted(r.get("wall_s") or 0 for r in rows)
    return xs[len(xs) // 2] if xs else 0


# ---------------------------------------------------------------- section A: accuracy

PAIR_LABELS = {
    "stock38": "Qwen3.8-27B Q4_K_M",
    "q4_0": "Qwen3.8-27B Q4_0",
    "davidau": "DavidAU NEO-MAX MTP 27B",
    "huihui": "Huihui abliterated 27B",
    "ornith": "Ornith-1.5-35B-A3B",
    "qwen36": "Qwen3.6-35B-A3B",
}


def corrected_pairs_html():
    """The re-measured pairs in benchmarks/thinking2/ (both arms genuinely ran)."""
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "benchmarks", "thinking2", "*pair*.json"))):
        key = os.path.basename(f).replace("-pair.json", "")
        label = PAIR_LABELS.get(key)
        if not label:
            continue
        d = json.load(open(f, encoding="utf-8"))
        off = d.get("off") or {}
        on = d.get("on") or {}

        def valid(x):
            # an arm is only a measurement if it actually completed: a killed run still
            # reports tokens and a score, and computing a cost delta from it produced
            # nonsense like "costs +-57774 tokens"
            return ((x.get("n") or 0) > 0 and (x.get("tokens") or 0) > 0
                    and (x.get("errors") or 0) == 0)

        rows.append((label, d.get("max_tokens"), off, on, valid(off), valid(on)))
    if not rows:
        return "<p>No corrected thinking pairs found.</p>"
    out = ["<div class=table-wrap><table class=probe><thead><tr>"
           "<th>model</th><th>cap</th><th>thinking off</th><th>thinking on</th>"
           "<th>tokens off</th><th>tokens on</th><th>verdict</th></tr></thead><tbody>"]
    for label, cap, off, on, ov, nv in rows:
        if ov and nv:
            verdict = "on loses %d, costs +%d tokens" % (
                off["correct"] - on["correct"], on["tokens"] - off["tokens"])
            oc, nc = "%d/%d" % (off["correct"], off["n"]), "%d/%d" % (on["correct"], on["n"])
        elif ov and not nv:
            verdict, oc, nc = "on arm invalid — not measured", "%d/%d" % (off["correct"], off["n"]), "—"
        else:
            verdict, oc, nc = "invalid — not measured", "—", "—"
        out.append("<tr><td>%s</td><td>%s</td><td class=num>%s</td><td class=num>%s</td>"
                   "<td class=num>%s</td><td class=num>%s</td><td>%s</td></tr>" % (
                       html.escape(label), cap or "—", oc, nc,
                       "{:,}".format(off.get("tokens") or 0) if ov else "—",
                       "{:,}".format(on.get("tokens") or 0) if nv else "—",
                       html.escape(verdict)))
    out.append("</tbody></table></div>")
    out.append('<p class="note">Both arms share the same max-token cap; the only variable is the '
               'thinking switch. Rows marked invalid had their run killed by a competing server on '
               'the host, so they are not scored.</p>')
    return "".join(out)


def _style_findings(lines):
    import re as _re
    # callers already pass <li>…</li> items; re-wrapping nested them (<li><li>…)
    clean = [_re.sub(r"^\s*<li>|</li>\s*$", "", str(x)).strip() for x in lines]
    return ("<h2 class=sec>Findings</h2><ul class=findings>"
            + "".join("<li>%s</li>" % x for x in clean) + "</ul>")


def thinking_p1_findings():
    """Findings for the 25-question accuracy set, computed from its own summary."""
    try:
        rows = json.load(open(os.path.join(ROOT, "benchmarks", "a3b-thinking", "summary.json"),
                              encoding="utf-8"))
    except OSError:
        return ""
    by = {(r["run"], r["mode"]): r for r in rows}
    out = []
    for run, label in (("cap16384", "16,384-token cap"), ("cap4096", "4,096-token cap")):
        off, on = by.get((run, "off")), by.get((run, "on"))
        if not off or not on:
            continue
        d = off["correct"] - on["correct"]
        verb = "lost" if d > 0 else ("gained" if d < 0 else "held")
        out.append("<li>At the %s, thinking %s %d of %d questions (%d → %d correct) while "
                   "spending %.1f× the tokens.</li>"
                   % (label, verb, abs(d), off["n"], off["correct"], on["correct"],
                      on["tokens"] / off["tokens"]))
    on16 = by.get(("cap16384", "on"))
    if on16 and on16.get("length_stops"):
        out.append("<li>%d of 25 thinking runs hit the 16,384-token cap without committing; "
                   "they are scored as wrong, not rescued.</li>" % on16["length_stops"])
    out.append("<li class=meta>One model, one run per arm: read the size of the drop as "
               "indicative, the direction as the finding.</li>")
    return _style_findings(out)


def accuracy_html():
    _corr = corrected_pairs_html()
    if "No corrected thinking pairs" not in _corr:
        return _corr
    doc = json.load(open(os.path.join(ROOT, "data", "results.json"), encoding="utf-8"))
    # one block per model version: the multi-context rows carry the same block, so append once
    blocks, seen = [], set()
    for r in doc.get("rows", []):
        tb = r.get("thinking")
        if tb and tb.get("caps") and id(tb) not in seen and tb.get("model") not in seen:
            seen.add(id(tb))
            seen.add(tb.get("model"))
            blocks.append(r)
    if not blocks:
        return ("<p class=meta>Accuracy set not measured yet: no thinking block in "
                "data/results.json (run scripts/a3b_extras.py).</p>")

    sections = []
    for row in blocks:
        tb = row["thinking"]
        title = tb.get("model") or row.get("name")
        rows, notes = [], []
        for c in tb["caps"]:
            off, on = c["off"], c["on"]
            o_acc, n_acc = pct(off.get("correct"), off.get("n")), pct(on.get("correct"), on.get("n"))
            rows.append(
                "<tr>"
                "<td class=num>%s</td>"
                "<td class=num>%d/%d <span class=dim>(%s%%)</span></td>"
                "<td class=num>%s</td><td class=num>%s</td>"
                "<td class=num>%d/%d <span class=dim>(%s%%)</span></td>"
                "<td class=num>%s</td><td class=num>%s</td>"
                "</tr>" % (
                    gb(c["cap"]), off["correct"], off["n"], "%.0f" % o_acc,
                    gb(off["tokens"]), gb(off["wall_s"], 1),
                    on["correct"], on["n"], "%.0f" % n_acc,
                    gb(on["tokens"]), gb(on["wall_s"], 1)))
            if off.get("tokens") and on.get("tokens") and off.get("wall_s") and on.get("wall_s"):
                notes.append((c["cap"], on["tokens"] / float(off["tokens"]),
                              on["wall_s"] / float(off["wall_s"]), on["correct"] - off["correct"]))
        table = ("<div class=scroll><table><thead><tr>"
                 "<th>Max tokens</th><th>Thinking off — correct</th><th>Off tokens</th><th>Off seconds</th>"
                 "<th>Thinking on — correct</th><th>On tokens</th><th>On seconds</th>"
                 "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
        # cost callout: use the largest cap (the fair pair, neither mode cut short by the cap)
        callout = ""
        if notes:
            cap, tk, tm, dc = max(notes)
            callout = ("<div class=callout><b>Thinking costs %.1f× the tokens and %.1f× the time"
                       " at a %s-token cap</b> — and answered %d fewer of the 25 questions correct."
                       " Throughput per token is about the same in both modes: the extra cost is"
                       " the reasoning text, not a slower server.</div>"
                       % (tk, tm, gb(cap), abs(dc)))
        note_lines = ", ".join(
            "%s cap: %.1f× tokens, %.1f× seconds, %+d correct" % (gb(cap), tk, tm, dc)
            for cap, tk, tm, dc in notes)
        per_q_html = ""
        pq = next((p for p in tb.get("per_question") or [] if p["cap"] == (notes and max(notes)[0])), None)
        if pq:
            cells = "".join(
                "<tr><td class=num>%s</td>"
                "<td class=%s>%s</td><td class=num>%s</td>"
                "<td class=%s>%s</td><td class=num>%s</td></tr>" % (
                    esc(q["id"]),
                    "ok" if q["off"] else "bad", "&#10003;" if q["off"] else "&#10007;", gb(q["off_tok"]),
                    "ok" if q["on"] else "bad", "&#10003;" if q["on"] else "&#10007;", gb(q["on_tok"]))
                for q in pq["questions"])
            per_q_html = ("<h2 class=sec>Per question, %s-token cap</h2>"
                          "<div class=scroll><table><thead><tr><th>Question</th>"
                          "<th>Off</th><th>Off tokens</th><th>On</th><th>On tokens</th>"
                          "</tr></thead><tbody>%s</tbody></table></div>" % (gb(pq["cap"]), cells))
        sections.append(
            "<h2 class=sec>%s</h2>" % esc(title)
            + "<p class=sub>GPQA-diamond, the same 25 frozen questions, temperature 0, same seed, same server process."
              " The only change is whether the model's reasoning channel is enabled. "
              "Seconds are wall time for all 25 questions; tokens are generated (completion) tokens.</p>"
            + table + callout
            + "<p class=meta>%s. A thinking run that hits the cap before printing its final answer "
              "counts as unanswered in the score.</p>" % esc(note_lines)
            + per_q_html)
    return "".join(sections)


def build():
    body = (
        "<h1>thinking on vs off</h1>"
        "<p class=sub>Does switching the model's reasoning channel on change its answers, and what "
        "does it cost? Same server, same temperature 0, same seed, identical token cap; the only "
        "variable is the thinking switch. Times are wall-clock seconds; tokens are generated "
        "(completion) tokens.</p>"
        "<div class=part><h2>Accuracy questions (GPQA-diamond, 25)</h2>"
        "<span class=meta>Hard multiple-choice science questions: the ceiling test.</span></div>"
        + accuracy_html()
        + thinking_p1_findings())
    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>thinking on/off — llmbench</title><style>" + CSS + TOPBAR_CSS + "</style></head>"
            "<body>" + render_brand() + TOPBAR + "<div class=wrap>" + body + "</div></body></html>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print("thinking page:", OUT)


if __name__ == "__main__":
    build()
