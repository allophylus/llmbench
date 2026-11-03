#!/usr/bin/env python3
"""Build the llmbench site tabs: games table + chat results table."""
import glob, json, os, re, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(ROOT, "games")
CHAT = os.path.join(ROOT, "data", "chat")


def overview_names():
    """name strings exactly as the overview table shows them, keyed by short slug."""
    try:
        d = json.load(open(os.path.join(ROOT, "data", "results.json")))
    except Exception:
        return {}
    out = {}
    for r in d.get("rows", []):
        slug = r.get("slug", "")
        if slug == "qwen3-8-27b-q4km":
            out["27b"] = r.get("name")
        elif slug == "qwen3-6-35b-a3b-ud-q4km":
            out["a3b"] = r.get("name")
    return {k: v for k, v in out.items() if v}

MODEL_LABEL = {
    "27b": "Qwen3.8-27B",
    "a3b": "Qwen3.6-35B-A3B",
    "qwen3-8-27b-q4km": "Qwen3.8-27B",
    "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B",
}
GAME_LABEL = {"galaga": "arcade shooter (TUI-derived)", "gta": "top-down driving (TUI-derived)", "physics": "3D physics sandbox (TUI-derived)", "solar": "solar system mission"}

NAV = """<nav class="tabs"><a href="../">overview</a><a href="../games/" class="on">games</a><a href="../chat/">chat</a><a href="../thinking/">thinking</a><a href="../ablation/">ablation</a><a href="../method/">method</a></nav>"""

CSS = """
:root{--bg:#0f141b;--panel:#151c26;--line:#243040;--fg:#e8eef8;--dim:#9fb0c6;--faint:#6f8296;--gold:#f5c542;--blue:#8cc8ff;--bad:#ff7b72;--ok:#7ee787}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 16px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}
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
.prompt{color:var(--faint);font-size:12px;max-width:52ch}\n.detail{border:1px solid var(--line);border-radius:10px;padding:14px;margin:16px 0;background:var(--panel)}\n.detail h2{margin:0 0 6px;font-size:17px}.bigshot{width:min(560px,100%);border-radius:8px;border:1px solid var(--line);margin:10px 0}\n.promptbox{white-space:pre-wrap;font:12px/1.45 ui-monospace,monospace;color:var(--dim);background:#111821;border:1px solid var(--line);border-radius:8px;padding:10px;max-height:260px;overflow:auto}\n.notes{color:var(--dim);margin:4px 0 8px}.sec{margin:26px 0 6px;font-size:15px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.meta{color:var(--faint);font-size:12px}
@media(max-width:640px){th,td{padding:7px 6px;font-size:12px}.thumb{width:96px}
.detail,.wrap{min-width:0;max-width:100%}
.table-wrap{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
body{overflow-x:hidden}
.wrap{box-sizing:border-box}
html,body{max-width:100vw}
.wrap{width:100%;max-width:1180px;margin:0 auto;padding:28px 18px 60px}
@media(max-width:640px){.wrap{padding:20px 12px 48px}}
table{min-width:520px}
.detail .promptbox{max-height:180px}
.ans,.q{word-break:break-word}
}
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
        game = slug[len(base):].lstrip("-") or "space shooter (v1 prompt)"
        model_file = ""
        _gj = os.path.join(d, "gen.json")
        if os.path.exists(_gj):
            try:
                model_file = os.path.basename(json.load(open(_gj)).get("model_requested") or "")
            except Exception:
                model_file = ""
        if model_file.startswith("active.") or model_file == "":
            model_file = {"qwen3-8-27b-q4km": "Qwen3.8-27B-Q4_K_M.gguf",
                          "qwen3-6-35b-a3b-ud-q4km": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"}.get(base, model_file)
        model = MODEL_LABEL[base]
        b = json.load(open(os.path.join(d, "build.json"))) if os.path.exists(os.path.join(d, "build.json")) else {}
        g = json.load(open(os.path.join(d, "gen.json"))) if os.path.exists(os.path.join(d, "gen.json")) else {}
        m = json.load(open(os.path.join(d, "metrics.json"))) if os.path.exists(os.path.join(d, "metrics.json")) else {}
        rj = os.path.join(d, "robot_metrics.json")
        robot = json.load(open(rj)) if os.path.exists(rj) else {}
        att = b.get("attempts") or b.get("turns_used") or len(glob.glob(os.path.join(d, "attempts", "attempt-*"))) or 1
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
        rows.append(dict(model=model, model_file=model_file, game=GAME_LABEL.get(game, game), slug=slug,
                         thinking=bool(b.get("thinking")), robot=robot, build=b,
                         attempts=att, retries=retries, tokens=tok, wall=wall,
                         status=status, notes="; ".join(notes), shot=shot))
    return rows


def attempts_table(r):
    b = r.get("build") or {}
    per = b.get("per_attempt") or b.get("per_turn") or []
    if not per:
        return ""
    rows = []
    for a in per:
        n = a.get("attempt") or a.get("n") or a.get("turn")
        ok = a.get("ok")
        reasons = a.get("reasons") or a.get("errors") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        issue = a.get("error") or "; ".join(str(x) for x in reasons) or ("renders" if ok else "")
        toks = a.get("tokens") or a.get("completion_tokens")
        wall = a.get("wall_s")
        rows.append("<tr>"
                    f"<td class=num>{esc(n)}</td>"
                    f"<td class={'ok' if ok else 'bad'}>{'ok' if ok else 'failed'}</td>"
                    f"<td class=meta>{esc(issue) or '—'}</td>"
                    f"<td class=num>{'' if toks is None else toks}</td>"
                    f"<td class=num>{'' if wall is None else round(float(wall),1)}</td></tr>")
    return ("<table class=subtbl><thead><tr><th>Turn</th><th>Result</th><th>Issue</th>"
            "<th>Tokens</th><th>s</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

def robot_block(r):
    m = r.get("robot") or {}
    if not m:
        return ""
    score = m.get("final_score")
    verdict = m.get("verdict") or ""
    vid = "https://d1zqwbb1zduc6n.cloudfront.net/llmbench/videos/game__%s__robot.mp4" % r["slug"]
    return (f"<p class=meta>robot play: <b>{'' if score is None else score}</b> points · {esc(verdict)} · "
            f"<a href='{vid}'>watch the robot run →</a></p>")

def build_games():
    rows = game_rows()
    tr = []
    for r in rows:
        shot = (f"<img class=thumb src='{esc(r['slug'])}/{esc(r['shot'])}' alt=''>") if r["shot"] else "—"
        tr.append("<tr>"
                  f"<td><a href='#{esc(r['slug'])}'>{esc(r['model'])}</a><br><span class=meta>{esc(r.get('model_file'))}</span></td><td>{esc(r['game'])}</td>"
                  f"<td>{'on' if r.get('thinking') else 'off'}</td>"
                  f"<td class=num>{esc(r['attempts'])}</td><td class=num>{esc(r['retries'])}</td>"
                  f"<td class=num>{'' if r['tokens'] is None else r['tokens']}</td>"
                  f"<td class=num>{'' if r['wall'] is None else round(float(r['wall']),1)}</td>"
                  f"<td>{esc(r['status'])}</td><td class=meta>{esc(r['notes']) or '—'}</td>"
                  f"<td>{0 if r['robot'] else '—'}</td>"
                  f"<td>{shot}</td>"
                  f"<td><a href='{esc(r['slug'])}/index.html'>play</a></td></tr>")

    details = []
    for r in rows:
        d = os.path.join(GAMES, r["slug"])
        prompt = ""
        for cand in (os.path.join(d, "attempts", "attempt-1", "prompt.txt"),):
            if os.path.exists(cand):
                prompt = open(cand, encoding="utf-8", errors="replace").read().strip()
                break
        shot = (f"<img class=bigshot src='{esc(r['slug'])}/{esc(r['shot'])}' alt=''>") if r["shot"] else ""
        details.append(
            f"<section class=detail id='{esc(r['slug'])}'>"
            f"<h2>{esc(r['model'])} — {esc(r['game'])}</h2><p class=meta>{esc(r.get('model_file'))}</p>"
            f"<p class=meta>{esc(r['status'])} · thinking {'on' if r.get('thinking') else 'off'} · "
            f"{esc(r['attempts'])} attempt(s), {esc(r['retries'])} repeat(s) · "
            f"{'' if r['tokens'] is None else r['tokens']} tokens · "
            f"{'' if r['wall'] is None else round(float(r['wall']),1)}s</p>"
            f"<p class=notes>{esc(r['notes']) or '—'}</p>"
            + (f"<details><summary>prompt used</summary><pre class=promptbox>{esc(prompt)}</pre></details>" if prompt else "")
            + attempts_table(r) + robot_block(r) + shot +
            f"<p><a href='{esc(r['slug'])}/index.html'>play the game →</a> · "
            f"<a href='{esc(r['slug'])}/metrics.json'>metrics</a></p></section>")

    body = ("<p class=sub>Each model writes a single-file three.js game from a frozen prompt. "
            "The model draws everything with geometry — no images, textures or audio files. "
            "Repeats = extra generation turns allowed to fix a failing build (max 10).</p>"
            "<div class=table-wrap><table><thead><tr><th>Model</th><th>Game</th><th>Thinking</th><th>Attempts</th><th>Repeats</th>"
            "<th>Tokens</th><th>Build s</th><th>Status</th><th>What's wrong / notes</th>"
            "<th>Robot</th><th>Screenshot</th><th>Play</th></tr></thead><tbody>"
            + "".join(tr) + "</tbody></table></div>"
            "<h2 class=sec>Details</h2>" + "".join(details))
    open(os.path.join(GAMES, "index.html"), "w").write(page("games — model-written browser games", body))
    print("games rows:", len(rows))

def build_chat():
    files = sorted(glob.glob(os.path.join(CHAT, "*.json")))
    OV = overview_names()
    groups = {}
    for f in files:
        d = json.load(open(f))
        base = d.get("model", "model")
        think = bool(d.get("thinking"))
        groups.setdefault(base, {})[think] = d

    summary_rows, details = [], []
    for base, modes in groups.items():
        label = OV.get(base) or MODEL_LABEL.get(base, base)
        for think in (False, True):
            d = modes.get(think)
            if not d:
                continue
            qs = d.get("questions", [])
            corr = sum(1 for q in qs if q.get("verdict") == "correct")
            part = sum(1 for q in qs if q.get("verdict") == "partial")
            wrong = len(qs) - corr - part
            toks = sum(q.get("tokens") or 0 for q in qs)
            ms = [q.get("ms") for q in qs if q.get("ms")]
            avg_ms = int(sum(ms) / len(ms)) if ms else None
            acc = round(100.0 * corr / len(qs), 1) if qs else None
            tps = [q.get("decode_tps") for q in qs if isinstance(q.get("decode_tps"), (int, float))]
            mean_tps = round(sum(tps) / len(tps), 1) if tps else None
            anchor = "chat-%s-%s" % (base, "on" if think else "off")
            mode = "on" if think else "off"
            summary_rows.append(
                "<tr>"
                f"<td><a href='#{esc(anchor)}'>{esc(label)}</a></td><td>{mode}</td>"
                f"<td class=num>{corr}</td><td class=num>{part}</td><td class=num>{wrong}</td>"
                f"<td class=num>{'' if acc is None else acc}%</td>"
                f"<td class=num>{'' if mean_tps is None else mean_tps}</td>"
                f"<td class=num>{toks}</td><td class=num>{'' if avg_ms is None else round(avg_ms/1000.0,2)}</td>"
                "</tr>")
            tr = []
            for q in qs:
                v = q.get("verdict", "unscored")
                cls = {"correct": "ok", "partial": "warn", "wrong": "bad"}.get(v, "")
                tr.append("<tr>"
                          f"<td class=num>{esc(q['id'])}</td><td>{esc(q.get('topic'))}</td>"
                          f"<td class=q>{esc(q.get('q'))}</td>"
                          f"<td class=ans>{esc(q.get('answer') or q.get('error') or '—')}</td>"
                          f"<td class={cls}>{esc(v)}</td>"
                          f"<td class=num>{'' if q.get('tokens') is None else q['tokens']}</td>"
                          f"<td class=num>{'' if q.get('ms') is None else round(q['ms']/1000.0,2)}</td></tr>")
            details.append(
                f"<section class=detail id='{esc(anchor)}'>"
                f"<h2>{esc(label)} — thinking {mode} <span class=pill>{'' if acc is None else acc}%</span></h2>"
                f"<p class=meta>{corr} correct · {part} partial · {wrong} wrong · {toks} tokens · "
                f"avg {'' if avg_ms is None else avg_ms} ms/question</p>"
                "<div class=table-wrap><table><thead><tr><th>#</th><th>Topic</th><th>Question</th><th>Answer</th>"
                "<th>Verdict</th><th>Tokens</th><th>s</th></tr></thead><tbody>"
                + "".join(tr) + "</tbody></table></div></section>")

    # the campaign suite: every model on the same 10 questions, thinking off. Older one-off
    # files ("27b") used a different prompt set and are not part of this comparison.
    camp = []
    for base, modes in groups.items():
        d = modes.get(False)
        if not d or base == "27b":
            continue
        qs = d.get("questions", [])
        c = sum(1 for q in qs if q.get("verdict") == "correct")
        p = sum(1 for q in qs if q.get("verdict") == "partial")
        tps = [q.get("decode_tps") for q in qs if isinstance(q.get("decode_tps"), (int, float))]
        camp.append((OV.get(base) or MODEL_LABEL.get(base, base), c, p, len(qs) - c - p,
                     round(100.0 * c / len(qs), 1) if qs else None,
                     round(sum(tps) / len(tps), 1) if tps else None))
    camp.sort(key=lambda x: -(x[5] or 0))
    saturated = len(camp) >= 3 and len({(x[1], x[2]) for x in camp}) == 1


    body = ("<p class=sub>Ten fixed knowledge questions, temperature 0, thinking off. "
            "Accuracy = strictly correct answers.</p>"
            + (f"<p class=warn><b>Saturated test.</b> All {len(camp)} models score "
               f"{camp[0][1]}/{camp[0][3]} correct plus {camp[0][2]} partial "
               f"({camp[0][4]}%), so this suite cannot tell these models apart. "
               "The table is ordered by decode speed, not by quality — a tie is a tie.</p>"
               if saturated else "")
            + "<div class=table-wrap><table><thead><tr><th>Model</th><th>Correct</th><th>Partial</th>"
            "<th>Wrong</th><th>Accuracy</th><th>Decode t/s</th></tr></thead><tbody>"
            + "".join(f"<tr><td>{esc(n)}</td><td class=num>{c}</td><td class=num>{p}</td>"
                      f"<td class=num>{w}</td><td class=num>{a}%</td><td class=num>{t}</td></tr>"
                      for (n, c, p, w, a, t) in camp)
            + '</tbody></table></div>'
            '<p class=meta>Decode t/s is the mean of the server rate for each short answer '
            '(includes the first, warm-up question), so it sits slightly below the steady-state '
            'figure in the overview table. Raw per-question JSONs: '
            '<a href="../raw-chat/">raw-chat/</a>. How it is scored: '
            '<a href="../method/">method</a>.</p>' 
            "<h2 class=sec>Per-question detail</h2>" + "".join(details))
    os.makedirs(os.path.join(ROOT, "chat"), exist_ok=True)
    open(os.path.join(ROOT, "chat", "index.html"), "w").write(page("chat — knowledge accuracy", body))
    print("chat groups:", len(groups))

if __name__ == "__main__":
    build_games()
    build_chat()
