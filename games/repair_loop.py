#!/usr/bin/env python3
"""repair_loop.py — fix a generated browser game by feeding its own runtime errors back.

  python3 repair_loop.py <game_dir> <base_url> [--turns 10] [--slug NAME]

Each turn: load the game in headless Chrome, collect console/page errors and whether
`window.__game` came up. If it is broken, send the model its own code plus the exact
error and ask for a corrected full file. Repeat until it validates or the turn budget
is spent. Every attempt is kept under <game_dir>/attempts/attempt-N/ and summarised in
build.json — so "how many repeats did it need" is measured, not guessed.
"""
import argparse, json, os, re, shutil, subprocess, sys, time, urllib.request

CHROME = (os.environ.get("CHROME_BIN") or shutil.which("google-chrome")
          or shutil.which("chromium") or "/usr/bin/google-chrome")

PROBE = r"""
from playwright.sync_api import sync_playwright
import json, sys
path = sys.argv[1]
out = {"load": False, "canvas": 0, "ready": False, "errors": []}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME_PATH, headless=True, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1280, "height": 800})
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
    b.close()
print(json.dumps(out))
"""

def probe(path, workdir):
    script = os.path.join(workdir, "_probe.py")
    open(script, "w").write(PROBE.replace("CHROME_PATH", repr(CHROME)))
    r = subprocess.run([sys.executable, script, path], capture_output=True, text=True, cwd=workdir)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"load": False, "canvas": 0, "ready": False,
                "errors": ["probe failed: " + (r.stderr or "")[-200:]}]}

def ask_model(base, prompt, timeout=900):
    mid = json.load(urllib.request.urlopen(base.rstrip("/") + "/v1/models", timeout=20))["data"][0]["id"]
    body = json.dumps({"model": mid, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.0, "max_tokens": 9000,
                       "chat_template_kwargs": {"enable_thinking": False},
                       "stream": False}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    wall = time.time() - t0
    content = r["choices"][0]["message"].get("content") or ""
    m = re.search(r"```(?:html)?\s*\n(.*?)```", content, re.S)
    html = m.group(1) if m else (re.search(r"(<!DOCTYPE html.*?</html>)", content, re.S | re.I).group(1)
                                 if re.search(r"(<!DOCTYPE html.*?</html>)", content, re.S | re.I) else "")
    u = r.get("usage") or {}
    return html, wall, u.get("completion_tokens")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_dir")
    ap.add_argument("base")
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--slug", default=None)
    a = ap.parse_args()

    d = os.path.abspath(a.game_dir)
    slug = a.slug or os.path.basename(d)
    html_path = os.path.join(d, "index.html")
    work = os.path.join(d, "attempts")
    os.makedirs(work, exist_ok=True)
    per = []
    ok = False
    t_start = time.time()

    for n in range(1, a.turns + 1):
        res = probe(html_path, work)
        ok = bool(res["load"] and res["canvas"] and res["ready"] and not
                  [e for e in res["errors"] if "favicon" not in e and "404" not in e])
        per.append({"attempt": n, "ok": ok, "canvas": res["canvas"], "ready": res["ready"],
                    "errors": res["errors"][:4]})
        print("[%s] turn %d: %s %s" % (slug, n, "PASS" if ok else "FAIL",
                                       "" if ok else (res["errors"][:1] or ["no canvas/ready"])))
        if ok:
            break
        code = open(html_path, encoding="utf-8", errors="replace").read()
        errs = "\n".join(res["errors"][:5]) or "the game renders nothing (canvas 0) or never sets window.__game.ready"
        prompt = ("You wrote this single-file three.js browser game. It FAILS in a real browser.\n\n"
                  "Observed failure:\n" + errs + "\n\n"
                  "Requirements it must satisfy: one self-contained HTML file, three.js from the pinned CDN "
                  "import map, everything drawn with geometry (no external assets), a working "
                  "window.__game = {ready:true, score, lives, over, player:{x,y}, enemies:[{x,y}], bullets:[{x,y}]} "
                  "updated every frame plus window.__game.reset(), keyboard and touch controls, and it must run "
                  "without console errors. Keep it under 350 lines.\n\n"
                  "Fix the actual defect and reply with the complete corrected file in one ```html block.\n\n"
                  "Current code:\n```html\n" + code + "\n```\n")
        try:
            new_html, wall, toks = ask_model(a.base, prompt)
        except Exception as e:
            per[-1]["error"] = str(e)[:160]
            print("[%s] turn %d: model error %s" % (slug, n, str(e)[:120]))
            continue
        if len(new_html) < 800:
            per[-1]["error"] = "model returned no usable html"
            continue
        ad = os.path.join(work, "attempt-%d" % n)
        os.makedirs(ad, exist_ok=True)
        open(os.path.join(ad, "index.html"), "w").write(new_html)
        open(os.path.join(ad, "prompt.txt"), "w").write(prompt)
        json.dump({"turn": n, "wall_s": round(wall, 1), "completion_tokens": toks},
                  open(os.path.join(ad, "gen.json"), "w"), indent=1)
        open(html_path, "w").write(new_html)
        per[-1].update({"wall_s": round(wall, 1), "tokens": toks, "bytes": len(new_html)})

    build = {"slug": slug, "turns_allowed": a.turns, "turns_used": len(per),
             "status": "plays" if ok else "still-broken", "per_turn": per,
             "total_s": round(time.time() - t_start, 1)}
    json.dump(build, open(os.path.join(d, "build.json"), "w"), indent=1)
    print(json.dumps(build, indent=1))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
