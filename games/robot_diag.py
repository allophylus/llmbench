#!/usr/bin/env python3
"""robot_diag.py — why did the robot score 0? Measures, per game:

  1. FIRE: does pressing Space actually create bullets[] entries? (count before/after)
  2. OVERLAP: while the robot plays, do any bullet/enemy pairs ever overlap in screen
     space (within the same radius the game draws at), and do any world positions
     coincide?  Measured from window.__game only — no source reading.
  3. SCORE WIRING: when a bullet is guaranteed to hit (teleport a bullet onto an
     enemy's position via a debug copy), does the score change AND does the HUD text
     change with it?  Separates "collision broken" from "HUD not wired".
  4. FORCED KILL: teleport the player under an enemy and fire normally.

Verdict per game:
  'game collision broken'      scoring never happens even with a guaranteed overlap,
                               or bullets/enemies never share the collision volume
  'score HUD not wired'        __game.score rises but the on-page HUD text does not
  'robot policy too weak'      overlaps DO happen / scoring works, but the robot misses

usage: robot_diag.py <game_dir> [...]     writes <game_dir>/diag.json
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webvalidate  # serve(), CHROME, VIEW

READ = """
() => {
  const g = window.__game;
  if (!g) return null;
  const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;
  const pts = a => Array.isArray(a) ? a.map(p => ({x: num(p && p.x), y: num(p && p.y)}))
                                     .filter(p => p.x !== null) : [];
  const c = document.querySelector('canvas');
  const hud = document.body.innerText.replace(/\\s+/g, ' ');
  return {score: num(g.score), lives: num(g.lives), over: !!g.over,
          player: g.player ? {x: num(g.player.x), y: num(g.player.y)} : null,
          enemies: pts(g.enemies), bullets: pts(g.bullets),
          w: c ? c.clientWidth : null, h: c ? c.clientHeight : null, hud};
}
"""

# Debug copy that exposes the live arrays, so we can force a guaranteed hit.
DEBUG_PATCH = (
    "function loop() {",
    "window.__dbg={get:()=>({bullets,enemies,player})};\nfunction loop() {",
)


def make_debug(src):
    out = src
    for old, new in (("function loop() {", "window.__dbg={get:()=>({bullets,enemies,player})};\nfunction loop() {"),):
        if old in out:
            out = out.replace(old, new, 1)
            break
    return out if "__dbg" in out else None


def key(page, kind, k):
    page.evaluate("([kind,k]) => window.dispatchEvent(new KeyboardEvent(kind,"
                  " {key:k, code:k===' '?'Space':k, bubbles:true}))", [kind, k])


def diag(slug_dir):
    slug = os.path.basename(slug_dir.rstrip("/"))
    res = {"slug": slug}
    src = open(os.path.join(slug_dir, "index.html")).read()
    httpd, url = webvalidate.serve(slug_dir)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=webvalidate.CHROME, headless=True,
                                  args=["--use-gl=angle", "--use-angle=swiftshader",
                                        "--enable-unsafe-swiftshader", "--no-sandbox"])
            pg = b.new_page(viewport=webvalidate.VIEW)
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(url, wait_until="load", timeout=45000)
            pg.wait_for_timeout(2500)

            # ---------- 1. does fire create bullets? ----------
            before = pg.evaluate(READ)
            key(pg, "keydown", " ")
            pg.wait_for_timeout(500)
            key(pg, "keyup", " ")
            after = pg.evaluate(READ)
            res["fire"] = {"bullets_before": len(before["bullets"]),
                           "bullets_after": len(after["bullets"]),
                           "fire_creates_bullets": len(after["bullets"]) > len(before["bullets"])}

            # ---------- 2. overlap observation during a 12 s burst ----------
            key(pg, "keydown", " ")
            min_d = 1e9
            n_pairs = 0
            overlaps = 0
            for _ in range(120):                      # 12 s at 10 Hz
                st = pg.evaluate(READ)
                for bl in st["bullets"]:
                    for e in st["enemies"]:
                        n_pairs += 1
                        d = ((bl["x"] - e["x"]) ** 2 + (bl["y"] - e["y"]) ** 2) ** 0.5
                        min_d = min(min_d, d)
                        if d < 12:                    # ~a ship-half-width on screen
                            overlaps += 1
                pg.wait_for_timeout(100)
            key(pg, "keyup", " ")
            res["overlap"] = {"pairs_sampled": n_pairs,
                              "min_screen_distance_px": round(min_d, 2) if n_pairs else None,
                              "close_pairs_lt12px": overlaps,
                              "observed": overlaps > 0}

            # ---------- 3. guaranteed hit via debug copy ----------
            dbg = make_debug(src)
            if dbg is None:
                res["forced_hit"] = {"skipped": "could not expose internals (no `function loop()`)"}
            else:
                ddir = os.path.join(slug_dir, "_diag")
                os.makedirs(ddir, exist_ok=True)
                open(os.path.join(ddir, "index.html"), "w").write(dbg)
                dhttpd, durl = webvalidate.serve(ddir)
                try:
                    pg2 = b.new_page(viewport=webvalidate.VIEW)
                    pg2.goto(durl, wait_until="load", timeout=45000)
                    pg2.wait_for_timeout(2500)
                    key(pg2, "keydown", " ")
                    pg2.wait_for_timeout(400)
                    key(pg2, "keyup", " ")
                    r = pg2.evaluate("""async () => {
                      const s0 = {score: __game.score, hud: document.body.innerText};
                      const d = window.__dbg.get();
                      if (!d.bullets.length || !d.enemies.length)
                        return {skip: 'no bullet or no enemy', bullets: d.bullets.length,
                                enemies: d.enemies.length};
                      const e = d.enemies[0], bl = d.bullets[0];
                      bl.position.copy(e.position);        // guaranteed overlap
                      const dist = bl.position.distanceTo(e.position);
                      await new Promise(r => setTimeout(r, 500));
                      return {skip: null, dist_before_tick: dist,
                              score_before: s0.score, score_after: __game.score,
                              hud_before: s0.hud.replace(/\\s+/g,' ').slice(0,120),
                              hud_after: document.body.innerText.replace(/\\s+/g,' ').slice(0,120)};
                    }""")
                    rs = r.get("score_after"), r.get("score_before")
                    res["forced_hit"] = {
                        **r,
                        "score_incremented": (rs[0] is not None and rs[1] is not None
                                              and rs[0] > rs[1]),
                        "hud_changed": r.get("hud_before") != r.get("hud_after"),
                    }
                    pg2.close()
                finally:
                    dhttpd.shutdown()
                    import shutil as _sh
                    _sh.rmtree(ddir, ignore_errors=True)

            # ---------- 4. true 3D separation in normal play (world units) ----------
            dbg2 = make_debug(src)
            if dbg2:
                src2 = dbg2.replace(
                    "window.__dbg={get:()=>({bullets,enemies,player})};",
                    "window.__dbg={get:()=>({bullets:bullets.map(b=>b.position.clone()),"
                    "enemies:enemies.map(e=>e.position.clone())})};")
                ddir = os.path.join(slug_dir, "_diag2")
                os.makedirs(ddir, exist_ok=True)
                open(os.path.join(ddir, "index.html"), "w").write(src2)
                dhttpd, durl = webvalidate.serve(ddir)
                try:
                    pg3 = b.new_page(viewport=webvalidate.VIEW)
                    pg3.goto(durl, wait_until="load", timeout=45000)
                    pg3.wait_for_timeout(2500)
                    key(pg3, "keydown", " ")
                    best, pair = 1e9, None
                    for _ in range(100):
                        pg3.wait_for_timeout(100)
                        r = pg3.evaluate("""() => { const d = window.__dbg.get(); let m = 1e9, pp = null;
                          for (const b of d.bullets) for (const e of d.enemies) {
                            const dd = b.distanceTo(e);
                            if (dd < m) { m = dd; pp = {bullet: [b.x, b.y, b.z].map(n => +n.toFixed(2)),
                                                       enemy: [e.x, e.y, e.z].map(n => +n.toFixed(2))}; } }
                          return {m, pp, score: window.__game.score}; }""")
                        if r["m"] < best:
                            best, pair = r["m"], r["pp"]
                    key(pg3, "keyup", " ")
                    res["world_separation"] = {
                        "min_distance_units": round(best, 3) if best < 1e8 else None,
                        "pair": pair,
                        "collision_radius_units": 1.4,
                        "reachable": (best < 1.4) if best < 1e8 else None}
                    pg3.close()
                finally:
                    dhttpd.shutdown()
                    import shutil as _sh
                    _sh.rmtree(ddir, ignore_errors=True)

            res["page_errors"] = errs
            b.close()
    finally:
        httpd.shutdown()

    fh = res.get("forced_hit") or {}
    ov = res.get("overlap") or {}
    if fh.get("score_incremented") and not fh.get("hud_changed"):
        verdict = "score HUD not wired"
    elif fh.get("score_incremented"):
        ws = res.get("world_separation") or {}
        if ws.get("reachable") is False:
            verdict = ("game collision broken: bullets never enter the hit volume in "
                       "normal play (min world distance %.2f vs radius %.1f) even though "
                       "the hit test itself scores when forced"
                       % (ws.get("min_distance_units") or -1, ws.get("collision_radius_units") or 0))
        else:
            verdict = "game collision works (robot policy too weak)"
    elif fh.get("skip") or "skipped" in fh:
        verdict = "inconclusive: could not force a hit"
    else:
        verdict = "game collision broken"
    if not (res.get("fire") or {}).get("fire_creates_bullets"):
        verdict = "game collision broken (fire does not create bullets)"
    res["verdict"] = verdict
    json.dump(res, open(os.path.join(slug_dir, "diag.json"), "w"), indent=1)
    print(slug, "->", verdict)
    print(json.dumps({k: res.get(k) for k in ("fire", "overlap", "forced_hit")}, indent=1)[:1200])
    return res


if __name__ == "__main__":
    for d in sys.argv[1:]:
        diag(d)
