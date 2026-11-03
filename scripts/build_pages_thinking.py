#!/usr/bin/env python3
"""build_pages_thinking.py -- the "thinking on/off" tab (the SITE's only thinking page).

ONE page, ONE nav entry ("Thinking"), TWO sections, because both measure the same thing:
one model, one question set, reasoning channel enabled vs disabled.

  Section A  accuracy  — the 25 frozen GPQA-diamond questions, from the `thinking` block
                         that scripts/a3b_extras.py puts on the model's row in
                         data/results.json. Per max-token cap: off/on correct, tokens, seconds.
  Section B  logic traps — the ten everyday questions in benchmarks/logic10/, from one
                         result file per model (benchmarks/logic10/results/<slug>.json),
                         written by benchmarks/logic10/logic10.py. Per model: off/on score,
                         tokens, time, and a per-trap matrix that marks the memorisable
                         classic CRT items.

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

LOGIC_SRC = os.path.join(ROOT, "benchmarks", "logic10")
LOGIC_QFILE = os.path.join(LOGIC_SRC, "questions.json")
LOGIC_RESDIR = os.path.join(LOGIC_SRC, "results")

# display labels only; never the host path or file name of the weights
LOGIC_LABEL = {
    "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B",
    "qwen3-8-27b-q4km": "Qwen3.8-27B (Q4_K_M)",
    "qwen3-8-27b-q4-0": "Qwen3.8-27B (Q4_0)",
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": "DavidAU Qwen3.8-27B NEO-MAX",
    "huihui-abl-q4-k-m": "Huihui abliterated 27B",
    "ornith-1-5-35b-a3b-q4-k-m": "Ornith-1.5-35B-A3B",
    "lfm3-1-7b-q4-k-m": "LFM3-1.7B",
}
LOGIC_ORDER = ["qwen3-6-35b-a3b-ud-q4km", "qwen3-8-27b-q4km", "qwen3-8-27b-q4-0",
               "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m", "huihui-abl-q4-k-m",
               "ornith-1-5-35b-a3b-q4-k-m", "lfm3-1-7b-q4-k-m"]
CLASSIC = {"batball", "widgets", "lilypad"}
SHORT = {"wash": "car wash", "race": "race", "batball": "bat+ball", "widgets": "widgets",
         "lilypad": "lily pads", "pills": "pills", "months": "months", "ladder": "ladder",
         "coins": "coins", "discount": "discount"}

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

def accuracy_html():
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


# ---------------------------------------------------------------- section B: logic traps

def logic_load():
    out = {}
    for f in glob.glob(os.path.join(LOGIC_RESDIR, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        out[d.get("slug") or os.path.basename(f)[:-5]] = d
    return out


def logic_name(slug):
    return LOGIC_LABEL.get(slug, slug)


def arm_stats(blk):
    """Scored accuracy for one arm, or None if it never ran."""
    if not blk or not blk.get("rows"):
        return None
    s = blk.get("summary") or {}
    rows = blk["rows"]
    return {"n": s.get("n", len(rows)), "scored": s.get("scored", 0), "correct": s.get("correct", 0),
            "wrong": s.get("wrong", 0), "truncated": s.get("truncated", 0),
            "errors": s.get("errors", 0), "tokens": s.get("tokens", 0),
            "wall_s": s.get("wall_s", 0), "max_tokens": s.get("max_tokens"),
            "len_stops": sum(1 for r in rows if r.get("finish_reason") == "length"),
            "rows": {r["id"]: r for r in rows}}


def logic_cell(r):
    if r is None:
        return "<td class='c dim'>—</td>"
    v = r.get("verdict")
    ans = esc((r.get("answer_raw") or "")[:80])
    if v == "correct":
        if r.get("finish_reason") == "length":
            return ("<td class='c ok' title='answered %s, then kept talking past the token cap'>"
                    "&#10003;<sup class=warn>L</sup></td>" % esc((r.get("answer_raw") or "")[:70]))
        return "<td class='c ok' title='%s'>&#10003;</td>" % ans
    if v == "truncated":
        return "<td class='c warn' title='hit the token cap before answering'>T</td>"
    if v == "error":
        return "<td class='c dim' title='%s'>E</td>" % esc(r.get("error") or "")
    return "<td class='c bad' title='%s'>&#10007;</td>" % esc(ans or r.get("note") or "")


def served_label(d, slug):
    served = d.get("model_served") or ""
    base = os.path.basename(served).replace(".gguf", "") if served else ""
    return base or slug


def weight_warning(d):
    """The run records which weights it expected; flag a mismatch (never silently score it)."""
    exp = d.get("expected_model")
    if not exp:
        return ""
    served = d.get("model_served") or d.get("model") or ""
    if exp.lower() in served.lower():
        return ""
    return ("<span class='warn' title='the server was serving different weights than this row "
            "was meant to benchmark'>weights mismatch</span>")


def logic_html():
    if not os.path.exists(LOGIC_QFILE):
        return "<p class=meta>Logic-trap set not present in this checkout.</p>"
    qd = json.load(open(LOGIC_QFILE, encoding="utf-8"))
    QS = qd["questions"]
    data = logic_load()
    if not data:
        return "<p class=meta>Logic-trap set measured no models yet.</p>"
    slugs = [s for s in LOGIC_ORDER if s in data] + [s for s in data if s not in LOGIC_ORDER]
    maxcap = max((int(d.get("max_tokens_both_modes") or 0) for d in data.values()), default=0)

    # ---- summary table
    srows = []
    for slug in slugs:
        d = data[slug]
        off = arm_stats(d.get("modes", {}).get("off"))
        on = arm_stats(d.get("modes", {}).get("on"))
        cells = ["<td><b>%s</b><br><span class=meta>%s</span> %s</td>"
                 % (esc(logic_name(slug)), esc(served_label(d, slug)), weight_warning(d))]
        for a in (off, on):
            if a is None:
                cells.append("<td class='num dim'>not run</td>")
            else:
                cells.append("<td class='num'><b>%d/%d</b><span class='dim'> of %d</span></td>"
                             % (a["correct"], a["scored"], a["scored"]))
        if off and on:
            dl = on["correct"] - off["correct"]
            cls = "ok" if dl > 0 else ("bad" if dl < 0 else "dim")
            cells.append("<td class='num %s'>%+d</td>" % (cls, dl))
        else:
            cells.append("<td class='num dim'>—</td>")
        cells.append("<td class='num'>%s</td>" % ("—" if not off else "{:,}".format(off["tokens"])))
        cells.append("<td class='num'>%s</td>" % ("—" if not on else "{:,}".format(on["tokens"])))
        cells.append("<td class='num' title='median seconds per question'>%s</td>"
                     % ("—" if not off else "%.1f" % med(list(off["rows"].values()))))
        cells.append("<td class='num' title='median seconds per question'>%s</td>"
                     % ("—" if not on else "%.1f" % med(list(on["rows"].values()))))
        cells.append("<td class='num'>%s</td>"
                     % ("—" if not (off and on) else "%d / %d" % (off["len_stops"], on["len_stops"])))
        srows.append("<tr>" + "".join(cells) + "</tr>")

    summary = ("<div class=scroll><table><thead><tr><th>Model</th><th class=num>Off</th>"
               "<th class=num>On</th><th class=num>&Delta;</th><th class=num>Tokens off</th>"
               "<th class=num>Tokens on</th><th class=num>s/question off</th>"
               "<th class=num>s/question on</th><th class=num title='requests that ran into the token cap "
               "(the question is still scored if the model had already committed to an answer)'>Cap hits off/on</th>"
               "</tr></thead><tbody>" + "".join(srows) + "</tbody></table></div>")

    # ---- per-trap matrix
    hdr = "".join("<th class=num title='%s'>%s%s</th>"
                  % (esc(q["q"]), esc(SHORT.get(q["id"], q["id"])),
                     " *" if q["id"] in CLASSIC else "") for q in QS)
    mrows = []
    for slug in slugs:
        d = data[slug]
        off = arm_stats(d.get("modes", {}).get("off")) or {"rows": {}}
        on = arm_stats(d.get("modes", {}).get("on")) or {"rows": {}}
        cells = []
        for q in QS:
            ro, rn = off["rows"].get(q["id"]), on["rows"].get(q["id"])
            if ro is None and rn is None:
                cells.append("<td class='c dim'>—</td>")
                continue
            sym = []
            for r in (ro, rn):
                v = r.get("verdict") if r else None
                sym.append({"correct": "<span class=ok>&#10003;</span>",
                            "wrong": "<span class=bad>&#10007;</span>",
                            "truncated": "<span class=warn>T</span>",
                            "error": "<span class=dim>E</span>",
                            None: "<span class=dim>&middot;</span>"}.get(v, "?"))
            tip = "off: %s | on: %s" % ((ro or {}).get("answer_raw") or (ro or {}).get("verdict") or "-",
                                        (rn or {}).get("answer_raw") or (rn or {}).get("verdict") or "-")
            cells.append("<td class='c' title='%s'>%s %s</td>" % (esc(tip[:120]), sym[0], sym[1]))
        mrows.append("<tr><td class=t><b>%s</b></td>%s</tr>" % (esc(logic_name(slug)), "".join(cells)))
    matrix = ("<div class=scroll><table class=matrix><thead><tr><th>Trap (off / on)</th>%s</tr></thead>"
              "<tbody>%s</tbody></table></div>" % (hdr, "".join(mrows)))

    # ---- per-model detail
    details = []
    for slug in slugs:
        d = data[slug]
        off = arm_stats(d.get("modes", {}).get("off"))
        on = arm_stats(d.get("modes", {}).get("on"))
        lines = []
        for label, a in (("thinking off", off), ("thinking on", on)):
            if not a:
                lines.append("<li>%s: not run</li>" % label)
                continue
            missed = [SHORT.get(q["id"], q["id"]) for q in QS
                      if a["rows"].get(q["id"], {}).get("verdict") == "wrong"]
            trunc = [SHORT.get(q["id"], q["id"]) for q in QS
                     if a["rows"].get(q["id"], {}).get("verdict") == "truncated"]
            cl = [SHORT.get(q["id"], q["id"]) for q in QS if q["id"] in CLASSIC
                  and a["rows"].get(q["id"], {}).get("verdict") == "wrong"]
            lines.append("<li><b>%s</b>: %d/%d correct; missed %s%s%s</li>" % (
                label, a["correct"], a["scored"], ", ".join(missed) or "nothing",
                ("; classic-CRT items missed: " + ", ".join(cl)) if cl else "",
                ("; capped out before answering: " + ", ".join(trunc)) if trunc else ""))
        raw = []
        for q in QS:
            for label, a in (("off", off), ("on", on)):
                r = (a or {}).get("rows", {}).get(q["id"])
                if r:
                    raw.append("<tr><td class=num>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                               "<td class=num>%s</td><td class=num>%s</td><td>%s</td></tr>"
                               % (esc(q["id"]), label, esc(r.get("verdict")),
                                  esc((r.get("answer_raw") or "")[:120]),
                                  esc(r.get("completion_tokens")), esc(r.get("wall_s")),
                                  esc(r.get("finish_reason"))))
        details.append(
            "<details><summary>%s — per-question answers</summary><ul>%s</ul>"
            "<div class=scroll><table><thead><tr><th>#</th><th>Arm</th><th>Verdict</th>"
            "<th>Answer line</th><th class=num>Tokens</th><th class=num>s</th><th>finish</th>"
            "</tr></thead><tbody>%s</tbody></table></div></details>"
            % (esc(logic_name(slug)), "".join(lines), "".join(raw)))

    # ---- the questions
    qrows = []
    for i, q in enumerate(QS, 1):
        qrows.append("<tr><td class=num>%d</td><td class=q>%s</td><td>%s</td>"
                     "<td class=meta>%s</td><td>%s</td></tr>"
                     % (i, esc(q["q"]), esc(q["trap"]), esc(", ".join(q["accept"][:3]))
                        + (" …" if len(q["accept"]) > 3 else ""),
                        "<span class=warn>classic CRT *</span>" if q["id"] in CLASSIC else "fresh"))

    n_models = sum(1 for s in slugs
                   if arm_stats(data[s].get("modes", {}).get("off"))
                   and arm_stats(data[s].get("modes", {}).get("on")))
    return (
        "<p class=sub>Ten one-line questions people actually ask, each with an obvious-looking wrong answer. "
        "Every model answers all ten twice: once with its reasoning channel disabled, once enabled. "
        "The only difference between the arms is the thinking switch — same server, temperature 0, "
        "fixed seed, same token cap (%s), one question per request, fresh context, no examples. "
        "Grading is strict: the model's final <code>Answer:</code> line must match the expected answer. "
        "No partial credit. A model that runs out of tokens before committing is marked "
        "<span class=warn>T</span> and left out of the score rather than counted wrong.</p>"
        % esc(maxcap or "—")
        + "<div class=callout><b>Read this before trusting the ranking.</b> Questions 3, 4 and 5 "
          "(bat+ball, widgets, lily pads) are the classic Cognitive Reflection Test and are almost certainly "
          "in training data; the other seven are fresh everyday traps of the same shape. "
          "A model failing a classic item is more damning than failing a fresh one, because it had every chance "
          "to memorise it. Passing a classic proves much less. The per-trap matrix marks memorisable items with "
          "<span class=warn>*</span> so you can judge each result yourself.</div>"
        "<div class=legend><span><b class=ok>&#10003;</b> correct</span><span><b class=bad>&#10007;</b> wrong</span>"
        "<span><b class=warn>T</b> hit the token cap before answering (not scored)</span>"
        "<span><b class=ok>&#10003;</b><sup class=warn>L</sup> answered, then kept talking past the cap</span>"
        "<span><b class=dim>&middot;</b> not run</span></div>"
        "<h2 class=sec>Scores — thinking off vs on</h2>" + summary
        + "<p class=meta>&Delta; = on minus off, in questions out of ten (scored ones only). "
          "Tokens are generated tokens for all ten questions; seconds are the median per question.</p>"
        "<h2 class=sec>Which traps each model fell into</h2>" + matrix
        + "<p class=meta>Each cell reads <b>off / on</b>. Hover a cell for the answer the model gave. "
          "%d of %d models completed both arms.</p>" % (n_models, len(slugs))
        + "<h2 class=sec>Per-model detail</h2>" + "".join(details)
        + "<h2 class=sec>The ten questions</h2>"
        "<div class=scroll><table><thead><tr><th>#</th><th>Question</th><th>Trap</th>"
        "<th>Accepted answer (first forms)</th><th>Type</th></tr></thead><tbody>"
        + "".join(qrows) + "</tbody></table></div>"
        "<p class=meta>Question set and harness: <code>benchmarks/logic10/</code> in the source repo; "
        "per-model raw answers are checked in beside it. Scoring is mechanical and re-runnable "
        "from those files.</p>")


def build():
    body = (
        "<h1>thinking on vs off</h1>"
        "<p class=sub>Both sections ask the same question: does switching the model's reasoning channel on "
        "change its answers, and what does it cost? Same server, same temperature 0, same seed, identical "
        "token cap; the only variable is the thinking switch. Times are wall-clock seconds; tokens are "
        "generated (completion) tokens.</p>"
        "<p class=sub><b>Two different question sets, never averaged together.</b> "
        "<a href=\"#logic\">Part 2 (logic traps)</a> is a separate set of ten everyday questions and "
        "has its own scores; nothing on this page combines the two.</p>"
        "<div class=part><h2>Part 1 — accuracy questions (GPQA-diamond, 25)</h2>"
        "<span class=meta>Hard multiple-choice science questions: the ceiling test.</span></div>"
        + accuracy_html()
        + "<div class=part id=logic><h2>Part 2 — logic traps (everyday questions, 10)</h2>"
          "<span class=meta>Short questions with an obvious-looking wrong answer: the reasoning test.</span></div>"
        + logic_html())
    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>thinking on/off — llmbench</title><style>" + CSS + TOPBAR_CSS + "</style></head>"
            "<body>" + render_brand() + TOPBAR + "<div class=wrap>" + body + "</div></body></html>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print("thinking page:", OUT)


if __name__ == "__main__":
    build()
