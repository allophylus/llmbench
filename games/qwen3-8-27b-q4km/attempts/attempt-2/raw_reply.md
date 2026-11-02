```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NOVA STRIKE</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#04060f;}
  #c{position:fixed;inset:0;display:block;}
  .hud{position:fixed;top:0;left:0;right:0;display:flex;justify-content:space-between;
       padding:16px 22px;pointer-events:none;font-family:ui-monospace,Menlo,Consolas,monospace;
       color:#cfe6ff;text-shadow:0 0 12px rgba(80,180,255,.55);z-index:5;}
  .hud .lab{font-size:11px;letter-spacing:3px;opacity:.65;}
  .hud .val{font-size:30px;font-weight:700;line-height:1;}
  .hud .lives{font-size:24px;letter-spacing:4px;color:#ff5d7a;text-shadow:0 0 12px rgba(255,90,120,.6);}
  .title{position:fixed;top:14px;left:50%;transform:translateX(-50%);text-align:center;
         pointer-events:none;font-family:ui-monospace,Menlo,Consolas,monospace;z-index:5;}
  .title h1{margin:0;font-size:22px;letter-spacing:8px;color:#eaf6ff;text-shadow:0 0 18px rgba(120,200,255,.7);}
  .title p{margin:4px 0 0;font-size:10px;letter-spacing:3px;opacity:.55;}
  .over{position:fixed;inset:0;display:none;flex-direction:column;align-items:center;justify-content:center;
        gap:14px;pointer-events:none;font-family:ui-monospace,Menlo,Consolas,monospace;z-index:6;
        background:radial-gradient(circle at 50% 45%,rgba(120,20,40,.35),rgba(0,0,0,.55));}
  .over h2{margin:0;font-size:64px;letter-spacing:10px;color:#ff5d7a;text-shadow:0 0 30px rgba(255,60,90,.8);}
  .over p{margin:0;font-size:16px;letter-spacing:4px;color:#eaf6ff;animation:blink 1s steps(2) infinite;}
  @keyframes blink{50%{opacity:.25;}}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="title"><h1>NOVA STRIKE</h1><p>ARROWS / A D &nbsp;·&nbsp; SPACE FIRE &nbsp;·&nbsp; R RESTART</p></div>
<div class="hud">
  <div><div class="lab">SCORE</div><div class="val" id="score">0</div></div>
  <div style="text-align:right"><div class="lab">LIVES</div><div class="lives" id="lives">♥ ♥ ♥</div></div>
</div>
<div class="over" id="over"><h2>GAME OVER</h2><p>PRESS R TO RESTART</p></div>

<script type="importmap">
{"imports": {"three": "https://unpkg.com/three@0.160.0/build/three.module.js"}}
</script>
<script type="module">
import * as THREE from 'three';

const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x04060f);
scene.fog = new THREE.Fog(0x04060f, 40, 150);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 400);
camera.position.set(0, 0, 12);
camera.lookAt(0, 0, 0);

scene.add(new THREE.AmbientLight(0x334466, 0.9));
const key = new THREE.DirectionalLight(0x88bbff, 1.1); key.position.set(4, 8, 10); scene.add(key);
const rim = new THREE.PointLight(0xff5d7a, 1.2, 60); rim.position.set(-6, 2, 6); scene.add(rim);

// Starfield
const STAR_N = 700, starPos = new Float32Array(STAR_N * 3);
for (let i = 0; i < STAR_N; i++) {
  starPos[i*3]   = (Math.random()*2-1) * 40;
  starPos[i*3+1] = (Math.random()*2-1) * 24;
  starPos[i*3+2] = -Math.random() * 140;
}
const starGeo = new THREE.BufferGeometry();
starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xbfe0ff, size: 0.5, sizeAttenuation: true, transparent: true, opacity: 0.9 }));
scene.add(stars);

// Shared geometry / materials
const playerGeo = new THREE.ConeGeometry(0.7, 1.6, 4);
const playerMat = new THREE.MeshStandardMaterial({ color: 0x22d3ee, emissive: 0x0e7490, emissiveIntensity: 0.8, metalness: 0.4, roughness: 0.4 });
const bulletGeo = new THREE.BoxGeometry(0.22, 1.1, 0.22);
const bulletMat = new THREE.MeshStandardMaterial({ color: 0xfff2a8, emissive: 0xffd24a, emissiveIntensity: 1.6 });
const enemyGeo = new THREE.OctahedronGeometry(0.85, 0);
const enemyMats = [
  new THREE.MeshStandardMaterial({ color: 0xff5d7a, emissive: 0x7a1020, emissiveIntensity: 0.9 }),
  new THREE.MeshStandardMaterial({ color: 0xffb020, emissive: 0x7a4a00, emissiveIntensity: 0.9 }),
  new THREE.MeshStandardMaterial({ color: 0x9d6bff, emissive: 0x3a1a7a, emissiveIntensity: 0.9 }),
];
const boomGeo = new THREE.SphereGeometry(0.5, 12, 12);
const boomMat = new THREE.MeshBasicMaterial({ color: 0xffd24a, transparent: true, opacity: 1 });

const player = new THREE.Mesh(playerGeo, playerMat);
player.rotation.x = Math.PI / 2;
player.position.set(0, -4, 0);
scene.add(player);

const BOUND = 10, MAX_ENEMIES = 12, MAX_BULLETS = 40, COOLDOWN = 0.18;
let score = 0, lives = 3, over = false, ready = false;
let lastShot = 0, spawnTimer = 0, spawnInterval = 1.1, invuln = 0;
const enemies = [], bullets = [], booms = [];
const keys = {};

const scoreEl = document.getElementById('score');
const livesEl = document.getElementById('lives');
const overEl = document.getElementById('over');

function toScreen(v) {
  const p = v.clone().project(camera);
  return { x: (p.x * 0.5 + 0.5) * canvas.clientWidth, y: (-p.y * 0.5 + 0.5) * canvas.clientHeight };
}

function spawnEnemy() {
  if (enemies.length >= MAX_ENEMIES) return;
  const m = new THREE.Mesh(enemyGeo, enemyMats[(Math.random() * enemyMats.length) | 0]);
  m.position.set((Math.random()*2-1) * 9, 3, -40 - Math.random() * 20);
  m.userData = { speed: 6 + Math.random() * 6, spin: (Math.random()*2-1) * 2 };
  scene.add(m); enemies.push(m);
}

function fire() {
  if (bullets.length >= MAX_BULLETS) return;
  const b = new THREE.Mesh(bulletGeo, bulletMat);
  b.position.set(player.position.x, player.position.y + 1, player.position.z);
  scene.add(b); bullets.push(b);
}

function boom(pos) {
  const s = new THREE.Mesh(boomGeo, boomMat.clone());
  s.position.copy(pos); s.scale.setScalar(0.1);
  scene.add(s); booms.push({ mesh: s, life: 0.4 });
}

function removeEnemy(e) {
  scene.remove(e); const i = enemies.indexOf(e); if (i >= 0) enemies.splice(i, 1);
}
function removeBullet(b) {
  scene.remove(b); const i = bullets.indexOf(b); if (i >= 0) bullets.splice(i, 1);
}

function reset() {
  for (const e of enemies.slice()) removeEnemy(e);
  for (const b of bullets.slice()) removeBullet(b);
  for (const o of booms.slice()) { scene.remove(o.mesh); o.mesh.material.dispose(); }
  booms.length = 0;
  score = 0; lives = 3; over = false; invuln = 0; lastShot = 0; spawnTimer = 0; spawnInterval = 1.1;
  player.position.set(0, -4, 0);
  overEl.style.display = 'none';
  updateHUD();
}

function updateHUD() {
  scoreEl.textContent = String(score);
  livesEl.textContent = '♥ '.repeat(Math.max(0, lives)).trim() || '—';
  overEl.style.display = over ? 'flex' : 'none';
}

function gameOver() {
  over = true; updateHUD();
}

function update(dt, t) {
  // player
  let dir = 0;
  if (keys['ArrowLeft'] || keys['a']) dir -= 1;
  if (keys['ArrowRight'] || keys['d']) dir += 1;
  player.position.x = THREE.MathUtils.clamp(player.position.x + dir * 16 * dt, -BOUND, BOUND);
  player.rotation.z = -dir * 0.35;
  player.position.y = -4 + Math.sin(t * 3) * 0.12;

  // shooting
  if (keys[' '] && t - lastShot >= COOLDOWN) { fire(); lastShot = t; }

  // spawn
  spawnTimer += dt;
  if (spawnTimer >= spawnInterval) { spawnTimer = 0; spawnEnemy(); spawnInterval = Math.max(0.45, spawnInterval - 0.02); }

  // bullets
  for (const b of bullets.slice()) {
    b.position.z += 45 * dt;
    if (b.position.z > 14) removeBullet(b);
  }

  // enemies
  for (const e of enemies.slice()) {
    e.position.z += e.userData.speed * dt;
    e.rotation.x += e.userData.spin * dt;
    e.rotation.y += e.userData.spin * 0.7 * dt;
    if (e.position.z > 14) { removeEnemy(e); continue; }
    // vs player
    if (invuln <= 0 && e.position.distanceTo(player.position) < 1.6) {
      boom(e.position); removeEnemy(e);
      lives--; invuln = 1.2; updateHUD();
      if (lives <= 0) { gameOver(); break; }
    }
  }
  if (invuln > 0) invuln -= dt;
  playerMat.emissiveIntensity = invuln > 0 ? (Math.sin(t * 30) > 0 ? 1.6 : 0.2) : 0.8;

  // collisions bullet vs enemy
  for (const b of bullets.slice()) {
    for (const e of enemies.slice()) {
      if (b.position.distanceTo(e.position) < 1.2) {
        boom(e.position); removeEnemy(e); removeBullet(b);
        score += 10; updateHUD(); break;
      }
    }
  }

  // explosions
  for (const o of booms.slice()) {
    o.life -= dt;
    o.mesh.scale.setScalar(0.1 + (0.4 - o.life) * 6);
    o.mesh.material.opacity = Math.max(0, o.life / 0.4);
    if (o.life <= 0) { scene.remove(o.mesh); o.mesh.material.dispose(); booms.splice(booms.indexOf(o), 1); }
  }

  // starfield scroll
  const sp = starGeo.attributes.position;
  for (let i = 0; i < STAR_N; i++) {
    let z = sp.getZ(i) + 22 * dt;
    if (z > 12) z -= 152;
    sp.setZ(i, z);
  }
  sp.needsUpdate = true;
}

function publish() {
  window.__game = {
    ready, score, lives, over,
    player: toScreen(player.position),
    enemies: enemies.map(e => toScreen(e.position)),
    bullets: bullets.map(b => toScreen(b.position)),
    reset
  };
}

window.addEventListener('keydown', (e) => {
  const k = e.key;
  if (k === ' ') e.preventDefault();
  keys[k] = true;
  if (k === 'r' || k === 'R') reset();
});
window.addEventListener('keyup', (e) => { keys[e.key] = false; });

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const clock = new THREE.Clock();
function loop() {
  requestAnimationFrame(loop);
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.elapsedTime;
  if (!over) update(dt, t);
  renderer.render(scene, camera);
  publish();
  ready = true;
}
updateHUD();
loop();
</script>
</body>
</html>
```