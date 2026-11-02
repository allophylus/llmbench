#!/usr/bin/env python3
"""webadapt.py — build instrumented copies of generated games (evidence only).

usage: webadapt.py <repo_games_dir> <slug> [...]

Writes <games>/_scratch/<slug>/adapted.html: the game's index.html with a probe
appended that exposes the live three.js scene as window.__wv(). It never edits the
published game file — it only lets the validator record WHY something is invisible
(e.g. the player mesh projects outside the camera frustum).

The probe finds the renderer through the canvas (three.js 0.160 keeps an internal
`renderer` back-reference on the WebGL context creation path only when exposed), so
instead of relying on internals we re-run the page's own module and publish its
objects via a small source rewrite: `const scene = new THREE.Scene();` is a fixed
pattern in the frozen prompt's expected output, and anything it cannot patch is
reported as "scene not exposed" (a metric, not a guess).
"""
import os
import re
import sys

games = os.path.abspath(sys.argv[1])
PROBE = """
// ---- webvalidate instrumentation (added by webadapt.py; NOT part of the game) ----
window.__wv = () => {
  try {
    const R = window.__wvR;
    if (!R) return {scene_exposed: false};
    const {scene, camera, player, renderer} = R;
    let v;
    // Vector3.project() uses camera.matrixWorldInverse, which three.js only refreshes
    // inside render(); update it explicitly (this is what Camera.updateMatrixWorld does
    // when matrixWorldAutoUpdate is on).
    scene.updateMatrixWorld(true);
    camera.updateMatrixWorld(true);
    camera.matrixWorldInverse.copy(camera.matrixWorld).invert();
    v = player.position.clone().project(camera);
    const w = renderer.domElement.clientWidth, h = renderer.domElement.clientHeight;
    const px = [(v.x + 1) / 2 * w, (1 - v.y) / 2 * h];
    // A ship whose CENTRE is low can still be visible: measure the mesh's world-space
    // bounding sphere instead of a single point.
    let ext = null, extOnscreen = null;
    try {
      player.geometry.computeBoundingSphere();
      const bs = player.geometry.boundingSphere.clone();
      bs.applyMatrix4(player.matrixWorld);
      const ctr = bs.center.clone().project(camera);
      const radPx = bs.radius * (h / (2 * Math.tan(camera.fov * Math.PI / 360))) / Math.abs(ctr.z * 2);
      const cx = (ctr.x + 1) / 2 * w, cy = (1 - ctr.y) / 2 * h;
      ext = [Math.round(cx - radPx), Math.round(cy - radPx), Math.round(cx + radPx), Math.round(cy + radPx)];
      extOnscreen = cx + radPx > 0 && cx - radPx < w && cy + radPx > 0 && cy - radPx < h
                    && ctr.z > -1 && ctr.z < 1;
    } catch (e) { ext = String(e); }
    return {
      scene_exposed: true,
      player_bbox_px: ext,
      player_bbox_onscreen: extOnscreen,
      player_bbox_fully_onscreen: Array.isArray(ext) && ext[0] >= 0 && ext[1] >= 0 && ext[2] <= w && ext[3] <= h,
      children: scene.children.length,
      player_world: [player.position.x, player.position.y, player.position.z].map(n => +n.toFixed(2)),
      player_ndc: [v.x, v.y, v.z].map(n => +n.toFixed(3)),
      player_px: px.map(n => Math.round(n)),
      player_onscreen: v.z > -1 && v.z < 1 && Math.abs(v.x) <= 1 && Math.abs(v.y) <= 1
                        && px[0] >= 0 && px[0] <= w && px[1] >= 0 && px[1] <= h,
      viewport: [w, h],
      hud_boxes: [...document.querySelectorAll('.hud, .hud *')]
        .filter(e => e.textContent.trim() && !e.querySelector('*'))
        .map(e => { const r = e.getBoundingClientRect();
                    return {x: Math.round(r.left), y: Math.round(r.top),
                            w: Math.round(r.width), h: Math.round(r.height)}; }),
    };
  } catch (e) { return {scene_exposed: false, error: String(e)}; }
};
"""

for slug in sys.argv[2:]:
    src = open(os.path.join(games, slug, "index.html")).read()
    # Publish the three objects the probe needs. Only matches the exact declarations
    # the prompt asks for; if a game declares them differently we do not guess.
    patched = src
    patched = patched.replace("const scene = new THREE.Scene();",
                              "const scene = new THREE.Scene();", 1)
    m = re.search(r"const scene\s*=\s*new THREE\.Scene\(\);", src)
    m2 = re.search(r"const player\s*=\s*new THREE\.Mesh\([^;]*\);", src)
    m3 = re.search(r"const camera\s*=\s*new THREE\.PerspectiveCamera\([^;]*\);", src)
    if not (m and m2 and m3):
        print(f"{slug}: could not patch (scene={bool(m)} player={bool(m2)} camera={bool(m3)})")
    else:
        end_player = m2.end()
        patched = (src[:end_player]
                   + "\n// webadapt: expose objects for the validator\n"
                   + "window.__wvR = {scene, camera, player, renderer};\n"
                   + src[end_player:])
    patched = patched.replace("</body>", f"<script>{PROBE}</script>\n</body>", 1)
    outdir = os.path.join(games, "_scratch", slug)
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, "adapted.html"), "w").write(patched)
    # The CDN import needs the page served over http (module CORS is fine via CDN);
    # adapted.html references no local files, so it can live alone in _scratch/<slug>.
    print("wrote", os.path.join(outdir, "adapted.html"))
