# A3B benchmark session — 2026-11-03 (llmbench)

Host: the benchmark box (R9700, llama.cpp b11517 Vulkan, systemd unit `qwen-longctx`).
Model under test: `models/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`.
**Restored at end:** preset `stock38mtp` (Qwen3.8-27B-Q4_K_M + mmproj + MTP + ngram-cache,
ctx 131072) via `bin/switch-model.sh stock38mtp` — verified: serving, answers OK,
argv identical to the pre-session ExecStart.

## Results (full detail in each RESULTS.md)
1. `benchmarks/a3b-260k/RESULTS.md` — 260K loads fine, no OOM.
   - 30K prompt (c=32768): prefill 2494.5 t/s, decode 98.13 t/s, VRAM 21.17 GiB
   - 131K (c=262144): prefill 1028.5 t/s, decode 78.57 t/s, VRAM 23.82 GiB
   - 260K (c=262144): **prefill 566.0 t/s (459.6 s), decode 62.31 t/s, VRAM 23.82 GiB**, answered correctly
   - Caveat found: `/tokenize` is only linear on repeated identical content — build long
     prompts from a repeated unit (harness `a3b_ctx_run3.py`).
   - `-np` not passed (server defaults n_slots 4, kv_unified) — "standard apple-to-apple
     flags" as used elsewhere on this box do not include `-np 1`.
2. `benchmarks/a3b-games/RESULTS.md` — 3 attempts per game, no first-shot pass.
   physics-3d ACCEPTED at repair turn 2 (full gate + playtest score 10). galaga-3d and
   gta-3d never pass (start-gated / ready=false; then byte-identical re-emissions).
3. `benchmarks/a3b-thinking/RESULTS.md` — cap 16K both modes: off 22/25, 91,075 tok,
   1244.9 s vs on 18/25, 300,352 tok, 4338.8 s (thinking costs 3.3× tokens for −4 correct).

## Harness fixes (in repo, backups kept)
- `games/webgen.py`: was not sending `enable_thinking:false` (A3B thinks by default → 8000-token cap eaten).
- `games/build_run.py`: passed `--overwrite` (rejected), relied on webgen exit code (0 or 2 on the same
  rejection), and webgen refuses `--max-attempts 1` — patched; backup `.bak-20261103`.
- `games/webvalidate.py`: pageerror now carries file:line from the stack.

## Environment lessons
- **Local exec kills child processes when the call returns** (even `setsid -f`, `nohup`, `screen -dmS` locally).
  Long runs that must outlive the call belong on the remote host inside `screen` (now installed on .148).
- .148 now has `bench-work/venv` (playwright + chromium 1248), `screen`, and
  `bench-work/games/` with the drivers (`build_run2.py`, `repair_gate3.py`, `repair_one.py`).
- Never `pkill -f <name>` when the pattern also matches your own ssh command line — it killed the session.
