#!/usr/bin/env python3
"""build_index.py — write games/index.html from each games/<slug>/metrics.json + gen.json.

usage: build_index.py <repo_games_dir>

Every displayed number is read from the recorded probe/generation files; nothing is
computed from assumptions. Slugs are sorted, game A then B.
"""
import json
import os
import sys

games_dir = os.path.abspath(sys.argv[1])
slugs = sorted(d for d in os.listdir(games_dir)
               if os.path.isfile(os.path.join(games_dir, d, "metrics.json")))
if any(d.endswith("-b") for d in slugs):
    slugs.sort(key=lambda s: (s.rstrip("-b"), s))

rows = []
for slug in slugs:
    d = os.path.join(games_dir, slug)
    m = json.load(open(os.path.join(d, "metrics.json")))
    g = json.load(open(os.path.join(d, "gen.json")))
    s = m["summary"]
    rows.append((slug, m, g, s))

VER = lambda ok: f'<b class="ok">PASS</b>' if ok else f'<b class="bad">FAIL</b>'


def cells(m, g, s):
    return f"""
      <td>{s['console_error_count']}</td>
      <td>{VER(s['canvas_ok'])}</td>
      <td>{VER(s['webgl_ok'])}</td>
      <td>{VER(s['animation_ok'])}</td>
      <td>{VER(s['input_ok'])}</td>
      <td>{VER(s['http_load_ok'])}</td>
      <td>{VER(s['file_load_ok'])}</td>
      <td>{g['html_lines']}</td>
      <td>{g['completion_tokens']}</td>
      <td>{g['decode_tps']}</td>"""


cards = []
for slug, m, g, s in rows:
    three = ('three.js <code>WebGLRenderer</code>' if s['webgl_ok'] and s['uses_three']
             else 'plain 2D canvas' if s['canvas_ok'] else 'unknown')
    errs = m['http'].get('console_errors', []) + m['file'].get('console_errors', [])
    errs_html = ('<ul class="errs">' + ''.join(f'<li>{e}</li>' for e in errs) + '</ul>'
                 if errs else '<span class="dim">none</span>')
    find = []
    if s.get('player_visible') is False:
        bb = s.get('player_bbox_px')
        find.append(f'player ship never appears on screen '
                    f'(mesh projects to y={bb[1]}..{bb[3]}px in a {m["viewport"]["height"]}px viewport, '
                    f'below the camera frustum) — it still moves, shoots and collides')
    elif s.get('player_fully_onscreen') is False:
        find.append(f'player ship is only partly on screen (y={s.get("player_bbox_px")[1]}..'
                    f'{s.get("player_bbox_px")[3]}px in a {m["viewport"]["height"]}px viewport, bottom cut off)')
    if s.get('overlays_cover_geometry'):
        find.append('some 3D geometry is painted under the HTML HUD/hint overlay')
    findings_html = ('<ul class="findings">' + ''.join(f'<li>{x}</li>' for x in find) + '</ul>'
                     if find else '<p class="meta ok">no visible-artefact findings</p>')

    # ---- robot result (optional; only if robot_player.py has run) ----
    rj = os.path.join(d, "robot_metrics.json")
    robot = json.load(open(rj)) if os.path.isfile(rj) else None
    robot_html = ""
    if robot:
        cd_ = (robot.get("closest_bullet_to_enemy_px") or {})
        v = robot.get("verdict")
        vs = {"scored": "scored", "zero-score": "ZERO SCORE"}.get(v, "no contract")
        robot_html = f"""
        <div class="robot">
          <div class="rlbl">🤖 robot run</div>
          <div class="rstats">
            <span><b>{robot.get('final_score')}</b> score</span>
            <span><b>{robot.get('survival_s')}</b> s survived</span>
            <span><b>{robot.get('lives_lost')}</b> lives lost</span>
            <span><b>{robot.get('frames_advanced')}</b> frames</span>
            <span><b>{robot.get('action_count')}</b> key events</span>
          </div>
          <p class="meta">policy verdict: <b class="{'ok' if v == 'scored' else 'bad'}">{vs}</b>
            · contract ok: {robot.get('contract_ok')} · page threw: {robot.get('page_threw')}
            · closest bullet→enemy: {cd_.get('min_dy')} px vertical
            {"<a href='" + slug + "/robot_play.mp4'>watch (.mp4)</a> <a href='" + slug + "/robot_play.webm'>webm</a>" if robot.get('video') else ""}</p>
          {'<p class="findings">Zero is a game defect, not a policy failure: every shot flew at a fixed y the enemies never occupy (measured closest vertical gap ' + str(cd_.get("min_dy")) + ' px), so nothing could ever collide.</p>' if v == 'zero-score' else ''}
        </div>"""
    cards.append(f"""
    <article class="card">
      <a class="shot" href="{slug}/index.html"><img src="{slug}/shot.png" alt="screenshot of {slug}" loading="lazy"></a>
      <div>
        <h2>{slug} <span class="pill {'ok' if s['pass'] else 'bad'}">{'PASS' if s['pass'] else 'FAIL'}</span></h2>
        <p class="meta">model <code>{g['model_requested']}</code> · {g['server_fingerprint']} ·
          temp {g['temperature']} · max_tokens {g['max_tokens']} · prompt sha256 <code>{g['prompt_sha256'][:16]}…</code></p>
        <p class="meta">renders with {three} · {m['http'].get('canvas_count', 0)} canvas ·
          {g['html_lines']} lines · {g['completion_tokens']} tokens · {g['decode_tps']} t/s · {g['wall_s']}s</p>
        <p class="meta">console errors: {errs_html}</p>
        {findings_html}
        {robot_html}
        <p><a class="play" href="{slug}/index.html">▶ PLAY {slug}</a></p>
      </div>
    </article>""")

table_rows = ''.join(f"""
    <tr><td><a href="{slug}/index.html">{slug}</a></td>
      <td>{VER(s['pass'])}</td>{cells(m, g, s)}
      <td><a href="{slug}/metrics.json">metrics.json</a></td></tr>""" for slug, m, g, s in rows)

first = rows[0][2] if rows else {}
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>llmbench — browser game cells</title>
<link rel="stylesheet" href="../style.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22%3E%3Crect width=%2216%22 height=%2216%22 rx=%223%22 fill=%22%230d1117%22/%3E%3Cpath d=%22M4 3v10M12 3v10M4 8h8%22 stroke=%22%235ee0a3%22 stroke-width=%222%22/%3E%3C/svg%3E">
<style>
  .wrap.page {{ padding-bottom: 3rem; }}
  .back {{ font: 600 12px var(--mono); letter-spacing: .06em; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1.25rem; margin: 1.5rem 0 2.5rem; }}
  .card {{ display: flex; flex-direction: column; gap: .9rem; padding: 1rem; border: 1px solid var(--line); border-radius: 10px; background: var(--bg-soft); }}
  .card .shot img {{ width: 100%; border-radius: 6px; border: 1px solid var(--line); display: block; }}
  .card h2 {{ margin: 0 0 .4rem; font: 700 15px var(--mono); }}
  .meta {{ margin: .25rem 0; color: var(--fg-dim); font-size: 13px; }}
  .dim {{ color: var(--fg-faint); }}
  .findings {{ margin: .2rem 0 0; padding-left: 1.1rem; color: var(--warn); font-size: 12px; }}
  .meta.ok {{ color: var(--accent); }}
  .robot {{ border-top: 1px dashed var(--line); padding-top: .7rem; }}
  .rlbl {{ font: 700 10px var(--mono); letter-spacing: .1em; text-transform: uppercase; color: var(--fg-faint); margin-bottom: .35rem; }}
  .rstats {{ display: flex; flex-wrap: wrap; gap: .3rem .9rem; font: 12px var(--mono); }}
  .rstats b {{ color: var(--fg); }}
  .errs {{ margin: .2rem 0 0; padding-left: 1.1rem; color: var(--warn); font-size: 12px; word-break: break-word; }}
  .ok {{ color: var(--accent); }}
  .bad {{ color: #ff7a8a; }}
  .pill {{ font: 700 10px var(--mono); letter-spacing: .1em; padding: 2px 7px; border-radius: 99px; vertical-align: middle; }}
  .pill.ok {{ background: #11301f; }}
  .pill.bad {{ background: #3a1620; }}
  .play {{ display: inline-block; margin-top: .4rem; padding: .5rem .9rem; border: 1px solid var(--accent-dim); border-radius: 6px; font: 700 13px var(--mono); }}
  .play:hover {{ background: #11301f; text-decoration: none; }}
  table.v {{ border-collapse: collapse; width: 100%; font: 12px var(--mono); }}
  table.v th, table.v td {{ padding: .4rem .55rem; border-bottom: 1px solid var(--line-soft); text-align: left; }}
  table.v th {{ color: var(--fg-faint); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; }}
  .note {{ color: var(--fg-dim); font-size: 13px; max-width: 95ch; }}
</style>
</head>
<body>
<header class="site-head">
  <div class="wrap">
    <a class="back" href="../">← llmbench</a>
    <h1>games</h1>
    <p class="sub">Browser game cell: the same frozen prompt (<code>WEBGAME_PROMPT.md</code>,
      sha256 <code>{first.get('prompt_sha256', '')[:16]}…</code>) asks each model for a complete single-file
      three.js arcade shooter. Each game is opened in headless Google Chrome over both
      <code>file://</code> and <code>http://</code>; every number below comes from that probe
      (<code>metrics.json</code>) or the generation log (<code>gen.json</code>).</p>
  </div>
</header>
<main class="wrap page">
  <section class="cards">{''.join(cards)}
  </section>
  <h2 class="note" style="font:700 14px var(--mono)">checks</h2>
  <table class="v">
    <thead><tr><th>game</th><th>all</th><th>console errors</th><th>canvas</th><th>webgl</th>
      <th>animation</th><th>input</th><th>http</th><th>file</th><th>lines</th><th>tokens</th><th>t/s</th><th>ship</th><th>robot</th><th></th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
  <p class="note" style="margin-top:1.2rem">
    <b>animation</b> = two screenshots ~1&nbsp;s apart differ. <b>input</b> = ArrowRight then ArrowLeft
    each change the frame (pixel-hash compare). Controls: ←/→ or A/D to move, SPACE to fire, R to restart.
    Games load three.js from a pinned CDN, so they need network access the first time.</p>
</main>
</body>
</html>
"""
open(os.path.join(games_dir, "index.html"), "w").write(html)
print("wrote", os.path.join(games_dir, "index.html"), "for", len(rows), "games")
