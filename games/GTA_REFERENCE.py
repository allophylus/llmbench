#!/usr/bin/env python3
"""GTA_REFERENCE.py — canonical implementation of the llmbench GTA cell (v1).

Reference only: used to prove drive_gta.py can score, never shipped as a model result.
Implements GTA_PROMPT.md clause by clause: the hard-coded 80x20 city, one-cell arrow
driving on roads, buildings as bumps, five timed waypoints, two greedy police cars.

Determinism: no randomness is needed for a correct run (random.seed(1337) is still called
so the file satisfies the prompt), and all timers run off a fixed 20 Hz tick.
"""
import curses
import random
import sys
import time

W, H = 80, 20
COLS, ROWS = 100, 30
FPS = 20
TICK = 1.0 / FPS
OFF_Y, OFF_X = 2, 2            # where the map is drawn on the 100x30 screen
POLICE_TICKS = 10              # police move once per 0.5 s
MISSION_LIMIT = 30             # s per mission
GRACE_TICKS = 40               # 2 s of capture immunity after a capture

MAP = [
    "................................................................................",  # 0
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 1
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 2
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 3
    "................................................................................",  # 4
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 5
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 6
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 7
    "........................H.......................................................",  # 8
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 9
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 10
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 11
    "........................................P.......................................",  # 12
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 13
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 14
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 15
    "................................................................................",  # 16
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 17
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 18
    ".#######.#######.#######.#######.#######.#######.#######.#######.#######.######.",  # 19
]

SPAWN = (4, 4)
WAYPOINTS = [(24, 0), (24, 12), (64, 12), (64, 4), (8, 16)]
POLICE_START = [(40, 8), (56, 16)]


def walkable(x, y):
    return 0 <= x < W and 0 <= y < H and MAP[y][x] != "#"


def read_key(stdscr):
    ch = stdscr.getch()
    if ch == -1:
        return None
    if ch == 27:
        ch2 = stdscr.getch()
        if ch2 == -1:
            return None
        if ch2 == ord("["):
            ch3 = stdscr.getch()
            return {ord("D"): "left", ord("C"): "right",
                    ord("A"): "up", ord("B"): "down"}.get(ch3)
        return None
    if ch in (ord("q"), ord("Q")):
        return "quit"
    return None


def police_step(pol, px, py):
    dx, dy = px - pol[0], py - pol[1]
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    cands = ([(sx, 0), (0, sy)] if abs(dx) >= abs(dy) else [(0, sy), (sx, 0)])
    for cx, cy in cands:
        if cx == 0 and cy == 0:
            continue
        nx, ny = pol[0] + cx, pol[1] + cy
        if walkable(nx, ny):
            pol[0], pol[1] = nx, ny
            return


def main():
    random.seed(1337)
    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    stdscr.nodelay(True)
    stdscr.keypad(False)
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    px, py = SPAWN
    police = [list(p) for p in POLICE_START]
    score, missions, bumps = 0, 0, 0
    captures = 0
    grace_until = -1
    mission_start = 0
    ticks = 0
    reason = None

    try:
        while True:
            key = read_key(stdscr)
            if key == "quit":
                reason = "quit"
                break
            if key in ("left", "right", "up", "down"):
                nx, ny = px, py
                if key == "left":
                    nx -= 1
                elif key == "right":
                    nx += 1
                elif key == "up":
                    ny -= 1
                else:
                    ny += 1
                if walkable(nx, ny):
                    px, py = nx, ny
                    if missions < len(WAYPOINTS) and (px, py) == WAYPOINTS[missions]:
                        score += 100
                        missions += 1
                        mission_start = ticks // FPS
                        if missions == len(WAYPOINTS):
                            reason = "complete"
                else:
                    bumps += 1

            # ---- police -------------------------------------------------
            if ticks % POLICE_TICKS == 0 and ticks:
                for pol in police:
                    police_step(pol, px, py)
                if ticks >= grace_until:
                    for pol in police:
                        if (pol[0], pol[1]) == (px, py):
                            captures += 1
                            score -= 50
                            police = [list(p) for p in POLICE_START]
                            grace_until = ticks + GRACE_TICKS
                            break
                if captures >= 3:
                    reason = "busted"
                    break

            # ---- mission timer ------------------------------------------
            if missions < len(WAYPOINTS) and (ticks // FPS) - mission_start >= MISSION_LIMIT:
                reason = "mission_timeout"
            if reason:
                break

            # ---- draw ----------------------------------------------------
            dw = stdscr
            dw.erase()
            head = "CITY  score=%d  missions=%d/%d  bumps=%d  captures=%d" % (
                score, missions, len(WAYPOINTS), bumps, captures)
            try:
                dw.addstr(0, 0, head[:COLS - 1])
            except curses.error:
                pass
            for y in range(H):
                row = list(MAP[y])
                for pol in police:
                    if pol[1] == y:
                        row[pol[0]] = "C"
                if missions < len(WAYPOINTS):
                    wx, wy = WAYPOINTS[missions]
                    if wy == y:
                        row[wx] = "*"
                if py == y:
                    row[px] = "@"
                try:
                    dw.addstr(OFF_Y + y, OFF_X, "".join(row))
                except curses.error:
                    pass
            status = "STATUS x=%d y=%d score=%d missions=%d bumps=%d t=%d" % (
                px, py, score, missions, bumps, ticks // FPS)
            try:
                dw.addstr(ROWS - 1, 0, status[:COLS - 1])
            except curses.error:
                pass
            dw.refresh()

            ticks += 1
            time.sleep(TICK)
    finally:
        try:
            curses.nocbreak()
            stdscr.keypad(False)
            curses.echo()
            curses.endwin()
        except curses.error:
            pass

    t = ticks // FPS
    print("STATUS x=%d y=%d score=%d missions=%d bumps=%d t=%d" % (px, py, score, missions, bumps, t))
    print("GAMEOVER score=%d missions=%d bumps=%d t=%d" % (score, missions, bumps, t))
    print("REASON %s" % (reason or "ended"))
    for y in range(H):
        row = list(MAP[y])
        for pol in police:
            if pol[1] == y:
                row[pol[0]] = "C"
        if py == y:
            row[px] = "@"
        print("".join(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
