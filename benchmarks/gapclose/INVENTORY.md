# Gap-close inventory — what this host can actually re-measure

Date: 2026-11-03. Host: `the GPU host` (AMD Radeon AI PRO R9700 32 GiB, RADV/Vulkan,
`llama-server` b11517, prod unit `qwen-longctx.service` on :8080 serving `the served model file`).
Raw record source: `~/.openclaw/workspace/llmbench/results/*.json` (the `sources[]` of every
`data/results.json` row); every record's `env.host` is this box.

Loadable = a complete `.gguf` (+ mmproj where the model is multimodal) whose size fits the
~31.86 GiB usable card and which is a *generative chat* model (a drafter head is not a model).

Disk check: `/` is **97 % full, 9.9 GiB free** — re-downloading any multi-GB model is not
possible in this campaign without deleting something else. Rows whose weights were deleted
are therefore **not re-measurable on this host** (they were measured here when the file existed;
their numbers are historical, not verifiable now).

## Weights present on this host (complete `.gguf` / sharded sets / dirs)

| path | size | what it is | usable as a model |
|---|---|---|---|
| `models/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` | 22.13 GB | Qwen3.6-35B-A3B Q4_K_M | **yes** (mmproj `qwen36/mmproj-Qwen3.6-35B-A3B-F16.gguf` present) |
| `models/Qwen3.8-27B-Q4_K_M.gguf` | 16.1 GB | Qwen3.8-27B Q4_K_M (+ `mmproj-Qwen3.8-27B-F16.gguf` 885 MB) | **yes** |
| `models/Qwen3.8-27B-Q4_0.gguf` | 15 GB | Qwen3.8-27B Q4_0 | **yes** (same mmproj) |
| `models/DavidAU-Qwen3.8-27B-NEO-MAX-MTP-Q4_K_M.gguf` | 18 GB | DavidAU NEO-MAX MTP finetune | **yes** (same mmproj) |
| `models/Huihui-abl-Q4_K_M.gguf` | 16 GB | Huihui abliterated 27B | **yes** (same mmproj) |
| `models/bench-new/ornith35a3b/Ornith-1.5-35B-Q4_K_M.gguf` | 21.7 GB | Ornith-1.5-35B-A3B | **yes** (mmproj absent — text-only) |
| `llmbench/tune/dl4/LFM3-1.7B-Q4_K_M.gguf` | 1.1 GB | LFM3-1.7B | **yes** (text-only) |
| `models/Qwen3.8-27B-DFlash2-Q4_K_M.gguf` | 1.1 GB | DFlash2 drafter | no — drafter, not a model |
| `models/Qwen3.8-Flash-Next-mtp-drafter-Q4_K_L.gguf` | 1.9 GB | MTP drafter | no — drafter |
| `models/qwen2_0/Qwen3.8-Flash-Next-…-Q2_0-0000{1,2}-of-00002.gguf` | 37.6 GB total | Qwen3.8-Flash-Next Q2_0 shards | no — **exceeds 31.86 GiB card; no session/tokenizer files in the dir** |
| `models/iq3xxs/…IQ3_XXS-0000{1,2}-of-00002.gguf` (+ `mmproj-…-BF16.gguf`) | 75.8 GB | Qwen3.8-Flash-Next IQ3_XXS shards | no — **exceeds card by 2.4×** |
| `models/mxfp4-gguf/`, `models/iq3xxs/IQ3_XXS/` | — | empty dirs / logs | no |

## Per row in `data/results.json` (19)

| # | slug | weights for that row | runnable here? | why |
|---|---|---|---|---|
| 1 | `davidau-qwen3-8-27b-neo-max-mtp-q4-k-m` | `models/DavidAU-Qwen3.8-27B-NEO-MAX-MTP-Q4_K_M.gguf` | **yes** | file present, 18 GB |
| 2 | `huihui-abl-q4-k-m` | `models/Huihui-abl-Q4_K_M.gguf` | **yes** | present, 16 GB |
| 3 | `lfm2-5-24b-a2b-q4-k-m` | `LFM2.5-24B-A2B-Q4_K_M.gguf` (deleted) | **no** | weights absent; 9.9 GB free ≠ ~14 GB download |
| 4 | `lfm2-5-8b-a1b-q6-k` | `llmbench/tune/dl/LFM2.5-8B-A1B-Q6_K.gguf` (dir empty) | **no** | weights absent (dir kept, file gone) |
| 5 | `lfm3-1-7b-q4-k-m` | `llmbench/tune/dl4/LFM3-1.7B-Q4_K_M.gguf` | **yes** | present, 1.1 GB |
| 6 | `minicpm5-2b-q8-0` | `MiniCPM5-2B-Q8_0.gguf` (deleted) | **no** | weights absent |
| 7 | `muse-glimmer-30b-q4-k-m` | `Muse-Glimmer-30B-Q4_K_M.gguf` (deleted) | **no** | weights absent |
| 8 | `nemotron-3-5-lightning-30b-a3b-q4-0` | `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-Q4_0.gguf` (deleted) | **no** | weights absent |
| 9 | `ornith-1-5-35b-a3b-q4-k-m` | `models/bench-new/ornith35a3b/Ornith-1.5-35B-Q4_K_M.gguf` | **yes** | present, 21.7 GB (text-only, row has no vision cells) |
| 10 | `ornith-1-5-9b-q8-0` | `Ornith-1.5-9B-Q8_0.gguf` (deleted) | **no** | weights absent |
| 11 | `qwen3-6-35b-a3b-ud-q4km` | `models/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` | **yes** | present |
| 12 | `qwen3-6-35b-a3b-ud-q4km-ctx256k` | same as #11 | **yes** | speed row for the same weights at `-c 262144` |
| 13 | `qwen3-6-35b-a3b-ud-q4km-ctx32k` | same as #11 | **yes** | speed row at `-c 32768` |
| 14 | `qwen3-8-27b-q4-0` | `models/Qwen3.8-27B-Q4_0.gguf` | **yes** | present, 15 GB |
| 15 | `qwen3-8-27b-q4km` | `models/Qwen3.8-27B-Q4_K_M.gguf` | **yes** | present; this is the prod model today |
| 16 | `qwen3-8-27b-dflash2-q4-k-m` | drafter only | **no (as a model)** | status `failed`: "load failed" — it is a 1.1 GB drafter, not a 27B trunk; re-running reproduces the same failure by design |
| 17 | `qwen3-8-27b-mxfp4` | `<radiance-build>/models/qwen3.8-27b-mxfp4.rad` (absent) | **no** | different engine (radiance `.rad` container), not llama.cpp; weights absent from that path. `models/mxfp4-gguf/` holds only download logs |
| 18 | `underdog-saluki-27b-iq2` | `llmbench/tune/dl/Underdog-Saluki-27B-1.0-IQ2-mix.gguf` (dir empty) | **no** | weights absent |
| 19 | `xing4-0-29b-q5-0` | `xing4_0-29b-q5_0.gguf` (deleted) | **no** | weights absent; row status already `failed` |

**Runnable set for this campaign: 6 distinct models** —
`qwen3-6-35b-a3b-ud-q4km` (2 ctx variants), `qwen3-8-27b-q4km`, `qwen3-8-27b-q4-0`,
`davidau-qwen3-8-27b-neo-max-mtp-q4-k-m`, `huihui-abl-q4-k-m`, `ornith-1-5-35b-a3b-q4-k-m`,
`lfm3-1-7b-q4-k-m` (7 rows if the two A3B ctx variants are counted separately).

Not re-measurable on this host: 12 rows (lfm2-5-24b, lfm2-5-8b, minicpm5-2b, muse-glimmer-30b,
nemotron-3.5, ornith-1.5-9b, qwen3.8-dflash2, qwen3.8-mxfp4, underdog-saluki, xing4, plus the two
Qwen3.8-Flash-Next variants which are only present as card-exceeding shard sets and have no row).
The three game cells and thinking cells attached to the TASK belong to A3B/Qwen3.8-27B rows, both
present.

## Caveat on "runnable"

Qwen3.8-27B Q4_K_M is the current prod model; every experiment must stop the unit (or override
its ExecStart drop-in) and restore `stock38mtp` afterwards, as documented in `docs/BENCHMARK.md` §2.
