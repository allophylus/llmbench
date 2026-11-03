#!/usr/bin/env python3
"""suite_run.py — run one (model, spec) cell of the 4-game suite, or the whole matrix.

One cell = generate a single-file three.js game from a frozen spec prompt, gate it
(run/load/canvas/three/contract), execute that spec's behavioural assertions, and score
SPEC COMPLIANCE. On a failed gate or failed assertions the model gets its OWN code plus
the exact failing evidence back — max 10 repair turns. Every turn is recorded.

usage:
  suite_run.py --base http://127.0.0.1:8080 --model-slug qwen3-8-27b-q4km \
               --spec ball-drop-sandbox --out games/suite/out [--attempts 11]
  suite_run.py ... --spec all            # every spec in SPEC_ORDER
  suite_run.py --matrix-missing          # list (slug, spec) cells with no result yet (json)

Output layout (per cell):
  games/suite/out/<slug>/<spec>/attempt-<n>/{prompt.txt,raw_reply.md,index.html,
                                             gen.json,probe.json,shot.png}
  games/suite/out/<slug>/<spec>/build.json   summary: accepted attempt, per-attempt
                                             {tokens, wall_s, gate, passed/total,
                                              compliance, screenshot}
  games/suite/out/<slug>/index.html          the accepted (or best) game, for the site
  games/suite/out/<slug>/shot-<spec>.png     the screenshot shown in the side-by-side page

Rules that are deliberate and must not be relaxed:
  * max 10 repair turns (11 attempts total: 1 initial + 10 repairs);
  * assertion failures do NOT block acceptance by themselves — the run gate decides
    acceptance; assertions and compliance are recorded per attempt (the benchmark is
    "what did it produce", not "did it eventually pass everything");
  * a repair turn is triggered by a failed gate OR a failed assertion, and the model is
    told exactly which assertion failed and what the grader observed.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import playprobe  # noqa: E402

SPEC_ORDER = ["ball-drop-sandbox", "tower-stacker", "tower-defence", "match3-cascades"]
MAX_REPAIRS = 10
PY = sys.executable


def spec_path(spec):
    return os.path.join(HERE, "specs", "GAME_SPEC_%s.md" % spec)


def extract_html(content):
    m = re.search(r"```(?:html|HTML)?\s*\n(.*?)```", content, re.S)
    if m and "<" in m.group(1):
        return m.group(1)
    m = (re.search(r"(<!DOCTYPE\s+html.*?</html>)", content, re.S | re.I)
         or re.search(r"(<html.*?</html>)", content, re.S | re.I))
    return m.group(1) if m else ""


def model_id(base):
    d = json.load(urllib.request.urlopen(base.rstrip("/") + "/v1/models", timeout=30))
    return (d.get("models") or [{}])[0].get("model") or d["data"][0]["id"]


def ask(base, prompt, mid, max_tokens=9000, timeout=1500):
    body = json.dumps({"model": mid, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.0, "max_tokens": max_tokens,
                       "chat_template_kwargs": {"enable_thinking": False},
                       "stream": False}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    wall = time.time() - t0
    u = r.get("usage") or {}
    t = r.get("timings") or {}
    return {"content": r["choices"][0]["message"].get("content") or "",
            "wall_s": round(wall, 2),
            "prompt_tokens": u.get("prompt_tokens"),
            "completion_tokens": u.get("completion_tokens"),
            "decode_tps": round(t["predicted_per_second"], 2) if t.get("predicted_per_second") else None}


def repair_prompt(spec, code, probe, attempt):
    lines = []
    if not probe["gate"].get("pass"):
        g = probe["gate"]
        why = []
        if not g.get("load_ok", True):
            why.append("the page did not load: " + str(g.get("load_error", ""))[:200])
        if not g.get("ready"):
            why.append("window.__game.ready never became true")
        if not g.get("canvas"):
            why.append("no sized <canvas>")
        if not g.get("three"):
            why.append("three.js not detected at runtime")
        if g.get("contract_missing"):
            why.append("window.__game contract missing/incorrect keys: " + ", ".join(g["contract_missing"]))
        lines.append("The run gate FAILED:\n- " + "\n- ".join(why))
    failed = [a for a in probe["assertions"] if not a["ok"]]
    if failed:
        lines.append("These behavioural assertions FAILED (the grader calls step(1/60) / swap() "
                     "through window.__game and reads the state you publish):")
        for a in failed[:6]:
            lines.append("- %s (%s): got %s, want %s" % (a["id"], a["desc"],
                        json.dumps(a["got"])[:300], json.dumps(a["want"])[:160]))
    if probe["compliance"].get("violations"):
        lines.append("SPEC VIOLATIONS (things this task did not ask for, or forbidden "
                     "implementation choices):\n- " +
                     "\n- ".join(probe["compliance"]["violations"]))
    if probe.get("console_errors"):
        lines.append("Console errors:\n" + "\n".join(probe["console_errors"][:5]))
    spec_text = open(spec_path(spec), encoding="utf-8").read()
    return ("You wrote this single-file three.js game. It is being graded against the spec below"
            " and does not pass yet (repair turn %d of up to %d).\n\n" % (attempt, MAX_REPAIRS)
            + "\n\n".join(lines)
            + "\n\nFix the actual defects. Keep everything that already works. Reply with the "
              "COMPLETE corrected file in one ```html block and nothing else.\n\n"
              "=== SPEC (unchanged) ===\n" + spec_text
            + "\n\n=== YOUR CURRENT FILE ===\n```html\n" + code + "\n```\n")


def run_cell(base, slug, spec, out_root, attempts, skip_done=False):
    cell = os.path.join(out_root, slug, spec)
    os.makedirs(cell, exist_ok=True)
    if skip_done and os.path.isfile(os.path.join(cell, "build.json")):
        try:  # resumable: a cell that already has a summary is not re-run
            return json.load(open(os.path.join(cell, "build.json")))
        except Exception:
            pass
    frozen = open(spec_path(spec), "rb").read()
    prompt = frozen.decode()
    mid = model_id(base)
    per, accepted, best = [], None, (-1, None)
    t_all = time.time()
    cur_prompt = prompt
    for n in range(1, attempts + 1):
        ad = os.path.join(cell, "attempt-%d" % n)
        os.makedirs(ad, exist_ok=True)
        open(os.path.join(ad, "prompt.txt"), "w").write(cur_prompt)
        print("[%s/%s] attempt %d: generating ..." % (slug, spec, n), flush=True)
        try:
            r = ask(base, cur_prompt, mid)
        except Exception as e:
            per.append({"attempt": n, "error": "model request failed: %s" % str(e)[:200]})
            print("[%s/%s] attempt %d: model error %s" % (slug, spec, n, str(e)[:120]), flush=True)
            break
        open(os.path.join(ad, "raw_reply.md"), "w").write(r["content"])
        html = extract_html(r["content"])
        rec = {"attempt": n, "wall_s": r["wall_s"], "prompt_tokens": r["prompt_tokens"],
               "completion_tokens": r["completion_tokens"], "decode_tps": r["decode_tps"],
               "html_bytes": len(html)}
        if len(html) < 800:
            rec.update({"gate_pass": False, "passed": 0, "total": len(playprobe.A[spec]),
                        "compliance": 0, "note": "reply contained no usable HTML"})
            json.dump(rec, open(os.path.join(ad, "gen.json"), "w"), indent=1)
            per.append(rec)
            print("[%s/%s] attempt %d: no usable html" % (slug, spec, n), flush=True)
            cur_prompt = ("Your reply did not contain a complete HTML file in one ```html block. "
                          "Reply with the full document only.\n\n=== SPEC ===\n" + prompt)
            continue
        open(os.path.join(ad, "index.html"), "w").write(html)
        json.dump(rec, open(os.path.join(ad, "gen.json"), "w"), indent=1)
        pr = playprobe.run(spec, ad, os.path.join(ad, "shot.png"), os.path.join(ad, "probe.json"))
        rec.update({"gate_pass": bool(pr["gate"].get("pass")), "passed": pr["passed"],
                    "total": pr["total"],
                    "compliance": pr["compliance"]["score"],
                    "violations": pr["compliance"].get("violations", []),
                    "assertions": pr["assertions"]})
        per.append(rec)
        score = pr["passed"] * 10 + pr["compliance"]["score"] + (100 if pr["gate"].get("pass") else 0)
        if score > best[0]:
            best = (score, n)
        print("[%s/%s] attempt %d: gate=%s assertions=%d/%d compliance=%s (%ss, %s tok)"
              % (slug, spec, n, "PASS" if rec["gate_pass"] else "FAIL", pr["passed"], pr["total"],
                 rec["compliance"], r["wall_s"], r["completion_tokens"]), flush=True)
        if rec["gate_pass"] and pr["passed"] == pr["total"]:
            accepted = n
            break
        cur_prompt = repair_prompt(spec, html, pr, n)
    build = {"slug": slug, "spec": spec, "model_id": mid, "base_url": base,
             "prompt_file": os.path.basename(spec_path(spec)),
             "prompt_sha256": __import__("hashlib").sha256(frozen).hexdigest(),
             "max_repairs": MAX_REPAIRS, "turns_allowed": attempts,
             "turns_used": len(per), "accepted_attempt": accepted,
             "best_attempt": best[1],
             "status": "all-accepted" if accepted else ("plays-with-failures" if any(
                 p.get("gate_pass") for p in per) else "never-ran"),
             "per_attempt": per,
             "total_wall_s": round(time.time() - t_all, 1),
             "total_prompt_tokens": sum(p.get("prompt_tokens") or 0 for p in per),
             "total_completion_tokens": sum(p.get("completion_tokens") or 0 for p in per),
             "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    json.dump(build, open(os.path.join(cell, "build.json"), "w"), indent=1)
    pick = accepted or best[1]
    if pick:
        src = os.path.join(cell, "attempt-%d" % pick)
        mdir = os.path.join(out_root, slug)
        os.makedirs(mdir, exist_ok=True)
        if os.path.exists(os.path.join(src, "index.html")):
            shutil.copyfile(os.path.join(src, "index.html"), os.path.join(mdir, "index.html"))
        if os.path.exists(os.path.join(src, "shot.png")):
            shutil.copyfile(os.path.join(src, "shot.png"),
                            os.path.join(mdir, "shot-%s.png" % spec))
    return build


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--model-slug", required=True)
    ap.add_argument("--spec", required=True, help="spec name or 'all'")
    ap.add_argument("--out", default=os.path.join(HERE, "suite", "out"))
    ap.add_argument("--attempts", type=int, default=MAX_REPAIRS + 1)
    ap.add_argument("--skip-done", action="store_true")
    a = ap.parse_args()
    specs = SPEC_ORDER if a.spec == "all" else [a.spec]
    assert a.attempts <= MAX_REPAIRS + 1, "the suite caps repair turns at 10"
    for s in specs:
        os.makedirs(os.path.join(a.out, a.model_slug), exist_ok=True)
        run_cell(a.base, a.model_slug, s, a.out, a.attempts, a.skip_done)


if __name__ == "__main__":
    main()
