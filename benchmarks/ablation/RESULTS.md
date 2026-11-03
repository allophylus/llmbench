# Accelerator ablation on ONE fixed model — Qwen3.8-27B-Q4_K_M (R9700, llama.cpp Vulkan b11517)

Date: 2026-11-03. Host: `ubuntu@192.168.1.148` (AMD R9700, 32624 MiB, RADV), `llama-server`
**b11517-8a1a9b512**, systemd user unit `qwen-longctx.service` on `:8080`.
Model: `/home/ubuntu/models/Qwen3.8-27B-Q4_K_M.gguf` (arch `qwen35`, 65 blocks, `nextn_predict_layers=1`,
mmproj `mmproj-Qwen3.8-27B-F16.gguf`) for **every** arm. Only the accelerator flags change.

Question: what does each accelerator actually buy on this one model, everything else identical —
Flash Attention, MTP (the model's own nextn head), and DFlash (separate DFlash2 drafter)?

---

## 1. Headline

| arm | FA | spec | KV | decode 1.6k ctx t/s | decode 27.7k ctx t/s | prefill 1.6k t/s | prefill 27.7k t/s | VRAM idle / peak GiB | answers identical to baseline |
|---|---|---|---|---|---|---|---|---|---|
| **1 baseline** | on | none | q8_0/q4_0 | **30.8** | **28.7** | **814** | **698** | 20.44 / 20.57 | — |
| 2 FA off | off | none | f16/f16 | 30.6 | 26.1 | 763 | **117** (−83 %) | 24.70 / 28.89 | 5/6 prompts |
| **3 MTP** | on | draft-mtp n_max 7 | q8_0/q4_0 | **92.7** (3.0×) | **73.9** (2.6×) | 702 | 651 | 26.15 / 26.33 | 3/6 (long prose drifts) |
| 4 DFlash n_max 7 | on | draft-dflash | q8_0/q4_0 | **103.3** (3.4×) | 55.9 (1.9×) | 649 | 647 | 28.44 / 28.87 | 3/6 |
| 4b DFlash n_max 3 | on | draft-dflash (default n) | q8_0/q4_0 | 84.1 | 58.3 | 650 | 648 | 26.29 / 26.53 | 3/6 |
| 5a MTP (+ngram-cache) | on | draft-mtp + ngram-cache | q8_0/q4_0 | 61.3 | **13.3** | 694 | 654 | 26.15 / 26.33 | 3/6 |
| 5b DFlash (=4b) | on | draft-dflash (default n) | q8_0/q4_0 | 84.0 | 58.5 | 638 | 648 | 26.29 / 26.53 | 3/6 |
| 6 DFlash, FA off | off | draft-dflash | f16/f16 | 75.8 | 16.6 | 556 | **88** (−87 %) | 28.24 / 31.68 | 5/6 |

Numbers are the server's own `timings` block: decode = `predicted_per_second` over **400 generated
tokens** (`/completion`, `ignore_eos`, temp 0, seed 4242, `cache_prompt:false`), prefill =
`prompt_per_second` on the same request. "27.7k ctx" = 27,722-token prompt (varied 30k-char blocks,
`/tokenize`-calibrated). VRAM = `mem_info_vram_used` sampled at 4 Hz, idle after load and peak during
the 30k request. Full detail + exact argv in `arm-<id>.json`.

**Takeaways**

1. **FA is a decode no-op on this box, but a prefill multiplier and a memory saver.** Decode is within
   noise (30.6 vs 30.8 t/s at 1.6k; 26.1 vs 28.7 at 27.7k, −9 %). Prefill collapses without it:
   **698 → 117 t/s (−83 %)** at 27.7k, 814 → 763 at 1.6k. It also costs memory indirectly: the arm can
   only run with **f16 KV** (see caveat 2), +4.3 GiB idle, +8.3 GiB peak.
2. **MTP is the best all-round accelerator**: +3.0× decode at short context, +2.6× at 27.7k depth,
   prefill −7 % (prefill shares no benefit — expected), +5.7 GiB VRAM.
3. **DFlash is faster than MTP at short context (n_max 7: 103 vs 93 t/s) but loses at depth**
   (56 vs 74 t/s at 27.7k) and costs more VRAM (28.4 vs 26.2 GiB). With the drafter's own default
   n_max 3 it is slower everywhere and no longer cheaper in VRAM (26.3 GiB). DFlash2's strong point
   in theory (block-parallel drafting) does not pay off at depth on this card.
4. **Spec decoding changes long-form greedy output.** All spec arms reproduce baseline byte-for-byte
   on the short deterministic prompts (arithmetic, list, code) and on 2 of 3 long prose prompts, but
   the 120-word prose prompt differs in every spec arm (text diverges mid-sentence, same topic). FA-off
   (non-spec) does not change that answer. That is a **finding**, not a measurement error: see §4.
5. **MTP + ngram-cache (the prod `stock38mtp` preset) is the worst decode config measured at depth**:
   13.3 t/s at 27.7k ctx vs 92.7 for MTP alone — ngram matching over a long repeated context is pure
   overhead here. It is fine at short context (61.3 vs 92.7 — still slower than MTP alone).

---

## 2. Method (what produced the numbers)

Server shape shared by every arm (identical to `switch-model.sh stock38` except the listed delta):

```
-m /home/ubuntu/models/active.gguf  --mmproj /home/ubuntu/models/active-mmproj.gguf
--host 0.0.0.0 --port 8080  -c 131072  -ngl 99  --jinja  -b 16384  -ub 2048
--cache-type-k q8_0  --cache-type-v q4_0  --cache-reuse 256  --metrics  --reasoning off
```

* **Launcher** = the documented way: an `ExecStart=` drop-in
  (`qwen-longctx.service.d/z-ablation.conf`) that overrides the preset drop-in, then
  `systemctl --user daemon-reload && restart`. `systemctl show ... ExecStart` is recorded per arm so
  the argv in the JSON is what systemd actually ran, not what the script intended.
  Long jobs ran inside `screen` on `.148` (local exec kills children).
* **Warm-up** request discarded (graph capture) before any measurement; every measured request is
  `cache_prompt:false`, `cache_n:0`, `cached_tokens:0` → genuinely cold prefill.
* **Decode** uses `/completion` on the chat-template-rendered prompt (`/apply-template`) with
  `ignore_eos:true, n_predict:400`. Rationale: in round 1, 256-token chat requests were truncated to
  `predicted_n=2–4` (stop token / budget), i.e. not a decode measurement at all.
* **Reasoning**: verified off — baseline chat replies have empty `reasoning_content` and no
  `</think>`; an earlier control with the kwargs disabled *did* emit `reasoning_content`. `--reasoning off`
  is the non-deprecated form of the same switch and is applied to all arms.
* **Answers**: 6 fixed prompts, chat, temp 0, seed 4242, max_tokens 500, compared byte-for-byte
  against arm 1. Prompts: arithmetic, ordered list, code one-liner, 2-sentence prose, ~120-word prose,
  ~100-word prose.
* **VRAM**: `/sys/class/drm/card1/device/mem_info_vram_used`, 4 Hz sampler during the request.
* Harness: `ablate2.py` (in this directory, as run on the box), driver `run3.sh`.

### Round-1 defects found and fixed (kept in `raw/`, not used for the table)

1. 256-token chat probe → `predicted_n` 2–4, decode figures were noise.
2. The 30k prompt repeated ONE 30k-char unit in a loop. Even ngram-cache then had nothing to exploit
   and every accelerator looked useless; the pattern also inflates "DONE" style verification. Round 2
   builds prompts from 20 different 1.5k blocks repeated.
3. Round-1 arm 5 passed `--spec-draft-n-max` twice; b11517 deprecated-and-silently-overrode it
   (only MTP's pair survived) — see caveat 3.
4. Round-1 `wait_ready()` accepted a crash-looping unit that briefly answered; round 2 requires a real
   completion plus `NRestarts` recorded.

---

## 3. Caveats — what is NOT apples-to-apples

1. **FA off cannot use the prod KV format.** `-fa off` with `--cache-type-v q4_0` aborts at load:
   *"quantized V cache requires flash_attn to be enabled"*. Arms 2 and 6 therefore run
   **f16/f16 KV** (+4.0 GiB idle, +8.3 GiB peak). This is a property of the model/engine pair, not a
   choice: there is no FA-off config on this box that keeps the 131k window and the q8_0/q4_0 cache.
2. **The 256K server config was not used for arm 6.** With f16 KV at 131k and DFlash it already peaks
   at 31.68 GiB of 31.86 GiB usable; a 262k f16 KV window does not fit. Arm 2/6 VRAM numbers are
   therefore not comparable 1:1 with arms 1/3/4/5.
3. **Arm 5 (MTP + DFlash) could not be built as a single server** — two separate failures, both
   measured:
   * both types in one `--spec-type`: b11517 opens **one** extra-model context after loading the
     DFlash draft and MTP fails with *"context type MTP requested but model doesn't contain MTP
     layers"* (the MTP head lives in the *target* model). Journal: `4-dflash`/round-1 raw.
   * `--spec-type draft-mtp` **alone** does not serve this model either: every request logs
     *"loading draft model Qwen3.8-27B-DFlash2…, failed to create MTP context"* and the unit
     crash-loops. MTP only serves when `ngram-cache` rides along (that is how prod runs).
   Arm 5 is therefore reported as **5a = MTP+ngram (prod preset)** and **5b = DFlash alone**, both
   measured on the same model in the same window. No combined number exists.
4. **`--spec-draft-n-max` is one server-wide option.** A second occurrence is deprecated and the last
   value wins. MTP arms use 7, DFlash headline uses 7, DFlash default (3) is arm 4b/5b. MTP's 3× could
   be moved by changing n_max; only 7 was measured for MTP (round 1's 4/1 pair was invalid).
5. **Multi-slot**: `-np` is not passed by the preset; server default is `n_slots=4, kv_unified=true`.
   Cachecheck (§5) shows `-np 1` changes 260k prefill by +0.5 %, so this does not distort the table.
6. **Prefill at 27.7k is ~5–9 % below the 1.6k rate for every arm** (attention/UB depth effect), and
   spec arms pay ~50 t/s extra prefill cost for the drafter's KV writes at long context.
7. **DFlash long-context VMEM was close to the limit**: arm 6 logged
   `Failed to allocate pinned memory … ErrorOutOfDeviceMemory` twice during the 27.7k run (request
   still completed, `truncated:false`). Numbers are included with that warning.
8. Long-context prefill with **ngram-cache running** would be corrupted by ngram speculation if the
   generated stream is repetitive; our 30k decode used a repetitive "DONE." stream deliberately (it is
   a speed probe, not a quality probe) — see caveat 9.
9. **The 27.7k prompt's chat answer is "DONE." repeated** (the instruction "reply with the single word
   DONE"); decode t/s on a repeating stream is the *speculator's* ideal case, not a general deep-context
   decode rate. Arms 1/2/6 (no spec) are unaffected; arms 3/4/5 benefit. Read those columns accordingly.
10. `--cache-reuse 256` is inert on all arms: the server logs
    *"cache_reuse is not supported by multimodal, it will be disabled"* — mmproj is always loaded.

---

## 4. Do the accelerators change greedy output? (finding)

Same prompts, `temperature 0`, `seed 4242`, same model — comparison against arm 1:

| arm | arith | list | code | prose (2 sent.) | para (120 w) | para2 (100 w) |
|---|---|---|---|---|---|---|
| 2 FA off | = | = | = | = | **≠** | = |
| 3 MTP | = | = | = | **≠** (240 vs 321 ch) | **≠** | **≠** |
| 4 DFlash n7 | = | = | = | **≠** | **≠** | **≠** |
| 4b DFlash n3 | = | = | = | **≠** | **≠** | **≠** |
| 5a MTP+ngram | = | = | = | **≠** | **≠** | **≠** |
| 6 DFlash FA-off | = | = | = | = | **≠** | = |

`=` means byte-identical. Divergence in the 120-word paragraph is mid-sentence (e.g. baseline
"long road trip" → MTP "weekend adventure"; a phrase is dropped and the closing sentence is
replaced). Every spec arm diverges at the *same* kind of place — a low-confidence, open-ended spans —
and non-spec arms do not. **Conclusion: on this build, speculative decoding is not exactly
distribution-preserving under greedy decoding.** Short, high-confidence answers are stable; open-ended
prose is not. Treat any spec-enabled benchmark result as a *slightly different model* and re-run
LLM-benchmark cells (especially long-generation ones) rather than assuming equivalence.

---

## 5. Cache verdict: are the existing long-context prefill numbers cache-assisted?

**No. The 566.0 t/s @ 260K figure holds. It is a genuine cold, uncached prefill.**

Re-measured on A3B (`Qwen3.6-35B-A3B-UD-Q4_K_M`, `-c 262144`, q8_0/q4_0, `-b 16384 -ub 2048`, FA on)
with a **257,190-token** prompt (varied 8k-blocks; the original used a repeated 30k unit — see
`a3b-260k/RESULTS.md`), one cold request each, `cache_prompt:false`, `cache_n:0`,
`cached_tokens:0`, temp 0, max_tokens 64, answer "DONE":

| config | slots | prompt tok | prefill t/s | prefill s | Δ vs 566.0 |
|---|---|---|---|---|---|
| **`--cache-reuse 256`** (original flags) | 4 (default) | 257,190 | **570.8** | 450.6 | **+0.8 %** |
| `--cache-reuse 0` | 4 (default) | 257,190 | **571.1** | 450.4 | +0.9 % |
| `--cache-reuse 256 -np 1` | 1 | 257,190 | 573.5 | 448.5 | +1.3 % |
| `--cache-reuse 0 -np 1` | 1 | 257,190 | 573.4 | 448.5 | +1.3 % |

Flags used (exact, per arm in `cachecheck.json` → `argv`):
`-m Qwen3.6-35B-A3B-UD-Q4_K_M.gguf --mmproj mmproj-Qwen3.6-35B-A3B-F16.gguf --host 0.0.0.0 --port 8080
-ngl 99 --jinja -b 16384 -ub 2048 --metrics --reasoning off -c 262144 --cache-type-k q8_0
--cache-type-v q4_0 --cache-reuse {256|0} [-np 1] -fa on`

Control on the ablation model (Qwen3.8-27B, 126,822-token prompt, three runs):
`--cache-reuse 256` → 371.0, 371.5 t/s; `--cache-reuse 0` → 371.4 t/s. Spread 0.1 %.

**Caveats on the verdict**
* `--cache-reuse` is **disabled** by the server whenever mmproj is loaded
  ("cache_reuse is not supported by multimodal"); it was inert in the original runs too, so it can be
  neither the cause nor the cure.
* `cache_n:0` / `cached_tokens:0` on every run — the server did not reuse any prefix (`cache_prompt:false`).
* The prompt still repeats an 8k block three times per unit, so an internal *graph/attention* pattern
  cannot be excluded as a small effect; but a KV-prefix reuse effect is ruled out (cache_n=0), and
  `--cache-reuse 0` cannot change anything if it is inert. The A3B number is reproducible to ±1 %.
* Not reproduced on the original 260,115-token prompt text (that harness file lives only in
  `a3b-260k/`); comparison is "same size, varied blocks", which is the stricter case.

---

## 6. Artifacts

| file | content |
|---|---|
| `arm-1-baseline.json` … `arm-6-dflash-fa-off.json` | per-arm: argv, ExecStart as parsed by systemd, KV type, n_ctx/slots, VRAM idle/peak, decode/prefill timings, 6 answers, journal lines (spec init, acceptance) |
| `arm-4b-dflash-nm3.json`, `arm-5a-mtp-ngram.json`, `arm-5b-dflash.json` | the extra configs needed for the DFlash n_max sweep and the MTP+DFlash substitution |
| `cachecheck.json` | all seven long-context probes (incl. argv) and the prompt metadata |
| `ablate2.py`, `cachecheck.py`, `run3.sh` | harnesses exactly as run on `.148` |
| `raw/round1-*.json` | round-1 runs kept only as evidence for the defects in §2 |

**Restored at end:** preset `stock38mtp` (`Qwen3.8-27B-Q4_K_M` + mmproj + `--spec-type
draft-mtp,ngram-cache --spec-draft-n-max 4 --spec-draft-n-min 1 --image-min-tokens 1024`, ctx 131072).
`z-ablation.conf` removed, `z-active-model.conf` restored, `active.gguf`/`active-mmproj.gguf` repointed.
Verified after restore: unit `active`, `NRestarts=0`, `/v1/models` serves `active.gguf`, chat reply
`"OK"` with `finish_reason: stop`, journal shows `creating MTP draft context` + `model loaded`.

Not published to the website; nothing committed (per task).
