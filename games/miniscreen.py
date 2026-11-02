#!/usr/bin/env python3
"""miniscreen.py — deliberately plain VT emulator used for scoring frames.

Local copy of llmbench/tetris/miniscreen.py with ICH/DCH/ECH/IL/DL implemented to real VT
semantics (the tetris copy blanks the cursor row on DL, which is wrong for curses' line
optimisations; curses emits ESC[1P on the physics cell and the old model corrupted rows).

Characters are classified explicitly (chr(27) escaped, nothing implicit), text runs are
copied next to each other, and only the control sequences curses really emits are acted on.
"""
import re

ESC = chr(27)
CSI_RE = re.compile(ESC + r"\[([0-9;?]*)([A-Za-z@`])")
SIMPLE_RE = re.compile(ESC + r"(?:[()*+][0-9A-Za-z]|[=>78Mc])")
OSC_RE = re.compile(ESC + r"\][^\x07" + ESC + r"]*(?:\x07|" + ESC + r"\\)")
PRINT_RE = re.compile(r"[^" + ESC + r"\r\n\b\x07\x00]+")


class MiniScreen:
    def __init__(self, rows=30, cols=100):
        self.rows, self.cols = rows, cols
        self.r = self.c = 0
        self.buf = [[" "] * cols for _ in range(rows)]
        self.top, self.bot = 0, rows - 1
        self.moves = 0

    # -- scrolling ------------------------------------------------------
    def _up(self, n=1):
        for _ in range(n):
            del self.buf[self.top]
            self.buf.insert(self.bot, [" "] * self.cols)

    def _down(self, n=1):
        for _ in range(n):
            del self.buf[self.bot]
            self.buf.insert(self.top, [" "] * self.cols)

    def _lf(self):
        if self.r == self.bot:
            self._up()
        elif self.r < self.rows - 1:
            self.r += 1

    def _ri(self):
        if self.r == self.top:
            self._down()
        elif self.r > 0:
            self.r -= 1

    # -- main loop ------------------------------------------------------
    def feed(self, text):
        text = OSC_RE.sub("", text)
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ord(ch) == 27:
                m = CSI_RE.match(text, i)
                if m:
                    self._csi(m.group(1), m.group(2))
                    i = m.end()
                    continue
                if i + 1 < n and text[i + 1] == "M":
                    self._ri(); i += 2; continue
                if i + 1 < n and text[i + 1] == "D":
                    self._lf(); i += 2; continue
                m = SIMPLE_RE.match(text, i)
                i = m.end() if m else min(n, i + 2)
                continue
            if ord(ch) == 13:
                self.c = 0; i += 1; continue
            if ord(ch) == 10:
                self._lf(); i += 1; continue
            if ord(ch) == 8:
                self.c = max(0, self.c - 1); i += 1; continue
            if ord(ch) == 7 or ord(ch) == 0:
                i += 1; continue
            m = PRINT_RE.match(text, i)
            run = m.group(0)
            i = m.end()
            for ch2 in run:
                if self.r >= self.rows:
                    break
                if 0 <= self.c < self.cols:
                    self.buf[self.r][self.c] = ch2
                self.c += 1
                if self.c >= self.cols:
                    self.c = 0
                    self._lf()
                    if self.r >= self.rows:
                        break
        return self

    def _csi(self, params, final):
        ps = [p for p in params.replace("?", "").split(";") if p != ""]
        nums = [int(p) if p.isdigit() else 0 for p in ps]
        a = nums[0] if (nums and nums[0]) else 1
        if final in ("H", "f"):
            self.r = max(0, min(self.rows - 1, (nums[0] if nums and nums[0] else 1) - 1))
            self.c = max(0, min(self.cols - 1, (nums[1] if len(nums) > 1 and nums[1] else 1) - 1))
        elif final == "d":
            self.r = max(0, min(self.rows - 1, a - 1))
        elif final in ("G", "`"):
            self.c = max(0, min(self.cols - 1, a - 1))
        elif final == "A":
            self.r = max(0, self.r - a)
        elif final == "B":
            self.r = min(self.rows - 1, self.r + a)
        elif final == "C":
            self.c = min(self.cols - 1, self.c + a)
        elif final == "D":
            self.c = max(0, self.c - a)
        elif final == "E":
            self.r = min(self.rows - 1, self.r + a); self.c = 0
        elif final == "F":
            self.r = max(0, self.r - a); self.c = 0
        elif final == "J":
            for rr in range(self.r, self.rows):
                self.buf[rr] = [" "] * self.cols
        elif final == "K":
            for cc in range(self.c, self.cols):
                self.buf[self.r][cc] = " "
        elif final == "M":                        # DL — delete lines, shift region up
            for _ in range(a):
                if self.top <= self.r <= self.bot:
                    del self.buf[self.r]
                    self.buf.insert(self.bot, [" "] * self.cols)
            self.c = 0
        elif final == "L":                        # IL — insert blank lines, shift down
            for _ in range(a):
                if self.top <= self.r <= self.bot:
                    del self.buf[self.bot]
                    self.buf.insert(self.r, [" "] * self.cols)
            self.c = 0
        elif final == "@":                        # ICH — insert blanks at the cursor
            row = self.buf[self.r]
            for _ in range(a):
                row.insert(self.c, " ")
                row.pop()
        elif final == "P":                        # DCH — delete chars, shift the rest left
            row = self.buf[self.r]
            for _ in range(min(a, self.cols - self.c)):
                del row[self.c]
                row.append(" ")
        elif final == "X":                        # ECH — blank chars from the cursor
            for cc in range(self.c, min(self.cols, self.c + a)):
                self.buf[self.r][cc] = " "
        elif final == "r":                        # DECSTBM — curses sets it before every IL/DL
            top = nums[0] if len(nums) > 0 and nums[0] else 1
            bot = nums[1] if len(nums) > 1 and nums[1] else self.rows
            self.top, self.bot = top - 1, min(self.rows - 1, bot - 1)
            self.r, self.c = self.top, 0
        # m / h / l / n / c / q and friends: no cell effect

    def lines(self):
        return ["".join(row).rstrip() for row in self.buf]
