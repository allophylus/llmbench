#!/usr/bin/env python3
"""drive_physics.py — run the llmbench physics/graphics cell twice and check the physics.

usage: python3 drive_physics.py <game.py> <metrics.json> [out.cast]

No keys are sent: the cell is a 150-frame deterministic simulation. The driver reads the
`STATUS t=.. b1=(x,y,vy) b2=(x,y,vy) b3=(x,y,vy)` line off the rendered bottom row on
every sample, then scores five independent checks:

  a_monotone_fall   while a ball is above the floor (y<28) its vy never decreases
  b_bounce          on each floor bounce vy == -int(prev_vy*0.8) within +-1, vy<=0 and
                    |vy|<=|prev_vy|, for >=80% of bounce events (and >=1 event)
  c_no_tunneling    y stays inside 1..28 on every frame
  d_wall_bounds     x stays inside 1..98 on every frame
  e_determinism     the game is run twice; both STATUS streams agree on every shared frame

cell score = checks passed / 5.0  (0.0 .. 1.0)
Hard timeout 45 s per run; each pty child is SIGKILLed on timeout.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptybench

RE_STATUS = re.compile(
    r"STATUS\s+t=(\d+)\s+"
    r"b1=\((-?\d+),(-?\d+),(-?\d+)\)\s+"
    r"b2=\((-?\d+),(-?\d+),(-?\d+)\)\s+"
    r"b3=\((-?\d+),(-?\d+),(-?\d+)\)")
RE_GAMEOVER = re.compile(r"GAMEOVER\s+t=(\d+)")


def collect(res):
    """Sample the rendered STATUS row into {t: [(x,y,vy)]*3}, ignoring duplicates."""
    frames = {}
    for row in res.last_row(ptybench.ROWS - 1):
        m = RE_STATUS.search(row)
        if not m:
            continue
        g = [int(v) for v in m.groups()]
        frames[g[0]] = [(g[1], g[2], g[3]), (g[4], g[5], g[6]), (g[7], g[8], g[9])]
    for m in RE_STATUS.finditer(res.text):          # last printed frame after endwin
        g = [int(v) for v in m.groups()]
        frames.setdefault(g[0], [(g[1], g[2], g[3]), (g[4], g[5], g[6]), (g[7], g[8], g[9])])
    return frames


def check_fall(frames):
    ts = sorted(frames)
    bad = 0
    for a, b in zip(ts, ts[1:]):
        for i in range(3):
            pa, pb = frames[a][i], frames[b][i]
            if pb[2] >= pa[2]:
                continue
            # the only legal drop is a floor bounce: vy was positive and the ball
            # crossed (or was already clamped to) row 28 during this tick
            bounce = (pa[2] > 0) and (pa[1] >= 28 or pa[1] + pa[2] > 28)
            if not bounce:
                bad += 1
    return bad == 0 and len(ts) > 1, {"decreases_above_floor": bad}


def check_bounce(frames):
    ts = sorted(frames)
    events, ok = 0, 0
    samples = []
    for a, b in zip(ts, ts[1:]):
        for i in range(3):
            pa, pb = frames[a][i], frames[b][i]
            if pa[2] > 0 and pb[2] < 0:                 # crossed zero: floor bounce
                events += 1
                want = -int(pa[2] * 0.8)
                good = abs(pb[2] - want) <= 1 and pb[2] <= 0 and abs(pb[2]) <= abs(pa[2])
                ok += 1 if good else 0
                if len(samples) < 6:
                    samples.append({"prev_vy": pa[2], "vy": pb[2], "want": want})
    frac = (ok / events) if events else 0.0
    return events >= 1 and frac >= 0.8, {"bounce_events": events, "consistent": ok,
                                         "fraction": round(frac, 3), "samples": samples}


def check_bounds(frames, idx, lo, hi):
    bad = 0
    for t, balls in frames.items():
        for b in balls:
            if not (lo <= b[idx] <= hi):
                bad += 1
    return bad == 0 and len(frames) > 0, {"violations": bad}


def check_determinism(a, b):
    common = set(a) & set(b)
    if not common:
        return False, {"common_frames": 0}
    same = sum(1 for t in common if a[t] == b[t])
    presence = len(common) / max(len(a), len(b), 1)
    ok = same == len(common) and presence >= 0.9 and len(common) >= 50
    return ok, {"common_frames": len(common), "identical_frames": same,
                "presence": round(presence, 3)}


def main():
    game = os.path.abspath(sys.argv[1])
    met = os.path.abspath(sys.argv[2])
    cast = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 else met + ".cast"

    t_max = float(os.environ.get("GAMEBENCH_T_MAX", "45"))
    res1 = ptybench.run(game, [], t_max=t_max)
    res2 = ptybench.run(game, [], t_max=t_max)
    f1, f2 = collect(res1), collect(res2)

    a_ok, a_ev = check_fall(f1)
    b_ok, b_ev = check_bounce(f1)
    c_ok, c_ev = check_bounds(f1, 1, 1, 28)
    d_ok, d_ev = check_bounds(f1, 0, 1, 98)
    e_ok, e_ev = check_determinism(f1, f2)

    checks = {"a_monotone_fall": a_ok, "b_bounce": b_ok, "c_no_tunneling": c_ok,
              "d_wall_bounds": d_ok, "e_determinism": e_ok}
    passed = sum(1 for v in checks.values() if v)

    gm = RE_GAMEOVER.search(res1.text)
    crash_lines = ptybench.crashes(res1)
    crashed = 1 if (crash_lines or not f1 or res1.exit_code not in (0, None)) else 0

    metrics = {
        "cell": "gfx-physics",
        "score": round(passed / 5.0, 2),
        "checks_passed": passed,
        "checks": {k: int(v) for k, v in checks.items()},
        "crashed": int(crashed),
        "frames": int(res1.frames),
        "cast": cast,
        # --- supporting evidence -------------------------------------------
        "status_frames": len(f1),
        "status_frames_run2": len(f2),
        "gameover": bool(gm),
        "gameover_t": int(gm.group(1)) if gm else None,
        "detail": {"fall": a_ev, "bounce": b_ev, "tunneling": c_ev,
                   "walls": d_ev, "determinism": e_ev},
        "crash_samples": crash_lines,
        "exit_code": res1.exit_code,
        "killed": res1.killed,
        "duration_s": round(res1.duration + res2.duration, 1),
    }

    ptybench.write_cast(cast, res1, "drive_physics.py %s" % os.path.basename(game))
    with open(met, "w") as f:
        json.dump(metrics, f, indent=1)
    with open(met + ".raw.txt", "wb") as f:
        f.write(res1.raw)
    with open(met + ".screen.txt", "w") as f:
        f.write("\n".join(res1.screens[-1] if res1.screens else []))
    with open(met + ".summary", "w") as f:
        f.write(json.dumps(metrics) + "\n")
    print(json.dumps(metrics, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
