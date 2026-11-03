#!/usr/bin/env python3
"""repair_one.py — ONE model repair turn for a failing game, with a supplied failure text.

Same shape as repair_loop.ask_model, but the "observed failure" is the headline the
gate actually reported (e.g. ready stays false), which repair_loop's own probe cannot
see. Keeps the reply in a numbered folder so the attempt count stays honest.

usage: repair_one.py <game_dir> <base_url> <slug> "<failure text>"
"""
import json, os, re, sys, time, urllib.request

d, base, slug, why = sys.argv[1], sys.argv[2].rstrip("/"), sys.argv[3], sys.argv[4]
html_path = os.path.join(d, "index.html")
code = open(html_path, encoding="utf-8", errors="replace").read()
work = os.path.join(d, "repair")
os.makedirs(work, exist_ok=True)
n = 1 + max([int(x.split("-")[1]) for x in os.listdir(work)
             if x.startswith("turn-") and x.split("-")[1].isdigit()] or [0])
ad = os.path.join(work, f"turn-{n}")
os.makedirs(ad, exist_ok=True)

prompt = ("You wrote this single-file three.js browser game. It FAILS an automated browser grader.\n\n"
          "Observed failure:\n" + why + "\n\n"
          "Hard requirements: one self-contained HTML file; three.js from the pinned CDN import map; "
          "everything drawn with geometry/materials/lights (no external assets, textures, audio); "
          "a canvas that fills the window; a live animation loop; keyboard (arrows/A-D/space) AND "
          "on-screen touch controls; no console errors.\n\n"
          "GRADER CONTRACT (checked every frame, must be true from the first frame, no click needed):\n"
          "window.__game = {ready:true (boolean), score:0, lives:3, over:false, "
          "player:{x:number,y:number}, enemies:[{x,y}...], bullets:[{x,y}...], "
          "reset:function} — and reset() must be a callable function that restarts the game.\n"
          "The game must be PLAYING immediately on load (ready true, ships/enemies moving, "
          "SPACE fires, arrows move the player). A start screen that waits for a click is a FAIL.\n\n"
          "Fix the actual defect and reply with the complete corrected file in one ```html block. "
          "Keep it under 350 lines and finish with </html>.\n\n"
          "Current code:\n```html\n" + code + "\n```\n")
open(os.path.join(ad, "prompt.txt"), "w").write(prompt)

mid = json.load(urllib.request.urlopen(base + "/v1/models", timeout=20))["data"][0]["id"]
body = json.dumps({"model": mid, "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.0, "max_tokens": 9000,
                   "chat_template_kwargs": {"enable_thinking": False},
                   "stream": False}).encode()
req = urllib.request.Request(base + "/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json"})
t0 = time.time()
r = json.load(urllib.request.urlopen(req, timeout=1500))
wall = time.time() - t0
content = r["choices"][0]["message"].get("content") or ""
m = re.search(r"```(?:html)?\s*\n(.*?)```", content, re.S)
html = m.group(1) if m else (re.search(r"(<!DOCTYPE html.*?</html>)", content, re.S | re.I).group(1)
                             if re.search(r"(<!DOCTYPE html.*?</html>)", content, re.S | re.I) else "")
u = r.get("usage") or {}
json.dump({"turn": n, "wall_s": round(wall, 1),
           "completion_tokens": u.get("completion_tokens"),
           "finish_reason": r["choices"][0].get("finish_reason"),
           "html_bytes": len(html.encode())},
          open(os.path.join(ad, "gen.json"), "w"), indent=1)
open(os.path.join(ad, "raw_reply.md"), "w").write(content)
if len(html) > 800:
    open(html_path, "w").write(html)
print(f"turn {n}: {len(html)} bytes, {u.get('completion_tokens')} tok, {wall:.0f}s", flush=True)
