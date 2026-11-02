#!/usr/bin/env python3
"""score_pack.py — run a frozen pack against :8081 and score it.

  score_pack.py aime        [--n N] [--samples 1|3] [--temp 0.0|0.6]  -> pub-aime10x3
  score_pack.py livebench   [--n N]                                   -> pub-livebench25
  score_pack.py shell       [--n N] [--turns 6]                       -> agent-shell10

Writes results/<id>.pub.json (SCHEMA-1 test cell, same shape emit_pub.py writes),
results/<id>.detail.json (per-question) and prints a one-line JSON summary.

Scoring (all deterministic, no LLM judge):
  aime      : extract last integer in the response, compare to answer (AIME answers 000-999)
  livebench : coding_completion -> run public tests against generated solution (real pass/fail);
              math -> last number / ground-truth integer match; reasoning -> conservative
              normalised exact match against ground truth. Metric reported as 'acc'
              (coding entries counted by tests-passed, others by match).
  shell     : model gets ONE bash tool call per turn, harness executes it in a scratch
              dir, up to --turns turns; success = frozen python predicate on the dir.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import r97  # noqa: E402

PACKS = os.path.join(SUITE, "packs")
RESULTS = (os.environ.get("LLMBENCH_RESULTS") or os.environ.get("R97_RESULTS")
           or os.path.join(SUITE, "results"))


def pack(name):
    p = os.path.join(PACKS, name)
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]


def emit(cid, task, acc, samples, dur, metrics_extra=None, notes=""):
    cell = {"id": cid, "task": task, "acc": round(float(acc), 4) if acc is not None else None,
            "metric": "acc", "samples": samples, "duration_s": int(dur),
            "n_a": acc is None, "reason": "" if acc is not None else notes}
    if metrics_extra:
        cell["metrics"] = metrics_extra
    return cell


LAST_INT = re.compile(r"(-?\d[\d,]*)")


def last_int(s):
    m = LAST_INT.findall(s.replace(",", ""))
    return m[-1] if m else None


def boxed(s):
    m = re.findall(r"\\boxed\{([^}]*)\}", s)
    if m:
        return m[-1].strip()
    m = re.findall(r"\\boxed\s*\{?\s*(-?\d[\d,]*)\s*\}?", s)
    return m[-1].replace(",", "") if m else None


# ------------------------------------------------------------------ AIME
LETTER = re.compile(r"\b([ABCD])\b")


def extract_letter(txt):
    """GPQA answer letter: prefer a boxed letter, then 'Answer: X', then the last
    standalone A-D letter in the response."""
    m = re.search(r"\\boxed\{\s*\(?([ABCD])\)?\s*\}", txt)
    if m:
        return m.group(1)
    m = re.search(r"answer\s*(?:is|:)\s*\**\s*\(?([ABCD])\b", txt, re.I)
    if m:
        return m.group(1).upper()
    ms = LETTER.findall(txt)
    return ms[-1] if ms else None


def run_gpqa(n=None):
    rows = pack("gpqa25.jsonl")
    if n:
        rows = rows[:n]
    t0 = time.time()
    ok = 0
    detail = []
    for r in rows:
        opts = "\n".join(f"{'ABCD'[i]}) {c}" for i, c in enumerate(r["choices"]))
        prompt = (r["question"] + "\n\nChoices:\n" + opts +
                  "\n\nThink step by step. Finish with a line 'Answer: <letter>' where "
                  "<letter> is one of A, B, C, D.")
        resp = r97.chat(prompt=prompt, temperature=0.0, max_tokens=LONG_CAP,
                        n_predict=LONG_CAP, seed=5)
        got = extract_letter(resp["content"])
        good = got == r["answer_letter"]
        ok += good
        detail.append({"id": r["id"], "answer": r["answer_letter"], "got": got,
                       "ok": good, "resp_tail": resp["content"][-300:]})
    dur = time.time() - t0
    cell = emit("pub-gpqa25", "gpqa-diamond", ok / len(rows) if rows else None,
                len(rows), dur, {"correct": ok, "total": len(rows), "temp": 0.0},
                "no samples")
    return cell, detail


# ------------------------------------------------------------------ long-context dimension
FILLER_FILE = "filler.json"
# Thinking models spend the first N tokens of the completion in their reasoning channel
# (visible content is empty until reasoning ends, ~300-600 tokens on LFM-8B). Caps must
# clear that budget or every answer looks empty.
LONG_CAP = 4096


def filler():
    import hashlib
    d = json.load(open(os.path.join(PACKS, FILLER_FILE)))
    h = hashlib.sha256(d["text"].encode()).hexdigest()
    return d["text"], h


def build_embedded(item_text, target_tokens, sides=(75, 25)):
    """Question planted at a frozen depth inside the haystack.

    The item is inserted 75% of the way through the filler (so 25% of the context follows
    it), and the final 25% carries a one-line pointer back to it. The answer is requested
    after the whole document — i.e. the model must still hold the question across tens of
    thousands of tokens of unrelated material.
    """
    text, fh = filler()
    need = max(0, target_tokens * 4 - len(item_text) - 200)
    hay = (text * (need // max(1, len(text)) + 1))[:need]
    cut = int(len(hay) * 0.75)
    head, tail = hay[:cut], hay[cut:]
    return head + "\n\n" + item_text + "\n\n" + tail, fh


def run_embedded(kind, target_tokens, n=None):
    """ctx-<kind><K> — same frozen questions, embedded in ~K tokens of distractor context."""
    rows = pack("gpqa25.jsonl") if kind == "gpqa" else pack("livebench25.jsonl")
    if n:
        rows = rows[:n]
    cid = f"ctx-{kind}{target_tokens // 1000}k"
    t0 = time.time()
    ok = 0
    detail = []
    fh = None
    prompt_tokens = []
    prefill_ms = 0.0
    for r in rows:
        if kind == "gpqa":
            opts = "\n".join(f"{'ABCD'[i]}) {c}" for i, c in enumerate(r["choices"]))
            item = (r["question"] + "\n\nChoices:\n" + opts)
            ask = ("\n\nAnswer the question about the document above. Think step by step. "
                   "Finish with a line 'Answer: <letter>' where <letter> is A, B, C or D.")
            want = r["answer_letter"]
            score = extract_letter
        else:
            item = r["prompt"]
            ask = "\n\nAnswer the question about the document above."
            want = r.get("ground_truth") or ""
            score = lambda t: "ok" if normalised_match(t, want) else None  # noqa: E731
        body = item + ask
        hay, fh = build_embedded(body, target_tokens)
        prompt = hay + "\n\nDocument ends.\n\n" + body
        resp = r97.chat(prompt=prompt, temperature=0.0, max_tokens=LONG_CAP,
                        n_predict=LONG_CAP, seed=9, timeout=3600)
        ptok = resp.get("prompt_n") or 0
        prompt_tokens.append(ptok)
        prefill_ms += resp.get("prompt_ms") or 0
        got = score(resp["content"])
        good = got == want if kind == "gpqa" else got == "ok"
        # a truncated prompt is a harness limit, not a model error: flag it
        truncated = bool(ptok and ptok < target_tokens * 0.8)
        ok += good
        detail.append({"id": r["id"], "want": want, "got": got, "ok": good,
                       "prompt_tokens": ptok, "truncated": truncated,
                       "resp_tail": resp["content"][-200:]})
    dur = time.time() - t0
    trunc = sum(1 for d in detail if d["truncated"])
    metrics = {"correct": ok, "total": len(rows), "temp": 0.0,
               "target_ctx_tokens": target_tokens,
               "prompt_tokens_mean": int(sum(prompt_tokens) / len(prompt_tokens)) if prompt_tokens else None,
               "prefill_s_total": round(prefill_ms / 1000, 1),
               "filler_sha256": fh, "ctx_overflow_fails": trunc}
    cell = emit(cid, f"{kind}-embedded-{target_tokens // 1000}k",
                ok / len(rows) if rows else None, len(rows), dur, metrics, "no samples")
    if trunc:
        cell["reason"] = (f"{trunc}/{len(rows)} prompts truncated below the target context "
                          "(server window limit) — counted as failures, not model errors")
    return cell, detail, metrics


def run_aime(n=None, samples=3, temp=0.6):
    rows = pack("aime2026-10.jsonl")
    if n:
        rows = rows[:n]
    t0 = time.time()
    got = 0
    correct_vote = 0
    correct_p1 = 0
    detail = []
    for i, r in enumerate(rows):
        prompt = (r["problem"] + "\n\nSolve the problem. The answer is an integer between 0 "
                  "and 999. Give your final answer on its own last line as: Answer: <integer>")
        votes, first = [], None
        for s in range(samples):
            resp = r97.chat(prompt=prompt, temperature=temp, seed=1000 + i * 10 + s,
                            max_tokens=LONG_CAP, n_predict=LONG_CAP)
            txt = resp["content"]
            a = boxed(txt) or last_int(txt.split("Answer:")[-1] if "Answer:" in txt else txt)
            if first is None:
                first = a
            votes.append(a)
        # majority vote over non-empty votes
        from collections import Counter
        c = Counter(v for v in votes if v is not None)
        win = c.most_common(1)[0][0] if c else None
        ok_vote = str(win) == str(r["answer"])
        ok_p1 = str(first) == str(r["answer"])
        got += ok_vote
        correct_vote += ok_vote
        correct_p1 += ok_p1
        detail.append({"id": r["id"], "answer": r["answer"], "votes": votes,
                       "vote": win, "ok_vote": ok_vote, "first": first, "ok_pass1": ok_p1})
    dur = time.time() - t0
    acc = correct_vote / len(rows) if rows else None
    cell = emit("pub-aime10x3", "aime2026-" + str(len(rows)), acc, len(rows), dur,
                {"correct": correct_vote, "total": len(rows),
                 "pass1_acc": round(correct_p1 / len(rows), 4) if rows else None,
                 "samples": samples, "temp": temp},
                "no samples")
    return cell, detail


# ------------------------------------------------------------------ LiveBench
def run_livebench(n=None):
    rows = pack("livebench25.jsonl")
    if n:
        rows = rows[:n]
    t0 = time.time()
    detail, ok = [], 0
    for r in rows:
        prompt = r["prompt"]
        if r["task"] != "coding_completion":
            prompt += ("\n\nAnswer with your final answer only, on the last line, prefixed "
                       "by 'Answer: '.")
        resp = r97.chat(prompt=prompt, temperature=0.0, max_tokens=LONG_CAP,
                        n_predict=LONG_CAP, seed=7)
        txt = resp["content"]
        passed = False
        info = ""
        if r["task"] == "coding_completion":
            passed, info = check_coding(r, txt)
        else:
            gt = r.get("ground_truth")
            # reasoning/math ground truth is stored in the *scored* form for coding/math
            # tasks the official pipeline judges against this string; we do normalised
            # exact match (conservative; no LLM judge).
            passed = normalised_match(txt, gt)
            info = (gt or "")[:120]
        ok += passed
        detail.append({"id": r["id"], "task": r["task"], "category": r["category"],
                       "ok": passed, "info": info, "resp_head": txt[:400]})
    dur = time.time() - t0
    cell = emit("pub-livebench25", "livebench-25", ok / len(rows) if rows else None,
                len(rows), dur, {"correct": ok, "total": len(rows), "temp": 0.0},
                "no samples")
    return cell, detail


def normalised_match(txt, gt):
    if not gt:
        return False
    g = str(gt).strip().lower()
    t = txt.lower()

    def norm(s):
        s = s.strip().strip(".").strip()
        s = re.sub(r"\s+", " ", s)
        return s

    def same(a, b):
        return norm(a) == norm(b) or norm(a).replace(" ", "") == norm(b).replace(" ", "")

    # 1) the task's own declared output format: <solution>a, b, c</solution>
    for m in re.findall(r"<solution>(.*?)</solution>", t, re.S):
        if same(m, g):
            return True
    # 2) last "answer:" line
    m = re.findall(r"answer\s*:\s*(.+)", t)
    if m and same(m[-1], g):
        return True
    # 3) the ground truth stated verbatim as the tail of the response
    if same(t[-len(norm(g)) - 40:] if len(t) > len(g) + 40 else t, g):
        return True
    return False


def check_coding(r, txt, stub=None):
    """Extract python block, append Solution/class as needed, run public tests."""
    blocks = re.findall(r"```(?:python)?\n(.*?)```", txt, re.S)
    if blocks:
        code = blocks[-1]
    else:
        # no fence: take from the first class/import/def line to the end
        m = re.search(r"^(?:class |import |from |def )", txt, re.M)
        code = txt[m.start():] if m else txt
    with open(os.path.join(PACKS, f"coding_{r['id']}.json")) as f:
        meta = json.load(f)
    tests = json.loads(meta["tests"])
    starter = stub if stub is not None else meta["starter"]
    # coding_completion continuations are often written un-indented; the starter's
    # enclosing def sits at 4 spaces, its body at 8.
    if starter and "class Solution" not in code:
        lines = code.splitlines()
        m = re.search(r"\n(\s+)def\s+\w+\(", starter)
        want = (m.group(1) + "    ") if m else "        "
        if lines and not lines[0].startswith((" ", "\t")):
            lines = [("" if not l.strip() else want + l) for l in lines]
        code = "\n".join(lines)
    full = starter.rstrip() + "\n" + code if starter and "class Solution" not in code else code
    runner = build_runner(full, meta, tests)
    try:
        p = subprocess.run([sys.executable, "-c", runner], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return False, ("run error: " + (p.stderr or "")[-200:])
        line = next((l for l in reversed(p.stdout.strip().splitlines())
                     if l.startswith("__RESULT__")), None)
        if line is None:
            return False, "no result marker (stdout tail: " + p.stdout.strip()[-120:] + ")"
        res = json.loads(line[len("__RESULT__"):])
    except Exception as e:
        return False, f"harness error {e}"
    okc = 0
    for t, got in zip(tests, res):
        exp = t["output"]
        got_s = py_literal(got)
        if got_s == py_literal(exp):
            okc += 1
    return okc == len(tests), f"{okc}/{len(tests)} public tests"


def py_literal(v):
    """LiveBench public outputs are python literals ('true/false' are booleans in the
    harness; a returned Python bool must compare equal). Normalise conservatively."""
    if isinstance(v, str):
        s = v.strip()
        if s.lower() in ("true", "false"):
            return s.lower()
        try:
            val = eval(s, {"__builtins__": {}}, {})  # frozen pack, not model output
            return json.dumps(val, sort_keys=True, default=str)
        except Exception:
            return s
    if isinstance(v, bool):
        return "true" if v else "false"
    try:
        return json.dumps(v, sort_keys=True, default=str)
    except Exception:
        return str(v)


def build_runner(code, meta, tests):
    # LeetCode-style inputs: one JSON value per line (LiveBench public_test_cases format).
    runner = f"""
import json
import typing
{code}

sol = Solution()
_res = []
_tests = {json.dumps(tests)}
def _parse(raw):
    args = []
    for line in raw.split(chr(10)):
        line = line.strip()
        if not line:
            continue
        try:
            args.append(json.loads(line))
        except Exception:
            try:
                # negative numbers need int(); eval with empty __builtins__ has none
                args.append(eval(line, {{"__builtins__": {{"int": int}}}}, {{}}))  # noqa: S307 - frozen pack
            except Exception:
                args.append(line.strip('"'))
    return args
for _t in _tests:
    try:
        _a = _parse(_t["input"])
        _res.append(sol.{meta['method']}(*_a))
    except Exception as _e:
        _res.append("__ERR__:" + str(_e)[:60])
print("__RESULT__" + json.dumps(_res, default=str))
"""
    return runner.strip()


# ------------------------------------------------------------------ shell10 (agentic)
TOOL = [{"type": "function", "function": {
    "name": "bash",
    "description": "Run one bash command in the task working directory. Returns exit code and output.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                   "required": ["command"]}}}]


TOOL_PROMPT = """
## Tools
You can call exactly one tool by replying with a single JSON object and nothing else:
{"name": "bash", "arguments": {"command": "<bash command>"}}
The harness executes it in the task working directory and replies with exit code and output.
When the task is complete, reply with the single word DONE (no JSON).
Never reply with prose alongside a tool call; either a JSON tool call or DONE.
"""


def parse_tool_text(txt):
    """Extract {"name","arguments"}/{"command"} style tool call from plain text."""
    if not txt:
        return None
    # 1) native-style arguments object
    for m in re.finditer(r'\{\s*"name"\s*:\s*"bash"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}', txt, re.S):
        try:
            d = json.loads(m.group(1))
            if d.get("command"):
                return d["command"]
        except Exception:
            pass
    # 2) bare {"command": "..."} — scan for balanced braces so nested quotes survive
    for m in re.finditer(r'\{\s*"command"\s*:', txt):
        i = m.start()
        depth = 0
        for j in range(i, len(txt)):
            if txt[j] == "{":
                depth += 1
            elif txt[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        d = json.loads(txt[i:j + 1])
                        if isinstance(d.get("command"), str) and d["command"].strip():
                            return d["command"]
                    except Exception:
                        pass
                    break
    for m in re.finditer(r"\{[^{}]*\"command\"[^{}]*\}", txt, re.S):
        try:
            d = json.loads(m.group(0))
        except Exception:
            continue
        if isinstance(d.get("arguments"), dict) and d["arguments"].get("command"):
            return d["arguments"]["command"]
        if isinstance(d.get("command"), str):
            return d["command"]
    m = re.search(r"```(?:bash|sh)?\n(.*?)```", txt, re.S)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return None


def run_shell(n=None, turns=6):
    rows = pack("shell10.jsonl")
    if n:
        rows = rows[:n]
    t0 = time.time()
    ok = 0
    detail = []
    for r in rows:
        d = tempfile.mkdtemp(prefix="sh10_")
        for name, content in (r.get("setup") or {}).items():
            fp = os.path.join(d, name)
            os.makedirs(os.path.dirname(fp) or d, exist_ok=True)
            with open(fp, "w") as f:
                f.write(content)
        msgs = [{"role": "system", "content":
                 "You are an agent with exactly one tool: bash. Each turn you may either call "
                 "bash once, or reply DONE when the task is complete. Work in the current "
                 "directory. Never delete files you were not asked to touch." + TOOL_PROMPT},
                {"role": "user", "content": r["prompt"]}]
        log, done_turn, peak = [], None, 0
        for tn in range(turns):
            resp = r97.chat(messages=msgs, tools=TOOL, temperature=0.0,
                            max_tokens=LONG_CAP, n_predict=LONG_CAP, seed=11)
            peak = max(peak, resp.get("prompt_n") or 0)
            calls = resp["tool_calls"]
            text_cmd = None
            if not calls:
                # many local chat templates are not trained on native tool calls:
                # accept a JSON/bash-block tool call in the text as well
                text_cmd = parse_tool_text(resp["content"])
                if text_cmd:
                    calls = [{"id": f"text{tn}", "type": "function",
                              "function": {"name": "bash",
                                           "arguments": json.dumps({"command": text_cmd})}}]
            if not calls:
                content = resp["content"]
                msgs.append({"role": "assistant", "content": content})
                log.append({"turn": tn + 1, "cmd": None, "reply": content[:300]})
                if "DONE" in content.upper():
                    done_turn = tn + 1
                    break
                msgs.append({"role": "user", "content": "No tool call seen. Call the bash tool or reply DONE."})
                continue
            c = calls[0]
            fn = (c.get("function") or {})
            cid = c.get("id") or f"call{tn}"
            try:
                cmd = json.loads(fn.get("arguments") or "{}").get("command", "")
            except Exception:
                cmd = text_cmd or ""
            if text_cmd:
                # text-mode call: echo the call back in the same syntax the model used
                msgs.append({"role": "assistant", "content": resp["content"]})
            else:
                msgs.append({"role": "assistant", "content": "", "tool_calls": [c]})
            try:
                p = subprocess.run(["bash", "-lc", cmd], cwd=d, capture_output=True,
                                   text=True, timeout=60)
                out = (p.stdout or "") + (p.stderr or "")
                rc = p.returncode
            except Exception as e:
                out, rc = f"exec error {e}", -1
            result_text = f"exit={rc}\n{out[-2000:]}"
            if text_cmd:
                msgs.append({"role": "user", "content": "TOOL RESULT\n" + result_text})
            else:
                msgs.append({"role": "tool", "tool_call_id": cid, "content": result_text})
            log.append({"turn": tn + 1, "cmd": cmd[:300], "rc": rc, "out": out[-300:],
                        "mode": "text" if text_cmd else "native"})
            if tn + 1 == turns:
                done_turn = turns if "DONE" in (resp["content"] or "").upper() else None
        passed = eval_success(d, r["success"])
        ok += passed
        detail.append({"id": r["id"], "ok": passed, "turns": len(log),
                       "done_turn": done_turn, "ctx_peak_used": peak, "log": log})
        shutil.rmtree(d, ignore_errors=True)
    dur = time.time() - t0
    peak_max = max([d.get("ctx_peak_used") or 0 for d in detail] or [0])
    cell = emit("agent-shell10", "shell10", ok / len(rows) if rows else None, len(rows), dur,
                {"correct": ok, "total": len(rows), "max_turns": turns, "temp": 0.0,
                 "ctx_peak_used": peak_max},
                "no samples")
    return cell, detail


def eval_success(d, expr):
    def read(p, mode="r"):
        with open(os.path.join(d, p), mode) as f:
            return f.read()
    def exists(p):
        return os.path.exists(os.path.join(d, p))
    def isdir(p):
        return os.path.isdir(os.path.join(d, p))
    def listdir(p="."):
        return os.listdir(os.path.join(d, p))
    def ok(cmd):
        p = subprocess.run(["bash", "-lc", cmd], cwd=d, capture_output=True, text=True)
        return p.returncode == 0
    try:
        return bool(eval(expr, {"read": read, "exists": exists, "isdir": isdir,
                                "listdir": listdir, "ok": ok, "__builtins__": {}}))
    except Exception:
        return False


# ------------------------------------------------------------------ main
def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(2)
    cmd = a[0]
    opt = dict(zip(a[1::2], a[2::2]))
    n = int(opt["--n"]) if "--n" in opt else None
    samples = int(opt.get("--samples", 3))
    temp = float(opt.get("--temp", 0.6))
    turns = int(opt.get("--turns", 6))
    os.makedirs(RESULTS, exist_ok=True)
    if cmd == "gpqa":
        cell, detail = run_gpqa(n)
    elif cmd == "ctx":
        kind = opt["--kind"]; k = int(opt["--k"])
        cell, detail, _m = run_embedded(kind, k, n)
    elif cmd == "aime":
        cell, detail = run_aime(n, samples, temp)
    elif cmd == "livebench":
        cell, detail = run_livebench(n)
    elif cmd == "shell":
        cell, detail = run_shell(n, turns)
    else:
        sys.exit(f"unknown {cmd}")
    with open(os.path.join(RESULTS, cell["id"] + ".pub.json"), "w") as f:
        json.dump(cell, f, indent=1)
    with open(os.path.join(RESULTS, cell["id"] + ".detail.json"), "w") as f:
        json.dump(detail, f, indent=1)
    print(json.dumps(cell))


if __name__ == "__main__":
    main()
