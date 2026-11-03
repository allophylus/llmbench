# A3B browser-game cells — 2026-11-03

Model: `models/qwen36/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` on the R9700
(`llama-server` b11517, Vulkan, `-c 32768 -ngl 99 -fa on -b 16384 -ub 2048 -ctk q8_0 -ctv q4_0
--cache-reuse 256`, no speculative decoding, thinking forced off per request).

Prompts: frozen `games/WEBGAME_GALAGA.md`, `WEBGAME_GTA.md`, `WEBGAME_PHYSICS.md`
(sha256 recorded in each `gen.json`). Method: `docs/BENCHMARK.md` §5 — temperature 0.0,
max_tokens 8000, up to 3 attempts to pass the gate, then `games/repair_loop.py` repair
turns (10 max). Gate: `games/webvalidate.py` (load ×2, 0 console errors, canvas, WebGL,
THREE in use, animation advancing, keys change pixels, `window.__game` contract).
Screenshots from the gate; the passing game also has a 1280×800 Playwright webm.

## Numbers

| game | attempts to gate | accepted at attempt | gen tokens (3 attempts) | gen wall s | repair turns | repair outcome | final gate |
|---|---|---|---|---|---|---|---|
| galaga-3d | 3 | – (never) | 12,645 | 331.9 | 10 (cap) | still broken | pass=true, contract=**false** |
| gta-3d | 3 | – (never) | 13,184 | 339.7 | 6 (stalled) | stalled, no progress | animation+input+contract false |
| physics-3d | 3 | – (never) | 10,650 | 320.1 | 2 | **ACCEPTED at turn 2** | all 8 checks green, 0 console errors |

Decode during generation: 51–52 t/s for ~4.2 K-token files (three generations in flight
at once; single-stream rate is ~100 t/s), wall 75–86 s per file.

Per-attempt gate detail (final generation run, attempt 1/2/3):

* **galaga** — all 3 attempts: load, canvas, WebGL, three.js, animation, input all pass,
  0 console errors; `contract_ok=false` because `window.__game.ready` never becomes true
  (the game builds a start overlay and waits for a click; reset() exists). Repair turn 1
  fixed `ready`, but every later turn's file throws
  `Cannot read properties of undefined (reading 'position')` inside `animate()` —
  the model then returned a **byte-identical file** on turns 3–10 (same 4,125 tokens,
  same bytes), so the loop could not converge.
* **gta** — attempt 1/2: loads, canvas/WebGL/three.js, but animation frozen and input
  does nothing, 681/687 console errors. Attempt 3: 2 console errors, animation+input+
  contract all fail. Repair turns 2–6 returned the same file (4,589 tokens) with
  "ready is false" + `reset()` not callable → stalled at turn 6.
* **physics** — attempts 1–3: load/canvas/WebGL/three.js/contract pass, animation+input
  fail (static scene). Repair turn 1 (2,492 tok, 35.7 s) produced the accepted game:
  249 lines, three.js via unpkg import map, 0 console errors, animation advancing,
  input moves pixels, `window.__game` complete. Re-run of the gate on the final
  `index.html` a second time: accept again.
  Playtest after the gate (`playtest.json`): after arrow/space input the game reports
  `score: 10, lives: 3, over: false, ready: true, enemies: 2` — i.e. it is scoring,
  not just animating.

## Findings

1. **The harness, not the model, decides this cell's numbers.** A3B never passes on its
   first generation: 0/3 games accepted from generation alone; 1/3 after repair.
2. **A3B's repair loop de-rails at temperature 0**: after one edit it re-emits the same
   file verbatim (identical token counts, identical bytes), so "10 repair turns" are
   really 2 distinct attempts. Token spend still counts them (galaga ≈41 K repair tokens
   for 2 distinct files). Reported as *stalled*, not as a model fix.
3. **Its first drafts are static or start-gated.** Physics and gta come out with a start
   overlay / no running loop; galaga runs but forgets `ready`. The gate does not click
   "START", so any start screen automatically fails animation.
4. **Screenshots** (from the gate): physics shows a running 3D scene with HUD + touch
   pads (green player, red block, score/lives); galaga shows starfield, cyan ship, HUD,
   touch pads; gta shows the "NEON DRIVER / START ENGINE" overlay over a black scene —
   consistent with the gate result.

## Changes made to the harness (needed to run at all; all in the repo)

* `games/webgen.py` — sends `chat_template_kwargs: {enable_thinking:false}` (it did not;
  A3B defaults to thinking and would spend the 8000-token cap in reasoning).
* `games/build_run.py` — no longer passes `--overwrite` (webgen rejects it); passes
  `--max-attempts 3` (webgen refuses `1`); locates `gen.json`/`index.html` wherever
  webgen writes them; accepts a file whenever `gen.json` exists instead of trusting
  webgen's exit code (it returns 0 or 2 for the same rejection).
  Backup: `build_run.py.bak-20261103`.
* `games/webvalidate.py` — pageerror text now includes file:line from the stack.
* `benchmarks/a3b-games/build_run2.py`, `repair_gate3.py`, `repair_one.py` — the drivers
  used here (explicit gate after every attempt/repair turn, absolute paths so the
  file:// leg works, no-progress stop, gate reason fed to the model).
* Tooling ran on .148 (venv + Playwright chromium) because local exec kills child
  processes on return; `.148` now has `screen`, a venv and chromium for this work.

## Artifacts (this directory)

`qwen3-6-35b-a3b-<game>/` — `index.html` (final), `build.json` (per-attempt), `metrics.json`,
`shot.png`, `playtest.json` (physics), `video/` (physics webm), `attempts/`, `repair/`
(turn prompts, replies, gen.json, log.json). Driver logs: `repair4-*.log`, `b2-*.log`.
