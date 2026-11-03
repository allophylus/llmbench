#!/usr/bin/env python3
"""build_pages_games.py -- the games tab: one row per (model, game cell).

Reads games/<model-dir>-<game>/ (index.html, build.json, metrics.json, shot.png,
video/*.webm). A directory without an index.html cannot show a screenshot, so it is
listed as "not run" instead of being dropped.

Status wording (visitor-facing, generic):
  pass         final gate green (all 8 checks, 0 console errors)
  fail         never passed the gate
  in progress  no result written yet

Mobile: wide table scrolls horizontally; the details block under it gives each cell
its screenshot, links and a compact stats list, so nothing is only reachable by
sideways scrolling.
"""
import glob
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(ROOT, "games")

MODEL_LABEL = {
    "qwen3-8-27b-q4km": "Qwen3.8-27B",
    "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B",
}
MODEL_FILE = {
    "qwen3-8-27b-q4km": "Qwen3.8-27B-Q4_K_M.gguf",
    "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
}
# display name for the cell's prompt family
GAME_NAME = {
    "galaga": "galaga-3d",
    "gta": "gta-3d",
    "physics": "physics-3d",
    "solar": "solar-system",
}
CELLS = ("galaga", "gta", "physics", "solar")
# ordering of cells; unknown suffixes after the known ones
CELL_ORDER = {c: i for i, c in enumerate(CELLS)}

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 16px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
.tabs a{padding:7px 13px;border:1px solid var(--line);border-radius:8px;color:var(--dim);text-decoration:none;font-size:13px;min-height:36px;display:inline-flex;align-items:center}
.tabs a.on{background:#1b2431;color:var(--fg);border-color:#33506b}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{width:100%;border-collapse:collapse;background:var(--panel);min-width:860px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
thead th{background:#1b2431;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
tbody tr:nth-child(even) td{background:#131a24}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
.thumb{width:150px;border-radius:6px;border:1px solid var(--line);display:block}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--gold)}.pend{color:var(--faint)}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;border:1px solid var(--line);font-size:11px;color:var(--dim)}
.meta{color:var(--faint);font-size:12px}.notes{color:var(--dim);margin:4px 0 8px}
.detail{border:1px solid var(--line);border-radius:10px;padding:14px;margin:16px 0;background:var(--panel)}
.detail h2{margin:0 0 6px;font-size:17px}.bigshot{width:min(560px,100%);border-radius:8px;border:1px solid var(--line);margin:10px 0;display:block}
video{width:min(560px,100%);border-radius:8px;border:1px solid var(--line);margin:10px 0;display:block;background:#000}
.sec{margin:26px 0 6px;font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.stat{display:inline-block;margin:0 14px 6px 0;min-width:120px}
.stat b{display:block;font:15px ui-monospace,monospace}
.stat span{color:var(--faint);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
a{color:var(--blue)}
.hintm{display:none;color:var(--dim);font-size:12.5px;margin:0 0 8px}
@media(max-width:760px){
  .hintm{display:block}
  .scroll{position:relative}
  .scroll::after{content:"";position:sticky;right:0;display:block}
}
@media(max-width:640px){
  .wrap{padding:18px 12px 48px}
  th,td{padding:7px 7px;font-size:12px}
  .thumb{width:110px}
  table{min-width:760px}
  .detail{padding:11px}
}
"""

NAV = ("<nav class=tabs><a href='../'>overview</a>"
       "<a href='../games/' class=on>games</a>"
       "<a href='../thinking/'>thinking on/off</a>"
       "<a href='../chat/'>chat</a></nav>")


def rel(slug):
    """page-relative path to a game artifact: 'qwenx-galaga/index.html'"""
    return slug.rsplit("/", 1)[-1] if slug else ""


def esc(s):
    return html.escape(str("" if s is None else s))


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _split(slug):
    """'qwen3-6-35b-a3b-ud-q4km-physics' -> ('qwen3-6-35b-a3b-ud-q4km', 'physics')"""
    for base in sorted(MODEL_LABEL, key=len, reverse=True):
        if slug == base:
            return base, ""
        if slug.startswith(base + "-"):
            return base, slug[len(base) + 1:]
    return None, None


def scan():
    """Every model x cell we know about: existing dirs + known cells not yet run."""
    found = {}
    for d in sorted(glob.glob(os.path.join(GAMES, "*"))):
        if not os.path.isdir(d):
            continue
        slug = os.path.basename(d)
        base, game = _split(slug)
        if not base:
            continue
        key = game or "space-shooter"
        found[(base, key)] = d
    # an A3B model entry that has only empty placeholders still gets "not run" cells
    models = sorted({base for base, _ in found})
    # only cells this model actually ran: a model never attempted a prompt family must
    # not get an invented "not run" row for it
    cells = []
    for (b, g) in found:
        if g not in cells and g != "space-shooter":
            cells.append(g)
    cells.sort(key=lambda c: (CELL_ORDER.get(c, 99), c))
    if "space-shooter" in {g for _, g in found}:
        cells.append("space-shooter")
    return models, cells, found


def collect(base, game, d):
    r = dict(model=MODEL_LABEL[base], model_file=MODEL_FILE.get(base, ""),
             game=GAME_NAME.get(game, game), slug=os.path.join(os.path.basename(os.path.dirname(d)), os.path.basename(d)),
             has_game=os.path.exists(os.path.join(d, "index.html")))
    if not r["has_game"]:
        r.update(status="not run", status_cls="pend", notes="no build recorded yet",
                 attempts=None, tokens=None, wall=None, gen_tokens=None, gen_wall=None,
                 repair_tokens=None, repair_wall=None, repair_turns=None, reasons="", shot="", video="")
        return r
    b = _load(os.path.join(d, "build.json"))
    g = _load(os.path.join(d, "gen.json"))
    m = _load(os.path.join(d, "metrics.json"))
    rep = b.get("repair") or {}
    s = m.get("summary", {}) if isinstance(m, dict) else {}
    checks = s.get("checks") or s
    errors = s.get("console_error_count")

    passed = bool(b.get("accepted_attempt")) or rep.get("status") == "accepted"
    if not s and not b:
        status, cls = "in progress", "pend"
    elif passed:
        status, cls = "pass", "ok"
    else:
        status, cls = "fail", "bad"

    attempts = b.get("attempts_used") or b.get("attempts")
    # old cells only kept gen.json; new ones report the generation pass separately from repair
    _gen_tok = b.get("total_completion_tokens")
    _rep_tok = rep.get("repair_tokens")
    if _gen_tok is not None and _rep_tok is not None and "generation_tokens" not in b:
        _gen_tok = _gen_tok - _rep_tok
    tok = _gen_tok if _gen_tok is not None else g.get("completion_tokens")
    _gen_wall = b.get("total_wall_s")
    _rep_wall = rep.get("repair_wall_s")
    if _gen_wall is not None and _rep_wall is not None and "generation_wall_s" not in b:
        _gen_wall = _gen_wall - _rep_wall
    wall = _gen_wall if _gen_wall is not None else g.get("wall_s")
    turns = rep.get("turns_used") or len(rep.get("turns") or []) or None
    distinct = rep.get("distinct_outputs")

    reasons = []
    if status == "fail":
        for k in ("animation_ok", "input_ok", "contract_ok", "console_error_count"):
            if k in checks and not checks.get(k):
                reasons.append({"animation_ok": "no running animation",
                                "input_ok": "keys do not change pixels",
                                "contract_ok": "window.__game contract missing",
                                "console_error_count": "console errors"}[k])
        if rep.get("status") == "stalled-no-progress":
            reasons.append("repair stalled (same file re-emitted)")
        elif rep.get("status") == "still-broken" and turns:
            reasons.append("repair cap reached (%d turns)" % turns)
    if not reasons:
        last = (rep.get("turns") or [{}])[-1]
        reasons = last.get("failed") or []
    shot = "shot.png" if os.path.exists(os.path.join(d, "shot.png")) else ""
    vids = sorted(glob.glob(os.path.join(d, "video", "*.webm")))
    r.update(status=status, status_cls=cls,
             attempts=attempts, gen_tokens=tok, gen_wall=wall,
             repair_tokens=rep.get("repair_tokens"), repair_wall=rep.get("repair_wall_s"),
             tokens=tok, wall=wall,
             repair_turns=turns, repair_status=rep.get("status"), distinct=distinct,
             errors=errors, reasons="; ".join(reasons), shot=shot,
             video=("video/" + os.path.basename(vids[0])) if vids else "")
    return r


def fmt_num(v, nd=0):
    if v is None:
        return "—"
    return ("{:,.%df}" % nd).format(float(v))


def build():
    models, cells, found = scan()
    rows = []
    for base in models:
        for c in cells:
            d = found.get((base, c))
            if not d:
                if not any(g == c for (b2, g) in found if b2 == base):
                    continue
                rows.append(dict(model=MODEL_LABEL[base], model_file=MODEL_FILE.get(base, ""),
                                 game=GAME_NAME.get(c, c), slug="", has_game=False,
                                 status="not run", status_cls="pend",
                                 notes="no build recorded yet", attempts=None, tokens=None,
                                 wall=None, gen_tokens=None, gen_wall=None, repair_tokens=None,
                                 repair_wall=None, repair_turns=None, reasons="", shot="", video=""))
                continue
            rows.append(collect(base, c, d))

    def rep_label(r):
        rep = r.get("repair_turns")
        if rep is None:
            return "—"
        out = str(rep)
        if r.get("distinct") is not None and rep:
            out += " <span class=meta>(%d distinct file%s)</span>" % (
                r["distinct"], "" if r["distinct"] == 1 else "s")
        return out

    tr = []
    for r in rows:
        name = esc(r["model"]) + "<br><span class=meta>" + esc(r["game"]) + "</span>"
        if r["has_game"]:
            name = "<a href='#%s'>%s</a>" % (esc(r["slug"]), name)
        shot = ("<img class=thumb loading=lazy decoding=async src='%s/%s' alt='%s screenshot'>"
                % (esc(rel(r["slug"])), esc(r["shot"]), esc(r["game"]))) if r["shot"] else '<span class=pend>—</span>'
        rep_s = rep_label(r)
        links = []
        if r["has_game"]:
            links.append("<a href='%s/index.html'>play</a>" % esc(rel(r["slug"])))
            if r["video"]:
                links.append("<a href='%s/%s'>video</a>" % (esc(rel(r["slug"])), esc(r["video"])))
            links.append("<a href='%s/metrics.json'>metrics</a>" % esc(rel(r["slug"])))
        tr.append("<tr>"
                  "<td>%s<br><span class=meta>%s</span></td>" % (name, esc(r["model_file"]))
                  + "<td class=%s>%s</td>" % (r["status_cls"], esc(r["status"]))
                  + "<td class=num>%s</td>" % esc("" if r["attempts"] is None else r["attempts"])
                  + "<td class=num>%s</td>" % fmt_num(r.get("gen_tokens"))
                  + "<td class=num>%s</td>" % ("" if r.get("gen_wall") is None else "{:,.1f}".format(float(r["gen_wall"])))
                  + "<td class=num>%s</td>" % rep_s
                  + "<td class=meta>%s</td>" % (esc(r["reasons"]) or "—")
                  + "<td>%s</td>" % shot
                  + "<td>%s</td>" % (" · ".join(links) or "—")
                  + "</tr>")

    details = []
    for r in rows:
        if not r["has_game"]:
            continue
        d = os.path.join(GAMES, r["slug"])
        shot = ("<img class=bigshot loading=lazy decoding=async src='%s/%s' alt='%s screenshot'>"
                % (esc(rel(r["slug"])), esc(r["shot"]), esc(r["game"]))) if r["shot"] else ""
        vid = ("<video controls preload=none playsinline muted loop src='%s/%s'></video>"
               % (esc(rel(r["slug"])), esc(r["video"]))) if r["video"] else ""
        rep_s = rep_label(r)
        stats = []
        stats.append("<span class=stat><b>%s</b><span>gate attempts</span></span>" %
                     esc("" if r["attempts"] is None else r["attempts"]))
        stats.append("<span class=stat><b>%s</b><span>tokens, 3 attempts</span></span>" % fmt_num(r.get("gen_tokens")))
        stats.append("<span class=stat><b>%s</b><span>seconds, 3 attempts</span></span>" %
                     ("" if r.get("gen_wall") is None else "{:,.1f}".format(float(r["gen_wall"]))))
        stats.append("<span class=stat><b>%s</b><span>repair turns</span></span>" % rep_s)
        if r.get("repair_tokens") is not None:
            stats.append("<span class=stat><b>%s</b><span>repair tokens</span></span>" % fmt_num(r["repair_tokens"]))
        if r.get("repair_wall") is not None:
            stats.append("<span class=stat><b>%s</b><span>repair seconds</span></span>" %
                         "{:,.1f}".format(float(r["repair_wall"])))
        if r.get("errors") is not None:
            stats.append("<span class=stat><b>%s</b><span>console errors</span></span>" % esc(r["errors"]))
        details.append(
            "<section class=detail id='%s'>" % esc(r["slug"])
            + "<h2>%s — %s <span class='pill %s'>%s</span></h2>"
              % (esc(r["model"]), esc(r["game"]), r["status_cls"], esc(r["status"]))
            + "<p class=meta>%s · temp 0 · thinking off per request · up to 3 generation attempts, "
              "then ≤10 gate-driven repair turns</p>" % esc(r["model_file"])
            + "<div>" + "".join(stats) + "</div>"
            + ("<p class=notes>%s</p>" % esc(r["reasons"]) if r["reasons"] else "")
            + vid + shot
            + "<p><a href='%s/index.html'>open the final build →</a>" % esc(rel(r["slug"]))
            + (" · <a href='%s/%s'>screen recording (webm) →</a>" % (esc(rel(r["slug"])), esc(r["video"])) if r["video"] else "")
            + " · <a href='%s/metrics.json'>gate metrics</a></p>" % esc(rel(r["slug"]))
            + "</section>")

    body = (
        "<p class=sub>Each model writes a single-file three.js game from a frozen prompt — "
        "geometry only, no images, textures or audio files. A gate then loads it twice "
        "(http and file), checks canvas + WebGL, that animation advances, that keys change "
        "pixels, and that <code>window.__game</code> is complete. "
        "Repair turns = extra edits allowed after a failing gate (max 10). "
        "Seconds are generation wall time; they exclude the gate.</p>"
        "<p class=hintm>Swipe the table sideways for all columns — each cell is repeated below with its screenshot and links.</p>"
        "<div class=scroll><table><thead><tr>"
        "<th>Model / game</th><th>Outcome</th><th>Attempts</th><th>Gen tokens</th>"
        "<th>Gen s</th><th>Repair turns</th><th>What failed</th><th>Screenshot</th><th>Links</th>"
        "</tr></thead><tbody>" + "".join(tr) + "</tbody></table></div>"
        "<h2 class=sec>Details</h2>" + "".join(details))
    out = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
           "<meta name=viewport content='width=device-width,initial-scale=1'>"
           "<title>games — model-written browser games</title><style>" + CSS + "</style>"
           "</head><body><div class=wrap>" + NAV
           + "<h1>games — model-written browser games</h1>" + body + "</div></body></html>")
    open(os.path.join(GAMES, "index.html"), "w", encoding="utf-8").write(out)
    print("games rows:", len(rows),
          "| pass:", sum(1 for r in rows if r["status"] == "pass"),
          "| fail:", sum(1 for r in rows if r["status"] == "fail"))


if __name__ == "__main__":
    build()
