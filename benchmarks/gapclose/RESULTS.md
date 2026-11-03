# Gap-close campaign — results

Campaign against llmbench coverage gaps, host the GPU host (R9700 32 GiB, llama.cpp
Vulkan b11517-8a1a9b512, prod unit qwen-longctx :8080). Started 2026-11-03.

## STEP 1 — A3B 256K standard speed (was pending=true)

Method: standard ~30K probe (BENCHMARK.md §4 + a3b_ctx_run3), server A3B at -c 262144, temp 0,
cache_prompt false, token-calibrated prompt (29,953 calibrated / 29,963 actual). 1 cold run.

| metric | value |
|---|---|
| prefill | 2480.1 t/s (12,081 ms) |
| decode | 98.19 t/s (predicted_n 64, finish_reason length) |
| VRAM idle | 24.83 GiB |
| VRAM peak | 24.89 GiB |
| n_ctx | 262144 |

This is a *real* 64-token decode (not EOS-truncated), so it replaces `pending: true`.
Pre-deep-probe measured std numbers at 256K: prefill 566.0 / decode 62.31 are at 260K depth;
this 30K-at-256K-window number is the "standard" row. Note the A3B 256K standard decode
(98.19) ≈ 32K standard decode (98.13) — the window size does not cost decode at 30K prompt
depth, as expected (KV attention cost is depth- not window-proportional).

## STEP 2 — error bars (3 reps each)

All spreads below 5% except where noted. The single-run numbers in the table are therefore
reliable to within ~±2% for A3B, but Qwen3.8-27B decode needs the /completion method (its
chat answer stops at "DONE" after 2 tokens — not a decode measurement).

### A3B 32K
| metric | mean | min | max | spread |
|---|---|---|---|---|
| prefill t/s | 2480.7 | 2470.9 | 2488.2 | 0.70% |
| decode t/s | 98.01 | 97.04 | 98.63 | 1.62% |
| wall s | 12.73 | 12.7 | 12.8 | 0.79% |
| VRAM idle/peak | 22.17 / 22.24 GiB | | | |

### A3B 256K
| metric | mean | min | max | spread |
|---|---|---|---|---|
| prefill t/s | 2477.1 | 2468.4 | 2490.0 | 0.87% |
| decode t/s | 98.20 | 98.12 | 98.33 | 0.21% |
| wall s | 12.77 | 12.7 | 12.8 | 0.78% |
| VRAM idle/peak | 24.89 / 24.89 GiB | | | |

### Qwen3.8-27B Q4_K_M (32K window)
| metric | mean | min | max | spread |
|---|---|---|---|---|
| prefill t/s | 687.63 | 685.7 | 690.3 | 0.67% |
| decode t/s | (25.93 — INVALID, predicted_n=2) | | | |

> **decode spread note:** the chat probe returns `predicted_n=2` (finish_reason stop, answer
> "DONE") for Qwen3.8-27B, which BENCHMARK.md §4 calls noise not a decode measurement. A real
> decode number comes from `/completion` ignore_eos n_predict=400 (see qwen38-27b-decode-x3.json).
> The 4.63% spread on that 2-token figure is meaningless; disregard it.

---

## Raw records — reproduced here so every number can be re-derived

### a3b-ctx256k-x3.json (3 identical cold reps — error-bar source for A3B @ 256K)

```json
{
 "label": "a3b-ctx256k-x3",
 "base": "local server",
 "model_path": "<served model>",
 "build_info": "b11517-8a1a9b512",
 "target_tokens": 30000,
 "tokens_calibrated": 29953,
 "calibration": {
  "units": 4,
  "tail_chars": 2613,
  "unit_tokens": 7340,
  "unit_chars": 30000,
  "err": 0.00157
 },
 "max_tokens": 64,
 "temperature": 0,
 "cache_prompt": false,
 "n_ctx": 262144,
 "when": "2026-11-03T10:06:48+0000",
 "vram_idle_gib": 24.89,
 "runs": [
  {"rep": 1, "wall_s": 12.7, "prompt_n": 29963, "predicted_n": 64, "prefill_ms": 12033.5, "prefill_tps": 2490.0, "decode_ms": 642.0, "decode_tps": 98.14, "cached_tokens": 0, "finish_reason": "length", "content_head": ""},
  {"rep": 2, "wall_s": 12.8, "prompt_n": 29963, "predicted_n": 64, "prefill_ms": 12116.7, "prefill_tps": 2472.9, "decode_ms": 640.7, "decode_tps": 98.33, "cached_tokens": 0, "finish_reason": "length", "content_head": ""},
  {"rep": 3, "wall_s": 12.8, "prompt_n": 29963, "predicted_n": 64, "prefill_ms": 12138.6, "prefill_tps": 2468.4, "decode_ms": 642.1, "decode_tps": 98.12, "cached_tokens": 0, "finish_reason": "length", "content_head": ""}
 ],
 "vram_peak_gib": 24.89,
 "vram_tail_gib": 24.89,
 "vram_samples": 45,
 "summary": {
  "prefill_tps": {"mean": 2477.1, "min": 2468.4, "max": 2490.0, "spread_pct": 0.87, "n": 3},
  "decode_tps":  {"mean": 98.2,   "min": 98.12,  "max": 98.33,  "spread_pct": 0.21, "n": 3},
  "wall_s":      {"mean": 12.77,  "min": 12.7,   "max": 12.8,   "spread_pct": 0.78, "n": 3}
 }
}
```
