
from playwright.sync_api import sync_playwright
import json, sys
path = sys.argv[1]
vid = sys.argv[2] if len(sys.argv) > 2 else ""
out = {"load": False, "canvas": 0, "ready": False, "errors": []}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1280, "height": 800},
                        **({"record_video_dir": vid, "record_video_size": {"width": 1280, "height": 800}} if vid else {}))
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: out["errors"].append("pageerror: " + str(e)[:200]))
    pg.on("console", lambda m: out["errors"].append("console: " + m.text[:200]) if m.type == "error" else None)
    try:
        pg.goto("file://" + path, wait_until="load", timeout=30000)
        pg.wait_for_timeout(2500)
        out["load"] = True
        out["canvas"] = pg.evaluate("()=>document.querySelectorAll('canvas').length")
        out["ready"] = pg.evaluate("()=>!!(window.__game && window.__game.ready)")
    except Exception as e:
        out["errors"].append("nav: " + str(e)[:200])
    ctx.close()
    b.close()
print(json.dumps(out))
