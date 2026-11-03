#!/usr/bin/env python3
"""build_run2.py — one webgen attempt per outer attempt, with an explicit gate, kept simple.

Why a second driver: the repo's build_run.py calls webgen with a different output shape
than this webgen.py writes (<d>/attempts/attempt-1/...), and webgen's exit code is not
stable (0 or 2 on the same rejection). This driver calls webgen with --max-attempts 1,
waits for the request to finish, then grades the produced file with the official
webvalidate gate and records everything in the same build.json shape.

usage: build_run2.py --base URL --prompt P.md --slug S --out DIR --attempts N
"""
import argparse, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ENV = dict(os.environ)
ENV.setdefault("CHROME_BIN", subprocess.check_output(
    "ls -d .cache/ms-playwright/chromium-1248/chrome-linux*/chrome | head -1",
    shell=True, text=True).strip())

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--prompt", required=True)
ap.add_argument("--slug", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--attempts", type=int, default=3)
ap.add_argument("--max-tokens", type=int, default=8000)
ap.add_argument("--timeout", type=int, default=1800)
a = ap.parse_args()

out = os.path.abspath(a.out)
os.makedirs(os.path.join(out, "attempts"), exist_ok=True)
per, accepted = [], None
t0 = time.time()


def find_gen(d):
    for p in (os.path.join(d, "gen.json"),
              os.path.join(d, "attempts", "attempt-1", "gen.json"),):
        if os.path.exists(p):
            return p
    return None


def find_html(d):
    for p in (os.path.join(d, "attempts", "attempt-1", "index.html"),
              os.path.join(d, "index.html")):
        if os.path.exists(p):
            return p
    return None


for n in range(1, a.attempts + 1):
    d = os.path.join(out, "attempts", f"attempt-{n}")
    os.makedirs(d, exist_ok=True)
    print(f"[attempt {n}] generating ...", flush=True)
    rc = subprocess.call([PY, os.path.join(HERE, "webgen.py"), a.base, a.prompt, d,
                          a.slug, "--max-attempts", "1",
                          "--max-tokens", str(a.max_tokens),
                          "--timeout", str(a.timeout)],
                         env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    gp, hp = find_gen(d), find_html(d)
    rec = {"attempt": n, "webgen_rc": rc}
    if not gp or not hp:
        rec.update({"outcome": "no-output", "reasons": [f"webgen rc={rc}, no gen.json/html"],
                    "ok": False})
        per.append(rec)
        print(f"[attempt {n}] FAIL no output (rc={rc})", flush=True)
        continue
    g = json.load(open(gp))
    rec.update({k: g.get(k) for k in ("completion_tokens", "prompt_tokens", "wall_s",
                                      "decode_tps", "html_lines", "html_bytes",
                                      "finish_reason", "extraction")})
    # grade the produced file with the official gate
    gdir = os.path.join(d, "_gate")
    os.makedirs(gdir, exist_ok=True)
    shutil.copyfile(hp, os.path.join(gdir, "index.html"))
    grc = subprocess.call([PY, os.path.join(HERE, "webvalidate.py"), gdir],
                          env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        m = json.load(open(os.path.join(gdir, "metrics.json")))
        s = m.get("summary") or {}
    except Exception as e:
        m, s = {}, {"accept": False, "contract_reasons": [f"gate crashed: {e}"]}
    shutil.copyfile(os.path.join(gdir, "metrics.json"), os.path.join(d, "metrics.json")) \
        if os.path.exists(os.path.join(gdir, "metrics.json")) else None
    for f in ("shot.png", "build.webm"):
        if os.path.exists(os.path.join(gdir, f)):
            shutil.copyfile(os.path.join(gdir, f), os.path.join(d, f))
    rec.update({"ok": bool(s.get("accept")), "gate_rc": grc,
                "checks": {k: s.get(k) for k in ("http_load_ok", "file_load_ok", "canvas_ok",
                                                 "webgl_ok", "uses_three", "animation_ok",
                                                 "input_ok", "contract_ok",
                                                 "console_error_count")},
                "contract_reasons": s.get("contract_reasons")})
    rec["reasons"] = [] if rec["ok"] else [k for k, v in rec["checks"].items() if not v]
    per.append(rec)
    print(f"[attempt {n}] {'PASS' if rec['ok'] else 'FAIL ' + ','.join(rec['reasons'])}", flush=True)
    if rec["ok"] and accepted is None:
        accepted = n
        shutil.copyfile(hp, os.path.join(out, "index.html"))
        if os.path.exists(os.path.join(d, "shot.png")):
            shutil.copyfile(os.path.join(d, "shot.png"), os.path.join(out, "shot.png"))
        json.dump(g, open(os.path.join(out, "gen.json"), "w"), indent=1)
        break

build = {"slug": a.slug, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
         "prompt_file": os.path.basename(a.prompt), "max_attempts": a.attempts,
         "attempts_used": len(per), "accepted_attempt": accepted,
         "status": "accepted" if accepted else "rejected", "per_attempt": per,
         "total_wall_s": round(time.time() - t0, 1),
         "total_completion_tokens": sum(r.get("completion_tokens") or 0 for r in per),
         "total_prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in per)}
json.dump(build, open(os.path.join(out, "build.json"), "w"), indent=1)
print(json.dumps({k: build[k] for k in ("slug", "attempts_used", "accepted_attempt",
                                        "total_wall_s", "total_completion_tokens")}))
sys.exit(0 if accepted else 1)
