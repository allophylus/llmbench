# R9700 CARD LOCK — ctx-sweep (priority)

**State: RELEASED** — sweep completed 2026-11-03 21:21 UTC (35/35 cells).
Prod preset `stock38mtp` restored and verified healthy at 131072 ctx on :8080.
The `zz-ctxsweep-lock.conf` drop-in has been removed and the unit reset.

_(Held by `llmbench ctx-sweep` from 15:49 to 21:21 UTC.)_

## Why this agent has the card
Fen's instruction for this task: the matched-context sweep is **the priority once a
slot frees**, and if the 4-game suite has not started its model runs, take the card.
At 15:46 UTC the 4-game suite was still `queued` in
`benchmarks/gapclose/state.json` (no screen, no process).

## What is happening to run concurrently
- `think2` (gapclose STEP 4 thinking) reached its **last model, `qwen36`** at 15:49:00
  UTC — 5 of 5 models done (stock38, huihui, davidau, q4_0, ornith).
- The sweep re-asserts its server on :8080 before **every** cell, so a stray `srv.sh`
  restart from another script is detected and replaced, not measured.

## Hard rules for other agents while this lock is up
1. Do **not** start `~/bin/srv.sh`, `srv_lfm3.sh`, games, ablation, or any load on
   GPU 0 (card1) — the sweep restarts `llama-server` on :8080 and :8091 per cell.
2. Do **not** `pkill` llama-server. The sweep never uses `pkill -f`.
3. Read `benchmarks/ctx-sweep/state.json` for live progress; every finished cell is
   committed there. It is safe to read at any time.
4. If you need the card, leave `benchmarks/ctx-sweep/CARD-RELEASE-REQUEST.txt` — the
   sweep finishes the current cell and can resume later from `state.json`.

## Release
On completion the sweep runs `~/bin/srv.sh stock38mtp` (prod preset) and updates this
file to **RELEASED** with the finish time.

## Coordination findings (2026-11-03, superseded by the lock above)
- The **prod unit `qwen-longctx` fights any external sweep**: `Restart=on-failure` brings
  it back ~30 s after a stop, loading `active.gguf` at `-c 131072/262144`.
- `systemctl --user mask` **cannot** be used (a real unit file exists; no `--runtime`).
  `set-property StartLimitIntervalSec=` is rejected by this systemd.
- Therefore the sweep locks the unit with an **empty drop-in sentinel**
  `qwen-longctx.service.d/zz-ctxsweep-lock.conf` + `daemon-reload` + `stop`.
  `ctx-sweep-run.sh` deletes it, reloads, and restores `stock38mtp` when the sweep ends.
- `think2` finished all 5 thinking models (last one, qwen36, 15:56 UTC); the harness it
  runs under calls `srv.sh` once at the end, which is what put a rival server on :8080.
- Any cell measured while a second llama-server held the card is **discarded and re-run**
  (LFM3 256K, 27B 64K and 27B 128K were re-run for that reason).

## Post-run notes for whoever takes the card next
- `logic10_slot.sh` (peer) takes the card whenever `~/ctx-sweep/slot.state` is stale/absent
  and no server listens; it kills servers on :8080/:8091. During this sweep it killed a
  cell mid-prefill twice. Before launching again, set slot.state to `BUSY` first and keep a
  peer (notify) aware of the start time.
- `logic10_seal.sh` waits for `~/ctx-sweep/ALLDONE`, which now exists; it may start the
  production restore on its own. If a restore is already healthy (n_ctx 131072,
  `active` + `enabled`), no action is needed.
