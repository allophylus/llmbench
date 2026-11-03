<!--
GAME SPEC — llmbench browser cell "match3-cascades"

FROZEN. Sent verbatim as the single user message. Do not edit: the sha256 of this file is
recorded per run (gen.json:prompt_sha256).

Contract note: this task's window.__game contract is its own — {ready, over, score} plus
the board and swap()/settle(). No enemies, no bullets, no player ship. The game's only
action is swap two adjacent jewels.

The grader (games/playprobe.py) runs headless Chrome with a virtual clock and calls
window.__game.step(1/60) exactly N times, or window.__game.swap(i, j) for a move.
-->

Write a complete, self-contained browser game as ONE HTML file using three.js.
Reply with the file inside one ```html fenced block and nothing else.

## BOARD
An 8 x 8 grid of jewels seen from a front-facing camera, each jewel a small three.js
mesh (sphere, octahedron, box, torus, icosahedron for the five types) in one of 5 colours
with lighting so they read as 3D. NO external images, textures, models, fonts or audio.
HUD in HTML: score, moves used / 30, best cascade this game. Canvas fills the window and
adapts on resize. A move counter and a short hint line ("swap two adjacent jewels") are
enough; no menus.

## RULES
- The 8 x 8 board is generated from an integer seed through a seeded generator (see below)
  and contains NO starting match and at least one possible move.
- A move = swap two horizontally or vertically ADJACENT jewels. If the swap creates no
  match of 3 or more in a row/column, it is reverted and does not count as a move.
  A legal move counts one move (max 30 moves; `over: true` after move 30 is resolved).
- Match resolution is a cascade: after a swap, find every horizontal or vertical run of
  3 or more same-type jewels, remove them, apply gravity (jewels fall, empty cells at the
  top are refilled from the seeded generator), then look again — repeat until the board has
  NO runs of 3 or more. That final state is a STABLE board.
- SCORING (exact, numeric): each removed run of length L (horizontal or vertical) gives
  L × L × 10 points multiplied by the cascade depth (depth 1 = the first resolution after
  a swap, depth 2 = the next one, and so on). A cell that belongs to both a horizontal
  and a vertical run is counted only in the longer run (ties: the horizontal run).
  No points for a swapped pair that does not match.
- The game ends when 30 legal moves are used OR when no legal move exists
  (`over: true`). Score is the total; the HUD shows it.

## THE MACHINE-READABLE CONTRACT (mandatory)
The grader drives the game through `window.__game` ONLY:

```js
window.__game = {
  ready: false,      // boolean, true once the board is built and swap() works
  seed: 1234,        // integer, the seed currently running
  grid: [],          // 8 x 8 array of small integers 0..4 (grid[row][col], row 0 = top)
  score: 0,          // number, same as HUD
  moves: 0,          // integer, legal moves used (0..30)
  over: false,       // boolean
  cascade: 0,        // integer, depth of the most recent resolved cascade (0 if none)
  step: function (dt) {},          // advance exactly dt seconds, once
  reset: function (seed) {},       // rebuild the 8x8 board from this integer seed
  swap: function (r1, c1, r2, c2) {}, // perform one move; returns true if legal+scored,
                                      // false if the swap was reverted. Must resolve all
                                      // cascades synchronously before returning.
  settle: function () {},          // resolve any runs already on the board (used by the
                                   // grader to prove the board is stable after a move);
                                   // must be a no-op on a stable board
  hash: function () {}             // string: grid + score + moves, stable serialisation
};
```

All randomness (initial board, refills) comes from a seeded generator inside a closure
(mulberry32/xorshift/LCG), never Math.random or Date, so `reset(1234)` twice gives the same
board AND the same refill sequence. The animation loop runs requestAnimationFrame with
THREE.Clock and never throws; 0 console errors; key listeners on `window` (R = restart).
Touch: jewels respond to pointerdown drag to an adjacent jewel (swap), plus nothing else.

## BEHAVIOURAL ASSERTIONS (the grader runs exactly these)
S = window.__game, after `S.reset(1234)`.
1. initial board: 8 x 8, every cell an integer 0..4, no horizontal or vertical run of 3 or
   more, and S.settle() on it leaves the grid unchanged and score unchanged.
2. seeded cascade: the grader plays the fixed script [(7,0,7,1), (7,2,7,3), (7,4,7,5),
   (7,6,7,7), (6,0,6,1)] with S.swap(...); after the script, score equals a FIXED number
   the game must reproduce from seed 1234 (any deterministic value is fine — the grader
   records it once and checks that a second reset(1234) + same script gives exactly the
   same score and the same final hash).
3. no unsolicited cascades: after every S.swap(...) returns, S.settle() must not change
   the grid or the score (the board must be stable when swap returns).
4. stability invariant: at every one of 200 random legal swaps sampled by the grader,
   the returned grid has no run of 3 or more.
5. determinism: reset(1234) + the script from (2) → (score, hash) equal on a second run;
   reset(99) → different initial grid.

## WHAT COUNTS AS A SPEC VIOLATION
- a swap that is accepted without a match (no revert), or points awarded for it;
- cascades that leave runs on the board (unstable return from swap());
- refills from Math.random or from a pool that is not seeded (non-deterministic board);
- a falling-jewels timer/animation that must play before the board settles (swap must
  resolve synchronously so the state is readable);
- any enemy/bullet/weapon/lives code path, a timer-based "game over by running out of
  time" that replaces the 30-move rule;
- a physics library for the gravity animation.

## SIZE AND OUTPUT
Under about 500 lines. Output ONE ```html block with a complete document (pinned import
map `https://unpkg.com/three@0.160.0/build/three.module.js`), then stop.
