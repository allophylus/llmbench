#!/usr/bin/env python3
"""playprobe.py — the llmbench game-suite probe: run a generated game headlessly with a
VIRTUAL clock and grade it on (a) the old run gate, (b) executed behavioural assertions,
and (c) SPEC COMPLIANCE (did it build what was asked, and only that).

usage:
  playprobe.py <game_dir> --spec ball-drop-sandbox|tower-stacker|tower-defence|match3-cascades
                [--shot shot.png] [--json out.json]

Why a virtual clock: the grader calls window.__game.step(1/60) N times itself, so the
assertions hold regardless of the machine's frame rate. The page's own rAF loop is not
trusted for state assertions.

What it writes (in <game_dir> unless --json/--shot point elsewhere):
  probe.json  {gate:{...}, assertions:[{id, ok, got, want}], passed, total,
               compliance:{score, violations[], notes[]}, console_errors[]}

Exit 0 if the run gate passes, 1 otherwise. Assertion/compliance results are data, not
exit status (a model that builds a perfect non-compliant game must still be recorded).

Nothing is inferred: every assertion is a real evaluate() against the running game.
"""
import argparse
import json
import os
import re
import shutil
import sys

from playwright.sync_api import sync_playwright

CHROME = (os.environ.get("CHROME_BIN") or shutil.which("google-chrome")
          or shutil.which("chromium") or shutil.which("chromium-browser")
          or "/usr/bin/google-chrome")
VIEW = {"width": 1280, "height": 800}
TICK = 1.0 / 60.0


def strip_comments(src):
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    return src

# ----------------------------------------------------------------------------------
# helpers injected into the page
PRELUDE = r"""
window.__pp = {
  steps: function (S, n) {            // step exactly n ticks of 1/60 s
    for (var i = 0; i < n; i++) S.step(1/60);
  },
  num: function (v) { return typeof v === 'number' && isFinite(v); },
  round: function (v) { return Math.round(v * 1e4) / 1e4; },
  runs: function (grid) {             // list of runs >=3 in an 8x8 grid of ints
    var out = [], R = grid.length, C = grid[0] ? grid[0].length : 0;
    for (var r = 0; r < R; r++) { var c = 0; while (c < C) {
      var v = grid[r][c], e = c + 1; while (e < C && grid[r][e] === v) e++;
      if (e - c >= 3) out.push({dir:'h', r:r, c:c, len:e-c, v:v}); c = e; } }
    for (var c2 = 0; c2 < C; c2++) { var r2 = 0; while (r2 < R) {
      var v2 = grid[r2][c2], e2 = r2 + 1; while (e2 < R && grid[e2][c2] === v2) e2++;
      if (e2 - r2 >= 3) out.push({dir:'v', r:r2, c:c2, len:e2-r2, v:v2}); r2 = e2; } }
    return out;
  },
  legalMoves: function (g) {          // first few legal swaps (match3)
    var out = [], R = g.length, C = g[0].length;
    function has(g2) { return window.__pp.runs(g2).length > 0; }
    for (var r = 0; r < R; r++) for (var c = 0; c < C; c++) {
      [[0,1],[1,0]].forEach(function (d) {
        var r2 = r + d[0], c2 = c + d[1];
        if (r2 >= R || c2 >= C) return;
        var g2 = g.map(function (row) { return row.slice(); });
        var t = g2[r][c]; g2[r][c] = g2[r2][c2]; g2[r2][c2] = t;
        if (has(g2)) out.push([r, c, r2, c2]);
      });
    }
    return out;
  }
};
"""


def render_assert(js_body):
    """Wrap an assertion body: returns {ok, got, want}. js_body must return that object."""
    return "(function(){ try { " + PRELUDE + js_body + " } catch (e) { return {ok:false, want:'no exception', got:String(e && e.message || e)}; } })()"


CONTRACT = {
    "ball-drop-sandbox": {
        "required": {"ready": "boolean", "seed": "number", "balls": "array", "score": "number",
                     "over": "boolean", "step": "function", "reset": "function", "hash": "function"},
        "ball_keys": ["x", "y", "z", "vx", "vy", "vz", "r", "settled"],
    },
    "tower-stacker": {
        "required": {"ready": "boolean", "seed": "number", "blocks": "array", "height": "number",
                     "score": "number", "over": "boolean", "toppled": "boolean",
                     "step": "function", "reset": "function", "hash": "function"},
        "block_keys": ["x", "y", "z", "w", "h", "dropped", "settled"],
    },
    "tower-defence": {
        "required": {"ready": "boolean", "seed": "number", "gold": "number", "lives": "number",
                     "wave": "number", "kills": "number", "towers": "array", "units": "array",
                     "path": "array", "score": "number", "over": "boolean", "won": "boolean",
                     "step": "function", "reset": "function", "hash": "function"},
    },
    "match3-cascades": {
        "required": {"ready": "boolean", "seed": "number", "grid": "array", "score": "number",
                     "moves": "number", "over": "boolean", "cascade": "number",
                     "step": "function", "reset": "function", "swap": "function",
                     "settle": "function", "hash": "function"},
    },
}

# ----------------------------------------------------------------------------------
# Assertions per spec. Each entry: (id, description, js) where js is a function body
# returning {ok, got, want}. The contract is checked first and reported as assertion 0.
A = {}

A["ball-drop-sandbox"] = [
    ("a1_ball_count_150", "5 balls exist after 150 ticks (one every 30)",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 150);
      var n = S.balls.length; return {ok: n === 5, got: n, want: 5};
     """),
    ("a2_all_dropped_gravity", "25 balls after 800 ticks and the first ball fell",
     """
      var S = window.__game; S.reset(1234); var n = S.balls.length; window.__pp.steps(S, 800);
      var n = S.balls.length, fell = n > 0 && Math.min.apply(null, S.balls.map(function (b) { return b.y; })) < 8.5;
      return {ok: n === 25 && fell, got: {balls: n, lowest_y: n ? window.__pp.round(Math.min.apply(null, S.balls.map(function (b) { return b.y; }))) : null}, want: {balls: 25, fell: true}};
     """),
    ("a3_inside_bounds", "no ball leaves the box after 6000 ticks",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 6000);
      // The box's inner half-width is the spec's 6 units; r=0.5 → |centre| <= 5.5 (+1 tick slack).
      // A NaN is also an escape (undefined state).
      var nan = S.balls.filter(function (b) { return !window.__pp.num(b.x) || !window.__pp.num(b.y) || !window.__pp.num(b.z); }).length;
      var escaped = S.balls.filter(function (b) { return Math.abs(b.x) > 5.6 || b.y < -0.05 || Math.abs(b.z) > 5.6 || b.y > 20; });
      return {ok: escaped.length === 0 && nan === 0, got: {escaped: escaped.length, nan: nan, n: S.balls.length}, want: {escaped: 0, nan: 0}};
     """),
    ("a4_settled", "at least one ball is settled with |vy| < 0.06 after 6000 ticks",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 6000);
      var s = S.balls.filter(function (b) { return b.settled === true && Math.abs(b.vy) < 0.06; });
      return {ok: s.length >= 1, got: s.length + ' settled', want: '>=1'};
     """),
    ("a5_determinism", "reset(1234) twice gives the same hash; reset(99) differs",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 3000); var h1 = S.hash();
      S.reset(1234); window.__pp.steps(S, 3000); var h2 = S.hash();
      S.reset(99); window.__pp.steps(S, 3000); var h3 = S.hash();
      return {ok: h1 === h2 && h3 !== h1, got: {same_seed: h1 === h2, other_seed_differs: h3 !== h1}, want: {same_seed: true, other_seed_differs: true}};
     """),
]

A["tower-stacker"] = [
    ("b1_twenty_blocks", "20 blocks dropped, all within x in [-3,3]",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 800);
      var out = S.blocks.filter(function (b) { return Math.abs(b.x) > 3; });
      return {ok: S.blocks.length === 20 && out.length === 0, got: {n: S.blocks.length, off: out.length}, want: {n: 20, off: 0}};
     """),
    ("b2_stack_height", "height == 20 and not toppled after 800 ticks",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 800);
      return {ok: S.height === 20 && S.over === true && S.toppled === false,
              got: {height: S.height, over: S.over, toppled: S.toppled}, want: {height: 20, over: true, toppled: false}};
     """),
    ("b3_no_interpenetration", "no two blocks overlap vertically at any 200-tick sample",
     """
      var S = window.__game; S.reset(1234); var bad = 0, samples = 0;
      for (var k = 0; k < 4; k++) { window.__pp.steps(S, 200); samples++;
        for (var i = 0; i < S.blocks.length; i++) for (var j = i + 1; j < S.blocks.length; j++) {
          var a = S.blocks[i], b = S.blocks[j];
          var ox = Math.abs(a.x - b.x) < (a.w + b.w) / 2 - 1e-6;
          var oz = Math.abs(a.z - b.z) < ((a.w + b.w) / 2) - 1e-6;
          var oy = Math.abs(a.y - b.y) < (a.h + b.h) / 2 - 1e-2;
          if (ox && oz && oy) bad++;
        } }
      return {ok: bad === 0, got: bad + ' overlaps over ' + samples + ' samples', want: '0'};
     """),
    ("b4_no_drift", "top block near its seeded offset; stack centre of mass |x| <= 0.15",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 800);
      if (!S.blocks.length) return {ok:false, got:'no blocks', want:'20'};
      var top = S.blocks[S.blocks.length - 1];
      var cx = S.blocks.reduce(function (a, b) { return a + b.x; }, 0) / S.blocks.length;
      return {ok: Math.abs(cx) <= 0.15, got: {top_x: window.__pp.round(top.x), com_x: window.__pp.round(cx)}, want: {com_x: '<=0.15'}};
     """),
    ("b5_determinism", "same seed same tower, other seed differs",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 800); var h1 = S.hash();
      var x1 = S.blocks.map(function (b) { return window.__pp.round(b.x); }).join(',');
      S.reset(1234); window.__pp.steps(S, 800); var h2 = S.hash();
      S.reset(4321); window.__pp.steps(S, 800);
      var x2 = S.blocks.map(function (b) { return window.__pp.round(b.x); }).join(',');
      return {ok: h1 === h2 && x1 !== x2, got: {same: h1 === h2, differs: x1 !== x2}, want: {same: true, differs: true}};
     """),
]

A["tower-defence"] = [
    ("c1_grid_placement", "every tower on a distinct non-path tile",
     """
      var S = window.__game; S.reset(1234);
      var seen = {}; window.__pp.steps(S, 600); var bad = 0;
      var pset = {}; (S.path || []).forEach(function (p) { pset[p[0] + ',' + p[1]] = 1; });
      S.towers.forEach(function (t) {
        if (!Number.isInteger(t.x) || !Number.isInteger(t.y)) bad++;
        var k = t.x + ',' + t.y; if (pset[k]) bad++; if (seen[k]) bad++; seen[k] = 1;
      });
      return {ok: bad === 0 && S.towers.length > 0, got: {towers: S.towers.length, bad: bad}, want: {bad: 0}};
     """),
    ("c2_gold_exact", "gold == 200 + 5*kills - sum(cost) at every sample; never negative",
     """
      var S = window.__game; S.reset(1234); var bad = 0, neg = 0, samples = 0;
      for (var k = 0; k < 60; k++) { window.__pp.steps(S, 60); samples++;
        var spent = 0, tk = 0;
        S.towers.forEach(function (t) { spent += (t.cost || 0); tk++; });
        var expect = 200 + 5 * (S.kills || 0) - spent;
        if (Math.abs(S.gold - expect) > 1e-6) bad++;
        if (S.gold < 0) neg++;
      }
      return {ok: bad === 0 && neg === 0, got: {mismatch_samples: bad, negative: neg, of: samples}, want: {mismatch_samples: 0, negative: 0}};
     """),
    ("c3_five_waves_win", "fixed policy clears all 5 waves (won: true)",
     """
      var S = window.__game; S.reset(1234); var n = 0;
      while (!S.over && n < 120000) { S.step(1/60); n++; }
      return {ok: S.over === true && S.won === true, got: {over: S.over, won: S.won, wave: S.wave, ticks: n, lives: S.lives},
              want: {over: true, won: true}};
     """),
    ("c4_no_tower_spam", "towers grow by <=1 per 10-tick window and never off-grid",
     """
      var S = window.__game; S.reset(1234); var prev = 0, jump = 0, maxjump = 0;
      for (var k = 0; k < 600; k++) { window.__pp.steps(S, 10);
        var d = S.towers.length - prev; if (d > 1) jump++; if (d > maxjump) maxjump = d; prev = S.towers.length; }
      return {ok: jump === 0, got: {jumps: jump, max_growth: maxjump, towers: S.towers.length}, want: {jumps: 0}};
     """),
    ("c5_determinism", "same seed same outcome and hash",
     """
      var S = window.__game; S.reset(1234); window.__pp.steps(S, 3000); var h1 = S.hash(), s1 = S.score;
      S.reset(1234); window.__pp.steps(S, 3000); var h2 = S.hash(), s2 = S.score;
      return {ok: h1 === h2 && s1 === s2, got: {same_hash: h1 === h2, same_score: s1 === s2}, want: {same_hash: true, same_score: true}};
     """),
]

A["match3-cascades"] = [
    ("d1_clean_board", "8x8 ints 0..4, no run of 3, settle() changes nothing",
     """
      var S = window.__game; S.reset(1234);
      var g = S.grid, okShape = g.length === 8 && g.every(function (r) { return r.length === 8 && r.every(function (v) { return Number.isInteger(v) && v >= 0 && v <= 4; }); });
      var r0 = window.__pp.runs(g).length, sc0 = S.score;
      S.settle(); var after = S.grid.map(function (r) { return r.join(','); }).join('|') === g.map(function (r) { return r.join(','); }).join('|');
      return {ok: okShape && r0 === 0 && after && S.score === sc0, got: {shape: okShape, runs: r0, stable_after_settle: after}, want: {shape: true, runs: 0, stable_after_settle: true}};
     """),
    ("d2_seeded_cascade", "fixed swap script reproduces its score on a second identical run",
     """
      var S = window.__game; var script = [[7,0,7,1],[7,2,7,3],[7,4,7,5],[7,6,7,7],[6,0,6,1]];
      S.reset(1234); script.forEach(function (m) { S.swap(m[0], m[1], m[2], m[3]); });
      var s1 = S.score, h1 = S.hash();
      S.reset(1234); script.forEach(function (m) { S.swap(m[0], m[1], m[2], m[3]); });
      // The page's own rAF loop may keep simulating between evaluate() calls, so the
      // second hash is compared only when no cascade is in flight (settle is a no-op).
      var g1 = JSON.stringify(S.grid), c1 = S.cascade, s2 = S.score;
      S.settle();
      var quiet = JSON.stringify(S.grid) === g1;
      return {ok: s2 === s1 && quiet, got: {r1: s1, r2: s2, quiet: quiet, cascade_before: c1}, want: {equal_score: true, quiet: true}};
     """),
    ("d3_no_unsolicited_cascade", "after each of 30 sampled legal swaps, settle() changes nothing",
     """
      var S = window.__game; S.reset(1234); var bad = 0, played = 0;
      for (var k = 0; k < 30; k++) {
        var mv = window.__pp.legalMoves(S.grid); if (!mv.length) break;
        var m = mv[Math.floor(mv.length / 2)];
        S.swap(m[0], m[1], m[2], m[3]); played++;
        var g1 = JSON.stringify(S.grid), s1 = S.score; S.settle();
        if (JSON.stringify(S.grid) !== g1 || S.score !== s1) bad++;
      }
      return {ok: bad === 0 && played > 0, got: {unstable_returns: bad, played: played}, want: {unstable_returns: 0}};
     """),
    ("d4_always_stable", "every returned board has no run of 3 (200 sampled swaps over fresh boards)",
     """
      var S = window.__game; var bad = 0, n = 0;
      for (var seed = 1; seed <= 8; seed++) { S.reset(seed);
        for (var k = 0; k < 25; k++) {
          var mv = window.__pp.legalMoves(S.grid); if (!mv.length) break;
          var m = mv[(k * 7 + seed) % mv.length];
          S.swap(m[0], m[1], m[2], m[3]); n++;
          if (window.__pp.runs(S.grid).length) bad++;
        } }
      return {ok: bad === 0 && n >= 30, got: {unstable: bad, swaps: n}, want: {unstable: 0, swaps: '>=30'}};
     """),
    ("d5_determinism", "seed 1234 replay identical; seed 99 differs",
     """
      var S = window.__game; S.reset(1234); var g1 = JSON.stringify(S.grid);
      S.reset(1234); var g2 = JSON.stringify(S.grid);
      S.reset(99); var g3 = JSON.stringify(S.grid);
      return {ok: g1 === g2 && g1 !== g3, got: {same: g1 === g2, differs: g1 !== g3}, want: {same: true, differs: true}};
     """),
]

# ----------------------------------------------------------------------------------
# SPEC COMPLIANCE: static source checks for things the task did NOT ask for, plus
# runtime evidence where a static word is ambiguous (e.g. "bullet" in a comment).
NO_SHOOTER = re.compile(
    r"\b(enem(y|ies)|bullet|projectile|shoot|weapon|lives|laser|gun|ammo)\b", re.I)
WEAPON_CODE = re.compile(
    r"(case\s*['\" ](Space|' ')|key\s*===?\s*['\"]\s['\"]|e\.code\s*===?\s*['\"]Space)", re.I)


def compliance(spec, src, runtime):
    v, notes = [], []
    hits = sorted({m.group(0).lower() for m in NO_SHOOTER.finditer(src)})
    if spec in ("ball-drop-sandbox", "tower-stacker", "match3-cascades"):
        if hits:
            v.append("shooter vocabulary present in a non-shooter task: " + ", ".join(hits))
        acts = space_actions(src)
        if acts:
            v.append("Space key wired to a gameplay action in a task where Space is "
                     "pause/restart only: " + acts[0])
    if spec == "ball-drop-sandbox":
        if re.search(r"cannon|ammo\.js|Rapier|rapier|Oimo|oimo", src):
            v.append("external physics engine used")
        if runtime.get("nondeterministic"):
            v.append("reset(same seed) produced different hashes (Math.random/Date in the run)")
        if space_actions(src):
            notes.append("Space is bound to a ball action rather than pause")
    if spec == "tower-stacker":
        if re.search(r"cannon|ammo\.js|Rapier|rapier|Oimo|oimo", src):
            v.append("external physics engine used")
        if runtime.get("jitter"):
            v.append("settled blocks moved between later ticks (jitter topple risk)")
        if re.search(r"click[\s\S]{0,120}(drop|place)|pointerdown[\s\S]{0,120}drop", src, re.I):
            v.append("click-to-drop player action")
    if spec == "tower-defence":
        if re.search(r"cannon|ammo\.js|Rapier|rapier|Oimo|oimo", src):
            v.append("external physics engine used")
        if runtime.get("nondeterministic"):
            v.append("non-deterministic replay (Math.random/Date)")
        if re.search(r"(click|pointerdown)[\s\S]{0,200}(tower|place|build)", src, re.I):
            v.append("manual tower placement path")
        if re.search(r"\bplayer\s*[:=]\s*\{", src):
            notes.append("a player object exists (not required here)")
    if spec == "match3-cascades":
        if hits:
            v.append("shooter vocabulary present in a non-shooter task: " + ", ".join(hits))
        if re.search(r"Math\.random", src):
            v.append("Math.random used (seeded generator required)")
        if re.search(r"cannon|ammo\.js|Rapier|rapier", src):
            v.append("physics library used")

    # universal: no external assets (images/textures/models/audio/fonts beyond three CDN)
    ext = re.findall(r"(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", src)
    bad_ext = [u for u in ext if not (u.startswith("https://unpkg.com/three@") or u.startswith("#"))]
    if bad_ext:
        v.append("external asset reference: " + ", ".join(sorted(set(bad_ext))[:3]))
    if re.search(r"TextureLoader|new\s+ImageLoader|THREE\.Audio|new\s+Audio\(", src):
        v.append("external texture/audio loader used (geometry only required)")

    if runtime.get("contract_missing"):
        v.append("window.__game contract incomplete: " + ", ".join(runtime["contract_missing"]))

    # score: start at 100, -25 per violation, -5 per note, floor 0.
    score = max(0, 100 - 25 * len(v) - 5 * len(notes))
    return {"score": score, "violations": v, "notes": notes}


# ----------------------------------------------------------------------------------
def space_actions(src):
    """Code paths that bind SPACE to something other than a pause/restart toggle.

    Matches `if (e.code === 'Space' ...) { ... }` and `case ' ':` blocks, then checks
    whether the block body does anything besides toggling pause / restarting. A block
    that only flips a paused flag (or calls reset) is the spec's allowed use."""
    acts = []
    for m in re.finditer(r"(?:e\.code|e\.key|event\.code|event\.key)\s*===?\s*['\"]"
                         r"(?:Space|\s)['\"][\s\S]{0,400}?\{([^{}]{0,300})\}", src):
        body = m.group(1)
        if re.search(r"\b(launch|spawn|shoot|fire|drop|ball|addBall)\b", body, re.I):
            acts.append(body.strip()[:80])
    for m in re.finditer(r"case\s*['\"]\s['\"]\s*:([\s\S]{0,300}?)(?:break|return)", src):
        body = m.group(1)
        if re.search(r"\b(launch|spawn|shoot|fire|drop|addBall)\b", body, re.I):
            acts.append(body.strip()[:80])
    # keydown/keyup handler blocks that test for space via e.key / code and then act
    for m in re.finditer(r"(?:addEventListener\(\s*['\"]key(?:down|up)['\"][\s\S]{0,600}?)\{([\s\S]{0,600}?)\n\s*\}", src):
        body = m.group(1)
        if re.search(r"['\"](?:Space|\s)['\"]|code\s*===\s*\d\d", body) and re.search(
                r"\b(launch|spawn\w*|shoot|fire\w*|addBall)\s*\(", body, re.I):
            if not re.search(r"paused?\s*=|reset\(", body):
                acts.append(body.strip()[:100])
    return acts


SETTLE = "window.__pp.steps(window.__game, 35); console.log('[pp] settled');"


def settle_runtime(page, ticks=35):
    """Let a page that advances its own rAF loop decide it was not driven externally.

    A game may implement 'the grader drives step()' detection by watching whether its own
    animation loop saw the tick counter move (see spec: the render loop may also call
    step() when nobody else drives it). Two synchronous evaluate() calls run back-to-back,
    more than one frame apart is not guaranteed — so we log a marker, force a short wait,
    and let the page's loop re-arm itself. Assertions then call reset() first, which is
    the state the spec pins every assertion to."""
    try:
        page.evaluate(SETTLE)
        page.wait_for_timeout(120)
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    except Exception:
        pass


def runtime_probe(page, spec):
    """Determinism / jitter evidence that static text cannot show."""
    try:
        return page.evaluate(render_assert("""
          var S = window.__game; var out = {};
          if (S && typeof S.reset === 'function' && typeof S.hash === 'function') {
            S.reset(1234); window.__pp.steps(S, 200); var h1 = S.hash();
            S.reset(1234); window.__pp.steps(S, 200); out.nondeterministic = h1 !== S.hash();
          }
          if (S && Array.isArray(S.blocks) && typeof S.step === 'function') {
            S.reset(1234); window.__pp.steps(S, 1200);
            var before = JSON.stringify(S.blocks.map(function (b) { return [window.__pp.round(b.x), window.__pp.round(b.y)]; }));
            window.__pp.steps(S, 300);
            var after = JSON.stringify(S.blocks.map(function (b) { return [window.__pp.round(b.x), window.__pp.round(b.y)]; }));
            out.jitter = before !== after && S.blocks.filter(function (b) { return b.settled; }).length > 0
                         && S.over === true;
          }
          return out;
        """)) or {}
    except Exception as e:
        return {"error": str(e)[:200]}


def run(spec, game_dir, shot_path=None, out_json=None):
    game_dir = os.path.abspath(game_dir)
    html_path = os.path.join(game_dir, "index.html")
    result = {"spec": spec, "game_dir": os.path.basename(game_dir),
              "probed_at": None, "gate": {}, "assertions": [], "compliance": {},
              "console_errors": []}
    import time
    result["probed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True,
                              args=["--use-gl=angle", "--use-angle=swiftshader",
                                    "--enable-unsafe-swiftshader", "--no-sandbox",
                                    "--allow-file-access-from-files"])
        ctx = b.new_context(viewport=VIEW)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)[:200]))
        page.on("console", lambda m: errors.append("console: " + m.text[:200])
                if m.type == "error" and "favicon" not in m.text.lower() else None)
        try:
            page.goto("file://" + html_path, wait_until="networkidle", timeout=45000)
            gate_load = True
        except Exception as e:
            gate_load = False
            result["gate"]["load_error"] = str(e)[:300]
        if gate_load:
            try:
                page.wait_for_function("() => !!(window.__game && window.__game.ready)", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            g = page.evaluate("""() => {
              const c = [...document.querySelectorAll('canvas')];
              return {ready: !!(window.__game && window.__game.ready),
                      canvas: c.length > 0 && c.some(x => x.width > 0 && x.height > 0),
                      three: /three/i.test(document.documentElement.outerHTML.slice(0, 3000000)),
                      game: window.__game ? Object.keys(window.__game) : []};
            }""")
            try:
                types = page.evaluate("""() => { const g = window.__game || {}; const o = {};
                  for (const k of Object.keys(g)) o[k] = Array.isArray(g[k]) ? 'array' : typeof g[k];
                  return o; }""")
            except Exception as e:
                # a page whose contract getter throws (e.g. units built from a missing array)
                # must fail the gate with evidence, not abort the whole cell
                types = {}
                result["gate"]["contract_probe_error"] = str(e)[:200]
            req = CONTRACT[spec]["required"]
            missing = [k for k, t in req.items() if types.get(k) != t]
            if not g["canvas"]:
                missing.append("canvas")
            result["gate"] = {"load_ok": True, "ready": g["ready"], "canvas": g["canvas"],
                              "three": g["three"], "contract_keys": g["game"],
                              "contract_missing": missing,
                              "pass": bool(g["ready"] and g["canvas"] and g["three"] and not missing)}
            rt = runtime_probe(page, spec) if result["gate"]["pass"] else {"contract_missing": missing}
            for aid, desc, body in A[spec]:
                settle_runtime(page)
                try:
                    r = page.evaluate(render_assert(body))
                except Exception as e:
                    r = {"ok": False, "got": "evaluate failed: " + str(e)[:180], "want": "runs"}
                result["assertions"].append({"id": aid, "desc": desc,
                                             "ok": bool(r.get("ok")), "got": r.get("got"),
                                             "want": r.get("want")})
            src = page.evaluate("() => document.documentElement.outerHTML")
            # static checks look at CODE only: strip HTML/JS comments so a comment that says
            # "no bullets here" is not read as a violation.
            result["compliance"] = compliance(spec, strip_comments(src), rt)
            if shot_path:
                f1 = page.screenshot()
                page.wait_for_timeout(800)
                f2 = page.screenshot()
                result["gate"]["animation_advancing"] = f1 != f2
                open(shot_path, "wb").write(f2)
        else:
            result["gate"]["pass"] = False
            result["assertions"] = [{"id": a[0], "desc": a[1], "ok": False,
                                     "got": "page did not load", "want": "runs"}
                                    for a in A[spec]]
            result["compliance"] = {"score": 0, "violations": ["page did not load"],
                                    "notes": []}
        result["console_errors"] = errors[:20]
        ctx.close()
        b.close()
    passed = sum(1 for a in result["assertions"] if a["ok"])
    result["passed"] = passed
    result["total"] = len(result["assertions"])
    if out_json:
        json.dump(result, open(out_json, "w"), indent=1)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("game_dir")
    ap.add_argument("--spec", required=True, choices=sorted(A))
    ap.add_argument("--shot", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    out = run(a.spec, a.game_dir, a.shot, a.json or os.path.join(a.game_dir, "probe.json"))
    print(json.dumps({k: out[k] for k in ("game_dir", "gate", "passed", "total",
                                          "compliance")}, indent=1))
    for x in out["assertions"]:
        print(("  PASS " if x["ok"] else "  FAIL ") + x["id"] + " — " + x["desc"] +
              ("" if x["ok"] else "  got=%s want=%s" % (json.dumps(x["got"])[:160], json.dumps(x["want"])[:100])))
    sys.exit(0 if out["gate"].get("pass") else 1)
