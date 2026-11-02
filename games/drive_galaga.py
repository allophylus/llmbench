#!/usr/bin/env python3
"""drive_galaga.py — play a model-written Galaga-like shooter, frozen key timeline.

usage: python3 drive_galaga.py <game.py> <metrics.json> [out.cast]

The game runs on a 100x30 pty (TERM=xterm) and TIMELINE is replayed on the wall clock:
one SPACE per second plus a 2 s left/right sweep reversed every 8 presses, for ~92 s. The
timeline is a module-level list of (t_seconds, key) tuples and knows nothing about the
game's internals, so every implementation gets the same input.

Scoring reads only the game's own contract, off the RENDERED screen (curses re-sends just
the digits that change, so the byte stream is not a usable transcript):
  score          max `STATUS score=`
  aliens_killed  `GAMEOVER aliens_killed=`, else max(score)//10 when the run times out
  survived_s     max `STATUS t=`
  lives_lost     3 - min(`STATUS lives=`), never negative
  crashed        1 on a mid-play traceback, no STATUS at all, or a non-zero exit

Hard timeout 120 s; the pty child is SIGKILLed on timeout. Writes metrics.json and an
asciicast v2 recording.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptybench

WARMUP = 3.0          # s before the first key: interpreter start + curses init
PLAY = 92.0


def build_timeline():
    ev = []
    tm = WARMUP - 0.5
    d = "RIGHT"
    n = 0
    while tm < WARMUP + PLAY:
        ev.append((round(tm, 2), d))
        ev.append((round(tm + 0.125, 2), d))
        n += 2
        if n % 16 == 0:                 # 8 presses (16 cells) each way, 2 s per leg
            d = "RIGHT" if d == "LEFT" else "LEFT"
        tm += 0.25
    tf = WARMUP + 0.4
    while tf < WARMUP + PLAY:
        ev.append((round(tf, 2), "SPACE"))
        tf += 1.0
    ev.sort(key=lambda e: (e[0], 0 if e[1] in ("LEFT", "RIGHT") else 1))
    return ev


TIMELINE = build_timeline()


def main():
    game = os.path.abspath(sys.argv[1])
    met = os.path.abspath(sys.argv[2])
    cast = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 else met + ".cast"

    t_max = float(os.environ.get("GAMEBENCH_T_MAX", "120"))
    res = ptybench.run(game, TIMELINE, t_max=t_max)

    st_re = re.compile(r"STATUS\s+score=(\d+)\s+lives=(\d+)\s+wave=(\d+)\s+aliens=(\d+)\s+t=(\d+)")
    go_re = re.compile(r"GAMEOVER\s+score=(\d+)\s+aliens_killed=(\d+)\s+t=(\d+)")

    statuses = []
    for row in res.last_row(ptybench.ROWS - 1):
        m = st_re.search(row)
        if m:
            statuses.append(tuple(int(g) for g in m.groups()))
    # a sample can land on a half-repainted row; a game second can never exceed wall time
    statuses = [s for s in statuses if 0 <= s[4] <= res.duration + 2]
    gm = go_re.search(res.text)

    score = max([s[0] for s in statuses], default=0)
    survived = max([s[4] for s in statuses], default=0)
    lives_min = min([s[1] for s in statuses], default=3)
    kills = None
    if gm:
        score = max(score, int(gm.group(1)))
        kills = int(gm.group(2))
        survived = max(survived, int(gm.group(3)))
    if kills is None:
        kills = score // 10

    crash_lines = ptybench.crashes(res)
    field = 0
    for lines_ in res.screens:
        body = "\n".join(lines_)
        if "A" in body and ("^" in body or "<" in body or ">" in body):
            field = 1
            break
    crashed = 1 if (crash_lines or not statuses or res.exit_code not in (0, None)) else 0

    metrics = {
        "cell": "game-galaga",
        "score": int(score),
        "aliens_killed": int(kills),
        "survived_s": int(survived),
        "lives_lost": int(max(0, 3 - lives_min)),
        "crashed": int(crashed),
        "frames": int(res.frames),
        "cast": cast,
        # --- supporting evidence (not part of the cell score) ---------------
        "crash_before_10s": int(1 if (crashed and survived < 10) else 0),
        "status_frames": len(statuses),
        "field_drawn": field,
        "gameover": bool(gm),
        "gameover_line": gm.group(0) if gm else None,
        "ended_at_s": res.t_event,
        "wave_max": max([s[2] for s in statuses], default=0),
        "aliens_left_min": min([s[3] for s in statuses], default=0),
        "crash_samples": crash_lines,
        "exit_code": res.exit_code,
        "killed": res.killed,
        "duration_s": round(res.duration, 1),
        "output_bytes": len(res.raw),
        "timeline_events": len(TIMELINE),
    }

    ptybench.write_cast(cast, res, "drive_galaga.py %s" % os.path.basename(game))
    with open(met, "w") as f:
        json.dump(metrics, f, indent=1)
    with open(met + ".raw.txt", "wb") as f:
        f.write(res.raw)
    with open(met + ".screen.txt", "w") as f:
        f.write("\n".join(res.screens[-1] if res.screens else []))
    with open(met + ".summary", "w") as f:
        f.write(json.dumps(metrics) + "\n")
    print(json.dumps(metrics, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
