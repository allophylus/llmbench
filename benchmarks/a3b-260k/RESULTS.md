# A3B long-context measurement — 2026-11-03

Model: `models/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (Q4_K_M, 22.13 GB file)
Server: `llama-server` b11517-8a1a9b512, Vulkan (R9700, 34.21 GB card), systemd unit
`qwen-longctx.service` with the standard apple-to-apple flags:

```
-ngl 99 --jinja -fa on -b 16384 -ub 2048 --cache-type-k q8_0 --cache-type-v q4_0 --cache-reuse 256 --metrics
-c <32768 | 262144>           (varied per run; nothing else changed)
```

No speculative decoding (`--spec-type` absent). `-np` not passed (server default: n_slots = 4,
kv_unified = 'true'; per-slot ctx = c / 4).

Method (BENCHMARK.md §4 speed probe + §3 ctx cell):
1. Cold request per run: `POST /v1/chat/completions`, `temperature 0`, `cache_prompt:false`,
   `stream:false`, `max_tokens` as listed.
2. Prompt built from the frozen pack `llmbench/suite/packs/ctx_filler.txt`: one identical
   30,000-char unit repeated K times + a prefix tail, calibrated with `POST /tokenize` to
   within 0.5 % of target (harness `a3b_ctx_run3.py`). Note: `/tokenize` is exactly linear
   only for repeated identical content — a contiguous 380k-char slice of the pack reads as
   93,635 tokens (4.06 chars/token per sub-100k chunk), so long prompts must be built from
   repeated units.
3. Prefill = `timings.prompt_per_second`, decode = `timings.predicted_per_second`
   (`predicted_n` shown; 256 for the short probe, 128 for long, 30-70 for the 260k run).
4. VRAM = `/sys/class/drm/card1/device/mem_info_vram_used`, sampled at 1 Hz during the request.

## Results

| run | n_ctx | prompt tokens (calibrated) | max_tokens | predicted_n | prefill t/s | prefill s | decode t/s | VRAM idle GiB | VRAM peak GiB | wall s |
|---|---|---|---|---|---|---|---|---|---|---|
| short probe (c=32768) | 32768 | 621 | 256 | 256 | 1812.4 | 0.34 | 101.88 | 21.17 | 21.14 | 2.8 |
| ctx30k @ c=32768 | 32768 | 29,988 | 64 | 64 | 2494.5 | 12.0 | 98.13 | 21.17 | 21.17 | 12.7 |
| ctx131k @ c=262144 | 262144 | 131,195 | 128 | 70 | 1028.5 | 127.6 | 78.57 | 23.82 | 23.82 | 129.0 |
| **ctx260k @ c=262144** | 262144 | **260,115** | 128 | 30 | **566.0** | **459.6** | **62.31** | 23.82 | 23.82 | 460.3 |

* Loads / OOM: **loads**. `n_ctx=262144` reported by `/props`; model loaded in ~5 s
  (03:53:47 → "model loaded"), KV+weights resident, idle VRAM 23.82 GiB of 31.86 GiB
  usable — no OOM, no error in the journal. Answers correctly at full depth (reply "DONE").
* (superseded) first pass with mis-calibrated prompts: 93,658 tok @ 1337.6 t/s and a
  re-run at the same size — see `ctx130k_at260k.json` / `ctx258k_at260k.json`; keep for
  the tokenizer caveat only, not as context rungs.
* Decode at 260k is 62.3 t/s = 61 % of the 32k-rate (101.9) — attention over a full
  260k KV costs ~4 ms/token.
* `--cache-reuse` is logged as "not supported by this context, disabled" by this build in
  both runs — same behaviour as prod; no effect on these cold numbers.

## Reproduce

```bash
# on .148, prod unit swapped to A3B with -c 262144 (see z-active-model.conf saved here)
flock llmbench/queue.lock \
  python3 bench-work/a3b_ctx_run3.py 260000 128 ctx260k out.json
```

Raw JSON for every row: this directory.
