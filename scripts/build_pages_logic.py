#!/usr/bin/env python3
"""build_pages_logic.py — the "logic traps" tab.

Source of truth: benchmarks/logic10/results/<slug>.json (one file per model, written by
benchmarks/logic10/logic10.py) plus benchmarks/logic10/questions.json (order, wording,
trap types, contamination flags). Writes logic/index.html. Nothing on this page is typed
by hand: every number is read from a result file, and a model with a missing or incomplete
arm is shown as "not run" rather than scored.

Columns: off score, on score, delta, tokens off/on, wall off/on, per-question matrix.
"""
import glob, sys
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_nav import render_nav, render_topbar, render_brand, TOPBAR_CSS  # noqa: E402  single source of truth for the nav
SRC = os.path.join(ROOT, "benchmarks", "logic10")
QFILE = os.path.join(SRC, "questions.json")
RESDIR = os.path.join(SRC, "results")
OUTDIR = os.path.join(ROOT, "logic")
OUT = os.path.join(OUTDIR, "index.html")

# display labels only; model identity never reaches the page beyond these names
LABEL = {
    "lfm3-1-7b-q4-k-m": "LFM3-1.7B",
    "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B",
    "qwen3-8-27b-q4km": "Qwen3.8-27B (Q4_K_M)",
    "qwen3-8-27b-q4-0": "Qwen3.8-27B (Q4_0)",
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": "DavidAU Qwen3.8-27B NEO-MAX",
    "huihui-abl-q4-k-m": "Huihui abliterated 27B",
    "ornith-1-5-35b-a3b-q4-k-m": "Ornith-1.5-35B-A3B",
    "lfm3-1-7b-q4-k-m": "LFM3-1.7B",
}
ORDER = ["qwen3-6-35b-a3b-ud-q4km", "qwen3-8-27b-q4km", "qwen3-8-27b-q4-0",
         "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m", "huihui-abl-q4-k-m",
         "ornith-1-5-35b-a3b-q4-k-m", "lfm3-1-7b-q4-k-m"]

CLASSIC = {"batball", "widgets", "lilypad"}

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:clip}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}
h2.sec{margin:30px 0 8px;font-size:14px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--dim);margin:0 0 14px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}
.tabs a{padding:6px 12px;border:1px solid var(--line);border-radius:8px;color:var(--dim);text-decoration:none;font-size:13px;min-height:32px;display:inline-flex;align-items:center}
.tabs a.on{background:#1b2431;color:var(--fg);border-color:#33506b}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{width:100%;border-collapse:collapse;background:var(--panel)}
th,td{padding:8px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
thead th{background:#1b2431;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
tbody tr:nth-child(even) td{background:#131a24}
td.num,th.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--gold)}.dim{color:var(--faint)}
.callout{border-left:3px solid var(--gold);background:#1a1f27;padding:10px 14px;border-radius:6px;margin:14px 0}
.callout b{color:var(--gold)}
.meta{color:var(--faint);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 12px;font-size:12px;color:var(--dim)}
.legend span b{font-weight:600}
.matrix td.c{text-align:center;font-family:ui-monospace,monospace;font-size:13px}
.matrix td.t{min-width:9.5em;white-space:nowrap}
.qtext{color:var(--faint);font-size:11px;display:block;max-width:34ch}
details{margin:10px 0}
summary{cursor:pointer;color:var(--blue);font-size:13px}
pre{white-space:pre-wrap;word-break:break-word;font:12px/1.45 ui-monospace,monospace;color:var(--dim);background:#111821;border:1px solid var(--line);border-radius:8px;padding:9px;max-height:220px;overflow:auto;margin:6px 0 12px}
/* On a phone the shared style.css turns every table into a label-less card stack.
   These tables are matrices, so restore a real table that scrolls inside its own box
   (the page itself must never scroll sideways). */
@media(max-width:760px){
 .wrap{padding:18px 10px 48px}
 .scroll{overflow-x:auto}
 .scroll table{display:table;min-width:0;width:auto}
 .scroll thead{display:table-header-group;position:static}
 .scroll thead tr{display:table-row;overflow:visible;background:#1b2431;padding:0}
 .scroll thead th{display:table-cell;border:0;border-bottom:1px solid var(--line)}
 .scroll tbody{display:table-row-group}
 .scroll tbody tr{display:table-row;border:0;border-radius:0;margin:0;padding:0;background:transparent}
 .scroll tbody td{display:table-cell;border-bottom:1px solid var(--line);padding:6px 7px;font-size:12px}
 .scroll tbody td::before{content:none}
 .scroll tbody tr:nth-child(even) td{background:#131a24}
 .summary th,.summary td{white-space:nowrap}
 .matrix th,.matrix td{white-space:nowrap}
 .matrix td.t{font-size:11.5px}
 .scroll{position:relative}
 .scroll::after{content:"scroll \2192";position:absolute;right:6px;top:6px;font:600 9.5px/1 var(--mono,#9fb0c6);letter-spacing:.06em;color:#9fb0c6;background:#1b243180;padding:3px 5px;border-radius:4px;pointer-events:none}
 details ul{padding-left:1.1rem}
 details li{font-size:12.5px}
}
"""

TOPBAR = render_topbar("../", "logic")

SHORT = {"wash": "car wash", "race": "race", "batball": "bat+ball", "widgets": "widgets",
         "lilypad": "lily pads", "pills": "pills", "months": "months", "ladder": "ladder",
         "coins": "coins", "discount": "discount"}


def esc(s):
    return html.escape(str("" if s is None else s))


def med(rows):
    xs = sorted(r.get("wall_s") or 0 for r in rows)
    return xs[len(xs) // 2] if xs else 0


def load():
    out = {}
    for f in glob.glob(os.path.join(RESDIR, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        slug = d.get("slug") or os.path.basename(f)[:-5]
        out[slug] = d
    return out


def arm_stats(blk):
    """Scored accuracy plus the truncation caveat. Returns None if the arm never ran."""
    if not blk or not blk.get("rows"):
        return None
    s = blk.get("summary") or {}
    scored = s.get("scored", 0)
    corr = s.get("correct", 0)
    rows = blk["rows"]
    return {"n": s.get("n", len(rows)), "scored": scored, "correct": corr,
            "wrong": s.get("wrong", 0), "truncated": s.get("truncated", 0),
            "errors": s.get("errors", 0), "tokens": s.get("tokens", 0),
            "wall_s": s.get("wall_s", 0), "max_tokens": s.get("max_tokens"),
            "len_stops": sum(1 for r in rows if r.get("finish_reason") == "length"),
            "len_stops_answered": sum(1 for r in rows if r.get("finish_reason") == "length"
                                      and r.get("verdict") == "correct"),
            "rows": {r["id"]: r for r in rows}}


def cell(r):
    if r is None:
        return "<td class='c dim'>—</td>"
    v = r.get("verdict")
    if v == "correct":
        if r.get("finish_reason") == "length":
            return ("<td class='c ok' title='answered %s, then kept talking past the token cap'>"
                    "&#10003;<sup class=warn>L</sup></td>" % esc((r.get("answer_raw") or "")[:70]))
        return "<td class='c ok' title='%s'>&#10003;</td>" % esc((r.get("answer_raw") or "")[:80])
    if v == "truncated":
        return "<td class='c warn' title='hit the token cap before answering'>T</td>"
    if v == "error":
        return "<td class='c dim' title='%s'>E</td>" % esc(r.get("error") or "")
    return "<td class='c bad' title='%s'>&#10007;</td>" % esc((r.get("answer_raw") or r.get("note") or "")[:80])


def name(slug):
    return LABEL.get(slug, slug)


def served_label(d, slug):
    """Weights the server reported for this run (falls back to the slug's own name)."""
    served = d.get("model_served") or d.get("model") or ""
    base = os.path.basename(served).replace(".gguf", "") if served else ""
    return base or slug


def served_name(d):
    """Display name derived from the weights the server actually reported (never typed)."""
    m = (d.get("model") or "")
    base = os.path.basename(m)
    t = d.get("model_served") or ""
    if t:
        base = os.path.basename(t)
    base = base.replace(".gguf", "")
    for key, lab in LABEL.items():
        if key and key.split("-")[0] in base.lower():
            return lab
    return base or "unidentified model"


def weight_warning(d):
    """If the run recorded which weights it expected, confirm the served file matched."""
    exp = d.get("expected_model")
    if not exp:
        return "" if (d.get("model_served") or d.get("model")) else (
            "<span class='warn' title='run record does not name the served weights'>weights not recorded</span>")
    served = d.get("model_served") or d.get("model") or ""
    if exp.lower() in served.lower():
        return ""
    return ("<span class='warn' title='the server was serving different weights than this row "
            "was meant to benchmark'>weights mismatch</span>")


def build():
    qd = json.load(open(QFILE, encoding="utf-8"))
    QS = qd["questions"]
    data = load()
    slugs = [s for s in ORDER if s in data] + [s for s in data if s not in ORDER]
    maxcap = max((int(d.get("max_tokens_both_modes") or 0) for d in data.values()), default=0)

    # ---- summary table
    srows = []
    for slug in slugs:
        d = data[slug]
        off = arm_stats(d.get("modes", {}).get("off"))
        on = arm_stats(d.get("modes", {}).get("on"))
        cells = ["<td><b>%s</b></td>" % esc(name(slug))]
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
        cells.append("<td class='num'>%s</td>" % ("—" if not off else f"{off['tokens']:,}"))
        cells.append("<td class='num'>%s</td>" % ("—" if not on else f"{on['tokens']:,}"))
        cells.append("<td class='num' title='median seconds per question'>%s</td>"
                     % ("—" if not off else "%.1f" % med(list(off["rows"].values()))))
        cells.append("<td class='num' title='median seconds per question'>%s</td>"
                     % ("—" if not on else "%.1f" % med(list(on["rows"].values()))))
        cells.append("<td class='num'>%s</td>"
                     % ("—" if not (off and on) else "%d / %d" % (off["len_stops"], on["len_stops"])))
        cells[0] = ("<td><b>%s</b><br><span class=meta>%s</span> %s</td>"
                    % (esc(name(slug)), esc(served_label(d, slug)), weight_warning(d)))
        srows.append("<tr>" + "".join(cells) + "</tr>")

    summary = ("<div class=scroll><table class=summary><thead><tr><th>Model</th><th class=num>Off</th>"
               "<th class=num>On</th><th class=num>&Delta;</th><th class=num>Tokens off</th>"
               "<th class=num>Tokens on</th><th class=num>s/question off</th>"
               "<th class=num>s/question on</th><th class=num title='requests that ran into the token cap "
               "(the question is still scored if the model had already committed to an answer)'>Cap hits off/on</th>"
               "</tr></thead><tbody>"
               + "".join(srows) + "</tbody></table></div>")

    # ---- per-trap letter table
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
        mrows.append("<tr><td class=t><b>%s</b></td>%s</tr>" % (esc(name(slug)), "".join(cells)))
    matrix = ("<div class=scroll><table class=matrix><thead><tr><th>Trap (off / on)</th>%s</tr></thead><tbody>%s"
              "</tbody></table></div>" % (hdr, "".join(mrows)))

    # ---- per-model trap notes + raw answers
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
                label, a["correct"], a["scored"],
                ", ".join(missed) or "nothing",
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
            % (esc(name(slug)), "".join(lines), "".join(raw)))

    # ---- trap definitions
    qrows = []
    for i, q in enumerate(QS, 1):
        qrows.append("<tr><td class=num>%d</td><td class=q>%s</td><td>%s</td>"
                     "<td class=meta>%s</td><td>%s</td></tr>"
                     % (i, esc(q["q"]), esc(q["trap"]), esc(", ".join(q["accept"][:3]))
                        + (" …" if len(q["accept"]) > 3 else ""),
                        "<span class=warn>classic CRT *</span>" if q["id"] in CLASSIC else "fresh"))

    n_models = sum(1 for s in slugs if arm_stats(data[s].get("modes", {}).get("off"))
                   and arm_stats(data[s].get("modes", {}).get("on")))
    body = (
        "<p class=sub>Ten one-line questions people actually ask, each with an obvious-looking wrong answer. "
        "Every model answers all ten twice: once with its reasoning channel disabled, once enabled. "
        "The only difference between the two arms is the thinking switch — same server, same temperature 0, "
        "same fixed seed, same token cap (%s), one question per request, fresh context, no examples. "
        "Grading is strict: the model's final <code>Answer:</code> line must match the expected answer exactly. "
        "No partial credit. A model that runs out of tokens before committing to an answer is marked "
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
        + "<p class=meta>Each cell reads <b>off / on</b>. Hover a cell for the answer the model actually gave. "
          "%d of %d models completed both arms.</p>" % (n_models, len(slugs))
        + "<h2 class=sec>Per-model detail</h2>" + "".join(details)
        + "<h2 class=sec>The ten questions</h2>"
        "<div class=scroll><table><thead><tr><th>#</th><th>Question</th><th>Trap</th>"
        "<th>Accepted answer (first forms)</th><th>Type</th></tr></thead><tbody>"
        + "".join(qrows) + "</tbody></table></div>"
        "<p class=meta>Method and question file: <code>benchmarks/logic10/</code> in the source repo. "
        "Raw per-question JSON per model is checked in beside the harness. "
        "Scoring is mechanical and re-runnable from those files.</p>")

    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>logic traps — llmbench</title><style>" + CSS + TOPBAR_CSS + "</style></head>"
            "<body>" + render_brand() + TOPBAR + "<div class=wrap><h1>everyday logic traps</h1>" + body
            + "</div></body></html>")
    os.makedirs(OUTDIR, exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print("logic page:", OUT, "| models:", len(slugs), "| both arms:", n_models)


if __name__ == "__main__":
    build()
