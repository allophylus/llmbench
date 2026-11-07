# RTX 3090 — Qwen3.8-27B (ByteShape IQ4_XS), llama.cpp b12189 CUDA

Separate card, separate table. Not merged with the R9700 (Vulkan) rows.

Model file: `Qwen3.8-27B-IQ4_XS-3.84bpw.gguf` (huggingface.co/byteshape/Qwen3.8-27B-GGUF)
GPU: NVIDIA GeForce RTX 3090 24 GiB (CUDA, Windows) · build: llama.cpp b12189 win-cuda-12.4-x64 (llama-server.exe)
Filler sha256: `67ecdc055a6068ab6d86bdee52d0e1ba4ff8a15e39a6a989fe23d54be5a2dd2d`

## Matched-context sweep

| ctx | prompt tokens | prefill t/s | prefill s | decode t/s | peak VRAM GiB | draft accepted | status |
|---|---|---|---|---|---|---|---|
| 4,096 | 3590 | 1208.1 | 3.0 | 91.64 | 20.05 | 47/48 | ok |
| 32,768 | 32253 | 1256.5 | 25.7 | 74.42 | 21.01 | 47/47 | ok |
| 65,536 | 65016 | 1094.5 | 59.4 | 63.83 | 22.17 | 47/47 | ok |
| 131,072 | 130553 | 829.9 | 157.3 | 49.68 | 23.14 | 47/47 | ok |
| 262,144 | 261679 | 132.8 | 1969.9 | 8.38 | 23.08 | 47/47 | ok |

Flags: `-ngl 99 -fa on -b 16384 -ub 2048 -ctk q8_0 -ctv q4_0 --cache-reuse 256 --metrics --jinja -np 1 --reasoning off --spec-type draft-mtp --spec-draft-n-max 3`
MTP speculative decoding was ON (ByteShape's published command); the speed probe is a repetitive continuation, so draft acceptance is ~100% and decode is a best-case rate.

## GPQA-Diamond (25 frozen questions, 4096-token cap)

| arm | correct | tokens | length stops | wall s |
|---|---|---|---|---|
| thinking off | 16/25 | 65230 | 10 | 844.8 |
| thinking on | 19/25 | 81745 | 17 | 1149.5 |

## Chat, 10 fixed questions

9/10 correct, 1 partial, 0 wrong, 90.0% accuracy, mean decode 72.89 t/s.

## Control: the same probe without speculative decoding

32K rung, same flags minus `--spec-type draft-mtp`: decode **29.89 t/s** and prefill 1379.8 t/s (32253 prompt tokens). With MTP the same rung reads 74.42 t/s decode, so the published decode column is a speculative-decoding figure and the speed probe's repetitive output (draft acceptance 47/47) flatters it.

## Browser game (three.js Galaga)

status: accepted, attempts used: 1, completion tokens: 5377, wall: 94.5 s.
Gate: load, canvas, WebGL, three.js, animation advancing, input changing pixels and the
`window.__game` contract all true (attempt-1/validation.json). The http run logged 2 console
404s, both resource fetches of the shared `games/touch.js` that webgen injects by a path
computed for `games/<slug>/`; stored one level deeper the relative path escapes the served
root. The published copy carries `touch.js` beside it, so the page renders with 0 console
errors (verified in headless Chrome). The frames are the model's own geometry.
- attempt 1: pass

## Vision smoke

expected `ZQ-731`, got `ZQ-731
The user wants the alphanumeric code inside the red rectangle. Looking at the image, there's a red-bordered square on the left containing the text "ZQ-731". The blue circle on the right is irrelevant. The instruction is to reply with only the code, no extra text. So the response should be exactly "ZQ-731".` → pass (1.34 s).

