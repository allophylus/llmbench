```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ball Drop Sandbox</title>
<style>
  :root{
    --bg:#0b1418; --ink:#eaf3f1; --muted:#7f979b;
    --amber:#f2b45a; --teal:#37c6b0; --coral:#ef6f5c; --line:rgba(255,255,255,.09);
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;overflow:hidden;background:var(--bg);
    font-family:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;color:var(--ink)}
  #c{position:fixed;inset:0;display:block}
  .hud{position:fixed;inset:0;pointer-events:none;z-index:5}
  .panel{position:absolute;background:rgba(9,17,20,.55);border:1px solid var(--line);
    border-radius:12px;padding:14px 16px;backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px)}
  .tl{top:18px;left:18px;min-width:236px}
  .tr{top:18px;right:18px;text-align:right}
  .bl{bottom:18px;left:18px}
  .brand{font-size:11px;letter-spacing:.34em;color:var(--muted);text-transform:uppercase}
  .title{font-family:Georgia,"Times New Roman",serif;font-weight:700;font-size:30px;
    letter-spacing:-.01em;margin:5px 0 12px;line-height:1}
  .title em{font-style:normal;color:var(--amber)}
  .stat{display:flex;justify-content:space-between;align-items:baseline;gap:26px;
    padding:5px 0;border-top:1px solid var(--line)}
  .stat:first-of-type{border-top:none}
  .stat .k{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
  .stat .v{font-size:20px;font-variant-numeric:tabular-nums}
  .stat .v.amber{color:var(--amber)} .stat .v.teal{color:var(--teal)}
  .score{font-family:Georgia,serif;font-weight:700;font-size:46px;line-height:1;
    font-variant-numeric:tabular-nums;color:var(--ink)}
  .score .lbl{display:block;font-family:ui-monospace,monospace;font-size:10px;
    letter-spacing:.3em;color:var(--muted);text-transform:uppercase;margin-bottom:6px}
  .score .bonus{font-size:12px;color:var(--teal);letter-spacing:.1em;margin-top:8px;
    opacity:0;transition:opacity .4s}
  .score .bonus.on{opacity:1}
  .bar{height:6px;border-radius:4px;background:rgba(255,255,255,.08);margin-top:12px;overflow:hidden}
  .bar i{display:block;height:100%;width:0;border-radius:4px;
    background:linear-gradient(90deg,var(--teal),var(--amber));transition:width .25s ease}
  .keys{font-size:11px;color:var(--muted);letter-spacing:.06em;line-height:1.9}
  .keys b{color:var(--ink);background:rgba(255,255,255,.07);border:1px solid var(--line);
    border-radius:5px;padding:1px 7px;font-weight:600;margin-right:2px}
  .badge{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%) scale(.9);
    font-family:Georgia,serif;font-size:26px;letter-spacing:.02em;color:var(--amber);
    background:rgba(9,17,20,.7);border:1px solid var(--line);border-radius:14px;
    padding:16px 30px;opacity:0;transition:opacity .4s,transform .4s;pointer-events:none}
  .badge.on{opacity:1;transform:translate(-50%,-50%) scale(1)}
  .badge small{display:block;font-family:ui-monospace,monospace;font-size:11px;
    letter-spacing:.24em;color:var(--muted);text-transform:uppercase;margin-top:6px}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="hud">
  <div class="panel tl">
    <div class="brand">llmbench · cell</div>
    <div class="title">Ball <em>Drop</em> Sandbox</div>
    <div class="stat"><span class="k">Balls dropped</span><span class="v" id="dropped">0 / 25</span></div>
    <div class="stat"><span class="k">Still awake</span><span class="v teal" id="awake">0</span></div>
    <div class="stat"><span class="k">Settled</span><span class="v amber" id="settled">0</span></div>
    <div class="bar"><i id="bar"></i></div>
  </div>
  <div class="panel tr">
    <div class="score"><span class="lbl">Score</span><span id="score">0</span>
      <div class="bonus" id="bonus">+50 all settled</div></div>
  </div>
  <div class="panel bl keys">
    <div><b>Space</b> pause / resume</div>
    <div><b>R</b> restart (same seed)</div>
  </div>
  <div class="badge" id="badge">All 25 settled<small>run complete</small></div>
</div>

<script type="importmap">
{ "imports": { "three": "https://unpkg.com/three@0.160.0/build/three.module.js" } }
</script>
<script type="module">
import * as THREE from 'three';

/* ---------- constants ---------- */
const HALF_W = 4, HALF_D = 3, FLOOR_Y = 0, CEIL_Y = 9;
const R = 0.5, GRAV = -9.8, REST = 0.6, TANG = 0.985;
const SLEEP_SPEED = 0.05, SLEEP_TICKS = 30, TOTAL = 25, DROP_EVERY = 30;
const INNER_X = HALF_W - R, INNER_Z = HALF_D - R, FLOOR_R = FLOOR_Y + R;

/* ---------- deterministic RNG (mulberry32) ---------- */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);
  t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}

/* ---------- three.js scene ---------- */
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({canvas, antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1418);
scene.fog = new THREE.Fog(0x0b1418, 20, 46);

const camera = new THREE.PerspectiveCamera(42, innerWidth/innerHeight, 0.1, 100);
camera.position.set(0, 11.5, 15.5);
camera.lookAt(0, 2.2, 0);

/* lights */
scene.add(new THREE.HemisphereLight(0xbfe6e0, 0x0a1216, 0.55));
const key = new THREE.DirectionalLight(0xfff2df, 1.15);
key.position.set(7, 13, 9); key.castShadow = true;
key.shadow.mapSize.set(1024,1024);
key.shadow.camera.near = 1; key.shadow.camera.far = 40;
key.shadow.camera.left = -9; key.shadow.camera.right = 9;
key.shadow.camera.top = 9; key.shadow.camera.bottom = -9;
key.shadow.bias = -0.0004;
scene.add(key);
const fill = new THREE.DirectionalLight(0x8fd8cf, 0.35);
fill.position.set(-8, 6, -4); scene.add(fill);
const rim = new THREE.PointLight(0xf2b45a, 0.5, 30);
rim.position.set(0, 6, -6); scene.add(rim);

/* table */
const table = new THREE.Mesh(new THREE.BoxGeometry(16, 0.6, 12),
  new THREE.MeshStandardMaterial({color:0x12211f, roughness:0.9, metalness:0.05}));
table.position.y = -0.3; table.receiveShadow = true; scene.add(table);

/* glass box (open top) */
const glassMat = new THREE.MeshPhysicalMaterial({color:0x9fd8d0, metalness:0, roughness:0.06,
  transmission:0.92, thickness:0.5, ior:1.45, transparent:true, opacity:0.28,
  side:THREE.DoubleSide, depthWrite:false});
function wall(w,h,d,x,y,z){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),glassMat);
  m.position.set(x,y,z); m.renderOrder=2; scene.add(m);}
wall(2*HALF_W, 0.12, 2*HALF_D, 0, FLOOR_Y-0.06, 0);          // floor
wall(2*HALF_W, 3.2, 0.12, 0, FLOOR_Y+1.6, -HALF_D);          // back (higher)
wall(2*HALF_W, 2.4, 0.12, 0, FLOOR_Y+1.2,  HALF_D);          // front
wall(0.12, 2.4, 2*HALF_D, -HALF_W, FLOOR_Y+1.2, 0);          // left
wall(0.12, 2.4, 2*HALF_D,  HALF_W, FLOOR_Y+1.2, 0);          // right

/* floor grid (subtle) */
const grid = new THREE.GridHelper(2*HALF_W, 8, 0x2f5a55, 0x1c3a37);
grid.position.y = FLOOR_Y + 0.01; grid.material.opacity = 0.35; grid.material.transparent = true;
scene.add(grid);

/* ball meshes */
const ballGeo = new THREE.SphereGeometry(R, 28, 20);
const ballMat = new THREE.MeshStandardMaterial({color:0xf2b45a, roughness:0.32, metalness:0.15,
  emissive:0x2a1a05, emissiveIntensity:0.4});
const ballMeshes = [];
for(let i=0;i<TOTAL;i++){const m=new THREE.Mesh(ballGeo, ballMat); m.castShadow=true;
  m.visible=false; scene.add(m); ballMeshes.push(m);}

/* dust particles */
const P = 140, pPos = new Float32Array(P*3), pVel = new Float32Array(P*3);
for(let i=0;i<P;i++){pPos[i*3]=(Math.random()*2-1)*HALF_W; pPos[i*3+1]=Math.random()*CEIL_Y;
  pPos[i*3+2]=(Math.random()*2-1)*HALF_D; pVel[i*3]=(Math.random()*2-1)*0.05;
  pVel[i*3+1]=0.03+Math.random()*0.05; pVel[i*3+2]=(Math.random()*2-1)*0.05;}
const pGeo = new THREE.BufferGeometry();
pGeo.setAttribute('position', new THREE.BufferAttribute(pPos,3));
const pMat = new THREE.PointsMaterial({color:0x8fd8cf, size:0.05, transparent:true,
  opacity:0.5, depthWrite:false, blending:THREE.AdditiveBlending});
const points = new THREE.Points(pGeo, pMat); scene.add(points);
function updateDust(dt){for(let i=0;i<P;i++){pPos[i*3]+=pVel[i*3]*dt; pPos[i*3+1]+=pVel[i*3+1]*dt;
  pPos[i*3+2]+=pVel[i*3+2]*dt;
  if(pPos[i*3+1]>CEIL_Y){pPos[i*3+1]=0.1; pPos[i*3]=(Math.random()*2-1)*HALF_W; pPos[i*3+2]=(Math.random()*2-1)*HALF_D;}
  if(pPos[i*3]>HALF_W)pPos[i*3]=-HALF_W; if(pPos[i*3]<-HALF_W)pPos[i*3]=HALF_W;
  if(pPos[i*3+2]>HALF_D)pPos[i*3+2]=-HALF_D; if(pPos[i*3+2]<-HALF_D)pPos[i*3+2]=HALF_D;}
  pGeo.attributes.position.needsUpdate=true;}

/* ---------- simulation state ---------- */
let balls = [], rng = null, score = 0, over = false, paused = false, seed = 1234;
let stepCount = 0, dropped = 0, settledCount = 0;

function makeBall(x,y,z,vx,vy,vz){return {x,y,z,vx,vy,vz,r:R,settled:false,rest:0};}

function reset(s){
  seed = s|0; rng = mulberry32(seed);
  balls = []; score = 0; over = false; stepCount = 0; dropped = 0; settledCount = 0;
  for(let i=0;i<TOTAL;i++) ballMeshes[i].visible = false;
  updateHUD();
}

function spawn(){
  const x = (rng()*2-1)*(HALF_W-1.2);
  const z = (rng()*2-1)*(HALF_D-1.2);
  const y = CEIL_Y - 0.6 - rng()*0.8;
  const vx = (rng()*2-1)*0.6, vz = (rng()*2-1)*0.6, vy = -0.3 - rng()*0.4;
  balls.push(makeBall(x,y,z,vx,vy,vz));
  dropped++;
}

function step(dt){
  if(over) return;
  stepCount++;
  if(dropped < TOTAL && stepCount % DROP_EVERY === 0) spawn();

  const n = balls.length;
  for(let i=0;i<n;i++){
    const b = balls[i];
    if(b.settled) continue;
    b.vy += GRAV*dt;
    b.x += b.vx*dt; b.y += b.vy*dt; b.z += b.vz*dt;
  }

  /* ball-ball collisions */
  for(let i=0;i<n;i++){
    const a = balls[i];
    for(let j=i+1;j<n;j++){
      const c = balls[j];
      let dx=c.x-a.x, dy=c.y-a.y, dz=c.z-a.z;
      let d2 = dx*dx+dy*dy+dz*dz, min = a.r+c.r;
      if(d2 < min*min){
        let d = Math.sqrt(d2);
        if(d < 1e-6){ dx=1; dy=0; dz=0; d=1; }
        const nx=dx/d, ny=dy/d, nz=dz/d, overlap = min-d;
        const push = overlap*0.5;
        if(!a.settled){ a.x-=nx*push; a.y-=ny*push; a.z-=nz*push; }
        if(!c.settled){ c.x+=nx*push; c.y+=ny*push; c.z+=nz*push; }
        const rvx=c.vx-a.vx, rvy=c.vy-a.vy, rvz=c.vz-a.vz;
        const vn = rvx*nx+rvy*ny+rvz*nz;
        if(vn < 0){
          const jimp = -vn;
          if(!a.settled){ a.vx+=nx*jimp; a.vy+=ny*jimp; a.vz+=nz*jimp; }
          if(!c.settled){ c.vx-=nx*jimp; c.vy-=ny*jimp; c.vz-=nz*jimp; }
          const tx=rvx-vn*nx, ty=rvy-vn*ny, tz=rvz-vn*nz;
          if(!a.settled){ a.vx-=tx*(1-TANG)*0.5; a.vy-=ty*(1-TANG)*0.5; a.vz-=tz*(1-TANG)*0.5; }
          if(!c.settled){ c.vx+=tx*(1-TANG)*0.5; c.vy+=ty*(1-TANG)*0.5; c.vz+=tz*(1-TANG)*0.5; }
        }
      }
    }
  }

  /* walls + floor */
  for(let i=0;i<n;i++){
    const b = balls[i];
    if(b.settled) continue;
    if(b.x < -INNER_X){ b.x=-INNER_X; b.vx=-b.vx*REST; }
    else if(b.x > INNER_X){ b.x=INNER_X; b.vx=-b.vx*REST; }
    if(b.z < -INNER_Z){ b.z=-INNER_Z; b.vz=-b.vz*REST; }
    else if(b.z > INNER_Z){ b.z=INNER_Z; b.vz=-b.vz*REST; }
    if(b.y < FLOOR_R){ b.y=FLOOR_R; b.vy=-b.vy*REST; b.vx*=0.98; b.vz*=0.98; }
  }

  /* settle detection */
  settledCount = 0;
  for(let i=0;i<n;i++){
    const b = balls[i];
    if(b.settled){ settledCount++; continue; }
    const sp = Math.hypot(b.vx,b.vy,b.vz);
    const onFloor = b.y <= FLOOR_R + 0.02;
    let onSettled = false;
    if(!onFloor){
      for(let j=0;j<n;j++){ if(j===i) continue; const o=balls[j];
        if(o.settled){ const dx=o.x-b.x,dy=o.y-b.y,dz=o.z-b.z;
          if(dx*dx+dy*dy+dz*dz < (2*R)*(2*R)){ onSettled=true; break; } } }
    }
    if(sp < SLEEP_SPEED && (onFloor || onSettled)){
      b.rest++;
      if(b.rest >= SLEEP_TICKS){ b.settled=true; b.vx=0; b.vy=0; b.vz=0; }
    } else b.rest = 0;
  }

  score = settledCount*10 + (settledCount===TOTAL ? 50 : 0);
  if(settledCount === TOTAL) over = true;
  updateHUD();
}

/* ---------- HUD ---------- */
const el = id => document.getElementById(id);
const eDropped=el('dropped'), eAwake=el('awake'), eSettled=el('settled'),
      eScore=el('score'), eBar=el('bar'), eBonus=el('bonus'), eBadge=el('badge');
function updateHUD(){
  eDropped.textContent = dropped + ' / ' + TOTAL;
  eAwake.textContent = balls.length - settledCount;
  eSettled.textContent = settledCount;
  eScore.textContent = score;
  eBar.style.width = (settledCount/TOTAL*100) + '%';
  eBonus.classList.toggle('on', settledCount===TOTAL);
  eBadge.classList.toggle('on', over);
}

/* ---------- render sync ---------- */
function syncMeshes(){
  for(let i=0;i<TOTAL;i++){
    const m = ballMeshes[i];
    if(i < balls.length){ const b=balls[i]; m.visible=true; m.position.set(b.x,b.y,b.z); }
    else m.visible=false;
  }
}

/* ---------- contract ---------- */
window.__game = {
  ready:false, seed:1234, balls:[], score:0, over:false,
  step,
  reset,
  hash(){
    const r = v => (Math.round(v*1e4)/1e4).toFixed(4);
    let s = '';
    for(const b of balls) s += r(b.x)+','+r(b.y)+','+r(b.z)+','+r(b.vx)+','+r(b.vy)+','+r(b.vz)+';';
    return s + '#' + score;
  }
};

/* ---------- input ---------- */
window.addEventListener('keydown', e=>{
  if(e.code === 'Space'){ e.preventDefault(); paused = !paused; }
  else if(e.code === 'KeyR'){ reset(seed); }
});
window.addEventListener('resize', ()=>{
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

/* ---------- loop ---------- */
const clock = new THREE.Clock();
function animate(){
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  if(!paused) step(dt);
  syncMeshes();
  updateDust(dt);
  renderer.render(scene, camera);
}

reset(1234);
window.__game.ready = true;
animate();
</script>
</body>
</html>
```