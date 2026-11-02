#!/usr/bin/env python3
"""PHYSICS_REFERENCE.py — canonical implementation of the llmbench PHYSICS cell (v1).

Reference only: used to prove drive_physics.py can score, never shipped as a model result.

Integer-only kinematics, one tick = 0.1 s, 150 ticks, no input at all:

  * ball i (i=1..3) starts at x=10+15*i, y=2, vy=0, vx=3-i   -> (25,2,0,+2) (40,2,0,+1) (55,2,0,0)
  * each tick, in this exact order:
      1. a ball that is NOT at rest: vy += 1
      2. x += vx ; y += vy
      3. x < 1  -> x = 2 - x,  vx = -vx      (perfect wall reflection)
         x > 98 -> x = 196 - x, vx = -vx
      4. y > 28 -> y = 28, vy = -int(vy * 0.8)     (floor, integer truncation)
      5. y < 1  -> y = 1,  vy = -vy                (ceiling)
  * "at rest" = y == 28 and vy == 0: such a ball skips step 1 and slides with vx only.

The screen draws the physics box (cols 1..98, rows 1..28) and one line per frame:
  STATUS t=<T> b1=(<x>,<y>,<vy>) b2=(<x>,<y>,<vy>) b3=(<x>,<y>,<vy>)
All values are signed decimal integers. After 150 frames: GAMEOVER t=150.
"""
import curses
import random
import sys
import time

COLS, ROWS = 100, 30
FPS = 10
TICK = 1.0 / FPS
FRAMES = 150
X_LO, X_HI = 1, 98
Y_LO, Y_HI = 1, 28


def rest(b):
    return b[1] == Y_HI and b[2] == 0


def step(balls):
    for b in balls:
        if not rest(b):
            b[2] += 1
        b[0] += b[3]
        b[1] += b[2]
        if b[0] < X_LO:
            b[0] = 2 * X_LO - b[0]
            b[3] = -b[3]
        elif b[0] > X_HI:
            b[0] = 2 * X_HI - b[0]
            b[3] = -b[3]
        if b[1] > Y_HI:
            b[1] = Y_HI
            b[2] = -int(b[2] * 0.8)
        elif b[1] < Y_LO:
            b[1] = Y_LO
            if b[2] < 0:
                b[2] = -b[2]


def status_line(t, balls):
    return "STATUS t=%d " % t + " ".join(
        "b%d=(%d,%d,%d)" % (i + 1, b[0], b[1], b[2]) for i, b in enumerate(balls))


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

    balls = [[10 + 15 * i, 2, 0, 3 - i] for i in (1, 2, 3)]

    try:
        for t in range(FRAMES):
            stdscr.erase()
            for c in range(X_LO, X_HI + 1):
                try:
                    stdscr.addstr(Y_LO, c, "-")
                    stdscr.addstr(Y_HI, c, "-")
                except curses.error:
                    pass
            for r in range(Y_LO, Y_HI + 1):
                try:
                    stdscr.addstr(r, X_LO, "|")
                    stdscr.addstr(r, X_HI, "|")
                except curses.error:
                    pass
            for ch, (r, c) in (("+", (Y_LO, X_LO)), ("+", (Y_LO, X_HI)),
                               ("+", (Y_HI, X_LO)), ("+", (Y_HI, X_HI))):
                try:
                    stdscr.addstr(r, c, ch)
                except curses.error:
                    pass
            for i, b in enumerate(balls):
                if X_LO <= b[0] <= X_HI and Y_LO <= b[1] <= Y_HI:
                    try:
                        stdscr.addstr(b[1], b[0], str(i + 1))
                    except curses.error:
                        pass
            line = status_line(t, balls)
            try:
                stdscr.addstr(ROWS - 1, 0, line[:COLS - 1])
            except curses.error:
                pass
            stdscr.refresh()
            time.sleep(TICK)
            step(balls)
    finally:
        try:
            curses.nocbreak()
            stdscr.keypad(False)
            curses.echo()
            curses.endwin()
        except curses.error:
            pass

    print(status_line(FRAMES, balls))
    print("GAMEOVER t=%d" % FRAMES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
