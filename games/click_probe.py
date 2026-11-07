#!/usr/bin/env python3
"""click_probe.py — re-score a generated game after dispatching the start gesture.

Why (known harness limit): webvalidate never clicks. A game that renders behind a
"click to start" overlay therefore fails animation/input even though a human plays it
fine. This probe loads the same page over http, dispatches pointerdown+click on every
visible button / overlay / the canvas centre, then re-measures the three checks the
gate cares about, and records exactly what it clicked.

usage: click_probe.py <game_dir> [--json /abs/out.json]
Exit 0 when the page passes after the gesture.
"""
import argparse, hashlib, http.server, json, os, socket, socketserver, subprocess, sys, threading, time

from playwright.sync_api import sync_playwright

CHROME = "/usr/bin/google-chrome"
VIEW = {"width": 1280, "height": 800}


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    d = os.path.abspath(a.dir)
    os.chdir(d)
    port = free_port()
    httpd = socketserver.TCPServer(("127.0.0.1", port), Quiet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/index.html"
    out = {"dir": d, "url": url, "steps": [], "errors": []}

    def shot_hash(pg):
        return hashlib.sha256(pg.screenshot()).hexdigest()

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport=VIEW)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: out["errors"].append("pageerror: " + str(e)[:200]))
        pg.on("console", lambda m: out["errors"].append("console: " + m.text[:200]) if m.type == "error" else None)
        pg.goto(url, wait_until="load", timeout=45000)
        try:
            pg.wait_for_function("() => (window.__game && window.__game.ready) || !!document.querySelector('canvas')", timeout=15000)
        except Exception:
            pass
        pg.wait_for_timeout(2500)

        out["before"] = {
            "canvas": pg.evaluate("() => document.querySelectorAll('canvas').length"),
            "game": pg.evaluate("() => typeof window.__game !== 'undefined'"),
            "advancing": shot_hash(pg) != (pg.wait_for_timeout(1000) or shot_hash(pg)),
        }

        # what is on top of the canvas right now?
        out["targets"] = pg.evaluate("""() => {
          const out=[]; const cv=[...document.querySelectorAll('canvas')][0];
          const cr = cv ? cv.getBoundingClientRect() : {left:0,top:0,width:innerWidth,height:innerHeight};
          for (const el of document.querySelectorAll('button,[role=button],a,div,span,p')) {
            const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
            if (r.width < 20 || r.height < 12) continue;
            if (cs.visibility === 'hidden' || cs.opacity === '0' || cs.pointerEvents === 'none') continue;
            const txt = (el.textContent || '').trim().slice(0, 40);
            const looks = /start|tap|click|play|begin|press|go/i.test(txt) || el.tagName === 'BUTTON';
            if (!looks) continue;
            out.push({tag: el.tagName, id: el.id || '', txt, x: r.left + r.width/2, y: r.top + r.height/2});
          }
          return {canvas: [cr.left + cr.width/2, cr.top + cr.height/2], targets: out.slice(0, 8)};
        }""")

        clicks = ([t for t in out["targets"]["targets"]]
                  + [{"tag": "canvas-centre",
                      "x": out["targets"]["canvas"][0], "y": out["targets"]["canvas"][1],
                      "txt": "(canvas centre)"}])
        for c in clicks:
            try:
                pg.mouse.move(c["x"], c["y"])
                pg.mouse.down()
                pg.mouse.up()
                pg.wait_for_timeout(120)
                pg.mouse.click(c["x"], c["y"])
                pg.wait_for_timeout(200)
                out["steps"].append(f"clicked {c['tag']} '{c.get('txt','')}' at ({int(c['x'])},{int(c['y'])})")
            except Exception as e:
                out["steps"].append(f"click failed at ({c['x']},{c['y']}): {e}")
        pg.wait_for_timeout(700)
        # some builds wait for a keyboard 'start' too
        for key in ("Space", "Enter"):
            pg.keyboard.press(key)
            pg.wait_for_timeout(250)

        h1 = shot_hash(pg)
        pg.wait_for_timeout(1200)
        h2 = shot_hash(pg)
        out["after"] = {
            "advancing": h1 != h2,
            "game": pg.evaluate("() => typeof window.__game !== 'undefined'"),
            "game_ready": pg.evaluate("() => !!(window.__game && window.__game.ready)"),
            "game_keys": pg.evaluate("() => window.__game ? Object.keys(window.__game).slice(0,20) : []"),
        }
        # input: hold ArrowRight / ArrowLeft and compare frames
        c0 = pg.screenshot()
        pg.keyboard.down("ArrowRight"); pg.wait_for_timeout(500); pg.keyboard.up("ArrowRight")
        pg.wait_for_timeout(150)
        c1 = pg.screenshot()
        pg.keyboard.down("ArrowLeft"); pg.wait_for_timeout(500); pg.keyboard.up("ArrowLeft")
        pg.wait_for_timeout(150)
        c2 = pg.screenshot()
        out["after"]["input_right"] = hashlib.sha256(c0).hexdigest() != hashlib.sha256(c1).hexdigest()
        out["after"]["input_left"] = hashlib.sha256(c0).hexdigest() != hashlib.sha256(c2).hexdigest()
        pg.screenshot(path=os.path.join(d, "shot-after-click.png"))
        ctx.close(); b.close()
    httpd.shutdown()

    ok = bool(out["after"]["advancing"] and out["after"]["game"]
              and (out["after"]["input_right"] or out["after"]["input_left"]))
    out["pass_after_click"] = ok
    txt = json.dumps(out, indent=1)
    if a.json:
        open(a.json, "w").write(txt)
    print(txt)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
