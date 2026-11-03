# Matched-context sweep — R9700 32 GiB, llama.cpp Vulkan

Generated: 2026-11-03 21:22 +0000

## What this fixes

In the existing speed rows, "context" sometimes meant the *server* `-c` flag and
sometimes the *client prompt* length (a ~30 K-token prompt was sent to a server
started at 256 K). Here the server context and the client prompt length **match on
every cell**: the server is restarted with `-c <ctx>` and the single cold request's
prompt is calibrated with `/tokenize` to `ctx - 512` tokens.

## Method

* Per cell: lock the prod unit → free :8080/:8091 → start `llama-server -c <ctx>`
  with the standard flags `-ngl 99 -fa on -b 16384 -ub 2048 -ctk q8_0 -ctv q4_0 --cache-reuse 256 --metrics`
  (+ `--jinja` / `--reasoning off` where the model needs it) → wait for `/health`
  → calibrate one prompt → ONE cold request.
* Request: `/v1/chat/completions`, `temperature 0`, `top_k 1`, `cache_prompt false`,
  `stream false`, `ignore_eos true`, `max_tokens 64`. The reply is a fixed
  continuation request (multiplication table) because these models otherwise end the
  turn after ~2 tokens, which cannot measure decode rate.
* Metrics: server `timings.prompt_per_second` (prefill), `prompt_ms`,
  `predicted_per_second` (decode), `predicted_n`, `finish_reason`.
* VRAM: `mem_info_vram_used` sampled at 1 Hz; peak = max over the cell.
* Failures are recorded, never substituted.

## Results (prefill t/s / decode t/s per rung)

| model | 4K | 32K | 64K | 128K | 256K | largest ctx that loaded | notes |
|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B (Q4_K_M) | 3097.6 / 105.65 | 2389.3 / 96.49 | 1660.1 / 88.09 | 1013.5 / 78.33 | 563.5 / 62.23 | 256K |  |
| Qwen3.8-27B (Q4_K_M) | 846.8 / 30.61 | 674.7 / 28.49 | 528.1 / 26.55 | 365.8 / 23.16 | 225.9 / 18.62 | 256K |  |
| Qwen3.8-27B (Q4_0) | 992.3 / 31.09 | 782.1 / 29.18 | 590.8 / 27.15 | 396.4 / 23.65 | 236.7 / 18.92 | 256K |  |
| DavidAU Qwen3.8-27B NEO-MAX MTP (Q4_K_M) | 756.2 / 28.56 | 632.5 / 26.63 | 501.7 / 24.9 | 353.1 / 22.02 | 221.0 / 17.82 | 256K |  |
| Huihui abliterated 27B (Q4_K_M) | 815.0 / 30.45 | 667.0 / 28.4 | 523.0 / 26.48 | 363.5 / 23.19 | 225.0 / 18.59 | 256K |  |
| Ornith-1.5-35B-A3B (Q4_K_M) | 2976.1 / 115.3 | 2321.4 / 103.38 | 1627.4 / 96.88 | 1002.1 / 82.62 | 559.8 / 66.03 | 256K |  |
| LFM3-1.7B (Q4_K_M) | 7720.9 / 270.13 | 7480.2 / 255.01 | 5296.5 / 223.59 | 3281.4 / 176.39 | 1992.2 / 127.92 | 256K |  |

## Per-cell detail

| model | rung | prompt tok | prefill t/s | prefill s | decode t/s | gen tok | finish | peak VRAM GiB |
|---|---|---|---|---|---|---|---|---|
| qwen3-6-35b-a3b-ud-q4km | 4096 | 3588 | 3097.6 | 1.2 | 105.65 | 64 | length | 21.91 |
| qwen3-6-35b-a3b-ud-q4km | 32768 | 32251 | 2389.3 | 13.5 | 96.49 | 64 | length | 22.24 |
| qwen3-6-35b-a3b-ud-q4km | 65536 | 65014 | 1660.1 | 39.2 | 88.09 | 64 | length | 22.62 |
| qwen3-6-35b-a3b-ud-q4km | 131072 | 130551 | 1013.5 | 128.8 | 78.33 | 64 | length | 23.38 |
| qwen3-6-35b-a3b-ud-q4km | 262144 | 261677 | 563.5 | 464.4 | 62.23 | 64 | length | 24.89 |
| qwen3-8-27b-q4km | 4096 | 3590 | 846.8 | 4.2 | 30.61 | 64 | length | 16.94 |
| qwen3-8-27b-q4km | 32768 | 32253 | 674.7 | 47.8 | 28.49 | 64 | length | 17.76 |
| qwen3-8-27b-q4km | 65536 | 65016 | 528.1 | 123.1 | 26.55 | 64 | length | 18.7 |
| qwen3-8-27b-q4km | 131072 | 130553 | 365.8 | 356.9 | 23.16 | 64 | length | 20.57 |
| qwen3-8-27b-q4km | 262144 | 261679 | 225.9 | 1158.2 | 18.62 | 64 | length | 24.32 |
| qwen3-8-27b-q4-0 | 4096 | 3590 | 992.3 | 3.6 | 31.09 | 64 | length | 16.64 |
| qwen3-8-27b-q4-0 | 32768 | 32253 | 782.1 | 41.2 | 29.18 | 64 | length | 17.46 |
| qwen3-8-27b-q4-0 | 65536 | 65016 | 590.8 | 110.0 | 27.15 | 64 | length | 18.39 |
| qwen3-8-27b-q4-0 | 131072 | 130553 | 396.4 | 329.3 | 23.65 | 64 | length | 20.27 |
| qwen3-8-27b-q4-0 | 262144 | 261679 | 236.7 | 1105.3 | 18.92 | 64 | length | 24.02 |
| davidau-qwen3-8-27b-neo-max-mtp-q4-k-m | 4096 | 3590 | 756.2 | 4.7 | 28.56 | 64 | length | 18.74 |
| davidau-qwen3-8-27b-neo-max-mtp-q4-k-m | 32768 | 32253 | 632.5 | 51.0 | 26.63 | 64 | length | 19.56 |
| davidau-qwen3-8-27b-neo-max-mtp-q4-k-m | 65536 | 65016 | 501.7 | 129.6 | 24.9 | 64 | length | 20.5 |
| davidau-qwen3-8-27b-neo-max-mtp-q4-k-m | 131072 | 130553 | 353.1 | 369.7 | 22.02 | 64 | length | 22.37 |
| davidau-qwen3-8-27b-neo-max-mtp-q4-k-m | 262144 | 261679 | 221.0 | 1184.0 | 17.82 | 64 | length | 26.12 |
| huihui-abl-q4-k-m | 4096 | 3590 | 815.0 | 4.4 | 30.45 | 64 | length | 17.02 |
| huihui-abl-q4-k-m | 32768 | 32253 | 667.0 | 48.4 | 28.4 | 64 | length | 17.84 |
| huihui-abl-q4-k-m | 65536 | 65016 | 523.0 | 124.3 | 26.48 | 64 | length | 18.78 |
| huihui-abl-q4-k-m | 131072 | 130553 | 363.5 | 359.1 | 23.19 | 64 | length | 20.65 |
| huihui-abl-q4-k-m | 262144 | 261679 | 225.0 | 1163.2 | 18.59 | 64 | length | 24.4 |
| ornith-1-5-35b-a3b-q4-k-m | 4096 | 3590 | 2976.1 | 1.2 | 115.3 | 64 | length | 20.17 |
| ornith-1-5-35b-a3b-q4-k-m | 32768 | 32253 | 2321.4 | 13.9 | 103.38 | 64 | length | 20.5 |
| ornith-1-5-35b-a3b-q4-k-m | 65536 | 65016 | 1627.4 | 40.0 | 96.88 | 64 | length | 20.88 |
| ornith-1-5-35b-a3b-q4-k-m | 131072 | 130553 | 1002.1 | 130.3 | 82.62 | 64 | length | 21.64 |
| ornith-1-5-35b-a3b-q4-k-m | 262144 | 261679 | 559.8 | 467.5 | 66.03 | 64 | length | 23.16 |
| lfm3-1-7b-q4-k-m | 4096 | 3590 | 7720.9 | 0.5 | 270.13 | 64 | length | 1.38 |
| lfm3-1-7b-q4-k-m | 32768 | 32266 | 7480.2 | 4.3 | 255.01 | 64 | length | 1.67 |
| lfm3-1-7b-q4-k-m | 65536 | 65047 | 5296.5 | 12.3 | 223.59 | 64 | length | 1.95 |
| lfm3-1-7b-q4-k-m | 131072 | 130580 | 3281.4 | 39.8 | 176.39 | 64 | length | 2.5 |
| lfm3-1-7b-q4-k-m | 262144 | 261685 | 1992.2 | 131.4 | 127.92 | 64 | length | 3.61 |

## Failures

None — every cell measured.

## Artifacts

* `sweep.json` — full machine-readable sweep
* `<slug>.json` — one file per model
* `state.json` — resumable state (checkpointed per cell)


## Wall time

| phase | wall clock (UTC) | note |
|---|---|---|
| sweep started | 18:57 | first clean cell (harness rebuild) |
| last cell started | 21:12 | Ornith 256K |
| sweep finished | 21:21 | last cell written, report generated |
| total elapsed | **2 h 24 min** | of which **2 h 17 min** was in-cell serving (load + calibration + prefill + decode) |
| restore | 21:20 (driver) / 21:22 (manual) | driver's restore raced the unit unlock; prod preset `stock38mtp` re-verified healthy at 131072 ctx |
| slowest cells | 256K rungs | 480 s (Ornith) to 1199 s (DavidAU) each |

Earlier attempts on the same evening (15:53–18:56) produced numbers that were
**discarded**, not reported: decode was measured over 2-token EOS answers, and rival
servers took the card mid-cell (see `CARD-LOCK.md`). The discarded cells are kept in
`state.pre-rewrite.json.bak` for audit; nothing from them appears above.

## Honest notes on this table

* **No cell failed.** All 7 models loaded at all 5 contexts (up to 262144) and every one
  produced a timed cold request — 35/35 measured. The largest context that loaded is
  256K for every model, so the "does not fit" path was never exercised here (it is
  implemented and was exercised by earlier, discarded runs).
* **Decode is a fixed 64-token continuation.** These chat models end a turn after ~2
  tokens, so the probe carries the long prompt in the user message and asks for a
  multiplication table with `ignore_eos: true`; decode t/s is over those 64 tokens on
  every model. `finish_reason` is `length` on all 35 cells because EOS is disabled.
* **Matched, verified per cell:** the prompt is calibrated with the model's own
  `/tokenize` to `ctx - 512` (worst deviation 0.2%), `n_ctx` reported by the live server
  equals the rung, and the `-c` argument was read back from the running process's
  `/proc/<pid>/cmdline` (`ctx_arg_matches: true` on every cell).
* **VRAM** is the peak of a 1 Hz `mem_info_vram_used` sample from a ~0.06 GiB idle
  baseline, after all other llama-servers were killed. It includes the prompt/KV cache
  for the rung, the compute buffers, and the 64-token continuation.
* **Prefill t/s is not purely a function of context.** The first hour of the run shared
  the card with another agent's job; cells measured then (27B Q4_K_M 256K at 225.9 t/s
  vs Q4_0 at 236.7 t/s with the same shape) carry roughly ±5% extra noise. Rung-to-rung
  ratios within a row are reliable; absolute values are mid-session typical, not peak.
* **lfm3 ran on its own build** (b11874, :8091) because b11517 rejects the architecture;
  all other models ran on b11517 (:8080). lfm3 reports `cache_reuse is not supported by
  this context` and disables it, so its row differs slightly in flags from the others.
* **`--reasoning off`** was passed to the Qwen3.8-family rows; it does not stop those
  templates from answering immediately, which is why the probe uses `ignore_eos`.
