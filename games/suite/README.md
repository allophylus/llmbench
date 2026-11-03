# Game suite — 4 specs, executed assertions, spec compliance

Four frozen prompts, one per game, each with **its own** `window.__game` contract. The
point is not "can a model write a game" (the older v1/v2 shooter cell already asked that)
but "can it write *this* game and only this game" — a task-specific contract, a seeded
deterministic simulation, and a grader that executes the rules instead of pattern-matching
the source.

Why the old prompts were replaced here: `WEBGAME_PHYSICS.md`/`WEBGAME_PROMPT_v2.md` demanded
one shared contract (`enemies[]`, `bullets[]`, `lives`, SPACE to fire) for every task. Built
against that, the "3D physics sandbox" came back as a shooter. The new specs declare only
`{ready, over, score}` plus the handles that task actually needs — no enemy, bullet, weapon
or lives vocabulary in the ball, block or board tasks — and a task that adds them loses
compliance points.

| spec file | game | own handles (beyond ready/over/score) | grader seam |
|---|---|---|---|
| `specs/GAME_SPEC_ball-drop-sandbox.md` | 25 balls, box floor+walls, restitution, sphere-sphere | `balls[], step, reset, hash, seed` | `step(1/60)` × N |
| `specs/GAME_SPEC_tower-stacker.md` | 20 seeded-offset blocks, no jitter topple | `blocks[], height, toppled, step, reset, hash` | `step(1/60)` × N |
| `specs/GAME_SPEC_tower-defence.md` | fixed path, 5 fixed waves, one auto-placement policy, finite gold | `gold, lives, wave, kills, towers[], units[], path[], won, step, reset, hash` | `step(1/60)` × N |
| `specs/GAME_SPEC_match3-cascades.md` | 8×8 seeded board, swap, cascades to stable, numeric scoring | `grid, moves, cascade, swap(r1,c1,r2,c2), settle, hash` | `swap()` + `settle()` |

Prompts are frozen: `build.json:prompt_sha256` records the exact bytes each run used.

## Harness

| file | role |
|---|---|
| `playprobe.py` | opens `index.html` in headless Chrome, checks the run gate (load, ready, canvas, three.js, contract keys), then **executes the spec's behavioural assertions** through `window.__game` with a virtual clock (`step(1/60)` called by the grader, not by the page's rAF), then scores **spec compliance** from the code plus runtime evidence. Writes `probe.json` + a screenshot. |
| `suite_run.py` | one cell = generate → gate → assert → (repair) loop. Max **10 repair turns** (11 attempts). Each repair sends the model its own file plus the exact failed assertion ids, what the grader observed, and any spec violations. Resumable (`--skip-done`); one cell at a time. |

Per attempt, `build.json` records: tokens (prompt/completion), wall seconds, decode t/s,
gate pass, assertions passed/total with each `got`/`want`, compliance score 0-100 with the
violations list, and the screenshot.

### Assertions (executed, not inspected)

* ball-drop: ball count at 150 ticks, 25 balls + gravity at 800, nothing outside the box at
  6000, ≥1 settled ball, same seed ⇒ same hash / other seed ⇒ different.
* tower-stacker: 20 blocks within x ∈ [-3,3], height 20 and not toppled, no interpenetration
  at four samples, no drift (centre of mass |x| ≤ 0.15), determinism.
* tower-defence: towers on distinct non-path integer tiles, gold exact
  (`200 + 5·kills − Σcost`) and never negative, all 5 waves won under the fixed policy,
  ≤1 tower per 10-tick window, determinism.
* match3: clean 8×8 board and `settle()` is a no-op on it, the fixed 5-swap script replays
  identically, `settle()` after every `swap()` changes nothing, 200 sampled swaps all return
  stable boards, determinism.

### Compliance (0-100)

Starts at 100; −25 per violation, −5 per note. Violations are things the task did not ask
for or explicitly forbids: shooter vocabulary or a Space action in a non-shooter task,
external physics engine, `Math.random`/`Date` in a seeded simulation, click-to-place /
click-to-drop / manual launch where the spec says automatic, towers off-grid or two per
window, external image/texture/audio assets, missing contract keys. Runtime evidence
(non-deterministic replay, jitter after settle) counts the same as static evidence.
Comments are stripped first, so a comment is never read as code.

## Running

```sh
python3 games/suite_run.py --base http://127.0.0.1:8080 --model-slug <slug> --spec all
# one model at a time; the matrix is driven by games/suite_matrix.py
```

## Output layout

```
games/suite/out/<model-slug>/<spec>/attempt-<n>/{prompt.txt,raw_reply.md,index.html,gen.json,probe.json,shot.png}
games/suite/out/<model-slug>/<spec>/build.json
games/suite/out/<model-slug>/index.html        accepted (or best) game
games/suite/out/<model-slug>/shot-<spec>.png   frame shown on the side-by-side page
```

## Known limits

* Acceptance = the run gate. Assertion failures do not retry forever: a game that runs but
  fails an assertion is recorded with its numbers, because "needed 11 turns and still wrong
  physics" is the measurement.
* The grader's `step()`-driven clock means a game whose physics only advances inside its own
  rAF loop will stall under the grader and fail — that is intended (deterministic stepping is
  in the contract).
* Tower-defence/stacker seeds are only known to pass all 5 waves / not topple if the model
  implements the stated arithmetic; a correct-ish but drifting implementation will fail c3
  or b2 and be recorded as such.
