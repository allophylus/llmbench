# llmbench — benchmark protocol

How every model is measured, with the exact commands and parameters. This is the
repeating recipe for each new model. Nothing here is aspirational: every value below
is what the scripts actually run.

Principles:

- **Measure, never infer.** A number exists only if a request produced it. Blank = not measured.
- **Record artefacts.** Every cell writes a SCHEMA-1 JSON; every game writes its prompt,
  raw reply, HTML and validation result.
- **Fail closed.** A truncated prompt, a dead server or a missing JSON is recorded as a
  failure with a reason — it is never counted as a model error or silently dropped.

---

## 1. Test matrix

| Cell id | Task | Samples | Decode params | Measures |
|---|---|---|---|---|
| `pub-gpqa25` | GPQA diamond | 25 | temp 0.0, seed 5, max_tokens 4096 | science reasoning |
| `pub-aime10x3` | AIME 2026 | 15 × 3 samples | temp 0.6, seeds `1000+i*10+s`, max_tokens 4096 | math, pass@3 style sampling |
| `pub-livebench25` | LiveBench subset | 25 | temp 0.0, seed 7, max_tokens 4096 | mixed reasoning |
| `ctx-gpqa30k` (`c1`) | GPQA embedded in 30,000 tokens of context | 25 | temp 0.0, seed 9, max_tokens 4096 | retrieval at 30k |
| `ctx-gpqa110k` (`c2`) | GPQA embedded in 110,000 tokens | 25 | temp 0.0, seed 9, max_tokens 4096 | retrieval near the 131k window |
| `agent-tau2-telecom20` (`a`) | tau2-bench telecom | 20 tasks | task default, pass^1 headline | multi-turn tool use |
| `agent-shell10` (`b`) | shell command tasks | 10, 6 turns max | temp 0.0, seed 11 | shell competence |
| `agent-termbench8` (`8`) | terminal-bench core | 8 frozen task ids | task default | real terminal tasks |
| `bench-ctx-sweep` (`0`) | llama-bench `p=512..131072 n=128 r=1` | — | — | prefill/decode vs context length |
| `speed-probe` | live HTTP probe | 1 | cache_prompt=false, max_tokens=256, temp 0 | cold prefill, steady decode, ctx window |
| `game-galaga-3d` | browser game, three.js | 1 attempt (+up to 3) | temp 0.0, max_tokens 8000 | can the model draw + build a playable shooter |
| `game-gta-3d` | browser game, three.js | 1 attempt (+up to 3) | temp 0.0, max_tokens 8000 | top-down driving mission |
| `game-physics-3d` | browser game, three.js | 1 attempt (+up to 3) | temp 0.0, max_tokens 8000 | 3D physics sandbox |
| `robot-play` | automated player | 60 s @ 10 Hz | real KeyboardEvents | can the game be played at all, objectively |

Every chat cell uses the model's own served chat template with thinking disabled:
`--chat-template-kwargs '{"enable_thinking":false}'`.

---

## 2. Server configuration

Bench server (port **8081**), started per model, prod stopped first:

```bash
llama-server -m <model.gguf> \
  --host 0.0.0.0 --port 8081 \
  -ngl 99 -fa on -c 131072 --jinja -np 1 \
  -ctk q8_0 -ctv q4_0 \
  --chat-template-kwargs '{"enable_thinking":false}'
```

Prod server is `qwen-longctx.service` on **:8080** (same flags, model via
`~/.config/systemd/user/qwen-longctx.service.d/z-active-model.conf`).
`switch-model.sh <preset>` relinks `models/active.gguf` and rewrites that drop-in.

Rules that exist because they were learned the hard way:

- Queue work takes `flock /home/ubuntu/llmbench/queue.lock`; suites stop prod after the lock and
  **must** restore it in a trap (`restore-prod.sh`) and health-check `:8080`.
- Never `pkill -f llama-server`. A clean exit (`status=0/SUCCESS`) does not trigger
  `Restart=on-failure` and the unit sits dead. Restart the unit instead.
- Check `ss -ltnp | grep 8081` before blaming the unit: a hand-started server can hold the port.
- One model per card at a time (34.2 GB card; 20+ GB models never co-load).

---

## 3. Running the suite

Full pass for one model (prod stops, restores on exit):

```bash
bash /home/ubuntu/llmbench/suite/bin/run_suite.sh --models <slug> --cells 1,2,3,c1,c2,a,b,8,0
```

Cells: `1`=GPQA `2`=AIME `3`=LiveBench `c1`=ctx30k `c2`=ctx110k `a`=tau2 `b`=shell `8`=termbench `0`=llama-bench sweep.

Per-cell scripts and their exact call shapes:

```bash
score_pack.py gpqa                       # -> pub-gpqa25
score_pack.py aime  --n 15 --samples 3 --temp 0.6   # -> pub-aime10x3
score_pack.py livebench                  # -> pub-livebench25
score_pack.py shell --n 10 --turns 6     # -> agent-shell10
ctx_embed.py   --cell c1                 # 30k  -> ctx-gpqa30k
ctx_embed.py   --cell c2                 # 110k -> ctx-gpqa110k
tau2_cell.py   --slug <slug> --dry 0     # -> agent-tau2-telecom20 (20 tasks)
termbench_cell.py --n 8                  # -> agent-termbench8 (8 frozen ids)
```

Outputs: `/home/ubuntu/llmbench/suite/results{7}/<slug>.json` plus per-cell
`<cell>.pub.json` / `<cell>.detail.json`, and `.cast` recordings per cell.

---

## 4. Throughput probe (the numbers in the table)

Cold, uncached, long enough to be steady-state:

```bash
POST /v1/chat/completions
{"messages":[{"role":"user","content":"<~470-token filler> Count from 1 to 200"}],
 "temperature":0,"max_tokens":256,"cache_prompt":false,"stream":false}
```

Take `timings.prompt_per_second` (prefill) and `timings.predicted_per_second` (decode) with
`predicted_n ≈ 256`; context window from `/props` → `default_generation_settings.n_ctx`.
A 2-token generation is not a decode measurement — it is noise.

Written to `results/speed.<slug>.json` and merged by `scripts/update_data.py`.

---

## 5. Game cells (browser, three.js, model draws everything)

Prompts (frozen, one per cell):

- `games/WEBGAME_GALAGA.md` — arcade space shooter
- `games/WEBGAME_GTA.md` — top-down driving mission
- `games/WEBGAME_PHYSICS.md` — 3D physics sandbox

Shared hard requirements in every prompt:

1. One self-contained HTML file, three.js from a pinned CDN import map, no build step.
2. **The model must draw everything** with geometry/materials/lights/particles — no images,
   textures, models or audio files.
3. Must expose `window.__game = {ready, score, lives, over, player:{x,y}, enemies[], bullets[]}`
   and `window.__game.reset()`.
4. Keyboard on `window` + on-screen touch controls (pointer events, 390×844 usable).
5. Visual quality bar: deliberate palette, gradient/nebula background, particles, hit flash,
   screen shake, eased motion, readable HUD.
6. Keep the file under ~350 lines (truncated output = failed submission).

Generation:

```bash
python3 games/webgen.py <base_url> <prompt.md> games/<slug> <slug> --max-attempts 3 --max-tokens 8000
```

- temperature 0.0, max_tokens 8000, up to 3 attempts; **only a passing attempt is published**
- `build.json` records: attempts used, retries, per-attempt outcome, tokens (prompt+completion),
  wall time, decode t/s, server fingerprint
- `attempts/attempt-N/` keeps prompt, raw reply, extracted HTML, gen.json, validation.json

Validation gate (`games/webvalidate.py`, headless Chrome + Playwright):

| Check | Requirement |
|---|---|
| load | http (and file://) load succeeds |
| console | no console errors (favicon 404 ignored) |
| canvas/WebGL | canvas present, WebGL context created |
| three.js | `THREE` actually used at runtime |
| animation | two screenshots ~1s apart differ |
| input | arrow keys visibly change the scene |
| contract | `window.__game` present and `ready` |

Robot player (`games/robot_player.py`): 10 Hz closed loop for 60 s or until game over —
reads `__game`, steers under the nearest descending enemy, dodges, fires via **real
KeyboardEvents**. Records final score, lives lost, survival, actions, frames, console
errors, and a video. A score of 0 with aligned aim means the game's collision geometry is
broken — the control test is teleporting a bullet onto an enemy.

Touch: `games/touch.js` is injected into every published game by `webgen.py`
(◀ ▶ FIRE dispatching the same KeyboardEvents). The harness layer guarantees humans can
play; whether the model implements touch itself is a separate signal and stays in the prompt.

---

## 6. Tuning cells (config sweeps, subset of models)

| Cell | What it varies |
|---|---|
| `c0-pp512 … c0-pp131072` | prompt length sweep (prefill curve) |
| `c1-fa-off` / `c1-fa-on` | flash attention |
| `c4-kv-f16` / `c4-kv-q8q4` | KV cache quantisation |
| `c5-ctx-*` | NIAH + TTFT at 65k/131k/196k/262k |
| `c7-power-220W/250W/300W` | power cap vs speed/thermals |
| `np1` / `np4` | parallel slots |
| `spec-none` / `spec-mtp` / `spec-dflash` | speculative decoding |

---

## 7. Adding a new model (checklist)

1. **Get the file** onto the R9700: `~/models/<family>/<file>.gguf`.
2. **Verify integrity before believing any number:**
   `sha256sum <file>` vs the HF LFS oid
   (`curl -s https://huggingface.co/api/models/<repo>/tree/main?recursive=true` → `lfs.oid`).
   A `.aria2` file beside a full-size model = interrupted download; delete both and refetch.
3. **Identity:** `python3 scripts/gguf_meta.py <file>` (`general.name`, architecture, block
   counts). Never state model identity from labels alone.
4. **Fit check:** file size vs ~30 GB usable VRAM at the chosen quant; decide Q4_K_M/Q5/Q6.
5. **Run the suite** (section 3) inside the queue lock; prod restores on exit.
6. **Throughput probe** (section 4) → `results/speed.<slug>.json`.
7. **Generate the three game cells** (section 5), validate, publish.
8. **Publish:** `scripts/update_data.py --results-dir …` → commit site → `llmbench/publish.sh`.
9. **Record** in `results/<slug>.json` + the site row; blanks stay blank.

---

## 8. Data layout

```
llmbench/
  results/<slug>.json              SCHEMA-1 model record (tests[])
  results/<cell>.<pub|detail>.json per-cell outputs
  results/speed.<slug>.json        measured throughput
  recordings7/<slug>/<cell>.cast   asciinema captures (source of the videos)
  games/<slug>/                    published game + build.json + attempts/ + metrics
```

Site: `scripts/update_data.py` merges records → `data/results.json` (+ `.js`), video links
are `…/llmbench/videos/<slug>__<cell>.mp4`.

---

## 9. Publishing rules

- Site: GitHub Pages (`allophylus/llmbench`), needs `.nojekyll`. Pages can take 1–2 min to rebuild;
  a 404 immediately after a push is normal.
- Videos: S3 + CloudFront (`www.lowtechplace.com/llmbench/videos/`). **CloudFront caches 24 h
  and the deployer cannot invalidate.** To change a clip, publish it under a new filename
  (e.g. `…__cell-dark.mp4`) and point the link at that; re-uploading the same key serves
  the old bytes all day.
- The site links only videos that exist; broken links are a bug, not a placeholder.

---

## 10. Known failure modes

| Symptom | Cause | Action |
|---|---|---|
| Cell `n_a: true`, `llama-bench produced no JSON` | bench binary failed | re-run the sweep; don't infer speed from cell durations |
| Game HTML ends mid-line | reply hit `max_tokens` | regenerate with a larger budget **and** the "under 350 lines" rule |
| `int(*0.55)` in the renderer | empty cast length in a worker | guard empty → default length |
| Video unchanged after re-render | CloudFront 24 h cache | new filename, not a re-upload |
| `window.__game` missing | model ignored the contract | robot cannot score it; still human-playable via the touch layer |
| Robot scores 0 with perfect aim | model's collision geometry unreachable | verify by teleporting a bullet; report the defect, not a fix |
