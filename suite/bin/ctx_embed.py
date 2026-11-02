#!/usr/bin/env python3
"""ctx_embed.py — long-context dimension for the R9700 intel+agentic suite.

Cells (registered in run_suite.sh as 4 = c1, 5 = c2):
  c1  ctx-gpqa30k   : GPQA-25 questions embedded in ~30,000-token haystack
  c2  ctx-gpqa110k  : same questions, ~110,000-token haystack

Contract
--------
* **Deterministic haystack.** Built from the FROZEN pack `packs/filler.json` (fixed order,
  no RNG at runtime). The exact haystack text is materialised once as
  `packs/ctx_filler.txt` (fast path) and its sha256 appended to `packs/manifest.json`.
  If the frozen text is missing/mutated we rebuild it from filler.json and record the sha.
* **Needle placement at 25 / 50 / 75 % depth.** Every item is planted at each of the three
  depths (same question three times in one prompt) and a single answer is requested after
  the whole document — so a model that only attends near the end cannot pass by luck.
* **Token calibration.** One call to the server's POST /tokenize converts chars -> tokens
  for the real tokenizer (llama.cpp b11517). The prompt is then built to land within ±5 %
  of the target. If /tokenize is absent we fall back to a deterministic chars/token ratio
  measured once from the frozen pack (fillers.json "chars_per_token").
* **Scoring** = the cell-1 letter exact match (`score_pack.extract_letter`, frozen copy
  semantics: boxed letter -> "Answer: X" -> last standalone A-D).
* **duration_s** = wall clock for the whole cell incl. prefill.
* **Failure modes that are NOT model errors** are recorded, never silently zeroed:
    binding_reason "ctx-110k-OOM"    server rejected/aborted the 110k prompt (VRAM/KV)
    binding_reason "ctx-<k>-trunc"   prompt truncated by the server window
    binding_reason "ctx-<k>-error"   transport error (server died mid-cell)
  In every case the rung is skipped (n_a=true + reason) and the previous rung's record is
  kept — the suite must never lose the 30k row because 110k blew up.

Output (same SCHEMA-1 shape emit_pub.py writes, so the night run picks it up automatically):
  results/<id>.pub.json     the cell
  results/<id>.detail.json  per-question, per-depth evidence

Usage:
  ctx_embed.py --cell c1 [--n 2] [--dry]     # c1 -> ctx-gpqa30k
  ctx_embed.py --cell c2 [--n 2]             # c2 -> ctx-gpqa110k
  ctx_embed.py --cell c1 --base http://127.0.0.1:8081
  ctx_embed.py --selftest                    # offline: builds packs, no model needed
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.path.dirname(HERE)
PACKS = os.path.join(SUITE, "packs")
RESULTS = (os.environ.get("LLMBENCH_RESULTS") or os.environ.get("R97_RESULTS")
           or os.path.join(SUITE, "results"))
FILLER_JSON = os.path.join(PACKS, "filler.json")
FILLER_TXT = os.path.join(PACKS, "ctx_filler.txt")
MANIFEST = os.path.join(PACKS, "manifest.json")
GPQA = os.path.join(PACKS, "gpqa25.jsonl")

CELLS = {"c1": ("ctx-gpqa30k", 30000), "c2": ("ctx-gpqa110k", 110000)}
DEPTHS = (25, 50, 75)         # percent of haystack BEFORE the needle
TOL = 0.05                    # ±5 % prompt-token tolerance
LONG_CAP = 4096               # completion budget (thinking models burn ~300-600 first)
SEED = 9
# Deterministic fallback when /tokenize is unavailable: measured once on b11517 with
# packs/filler.json (380,292 chars -> 93,636 tokens). Only used if the endpoint is missing.
FALLBACK_CPT = 380292 / 93636.0


def cap_for(target):
    """Completion budget. Long prompts on LFM-8B suppress EOS and the model rambles to the
    cap (finish_reason=length), so keep the answer budget tight: ~1.2k tokens safely clears
    the ~300-600-token thinking preamble and leaves room for a short step-by-step + letter.
    """
    return min(LONG_CAP, 1280)


# ------------------------------------------------------------------ packs
def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def ensure_filler():
    """Materialise the frozen haystack text + record its sha in manifest.json.

    Deterministic: the text is always filler.json["text"] verbatim (fixed order). The .txt
    is a fast path only; it is rebuilt if it drifts from the frozen json.
    """
    if not os.path.exists(FILLER_JSON):
        raise SystemExit("missing %s — run bin/build_filler.py first" % FILLER_JSON)
    fj = json.load(open(FILLER_JSON))
    text = fj["text"]
    sha = _sha(text)
    if fj.get("sha256") and fj["sha256"] != sha:
        raise SystemExit("packs/filler.json sha mismatch (recorded %s actual %s) — "
                         "refusing to run on a mutated haystack" % (fj["sha256"][:12], sha[:12]))
    wrote = False
    if not os.path.exists(FILLER_TXT) or _sha(open(FILLER_TXT).read()) != sha:
        with open(FILLER_TXT, "w") as f:
            f.write(text)
        wrote = True
    # manifest entry (idempotent, preserves every existing pack entry + built stamp)
    man = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {"packs": {}}
    man.setdefault("packs", {})
    entry = {"n": 1, "chars": len(text), "sha256": sha,
             "source": "filler.json (build_filler.py; aime2026-10 + fixed prose, seed 20261027)",
             "note": "frozen long-context distractor haystack materialised verbatim; "
                     "the SAME text is used for ctx-gpqa30k and ctx-gpqa110k on every model"}
    if man["packs"].get("ctx_filler.txt", {}).get("sha256") != sha:
        man["packs"]["ctx_filler.txt"] = entry
        man.setdefault("filler_rebuilds", [])
        man["filler_rebuilds"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sha256": sha})
        with open(MANIFEST + ".new", "w") as f:
            json.dump(man, f, indent=1)
        os.replace(MANIFEST + ".new", MANIFEST)
    return text, sha, wrote


def gpqa_rows(n=None):
    rows = [json.loads(l) for l in open(GPQA) if l.strip()]
    return rows[:n] if n else rows


# ------------------------------------------------------------------ server
class Srv:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self._cpt = None
        self.tokenize_ok = None   # None = not probed, True/False after calibrate()

    def _post(self, path, payload, timeout):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def tokenize(self, content):
        """POST /tokenize -> token count, or None if the endpoint is absent."""
        try:
            d = self._post("/tokenize", {"content": content}, 300)
            toks = d.get("tokens")
            return len(toks) if isinstance(toks, list) else None
        except urllib.error.HTTPError as e:
            if e.code in (404, 405, 501):
                return None
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            return None

    def calibrate(self, text):
        """chars per token for THIS server's tokenizer (None -> frozen fallback)."""
        if self._cpt is None:
            n = self.tokenize(text) if text else None
            self.tokenize_ok = bool(n)
            self._cpt = (len(text) / n) if n else FALLBACK_CPT
        return self._cpt

    def props(self):
        try:
            with urllib.request.urlopen(self.base + "/props", timeout=10) as r:
                d = json.loads(r.read())
            return (d.get("default_generation_settings") or {}).get("n_ctx"), d.get("build_info")
        except Exception:
            return None, None

    def chat(self, prompt, timeout=3600):
        """One answer AFTER the whole document.

        Delivery: /v1/chat/completions with cache_prompt=False. Verified on b11517
        (suite/run/ctx_cache_repro.py): with the slot prompt cache enabled, the SECOND long
        prompt sharing our haystack prefix is silently answered from the cached tail
        (timings.prompt_n == 4, cache_n == 30108) and the model answers the PREVIOUS
        question. cache_prompt=False forces full processing every time (prompt_n == 30104).
        """
        cap = cap_for(0)
        payload = {"messages": [{"role": "user", "content": prompt}], "temperature": 0.0,
                   "stream": False, "seed": SEED, "max_tokens": cap,
                   "n_predict": cap, "cache_prompt": False}
        body = self._post("/v1/chat/completions", payload, timeout)
        ch = (body.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        content = msg.get("content") or ""
        if not content.strip():
            content = msg.get("reasoning_content") or ""
        tim = body.get("timings") or {}
        return {"content": content, "prompt_n": tim.get("prompt_n") or 0,
                "prompt_ms": tim.get("prompt_ms") or 0,
                "finish_reason": ch.get("finish_reason")}


# ------------------------------------------------------------------ scoring
_BOXED = re.compile(r"\\boxed\{\s*\(?([ABCD])\)?\s*\}")
_ANS = re.compile(r"answer\s*(?:is|:)\s*\**\s*\(?([ABCD])\b", re.I)
_LETTER = re.compile(r"\b([ABCD])\b")


def extract_letter(txt):
    """Identical rule to the cell-1 scorer (score_pack.extract_letter)."""
    m = _BOXED.search(txt or "")
    if m:
        return m.group(1).upper()
    m = _ANS.search(txt or "")
    if m:
        return m.group(1).upper()
    ms = _LETTER.findall(txt or "")
    return ms[-1] if ms else None


# ------------------------------------------------------------------ prompt build
def item_text(r):
    opts = "\n".join(f"{'ABCD'[i]}) {c}" for i, c in enumerate(r["choices"]))
    return r["question"] + "\n\nChoices:\n" + opts


ASK = ("\n\nDocument ends. Answer the question that appeared 3 times in the document above. "
       "Think step by step. Finish with a line 'Answer: <letter>' where <letter> is "
       "A, B, C or D.")


def build_prompt(hay, body, target_tokens, cpt):
    """Plant `body` at each depth in DEPTHS %, then ask once at the end.

    Returns (prompt, placements) where placements are (depth, byte_offset).
    """
    need = max(0, int(target_tokens * cpt) - len(body) * len(DEPTHS) - len(ASK) - 64)
    doc = (hay * (need // max(1, len(hay)) + 1))[:need]
    cuts = [int(len(doc) * d / 100.0) for d in DEPTHS]
    pieces, prev, marks = [], 0, []
    for d, c in zip(DEPTHS, cuts):
        pieces.append(doc[prev:c])
        marks.append((d, sum(len(p) for p in pieces)))
        pieces.append("\n\n" + body + "\n\n")
        prev = c
    pieces.append(doc[prev:])
    pieces.append(ASK)
    return "".join(pieces), marks


# ------------------------------------------------------------------ cell
def emit(cid, task, acc, n, dur, metrics, notes=""):
    return {"id": cid, "task": task, "acc": round(float(acc), 4) if acc is not None else None,
            "metric": "acc", "samples": n, "duration_s": int(dur), "n_a": acc is None,
            "reason": "" if acc is not None else notes, "metrics": metrics}


def run_cell(cell, n=None, base="http://127.0.0.1:8081"):
    cid, target = CELLS[cell]
    t0 = time.time()
    hay, fsha, rebuilt = ensure_filler()
    rows = gpqa_rows(n)
    srv = Srv(base)
    n_ctx, build = srv.props()
    cpt = srv.calibrate(hay)
    tok_avail = bool(srv.tokenize_ok)

    detail, ok, fails = [], 0, 0
    prompt_toks, prefill_ms, est = [], 0.0, []
    binding = None
    for r in rows:
        body = item_text(r)
        prompt, marks = build_prompt(hay, body, target, cpt)
        est_tok = len(prompt) / cpt
        est.append(est_tok)
        try:
            resp = srv.chat(prompt)
        except Exception as e:  # transport / server death
            msg = str(e)[:200]
            binding = "ctx-%dk-error" % (target // 1000)
            detail.append({"id": r["id"], "want": r["answer_letter"], "got": None, "ok": False,
                           "prompt_tokens": None, "error": msg, "depths": [d for d, _ in marks]})
            fails += 1
            break
        ptok = resp["prompt_n"]
        prompt_toks.append(ptok)
        prefill_ms += resp["prompt_ms"]
        got = extract_letter(resp["content"])
        good = got == r["answer_letter"]
        # Truncation = the server only processed a fraction of what we sent (cache thrash or
        # window). That is a HARNESS fault (n_a rung), never a model error -> not a 0.
        sent_est = est_tok / len(DEPTHS)
        truncated = bool(ptok < 0.8 * sent_est)
        if truncated:
            binding = "ctx-%dk-cache" % (target // 1000)
            detail.append({"id": r["id"], "want": r["answer_letter"], "got": got, "ok": False,
                           "prompt_tokens": ptok, "est_tokens": int(est_tok),
                           "truncated": True, "finish_reason": resp["finish_reason"],
                           "depths": [d for d, _ in marks], "placements": marks,
                           "resp_tail": resp["content"][-200:]})
            fails += 1
            break
        ok += good
        detail.append({"id": r["id"], "want": r["answer_letter"], "got": got, "ok": good,
                       "prompt_tokens": ptok, "est_tokens": int(est_tok),
                       "truncated": truncated, "finish_reason": resp["finish_reason"],
                       "depths": [d for d, _ in marks], "placements": marks,
                       "resp_tail": resp["content"][-200:]})

    dur = time.time() - t0
    served = [d for d in detail if d.get("prompt_tokens")]
    ran = len(served)
    if binding and ran == 0:      # nothing usable -> n_a rung, keep previous rows
        cell_out = emit(cid, "gpqa-embedded-%dk" % (target // 1000), None, len(rows), dur,
                        {"target_ctx_tokens": target, "filler_sha256": fsha,
                         "binding_reason": binding, "n_ctx": n_ctx},
                        notes="%s: long-context rung not scoreable (%s); earlier rung kept"
                              % (binding, detail[-1].get("error", "prompt rejected")))
    else:
        acc = ok / ran if ran else None
        cell_out = emit(cid, "gpqa-embedded-%dk" % (target // 1000), acc, ran, dur,
                        {"correct": ok, "total": ran, "temp": 0.0,
                         "target_ctx_tokens": target,
                         "prompt_tokens_mean": int(sum(prompt_toks) / len(prompt_toks)) if prompt_toks else None,
                         "prompt_tokens_est_mean": int(sum(est) / len(est)) if est else None,
                         "token_calibration": "server /tokenize" if tok_avail else "frozen ratio",
                         "chars_per_token": round(cpt, 3),
                         "prefill_s_total": round(prefill_ms / 1000, 1),
                         "needle_depths_pct": list(DEPTHS),
                         "filler_sha256": fsha, "n_ctx": n_ctx, "llama_build": build})
        if binding:
            cell_out["metrics"]["binding_reason"] = binding
            cell_out["reason"] = ("%d/%d questions hit %s — counted failing, previous rung kept"
                                  % (fails, ran, binding))
    cell_out["metrics"]["filler_materialised"] = rebuilt
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(cell_out, open(os.path.join(RESULTS, cid + ".pub.json"), "w"), indent=1)
    json.dump(detail, open(os.path.join(RESULTS, cid + ".detail.json"), "w"), indent=1)
    print(json.dumps(cell_out))
    return cell_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", choices=sorted(CELLS))
    ap.add_argument("--n", type=int)
    ap.add_argument("--base", default=(os.environ.get("LLMBENCH_BASE") or os.environ.get("R97_BASE") or "http://127.0.0.1:8080"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        hay, fsha, wrote = ensure_filler()
        man = json.load(open(MANIFEST))["packs"]["ctx_filler.txt"]
        assert man["sha256"] == fsha, "manifest not updated"
        assert _sha(open(FILLER_TXT).read()) == fsha, "ctx_filler.txt drifted"
        assert man["sha256"] == _sha(hay), "haystack mutated"
        cpt = FALLBACK_CPT
        for t in (30000, 110000):
            p, marks = build_prompt(hay, item_text(gpqa_rows(1)[0]), t, cpt)
            depths = [round(m[1] / len(p) * 100) for m in marks]
            assert depths == list(DEPTHS), depths
            est = len(p) / cpt
            assert abs(est - t) / t < TOL, (t, est)
            print("ok target=%d est_tokens=%d depths=%s chars=%d" % (t, est, depths, len(p)))
        print(json.dumps({"filler_sha256": fsha, "rebuilt": wrote, "selftest": "pass"}))
        return 0
    if not a.cell:
        ap.error("--cell required (or --selftest)")
    run_cell(a.cell, a.n, a.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
