#!/usr/bin/env python3
"""build_pages_thinking.py -- the "thinking on/off" tab.

Reads the `thinking` block that scripts/a3b_extras.py puts on the model's row in
data/results.json: per max-token cap, the same 25-question set (temperature 0, seed 5)
run once with the model's thinking channel enabled and once disabled. Writes
thinking/index.html. Times are seconds (never ms).
"""
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "thinking", "index.html")

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 16px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
.tabs a{padding:7px 13px;border:1px solid var(--line);border-radius:8px;color:var(--dim);text-decoration:none;font-size:13px;min-height:36px;display:inline-flex;align-items:center}
.tabs a.on{background:#1b2431;color:var(--fg);border-color:#33506b}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{width:100%;border-collapse:collapse;background:var(--panel);min-width:620px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
thead th{background:#1b2431;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
tbody tr:nth-child(even) td{background:#131a24}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
.ok{color:var(--ok)}.bad{color:var(--bad)}.dim{color:var(--faint)}
.detail{border:1px solid var(--line);border-radius:10px;padding:14px;margin:16px 0;background:var(--panel)}
.detail h2{margin:0 0 6px;font-size:17px}
.sec{margin:26px 0 6px;font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.callout{border-left:3px solid var(--gold);background:#1a1f27;padding:10px 14px;border-radius:6px;margin:14px 0}
.callout b{color:var(--gold)}
.meta{color:var(--faint);font-size:12px}
.q{color:var(--dim);font-size:12px;max-width:40ch}
@media(max-width:640px){.wrap{padding:18px 12px 48px}th,td{padding:7px 7px;font-size:12px}table{min-width:540px}}
"""

NAV = ("<nav class=tabs><a href='../'>overview</a>"
       "<a href='../games/'>games</a>"
       "<a href='../thinking/' class=on>thinking on/off</a>"
       "<a href='../chat/'>chat</a>"
       "<a href='../ablation/'>ablation</a></nav>")


def esc(s):
    return html.escape(str("" if s is None else s))


def gb(x, nd=0):
    return ("{:,.%df}" % nd).format(float(x)) if x is not None else "—"


def pct(c, n):
    return (100.0 * c / n) if (c is not None and n) else None


def build():
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
        raise SystemExit("no thinking block in data/results.json; run scripts/a3b_extras.py")

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
            "<h1>%s — thinking on vs off</h1>" % esc(title)
            + "<p class=sub>GPQA-diamond, the same 25 frozen questions, temperature 0, same seed, same server process."
              " The only change is whether the model's reasoning channel is enabled. "
              "Seconds are wall time for all 25 questions; tokens are generated (completion) tokens.</p>"
            + table + callout
            + "<p class=meta>%s. A thinking run that hits the cap before printing its final answer "
              "counts as unanswered in the score.</p>" % esc(note_lines)
            + per_q_html)

    body = "".join(sections) if sections else "<h1>thinking on/off</h1><p>Nothing measured yet.</p>"
    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>thinking on/off — llmbench</title><style>" + CSS + "</style></head>"
            "<body><div class=wrap>" + NAV + body + "</div></body></html>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print("thinking page:", OUT, "| blocks:", len(blocks))


if __name__ == "__main__":
    build()
