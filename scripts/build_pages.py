#!/usr/bin/env python3
"""Build the llmbench site tabs: games table + chat results table."""
import glob, json, os, re, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(ROOT, "games")
CHAT = os.path.join(ROOT, "data", "chat")

MODEL_LABEL = {
    "qwen3-8-27b-q4km": "Qwen3.8-27B",
    "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B",
}
GAME_LABEL = {"galaga": "arcade shooter", "gta": "top-down driving mission", "physics": "3D physics sandbox"}

NAV = """<nav class="tabs"><a href="../">overview</a><a href="../games/" class="on">games</a><a href="../chat/">chat</a></nav>"""

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 16px}
.tabs{display:flex;gap:8px;margin:0 0 18px}
.tabs a{padding:6px 12px;border:1px solid var(--line);border-radius:8px;color:var(--dim);text-decoration:none;font-size:13px}
.tabs a.on{background:#1b2431;color:var(--fg);border-color:#33506b}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
thead th{background:#1b2431;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim)}
tbody tr:nth-child(even) td{background:#131a24}
td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right;white-space:nowrap}
.thumb{width:150px;border-radius:6px;border:1px solid var(--line);display:block}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--gold)}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;border:1px solid var(--line);font-size:11px;color:var(--dim)}
.q{color:var(--fg)}.ans{color:var(--dim);font-size:13px}
.prompt{color:var(--faint);font-size:12px;max-width:52ch}
.meta{color:var(--faint);font-size:12px}
@media(max-width:640px){th,td{padding:7px 6px;font-size:12px}.thumb{width:96px}}
"""

def esc(s):
    return html.escape(str(s or ""))

def page(title, body):
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><div class=wrap>"
            f"{NAV}<h1>{esc(title)}</h1>{body}</div></body></html>")

def game_rows():
    rows = []
    for d in sorted(glob.glob(os.path.join(GAMES, "*"))):
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "index.html")):
            continue
        slug = os.path.basename(d)
        base = next((m for m in MODEL_LABEL if slug.startswith(m)), None)
        if not base:
            continue
        game = slug[len(base):].lstrip("-") or "shooter"
        model = MODEL_LABEL[base]
        b = json.load(open(os.path.join(d, "build.json"))) if os.path.exists(os.path.join(d, "build.json")) else {}
        g = json.load(open(os.path.join(d, "gen.json"))) if os.path.exists(os.path.join(d, "gen.json")) else {}
        m = json.load(open(os.path.join(d, "metrics.json"))) if os.path.exists(os.path.join(d, "metrics.json")) else {}
        att = b.get("attempts") or len(glob.glob(os.path.join(d, "attempts", "attempt-*"))) or 1
        retries = b.get("retries", max(0, att - 1) if isinstance(att, int) else 0)
        tok = b.get("total_completion_tokens") or g.get("completion_tokens")
        wall = b.get("total_wall_s") or g.get("wall_s")
        s = m.get("summary", {}) if isinstance(m, dict) else {}
        status = "renders" if s.get("canvas_ok") else ("failed" if m else "unverified")
        notes = []
        if s and not s.get("contract_ok"): notes.append("no window.__game contract → robot cannot score it")
        if s and not s.get("animation_ok"): notes.append("animation not advancing")
        if not notes and status == "renders": notes.append("playable in browser")
        shot = "shot.png" if os.path.exists(os.path.join(d, "shot.png")) else ""
        rows.append(dict(model=model, game=GAME_LABEL.get(game, game), slug=slug,
                         attempts=att, retries=retries, tokens=tok, wall=wall,
                         status=status, notes="; ".join(notes), shot=shot))
    return rows

def build_games():
    rows = game_rows()
    tr = []
    for r in rows:
        shot = (f"<img class=thumb src='{esc(r['slug'])}/{esc(r['shot'])}' alt=''>") if r["shot"] else "—"
        tr.append("<tr>"
                  f"<td>{esc(r['model'])}</td><td>{esc(r['game'])}</td>"
                  f"<td class=num>{esc(r['attempts'])}</td><td class=num>{esc(r['retries'])}</td>"
                  f"<td class=num>{'' if r['tokens'] is None else r['tokens']}</td>"
                  f"<td class=num>{'' if r['wall'] is None else round(float(r['wall']),1)}</td>"
                  f"<td>{esc(r['status'])}</td><td class=meta>{esc(r['notes']) or '—'}</td>"
                  f"<td>{shot}</td>"
                  f"<td><a href='{esc(r['slug'])}/index.html'>play</a></td></tr>")
    body = ("<p class=sub>Each model writes a single-file three.js game from a frozen prompt. "
            "The model draws everything with geometry — no images, textures or audio files. "
            "Repeats = extra generation turns allowed to fix a failing build (max 10).</p>"
            "<table><thead><tr><th>Model</th><th>Game</th><th>Attempts</th><th>Repeats</th>"
            "<th>Tokens</th><th>Build s</th><th>Status</th><th>What's wrong / notes</th>"
            "<th>Screenshot</th><th>Play</th></tr></thead><tbody>"
            + "".join(tr) + "</tbody></table>")
    open(os.path.join(GAMES, "index.html"), "w").write(page("games — model-written browser games", body))
    print("games rows:", len(rows))

def build_chat():
    files = sorted(glob.glob(os.path.join(CHAT, "*.json")))
    blocks = []
    for f in files:
        d = json.load(open(f))
        s = d.get("summary", {})
        label = MODEL_LABEL.get(d.get("model"), d.get("model"))
        head = (f"<h2>{esc(label)} <span class=pill>{s.get('accuracy','—')}% accurate</span> "
                f"<span class=meta>{s.get('correct',0)} correct · {s.get('partial',0)} partial · "
                f"{s.get('wrong',0)} wrong</span></h2>")
        tr = []
        for q in d.get("questions", []):
            v = q.get("verdict", "unscored")
            cls = {"correct": "ok", "partial": "warn", "wrong": "bad"}.get(v, "")
            tr.append("<tr>"
                      f"<td class=num>{esc(q['id'])}</td><td>{esc(q.get('topic'))}</td>"
                      f"<td class=q>{esc(q.get('q'))}</td>"
                      f"<td class=ans>{esc(q.get('answer') or q.get('error') or '—')}</td>"
                      f"<td class={cls}>{esc(v)}</td>"
                      f"<td class=num>{'' if q.get('tokens') is None else q['tokens']}</td>"
                      f"<td class=num>{'' if q.get('ms') is None else q['ms']}</td></tr>")
        blocks.append(head + "<table><thead><tr><th>#</th><th>Topic</th><th>Question</th><th>Answer</th>"
                             "<th>Verdict</th><th>Tokens</th><th>ms</th></tr></thead><tbody>"
                             + "".join(tr) + "</tbody></table>")
    body = ("<p class=sub>Ten fixed knowledge questions, temperature 0, max 220 tokens. "
            "Accuracy = strictly correct answers.</p>" + "".join(blocks))
    os.makedirs(os.path.join(ROOT, "chat"), exist_ok=True)
    open(os.path.join(ROOT, "chat", "index.html"), "w").write(page("chat — knowledge accuracy", body))
    print("chat models:", len(files))

if __name__ == "__main__":
    build_games()
    build_chat()
