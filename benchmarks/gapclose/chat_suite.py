#!/usr/bin/env python3
"""chat_suite.py — the 10-question chat suite (data/chat/27b.json schema) vs any server.

usage: chat_suite.py <base_url> <slug> <out.json> [--questions questions.json] [--max-tokens 512]
                     [--thinking false|true]

Each question: temp 0, seed fixed by index, enable_thinking as given (chat_template_kwargs).
verdict is a *string comparison* against the expected answer, done by a keyword matcher:
  - "correct"  if any expected alternative token (case-insensitive) appears in the answer
  - "partial"  if the answer is non-empty and the expected key terms are absent but the
               intended entity is recognisably referenced (numbers: numeric value present)
  - "wrong"    otherwise
The matcher is deliberately simple and identical for every model, so the comparison across
models is fair even where a human would grade differently; raw answers are always kept.
"""
import json, re, statistics, sys, time, urllib.request

BASE = sys.argv[1].rstrip("/")
SLUG = sys.argv[2]
OUT = sys.argv[3]
QFILE = "questions.json"
MAXT = 512
THINK = False
for i, a in enumerate(sys.argv):
    if a == "--questions": QFILE = sys.argv[i + 1]
    if a == "--max-tokens": MAXT = int(sys.argv[i + 1])
    if a == "--thinking": THINK = sys.argv[i + 1].lower() in ("1", "true", "yes")


def post(path, payload, timeout=1800):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


NUMWORDS = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
            "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
            "100": "100", "hundred": "100"}


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[`*_#]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def match(answer, expect):
    a, e = norm(answer), norm(expect)
    if not a:
        return "wrong"
    # alternatives are separated by '/', ';' or ' or '; each alternative is further
    # reduced to its comma-separated head terms ('Canberra, ACT' -> 'canberra').
    alts = []
    for x in re.split(r"[;/]| or ", e):
        x = norm(x)
        if not x:
            continue
        alts.append(x)
        for part in x.split(","):
            part = part.strip()
            if part:
                alts.append(part)
    for alt in alts:
        if alt and alt in a:
            return "correct"
        # a short numeric expectation must not match a compound like 'three-point'
        if alt.isdigit():
            for mt in re.finditer(r"\b%s\b" % alt, a):
                tail = a[mt.end():mt.end() + 2]
                if not tail.startswith("-") and not tail.startswith("."):
                    return "correct"
        if alt in NUMWORDS and re.search(r"\b%s\b" % NUMWORDS[alt], a):
            return "correct"
    # partial: some distinctive word of the expectation appears
    words = [w for w in re.findall(r"[a-z]{4,}", e) if w not in
             ("that", "with", "does", "what", "from", "your", "into", "have")]
    if any(w in a for w in words):
        return "partial"
    return "wrong"


def main():
    qs = json.load(open(QFILE))
    if isinstance(qs, dict):
        qs = qs.get("questions") or qs.get("qs")
    res = {"model": SLUG, "server_model": None, "base": BASE, "max_tokens": MAXT,
           "thinking": THINK, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "questions": [], "summary": {}}
    try:
        m = json.load(urllib.request.urlopen(BASE + "/v1/models", timeout=30))
        res["server_model"] = ((m.get("models") or [{}])[0].get("model")
                               or (m.get("data") or [{}])[0].get("id"))
    except Exception:
        pass
    tps, secs = [], []
    for idx, q in enumerate(qs):
        payload = {"messages": [{"role": "user", "content": q["q"]}],
                   "temperature": 0.0, "seed": 100 + idx, "max_tokens": MAXT,
                   "chat_template_kwargs": {"enable_thinking": bool(THINK)},
                   "stream": False}
        row = {"id": q["id"], "topic": q.get("topic"), "q": q["q"], "expect": q["expect"]}
        try:
            body, wall = post("/v1/chat/completions", payload)
        except Exception as e:
            row.update({"answer": "", "tokens": None, "ms": None, "decode_tps": None,
                        "ok": False, "verdict": "error", "error": str(e)[:300]})
            res["questions"].append(row)
            print(row["id"], "ERR", str(e)[:100], flush=True)
            continue
        ch = (body.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        ans = msg.get("content") or ""
        u = body.get("usage") or {}
        tim = body.get("timings") or {}
        v = match(ans, q["expect"])
        tk = u.get("completion_tokens")
        dt = tim.get("predicted_per_second")
        row.update({"answer": ans.strip(), "tokens": tk,
                    "ms": round(wall * 1000), "wall_s": round(wall, 2),
                    "decode_tps": round(dt, 2) if dt else None,
                    "finish_reason": ch.get("finish_reason"),
                    "reasoning_chars": len(msg.get("reasoning_content") or ""),
                    "ok": v == "correct", "verdict": v})
        res["questions"].append(row)
        if tk: tps.append(tk)
        secs.append(wall)
        print(row["id"], v, tk, row["wall_s"], repr(ans[:60]), flush=True)
        json.dump(res, open(OUT, "w"), indent=1)
    c = sum(1 for r in res["questions"] if r["verdict"] == "correct")
    p = sum(1 for r in res["questions"] if r["verdict"] == "partial")
    w = sum(1 for r in res["questions"] if r["verdict"] == "wrong")
    e = sum(1 for r in res["questions"] if r["verdict"] == "error")
    dts = [r["decode_tps"] for r in res["questions"] if r.get("decode_tps")]
    res["summary"] = {"n": len(res["questions"]), "correct": c, "partial": p, "wrong": w,
                      "errors": e, "accuracy": round(c / len(res["questions"]) * 100, 1),
                      "mean_tokens": round(statistics.mean(tps), 1) if tps else None,
                      "total_tokens": sum(t for t in tps if t),
                      "wall_s": round(sum(secs), 1),
                      "mean_decode_tps": round(statistics.mean(dts), 2) if dts else None}
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps(res["summary"], indent=1), flush=True)


if __name__ == "__main__":
    main()
