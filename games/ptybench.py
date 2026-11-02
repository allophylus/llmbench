#!/usr/bin/env python3
"""ptybench.py — shared pty capture rig for the llmbench game cells.

One job: run a curses game in a 100x30 pty, replay a frozen wall-clock key timeline, keep
a faithful VT screen model of everything the game drew, and hand back the evidence.

Design notes (why it looks like this):
  * The screen model is PERSISTENT across the whole run: a curses app only transmits the
    cells that changed, so per-chunk emulation is the only way to reconstruct each frame.
  * A frame boundary is a gap of >FRAME_GAP s in the byte stream, or 0.25 s of continuous
    output (for implementations that never sleep between refreshes). Both are needed; the
    first alone stalls on back-to-back repaints.
  * A truncated escape sequence at a frame boundary is carried into the next batch, so a
    split never corrupts the model.
  * Hard wall-clock timeout (T_MAX) with SIGKILL on the pty child: a driver must never hang
    because a model's game blocks or loops forever.
"""
import codecs
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from miniscreen import MiniScreen

COLS, ROWS = 100, 30
FRAME_GAP = 0.02           # s of output silence that closes a screen sample
BATCH_MAX = 0.25           # s of continuous output before forcing a sample
KEYMAP = {
    "LEFT": b"\x1b[D", "RIGHT": b"\x1b[C", "UP": b"\x1b[A", "DOWN": b"\x1b[B",
    "SPACE": b" ", "X": b"x", "Q": b"q", "ENTER": b"\r",
}

_INCOMPLETE = re.compile(r"\x1b\[[0-9;?]*$")
_LONE_ESC = re.compile(r"\x1b(\[[0-9;?]*)?$")


def _split_incomplete(s):
    """Return (complete_prefix, carried_tail) so a sample never cuts an escape sequence."""
    m = _INCOMPLETE.search(s)
    if m:
        return s[:m.start()], s[m.start():]
    if s.endswith("\x1b"):
        return s[:-1], "\x1b"
    return s, ""


class Run:
    def __init__(self):
        self.raw = bytearray()
        self.casts = []
        self.screens = []
        self.frames = 0
        self.exit_code = None
        self.killed = None
        self.duration = 0.0
        self.t_event = None            # wall time (s) of the first GAMEOVER sighting
        self._status_cache = {}

    @property
    def text(self):
        return self.raw.decode("utf-8", "replace")

    def last_row(self, row=ROWS - 1):
        """Rendered text of one screen row, sampled across the run."""
        return [s[row] for s in self.screens if row < len(s)]


def run(game, timeline, t_max=120.0, rows=ROWS, cols=COLS, stop_on=("GAMEOVER",)):
    """Run `game` under a pty and replay `timeline` [(t_seconds, keyname), ...]."""
    game = os.path.abspath(game)
    res = Run()
    t0 = time.time()

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, bytearray(struct.pack("HHHH", rows, cols, 0, 0)))
    env = dict(os.environ, TERM="xterm", LANG="C.UTF-8", LC_ALL="C.UTF-8",
               COLUMNS=str(cols), LINES=str(rows))
    pid = os.fork()
    if pid == 0:
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        os.dup2(slave, 0)
        os.dup2(slave, 1)
        os.dup2(slave, 2)
        os.close(master)
        os.close(slave)
        try:
            os.execvpe(sys.executable, [sys.executable, game], env)
        finally:
            os._exit(127)
    os.close(slave)

    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    scr = MiniScreen(rows, cols)
    pending = ""
    last_screen = None
    batch_start = 0.0
    events = sorted(timeline, key=lambda e: e[0])
    ei = 0
    last_data = time.time()

    def pump(timeout):
        try:
            r, _, _ = select.select([master], [], [], timeout)
        except (OSError, ValueError):
            return False
        if not r:
            return None
        try:
            d = os.read(master, 65536)
        except OSError:
            return False
        if not d:
            return False
        res.raw.extend(d)
        chunk = decoder.decode(d)
        res.casts.append((round(time.time() - t0, 3), chunk))
        return chunk

    def sample():
        nonlocal pending, last_screen
        if not pending:
            return
        text, pending = _split_incomplete(pending)
        if not text:
            return
        scr.feed(text)
        lines = tuple(scr.lines())
        if lines != last_screen:
            res.frames += 1
            last_screen = lines
            res.screens.append(lines)

    last_data = time.time()
    try:
        while True:
            now = time.time() - t0
            if now > t_max:
                res.killed = "T+%ds" % int(t_max)
                break
            while ei < len(events) and events[ei][0] <= now:
                try:
                    os.write(master, KEYMAP.get(events[ei][1], events[ei][1].encode()))
                except OSError:
                    break
                ei += 1
            chunk = pump(0.005)
            if chunk is False:
                break
            if chunk:
                if not pending:
                    batch_start = time.time()
                pending += chunk
                last_data = time.time()
                res._status_cache.clear()
            elif pending and (time.time() - last_data > FRAME_GAP
                              or time.time() - batch_start > BATCH_MAX):
                sample()
            if any(s.encode() in res.raw[-65536:] for s in stop_on):
                if res.t_event is None:
                    res.t_event = round(now, 2)
                end = time.time() + 1.5
                while time.time() < end:
                    c = pump(0.05)
                    if c is False:
                        break
                    if c:
                        pending += c
                break
    finally:
        sample()
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            _, st = os.waitpid(pid, 0)
            if os.WIFEXITED(st):
                res.exit_code = os.WEXITSTATUS(st)
            elif os.WIFSIGNALED(st):
                res.exit_code = -os.WTERMSIG(st)
        except ChildProcessError:
            pass
        res.duration = time.time() - t0
        try:
            os.close(master)
        except OSError:
            pass
    if res.exit_code == -9:
        res.exit_code = None       # our own kill, not a game fault
    return res


def write_cast(path, res, title=""):
    import json
    header = {"version": 2, "width": COLS, "height": ROWS,
              "timestamp": int(time.time() - res.duration), "title": title,
              "env": {"TERM": "xterm", "SHELL": "/bin/sh"}}
    with open(path, "w") as f:
        f.write(json.dumps(header) + "\n")
        for t, s in res.casts:
            f.write(json.dumps([t, "o", s]) + "\n")


TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)|^\w*Error:|^\w*Exception:")


def crashes(res, limit=5):
    return [l for l in res.text.splitlines() if TRACEBACK_RE.search(l)][:limit]
