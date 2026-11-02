#!/usr/bin/env python3
"""robot_player.py — an automated player that actually plays a generated three.js game.

usage: robot_player.py <game_dir> [<game_dir> ...] [--seconds 60] [--hz 10]
                       [--video none|webm]

Opens games/<slug>/index.html over a local http server in headless /usr/bin/google-chrome
(playwright), waits for window.__game.ready, then runs a closed-loop policy at ~10 Hz:

  read window.__game  ->  pick a target enemy  ->  dispatch real KeyboardEvents
                          (window.dispatchEvent(new KeyboardEvent(...)))  ->  repeat

Policy (deliberately simple, no knowledge of the source code):
  * threat = alive enemy closest to the player in y, weighted by x distance; if it is
    within KEEP_CLEAR px of the player horizontally it must be dodged.
  * desired x = x of the nearest enemy above the player (smallest positive dy), or the
    player centre when no enemy is above. If the threat is close in y AND near the
    player's x, desired x is pushed away from the threat instead.
  * hold ArrowLeft / ArrowRight while |dx| > DEADZONE, release inside it.
  * hold Space while an enemy is within FIRE_BAND px above the player's x column, or when
    any enemy is in the upper half and no shot is in flight.

Records (robot_metrics.json): final score, lives lost, survival seconds, frames advanced
(counted inside the page with requestAnimationFrame), action count (key events
dispatched), whether the page threw, console errors, contract validity.

Also saves robot_play.webm (playwright record_video_dir) and robot_shot.png.

Honesty rules: every number is measured. If the game never exposes window.__game, the
run is marked contract_ok=false and score/lives are reported as null, never as 0.
"""
import argparse
import http.server
import json
import os
import shutil
import socketserver
import sys
import threading
import time
import urllib.parse

from playwright.sync_api import sync_playwright

CHROME = "/usr/bin/google-chrome"
VIEW = {"width": 1280, "height": 800}

READ_STATE = """
() => {
  const g = window.__game;
  if (!g) return null;
  const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;
  const pts = a => Array.isArray(a) ? a.map(p => ({x: num(p && p.x), y: num(p && p.y)}))
                                     .filter(p => p.x !== null && p.y !== null) : [];
  const c = document.querySelector('canvas');
  return {
    ready: !!g.ready, score: num(g.score), lives: num(g.lives), over: !!g.over,
    player: g.player ? {x: num(g.player.x), y: num(g.player.y)} : null,
    enemies: pts(g.enemies), bullets: pts(g.bullets),
    w: c ? c.clientWidth : null, h: c ? c.clientHeight : null,
    has_reset: typeof g.reset === 'function',
  };
}
"""

FRAME_COUNTER = """
() => {
  window.__robotFrames = 0;
  const tick = () => { window.__robotFrames++; requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}
"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory):
    class H(Quiet):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=directory, **k)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), H)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}/index.html"


def key(page, kind, k):
    """Dispatch a real KeyboardEvent on window (never an internal API call)."""
    page.evaluate("([kind, k]) => window.dispatchEvent(new KeyboardEvent(kind,"
                  " {key: k, code: k === ' ' ? 'Space' : k, bubbles: true}))", [kind, k])


def _group(xs, gap):
    """Cluster sorted coordinate values; returns (min, max) of the largest cluster."""
    xs = sorted(xs)
    if not xs:
        return None
    best, cur = [xs[0], xs[0]], [xs[0], xs[0]]
    for v in xs[1:]:
        if v - cur[1] <= gap:
            cur[1] = v
        else:
            if cur[1] - cur[0] > best[1] - best[0]:
                best = cur
            cur = [v, v]
    if cur[1] - cur[0] > best[1] - best[0]:
        best = cur
    return best


HIST = {}   # enemy index-free history is unsafe (list order changes), so we track by slot
TRACK = []  # list of {"sx": [...], "sy": [...], "x", "age"} updated by note_state()


def note_state(st, dt):
    """Track approximate per-enemy screen velocity so the robot can lead its shots."""
    global TRACK
    enemies = st.get("enemies") or []
    used = set()
    new = []
    for e in enemies:
        # match to nearest tracked enemy (enemies move < 60 px between 10 Hz ticks)
        best, bi = None, None
        for i, t in enumerate(TRACK):
            if i in used:
                continue
            d = ((t["x"] - e["x"]) ** 2 + (t["y"] - e["y"]) ** 2) ** 0.5
            if d < 80 and (best is None or d < best):
                best, bi = d, i
        if bi is None:
            new.append({"x": e["x"], "y": e["y"], "vx": 0.0, "vy": 0.0, "n": 1})
        else:
            used.add(bi)
            t = TRACK[bi]
            k = min(1.0, 1.0 / (t["n"] + 1))
            t["vx"] += ((e["x"] - t["x"]) / max(dt, 1e-3) - t["vx"]) * k
            t["vy"] += ((e["y"] - t["y"]) / max(dt, 1e-3) - t["vy"]) * k
            t["x"], t["y"] = e["x"], e["y"]
            t["n"] += 1
            new.append(t)
    TRACK = new


def decide(st, held_ok_key=None):
    """Pure policy: state -> (keys_to_hold, reason). Coordinates are canvas pixels.

    Only window.__game is used; the policy never looks at the game's source.
    Enemies are descending toward larger y, so 'above' means smaller y.
    """
    p, w, h = st.get("player"), st.get("w") or 1280, st.get("h") or 800
    if not p:
        return set(), "no-player"
    px, py = p["x"], p["y"]
    enemies = [e for e in (st.get("enemies") or [])
               if 0 <= e["x"] <= w and 0 <= e["y"] <= h]   # drop off-screen projections
    if not enemies:
        return {" "}, "no-enemies-fire"

    above = [e for e in enemies if e["y"] < py - 0.05 * h]
    keys = set()
    lane = None
    if above:
        # shoot where enemies actually are: densest cluster of their columns
        cols = _group([e["x"] for e in above], 0.03 * w)
        lane = (cols[0] + cols[1]) / 2 if cols else px
        reason = "aim"
    else:
        near = min(enemies, key=lambda e: (e["x"] - px) ** 2 + (e["y"] - py) ** 2)
        lane = near["x"]
        reason = "close"

    # dodge: an enemy that is low on screen and within a ship-width of us horizontally
    danger = [e for e in enemies
              if (e["y"] - py) > -0.10 * h and abs(e["x"] - px) < 0.10 * w]
    if danger:
        d = min(danger, key=lambda e: abs(e["y"] - py))
        lane = px + (0.30 * w if d["x"] >= px else -0.30 * w)
        reason = "dodge"

    lane = max(0.05 * w, min(0.95 * w, lane))
    dx = lane - px
    if abs(dx) > 0.015 * w:
        keys.add("ArrowRight" if dx > 0 else "ArrowLeft")

    # Fire whenever the ship is lined up with the enemy lane. Firing is free (no ammo),
    # and the stream matters more than individual precision.
    if above and abs(lane - px) < 0.06 * w:
        keys.add(" ")
    return keys, reason


def play(slug_dir, seconds=60, hz=10, video=True):
    slug = os.path.basename(slug_dir.rstrip("/"))
    out = {"slug": slug, "hz": hz, "max_seconds": seconds,
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    httpd, url = serve(slug_dir)
    vdir = os.path.join(slug_dir, "_video")
    shutil.rmtree(vdir, ignore_errors=True)
    os.makedirs(vdir, exist_ok=True)
    page_errors, console_errors = [], []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True,
                                  args=["--use-gl=angle", "--use-angle=swiftshader",
                                        "--enable-unsafe-swiftshader", "--no-sandbox"])
            ctx = b.new_context(viewport=VIEW,
                                record_video_dir=vdir if video else None,
                                record_video_size=VIEW if video else None)
            page = ctx.new_page()
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}")
                    if m.type == "error" and "favicon" not in m.text.lower() else None)
            page.goto(url, wait_until="load", timeout=45000)

            # wait for the contract
            ready = False
            t_wait0 = time.time()
            for _ in range(300):                      # up to 30 s
                st = page.evaluate(READ_STATE)
                if st and st.get("ready"):
                    ready = True
                    break
                page.wait_for_timeout(100)
            out["ready_wait_s"] = round(time.time() - t_wait0, 2)
            out["contract_ok"] = bool(ready)
            first = page.evaluate(READ_STATE) if ready else None
            out["state_at_ready"] = first
            if ready and first:
                out["contract_has_reset"] = bool(first.get("has_reset"))
            else:
                out["contract_has_reset"] = False

            if ready:
                page.evaluate(FRAME_COUNTER)
                t0 = time.time()
                held = set()
                actions = 0
                samples = 0
                reasons = {}
                prev = None
                trace = []
                score_events = []
                closest_dy, closest_dx = 1e9, 1e9
                closest_pair = None
                max_bullets = max_enemies = 0
                min_lives = first.get("lives")
                last = first
                while time.time() - t0 < seconds:
                    st = page.evaluate(READ_STATE)
                    if not st:
                        out["contract_lost"] = True
                        break
                    samples += 1
                    last = st
                    if prev and st.get("score") is not None and prev.get("score") is not None \
                            and st["score"] > prev["score"]:
                        score_events.append({"t": round(time.time() - t0, 2),
                                             "score": st["score"]})
                    for bl in (st.get("bullets") or []):
                        for e in (st.get("enemies") or []):
                            dy = abs(bl["y"] - e["y"])
                            dx = abs(bl["x"] - e["x"])
                            if dy < closest_dy:
                                closest_dy = dy
                                closest_pair = {"bullet": [round(bl["x"]), round(bl["y"])],
                                                "enemy": [round(e["x"]), round(e["y"])],
                                                "t": round(time.time() - t0, 2)}
                            if dx < closest_dx:
                                closest_dx = dx
                    max_bullets = max(max_bullets, len(st.get("bullets") or []))
                    max_enemies = max(max_enemies, len(st.get("enemies") or []))
                    if st.get("lives") is not None and min_lives is not None:
                        min_lives = min(min_lives, st["lives"])
                    if st.get("over"):
                        break
                    note_state(st, 1.0 / hz)
                    want, why = decide(st, held)
                    if len(trace) < 40:   # keep the first ticks of flight for diagnosis
                        trace.append({"t": round(time.time() - t0, 2), "why": why,
                                      "keys": sorted(want),
                                      "player": [round(st["player"]["x"])],
                                      "enemies": [[round(e["x"]), round(e["y"])]
                                                  for e in st["enemies"][:6]],
                                      "bullets": [[round(b["x"]), round(b["y"])]
                                                  for b in st["bullets"][:4]]})
                    reasons[why] = reasons.get(why, 0) + 1
                    for k in list(held - want):
                        key(page, "keyup", k)
                        held.discard(k)
                        actions += 1
                    for k in list(want - held):
                        key(page, "keydown", k)
                        held.add(k)
                        actions += 1
                    prev = st
                    page.wait_for_timeout(int(1000 / hz))

                for k in list(held):
                    key(page, "keyup", k)
                    actions += 1
                survival = time.time() - t0
                frames = page.evaluate("() => window.__robotFrames || 0")
                out.update({
                    "final_score": last.get("score"),
                    "final_lives": last.get("lives"),
                    "lives_lost": (min_lives is not None and first.get("lives") is not None
                                   and first["lives"] - min_lives),
                    "over": last.get("over"),
                    "survival_s": round(survival, 2),
                    "samples": samples,
                    "frames_advanced": frames,
                    "approx_fps": round(frames / survival, 1) if survival > 0 else None,
                    "action_count": actions,
                    "score_events": score_events,
                    "policy_reasons": reasons,
                    "trace_first_ticks": trace,
                    "enemies_at_end": len(last.get("enemies") or []),
                    "max_bullets_on_screen": max_bullets,
                    "max_enemies_on_screen": max_enemies,
                    "closest_bullet_to_enemy_px": {
                        "min_dy": None if closest_dy > 1e8 else round(closest_dy, 1),
                        "min_dx": None if closest_dx > 1e8 else round(closest_dx, 1),
                        "at": closest_pair,
                        "note": "screen space; a hit is impossible if min_dy stays far above "
                                "the collision size the game uses",
                    },
                })
                page.screenshot(path=os.path.join(slug_dir, "robot_shot.png"))
            else:
                out.update({"final_score": None, "final_lives": None, "lives_lost": None,
                            "survival_s": 0.0, "frames_advanced": 0, "action_count": 0,
                            "note": "window.__game.ready never became true"})
            out["page_threw"] = bool(page_errors)
            out["page_errors"] = page_errors
            out["console_errors"] = console_errors
            ctx.close()   # flushes the video
            b.close()
            if video:
                vids = [f for f in os.listdir(vdir) if f.endswith(".webm")]
                if vids:
                    src = os.path.join(vdir, vids[0])
                    dst = os.path.join(slug_dir, "robot_play.webm")
                    shutil.move(src, dst)
                    out["video"] = "robot_play.webm"
    finally:
        httpd.shutdown()
        shutil.rmtree(vdir, ignore_errors=True)

    out["scored"] = (out.get("final_score") or 0) > 0
    out["verdict"] = ("scored" if out["scored"]
                      else "zero-score" if out.get("contract_ok") and out.get("final_score") == 0
                      else "no-contract")
    json.dump(out, open(os.path.join(slug_dir, "robot_metrics.json"), "w"), indent=1)
    print(slug, json.dumps({k: out.get(k) for k in
                            ("verdict", "contract_ok", "final_score", "lives_lost",
                             "survival_s", "frames_advanced", "action_count", "page_threw")}))
    return out


def to_mp4(slug_dir):
    webm = os.path.join(slug_dir, "robot_play.webm")
    mp4 = os.path.join(slug_dir, "robot_play.mp4")
    if not os.path.isfile(webm) or shutil.which("ffmpeg") is None:
        return False
    r = os.system(f'ffmpeg -y -loglevel error -i "{webm}" -c:v libx264 -pix_fmt yuv420p '
                  f'-movflags +faststart "{mp4}"')
    return r == 0 and os.path.isfile(mp4)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--hz", type=int, default=10)
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()
    for d in a.dirs:
        r = play(d, a.seconds, a.hz, video=not a.no_video)
        if not a.no_video:
            r["mp4"] = to_mp4(d)
            json.dump(r, open(os.path.join(d, "robot_metrics.json"), "w"), indent=1)
