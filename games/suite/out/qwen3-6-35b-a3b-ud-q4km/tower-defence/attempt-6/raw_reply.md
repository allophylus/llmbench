```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tower Defence</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{overflow:hidden;background:#111;font-family:monospace;color:#fff}
canvas{display:block}
#hud{position:absolute;top:10px;left:10px;background:rgba(0,0,0,.7);padding:10px 16px;border-radius:8px;font-size:14px;line-height:1.6;pointer-events:none;user-select:none}
#hud span{color:#4fc}
#controls{position:absolute;bottom:10px;left:50%;transform:translateX(-50%);display:flex;gap:10px}
#controls button{background:rgba(0,0,0,.7);color:#fff;border:1px solid #555;padding:8px 18px;border-radius:6px;cursor:pointer;font-family:monospace;font-size:14px;pointer-events:auto}
#controls button:hover{background:rgba(40,40,40,.9)}
#overlay{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.6);font-size:28px;pointer-events:none;opacity:0;transition:opacity .3s}
#overlay.show{opacity:1}
</style>
</head>
<body>
<div id="hud">
  <div>Wave: <span id="hWave">0</span> / 5</div>
  <div>Gold: <span id="hGold">200</span></div>
  <div>Lives: <span id="hLives">20</span></div>
  <div>Score: <span id="hScore">0</span></div>
  <div>Towers: <span id="hTowers">0</span></div>
</div>
<div id="controls">
  <button id="btnPause">Pause</button>
  <button id="btnRestart">Restart</button>
</div>
<div id="overlay"></div>

<script type="importmap">
{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js"}}
</script>
<script type="module">
import * as THREE from 'three';

// ── Seeded RNG (mulberry32) ──
function mulberry32(a) {
  return function() {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

// ── Path definition (16x10 grid, 6+ turns) ──
const PATH = [
  [0,4],[1,4],[2,4],[3,4],[4,4],[5,4],[6,4],[7,4],
  [7,3],[7,2],[7,1],[7,0],
  [8,0],[9,0],[10,0],[11,0],[12,0],
  [12,1],[12,2],[12,3],[12,4],[12,5],[12,6],[12,7],
  [13,7],[14,7],[15,7]
];
const PATH_SET = new Set(PATH.map(p => p[0]+','+p[1]));
const COLS = 16, ROWS = 10;

// ── Game State ──
let state = {
  ready: false, seed: 1234, gold: 200, lives: 20,
  wave: 0, kills: 0, score: 0, over: false, won: false,
  towers: [], units: [], path: PATH,
  tick: 0, paused: false,
  // wave management
  waveUnitsSpawned: 0, waveUnitsTotal: 0, waveUnitsRemaining: 0,
  waveBreakTimer: 0,
  // auto-build
  buildTimer: 0,
  // visual
  tracers: [],
  // rng
  rng: null,
};

// ── Three.js Setup ──
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);
const camera = new THREE.PerspectiveCamera(50, window.innerWidth/window.innerHeight, 0.1, 100);
camera.position.set(COLS/2, ROWS/2, 18);
camera.lookAt(COLS/2, ROWS/2, 0);

const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
document.body.prepend(renderer.domElement);

// ── Lighting ──
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(5, 10, 15);
scene.add(dirLight);

// ── Grid & Path ──
const tileGeo = new THREE.BoxGeometry(0.95, 0.1, 0.95);
const groundMat = new THREE.MeshLambertMaterial({color: 0x2d5a27});
const pathMat = new THREE.MeshLambertMaterial({color: 0x8b7355});
const startMat = new THREE.MeshLambertMaterial({color: 0x4488ff});
const endMat = new THREE.MeshLambertMaterial({color: 0xff4444});

const tiles = [];
for (let r = 0; r < ROWS; r++) {
  for (let c = 0; c < COLS; c++) {
    const isPath = PATH_SET.has(c+','+r);
    const mat = isPath ? pathMat : groundMat;
    const mesh = new THREE.Mesh(tileGeo, mat);
    mesh.position.set(c - COLS/2 + 0.5, 0, r - ROWS/2 + 0.5);
    scene.add(mesh);
    tiles.push({mesh, x: c, y: r, isPath});
  }
}

// Mark start and end
const startTile = tiles.find(t => t.x === PATH[0][0] && t.y === PATH[0][1]);
const endTile = tiles.find(t => t.x === PATH[PATH.length-1][0] && t.y === PATH[PATH.length-1][1]);
if (startTile) startTile.mesh.material = startMat;
if (endTile) endTile.mesh.material = endMat;

// ── Tower meshes ──
const towerGeo = new THREE.CylinderGeometry(0.3, 0.35, 0.5, 8);
const towerMat = new THREE.MeshLambertMaterial({color: 0x4488cc});
const towerUpgradedMat = new THREE.MeshLambertMaterial({color: 0xcc8844});
const towerGroup = new THREE.Group();
scene.add(towerGroup);

// ── Unit meshes ──
const unitGeo = new THREE.SphereGeometry(0.25, 8, 8);
const unitMat = new THREE.MeshLambertMaterial({color: 0xff3333});
const unitGroup = new THREE.Group();
scene.add(unitGroup);

// ── Tracer lines ──
const tracerMat = new THREE.LineBasicMaterial({color: 0xffff44});
const tracerGroup = new THREE.Group();
scene.add(tracerGroup);

// ── Tower placement ──
function placeTower(x, y) {
  const mesh = new THREE.Mesh(towerGeo, towerMat.clone());
  mesh.position.set(x - COLS/2 + 0.5, 0.35, y - ROWS/2 + 0.5);
  towerGroup.add(mesh);
  state.towers.push({x, y, level: 1, cost: 50, mesh});
}

function upgradeTower(tower) {
  tower.level = 2;
  tower.cost = 80;
  tower.mesh.material = towerUpgradedMat;
}

// ── Unit spawning ──
function spawnUnit(wave) {
  const hp = 30 + 10 * wave;
  const unit = {
    x: PATH[0][0], y: PATH[0][1],
    hp, maxHp: hp,
    wp: 0, // waypoint index
    progress: 0, // progress along current segment
    alive: true,
    mesh: new THREE.Mesh(unitGeo, unitMat.clone()),
  };
  unit.mesh.position.set(
    PATH[0][0] - COLS/2 + 0.5,
    0.3,
    PATH[0][1] - ROWS/2 + 0.5
  );
  unitGroup.add(unit.mesh);
  state.units.push(unit);
}

// ── Wave management ──
const WAVE_SIZES = [8, 12, 16, 20, 24];

function startWave() {
  state.wave++;
  state.waveUnitsTotal = WAVE_SIZES[state.wave - 1];
  state.waveUnitsSpawned = 0;
  state.waveUnitsRemaining = state.waveUnitsTotal;
  state.waveBreakTimer = 0;
}

function endWave() {
  if (state.wave >= 5) {
    state.over = true;
    state.won = true;
    state.score += 1000;
    showOverlay('YOU WIN! Score: ' + state.score);
    return;
  }
  state.waveBreakTimer = 60; // 1 second break
}

// ── Tower firing ──
function fireTracer(fromX, fromZ, toX, toZ) {
  const geo = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(fromX, 0.5, fromZ),
    new THREE.Vector3(toX, 0.5, toZ),
  ]);
  const line = new THREE.Line(geo, tracerMat);
  tracerGroup.add(line);
  state.tracers.push({line, life: 8});
}

function towersFire() {
  for (const tower of state.towers) {
    const range = tower.level === 1 ? 2.5 : 3.5;
    const damage = tower.level === 1 ? 12 : 18;
    const tx = tower.x - COLS/2 + 0.5;
    const tz = tower.y - ROWS/2 + 0.5;

    // Find target: unit furthest along path within range
    let bestUnit = null;
    let bestWp = -1;
    for (const unit of state.units) {
      if (!unit.alive) continue;
      const ux = unit.mesh.position.x;
      const uz = unit.mesh.position.z;
      const dist = Math.sqrt((tx-ux)**2 + (tz-uz)**2);
      if (dist <= range) {
        const wpScore = unit.wp + unit.progress;
        if (wpScore > bestWp) {
          bestWp = wpScore;
          bestUnit = unit;
        }
      }
    }
    if (bestUnit) {
      bestUnit.hp -= damage;
      fireTracer(tx, tz, bestUnit.mesh.position.x, bestUnit.mesh.position.z);
      if (bestUnit.hp <= 0) {
        bestUnit.alive = false;
        state.kills++;
        state.gold += 5;
        state.waveUnitsRemaining--;
        unitGroup.remove(bestUnit.mesh);
        if (state.waveUnitsRemaining <= 0 && state.waveUnitsSpawned >= state.waveUnitsTotal) {
          endWave();
        }
      }
    }
  }
}

// ── Auto placement policy ──
function autoBuild() {
  if (state.towers.length < 6) {
    if (state.gold >= 50) {
      // Find first empty non-path tile in row-major order
      for (let r = 0; r < ROWS; r++) {
        for (let c = 0; c < COLS; c++) {
          if (!PATH_SET.has(c+','+r)) {
            const occupied = state.towers.some(t => t.x === c && t.y === r);
            if (!occupied) {
              placeTower(c, r);
              state.gold -= 50;
              return;
            }
          }
        }
      }
    }
  } else {
    // Upgrade lowest-index tower not yet upgraded
    if (state.gold >= 30) {
      for (const tower of state.towers) {
        if (tower.level < 2) {
          upgradeTower(tower);
          state.gold -= 30;
          return;
        }
      }
    }
  }
}

// ── Unit movement ──
function moveUnits(dt) {
  const speed = 1.2; // tiles per second
  for (const unit of state.units) {
    if (!unit.alive) continue;
    unit.progress += speed * dt;
    while (unit.progress >= 1 && unit.wp < PATH.length - 1) {
      unit.progress -= 1;
      unit.wp++;
    }
    if (unit.wp >= PATH.length - 1 && unit.progress >= 1) {
      // Reached end
      unit.alive = false;
      state.lives--;
      unitGroup.remove(unit.mesh);
      if (state.lives <= 0) {
        state.over = true;
        showOverlay('GAME OVER - Lives: 0');
      }
      continue;
    }
    // Interpolate position
    const from = PATH[unit.wp];
    const to = PATH[Math.min(unit.wp + 1, PATH.length - 1)];
    const fx = from[0] - COLS/2 + 0.5;
    const fz = from[1] - ROWS/2 + 0.5;
    const tx = to[0] - COLS/2 + 0.5;
    const tz = to[1] - ROWS/2 + 0.5;
    unit.mesh.position.x = fx + (tx - fx) * unit.progress;
    unit.mesh.position.z = fz + (tz - fz) * unit.progress;
  }
}

// ── HUD update ──
function updateHUD() {
  document.getElementById('hWave').textContent = state.wave;
  document.getElementById('hGold').textContent = state.gold;
  document.getElementById('hLives').textContent = state.lives;
  document.getElementById('hScore').textContent = state.score;
  document.getElementById('hTowers').textContent = state.towers.length;
}

// ── Overlay ──
function showOverlay(text) {
  const el = document.getElementById('overlay');
  el.textContent = text;
  el.classList.add('show');
}
function hideOverlay() {
  document.getElementById('overlay').classList.remove('show');
}

// ── Hash function ──
function computeHash() {
  const t = state.towers.map(t => t.x+','+t.y+','+t.level).join(';');
  const u = state.units.filter(u => u.alive).map(u => u.wp+','+Math.round(u.progress*100)).join(';');
  return state.gold + '/' + state.lives + '/' + state.wave + '/' + state.score + '/' + t + '/' + u;
}

// ── Main step function ──
function step(dt) {
  if (state.over || state.paused) return;

  state.tick++;

  // Wave spawning
  if (state.wave > 0 && state.wave <= 5) {
    if (state.waveUnitsSpawned < state.waveUnitsTotal) {
      // Spawn units at fixed intervals (every 30 ticks = 0.5s)
      if (state.tick % 30 === 0) {
        spawnUnit(state.wave);
        state.waveUnitsSpawned++;
      }
    }
  }

  // Auto build every 10 ticks
  if (state.tick % 10 === 0) {
    autoBuild();
  }

  // Tower firing every 30 ticks
  if (state.tick % 30 === 0) {
    towersFire();
  }

  // Move units
  moveUnits(dt);

  // Wave break timer
  if (state.waveBreakTimer > 0) {
    state.waveBreakTimer--;
    if (state.waveBreakTimer <= 0 && state.wave < 5) {
      startWave();
    }
  }

  // Score
  state.score = 10 * state.kills + 100 * state.wave + 25 * state.towers.length;
  if (state.won) state.score += 1000;

  // Clean up tracers
  state.tracers = state.tracers.filter(tr => {
    tr.life--;
    if (tr.life <= 0) {
      tracerGroup.remove(tr.line);
      tr.line.geometry.dispose();
      return false;
    }
    return true;
  });

  updateHUD();
}

// ── Reset ──
function reset(seed) {
  // Clean up meshes
  while (towerGroup.children.length) towerGroup.remove(towerGroup.children[0]);
  while (unitGroup.children.length) unitGroup.remove(unitGroup.children[0]);
  while (tracerGroup.children.length) tracerGroup.remove(tracerGroup.children[0]);

  state = {
    ready: false, seed: seed || 1234, gold: 200, lives: 20,
    wave: 0, kills: 0, score: 0, over: false, won: false,
    towers: [], units: [], path: PATH,
    tick: 0, paused: false,
    waveUnitsSpawned: 0, waveUnitsTotal: 0, waveUnitsRemaining: 0,
    waveBreakTimer: 0,
    buildTimer: 0,
    tracers: [],
    rng: mulberry32(seed || 1234),
  };

  hideOverlay();
  updateHUD();
  state.ready = true;
}

// ── Game loop ──
const clock = new THREE.Clock();
let lastTime = 0;

function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();
  const dt = Math.min(delta, 0.05); // cap delta

  if (state.ready && !state.paused) {
    step(dt);
  }

  renderer.render(scene, camera);
}

// ── Resize ──
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ── Controls ──
document.getElementById('btnPause').addEventListener('click', () => {
  state.paused = !state.paused;
  document.getElementById('btnPause').textContent = state.paused ? 'Resume' : 'Pause';
});

document.getElementById('btnRestart').addEventListener('click', () => {
  reset(state.seed);
});

window.addEventListener('keydown', (e) => {
  if (e.code === 'KeyR') {
    reset(state.seed);
  }
  if (e.code === 'Space') {
    e.preventDefault();
    state.paused = !state.paused;
    document.getElementById('btnPause').textContent = state.paused ? 'Resume' : 'Pause';
  }
});

// Touch controls
document.getElementById('btnPause').addEventListener('pointerdown', (e) => {
  e.preventDefault();
  state.paused = !state.paused;
  document.getElementById('btnPause').textContent = state.paused ? 'Resume' : 'Pause';
});
document.getElementById('btnRestart').addEventListener('pointerdown', (e) => {
  e.preventDefault();
  reset(state.seed);
});

// ── Expose contract ──
window.__game = {
  get ready() { return state.ready; },
  get seed() { return state.seed; },
  get gold() { return state.gold; },
  get lives() { return state.lives; },
  get wave() { return state.wave; },
  get kills() { return state.kills; },
  get towers() { return state.towers.map(t => ({x: t.x, y: t.y, level: t.level, cost: t.cost})); },
  get units() { return state.units.filter(u => u.alive).map(u => ({x: u.x, y: u.y, hp: u.hp, wp: u.wp})); },
  get path() { return state.path; },
  get score() { return state.score; },
  get over() { return state.over; },
  get won() { return state.won; },
  step,
  reset,
  hash: computeHash,
};

// ── Start ──
reset(1234);
animate();

</script>
</body>
</html>
```