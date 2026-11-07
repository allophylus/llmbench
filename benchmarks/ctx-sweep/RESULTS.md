# Matched-context sweep — R9700 32 GiB, llama.cpp Vulkan

Generated: 2026-11-08 01:15 +0800

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
| Gemma 4 26B-A4B (UD-Q4_K_M) | 2706.0 / 94.98 | 2291.7 / 80.25 | 1577.0 / 72.26 | 940.6 / 62.8 | 509.2 / 47.77 | 256K |  |
| Nanbeige 4.3-33B (Q4_K) | 738.1 / 28.03 | 375.9 / 22.7 | 238.5 / 18.59 | 138.4 / 13.74 | 52.3 / 2.66 | 256K |  |

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
| gemma-4-26b-a4b-ud-q4-k-m | 4096 | 3597 | 2706.0 | 1.3 | 94.98 | 64 | length | 16.69 |
| gemma-4-26b-a4b-ud-q4-k-m | 32768 | 32261 | 2291.7 | 14.1 | 80.25 | 64 | length | 17.18 |
| gemma-4-26b-a4b-ud-q4-k-m | 65536 | 65025 | 1577.0 | 41.2 | 72.26 | 64 | length | 17.56 |
| gemma-4-26b-a4b-ud-q4-k-m | 131072 | 130570 | 940.6 | 138.8 | 62.8 | 64 | length | 18.32 |
| gemma-4-26b-a4b-ud-q4-k-m | 262144 | 261635 | 509.2 | 513.8 | 47.77 | 64 | length | 19.84 |
| nanbeige-4-3-33b-q4-k | 4096 | 3622 | 738.1 | 4.9 | 28.03 | 64 | length | 19.19 |
| nanbeige-4-3-33b-q4-k | 32768 | 32308 | 375.9 | 86.0 | 22.7 | 64 | length | 21.61 |
| nanbeige-4-3-33b-q4-k | 65536 | 65092 | 238.5 | 272.9 | 18.59 | 64 | length | 24.38 |
| nanbeige-4-3-33b-q4-k | 131072 | 130660 | 138.4 | 944.3 | 13.74 | 64 | length | 29.91 |
| nanbeige-4-3-33b-q4-k | 262144 | 261796 | 52.3 | 5001.2 | 2.66 | 64 | length | 31.85 |

## Failures

None — every cell measured.

## Artifacts

* `sweep.json` — full machine-readable sweep
* `<slug>.json` — one file per model
* `state.json` — resumable state (checkpointed per cell)

