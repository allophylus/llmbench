# Weight-Space-Programming Qwen3.8-27B — does the edit survive Q4_K_M?

Measured 7 November 2026 on the R9700 (32 GiB), llama.cpp Vulkan `b11517`, one model on the card
at a time. Page: `benchmarks/wsp/index.html`.

## What the release claims

`ReBatch/Qwen3.8-27B-Weight-Space-Programming` (Apache-2.0, base `Qwen/Qwen3.8-27B` at revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`) states that it changed **19,680,881 stored BF16
weights — about 0.071% of 27.78B parameters — all inside one tensor**,
`model.language_model.layers.29.mlp.down_proj.weight`, in 4,096 of its 17,408 input columns, with
patch identifier `repair-joint-quantwide-l29-a12` and a stored perturbation L2 norm of
**7.4606041947214665**. The claimed effect is on **CCPBench-A**: mean bias **2.714 → 1.518**
over all 500 questions (1 = no detectable bias, 5 = severe), judged by `gpt-6.1-terra`.
The card is explicit that capability preservation is *not* claimed, and that the model does not
claim a score at or below 1.50.

The much-quoted "MATH-500 7.9% → 48.1%" figure from the *Sparks of Weight-Space Programming*
write-up belongs to a different model (Qwen3.5-0.8B) and a different experiment; it does not
describe this release, and this page does not test that claim.

## What we found

**1. The edit is in the file, at the documented size.**

| tensor | ‖D‖_F | σ₁ | σ₂ | σ₁/σ₂ |
|---|---:|---:|---:|---:|
| `blk.29.ffn_down` (edited) | 13.69 | **7.438** | 0.505 | 14.7 |
| `blk.27.ffn_down` (control) | 8.69 | 0.424 | 0.195 | 2.2 |
| `blk.29.ffn_gate` (control) | 11.25 | 0.288 | 0.261 | 1.1 |

σ₁ of the dequantised difference is 7.438 against the documented 7.4606 — a 0.3% gap,
consistent with re-quantising the edited float32 weights to 4-bit. The controls, in the same
layer and neighbourhood, show no such low-rank component. **The edit survives Q4_K_M.**

**2. The local "Q4_K_M" baseline is not a uniform Q4_K_M file.** 417 of 866 tensors differ in
quantisation *type*: the baseline carries Q5_K (111), IQ4_XS (102), Q8_0 (101) and Q6_K (26)
tensors where the WSP file is uniform Q4_K/Q6_K. F32 tensors are bit-identical, so both files
do come from the same base weights. Consequence: the behavioural A/B below mixes the edit with
a precision difference, and this cannot be separated without re-quantising one checkpoint twice.

**3. Behaviour, same harness both arms** (`-c 32768`, thinking off, temperature 0/0.2):

| metric | baseline | WSP | Δ |
|---|---:|---:|---:|
| CCPBench-A mean, 30-question subset | 3.467 | **2.400** | −1.07 |
| … China-related (22 q) | 4.045 | **2.636** | −1.41 |
| … non-China control (8 q) | 1.875 | 1.750 | −0.12 |
| GPQA-25 (identical settings, 2048 cap) | 10/25 | 12/25 | +2 |
| MATH-500, first 20 items | 17/20 | 17/20 | 0 |
| Arithmetic set, 20 items | 20/20 | 20/20 | 0 |

The bias distribution moves in the tails: baseline `{1:5, 2:5, 3:1, 4:9, 5:10}` →
WSP `{1:11, 2:6, 3:6, 4:4, 5:3}`. WSP answers are also much longer (752 vs 365 completion
tokens on CCPBench), which is the main visible side effect.

**4. Speed** (standard probe, cold, one server):

| rung | baseline prefill / decode | WSP prefill / decode |
|---|---:|---:|
| 7.4K prompt, 3 reps | 838.3 / 30.16 | 771.5 / 30.05 |
| 129K prompt, 1 rep | 367.2 / 23.14 | 353.4 / 23.01 |

Decode is unchanged. Prefill is 4–8% lower — a single 0.07% tensor cannot cause that, and it
tracks the other structural difference between the files (the mixed-precision baseline).

## Caveats

- CCPBench scores come from `deepseek-chat` applying the official rubric to blinded responses,
  not `gpt-6.1-terra`. Absolute values are not comparable to the vendor's 2.714/1.518; the paired
  difference is the meaningful quantity. The 30-question subset (22 China / 8 control) was
  stratified by top-level topic with seed 5.
- GPQA ran with a 2048-token cap; WSP truncated on 13/25 and the baseline on 12/25, so the
  absolute accuracy is depressed for both. The paired +2 is inside the noise of a 25-question set.
- MATH-500 grading used a blinded reference-answer equivalence judge; the three baseline misses
  and three WSP misses are mostly answer-commitment failures at the token cap, not wrong algebra.

## Verdict

**Mixed-positive.** The weight edit demonstrably survives Q4_K_M quantisation and is present in
the published file at the claimed magnitude; the measured behaviour moves in the claimed
direction and by a large margin on the same questions, with no measurable damage to arithmetic
or MATH-500 and no decode penalty. It is *not* a clean single-variable experiment: the published
4-bit baseline differs from ours in precision, so the behavioural delta is an upper bound on
what the edit alone does. The only way to close that gap is to quantise the same base twice.

## Files

- `results.json` — every number above, machine-readable
- `DIFF.md` — full file-level diff report
- `raw/out/*.jsonl` — per-question answers, token counts, timings for both arms
- `raw/*.judged.json`, `raw/*.llmjudged.json` — judge outputs
- `bench_wsp.py`, `diff_gguf.py`, `svd_probe.py`, `judge_ccp.py`, `grade_math_llm.py`,
  `assemble_results.py`, `select_ccp.py`
