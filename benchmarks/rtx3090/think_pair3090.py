#!/usr/bin/env python3
"""think_pair.py — thinking ON vs OFF, same question set, same model and server flags.

usage: think_pair.py <base> <out_json> [--n 25]

Question set + prompt + scoring are cell 1's exactly (docs/BENCHMARK.md §1 pub-gpqa25):
  pack suites/packs/gpqa25.jsonl, prompt = question + "Choices:" + options + the frozen
  "Think step by step ... Answer: <letter>" line, temperature 0.0, seed 5, extraction
  via score_pack.extract_letter (boxed -> "Answer: X" -> last standalone A-D).

The ONLY variable is chat_template_kwargs.enable_thinking. Token caps are identical
(4096) unless --max-tokens-think is given; a mode that hits `length` before its
"Answer:" line is recorded as unanswered (correct=false, finish_reason=length), never
silently retried.
"""
import importlib.util, json, sys, time, urllib.request

BASE = sys.argv[1].rstrip("/")
OUT = sys.argv[2]
N = 25
MAXT_OFF = 4096
MAXT_ON = 4096
for i, a in enumerate(sys.argv):
    if a == "--n":
        N = int(sys.argv[i + 1])
    if a == "--max-tokens-off":
        MAXT_OFF = int(sys.argv[i + 1])
    if a == "--max-tokens-think":
        MAXT_ON = int(sys.argv[i + 1])

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
ROOT = __import__("os").path.dirname(__import__("os").path.dirname(HERE))
PACK = __import__("os").path.join(HERE, "packs", "gpqa25.jsonl")
SEED = 5


def load_extract_letter():
    spec = importlib.util.spec_from_file_location(
        "score_pack", __import__("os").path.join(ROOT, "suite", "bin", "score_pack.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.extract_letter


def post(path, payload, timeout=3600):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


def prompt_for(r):
    opts = "\n".join(f"{'ABCD'[i]}) {c}" for i, c in enumerate(r["choices"]))
    return (r["question"] + "\n\nChoices:\n" + opts +
            "\n\nThink step by step. Finish with a line 'Answer: <letter>' where "
            "<letter> is one of A, B, C, D.")


def run_mode(mode, items, extract):
    think = mode == "on"
    maxt = MAXT_ON if think else MAXT_OFF
    rows = []
    t_mode = time.time()
    for idx, it in enumerate(items):
        payload = {"messages": [{"role": "user", "content": prompt_for(it)}],
                   "temperature": 0.0, "seed": SEED, "max_tokens": maxt,
                   "chat_template_kwargs": {"enable_thinking": think},
                   "stream": False}
        row = {"i": idx, "id": it["id"], "answer_key": it["answer_letter"]}
        try:
            body, wall = post("/v1/chat/completions", payload)
        except Exception as e:
            row.update({"error": str(e)[:300], "correct": False})
            rows.append(row); print(mode, idx, "ERR", str(e)[:120], flush=True); continue
        ch = (body.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        u = body.get("usage") or {}
        tim = body.get("timings") or {}
        ans = extract(content)
        if ans is None and reasoning:
            ans = extract(reasoning)   # thinking variant may leave content empty at cap
        row.update({
            "content_tail": content[-200:], "answer_got": ans,
            "correct": bool(ans and ans == row["answer_key"]),
            "completion_tokens": u.get("completion_tokens"),
            "reasoning_chars": len(reasoning), "content_chars": len(content),
            "finish_reason": ch.get("finish_reason"),
            "wall_s": round(wall, 2),
            "prefill_tps": round(tim.get("prompt_per_second") or 0, 1),
            "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
        })
        rows.append(row)
        print(mode, idx, row["id"], "OK" if row["correct"] else "wrong",
              row["completion_tokens"], row["wall_s"], row["finish_reason"], flush=True)
    return {"mode": mode, "max_tokens": maxt, "wall_s": round(time.time() - t_mode, 1),
            "n": len(rows), "correct": sum(1 for r in rows if r.get("correct")),
            "tokens": sum((r.get("completion_tokens") or 0) for r in rows),
            "length_stops": sum(1 for r in rows if r.get("finish_reason") == "length"),
            "rows": rows}


def main():
    extract = load_extract_letter()
    items = [json.loads(l) for l in open(PACK) if l.strip()][:N]
    res = {"base": BASE, "pack": PACK, "seed": SEED, "temperature": 0.0,
           "settings": {"max_tokens_off": MAXT_OFF, "max_tokens_on": MAXT_ON},
           "when": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        m = json.load(urllib.request.urlopen(BASE + "/v1/models", timeout=30))
        res["model"] = ((m.get("models") or [{}])[0].get("model") if m.get("models")
                        else (m.get("data") or [{}])[0].get("id"))
    except Exception:
        pass
    for mode in ("off", "on"):
        res[mode] = run_mode(mode, items, extract)
        json.dump(res, open(OUT, "w"), indent=1)
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: (v if k not in ("off", "on") else
                          {kk: v[kk] for kk in ("mode", "n", "correct", "tokens", "wall_s", "length_stops")})
                      for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
