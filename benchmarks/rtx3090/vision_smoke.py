#!/usr/bin/env python3
"""vision_smoke.py — one-line vision check for the RTX 3090 cell (mmproj present).

Builds a small PNG containing a known string and a known shape, sends it as a data: URL
with a one-line question, and records whether the answer contains the string. This is a
smoke test, not a scored vision benchmark.

usage: vision_smoke.py <base_url> <out.json>
"""
import base64
import json
import sys
import time
import urllib.request

BASE = sys.argv[1].rstrip("/")
OUT = sys.argv[2] if len(sys.argv) > 2 else "vision-smoke.json"
SECRET = "ZQ-731"
IMG = "/tmp/vision-3090.png"


def make_image():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (520, 220), (250, 250, 248))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 250, 200], outline=(180, 30, 30), width=6)
    d.ellipse([300, 40, 480, 190], fill=(30, 90, 200))
    d.text((40, 95), SECRET, fill=(10, 10, 10))
    im.save(IMG)
    return IMG


def main():
    try:
        make_image()
    except Exception as e:
        json.dump({"ok": False, "error": f"cannot build image: {e}"}, open(OUT, "w"), indent=1)
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    b64 = base64.b64encode(open(IMG, "rb").read()).decode()
    payload = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "What alphanumeric code is printed inside the red rectangle "
                                 "in this image? Reply with only that code."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}],
        "temperature": 0, "max_tokens": 512, "stream": False}
    req = urllib.request.Request(BASE + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = json.loads(r.read())
    except Exception as e:
        json.dump({"ok": False, "error": str(e)[:400]}, open(OUT, "w"), indent=1)
        print(json.dumps({"ok": False, "error": str(e)[:200]}))
        return 1
    msg = (body.get("choices") or [{}])[0].get("message") or {}
    # the server runs with --reasoning auto: a thinking reply can put the answer in
    # reasoning_content and leave content empty, so grade the concatenation.
    ans = ((msg.get("content") or "") + "\n" + (msg.get("reasoning_content") or "")).strip()
    res = {"when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "prompt": "code inside the red rectangle", "expect": SECRET,
           "answer": ans, "ok": SECRET.lower() in ans.lower(),
           "wall_s": round(time.time() - t0, 2),
           "usage": body.get("usage"), "image_bytes": len(b64) * 3 // 4}
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
