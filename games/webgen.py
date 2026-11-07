#!/usr/bin/env python3
"""webgen.py — generate a single-file three.js game with a recorded attempts loop.

usage: webgen.py <base_url> <prompt_file> <out_dir> <slug>
                 [--max-attempts 3] [--max-tokens N] [--temperature T]
                 [--timeout S] [--record-webm]

For each attempt n (1..max-attempts) it writes
  <out_dir>/attempts/attempt-<n>/
      prompt.txt          the exact prompt sent
      raw_reply.md        the verbatim model reply
      index.html          the extracted HTML
      gen.json            usage, wall time, decode t/s, prompt sha256, model id
      validation.json     webvalidate result for this attempt
      build.webm          screen recording of the validation browser session
  <out_dir>/attempts/attempt-<n>.json  same as gen.json + validation summary (convenience)

An attempt is ACCEPTED only if webvalidate's full gate passes: loads over http and
file://, 0 console errors (favicon excluded), canvas + WebGL, three.js actually
present, animation advances, key input changes pixels, and window.__game contract ok.
The first accepted attempt becomes <out_dir>/index.html. If none passes, the best
attempt is copied to index.html but build.json records accepted_attempt: null and the
page is marked as not accepted — a failed attempt is never silently published as good.

  <out_dir>/build.json  {slug, model_requested, server_fingerprint, prompt_sha256,
                         attempts, accepted_attempt, per_attempt[], totals...}

No token or credential is read or written.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("base")
ap.add_argument("prompt_file")
ap.add_argument("out_dir")
ap.add_argument("slug")
ap.add_argument("--max-attempts", type=int, default=3)
ap.add_argument("--max-tokens", type=int, default=8000)
ap.add_argument("--temperature", type=float, default=0.0)
ap.add_argument("--timeout", type=int, default=600)
ap.add_argument("--record-webm", action="store_true", default=True)
ap.add_argument("--no-record-webm", dest="record_webm", action="store_false")
a = ap.parse_args()

outdir = os.path.abspath(a.out_dir)
os.makedirs(outdir, exist_ok=True)
attempts_root = os.path.join(outdir, "attempts")
os.makedirs(attempts_root, exist_ok=True)

base = a.base.rstrip("/")
if not base.endswith("/v1"):
    base += "/v1"

prompt_bytes = open(a.prompt_file, "rb").read()
prompt = prompt_bytes.decode()
prompt_sha = hashlib.sha256(prompt_bytes).hexdigest()

# Resolve the served model id (GET only; the benchmark box is read-only to us).
models = json.load(urllib.request.urlopen(base + "/models", timeout=30))
legacy = models.get("models") or []
model_id = (legacy[0]["model"] if legacy else models["data"][0]["id"])


def extract_html(content):
    import re
    fence = re.search(r"```(?:html|HTML)?\s*\n(.*?)```", content, re.S)
    if fence:
        return fence.group(1), "```fence```"
    m = (re.search(r"(<!DOCTYPE\s+html.*?</html>)", content, re.S | re.I)
         or re.search(r"(<html.*?</html>)", content, re.S | re.I))
    if m:
        return m.group(1), "raw <html>…</html>"
    return content, "raw reply (no html found)"


def validate(ad, record):
    """Run webvalidate.run() on an attempt dir, optionally recording the session."""
    sys.path.insert(0, HERE)
    import webvalidate
    if record:
        webvalidate.RECORD_DIR = ad
    else:
        webvalidate.RECORD_DIR = None
    webvalidate.run(ad)
    return json.load(open(os.path.join(ad, "metrics.json")))


build = {"slug": a.slug, "model_requested": model_id, "base_url": base,
         "prompt_file": os.path.basename(a.prompt_file), "prompt_sha256": prompt_sha,
         "max_attempts": a.max_attempts, "temperature": a.temperature,
         "max_tokens": a.max_tokens, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
         "per_attempt": [], "server_fingerprint": None}
t_all = time.time()
accepted = None
best = None

for n in range(1, a.max_attempts + 1):
    ad = os.path.join(attempts_root, f"attempt-{n}")
    os.makedirs(ad, exist_ok=True)
    open(os.path.join(ad, "prompt.txt"), "w").write(prompt)

    body = json.dumps({"model": model_id,
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": a.temperature, "max_tokens": a.max_tokens,
                       # suite rule (docs/BENCHMARK.md §1): thinking off for every cell,
                       # otherwise a 8000-token cap is spent inside reasoning_content
                       "chat_template_kwargs": {"enable_thinking": False},
                       "stream": False}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    rec = {"n": n}
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=a.timeout))
    except Exception as e:
        wall = time.time() - t0
        rec.update({"outcome": "request-failed", "reasons": [f"{type(e).__name__}: {e}"],
                    "wall_s": round(wall, 2)})
        json.dump({"slug": a.slug, "error": str(e), "wall_s": round(wall, 2)},
                  open(os.path.join(ad, "gen.json"), "w"), indent=1)
        build["per_attempt"].append(rec)
        continue
    wall = time.time() - t0

    choice = resp["choices"][0]
    content = choice["message"].get("content") or ""
    usage = resp.get("usage", {})
    tim = resp.get("timings", {})
    ctok = usage.get("completion_tokens") or tim.get("predicted_n") or 0
    dtps = tim.get("predicted_per_second") or (ctok / (wall or 1))
    code, how = extract_html(content)
    open(os.path.join(ad, "raw_reply.md"), "w").write(content)
    open(os.path.join(ad, "index.html"), "w").write(code)

    gen = {"slug": a.slug, "attempt": n, "base_url": base,
           "model_requested": model_id, "server_model": resp.get("model"),
           "server_fingerprint": resp.get("system_fingerprint"),
           "prompt_file": os.path.basename(a.prompt_file), "prompt_sha256": prompt_sha,
           "temperature": a.temperature, "max_tokens": a.max_tokens,
           "finish_reason": choice.get("finish_reason"), "extraction": how,
           "response_chars": len(content), "html_bytes": len(code.encode()),
           "html_lines": code.count("\n") + 1, "prompt_tokens": usage.get("prompt_tokens"),
           "completion_tokens": ctok, "total_tokens": usage.get("total_tokens"),
           "wall_s": round(wall, 2), "decode_tps": round(dtps, 2), "timings": tim,
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    json.dump(gen, open(os.path.join(ad, "gen.json"), "w"), indent=1)
    build["server_fingerprint"] = gen["server_fingerprint"]

    try:
        m = validate(ad, a.record_webm)
        s = m["summary"]
        json.dump(m, open(os.path.join(ad, "validation.json"), "w"), indent=1)
    except Exception as e:
        m, s = {}, {"accept": False, "contract_reasons": [f"validation crashed: {e}"]}

    reasons = []
    if not s.get("accept"):
        for k in ("http_load_ok", "file_load_ok", "canvas_ok", "webgl_ok", "uses_three",
                  "animation_ok", "input_ok", "contract_ok"):
            if not s.get(k):
                reasons.append(f"{k} failed")
        if s.get("console_error_count"):
            reasons.append(f"{s['console_error_count']} console error(s)")
        reasons += [r for r in (s.get("contract_reasons") or []) if r]
        if not reasons:
            reasons.append("validation did not return accept")

    rec.update({"outcome": "accepted" if s.get("accept") else "rejected",
                "reasons": reasons, "wall_s": round(wall, 2),
                "prompt_tokens": gen["prompt_tokens"], "completion_tokens": ctok,
                "decode_tps": gen["decode_tps"], "html_lines": gen["html_lines"],
                "validation_summary": s})
    build["per_attempt"].append(rec)
    json.dump({"gen": gen, "validation_summary": s, "reasons": reasons},
              open(os.path.join(attempts_root, f"attempt-{n}.json"), "w"), indent=1)

    if best is None:
        best = ad
    if s.get("accept"):
        accepted = ad
        break

build["attempts"] = len(build["per_attempt"])
build["accepted_attempt"] = int(accepted.rsplit("attempt-", 1)[1]) if accepted else None
build["accepted_source"] = os.path.relpath(accepted, outdir) if accepted else None
build["total_wall_s"] = round(time.time() - t_all, 2)
build["total_prompt_tokens"] = sum(r.get("prompt_tokens") or 0 for r in build["per_attempt"])
build["total_completion_tokens"] = sum(r.get("completion_tokens") or 0
                                       for r in build["per_attempt"])
build["total_decode_tps_avg"] = round(
    (build["total_completion_tokens"] /
     max(1e-6, sum((r.get("completion_tokens") or 0) / (r.get("decode_tps") or 1)
                   for r in build["per_attempt"]))), 2)
build["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

src = accepted or best
if src:
    shutil.copyfile(os.path.join(src, "index.html"), os.path.join(outdir, "index.html"))
    build["published_from"] = os.path.relpath(src, outdir)
    if accepted:
        shutil.copyfile(os.path.join(src, "gen.json"), os.path.join(outdir, "gen.json"))
        shutil.copyfile(os.path.join(src, "raw_reply.md"), os.path.join(outdir, "raw.md"))

    # every published game gets the harness touch layer: humans test these on phones
    _hp = os.path.join(outdir, "index.html")
    _html = open(_hp).read()
    if "touch.js" not in _html:
        # path relative to this page, so copies nested deeper (attempt pages) still resolve
        _rel = os.path.relpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "touch.js"),
                               os.path.abspath(outdir))
        _tag = '<script src="%s"></script>' % _rel
        _html = (_html.replace("</body>", _tag + "\n</body>", 1)
                 if "</body>" in _html else _html + _tag)
        open(_hp, "w").write(_html)
json.dump(build, open(os.path.join(outdir, "build.json"), "w"), indent=1)

if not accepted:
    print(f"FAILED: no attempt accepted in {build['attempts']} attempt(s); "
          f"index.html holds the best attempt and build.json marks it rejected",
          file=sys.stderr)
print(json.dumps({k: build[k] for k in ("slug", "attempts", "accepted_attempt",
                                        "total_wall_s", "total_completion_tokens")}))
sys.exit(0 if accepted else 2)
