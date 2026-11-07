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
  .hud{position:fixed;top:16px;left:18px;right:18px;display:flex;justify-content:space-between;
       align-items:flex-start;pointer-events:none;font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
       color:#cfe6ff;text-shadow:0 0 10px rgba(80,180,255,.55);z-index:5;}
  .brand{font-size:12px;letter-spacing:4px;color:#7fd0ff;opacity:.85;}
  .score{font-size:34px;font-weight:700;letter-spacing:2px;line-height:1;}
  .lives{font-size:22px;letter-spacing:6px;margin-top:6px;color:#ff5d7a;}
  .hint{position:fixed;bottom:14px;left:0;right:0;text-align:center;font-family:ui-monospace,monospace;
        font-size:12px;letter-spacing:2px;color:#5f7ba6;pointer-events:none;z-index:5;}
  #over{position:fixed;inset:0;display:none;flex-direction:column;align-items:center;justify-content:center;
        gap:14px;background:rgba(4,6,15,.55);backdrop-filter:blur(2px);z-index:6;
        font-family:ui-monospace,monospace;color:#fff;}
  #over h1{margin:0;font-size:64px;letter-spacing:8px;color:#ff5d7a;text-shadow:0 0 24px rgba(255,60,90,.7);}
  #over p{margin:0;font-size:16px;letter-spacing:3px;color:#9fd0ff;}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="hud">
  <div><div class="brand">NOVA STRIKE</div><div class="score" id="score">0</div></div>
  <div class="lives" id="lives">&#9679;&#9679;&#9679;</div>
</div>
<div class="hint">&larr; &rarr; / A D &nbsp;move &nbsp;&middot;&nbsp; SPACE &nbsp;fire &nbsp;&middot;&nbsp; R &nbsp;restart</div>
<div id="over"><h1>GAME OVER</h1><p>PRESS R TO RESTART</p></div>

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
scene.fog = new THREE.Fog(0x04060f, 120, 320);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 0, 0);

scene.add(new THREE.AmbientLight(0x334466, 1.2));
const key = new THREE.DirectionalLight(0x88bbff, 1.4); key.position.set(0, 0, 1); scene.add(key);
const rim = new THREE.PointLight(0xff5d7a, 1.2, 200); rim.position.set(0, 0, 40); scene.add(rim);

// Starfield
const STAR_N = 700, starGeo = new THREE.BufferGeometry(), starPos = new Float32Array(STAR_N * 3);
for (let i = 0; i < STAR_N; i++) {
  starPos[i*3] = (Math.random()*2-1)*120;
  starPos[i*3+1] = (Math.random()*2-1)*70;
  starPos[i*3+2] = -Math.random()*300;
}
starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xbfe0ff, size: 1.4, sizeAttenuation: true, transparent: true, opacity: 0.9 }));
scene.add(stars);

// Shared geometry / materials
const playerGeo = new THREE.ConeGeometry(1.4, 3.2, 4);
const playerMat = new THREE.MeshStandardMaterial({ color: 0x22d3ee, emissive: 0x0e7490, emissiveIntensity: 1.2, metalness: 0.4, roughness: 0.3 });
const player = new THREE.Mesh(playerGeo, playerMat);
player.rotation.x = Math.PI / 2;
player.position.set(0, -12, 20);
scene.add(player);

const bulletGeo = new THREE.BoxGeometry(0.5, 0.5, 2.4);
const bulletMat = new THREE.MeshStandardMaterial({ color: 0xfff2a8, emissive: 0xffd24a, emissiveIntensity: 2.2 });
const enemyGeo = new THREE.OctahedronGeometry(1.6, 0);
const enemyMats = [
  new THREE.MeshStandardMaterial({ color: 0xff5d7a, emissive: 0x7a1020, emissiveIntensity: 1.0 }),
  new THREE.MeshStandardMaterial({ color: 0xffb020, emissive: 0x7a4a00, emissiveIntensity: 1.0 }),
  new THREE.MeshStandardMaterial({ color: 0x9d6bff, emissive: 0x3a1a7a, emissiveIntensity: 1.0 }),
];
const boomGeo = new THREE.SphereGeometry(1, 12, 12);
const boomMat = new THREE.MeshBasicMaterial({ color: 0xffd24a, transparent: true, opacity: 0.9 });

const bullets = [], enemies = [], booms = [];
const keys = {};
let score = 0, lives = 3, over = false, ready = false, fireCd = 0, spawnT = 0, shake = 0;
const MAX_ENEMIES = 14, PLAYER_X = 40, PLAYER_Y = 12, BULLET_SPEED = 130, STAR_SPEED = 45;

const scoreEl = document.getElementById('score');
const livesEl = document.getElementById('lives');
const overEl = document.getElementById('over');

function toScreen(v) {
  const p = v.clone().project(camera);
  return { x: (p.x * 0.5 + 0.5) * canvas.clientWidth, y: (-p.y * 0.5 + 0.5) * canvas.clientHeight };
}
function fire() {
  const b = new THREE.Mesh(bulletGeo, bulletMat);
  b.position.set(player.position.x, player.position.y + 2, player.position.z);
  scene.add(b); bullets.push(b);
}
function spawnEnemy() {
  const e = new THREE.Mesh(enemyGeo, enemyMats[(Math.random() * enemyMats.length) | 0]);
  e.position.set((Math.random()*2-1)*PLAYER_X, 10 + Math.random()*10, -150);
  e.userData.speed = 22 + Math.random()*26;
  e.userData.spin = (Math.random()*2-1)*2;
  scene.add(e); enemies.push(e);
}
function boom(pos) {
  const m = new THREE.Mesh(boomGeo, boomMat.clone());
  m.position.copy(pos); m.scale.setScalar(0.1); m.userData.life = 0.4;
  scene.add(m); booms.push(m);
}
function removeEnemy(e) { scene.remove(e); const i = enemies.indexOf(e); if (i >= 0) enemies.splice(i, 1); }
function removeBullet(b) { scene.remove(b); const i = bullets.indexOf(b); if (i >= 0) bullets.splice(i, 1); }
function removeBoom(m) { scene.remove(m); const i = booms.indexOf(m); if (i >= 0) booms.splice(i, 1); }

function reset() {
  for (const b of bullets.slice()) removeBullet(b);
  for (const e of enemies.slice()) removeEnemy(e);
  for (const m of booms.slice()) removeBoom(m);
  score = 0; lives = 3; over = false; fireCd = 0; spawnT = 0; shake = 0;
  player.position.set(0, PLAYER_Y, 20);
  overEl.style.display = 'none';
  updateHud();
}
function updateHud() {
  scoreEl.textContent = score;
  livesEl.innerHTML = lives > 0 ? '&#9679;'.repeat(lives) : '&#9675;';
  overEl.style.display = over ? 'flex' : 'none';
}

window.addEventListener('keydown', (e) => {
  const k = e.key;
  if (k === ' ' || k === 'ArrowLeft' || k === 'ArrowRight' || k === 'ArrowUp' || k === 'ArrowDown') e.preventDefault();
  keys[k] = true;
  if ((k === 'r' || k === 'R') && over) reset();
});
window.addEventListener('keyup', (e) => { keys[e.key] = false; });
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  let dt = clock.getDelta();
  if (!isFinite(dt) || dt < 0) dt = 0;
  if (dt > 0.05) dt = 0.05;

  const sp = starGeo.attributes.position.array;
  for (let i = 0; i < STAR_N; i++) {
    sp[i*3+2] += STAR_SPEED * dt;
    if (sp[i*3+2] > 10) sp[i*3+2] = -300;
  }
  starGeo.attributes.position.needsUpdate = true;

  if (!over) {
    const mv = 42 * dt;
    if (keys['ArrowLeft'] || keys['a']) player.position.x -= mv;
    if (keys['ArrowRight'] || keys['d']) player.position.x += mv;
    player.position.x = Math.max(-PLAYER_X, Math.min(PLAYER_X, player.position.x));
    player.rotation.z = (keys['ArrowLeft'] || keys['a'] ? 0.25 : 0) + (keys['ArrowRight'] || keys['d'] ? -0.25 : 0);

    fireCd -= dt;
    if (keys[' '] && fireCd <= 0) { fire(); fireCd = 0.18; }

    spawnT -= dt;
    if (spawnT <= 0 && enemies.length < MAX_ENEMIES) { spawnEnemy(); spawnT = 0.7 + Math.random()*0.8; }

    for (const b of bullets.slice()) {
      b.position.z -= BULLET_SPEED * dt;
      if (b.position.z < -160) removeBullet(b);
    }
    for (const e of enemies.slice()) {
      e.position.z += e.userData.speed * dt;
      e.rotation.x += e.userData.spin * dt;
      e.rotation.y += e.userData.spin * dt;
      if (e.position.z > 30) { removeEnemy(e); continue; }
      for (const b of bullets.slice()) {
        if (e.position.distanceTo(b.position) < 2.4) {
          boom(e.position); removeEnemy(e); removeBullet(b); score += 10; updateHud(); break;
        }
      }
      if (enemies.includes(e) && e.position.distanceTo(player.position) < 3.2) {
        removeEnemy(e); lives--; shake = 0.5; updateHud();
        if (lives <= 0) over = true;
      }
    }
  }
  for (const m of booms.slice()) {
    m.userData.life -= dt;
    m.scale.setScalar(Math.max(0.1, m.scale.x + 14 * dt));
    m.material.opacity = Math.max(0, m.userData.life / 0.4);
    if (m.userData.life <= 0) removeBoom(m);
  }

  shake = Math.max(0, shake - dt);
  camera.position.x = (Math.random()*2-1) * shake * 0.6;
  camera.position.y = (Math.random()*2-1) * shake * 0.6;
  camera.lookAt(0, 0, -100);

  renderer.render(scene, camera);

  window.__game = {
    ready: true, score, lives, over,
    player: toScreen(player.position),
    enemies: enemies.map(e => toScreen(e.position)),
    bullets: bullets.map(b => toScreen(b.position)),
    reset
  };
  ready = true;
}
window.__game = { ready: false, score: 0, lives: 3, over: false, player: { x: 0, y: 0 }, enemies: [], bullets: [], reset };
updateHud();
animate();
</script>
</body>
</html>
```