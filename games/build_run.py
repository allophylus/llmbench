#!/usr/bin/env python3
"""build_run.py — generate a web game with a VALIDATION GATE and record every attempt.

Why: a single generation is not a benchmark. We need to know how many tries a model
needed, what each attempt produced, and why an attempt was rejected.

usage:
  build_run.py --base http://192.168.1.148:8080 --prompt WEBGAME_PROMPT.md \
               --slug my-model --out games/my-model --attempts 3

Per attempt n:
  <out>/attempts/attempt-<n>/prompt.txt     frozen prompt used
  <out>/attempts/attempt-<n>/raw_reply.md   verbatim model reply
  <out>/attempts/attempt-<n>/index.html     extracted HTML (candidate game)
  <out>/attempts/attempt-<n>/gen.json       usage / wall / decode t/s / hashes
  <out>/attempts/attempt-<n>/validation.json  gate result + reasons
  <out>/attempts/attempt-<n>/shot.png       rendered frame

Accepted attempt is copied to <out>/index.html. <out>/build.json summarises:
attempts used, which attempt was accepted, per-attempt outcome, totals.

The gate = webvalidate.py (load, console errors, canvas+WebGL, three.js present,
animation advancing, input changes pixels, window.__game contract).
"""
import argparse, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--prompt", required=True)
ap.add_argument("--slug", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--attempts", type=int, default=3)
ap.add_argument("--max-tokens", type=int, default=8000)
ap.add_argument("--timeout", type=int, default=600)
a = ap.parse_args()

out = os.path.abspath(a.out)
att_root = os.path.join(out, "attempts")
os.makedirs(att_root, exist_ok=True)
prompt_bytes = open(a.prompt, "rb").read()

per_attempt, accepted = [], None
t0 = time.time()
tot_pt = tot_ct = 0

for n in range(1, a.attempts + 1):
    d = os.path.join(att_root, f"attempt-{n}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "prompt.txt"), "wb").write(prompt_bytes)
    print(f"[attempt {n}] generating ...", flush=True)

    # webgen (this build) insists on its internal 3-attempt loop and rejects --max-attempts 1;
    # it stops at its first accepted attempt, so try 1 normally == one generation. Then
    # we grade webgen's published attempt ourselves and keep every reply for repair_loop.
    gen_rc = subprocess.call([PY, os.path.join(HERE, "webgen.py"), a.base, a.prompt, d,
                              a.slug, "--max-attempts", "3",
                              "--max-tokens", str(a.max_tokens),
                              "--timeout", str(a.timeout)])
    reasons, ok = [], False
    # webgen's exit code is not the contract (it returns 0 or 2 depending on phase when
    # the gate rejects). The contract is: gen.json written => a full reply was produced
    # and validated here below; webgen FAILED with no gen.json => no usable file.
    if not os.path.exists(os.path.join(d, "gen.json")) and gen_rc != 0:
        reasons.append(f"generator exit {gen_rc}")
    else:
        try:
            # webgen stores its per-attempt record at <d>/gen.json, but on some paths the
            # file lands as <d>/attempts/attempt-1/gen.json (phase dependent). Accept both.
            gp = os.path.join(d, "gen.json")
            if not os.path.exists(gp):
                gp = os.path.join(d, "attempts", "attempt-1", "gen.json")
            g = json.load(open(gp))
            tot_pt += g.get("prompt_tokens") or 0
            tot_ct += g.get("completion_tokens") or 0
            if g.get("html_bytes", 0) < 500:
                reasons.append("html too small / not extracted")
        except Exception as e:
            reasons.append(f"gen.json unreadable: {e}")

        if not reasons:
            # validation gate (writes metrics.json + shot.png into the attempt dir)
            vrc = subprocess.call([PY, os.path.join(HERE, "webvalidate.py"), d])
            m = {}
            for cand in ("metrics.json",):
                p = os.path.join(d, cand)
                if os.path.exists(p):
                    m = json.load(open(p))
            http = (m.get("http") or {})
            checks = {
                "load_ok": http.get("load_ok"),
                "canvas": http.get("canvas_present"),
                "webgl": http.get("webgl_ok"),
                "three_js": http.get("mentions_three") or http.get("uses_three_global"),
                "animation": http.get("animation_advancing"),
                "input": http.get("input_ok") or http.get("input_changes_pixels"),
                "contract": (m.get("contract") or {}).get("ok", http.get("contract_ok")),
            }
            ok = vrc == 0 and all(bool(v) for v in checks.values())
            reasons = [k for k, v in checks.items() if not v] or ([] if ok else [f"validator exit {vrc}"])
            json.dump({"ok": ok, "checks": checks, "reasons": reasons,
                       "validator_exit": vrc, "metrics": m},
                      open(os.path.join(d, "validation.json"), "w"), indent=1)
    per_attempt.append({"attempt": n, "ok": ok, "reasons": reasons})
    print(f"[attempt {n}] {'PASS' if ok else 'FAIL ' + ','.join(reasons)}", flush=True)
    if ok:
        accepted = n
        shutil.copyfile(os.path.join(d, "index.html"), os.path.join(out, "index.html"))
        if os.path.exists(os.path.join(d, "shot.png")):
            shutil.copyfile(os.path.join(d, "shot.png"), os.path.join(out, "shot.png"))
        break

build = {
    "slug": a.slug,
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "prompt_file": os.path.basename(a.prompt),
    "max_attempts": a.attempts,
    "attempts_used": len(per_attempt),
    "retries": max(0, len(per_attempt) - 1),
    "accepted_attempt": accepted,
    "status": "accepted" if accepted else "failed_all_attempts",
    "per_attempt": per_attempt,
    "total_wall_s": round(time.time() - t0, 1),
    "total_prompt_tokens": tot_pt,
    "total_completion_tokens": tot_ct,
}
json.dump(build, open(os.path.join(out, "build.json"), "w"), indent=1)
print(json.dumps(build, indent=1))
sys.exit(0 if accepted else 1)
