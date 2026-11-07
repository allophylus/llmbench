#!/usr/bin/env python3
"""r97.py — shared runtime for the R9700 intelligence/agentic suite.

Subcommands (all print JSON on stdout unless noted):
  probe                     :8081 health, model id, ctx, vram (JSON)
  chat --prompt P ...       one /v1/chat/completions call (JSON incl. usage+timings)

Env: R97_BASE (default http://127.0.0.1:8081)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("R97_BASE", "http://127.0.0.1:8081")
VRAM = ["/sys/class/drm/card1/device/mem_info_vram_used",
        "/sys/class/drm/card0/device/mem_info_vram_used"]


def vram_gib():
    for p in VRAM:
        try:
            with open(p) as f:
                return round(int(f.read().strip()) / 2**30, 2)
        except Exception:
            continue
    return None


def post(path, payload, timeout=1800):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


def get(path, timeout=20):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def model_id():
    d = get("/v1/models")
    return (d.get("data") or [{}])[0].get("id")


def chat(prompt=None, messages=None, tools=None, temperature=0.0, max_tokens=None,
         seed=None, timeout=1800, top_p=None, stop=None, n_predict=None):
    msgs = messages or [{"role": "user", "content": prompt}]
    payload = {"messages": msgs, "temperature": temperature, "stream": False}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if seed is not None:
        payload["seed"] = seed
    if top_p is not None:
        payload["top_p"] = top_p
    if stop:
        payload["stop"] = stop
    if n_predict:
        # llama.cpp-native cap (server ignores max_tokens for some chat templates)
        payload["n_predict"] = n_predict
    body, wall = post("/v1/chat/completions", payload, timeout=timeout)
    ch = (body.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    tim = body.get("timings") or {}
    # some chat templates stream the answer into a separate reasoning channel until
    # thinking completes; if `content` is empty the reasoning IS the visible answer
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    if not content.strip():
        content = reasoning
    return {"content": content,
            "reasoning_chars": len(reasoning),
            "content_empty_used_reasoning": bool(reasoning and not (msg.get("content") or "").strip()),
            "tool_calls": msg.get("tool_calls") or [],
            "finish_reason": ch.get("finish_reason"),
            "usage": body.get("usage") or {},
            "prompt_n": tim.get("prompt_n"),
            "predicted_n": tim.get("predicted_n"),
            "prompt_ms": round(tim.get("prompt_ms") or 0, 1) or None,
            "prefill_tps": round(tim.get("prompt_per_second") or 0, 1) or None,
            "decode_tps": round(tim.get("predicted_per_second") or 0, 2) or None,
            "wall_s": round(wall, 2)}


def wait_ready(timeout_s=900):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            d = get("/health", timeout=5)
            if d.get("status") == "ok":
                return round(time.time() - t0, 1)
        except Exception:
            pass
        time.sleep(2)
    return None


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(2)
    cmd = a[0]
    if cmd == "probe":
        out = {"base": BASE}
        try:
            out["health"] = get("/health")
            out["model_id"] = model_id()
            props = get("/props")
            dgs = props.get("default_generation_settings") or {}
            out["n_ctx"] = dgs.get("n_ctx")
            out["total_slots"] = props.get("total_slots")
            out["build"] = (props.get("build_info") or "")
            out["model_path"] = props.get("model_path")
        except Exception as e:
            out["error"] = str(e)
        out["vram_used_gib"] = vram_gib()
        print(json.dumps(out))
    elif cmd == "wait":
        tmo = int(a[a.index("--timeout") + 1]) if "--timeout" in a else 900
        s = wait_ready(tmo)
        print(json.dumps({"ready_s": s, "ok": s is not None}))
        sys.exit(0 if s is not None else 1)
    elif cmd == "chat":
        args = dict(zip(a[1::2], a[2::2]))
        r = chat(prompt=args.get("--prompt", ""),
                 temperature=float(args.get("--temp", 0.0)),
                 max_tokens=int(args["--max-tokens"]) if "--max-tokens" in args else None)
        print(json.dumps(r)[:2000])
    else:
        sys.exit(f"unknown {cmd}")


if __name__ == "__main__":
    main()
