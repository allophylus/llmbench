<!--
GAME SPEC — llmbench browser cell "ball-drop-sandbox"

FROZEN. Sent verbatim as the single user message. Do not edit: the sha256 of this file is
recorded per run (gen.json:prompt_sha256). A change means a new spec version and old
results are not comparable.

Contract note (why this file looks the way it does): the earlier v1/v2 game prompts used
one shared window.__game contract that demanded `enemies[]` and `bullets[]`. A physics task
built to that contract came back as a shooter. This spec has its OWN contract — only
{ready, over, score} plus the handles this task needs. There are no enemies and no
bullets anywhere in this task, and an automated grader penalises adding them.

The grader (games/playprobe.py) executes the assertions below in headless Chrome with a
virtual clock: it calls window.__game.step(1/60) exactly N times, so results do not depend
on the machine's frame rate. Words like "tick" below mean one step(1/60) call.
-->

Write a complete, self-contained browser simulation as ONE HTML file using three.js.
Reply with the file inside one ```html fenced block and nothing else.

## SCENE
A translucent glass box on a table: an open-top rectangular box with a floor and four
walls (a slightly higher back wall is fine). Camera looks into the box from the front-top
so the floor is clearly visible. Draw everything with three.js geometry, materials, lights
and particles — NO external images, textures, models, fonts or audio, no base64 art.
A deliberate 3-5 colour palette, soft lighting, and a readable HTML HUD over the canvas
(DOM text, not drawn into the canvas) showing: balls dropped / 25, balls still awake,
and the score. The canvas fills the window and adapts on resize.

## RULES (physics is analytic — write it yourself, no physics engine)
- 25 balls are dropped, one every 30 ticks, each from a seeded position near the top
  inside the box. Ball radius 0.5. All balls identical mass.
- gravity pulls down (about -9.8 units/s²); dt comes from step(1/60) or the frame clock.
- Floor and walls: a ball that crosses a bound is pushed back inside and its velocity
  component along that axis is multiplied by -restitution, restitution = 0.6.
- Ball vs ball: sphere-sphere. If two balls overlap, separate them along the centre line
  by half the overlap each (positional correction) and exchange the velocity component
  along the centre line (equal mass), then apply a little friction to the tangential part.
- A ball is "settled" when its speed is below 0.05 units/s AND it rests on the floor
  (or on another settled ball) for at least 30 consecutive ticks. Settled balls are frozen.
  Use a small sleep threshold, not a hard velocity zero each tick.
- Score = number of settled balls × 10, plus 50 bonus when all 25 are settled.
  The run is over (`over: true`) when all 25 balls are settled.

## NO PLAYER WEAPON, NO ENEMIES
This is a sandbox. Do NOT add a player character, weapons, projectiles, shooting,
enemies, lives, timers or levels. There must be no keys that launch a ball and no
Space-to-shoot. SPACE is only a pause/resume toggle, and R restarts the run with the same
seed. Adding combat or any launch mechanic is graded as a spec violation.

## DETERMINISM AND THE MACHINE-READABLE CONTRACT (mandatory)
The grader drives the simulation through `window.__game` ONLY. Exact shape
(extra keys are allowed, but these must exist with these types):

```js
window.__game = {
  ready: false,          // boolean, true once the scene is built and step() works
  seed: 1234,            // integer, the seed currently running
  balls: [],             // array of {x, y, z, vx, vy, vz, r, settled} — plain numbers,
                         // ALL balls that exist this run (0..25), settled ones included
  score: 0,              // number, same number as the HUD
  over: false,           // boolean, true once all 25 balls settled
  step: function (dt) {},        // advance the simulation by exactly dt seconds, once
  reset: function (seed) {},     // restart from scratch with the given integer seed
  hash: function () {}           // string: stable serialisation of the state, see below
};
```

`reset(seed)` must rebuild the world from that integer seed with NO randomness taken from
Math.random or Date: all random values must come from a seeded generator kept in a closure
(mulberry32, xorshift, LCG — your choice), so `reset(1234)` twice gives identical runs.
`step(dt)` must simulate exactly one fixed step of dt (no accumulated frame time from the
animation loop inside it when the grader calls it); the render loop may also call step()
itself when nobody else drives it.

`hash()` returns a string that changes if any ball's position/velocity or the score
changes. It must be built only from rounded numbers (e.g. 4 decimals) so floating-point
noise does not flip it: positions/velocities rounded to 1e-4, then the string of all balls
in index order plus the score.

The animation loop uses requestAnimationFrame with THREE.Clock and must never throw; the
page must have 0 console errors. Keyboard events are listened for on `window`.

## BEHAVIOURAL ASSERTIONS (the grader runs exactly these)
S = window.__game, after `S.reset(1234)`.
1. after 150 steps: S.balls.length is 5 (±0) — one new ball every 30 ticks.
2. after 800 steps: S.balls.length is 25 and S.balls[0].y has decreased from its spawn
   value (gravity acts).
3. after 6000 steps: every ball's x is within the inner box (± box half-width minus r)
   and y is at or above the floor (no ball escapes the box).
4. after 6000 steps: at least one ball has settled === true and its |vy| < 0.06.
5. determinism: reset(1234), run 3000 steps, h1 = S.hash(); reset(1234), run 3000 steps,
   h2 = S.hash(); h1 must equal h2. Then reset(99) and run 3000 steps → hash differs.

## WHAT COUNTS AS A SPEC VIOLATION (fails compliance, not just behaviour)
- any projectile/firing/weapon/enemy/lives code path, or Space launching a ball;
- balls spawned with Math.random (non-deterministic across reset with the same seed);
- step() driving a wall clock / requestAnimationFrame internally instead of the dt given;
- a physics engine library (cannon, ammo, rapier, oimo) instead of your own integration;
- settled balls that keep jittering (hash changes while nothing new is dropped).

## SIZE AND OUTPUT
Under about 450 lines. Correctness first. Output ONE ```html block with a complete
document (pinned import map `https://unpkg.com/three@0.160.0/build/three.module.js`), then stop.
