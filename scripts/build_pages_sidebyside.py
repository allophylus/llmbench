#!/usr/bin/env python3
"""build_pages_sidebyside.py — generate games/sidebyside/index.html from recorded results.

Rows = the 4 suite specs, columns = models. Each cell shows the playable game in an
iframe (or its screenshot when it never ran), the score badges (assertions passed,
spec compliance, attempts, build seconds on the accepted attempt) and a link to the
full attempt history (the per-cell build.json).

Every number is read from games/suite/out/<slug>/<spec>/build.json. A cell with no
build.json is shown as "not run" — never as a zero.

Visitor-facing text is generic: model display names and file names only (from
games/models.json), no hostnames, IPs, /home paths, GGUF-serving symlinks or third-party
video hosts. The page must stay readable at 400 px: the matrix scrolls horizontally,
each column is fixed-width, and a stacked card list below repeats every cell for narrow
screens.
"""
import glob
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_nav import render_nav, render_topbar, render_brand, TOPBAR_CSS  # noqa: E402  single source of truth for the nav
GAMES = os.path.join(ROOT, "games")
OUT = os.path.join(GAMES, "suite", "out")
DEST = os.path.join(GAMES, "sidebyside")

SPECS = [
    ("ball-drop-sandbox", "ball drop sandbox",
     "25 balls dropped into a glass box: gravity, restitution, ball-to-ball collisions. "
     "Deterministic seed, no player input beyond pause."),
    ("tower-stacker", "tower stacker",
     "20 blocks dropped at seeded offsets: stacking, friction, and a tower that must not "
     "topple from jitter or drift."),
    ("tower-defence", "tower defence",
     "A fixed path, five fixed waves, finite gold and one automatic build policy — no "
     "tower spam, exact economy."),
    ("match3-cascades", "match 3 cascades",
     "8x8 seeded board, adjacent swaps, cascades resolved until the board is stable, a "
     "stated numeric scoring rule."),
]

MODEL_NAME = {
    "qwen3-8-27b-q4km": ("Qwen3.8-27B Q4_K_M", "Qwen3.8-27B-Q4_K_M.gguf"),
    "qwen3-8-27b-q4-0": ("Qwen3.8-27B Q4_0", "Qwen3.8-27B-Q4_0.gguf"),
    "qwen3-6-35b-a3b-ud-q4km": ("Qwen3.6-35B-A3B Q4_K_M", "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"),
    "davidau-qwen3-8-27b-neo-max-mtp-q4-k-m": ("Qwen3.8-27B NEO-MAX (community finetune)", "NEO-MAX-MTP-Q4_K_M.gguf"),
    "huihui-abl-q4-k-m": ("Qwen3.8-27B abliterated (community)", "Huihui-abl-Q4_K_M.gguf"),
    "ornith-1-5-35b-a3b-q4-k-m": ("Ornith-1.5-35B-A3B Q4_K_M", "Ornith-1.5-35B-Q4_K_M.gguf"),
    "lfm3-1-7b-q4-k-m": ("LFM3-1.7B Q4_K_M", "LFM3-1.7B-Q4_K_M.gguf"),
}
ORDER = list(MODEL_NAME)


def esc(s):
    return html.escape(str(s if s is not None else ""))


def name(slug):
    return MODEL_NAME.get(slug, (slug, ""))[0]


def load(slug, spec):
    p = os.path.join(OUT, slug, spec, "build.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(open(p))
    except Exception:
        return None


def accepted(b):
    if not b or not b.get("per_attempt"):
        return None
    n = b.get("accepted_attempt") or b.get("best_attempt")
    if not n:
        return None
    for a in b["per_attempt"]:
        if a.get("attempt") == n:
            return a
    return None


def build_seconds(b):
    """Wall time of the accepted attempt + all repair turns before it."""
    if not b:
        return None
    n = b.get("accepted_attempt") or b.get("best_attempt")
    if not n:
        return None
    tot = sum((a.get("wall_s") or 0) for a in b["per_attempt"] if (a.get("attempt") or 0) <= n)
    return round(tot, 1)


def tokens(b):
    n = b.get("accepted_attempt") or b.get("best_attempt")
    if not b or not n:
        return None
    tot = 0
    for a in b["per_attempt"]:
        if (a.get("attempt") or 0) > n:
            continue
        tot += (a.get("prompt_tokens") or 0) + (a.get("completion_tokens") or 0)
    return tot


def badge(label, value, cls=""):
    return f"<span class='b {cls}'>{esc(value)}<i>{esc(label)}</i></span>"


def cell(slug, spec):
    b = load(slug, spec)
    mdir = os.path.join(OUT, slug)
    rel = lambda p: "../suite/out/%s/%s" % (slug, p)
    if b is None:
        return ("<div class='cell empty'><div class='frame'><span>not run</span></div>"
                "<div class='badges'>%s</div></div>" % badge("status", "no result", "pend"))
    a = accepted(b)
    gate = bool(a and a.get("gate_pass"))
    if gate and os.path.isfile(os.path.join(mdir, "index.html")):
        frame = (f"<iframe src='{esc(rel('index.html'))}' loading='lazy' "
                 f"title='{esc(name(slug))} — {esc(spec)}' sandbox='allow-scripts allow-same-origin'></iframe>")
        play = f"<a class='lnk' href='{esc(rel('index.html'))}' target='_blank' rel='noopener'>open full screen</a>"
    else:
        shot = rel("shot-%s.png" % spec)
        if os.path.isfile(os.path.join(mdir, "shot-%s.png" % spec)):
            frame = (f"<a class='frame shot' href='{esc(rel('index.html'))}'>"
                     f"<img src='{esc(shot)}' alt='{esc(name(slug))} {esc(spec)} frame' loading='lazy'>"
                     f"<span class='why'>{'failed gate' if b else 'no frame'}</span></a>")
        else:
            frame = "<div class='frame'><span>no frame recorded</span></div>"
        play = f"<a class='lnk' href='{esc(rel('index.html'))}' target='_blank' rel='noopener'>open what it built</a>"
    passed = a.get("passed") if a else None
    total = a.get("total") if a else None
    comp = a.get("compliance") if a else None
    att = b.get("turns_used")
    secs = build_seconds(b)
    tok = tokens(b)
    viol = (a or {}).get("violations") or []
    cls = "ok" if (passed == total and (comp or 0) >= 75) else ("warn" if gate else "bad")
    return (f"<div class='cell {cls}'>{frame}"
            f"<div class='badges'>"
            f"{badge('assertions', f'{passed}/{total}' if passed is not None else '—')}"
            f"{badge('compliance', comp if comp is not None else '—')}"
            f"{badge('attempts', att if att is not None else '—')}"
            f"{badge('build s', secs if secs is not None else '—')}"
            f"{badge('tokens', tok if tok is not None else '—')}"
            f"</div>{play}"
            + (f"<div class='viol' title='spec violations'>{len(viol)} spec violation"
               f"{'' if len(viol) == 1 else 's'}</div>" if viol else "")
            + f"<a class='lnk hist' href='../suite/out/{esc(slug)}/{esc(spec)}/build.json'>attempt history</a>"
              "</div>")


CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:100vw;margin:0 auto;padding:24px 14px 60px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 14px;max-width:70ch}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
.tabs a{padding:7px 12px;border:1px solid var(--line);border-radius:8px;color:var(--dim);text-decoration:none;font-size:13px;min-height:34px;display:inline-flex;align-items:center}
.tabs a.on{background:#1b2431;color:var(--fg);border-color:#33506b}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:10px}
table.mx{border-collapse:separate;border-spacing:10px 10px}
table.mx th{font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);font-weight:600;text-align:left;vertical-align:bottom;min-width:300px;max-width:300px;width:300px;padding:0 4px}
table.mx th.rowh{min-width:132px;width:132px;max-width:132px;vertical-align:top;padding:10px 4px 0 0}
table.mx th .fn{display:block;color:var(--faint);font-size:11px;text-transform:none;letter-spacing:0;font-family:ui-monospace,monospace;word-break:break-all}
table.mx th.rowh b{display:block;color:var(--fg);font-size:14px;text-transform:none;letter-spacing:0}
table.mx th.rowh span{display:block;color:var(--dim);font-size:12px;text-transform:none;letter-spacing:0;margin-top:4px}
.cell{width:300px;max-width:300px;background:#111821;border:1px solid var(--line);border-radius:9px;padding:8px}
.cell.ok{border-color:#23503a}.cell.warn{border-color:#4a3d16}.cell.bad{border-color:#4a2027}.cell.empty{border-style:dashed}
.frame{display:block;position:relative;width:284px;height:178px;border-radius:6px;overflow:hidden;background:#0b0f14;border:1px solid var(--line);margin-bottom:6px}
.frame iframe,.frame img{width:284px;height:178px;border:0;display:block}
.frame>span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--faint);font-size:12px}
.frame .why{position:absolute;left:6px;bottom:6px;background:#0b0f14cc;border-radius:4px;padding:1px 6px;font-size:11px;color:var(--gold)}
.badges{display:flex;flex-wrap:wrap;gap:5px;margin:2px 0 6px}
.b{display:inline-flex;flex-direction:column;background:#0d131b;border:1px solid var(--line);border-radius:6px;padding:2px 7px;font:600 12px ui-monospace,monospace;color:var(--fg);min-width:62px}
.b i{font-style:normal;font-weight:400;font-size:9.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.04em}
.b.pend{color:var(--faint)}
.lnk{display:inline-block;color:var(--dim);font-size:12px;margin-right:10px;text-decoration:none;border-bottom:1px dotted var(--line)}
.lnk:hover{color:var(--fg)}
.viol{color:var(--bad);font-size:11.5px;margin:0 0 4px}
.stack{margin-top:26px}
.stack h2{font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;margin:18px 0 8px}
.cards{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:760px){.cards{grid-template-columns:repeat(2,1fr)}}
.note{color:var(--dim);font-size:13px;max-width:80ch;margin-top:18px}
@media(max-width:520px){.wrap{padding:16px 10px 40px}table.mx th.rowh{min-width:104px;width:104px;max-width:104px}table.mx th.rowh span{font-size:11px}table.mx th{min-width:272px;max-width:272px;width:272px}.cell,.frame,.frame iframe,.frame img{width:256px}.frame{height:160px}}
"""


def main():
    os.makedirs(DEST, exist_ok=True)
    slugs = [s for s in ORDER if os.path.isdir(os.path.join(OUT, s))]
    extra = [os.path.basename(d) for d in glob.glob(os.path.join(OUT, "*")) if os.path.isdir(d)]
    slugs += [s for s in sorted(extra) if s not in slugs and not s.startswith("_")]

    head = "".join(
        f"<th><span>{esc(name(s))}</span><span class=fn>{esc(MODEL_NAME.get(s, ('',''))[1])}</span></th>"
        for s in slugs)
    rows = []
    for spec, label, blurb in SPECS:
        cells = "".join(f"<td>{cell(s, spec)}</td>" for s in slugs)
        rows.append(f"<tr><th class=rowh><b>{esc(label)}</b><span>{esc(blurb)}</span>"
                    f"<span class=fn><a href='../specs/GAME_SPEC_{esc(spec)}.md'>spec</a></span></th>{cells}</tr>")

    cards = []
    for spec, label, blurb in SPECS:
        cards.append(f"<h2>{esc(label)}</h2><div class=cards>" + "".join(
            f"<div><div class=meta>{esc(name(s))}</div>{cell(s, spec)}</div>" for s in slugs) + "</div>")

    body = (
        "<p class=sub>Four browser games, one frozen prompt each, the same models. Every "
        "game is generated as a single self-contained HTML file drawn with three.js, then "
        "graded in a headless browser: it must run, and a grader drives it through a small "
        "published state object and checks the rules numerically (determinism, counts, "
        "economy, stability). <b>Assertions</b> = rules verified by execution. "
        "<b>Compliance</b> = did it build what was asked, and only that (0-100, points off "
        "for extras the task did not request). <b>Attempts</b> = generations used, including "
        "up to 10 repair turns after a failure. Live frames are playable; a failed build "
        "shows its last screenshot.</p>"
        "<div class=scroll><table class=mx><thead><tr><th class=rowh>game</th>" + head +
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        "<div class=stack>" + "".join(cards) + "</div>"
        "<p class=note>Each specification uses its own minimal programmatic interface — "
        "only what that game needs — so a physics sandbox is never graded as a shooter. "
        "Scores are recorded per attempt; the full attempt history of every cell is linked "
        "under its frame.</p>"
    )
    nav = render_topbar("../../", "games")
    page = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>games side by side — same four games, every model</title>"
            f"<style>{CSS}{TOPBAR_CSS}</style></head><body>{render_brand()}{nav}<div class=wrap>"
            "<h1>games, side by side</h1>" + body + "</div></body></html>")
    open(os.path.join(DEST, "index.html"), "w").write(page)
    print("wrote", os.path.join(DEST, "index.html"), "models:", len(slugs))


if __name__ == "__main__":
    main()
