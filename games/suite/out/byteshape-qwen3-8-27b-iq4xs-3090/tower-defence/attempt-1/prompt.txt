<!--
GAME SPEC — llmbench browser cell "tower-defence"

FROZEN. Sent verbatim as the single user message. Do not edit: the sha256 of this file is
recorded per run (gen.json:prompt_sha256).

Contract note: this task's window.__game contract is its own — {ready, over, score} plus
waves/gold/towers. Enemy units exist here BY DESIGN (they are the wave units), but there is
NO player ship, NO player bullets, NO Space to shoot: the towers fire automatically and the
player never aims. The build action is ONE fixed auto-placement policy so the model cannot
spam towers.

The grader (games/playprobe.py) runs headless Chrome with a virtual clock and calls
window.__game.step(1/60) exactly N times. The grid cell is 1 unit; positions are integers.
-->

Write a complete, self-contained browser game as ONE HTML file using three.js.
Reply with the file inside one ```html fenced block and nothing else.

## BOARD
Flat top-down 3/4 view of a 16 x 10 tile board (tiles 1 unit). A fixed path runs from the
left edge to the right edge in a hard-coded list of tiles (include at least 6 turns).
Ground is drawn with three.js geometry (instanced tiles or a plane); the path is a distinct
colour; each tower is a small mesh on its tile; each wave unit is a small moving mesh on
the path. NO external images, textures, models, fonts or audio. HUD in HTML (DOM): wave,
gold, lives, score, towers placed. Canvas fills the window and adapts on resize.

## RULES
- Costs: a tower costs 50 gold to build and can be upgraded once for 30 gold (range grows).
  Start: 200 gold, 20 lives.
- Grid only: a tower may only be placed on an EMPTY tile that is NOT on the path and not
  the start/end tile. Towers never move.
- Waves (fixed composition, fixed order, started by a countdown, no player action):
  W1 8 units  | W2 12 units | W3 16 units | W4 20 units | W5 24 units
  Unit stats: hp = 30 + 10 × wave, speed = 1.2 tiles/s, reward = 5 gold.
  Units walk the fixed path from tile 0 to the last tile; a unit that reaches the end
  costs 1 life and is removed.
- Towers: range 2.5 tiles (3.5 after upgrade), fire every 30 ticks, 12 damage per shot
  (18 after upgrade), target = the unit furthest along the path within range. Draw a
  short tracer line when they fire.
- AUTOMATIC PLACEMENT POLICY (the only build action, runs at fixed moments):
  every 10 ticks, if gold >= 50, place a tower on the first EMPTY, non-path tile in
  row-major order (row 0 first, left to right) — that is, the model builds on the tiles
  nearest the path start first, one tower every build step, never two at once.
  After 6 towers exist, every 10 ticks with gold >= 30 instead upgrade the
  lowest-index tower that is not yet upgraded.
  The player does not choose the tile and cannot build by clicking. Mouse/touch may pan
  or zoom only.
- Wave ends when all its units are dead or gone; then a 60-tick break and the next wave
  starts. `over: true` when lives reach 0, or when wave 5 is cleared (win).
- Score = 10 × units killed + 100 × waves survived + 25 × towers placed + 1000 if all 5
  waves survive. Gold accounting is exact: it decreases by exactly the build cost and
  increases by exactly the reward per kill — no gold is created or lost anywhere else.

## THE MACHINE-READABLE CONTRACT (mandatory)
The grader drives the game through `window.__game` ONLY:

```js
window.__game = {
  ready: false,       // boolean, true once the board is built and step() works
  seed: 1234,         // integer, the seed currently running
  gold: 200,          // number, 0.. in whole gold
  lives: 20,          // number
  wave: 0,            // integer, 0 = before wave 1, 1..5 during/after a wave
  kills: 0,           // integer, units killed so far (the auditor cross-checks gold)
  towers: [],         // array of {x, y, level, cost} — integer tile coords; cost = total
                      //            gold spent on that tower (50, or 80 when upgraded)
  units: [],          // array of {x, y, hp, wp} — integer tile coords, wp = path index
  path: [[x, y], ...],// the fixed path tiles, start -> end, integers
  score: 0,           // number, same as HUD
  over: false,        // boolean
  won: false,         // boolean, true only when wave 5 is cleared
  step: function (dt) {},
  reset: function (seed) {},
  hash: function () {}   // string over gold/lives/wave/score + rounded unit and tower state
};
```

Everything that could vary must come from a seeded generator inside a closure
(mulberry32/xorshift/LCG), never Math.random or Date, so `reset(1234)` twice replays the
same game. Unit spawn offsets are deterministic. `step(dt)` advances exactly dt seconds;
the render loop may also call it when the grader is not driving.

The animation loop uses requestAnimationFrame with THREE.Clock, never throws, and the
page has 0 console errors. Key listeners on `window` (R = restart with the same seed;
SPACE = pause). Touch: on-screen pause/restart buttons with pointerdown/pointerup.

## BEHAVIOURAL ASSERTIONS (the grader runs exactly these)
S = window.__game, after `S.reset(1234)`; the grader runs the game forward in steps and
samples after every 60 steps.
1. every tower's tile (x, y) is a non-path tile, occupied by at most one tower, and
   `over` is false when the first tower appears.
2. gold accounting is exact: at every sample gold == 200 + 5 × kills − Σ tower.cost, where
   kills is the visible kill counter the game must publish as `window.__game.kills`, and
   gold never goes negative.
3. frames: by the time all 5 waves are over, wave reached 5 (or over is true with lives 0)
   and — with the fixed policy — the run is a WIN (`won: true`) when played to completion.
4. at every sample the number of towers never increases by more than 1 between
   consecutive 10-tick windows (no spam) and never exceeds the number of build steps x 1.
5. determinism: reset(1234) + run 3000 steps → h1; reset(1234) + run 3000 steps → h2;
   h1 == h2.

## WHAT COUNTS AS A SPEC VIOLATION
- click-to-place towers, a tower-type chooser, a sell button, or any manual aiming;
- towers placed off-grid (non-integer tiles), on the path, on an occupied tile, or two
  towers in the same 10-tick window;
- a player ship, player-fired bullets, a Space-to-shoot action;
- gold created or lost outside the three allowed amounts (−50 build, −30 upgrade, +5 kill);
- non-deterministic spawns or placements (Math.random / Date);
- a physics engine library for anything.

## SIZE AND OUTPUT
Under about 500 lines. Output ONE ```html block with a complete document (pinned import
map `https://unpkg.com/three@0.160.0/build/three.module.js`), then stop.
