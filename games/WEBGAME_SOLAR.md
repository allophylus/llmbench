Write a complete, playable browser game as a SINGLE self-contained HTML file using three.js.
Reply with the full file inside one ```html fenced block and nothing else.

IMPORTANT: keep the whole file under 350 lines. No large <style> block (30 lines max).
A truncated file is a failed submission.

Hard requirements (an automated browser grader checks them):
1. ONE FILE, NO BUILD STEP, runs from file:// — load three.js from a pinned CDN import map:
   <script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js"}}</script>
   <script type="module">import * as THREE from 'three'; ...</script>
2. You must DRAW everything yourself with three.js geometry, materials, lights and particles.
   NO external images, textures, models, fonts or audio files. Code-drawn only.
3. Expose machine-readable state, updated every frame:
   window.__game = { ready:true, phase:"earth"|"transit"|"mars"|"return"|"done",
                     rocket:{x,y,z}, earth:{x,y,z}, mars:{x,y,z},
                     distanceToTarget:number, score:0, over:false };
   window.__game.reset = function(){...};
4. Controls — BOTH keyboard and touchscreen:
   - Rotate/orbit the camera: arrow keys (or drag with one finger)
   - Zoom: +/- keys (or pinch with two fingers)
   - Launch / next step: Space (or an on-screen LAUNCH button)
   On-screen controls must use pointerdown/pointerup with touch-action:none and be usable at 390x844.

GAME BRIEF — SOLAR SYSTEM MISSION:
A stylised solar system: a glowing Sun at the centre, Earth and Mars orbiting on visible rings
(drawn as thin torus or line geometry), with a starfield background.
The player's rocket starts on Earth. Pressing LAUNCH fires the rocket from Earth on a transfer
trajectory to Mars; on arrival it enters Mars orbit, then LAUNCH again fires it back to Earth.
Show a HUD with: current phase, distance remaining to the target (in arbitrary units), and a
progress bar. The rocket must visibly travel between the planets (not teleport), with a particle
exhaust trail. Completing the round trip earns the score.
Visual quality bar (graded by a human): deliberate palette, glowing Sun, planet colours,
starfield, eased motion, readable HUD, subtle camera shake on launch.
