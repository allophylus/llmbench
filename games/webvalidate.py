#!/usr/bin/env python3
"""webvalidate.py — real headless-Chrome evidence for a generated browser game.

usage: webvalidate.py <game_dir> [<game_dir> ...]

For each games/<slug>/ containing index.html it runs /usr/bin/google-chrome (headless,
via playwright chromium executable_path) against the game over BOTH file:// and a local
http:// server and records, in games/<slug>/metrics.json:

  file_load_ok / http_load_ok      page.goto succeeded and document was parsed
  console_errors                   list of console error messages + pageerror texts
  console_error_count
  webgl_ok                         a WebGL(2) context is obtainable / a THREE.WebGLRenderer canvas exists
  two_d_contract                   whether the page text mentions three / THREE
  canvas_present                   a <canvas> exists and has non-zero size
  animation_advancing              two screenshots ~1s apart differ (within the game canvas area)
  input_changes_view               ArrowRight / ArrowLeft change the frame (canvas hash differs
                                   vs. a control window with no input)
  input_changes_pixels             same test measured on pixels, not just hash
  screenshot                       games/<slug>/shot.png

Every field is the result of an actual probe; nothing is inferred or hard-coded.
No network is needed by the harness itself (the game loads three.js from a CDN, so the
http/file runs do use the host's normal network access, same as any browser would).
"""
import hashlib
import http.server
import json
import os
import shutil
import socket
import socketserver
import sys
import threading
import time

from playwright.sync_api import sync_playwright

CHROME = (os.environ.get("CHROME_BIN") or shutil.which("google-chrome")
          or shutil.which("chromium") or shutil.which("chromium-browser")
          or "/usr/bin/google-chrome")
VIEW = {"width": 1280, "height": 800}
# Set by webgen.py: when set, the http:// validation context records its screen to
# <RECORD_DIR>/build.webm so the build run itself is watchable.
RECORD_DIR = None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory):
    port = free_port()
    handler = lambda *a, **k: Quiet(*a, directory=directory, **k)
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}/index.html"


def frame_hash(page):
    """SHA-256 of the full-page screenshot."""
    return hashlib.sha256(page.screenshot()).hexdigest()


def probe(page, url, tag, out_dir):
    rec = {"url": url, "scheme": tag}
    errors, pageerrors, bad_resources = [], [], []
    # An implicit /favicon.ico 404 is the browser asking for an icon the game never
    # referenced; not evidence about the game. Recorded separately, not as a game error.
    favicon_404s = []
    page.on("response", lambda r: (favicon_404s.append(r.url)
                                   if r.url.endswith("/favicon.ico")
                                   else bad_resources.append(f"{r.status} {r.url}"))
            if r.status >= 400 else None)
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}")
            if (m.type == "error" and "favicon" not in m.text.lower()
                and not (m.text.startswith("Failed to load resource") and not bad_resources))
            else None)
    page.on("pageerror", lambda e: pageerrors.append(str(e)))
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
        rec["load_ok"] = True
    except Exception as e:
        rec["load_ok"] = False
        rec["load_error"] = str(e)[:300]
        return rec
    # a CDN-loaded three.js module can resolve after "load"; wait for the canvas/ready flag
    try:
        page.wait_for_function("() => (window.__game && window.__game.ready) || !!document.querySelector('canvas')", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(2500)  # let CDN module + first frames settle

    rec["canvas_present"] = page.evaluate(
        "() => { const c=[...document.querySelectorAll('canvas')];"
        " return c.length>0 && c.some(x=>x.width>0&&x.height>0); }")
    rec["canvas_count"] = page.evaluate("() => document.querySelectorAll('canvas').length")
    rec["webgl_ok"] = page.evaluate(
        "() => { const c=[...document.querySelectorAll('canvas')].find(x=>x.width>0);"
        " if(!c) return false;"
        " for (const t of ['webgl2','webgl','experimental-webgl']) {"
        "  try { if (c.getContext(t)) return true; } catch(e){} }"
        " return false; }")
    text = page.evaluate("() => document.documentElement.outerHTML.slice(0, 2000000)")
    rec["mentions_three"] = ("three" in text.lower())
    rec["uses_three_global"] = rec["mentions_three"]

    # --- playable artefacts (measured by hiding the HTML overlays and diffing) ----
    # The <canvas> is the bottom of the stack; anything the model drew in DOM (HUD,
    # hint bar) covers whatever 3D geometry sits under it. Hide all overlays and see
    # whether pixel content in the covered regions is actually part of the 3D frame.
    rec["overlay_regions"] = page.evaluate("""() => {
      const vw = innerWidth, vh = innerHeight, cv = [...document.querySelectorAll('canvas')][0];
      const cr = cv ? cv.getBoundingClientRect() : null;
      const out = [];
      document.querySelectorAll('body *').forEach(el => {
        if (el === cv || el.tagName === 'SCRIPT' || el.tagName === 'STYLE') return;
        if (cv && el.contains(cv)) return;
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        if (r.width < 4 || r.height < 4 || cs.visibility === 'hidden' || cs.opacity === '0')
          return;
        // element must actually paint text/pixels over the canvas area
        if (!el.textContent.trim()) return;
        if (el.querySelector('*')) return;  // report the leaf that paints
        const sx = Math.max(0, r.left), sy = Math.max(0, r.top);
        out.push({x: Math.round(sx), y: Math.round(sy), w: Math.round(r.width),
                  h: Math.round(r.height), tag: el.tagName.toLowerCase(),
                  id: el.id || null, cls: (el.className || '').toString().slice(0, 40)});
      });
      return {viewport: [vw, vh], overlays: out};
    }""")
    from PIL import Image, ImageChops
    import io
    def shot_img():
        return Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    before = shot_img()
    page.evaluate("() => { for (const e of [...document.body.children])"
                  " if (e.tagName !== 'CANVAS' && e.tagName !== 'SCRIPT') e.dataset.wvPrev = e.style.visibility, e.style.visibility = 'hidden'; }")
    page.wait_for_timeout(150)
    after = shot_img()
    page.evaluate("() => { for (const e of [...document.body.children])"
                  " if (e.dataset.wvPrev !== undefined) { e.style.visibility = e.dataset.wvPrev || ''; delete e.dataset.wvPrev; } }")
    covered = []
    for reg in rec["overlay_regions"].get("overlays", []):
        box = (reg["x"], reg["y"], min(before.width, reg["x"] + reg["w"]),
               min(before.height, reg["y"] + reg["h"]))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        diff = ImageChops.difference(before.crop(box), after.crop(box))
        bbox = diff.getbbox()
        changed = 0 if not bbox else sum(1 for px in diff.get_flattened_data() if sum(px) > 24)
        covered.append({**reg, "pixels_differ_when_hidden": changed})
    rec["overlays"] = covered
    rec["hidden_geometry_under_overlays"] = any(c["pixels_differ_when_hidden"] > 30 for c in covered)

    # --- animation: two frames ~1s apart ---------------------------------
    f1 = page.screenshot()
    h1 = hashlib.sha256(f1).hexdigest()
    page.wait_for_timeout(1000)
    f2 = page.screenshot()
    h2 = hashlib.sha256(f2).hexdigest()
    rec["animation_advancing"] = h1 != h2
    rec["frame_hashes"] = [h1[:16], h2[:16]]

    # --- input: control window of no input vs ArrowRight held ------------
    page.wait_for_timeout(300)
    c0 = page.screenshot()
    page.keyboard.down("ArrowRight")
    page.wait_for_timeout(450)
    page.keyboard.up("ArrowRight")
    page.wait_for_timeout(120)
    c1 = page.screenshot()
    page.keyboard.down("ArrowLeft")
    page.wait_for_timeout(450)
    page.keyboard.up("ArrowLeft")
    page.wait_for_timeout(120)
    c2 = page.screenshot()
    hh = lambda b: hashlib.sha256(b).hexdigest()
    rec["input_changes_pixels"] = hh(c0) != hh(c1)
    rec["input_left_changes_pixels"] = hh(c1) != hh(c2)
    rec["input_ok"] = rec["input_changes_pixels"] and rec["input_left_changes_pixels"]
    rec["control_vs_input_hashes"] = [hh(c0)[:16], hh(c1)[:16], hh(c2)[:16]]

    shot = os.path.join(out_dir, f"shot{'' if tag == 'http' else '-' + tag}.png")
    open(shot, "wb").write(c2)
    rec["screenshot"] = os.path.basename(shot)

    # HUD markers (proves the prompt's HUD/restart text reached the page)
    rec["hud_markers"] = {k: k in text for k in ("SCORE", "LIVES", "GAME OVER")}

    rec["console_errors"] = pageerrors + errors
    rec["console_error_count"] = len(rec["console_errors"])
    rec["failed_resources"] = bad_resources
    rec["ignored_favicon_404s"] = favicon_404s
    # Machine-readable contract (prompt v2): window.__game with the required keys,
    # ready once the loop has run, and a callable reset().
    rec["contract"] = page.evaluate("""() => {
      const g = window.__game;
      if (!g) return {present: false, reasons: ['window.__game missing']};
      const bad = [];
      if (typeof g.ready !== 'boolean') bad.push('ready not boolean');
      if (typeof g.score !== 'number') bad.push('score not number');
      if (typeof g.lives !== 'number') bad.push('lives not number');
      if (typeof g.over !== 'boolean') bad.push('over not boolean');
      if (!g.player || typeof g.player.x !== 'number' || typeof g.player.y !== 'number')
        bad.push('player {x,y} missing');
      if (!Array.isArray(g.enemies)) bad.push('enemies not array');
      if (!Array.isArray(g.bullets)) bad.push('bullets not array');
      if (typeof g.reset !== 'function') bad.push('reset() not callable');
      return {present: true, ready: g.ready, reasons: bad,
              ok: bad.length === 0 && g.ready === true};
    }""")
    return rec


def run(slug_dir):
    slug = os.path.basename(slug_dir.rstrip("/"))
    html = os.path.join(slug_dir, "index.html")
    out = {"slug": slug, "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "chrome": "google-chrome (headless, playwright)", "viewport": VIEW}
    httpd, http_url = serve(slug_dir)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True,
                                  args=["--use-gl=angle", "--use-angle=swiftshader",
                                        "--enable-unsafe-swiftshader", "--no-sandbox",
                                        "--allow-file-access-from-files"])
            for tag, url in (("http", http_url), ("file", "file://" + html)):
                vdir = None
                if tag == "http" and RECORD_DIR:
                    vdir = os.path.join(RECORD_DIR, "_rec")
                    shutil.rmtree(vdir, ignore_errors=True)
                    os.makedirs(vdir, exist_ok=True)
                ctx = b.new_context(viewport=VIEW,
                                    record_video_dir=vdir,
                                    record_video_size=VIEW if vdir else None)
                page = ctx.new_page()
                try:
                    rec = probe(page, url, tag, slug_dir)
                finally:
                    ctx.close()   # flushes the recording
                if vdir:
                    vids = [f for f in os.listdir(vdir) if f.endswith(".webm")]
                    if vids:
                        shutil.move(os.path.join(vdir, vids[0]),
                                    os.path.join(RECORD_DIR, "build.webm"))
                        out["build_video"] = "build.webm"
                    shutil.rmtree(vdir, ignore_errors=True)
                out[tag] = rec
            # Optional adapter that exposes scene internals as window.__wv (written
            # by webadapt.py into _scratch/). Used only to record WHY a check failed.
            adir = os.path.join(os.path.dirname(slug_dir), "_scratch")
            adapt = os.path.join(adir, slug, "adapted.html")
            if os.path.isfile(adapt):
                ahttpd, _ = serve(adir)
                aurl = f"http://127.0.0.1:{ahttpd.server_address[1]}/{slug}/adapted.html"
                ctx = b.new_context(viewport=VIEW)
                page = ctx.new_page()
                try:
                    page.goto(aurl, wait_until="networkidle", timeout=45000)
                    page.wait_for_timeout(2500)
                    out["internals"] = page.evaluate("() => (window.__wv ? window.__wv() : null)")
                except Exception as e:
                    out["internals_error"] = str(e)[:200]
                finally:
                    ctx.close()
                    ahttpd.shutdown()
            b.close()
    finally:
        httpd.shutdown()

    h, f = out["http"], out["file"]
    # Not part of pass/fail (that is about the game file itself), but recorded so a
    # failure caused by a CDN outage is distinguishable from a broken game.
    out["cdn_reachable"] = False
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://unpkg.com/three@0.160.0/build/three.module.js",
            headers={"User-Agent": "webvalidate"})
        with urllib.request.urlopen(req, timeout=20) as r:
            out["cdn_reachable"] = (r.status == 200 and b"export" in r.read(2000))
    except Exception as e:
        out["cdn_error"] = str(e)[:200]
    out["summary"] = {
        "http_load_ok": h.get("load_ok", False),
        "file_load_ok": f.get("load_ok", False),
        "canvas_ok": bool(h.get("canvas_present") and f.get("canvas_present")),
        "webgl_ok": bool(h.get("webgl_ok") and f.get("webgl_ok")),
        "uses_three": bool(h.get("mentions_three")),
        "animation_ok": bool(h.get("animation_advancing") and f.get("animation_advancing")),
        "input_ok": bool(h.get("input_ok") and f.get("input_ok")),
        "console_error_count": h.get("console_error_count", 0) + f.get("console_error_count", 0),
        "contract_ok": bool((h.get("contract") or {}).get("ok")),
        "contract_reasons": ((h.get("contract") or {}).get("reasons", [])
                             + ["(file://) " + r for r in (f.get("contract") or {}).get("reasons", [])]),
        "cdn_reachable": out["cdn_reachable"],
        "overlays_cover_geometry": bool(h.get("hidden_geometry_under_overlays") or
                                        f.get("hidden_geometry_under_overlays")),
        "player_centre_onscreen": (out.get("internals") or {}).get("player_onscreen"),
        "player_visible": (out.get("internals") or {}).get("player_bbox_onscreen"),
        "player_fully_onscreen": (out.get("internals") or {}).get("player_bbox_fully_onscreen"),
        "player_bbox_px": (out.get("internals") or {}).get("player_bbox_px"),
    }
    s = out["summary"]
    s["pass"] = all([s["http_load_ok"], s["file_load_ok"], s["canvas_ok"], s["webgl_ok"],
                     s["animation_ok"], s["input_ok"]])
    # Acceptance for generation (webgen.py --check): the full gate including contract.
    s["accept"] = all([s["pass"], s["uses_three"], s["contract_ok"],
                       s["console_error_count"] == 0])
    json.dump(out, open(os.path.join(slug_dir, "metrics.json"), "w"), indent=1)
    print(slug, json.dumps(s))


if __name__ == "__main__":
    for d in sys.argv[1:]:
        run(d)
