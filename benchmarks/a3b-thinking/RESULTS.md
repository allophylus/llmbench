# A3B thinking ON vs OFF — 2026-11-03

Same model, same server process, same flags for every pair:
`Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, `-c 32768`, temp 0.0, seed 5, GPQA-diamond 25 questions
from the frozen pack `suite/packs/gpqa25.jsonl`, prompt and scoring identical to cell
`pub-gpqa25` (`score_pack.extract_letter`). The only variable: per-request
`chat_template_kwargs.enable_thinking` (true / false).

## Results

| run | thinking | max_tokens | correct | correct % | completion tokens | avg tok/q | wall s | length-stops (no final answer) |
|---|---|---|---|---|---|---|---|---|
| A | off | 4096 | 19/25 | 76% | 61,409 | 2,456 | 584.0 | 6 |
| A | on | 4096 | 17/25 | 68% | 96,097 | 3,844 | 1,004.3 | **20** |
| B | off | 16384 | **22/25** | **88%** | 91,075 | 3,643 | 1,244.9 | 0 |
| B | on | 16384 | 18/25 | 72% | 300,352 | 12,014 | 4,338.8 | **12** |

Run B is the fair comparison (identical cap in both modes, no mode cut short at the cap:
off 0 length-stops; on 12/25 still exhausted 16 K).

* Thinking **costs** 3.3× the completion tokens and 3.5× the wall time at equal cap,
  and was **wrong more often**: 18 vs 22 of 25 correct (−4 questions, −16 pts).
* Avg 12,014 tokens/question with thinking on = mostly `reasoning_content`
  (869,551 reasoning chars across the 25; the thinking channel is where the budget goes).
  A 4096 cap cuts thinking off before it reaches an "Answer:" line on 20/25 questions —
  that is why cell 1 historically runs with thinking off.
* Per-question agreement: 18 of 25 answers are the same in both modes; thinking changed
  its answer on 7 questions and gained only 1 of those (net −4).
* Throughput is comparable single-stream (~69–73 t/s in run B) — the cost is token count,
  not speed.

## Files

* `pair-cap4096.json`, `pair-cap16384.json` — per-question record (content tail, extracted
  letter, correctness, completion tokens, reasoning chars, wall, prefill/decode t/s,
  finish reason).
* `think_pair.py` — harness. `pair16384.log` — run log.
* `summary.json` — the four rows above as machine-readable records.

Note on scoring: a thinking-mode answer that hits the cap without printing "Answer: X" is
recorded as unanswered (correct=false, finish_reason=length), never retried.
