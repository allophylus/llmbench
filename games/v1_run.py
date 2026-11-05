#!/usr/bin/env python3
"""v1_run.py — generate a browser game, then repair it with its own gate evidence.

The v1 cells (galaga / gta / physics) used build_run.py for generation and repair_loop.py
for repair, which wrote two incompatible build.json shapes (repair_loop dropped the
attempt/checks/token record). This driver keeps the single schema the games page reads:

  build.json = {attempts_used, accepted_attempt, status, per_attempt[{checks, tokens,
                wall_s, decode_tps, html_lines, html_bytes}], total_*,
                repair:{status, turns_used, distinct_outputs, repair_tokens,
                        repair_wall_s, turns[]}}

Every attempt is graded by webvalidate.py (headless Chrome, file:// and http://), so the
checks are measured, not inferred. Max 10 repair turns (11 attempts total), matching the
suite harness rule. A repair that re-emits byte-identical code counts as no progress; two
identical outputs in a row ends the loop early as "stalled-no-progress".

usage: v1_run.py --base http://192.168.1.148:8080 --prompt WEBGAME_GALAGA.md \
                 --slug qwen3-6-35b-a3b-ud-q4km-galaga --out games/qwen3-6-35b-a3b-ud-q4km-galaga
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def ask(base, prompt, max_tokens, timeout):
    mid = json.load(urllib.request.urlopen(base.rstrip("/") + "/v1/models", timeout=30))["data"][0]["id"]
    body = json.dumps({"model": mid, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.0, "max_tokens": max_tokens,
                       "chat_template_kwargs": {"enable_thinking": False},
                       "stream": False}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    wall = time.time() - t0
    ch = (r.get("choices") or [{}])[0]
    content = (ch.get("message") or {}).get("content") or ""
    tim = r.get("timings") or {}
    u = r.get("usage") or {}
    return content, wall, (u.get("completion_tokens") or tim.get("predicted_n") or 0), \
        (u.get("prompt_tokens") or tim.get("prompt_n") or 0), ch.get("finish_reason"), \
        tim.get("predicted_per_second")


def extract_html(content):
    m = re.search(r"```(?:html|HTML)?\s*\n(.*?)```", content, re.S)
    if m and "<" in m.group(1):
        return m.group(1)
    m = (re.search(r"(<!DOCTYPE\s+html.*?</html>)", content, re.S | re.I)
         or re.search(r"(<html.*?</html>)", content, re.S | re.I))
    return m.group(1) if m else ""


def validate(d):
    subprocess.run([PY, os.path.join(HERE, "webvalidate.py"), d], capture_output=True, text=True)
    p = os.path.join(d, "metrics.json")
    if not os.path.isfile(p):
        return {"accept": False, "pass": False, "contract_reasons": ["no metrics.json"],
                "console_error_count": -1}
    m = json.load(open(p))
    s = dict(m.get("summary") or {})
    # The repair prompt must carry the ACTUAL failure text: a model told only "console
    # errors" re-emits the same crashing file ten times. These are the browser's words.
    errs = ((m.get("http") or {}).get("console_errors") or [])[:4]
    s["console_errors"] = [str(e)[:220] for e in errs]
    return s


def checks_of(s):
    return {"http_load_ok": s.get("http_load_ok"), "file_load_ok": s.get("file_load_ok"),
            "canvas_ok": s.get("canvas_ok"), "webgl_ok": s.get("webgl_ok"),
            "uses_three": s.get("uses_three"), "animation_ok": s.get("animation_ok"),
            "input_ok": s.get("input_ok"), "contract_ok": s.get("contract_ok"),
            "console_error_count": s.get("console_error_count")}


def failed_of(s):
    c = checks_of(s)
    out = [k for k in ("http_load_ok", "file_load_ok", "canvas_ok", "webgl_ok", "uses_three",
                       "animation_ok", "input_ok", "contract_ok") if not c.get(k)]
    if c.get("console_error_count"):
        out.append("console_error_count=%s" % c["console_error_count"])
    out += [str(x) for x in (s.get("console_errors") or [])]
    out += [str(x) for x in (s.get("contract_reasons") or [])[:4]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=9000)
    ap.add_argument("--timeout", type=int, default=1200)
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    prompt_bytes = open(a.prompt, "rb").read()
    prompt_text = prompt_bytes.decode()
    att = os.path.join(out, "attempts")
    os.makedirs(att, exist_ok=True)

    per_attempt, repair_turns, hashes = [], [], []
    tot_pt = tot_ct = 0
    gen_wall = rep_wall = 0.0
    accepted = None
    t_all = time.time()

    def one_attempt(n, prompt):
        d = os.path.join(att, "attempt-%d" % n)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "prompt.txt"), "w").write(prompt)
        content, wall, ct, pt, fin, tps = ask(a.base, prompt, a.max_tokens, a.timeout)
        html = extract_html(content)
        open(os.path.join(d, "raw_reply.md"), "w").write(content)
        open(os.path.join(d, "index.html"), "w").write(html)
        hashes.append(hashlib.sha256(html.encode()).hexdigest())
        s = validate(d) if len(html) >= 500 else {"accept": False, "pass": False,
                                                  "contract_reasons": ["no usable html"]}
        rec = {"attempt": n, "completion_tokens": ct, "prompt_tokens": pt,
               "wall_s": round(wall, 1), "decode_tps": round(tps or 0, 2),
               "html_lines": html.count("\n") + 1, "html_bytes": len(html.encode()),
               "finish_reason": fin, "ok": bool(s.get("accept")),
               "checks": checks_of(s), "failed": failed_of(s)}
        json.dump({"attempt": n, "prompt_tokens": pt, "completion_tokens": ct,
                   "wall_s": round(wall, 1), "finish_reason": fin,
                   "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
                  open(os.path.join(d, "gen.json"), "w"), indent=1)
        print("[%s] attempt %d: %s %s" % (a.slug, n, "PASS" if s.get("accept") else "FAIL",
                                          "" if s.get("accept") else ",".join(failed_of(s)[:4])),
              flush=True)
        return rec, s, html, ct, pt, wall

    rec, st, html, ct, pt, wall = one_attempt(1, prompt_text)
    per_attempt.append(rec)
    tot_ct += ct
    tot_pt += pt
    gen_wall += wall
    if st.get("accept"):
        accepted = 1
    else:
        cur_html = html
        for turn in range(1, a.turns + 1):
            if accepted:
                break
            errs = "\n".join(failed_of(st)[:10]) or "the page does not run"
            hint = ""
            if not st.get("animation_ok") or not st.get("input_ok"):
                hint = ("\nThe grader loads the page and presses ArrowRight and ArrowLeft. It never "
                        "clicks a button: the game must be running and responding to the arrow keys "
                        "immediately after load, with something visibly moving on screen. "
                        "Do not put the game behind a start screen.\n")
            code = open(os.path.join(att, "attempt-%d" % (rec["attempt"]), "index.html"),
                        encoding="utf-8", errors="replace").read()
            prompt = (
                "You wrote this single-file three.js browser game. It FAILS an automated browser grader.\n\n"
                "Failed checks:\n" + errs + "\n" + hint + "\n"
                "Requirements: one self-contained HTML file; three.js from the pinned CDN import map; "
                "everything drawn with geometry (no external images/textures/models/audio); a live "
                "`window.__game` object updated every frame with the keys the prompt asks for, plus "
                "`window.__game.reset()`; keyboard AND touch controls; no console errors; under ~350 lines.\n\n"
                "Fix the actual defect and reply with the complete corrected file in one ```html block.\n\n"
                "Current code:\n```html\n" + code + "\n```\n")
            prev_hash = hashes[-1]
            r, st, html, ct, pt, wall = one_attempt(rec["attempt"] + 1, prompt)
            rec = r
            per_attempt.append(r)
            tot_ct += ct
            tot_pt += pt
            rep_wall += wall
            distinct = hashes[-1] != prev_hash          # did it change the file it was given?
            repair_turns.append({"turn": turn, "accept": bool(st.get("accept")),
                                 "failed": None if st.get("accept") else failed_of(st)[:6],
                                 "completion_tokens": ct, "wall_s": rec["wall_s"],
                                 "html_bytes": rec["html_bytes"],
                                 "distinct": distinct})
            cur_html = html
            if st.get("accept"):
                accepted = rec["attempt"]
                break
            if not repair_turns[-1]["distinct"]:
                print("[%s] turn %d: identical output - stalled" % (a.slug, turn), flush=True)
                break

    status = "accepted" if accepted else "failed_all_attempts"
    # Publish the accepted file, or (when nothing passed) the last attempt, so a visitor
    # sees what the model actually produced instead of an empty "not run" cell. The
    # status field still reports fail — the file is evidence, not a pass.
    src = os.path.join(att, "attempt-%d" % (accepted or per_attempt[-1]["attempt"]))
    if os.path.exists(os.path.join(src, "index.html")):
        shutil.copyfile(os.path.join(src, "index.html"), os.path.join(out, "index.html"))
    if os.path.exists(os.path.join(src, "shot.png")):
        shutil.copyfile(os.path.join(src, "shot.png"), os.path.join(out, "shot.png"))
    rep_status = ("accepted" if accepted else
                  ("stalled-no-progress" if repair_turns and not repair_turns[-1]["distinct"]
                   else "still-broken")) if repair_turns else "not-needed"
    build = {
        "slug": a.slug,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "prompt_file": os.path.basename(a.prompt),
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "max_attempts": 1 + a.turns,
        "attempts_used": len(per_attempt),
        "accepted_attempt": accepted,
        "status": status,
        "per_attempt": per_attempt,
        "total_wall_s": round(gen_wall + rep_wall, 1),
        "total_completion_tokens": tot_ct,
        "total_prompt_tokens": tot_pt,
        "generation_wall_s": round(gen_wall, 1),
        "generation_tokens": per_attempt[0]["completion_tokens"],
        "repair": {"status": rep_status, "turns_used": len(repair_turns),
                   "distinct_outputs": len(set(hashes)),
                   "repair_tokens": sum(t["completion_tokens"] for t in repair_turns),
                   "repair_wall_s": round(rep_wall, 1), "turns": repair_turns},
    }
    json.dump(build, open(os.path.join(out, "build.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in build.items() if k != "per_attempt"}, indent=1))
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
