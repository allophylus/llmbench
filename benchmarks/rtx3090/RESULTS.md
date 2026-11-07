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


## Browser games — the other two TUI-derived cells (gta-3d, physics-3d)

Same frozen prompts and the same gate as the R9700 game rows
(`games/WEBGAME_GTA.md`, `games/WEBGAME_PHYSICS.md`, `games/build_run.py` with three
generation attempts then up to ten gate-driven repair turns). Server:
`llama-server.exe` b12189, `-c 32768 -ngl 99 -fa on -b 16384 -ub 2048 -ctk q8_0 -ctv
q4_0 --cache-reuse 256 --metrics --jinja -np 1 --reasoning off --spec-type draft-mtp
--spec-draft-n-max 3 --temp 0`, reached over an SSH tunnel to the gateway.

| cell | outcome | generation | repair turns | total tokens | total wall |
|---|---|---|---|---|---|
| gta-3d | **stalled** | 3 attempts, none passed the gate | 3 (cap 3 for this run) | 33,506 | 964.6 s |
| physics-3d | **pass**, attempt 1 | 1 attempt, all 7 gate checks green | 0 | 4,310 | 80.3 s |

`gta-3d`: every attempt renders (canvas, WebGL, three.js, animation advancing) but the
`window.__game` contract never reaches `ready` and arrow keys change nothing — the scene
sits in its game-over state with a RESTART button. A dispatched `pointerdown`+`click` on
that button and on the canvas centre (the known webvalidate limitation: it never clicks)
still leaves `ready:false` and input dead, so this is the model's defect, not the gate's.
Recorded as `stalled` after three repair turns rather than looping to ten, matching how
the A3B gta/physics cells are recorded. Artifacts: `games/gta-3d/` (attempts, repaired
candidate, `run.json` with both halves of the run).

`physics-3d`: accepted on attempt 1 with `load_ok`, `canvas`, `webgl`, `three_js`,
`animation`, `input` and `contract` all true (`games/physics-3d/attempts/attempt-1/validation.json`),
4,310 completion tokens over 80.3 s, prompt 533 tokens.

Note on the gate: `build_run.py` returns exit 2 from `webgen` whenever the gate rejects,
so `build.json` records `generator exit 2` per attempt rather than the individual failing
checks; the per-attempt `validation.json` files carry the check-level detail.

## Four-game spec suite (ball-drop-sandbox, tower-stacker, tower-defence, match3-cascades)

`games/suite_run.py` against the same server, same frozen specs, three attempts per cell
(the run is capped at 3 rather than the usual 11 because from attempt 2 the model
re-emits a byte-identical file — `sha256 ff37a709…` on every ball-drop attempt — i.e.
the same no-progress stall, and further turns cannot change the number).

| spec | gate | assertions (best) | compliance (best) | attempts | tokens | wall |
|---|---|---|---|---|---|---|
| ball-drop-sandbox | pass on all 3 | 2/5 | 100 | 3 (identical after 1) | 11,874 | 158.3 s |
| tower-stacker | fail, then **pass** | 5/5 | 100 | 2 (accepted 2) | 12,172 | 146.3 s |
| tower-defence | pass on all 3 | 0/5 | 100 | 3 | 19,778 | 251.0 s |
| match3-cascades | pass on all 3 | 1/5 | 75 → 100 | 3 | 12,009 | 157.3 s |

What the assertions say: the games load and run, but the behaviour the spec asks for is
mostly absent — the ball sandbox never reaches the required ball count/settling state and
the tower defence never places towers (0/5), so those two cells play but do not do the
task. tower-stacker is the one clean cell: 20 blocks, stable tower, no drift,
deterministic, 5/5. match3 starts with `Math.random` (compliance 75) and then scores 100
while still failing 4 of 5 rules.

Artifacts: `../../games/suite/out/byteshape-qwen3-8-27b-iq4xs-3090/<spec>/` (every
attempt, `build.json` with each assertion's observed value, screenshots).
