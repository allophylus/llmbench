CTX-SWEEP SLOT PROTOCOL (for logic10_slot.sh and any other agent)
==================================================================
File: ~/ctx-sweep/slot.state   (written atomically by ctx_sweep.py)

  BUSY <HH:MM:SS> <model>|<ctx>   -> a cell is LOADING or MEASURING.
                                     Do NOT touch :8080/:8091, do NOT kill llama-server.
  IDLE <HH:MM:SS> after <cell>    -> between cells. Safe to take the card.

Rules:
 1. Take the card ONLY when slot.state reads IDLE and a re-read 5 s later still says
    IDLE (ctx_sweep writes BUSY *before* it starts a server).
 2. Do NOT kill the sweep's server while slot.state says BUSY: a kill mid-cell voids
    that cell and it gets re-run.
 3. To hold the card: create qwen-longctx.service.d/zz-HOLDER.conf, and REMOVE it when
    done. ctx_sweep daemon-reloads at each cell start; a leftover holder drop-in makes
    the sweep's own unit-lock step fail.
 4. ctx_sweep locks the prod unit with zz-ctxsweep-lock.conf. That is expected; ignore.
 5. When the sweep finishes it writes ALLDONE and restores stock38mtp.

Status: read ~/ctx-sweep/state.json (one entry per finished cell) or tail ~/ctx-sweep/run1.log
