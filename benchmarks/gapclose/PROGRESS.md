# Gap-close campaign — progress log

## Completed
- STEP 0 inventory (INVENTORY.md): 7 runnable models, 12 not-re-measurable.
- STEP 1 A3B 256K standard speed: prefill 2480.1, decode 98.19, VRAM 24.83 GiB (kills pending=true).
- STEP 2 error bars: A3B 32K (0.7% prefill, 1.6% decode spread), A3B 256K (0.87%/0.21%),
  Qwen3.8-27B prefill 687.6 (0.67%). Qwen3.8 real decode 28.61 t/s via /completion (chat EOS-truncates).
  All spreads < 5%.
- STEP 3 chat (10-q suite): all 7 runnable models = 90% (9/10, 1 partial on Bunnings-onion q).
  Ceiling effect — questions too easy. Artifacts: data/chat/*.json.

## In progress
- STEP 4 thinking on/off (think screen, 5 models; A3B already done: off 22/25 > on 18/25).
- Off-mode ~30s/q; on-mode (thinking, cap 16384) ~60-100s/q and can run hours for dense 27B.

## Todo
- STEP 5 A3B ablation (ablate_a3b.py; MTP arms fail — A3B has no nextn tensors).
- STEP 6 games (top5 by decode speed; A3B galaga/gta rerun with enable_thinking off).

## Known issues fixed this campaign
1. chat_suite BASE url double /v1 (was 404).
2. lfm3 needs b11874 build (b11517 = unknown arch lfm3); runs :8091.
3. pkill -f self-match kills ssh (3x) — use kill <pid>.
4. --chat-template-kwargs JSON must be quoted in systemd ExecStart; --reasoning off is safer.
5. chat probe EOS-truncates decode (predicted_n=2) — use /completion ignore_eos.
