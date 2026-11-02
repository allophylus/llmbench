#!/usr/bin/env python3
"""GALAGA_REFERENCE.py — canonical implementation of the llmbench GALAGA cell (v1).

Reference only: used to prove drive_galaga.py can score, never shipped as a model result.
Implements GALAGA_PROMPT.md clause by clause, deterministically: random.seed(1337) at
start-up and a fixed 20 Hz logic tick, so the whole run is a pure function of the key
timeline.

Game rules implemented (must match the prompt exactly):
  * 100x30 terminal, playable columns 1..98, playable rows 2..24, ship row 24.
  * 5 columns x 4 rows of 'A' aliens, spacing 16 x 2, top-left alien starts at (10, 4).
  * formation drifts +/-1 column every 10 ticks (0.5 s), bouncing at the playfield edges;
    meanwhile it steps DOWN one row every 12 s OR every 4 player shots, whichever first.
  * player fires one bullet at a time, bullet travels 2 rows per tick and hits an alien
    in either cell it passes through.
  * exactly one random living alien fires straight down every 2.0 s.
  * bullet/alien hit: alien dies, score += 10. alien bullet on the ship cell, or any alien
    reaching the ship row: life lost; 3 lives, 2 s blinking invulnerability after a hit.
  * GAMEOVER when lives reach 0 or the formation reaches the ship row.
"""
import curses
import random
import sys
import time

COLS, ROWS = 100, 30
X_LO, X_HI = 1, 98
Y_TOP, Y_BOT = 2, 24
SHIP_ROW = 24
FPS = 20
TICK = 1.0 / FPS

STEP_SECS = 12
STEP_SHOTS = 4
BULLET_TICKS = 40          # one alien bullet every 2.0 s
INVULN_TICKS = 40          # 2 s of blinking invulnerability

ALIEN_X0, ALIEN_DX = 10, 16
ALIEN_Y0, ALIEN_DY = 4, 2
ALIEN_NC, ALIEN_NR = 5, 4

DRIFT_TICKS = 10         # formation drifts 1 column every 0.5 s


def new_formation():
    return [[ALIEN_X0 + c * ALIEN_DX, ALIEN_Y0 + r * ALIEN_DY, True]
            for r in range(ALIEN_NR) for c in range(ALIEN_NC)]


def blank_grid():
    return [[" "] * COLS for _ in range(ROWS)]


def frame_text(grid, status):
    rows = []
    for r in range(ROWS):
        rows.append("".join(grid[r])[:COLS - 1])
    rows[ROWS - 1] = status[:COLS - 1]
    return rows


def read_key(stdscr):
    ch = stdscr.getch()
    if ch == -1:
        return None
    if ch == 27:                                  # arrow keys arrive as ESC [ A/B/C/D
        ch2 = stdscr.getch()
        if ch2 == -1:
            return None
        if ch2 == ord("["):
            ch3 = stdscr.getch()
            if ch3 in (ord("D"), ord("C"), ord("A"), ord("B")):
                return {ord("D"): "left", ord("C"): "right",
                        ord("A"): "up", ord("B"): "down"}[ch3]
        return None
    if ch in (ord("q"), ord("Q")):
        return "quit"
    if ch == ord(" "):
        return "fire"
    if ch in (ord("<"), ord(",") , ord("h")):
        return "left"
    if ch in (ord(">"), ord("."), ord("l")):
        return "right"
    return None


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

    aliens = new_formation()
    ship_x = 48
    ship_y = SHIP_ROW
    bullet = None                # (x, y) or None — exactly one player bullet
    alien_bullets = []           # [(x, y)]
    score = 0
    kills = 0
    lives = 3
    wave = 1
    shots = 0
    shots_at_step = 0
    last_step_tick = 0
    drift_dir = 1
    invuln_until = -1
    ticks = 0
    gameover = None

    try:
        while True:
            # ---- input -------------------------------------------------
            key = read_key(stdscr)
            if key == "quit":
                break
            if key == "left":
                ship_x = max(X_LO, ship_x - 2)
            elif key == "right":
                ship_x = min(X_HI, ship_x + 2)
            elif key == "fire" and bullet is None:
                bullet = (ship_x, ship_y - 1)
                shots += 1
                shots_at_step += 1

            # ---- formation drift (every 4 ticks) ------------------------
            if ticks % DRIFT_TICKS == 0 and ticks:
                moved = [(a[0] + drift_dir, a[1]) for a in aliens if a[2]]
                if any(x < X_LO or x > X_HI for x, _ in moved):
                    drift_dir = -drift_dir
                else:
                    for a in aliens:
                        if a[2]:
                            a[0] += drift_dir

            # ---- formation step down ------------------------------------
            stepped = False
            if (ticks - last_step_tick) >= STEP_SECS * FPS:
                stepped = True
            if shots_at_step >= STEP_SHOTS:
                stepped = True
            if stepped:
                for a in aliens:
                    if a[2]:
                        a[1] += 1
                last_step_tick = ticks
                shots_at_step = 0

            # ---- alien bullets ------------------------------------------
            if ticks % BULLET_TICKS == 0:
                alive = [a for a in aliens if a[2]]
                if alive:
                    src = random.choice(alive)
                    alien_bullets.append([src[0], src[1] + 1])
            for b in alien_bullets:
                b[1] += 1
            alien_bullets = [b for b in alien_bullets if b[1] <= Y_BOT + 1]

            # ---- player bullet (2 rows/tick, both cells swept) ----------
            if bullet is not None:
                bx, by = bullet
                hit = None
                for yy in (by - 1, by - 2):
                    for a in aliens:
                        if a[2] and a[0] == bx and a[1] == yy:
                            hit = a
                            break
                    if hit is not None:
                        break
                if hit is not None:
                    hit[2] = False
                    score += 10
                    kills += 1
                    bullet = None
                else:
                    by -= 2
                    bullet = None if by < Y_TOP else (bx, by)

            # ---- collisions with the ship --------------------------------
            invulnerable = ticks < invuln_until
            if not invulnerable:
                hit = False
                for b in alien_bullets:
                    if b[1] == ship_y and b[0] == ship_x:
                        hit = True
                if hit:
                    alien_bullets = [b for b in alien_bullets
                                     if not (b[1] == ship_y and b[0] == ship_x)]
                    lives -= 1
                    invuln_until = ticks + INVULN_TICKS

            alive = [a for a in aliens if a[2]]
            if not alive:
                wave += 1
                aliens = new_formation()
                alive = [a for a in aliens if a[2]]
            reached = any(a[1] >= SHIP_ROW for a in alive)
            if lives <= 0:
                gameover = "lives"
            elif reached:
                gameover = "invaded"
            if gameover:
                break

            # ---- draw ----------------------------------------------------
            grid = blank_grid()
            grid[1][0] = "+"
            for c in range(1, COLS - 1):
                grid[1][c] = "-"
                grid[Y_BOT + 1][c] = "-"
            grid[1][COLS - 1] = "+"
            grid[Y_BOT + 1][0] = "+"
            grid[Y_BOT + 1][COLS - 1] = "+"
            for r in range(2, Y_BOT + 1):
                grid[r][0] = "|"
                grid[r][COLS - 1] = "|"
            for a in alive:
                if Y_TOP <= a[1] <= Y_BOT:
                    grid[a[1]][a[0]] = "A"
            for b in alien_bullets:
                if Y_TOP <= b[1] <= Y_BOT:
                    grid[b[1]][b[0]] = "!"
            if bullet is not None and Y_TOP <= bullet[1] <= Y_BOT:
                grid[bullet[1]][bullet[0]] = "|"
            blink = invulnerable and (ticks // 4) % 2 == 1
            if not blink:
                grid[ship_y][ship_x] = "^"
            status = "STATUS score=%d lives=%d wave=%d aliens=%d t=%d" % (
                score, max(lives, 0), wave, len(alive), ticks // FPS)
            for r, line in enumerate(frame_text(grid, status)):
                try:
                    stdscr.addstr(r, 0, line)
                except curses.error:
                    pass
            stdscr.refresh()

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

    print("STATUS score=%d lives=%d wave=%d aliens=%d t=%d" % (
        score, max(lives, 0), wave, len([a for a in aliens if a[2]]), ticks // FPS))
    print("GAMEOVER score=%d aliens_killed=%d t=%d" % (score, kills, ticks // FPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
