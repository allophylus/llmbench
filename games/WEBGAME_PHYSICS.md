IMPORTANT: keep the whole file under about 350 lines. A truncated file is a failed submission.
Write a complete, playable browser game as a SINGLE self-contained HTML file using three.js.
Reply with the full file inside one ```html fenced block and nothing else.

Hard requirements (an automated browser grader checks them):
1. ONE FILE, NO BUILD STEP, runs from file:// — load three.js from a pinned CDN import map:
   <script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js"}}</script>
   <script type="module">import * as THREE from 'three'; ...</script>
2. You must DRAW everything yourself with three.js geometry, materials, lights and particles.
   NO external images, textures, models, fonts or audio files. No base64 art. Code-drawn only.
3. You must expose a machine-readable state, updated every frame:
   window.__game = { ready:true, score:0, lives:3, over:false, player:{x,y}, enemies:[{x,y}], bullets:[{x,y}] };
   window.__game.reset = function(){...};
4. Input: listen on window for keydown/keyup (Arrows/WASD + Space). Also support touch:
   on-screen buttons using pointerdown/pointerup with touch-action:none, usable at 390x844.
5. Visual quality bar (this is graded by a human): deliberate 4-5 colour palette, gradient or
   nebula background instead of flat black, additive particle bursts on hits, hit-flash and
   screen shake, eased movement (no linear jumps), readable typographic HUD.
6. Keep it under ~450 lines. No commentary outside the code block.

GAME BRIEF:
3D PHYSICS SANDBOX. A translucent box. Balls spawn and fall under gravity, bounce off the
floor and walls with restitution, and collide with each other (simple sphere-sphere). The player launches a ball
with Space from a random position; a HUD shows ball count. Score = number of simultaneous balls still bouncing after
they settle is a failure; the game ends when 25 balls have been launched. Determinism matters: same seed/timing must
bounce the same way.
