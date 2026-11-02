```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NOVA STRIKE</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:100%;height:100%;overflow:hidden;background:#04060f}
  body{font-family:'Courier New',ui-monospace,monospace;color:#cfe6ff}
  #c{position:fixed;inset:0;display:block}
  .hud{position:fixed;top:0;left:0;right:0;display:flex;justify-content:space-between;
       padding:16px 22px;pointer-events:none;z-index:5;
       text-shadow:0 0 12px rgba(80,200,255,.55)}
  .lbl{font-size:11px;letter-spacing:3px;opacity:.65}
  .val{font-size:30px;font-weight:700;letter-spacing:2px}
  #score{color:#7ff0ff}
  #lives{color:#ff5d7a;font-size:26px;letter-spacing:4px}
  .hint{position:fixed;bottom:16px;left:0;right:0;text-align:center;font-size:12px;
        letter-spacing:2px;opacity:.5;pointer-events:none;z-index:5}
  #over{position:fixed;inset:0;display:none;flex-direction:column;align-items:center;
        justify-content:center;gap:14px;background:rgba(4,6,15,.55);z-index:10}
  #over h1{font-size:64px;letter-spacing:8px;color:#ff5d7a;
           text-shadow:0 0 26px rgba(255,60,90,.7)}
  #over p{font-size:16px;letter-spacing:3px;opacity:.85;animation:blink 1.1s steps(2) infinite}
  @keyframes blink{50%{opacity:.25}}
</style>
<script type="importmap">
{"imports": {"three": "https://unpkg.com/three@0.160.0/build/three.module.js"}}
</script>
</head>
<body>
<canvas id="c"></canvas>
<div class="hud">
  <div><div class="lbl">SCORE</div><div class="val" id="score">0</div></div>
  <div style="text-align:right"><div class="lbl">LIVES</div><div class="val" id="lives">♥ ♥ ♥</div></div>
</div>
<div class="hint">◄ ► / A D &nbsp;MOVE &nbsp;·&nbsp; SPACE &nbsp;FIRE &nbsp;·&nbsp; R &nbsp;RESTART</div>
<div id="over"><h1>GAME OVER</h1><p>PRESS R TO RESTART</p></div>

<script type="module">
import * as THREE from 'three';

const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({canvas, antialias:true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x04060f);
scene.fog = new THREE.Fog(0x04060f, 40, 150);

const camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 400);
camera.position.set(0, 0, 12);
camera.lookAt(0, 0, -10);

scene.add(new THREE.AmbientLight(0x334466, 0.9));
const key = new THREE.DirectionalLight(0x88bbff, 1.1); key.position.set(4, 8, 10); scene.add(key);
const rim = new THREE.PointLight(0xff5d7a, 1.2, 60); rim.position.set(-6, 2, 4); scene.add(rim);

// ---- Starfield (scrolls past the camera) ----
const STAR_N = 700, STAR_Z = 160;
const starGeo = new THREE.BufferGeometry();
const starPos = new Float32Array(STAR_N * 3);
for (let i = 0; i < STAR_N; i++){
  starPos[i*3]   = (Math.random()*2 - 1) * 45;
  starPos[i*3+1] = (Math.random()*2 - 1) * 28;
  starPos[i*3+2] = -Math.random() * STAR_Z;
}
starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({
  color:0xbfe0ff, size:0.5, sizeAttenuation:true, transparent:true, opacity:0.9, depthWrite:false
}));
scene.add(stars);

// ---- Shared geometry / materials ----
const playerGeo = new THREE.ConeGeometry(0.7, 1.8, 4);
const playerMat = new THREE.MeshStandardMaterial({color:0x2fd6ff, emissive:0x0a5f8a, metalness:0.4, roughness:0.35});
const projGeo = new THREE.BoxGeometry(0.28, 1.1, 0.28);
const projMat = new THREE.MeshStandardMaterial({color:0xffffff, emissive:0x66f0ff, emissiveIntensity:1.6});
const enemyGeo = new THREE.OctahedronGeometry(0.9, 0);
const enemyMats = [
  new THREE.MeshStandardMaterial({color:0xff5d7a, emissive:0x7a1020, metalness:0.3, roughness:0.5}),
  new THREE.MeshStandardMaterial({color:0xffb020, emissive:0x6a3a00, metalness:0.3, roughness:0.5}),
  new THREE.MeshStandardMaterial({color:0x9d5cff, emissive:0x2a0a6a, metalness:0.3, roughness:0.5}),
];
const boomGeo = new THREE.SphereGeometry(0.5, 12, 12);
const boomMat = new THREE.MeshBasicMaterial({color:0xffd27a, transparent:true, opacity:1, depthWrite:false});

// ---- Player ----
const player = new THREE.Mesh(playerGeo, playerMat);
player.rotation.x = Math.PI / 2;
player.position.set(0, -4, 6);
scene.add(player);

// ---- State ----
const BOUND_X = 10, PROJ_SPEED = 55, ENEMY_CAP = 14, COOLDOWN = 0.18;
let score = 0, lives = 3, gameOver = false;
let projectiles = [], enemies = [], booms = [];
let fireTimer = 0, spawnTimer = 0, invuln = 0;
const keys = {};

const scoreEl = document.getElementById('score');
const livesEl = document.getElementById('lives');
const overEl  = document.getElementById('over');

function updateHUD(){
  scoreEl.textContent = score;
  livesEl.textContent = lives > 0 ? '♥ '.repeat(lives).trim() : '—';
}
function spawnEnemy(){
  const m = new THREE.Mesh(enemyGeo, enemyMats[(Math.random()*enemyMats.length)|0]);
  m.position.set((Math.random()*2 - 1) * 12, 4, -55 - Math.random() * 20);
  m.userData.speed = 8 + Math.random() * 10;
  m.userData.spin  = (Math.random() - 0.5) * 4;
  scene.add(m); enemies.push(m);
}
function fire(){
  const p = new THREE.Mesh(projGeo, projMat);
  p.position.set(player.position.x, player.position.y + 1.2, player.position.z);
  scene.add(p); projectiles.push(p);
}
function boom(pos){
  const b = new THREE.Mesh(boomGeo, boomMat.clone());
  b.position.copy(pos); b.scale.setScalar(0.6); b.userData.life = 0.4;
  scene.add(b); booms.push(b);
}
function removeEnemy(e){ scene.remove(e); enemies.splice(enemies.indexOf(e), 1); }
function removeProjectile(p){ scene.remove(p); projectiles.splice(projectiles.indexOf(p), 1); }
function hitPlayer(){
  lives--; invuln = 1.2; updateHUD();
  if (lives <= 0){ gameOver = true; overEl.style.display = 'flex'; }
}
function reset(){
  for (const e of enemies.slice()) removeEnemy(e);
  for (const p of projectiles.slice()) removeProjectile(p);
  for (const b of booms.slice()){ scene.remove(b); b.material.dispose(); }
  booms.length = 0;
  score = 0; lives = 3; gameOver = false; fireTimer = 0; spawnTimer = 0; invuln = 0;
  player.position.set(0, -4, 6);
  overEl.style.display = 'none'; updateHUD();
}

// ---- Input ----
addEventListener('keydown', e => {
  if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Space'].includes(e.code)) e.preventDefault();
  keys[e.code] = true;
  if (e.code === 'KeyR' && gameOver) reset();
});
addEventListener('keyup', e => { keys[e.code] = false; });
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// ---- Loop ----
const clock = new THREE.Clock();
function animate(){
  requestAnimationFrame(animate);
  let dt = clock.getDelta();
  if (!isFinite(dt) || dt < 0) dt = 0;
  if (dt > 0.05) dt = 0.05;

  // starfield scroll
  const sp = starGeo.attributes.position;
  for (let i = 0; i < STAR_N; i++){
    let z = sp.getZ(i) + dt * 22;
    if (z > 12) z -= STAR_Z;
    sp.setZ(i, z);
  }
  sp.needsUpdate = true;

  if (!gameOver){
    // player movement (dt-scaled, clamped)
    let dir = 0;
    if (keys['ArrowLeft']  || keys['KeyA']) dir -= 1;
    if (keys['ArrowRight'] || keys['KeyD']) dir += 1;
    player.position.x = THREE.MathUtils.clamp(player.position.x + dir * 22 * dt, -BOUND_X, BOUND_X);
    player.rotation.z = -dir * 0.35;

    // shooting
    fireTimer -= dt;
    if (keys['Space'] && fireTimer <= 0){ fire(); fireTimer = COOLDOWN; }

    // spawning
    spawnTimer -= dt;
    if (spawnTimer <= 0 && enemies.length < ENEMY_CAP){
      spawnEnemy();
      spawnTimer = Math.max(0.35, 1.1 - score * 0.004);
    }

    // projectiles
    for (let i = projectiles.length - 1; i >= 0; i--){
      const p = projectiles[i];
      p.position.z -= PROJ_SPEED * dt;
      if (p.position.z < -70) removeProjectile(p);
    }

    // enemies
    for (let i = enemies.length - 1; i >= 0; i--){
      const e = enemies[i];
      e.position.z += e.userData.speed * dt;
      e.rotation.x += e.userData.spin * dt;
      e.rotation.y += e.userData.spin * 0.7 * dt;
      if (e.position.z > 14) removeEnemy(e);
    }

    // collisions: projectile vs enemy
    for (let i = enemies.length - 1; i >= 0; i--){
      const e = enemies[i];
      for (let j = projectiles.length - 1; j >= 0; j--){
        const p = projectiles[j];
        if (e.position.distanceTo(p.position) < 1.4){
          boom(e.position); removeEnemy(e); removeProjectile(p);
          score += 10; updateHUD(); break;
        }
      }
    }

    // collisions: enemy vs player
    if (invuln > 0) invuln -= dt;
    if (invuln <= 0){
      for (let i = enemies.length - 1; i >= 0; i--){
        const e = enemies[i];
        if (e.position.distanceTo(player.position) < 1.7){
          boom(e.position); removeEnemy(e); hitPlayer(); break;
        }
      }
    }
  }

  // explosions
  for (let i = booms.length - 1; i >= 0; i--){
    const b = booms[i];
    b.userData.life -= dt;
    b.scale.setScalar(0.6 + (0.4 - b.userData.life) * 6);
    b.material.opacity = Math.max(0, b.userData.life / 0.4);
    if (b.userData.life <= 0){ scene.remove(b); b.material.dispose(); booms.splice(i, 1); }
  }

  // player flicker while invulnerable
  player.visible = invuln <= 0 || (Math.floor(invuln * 12) % 2 === 0);

  renderer.render(scene, camera);
}
updateHUD();
animate();
</script>
</body>
</html>
```