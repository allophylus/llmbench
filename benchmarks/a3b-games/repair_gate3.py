#!/usr/bin/env python3
"""repair_gate3.py — bounded repair loop with no-progress detection.

Per turn: grade <dir>/index.html with the official gate. Accept -> done. Otherwise build
a failure text from the gate (failed checks, contract reasons, first 3 console errors with
file:line stacks). Ask the model for exactly ONE fix. Stop when:
  * the gate accepts, or
  * 10 repair turns are used, or
  * the same failure signature repeats 2 turns in a row (the model is not converging;
    burning 8 more turns changes nothing — recorded as stalled, not as a model error
    that got "fixed").

usage: repair_gate3.py <slug> <dir>
"""
import json, os, subprocess, sys

GAMES = "bench-work/games"
PY = "bench-work/venv/bin/python"
MAX_TURNS = 10
env = dict(os.environ)
env["CHROME_BIN"] = subprocess.check_output(
    "ls -d .cache/ms-playwright/chromium-1248/chrome-linux*/chrome | head -1",
    shell=True, text=True).strip()
env["PATH"] = "bench-work/venv/bin:" + env.get("PATH", "")


def gate(d):
    d = os.path.abspath(d)
    subprocess.run([PY, os.path.join(GAMES, "webvalidate.py"), d], cwd=GAMES, env=env,
                   capture_output=True, text=True, timeout=900)
    try:
        return json.load(open(os.path.join(d, "metrics.json")))
    except Exception as e:
        return {"summary": {"accept": False, "contract_reasons": [f"gate crashed: {e}"]}, "_crash": str(e)}


def describe(m):
    s = m.get("summary") or {}
    bad = [k for k in ("http_load_ok", "file_load_ok", "canvas_ok", "webgl_ok", "uses_three",
                       "animation_ok", "input_ok", "contract_ok") if not s.get(k)]
    errs = []
    for tag in ("http", "file"):
        c = (m.get(tag) or {}).get("contract") or {}
        if c.get("present") and c.get("ready") is False:
            errs.append(f"window.__game.ready is false ({tag}): the game does not start on its own")
        for r in c.get("reasons") or []:
            if r not in errs:
                errs.append(f"contract ({tag}): {r}")
        ce = (m.get(tag) or {}).get("console_errors") or []
        for e in ce[:3]:
            if e not in errs:
                errs.append(f"console ({tag}): {e}")
    if bad:
        errs.insert(0, "failed checks: " + ", ".join(bad))
    if m.get("_crash"):
        errs.append("gate crash: " + m["_crash"])
    why = "; ".join(errs) or "gate rejected without detail"
    sig = "|".join(sorted(set([x.split(":")[0] for x in errs]))) + "::" + why[:160]
    return why[:1500], bad, sig


def main():
    slug, d = sys.argv[1], os.path.abspath(sys.argv[2])
    rep = os.path.join(d, "repair")
    os.makedirs(rep, exist_ok=True)
    log, last_sig, stall = [], None, 0
    status = "still-broken"
    for t in range(1, MAX_TURNS + 1):
        m = gate(d)
        if (m.get("summary") or {}).get("accept"):
            log.append({"turn": t, "accept": True,
                        "checks": (m.get("summary") or {})})
            status = "accepted"
            print(f"[{slug}] turn {t}: ACCEPT", flush=True)
            break
        why, bad, sig = describe(m)
        log.append({"turn": t, "accept": False, "failed": bad, "why": why})
        print(f"[{slug}] turn {t}: reject {bad} :: {why[:220]}", flush=True)
        if sig == last_sig:
            stall += 1
            if stall >= 2:
                status = "stalled-no-progress"
                print(f"[{slug}] stalled: identical failure twice, stopping at turn {t}", flush=True)
                break
        else:
            stall = 0
        last_sig = sig
        r = subprocess.run([PY, os.path.join(GAMES, "repair_one.py"), d,
                            "<gate-server>", slug, why],
                           cwd=GAMES, env=env, capture_output=True, text=True, timeout=1800)
        print((r.stdout or "")[-250:], (r.stderr or "")[-250:], flush=True)
    json.dump({"slug": slug, "status": status, "turns": log},
              open(os.path.join(rep, "log.json"), "w"), indent=1)
    return 0 if status == "accepted" else 1


if __name__ == "__main__":
    sys.exit(main())
