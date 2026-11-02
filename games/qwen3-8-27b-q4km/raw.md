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
  .lbl{font-size:11px;letter-spacing:3px;opacity:.6}
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
</head>
<body>
<canvas id="c"></canvas>
<div class="hud">
  <div><div class="lbl">SCORE</div><div class="val" id="score">0</div></div>
  <div style="text-align:right"><div class="lbl">LIVES</div><div class="val" id="lives">♥ ♥ ♥</div></div>
</div>
<div class="hint">◄ ► / A D &nbsp;MOVE &nbsp;·&nbsp; SPACE &nbsp;FIRE &nbsp;·&nbsp; R &nbsp;RESTART</div>
<div id="over"><h1>GAME OVER</h1><p>PRESS R TO RESTART</p></div>

<script type="importmap">
{"imports": {"three": "https://unpkg.com/three@0.160.0/build/three.module.js"}}
</script>
<script type="module">
import * as THREE from 'three';

const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({canvas, antialias:true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
renderer.setSize(innerWidth, innerHeight);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x04060f);
scene.fog = new THREE.Fog(0x04060f, 40, 150);

const camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 400);
camera.position.set(0, 0, 14);
camera.lookAt(0, 0, -40);

scene.add(new THREE.AmbientLight(0x334466, 0.9));
const key = new THREE.DirectionalLight(0x88bbff, 1.1); key.position.set(4,8,10); scene.add(key);
const rim = new THREE.PointLight(0xff5d7a, 1.2, 60); rim.position.set(-6,-4,6); scene.add(rim);

// ---- Starfield (scrolls past the camera) ----
const STAR_N = 900, starPos = new Float32Array(STAR_N*3);
for(let i=0;i<STAR_N;i++){
  starPos[i*3]   = (Math.random()*2-1)*70;
  starPos[i*3+1] = (Math.random()*2-1)*45;
  starPos[i*3+2] = -Math.random()*150;
}
const starGeo = new THREE.BufferGeometry();
starGeo.setAttribute('position', new THREE.BufferAttribute(starPos,3));
const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({color:0xbfe0ff,size:0.5,sizeAttenuation:true,transparent:true,opacity:0.9}));
scene.add(stars);

// ---- Shared geometry / materials ----
const playerGeo = new THREE.ConeGeometry(0.7,1.6,4);
const playerMat = new THREE.MeshStandardMaterial({color:0x22d3ee,emissive:0x0e7490,emissiveIntensity:0.8,metalness:0.4,roughness:0.4});
const projGeo = new THREE.BoxGeometry(0.22,1.1,0.22);
const projMat = new THREE.MeshStandardMaterial({color:0xffffff,emissive:0x67e8f9,emissiveIntensity:2.2});
const enemyGeo = new THREE.OctahedronGeometry(0.85,0);
const enemyMats = [
  new THREE.MeshStandardMaterial({color:0xff5d7a,emissive:0x7a1024,emissiveIntensity:0.9,metalness:0.3,roughness:0.5}),
  new THREE.MeshStandardMaterial({color:0xffb020,emissive:0x7a4a00,emissiveIntensity:0.9,metalness:0.3,roughness:0.5}),
  new THREE.MeshStandardMaterial({color:0x9d6bff,emissive:0x3a1a7a,emissiveIntensity:0.9,metalness:0.3,roughness:0.5}),
];
const boomGeo = new THREE.IcosahedronGeometry(0.5,0);
const boomMat = new THREE.MeshBasicMaterial({color:0xffd27a,transparent:true,opacity:1});

// ---- Player ----
const player = new THREE.Mesh(playerGeo, playerMat);
player.rotation.x = Math.PI/2;
player.position.set(0,-6,10);
scene.add(player);

// ---- State ----
const keys = {};
let score=0, lives=3, over=false, fireCd=0, spawnT=0;
const projectiles=[], enemies=[], booms=[];
const scoreEl=document.getElementById('score'), livesEl=document.getElementById('lives'), overEl=document.getElementById('over');

function updateHUD(){
  scoreEl.textContent = score;
  livesEl.textContent = lives>0 ? '♥ '.repeat(lives).trim() : '—';
}
function spawnEnemy(){
  const m = new THREE.Mesh(enemyGeo, enemyMats[(Math.random()*enemyMats.length)|0]);
  m.position.set((Math.random()*2-1)*16, 2, -70);
  m.userData = {speed: 6+Math.random()*8, spin: (Math.random()*2-1)*3};
  scene.add(m); enemies.push(m);
}
function spawnBoom(p){
  const b = new THREE.Mesh(boomGeo, boomMat.clone());
  b.position.copy(p); b.userData = {life:0.45};
  scene.add(b); booms.push(b);
}
function removeObj(arr,o){ const i=arr.indexOf(o); if(i>=0) arr.splice(i,1); }
function killEnemy(e){
  scene.remove(e); removeObj(enemies,e);
  spawnBoom(e.position); score += 10; updateHUD();
}
function hitPlayer(){
  lives--; updateHUD();
  spawnBoom(player.position);
  if(lives<=0){ over=true; overEl.style.display='flex'; }
}
function reset(){
  score=0; lives=3; over=false; fireCd=0; spawnT=0;
  player.position.set(0,-6,10);
  for(const p of projectiles) scene.remove(p);
  for(const e of enemies) scene.remove(e);
  for(const b of booms) scene.remove(b);
  projectiles.length=0; enemies.length=0; booms.length=0;
  overEl.style.display='none'; updateHUD();
}

// ---- Input ----
addEventListener('keydown', e=>{
  if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Space'].includes(e.code)) e.preventDefault();
  keys[e.code]=true;
  if(e.code==='KeyR') reset();
});
addEventListener('keyup', e=>{ keys[e.code]=false; });

// ---- Resize ----
addEventListener('resize', ()=>{
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// ---- Loop ----
const clock = new THREE.Clock();
function animate(){
  requestAnimationFrame(animate);
  let dt = clock.getDelta();
  if(!isFinite(dt) || dt<=0) dt=0;
  if(dt>0.05) dt=0.05;

  // starfield scroll
  const sp = starGeo.attributes.position.array;
  for(let i=0;i<STAR_N;i++){
    sp[i*3+2] += 26*dt;
    if(sp[i*3+2] > 12){ sp[i*3+2] = -150; sp[i*3] = (Math.random()*2-1)*70; sp[i*3+1] = (Math.random()*2-1)*45; }
  }
  starGeo.attributes.position.needsUpdate = true;

  if(!over){
    // player movement (dt-scaled, clamped)
    let mv = 0;
    if(keys['ArrowLeft']||keys['KeyA']) mv -= 1;
    if(keys['ArrowRight']||keys['KeyD']) mv += 1;
    player.position.x += mv*22*dt;
    player.position.x = Math.max(-16, Math.min(16, player.position.x));
    player.rotation.z = -mv*0.35;

    // shooting
    fireCd -= dt;
    if(keys['Space'] && fireCd<=0){
      const p = new THREE.Mesh(projGeo, projMat);
      p.position.set(player.position.x, player.position.y+1.2, player.position.z);
      scene.add(p); projectiles.push(p); fireCd = 0.18;
    }

    // spawn enemies (capped)
    spawnT -= dt;
    if(spawnT<=0 && enemies.length<14){ spawnEnemy(); spawnT = 0.7 + Math.random()*0.8; }
  }

  // projectiles
  for(let i=projectiles.length-1;i>=0;i--){
    const p = projectiles[i];
    p.position.z -= 55*dt;
    if(p.position.z < -80){ scene.remove(p); removeObj(projectiles,p); }
  }

  // enemies
  for(let i=enemies.length-1;i>=0;i--){
    const e = enemies[i];
    e.position.z += e.userData.speed*dt;
    e.rotation.x += e.userData.spin*dt;
    e.rotation.y += e.userData.spin*0.7*dt;
    if(e.position.z > 12){ scene.remove(e); removeObj(enemies,e); if(!over) hitPlayer(); }
  }

  // collisions
  for(let i=enemies.length-1;i>=0;i--){
    const e = enemies[i];
    for(let j=projectiles.length-1;j>=0;j--){
      const p = projectiles[j];
      if(e.position.distanceTo(p.position) < 1.4){
        scene.remove(p); removeObj(projectiles,p);
        killEnemy(e); break;
      }
    }
    if(!over && e.position.distanceTo(player.position) < 1.7){
      scene.remove(e); removeObj(enemies,e); hitPlayer();
    }
  }

  // explosions
  for(let i=booms.length-1;i>=0;i--){
    const b = booms[i];
    b.userData.life -= dt;
    b.scale.setScalar(1 + (0.45-b.userData.life)*6);
    b.material.opacity = Math.max(0, b.userData.life/0.45);
    if(b.userData.life<=0){ scene.remove(b); removeObj(booms,b); }
  }

  renderer.render(scene, camera);
}
updateHUD();
animate();
</script>
</body>
</html>
```