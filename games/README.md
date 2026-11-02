# Browser game cell (v1)

The terminal cells in the night7 runs are pty/curses games. This cell is the
browser counterpart: one frozen prompt (`WEBGAME_PROMPT.md`, sha256 recorded in each
`gen.json`) asks for a complete single-file three.js shooter.

| script | role |
|---|---|
| `WEBGAME_PROMPT.md` | frozen prompt; never edit (a change = v2, results not comparable) |
| `webgen.py` | POST prompt to `<base_url>/v1/chat/completions`, extract HTML, write `index.html` + `gen.json` |
| `webvalidate.py` | headless Chrome (playwright, `/usr/bin/google-chrome`) over `file://` and a local `http://`; writes `metrics.json` + screenshots |
| `webadapt.py` | optional: builds `_scratch/<slug>/adapted.html` with a probe exposing the live scene, so metrics can explain *why* something is invisible |
| `build_index.py` | renders this directory's `index.html` from the recorded `metrics.json`/`gen.json` |

Usage:
```sh
./webgen.py http://192.168.1.148:8080 WEBGAME_PROMPT.md ../llmbench/games/<slug> <slug>
python3 webadapt.py ../llmbench/games <slug>      # optional, evidence only
python3 webvalidate.py ../llmbench/games/<slug>
python3 build_index.py ../llmbench/games
```

What `metrics.json` records per scheme: load ok, console/page errors (implicit
`/favicon.ico` 404s are listed separately as `ignored_favicon_404s`), canvas present,
WebGL context obtainable, frame changes over ~1 s, frame changes for ArrowRight and
ArrowLeft, which 3D geometry is hidden under HTML overlays (pixel diff with overlays
hidden), and — from the adapter — the player mesh's projected bounding box.

Pass = load ×2, canvas, WebGL, animation, input. `player_visible` /
`overlays_cover_geometry` are reported as findings but do not flip `pass`.

## v1 results (2026-11-02, model `/home/ubuntu/models/active.gguf`, Q4_K_M, temp 0)

Both samples used three.js (`WebGLRenderer`, importmap CDN), 0 console errors.

* `qwen3-8-27b-q4km` — all checks pass, but the player mesh is placed at z=+10 while the
  camera sits at z=+14 looking down −z, so the ship projects to y≈1052..1827 px in an
  800 px viewport: it moves, shoots, collides and scores, but is never visible.
* `qwen3-8-27b-q4km-b` — all checks pass; ship visible at the bottom (partly clipped),
  firing/collision/explosions work; its bottom HUD hint bar is painted over the ship.
