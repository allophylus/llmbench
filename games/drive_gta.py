#!/usr/bin/env python3
"""drive_gta.py — play a model-written top-down GTA cell, frozen key timeline.

usage: python3 drive_gta.py <game.py> <metrics.json> [out.cast]

The route is computed once, at import time, by BFS over the map that GTA_PROMPT.md
publishes: spawn (4,4) -> waypoint 1..5, one arrow key per cell, 0.12 s apart, with a
1.5 s pause on each waypoint. Nothing is read from the game being tested, so every
implementation sees the identical input; the timeline is a plain module-level list of
(t_seconds, key) tuples.

Scoring (from the rendered STATUS/GAMEOVER lines, never from pixels):
  score      `GAMEOVER score=` (or max STATUS score= when the run times out)
  missions   waypoints reached — the cell score is missions completed
  bumps      building bumps (efficiency penalty; a clean route has 0)
  survived_t max STATUS t=
  crashed    1 on a mid-play traceback, no STATUS at all, or a non-zero exit

Hard timeout 120 s; the pty child is SIGKILLed on timeout.
"""
import json
import os
import re
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptybench

WARMUP = 3.0
PRESS = 0.12               # s between single-cell moves
PAUSE = 1.5                # s parked on a completed waypoint

MAP = [
    "................................................................................",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    "................................................................................",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    "........................H.......................................................",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    "........................................P.......................................",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    "................................................................................",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",
]
H, W = len(MAP), len(MAP[0])
SPAWN = (4, 4)
WAYPOINTS = [(24, 0), (24, 12), (64, 12), (64, 4), (8, 16)]


def walkable(x, y):
    return 0 <= x < W and 0 <= y < H and MAP[y][x] != "#"


def bfs(start, goal):
    """Shortest road-only route as a list of 'left'/'right'/'up'/'down' steps."""
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for dx, dy, k in ((-1, 0, "LEFT"), (1, 0, "RIGHT"), (0, -1, "UP"), (0, 1, "DOWN")):
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt not in prev and walkable(*nxt):
                prev[nxt] = (cur, k)
                q.append(nxt)
    if goal not in prev:
        return []
    out = []
    cur = goal
    while prev[cur] is not None:
        cur, k = prev[cur]
        out.append(k)
    return out[::-1]


def build_timeline():
    ev = []
    t = WARMUP
    pos = SPAWN
    for wp in WAYPOINTS:
        for k in bfs(pos, wp):
            ev.append((round(t, 2), k))
            t += PRESS
        pos = wp
        t += PAUSE
    return ev


TIMELINE = build_timeline()


def main():
    game = os.path.abspath(sys.argv[1])
    met = os.path.abspath(sys.argv[2])
    cast = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 else met + ".cast"

    t_max = float(os.environ.get("GAMEBENCH_T_MAX", "120"))
    res = ptybench.run(game, TIMELINE, t_max=t_max)

    st_re = re.compile(r"STATUS\s+x=(\d+)\s+y=(\d+)\s+score=(-?\d+)\s+missions=(\d+)\s+bumps=(\d+)\s+t=(\d+)")
    go_re = re.compile(r"GAMEOVER\s+score=(-?\d+)\s+missions=(\d+)\s+bumps=(\d+)\s+t=(\d+)")
    reason_re = re.compile(r"REASON\s+(\w+)")

    statuses = []
    for row in res.last_row(ptybench.ROWS - 1):
        m = st_re.search(row)
        if m:
            statuses.append(tuple(int(g) for g in m.groups()))
    # a sample can land on a half-repainted row; a game second can never exceed wall time
    statuses = [s for s in statuses if 0 <= s[5] <= res.duration + 2]
    gm = go_re.search(res.text)
    reason = reason_re.search(res.text)

    score = max([s[2] for s in statuses], default=0)
    missions = max([s[3] for s in statuses], default=0)
    bumps = max([s[4] for s in statuses], default=0)
    survived = max([s[5] for s in statuses], default=0)
    if gm:
        score = int(gm.group(1))
        missions = int(gm.group(2))
        bumps = int(gm.group(3))
        survived = max(survived, int(gm.group(4)))

    crash_lines = ptybench.crashes(res)
    crashed = 1 if (crash_lines or not statuses or res.exit_code not in (0, None)) else 0
    final_map = "@" in res.text.split("GAMEOVER", 1)[-1] if "GAMEOVER" in res.text else False

    metrics = {
        "cell": "game-gta",
        "score": int(score),
        "missions": int(missions),
        "missions_target": len(WAYPOINTS),
        "bumps": int(bumps),
        "survived_t": int(survived),
        "crashed": int(crashed),
        "frames": int(res.frames),
        "cast": cast,
        # --- supporting evidence -------------------------------------------
        "reason": reason.group(1) if reason else None,
        "status_frames": len(statuses),
        "final_map_printed": int(final_map),
        "map_drawn": int(any("#" in "\n".join(s) and "*" in "\n".join(s) for s in res.screens)),
        "crash_samples": crash_lines,
        "exit_code": res.exit_code,
        "killed": res.killed,
        "duration_s": round(res.duration, 1),
        "output_bytes": len(res.raw),
        "timeline_events": len(TIMELINE),
    }

    ptybench.write_cast(cast, res, "drive_gta.py %s" % os.path.basename(game))
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
