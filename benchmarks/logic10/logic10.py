#!/usr/bin/env python3
"""logic10.py — ten everyday trap questions, thinking ON vs OFF, one request per question.

Same method as benchmarks/a3b-thinking/think_pair.py:
  * temperature 0.0, fixed seed, one question per request, fresh context (no history),
    no few-shot examples;
  * identical max_tokens for both arms;
  * the ONLY variable between arms is chat_template_kwargs.enable_thinking.

Grading (strict, from questions.json):
  * the model's "commitment" is the text after the LAST standalone line starting with
    'Answer:' across content + reasoning channel (thinking repeats intermediate answers);
  * it must equal one of the question's `accept` patterns after normalisation
    (lowercase, strip punctuation/currency/thousands separators, collapse spaces);
  * a canned refusal to answer counts as wrong, not as "unscored";
  * if finish_reason == length and no usable answer line was emitted, the question is
    flagged `truncated` — reported as such, excluded from any score claim.
Raw answer text, reasoning tail and finish_reason are stored per question.

Resumable: state is written after every request to <out>.json; re-running the same
command continues where it stopped. One mode is completed before the other.

usage: logic10.py <out_json> --regrade        # re-apply the grader to stored answers
       logic10.py <base> <out_json> --slug NAME [--max-tokens 8192] [--modes off,on]
       [--expect SUBSTR] # refuse to run unless the served model path contains SUBSTR
                         # (catches a server that came up with the wrong weights)
       [--start-at ID]   # skip questions before ID (primes the server before timing)
"""
import json, os, re, sys, time, urllib.request

BASE = sys.argv[1].rstrip("/")
OUT = sys.argv[2]
MAXT = 8192
MODES = ["off", "on"]
SLUG = None
START_AT = None
EXPECT = None
for i, a in enumerate(sys.argv):
    if a == "--start-at":
        START_AT = sys.argv[i + 1]
    if a == "--expect":
        EXPECT = sys.argv[i + 1]
    if a == "--max-tokens":
        MAXT = int(sys.argv[i + 1])
    if a == "--modes":
        MODES = sys.argv[i + 1].split(",")
    if a == "--slug":
        SLUG = sys.argv[i + 1]

HERE = os.path.dirname(os.path.abspath(__file__))
QFILE = os.path.join(HERE, "questions.json")
QD = json.load(open(QFILE, encoding="utf-8"))
QS = QD["questions"]
SEED = int(QD.get("seed", 5))
TEMP = float(QD.get("temperature", 0.0))

PROMPT = "{q}\n\nAnswer in the format 'Answer: <your answer>'. Keep the final answer line short."

ANS_RE = re.compile(r"(?im)^\s*(?:\*\*)?answer\s*(?:\*\*)?\s*[:\-]\s*(.+?)\s*$")
REFUSAL_RE = re.compile(r"(?i)\b(i can'?t|cannot|can not|unable to|i(')?m not able|i won'?t)\b.{0,40}\b(answer|respond|help)")


def norm(s):
    s = s.lower().strip()
    if "answer" in s:                          # "19.2</think>Answer: 19.2" -> keep the final answer
        s = re.split(r"answer\s*[:\-]", s)[-1]
    s = re.sub(r"</?think>", "", s)
    s = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", s)
    s = re.sub(r"[\u2013\u2014]", "-", s)
    s = re.sub(r"\$\s?", "", s)                 # currency signs
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)   # thousands separators
    s = re.sub(r"[*_`\"']", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[.!?;:]+$", "", s).strip()
    return s


def commitment(content, reasoning):
    """The answer the model commits to: the last 'Answer:' payload, else the last sentence."""
    got, how = last_answer_line(content, reasoning)
    if got:
        return got, how
    if reasoning:
        got, how = last_answer_line("", reasoning)
        if got:
            return got, how
    txt = (content or "").strip()
    if txt:
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", txt) if x.strip()]
        if sents:
            return sents[-1], "last-sentence"
    return None, "none"


def last_answer_line(content, reasoning):
    for txt in (content, reasoning):
        if not txt:
            continue
        m = ANS_RE.findall(txt)
        if m:
            return m[-1], "answer-line"
    return None, "none"


def post(path, payload, timeout=3600):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


def grade(it, got, finish, content, reasoning):
    """Return (verdict, note). verdict in correct|wrong|truncated. Unscored only for transport errors."""
    if got is not None:
        g = norm(got)
        for a in it["accept"]:
            if g == norm(a) or (it.get("substring") and norm(a) in g):
                return "correct", None
        return "wrong", "not in accept set"
    # no answer line: decide truncated vs answered-but-unparseable
    if finish == "length":
        return "truncated", "cap reached before an 'Answer:' line — not scored"
    blob = (content or "") + "\n" + (reasoning or "")
    if REFUSAL_RE.search(blob):
        return "wrong", "declined to answer"
    # try a single-line whole-response answer (models sometimes omit the label)
    lines = [l for l in (content or "").strip().splitlines() if l.strip()]
    if lines and len(lines) <= 3:
        cand = norm(lines[-1])
        for a in it["accept"]:
            if cand == norm(a):
                return "correct", "unlabelled answer"
    return "wrong", "no parseable answer line"


def empty_state():
    st = {"harness": "logic10.py", "questions_file": "benchmarks/logic10/questions.json",
          "slug": SLUG, "base": BASE, "temperature": TEMP, "seed": SEED,
          "max_tokens_both_modes": MAXT,
          "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": None,
          "modes": {}, "server_flags": None}
    for m in ("off", "on"):
        st["modes"][m] = {"mode": m, "rows": [], "started": None, "finished": None}
    return st


def summarize(mode_block):
    rows = mode_block["rows"]
    scored = [r for r in rows if r.get("verdict") in ("correct", "wrong")]
    return {"n": len(rows), "correct": sum(1 for r in scored if r["verdict"] == "correct"),
            "wrong": sum(1 for r in scored if r["verdict"] == "wrong"),
            "truncated": sum(1 for r in rows if r.get("verdict") == "truncated"),
            "errors": sum(1 for r in rows if r.get("verdict") == "error"),
            "scored": len(scored),
            "tokens": sum(r.get("completion_tokens") or 0 for r in rows),
            "wall_s": round(sum(r.get("wall_s") or 0 for r in rows), 1),
            "max_tokens": MAXT}


def save(st):
    for m, b in st["modes"].items():
        b["summary"] = summarize(b)
    tmp = OUT + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, OUT)


def regrade():
    """Re-apply the current grader to stored raw answers (no requests are sent).

    Used when grading rules change: the result file keeps every raw answer, so scores
    are always reproducible from what the model actually printed.
    """
    path = OUT if OUT != "--regrade" else sys.argv[1]
    print("regrading", path)
    st = json.load(open(path))
    Q = {q["id"]: q for q in QS}
    for mode, blk in st["modes"].items():
        for r in blk["rows"]:
            if r.get("verdict") == "error":
                continue
            got, how = commitment(r.get("content_tail") or "", "")
            if r.get("answer_got"):
                got, how = r["answer_got"], r.get("answer_how") or how
            v, note = grade(Q[r["id"]], got, r.get("finish_reason"), r.get("content_tail") or "",
                            r.get("reasoning_tail") or "")
            if r.get("finish_reason") == "length" and v == "wrong" and not got:
                v, note = "truncated", note
            r.update({"verdict": v, "note": note, "answer_raw": got or r.get("answer_raw")})
        blk["summary"] = summarize(blk)
        print(mode, "->", blk["summary"]["correct"], "/", blk["summary"]["scored"],
              "trunc", blk["summary"]["truncated"])
    json.dump(st, open(path, "w"), indent=1)
    print("regraded", path)


def main():
    if "--regrade" in sys.argv:
        return regrade()
    st = json.load(open(OUT)) if os.path.exists(OUT) else empty_state()
    st["max_tokens_both_modes"] = MAXT
    try:
        pr = json.loads(urllib.request.urlopen(BASE + "/props", timeout=30).read())
        st["model"] = pr.get("model_alias") or pr.get("model_path")
        # /props echoes the launch path (usually the active.gguf symlink) -> resolve it
        st["model_served"] = os.path.realpath(st["model"]) if st["model"] else None
    except Exception as e:
        print("props error", e, flush=True)
    if SLUG:
        st["slug"] = SLUG
    st["expected_model"] = EXPECT
    if EXPECT:
        served = (st.get("model_served") or st.get("model") or "")
        # /props echoes the path it was started with, which is usually the active.gguf
        # symlink -> resolve it so the check compares weights, not link names.
        try:
            if os.path.islink(served) or served.startswith("/"):
                served = os.path.realpath(served)
        except Exception:
            pass
        if EXPECT.lower() not in served.lower():
            print("REFUSING: server serves %r, expected %r. No requests sent." % (served, EXPECT),
                  flush=True)
            sys.exit(3)

    for mode in MODES:
        blk = st["modes"][mode]
        done = {r["id"] for r in blk["rows"] if r.get("verdict") != "error"}
        blk["started"] = blk.get("started") or time.strftime("%Y-%m-%dT%H:%M:%S%z")
        ids = [q["id"] for q in QS]
        skip_until = ids.index(START_AT) if (START_AT in ids and mode == MODES[0]
                                             and not blk["rows"]) else 0
        for qi, it in enumerate(QS):
            if qi < skip_until:
                blk.setdefault("skipped_priming", []).append(it["id"])
                continue
            if it["id"] in done:
                continue
            payload = {"messages": [{"role": "user", "content": PROMPT.format(q=it["q"])}],
                       "temperature": TEMP, "seed": SEED, "max_tokens": MAXT,
                       "chat_template_kwargs": {"enable_thinking": mode == "on"},
                       "stream": False}
            row = {"id": it["id"], "mode": mode, "trap": it["trap"]}
            body = None
            last_err = None
            for attempt in (1, 2):
                try:
                    body, wall = post("/v1/chat/completions", payload)
                    break
                except Exception as e:
                    last_err = str(e)[:300]
                    body = None
            if body is None:
                row.update({"verdict": "error", "error": last_err})
                blk["rows"] = [r for r in blk["rows"] if r["id"] != it["id"]] + [row]
                save(st)
                print(mode, it["id"], "ERR", last_err, flush=True)
                continue
            ch = (body.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            fin = ch.get("finish_reason")
            u = body.get("usage") or {}
            tim = body.get("timings") or {}
            got, how = commitment(content, reasoning)
            verdict, note = grade(it, got, fin, content, reasoning)
            row.update({
                "verdict": verdict, "note": note, "answer_how": how,
                "answer_got": got,
                "answer_raw": (got or "")[:200],
                "content_tail": content[-600:],
                "reasoning_tail": reasoning[-400:] if reasoning else "",
                "finish_reason": fin,
                "completion_tokens": u.get("completion_tokens"),
                "predicted_n": tim.get("predicted_n"),
                "prompt_tokens": u.get("prompt_tokens"),
                "reasoning_chars": len(reasoning), "content_chars": len(content),
                "wall_s": round(wall, 2),
                "decode_tps": round(tim.get("predicted_per_second") or 0, 2),
            })
            blk["rows"] = [r for r in blk["rows"] if r["id"] != it["id"]] + [row]
            save(st)
            print(mode, it["id"], verdict, (got or "-")[:40], row["completion_tokens"],
                  row["wall_s"], fin, flush=True)
        blk["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save(st)
    save(st)
    print(json.dumps({m: summarize(st["modes"][m]) for m in st["modes"]}, indent=1))


if __name__ == "__main__":
    main()
