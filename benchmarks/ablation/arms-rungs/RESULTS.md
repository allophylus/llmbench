# Accelerator ablation at the matched context rungs

Generated: 2026-11-07 11:47 +0800

Same probe as the matched-context sweep: server restarted with `-c <rung>`, one
prompt calibrated with `/tokenize` to `rung - 512` tokens, ONE cold
`/v1/chat/completions` (temperature 0, `cache_prompt:false`, `ignore_eos`, 64
generated tokens). Cells are **decode t/s / prefill t/s** and, for non-baseline
arms, the change against that model's baseline at the same rung.

| model | arm | 4K | 32K | 64K | 128K | 256K |
|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B (Q4_K_M) | baseline | 106.6 / 3157 | 96.9 / 2435 | 90.5 / 1678 | 78.8 / 1018 | 62.5 / 563 |
|  | FA off (f16 KV) | 106.2 / 3236 (no change / +3%) | 88.2 / 2335 (-9% / -4%) | 68.5 / 66 (-24% / -96%) | — | — |
| Qwen3.8-27B (Q4_K_M) | baseline | 30.8 / 854 | 28.6 / 681 | 26.5 / 528 | 23.2 / 365 | 18.6 / 226 |
|  | FA off (f16 KV) | 30.6 / 834 (-1% / -2%) | 25.6 / 76 (-10% / -89%) | 21.6 / 24 (-19% / -95%) | — | does not fit |
|  | MTP n-max 7 | 90.1 / 734 (+193% / -14%) | 68.5 / 630 (+139% / -7%) | 55.8 / 499 (+110% / -6%) | 43.5 / 349 (+88% / -5%) | 28.6 / 216 (+54% / -4%) |
|  | DFlash n-max 7 | 95.1 / 690 (+209% / -19%) | 60.4 / 622 (+111% / -9%) | 47.6 / 496 (+80% / -6%) | 42.2 / 350 (+82% / -4%) | 28.7 / 219 (+54% / -3%) |

Cells marked `does not fit` are configurations whose server refused to start at that window; they are recorded, not substituted.

A dash is a cell that was not run. The FA-off arms stop at 64K on both models:
non-FA prefill had already collapsed there (24 t/s dense, 66 t/s MoE), so the
next rung is a multi-hour cell, and on the dense model the 256K f16 KV window
does not allocate at all.

