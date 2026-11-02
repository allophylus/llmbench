#!/usr/bin/env python3
"""gen_game.py — POST one frozen game prompt to a llama-server / OpenAI-compatible endpoint.

usage: gen_game.py <base_url> <prompt_file> <out_dir> <slug>

Writes <out_dir>/game.py  (fence stripped), <out_dir>/raw.md (verbatim reply) and
<out_dir>/gen.json (usage, wall time, decode t/s, prompt sha256).

Clone of ../tetris/gen_tetris.py with the prompt parameterised so the same generator
serves every game cell in this directory.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

base, prompt_path, outdir, slug = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
prompt_path = os.path.abspath(prompt_path)
prompt = open(prompt_path).read()
os.makedirs(outdir, exist_ok=True)

body = json.dumps({
    "model": "bench",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "max_tokens": 8192,
    "stream": False,
}).encode()
req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json"})
t0 = time.time()
resp = json.load(urllib.request.urlopen(req, timeout=3600))
wall = time.time() - t0

choice = resp["choices"][0]
content = choice["message"]["content"]
usage = resp.get("usage", {})
tim = resp.get("timings", {})
decode_tps = tim.get("predicted_per_second") or (
    usage.get("completion_tokens", 0) / (wall or 1))

m = re.search(r"```(?:python|py)?\s*\n(.*?)```", content, re.S)
code = m.group(1) if m else content
open(os.path.join(outdir, "raw.md"), "w").write(content)
open(os.path.join(outdir, "game.py"), "w").write(code)

gen = {
    "slug": slug,
    "base_url": base,
    "prompt_file": os.path.basename(prompt_path),
    "prompt_sha256": hashlib.sha256(open(prompt_path, "rb").read()).hexdigest(),
    "temperature": 0,
    "max_tokens": 8192,
    "finish_reason": choice.get("finish_reason"),
    "fenced_block_found": bool(m),
    "response_chars": len(content),
    "prompt_tokens": usage.get("prompt_tokens"),
    "completion_tokens": usage.get("completion_tokens"),
    "wall_s": round(wall, 2),
    "decode_tps": round(decode_tps, 2),
    "timings": tim,
    "server_model": resp.get("model"),
    "server_fingerprint": resp.get("system_fingerprint"),
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}
json.dump(gen, open(os.path.join(outdir, "gen.json"), "w"), indent=1)
print(json.dumps(gen, indent=1))
