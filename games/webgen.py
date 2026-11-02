#!/usr/bin/env python3
"""webgen.py — POST the frozen WEBGAME_PROMPT to an OpenAI-compatible endpoint and
save a single-file three.js game.

usage: webgen.py <base_url> <prompt_file> <out_dir> <slug> [--max-tokens N]
                 [--temperature T] [--overwrite]

<base_url> is e.g. http://192.168.1.148:8080 (no /v1 suffix) or .../v1 (either works).

Writes <out_dir>/index.html (extracted from ```html fence or raw <html>…</html>),
<out_dir>/raw.md (verbatim reply) and <out_dir>/gen.json (usage, wall time, decode
t/s, prompt sha256, model id). No token or credential is ever read or written.

Modelled on ../gen_game.py (terminal-game generator) so both cells record the same
fields where they overlap.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("base")
ap.add_argument("prompt_file")
ap.add_argument("out_dir")
ap.add_argument("slug")
ap.add_argument("--max-tokens", type=int, default=8000)
ap.add_argument("--temperature", type=float, default=0.0)
ap.add_argument("--timeout", type=int, default=600)
ap.add_argument("--overwrite", action="store_true")
a = ap.parse_args()

outdir = os.path.abspath(a.out_dir)
html_path = os.path.join(outdir, "index.html")
if os.path.exists(html_path) and not a.overwrite:
    sys.exit(f"refusing to overwrite {html_path} (pass --overwrite)")

base = a.base.rstrip("/")
if not base.endswith("/v1"):
    base += "/v1"

prompt_bytes = open(a.prompt_file, "rb").read()
prompt = prompt_bytes.decode()

# Resolve the actual served model id (prod box is read-only for us: GET only).
models = json.load(urllib.request.urlopen(base + "/models", timeout=30))
legacy = models.get("models") or []
model_id = (legacy[0]["model"] if legacy else models["data"][0]["id"])

body = json.dumps({
    "model": model_id,
    "messages": [{"role": "user", "content": prompt}],
    "temperature": a.temperature,
    "max_tokens": a.max_tokens,
    "stream": False,
}).encode()
req = urllib.request.Request(base + "/chat/completions", data=body,
                             headers={"Content-Type": "application/json"})
t0 = time.time()
try:
    resp = json.load(urllib.request.urlopen(req, timeout=a.timeout))
except Exception as e:  # keep evidence of failure, then surface it
    os.makedirs(outdir, exist_ok=True)
    json.dump({"slug": a.slug, "error": f"{type(e).__name__}: {e}",
               "wall_s": round(time.time() - t0, 2)},
              open(os.path.join(outdir, "gen.json"), "w"), indent=1)
    raise
wall = time.time() - t0

choice = resp["choices"][0]
content = choice["message"].get("content") or ""
usage = resp.get("usage", {})
tim = resp.get("timings", {})
completion_tokens = usage.get("completion_tokens") or tim.get("predicted_n") or 0
decode_tps = tim.get("predicted_per_second") or (completion_tokens / (wall or 1))

# --- extract the HTML -------------------------------------------------------
fence = re.search(r"```(?:html|HTML)?\s*\n(.*?)```", content, re.S)
if fence:
    code, how = fence.group(1), "```fence```"
else:
    m = re.search(r"(<!DOCTYPE\s+html.*?</html>)", content, re.S | re.I) or \
        re.search(r"(<html.*?</html>)", content, re.S | re.I)
    code, how = (m.group(1), "raw <html>…</html>") if m else (content, "raw reply (no html found)")

os.makedirs(outdir, exist_ok=True)
open(os.path.join(outdir, "raw.md"), "w").write(content)
open(html_path, "w").write(code)

gen = {
    "slug": a.slug,
    "base_url": base,
    "model_requested": model_id,
    "server_model": resp.get("model"),
    "server_fingerprint": resp.get("system_fingerprint"),
    "prompt_file": os.path.basename(a.prompt_file),
    "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
    "temperature": a.temperature,
    "max_tokens": a.max_tokens,
    "finish_reason": choice.get("finish_reason"),
    "extraction": how,
    "response_chars": len(content),
    "html_bytes": len(code.encode()),
    "html_lines": code.count("\n") + 1,
    "prompt_tokens": usage.get("prompt_tokens"),
    "completion_tokens": completion_tokens,
    "total_tokens": usage.get("total_tokens"),
    "wall_s": round(wall, 2),
    "decode_tps": round(decode_tps, 2),
    "timings": tim,
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}
json.dump(gen, open(os.path.join(outdir, "gen.json"), "w"), indent=1)
print(json.dumps(gen, indent=1))
