<!--
WEBGAME_PROMPT — FROZEN (llmbench browser-game cell v1, game cell "webgame-3js")

Sent verbatim as the single user message to every model. Never edit; the sha256 of
this exact file is recorded per run as gen.json:prompt_sha256. If the prompt must
change, that is a new benchmark version (v2) and old results are not comparable.

Graded automatically by games/webvalidate.py (headless Chrome + playwright):
  file:// load, http:// load, console errors, WebGL/canvas context, requestAnimationFrame
  advancing (two screenshots ~1s apart), and keyboard input visibly moving the player.
So every rule below must hold at RUN TIME, not merely be mentioned in the source.

The model's reply is the deliverable, not a tutorial. No commentary, no build step.
-->

Write a complete, playable arcade space shooter as a SINGLE self-contained HTML file
using three.js. Reply with the full file inside one ```html fenced block and nothing else.

Hard requirements (an automated browser grader checks all of them):

1. ONE FILE, NO BUILD STEP. `index.html` must run correctly when opened directly from
   disk via `file://`, with no local server, no bundler, no npm.
   - Load three.js from a pinned CDN via an ES-module import map, exactly like this:
       <script type="importmap">
       {"imports": {"three": "https://unpkg.com/three@0.160.0/build/three.module.js"}}
       </script>
       <script type="module"> import * as THREE from 'three'; ... </script>
   - The 3D scene MUST be rendered with THREE.WebGLRenderer on a <canvas>. A plain 2D
     <canvas> game is a failure. THREE must appear in the running code.

2. CANVAS FILLS THE WINDOW. The renderer canvas covers the full viewport, resizes with
   the window (handle `resize`), and the camera aspect is updated on resize.

3. SCENE. A perspective camera looking at a playfield of deep space. Include a visible
   starfield: at least several hundred star objects (THREE.Points is fine) distributed in
   depth that scroll past the camera so the scene looks alive. Use geometry + materials
   only — NO external images, textures, audio files or fonts. Colours via material
   `color` / `emissive` are fine. Lights are fine.

4. PLAYER. The player is a visible mesh (cone/box/octahedron cluster — your call) near the
   bottom of the view, moved on the X axis by the LEFT/RIGHT arrow keys AND A/D.
   Clamp its position so it stays on screen. Movement must be smooth (dt-scaled) and
   clearly visible to a grader that presses a key and compares screenshots.

5. SHOOTING. SPACE fires a projectile (small glowing mesh, e.g. a stretched box or
   sphere) that travels upward (away from camera). Add a short cooldown (~150-250 ms).
   Remove projectiles that leave the play area.

6. ENEMIES. Enemies spawn on a timer at random X positions near the far end of the
   playfield, below/around the starfield, and fly toward the player (descend toward the
   camera / bottom of the screen) at random speeds. They must be visible meshes with
   distinct colours. Cap the number alive so it never grows without bound.

7. COLLISION. Use simple distance (or bounding-sphere) checks in world space:
   - player projectile vs enemy  -> enemy destroyed (explosion effect or fade is a plus),
     score increases.
   - enemy vs player             -> player loses a life; the enemy is removed.
   Give the player 3 lives.

8. HUD overlay in plain HTML (absolutely positioned <div>s on top of the canvas, or
   DOM text): SCORE and LIVES, updated live. When lives reach 0, show "GAME OVER" and
   "Press R to restart"; pressing R resets score, lives, enemies and projectiles and
   resumes play. The animation loop must never throw (guard against NaN/holes).

9. PERFORMANCE. Use requestAnimationFrame with a THREE.Clock delta. Use shared
   geometry/material instances where sensible, and a reasonable object count (hundreds
   of objects max). No shadows or post-processing required.

9b. MACHINE-READABLE CONTRACT (mandatory — an automated robot plays the game through
    exactly these hooks; a game without them fails the benchmark, even if it looks fine):

   a) Expose `window.__game` and refresh it EVERY FRAME, before or after render, so a
      reader at any moment sees the current state. Exact shape (extra keys allowed):

        window.__game = {
          ready:   false,              // true once the loop has run at least once
          score:   0,                  // int, same number as the HUD
          lives:   3,                  // int, 3 -> 0
          over:    false,              // true when GAME OVER is shown
          player:  { x: 640, y: 700 }, // canvas pixel coordinates (see below)
          enemies: [{ x: 300, y: 120 }],
          bullets: [{ x: 640, y: 600 }],
          reset:   function () { ... } // same as pressing R
        };

      All x/y values are CSS pixel coordinates on the canvas: x from 0 (left) to
      canvas.clientWidth, y from 0 (top) to canvas.clientHeight. Enemies and bullets
      must be included while they are alive and removed when destroyed or out of play.
      Keep it as a plain data snapshot plus the `reset` function; do not put THREE
      objects in it. It must be cheap enough to rebuild every frame.

   b) Listen for input on `window` (`window.addEventListener('keydown', ...)`, not on a
      DOM element and not with `tabindex`/focus requirements), and read `event.key`.
      The robot drives the game with synthetic events:

        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
        window.dispatchEvent(new KeyboardEvent('keyup',   { key: 'ArrowLeft' }));

      The same must work for 'ArrowRight', 'ArrowUp', 'ArrowDown', ' ', 'a', 'd', 'r' and
      'R'. Do not require `event.code`, do not call preventDefault in a way that breaks
      synthetic events, and do not gate gameplay on pointer/click state.

   c) `window.__game.reset()` must fully restart the game (score 0, lives 3, enemies and
      bullets cleared, `over` false) exactly like pressing R.

   d) The game must stay fully playable by a human with the keyboard, unchanged — the
      contract adds a read-only state object and nothing the player sees.

10. SIZE. Keep the file under about 350 lines. Correctness and completeness matter far
    more than extra features: a smaller game that runs perfectly beats a big one that
    throws.

Output: one ```html block containing a complete <!DOCTYPE html> document, then stop.
