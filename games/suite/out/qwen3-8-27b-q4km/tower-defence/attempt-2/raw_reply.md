```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Tower Defence — llmbench</title>
<style>
  :root{
    --bg:#0a1418; --panel:rgba(10,22,26,.82); --line:rgba(120,200,190,.16);
    --ink:#e9f6f2; --dim:#7fa39c; --gold:#f4c15a; --life:#ff6f61; --cyan:#5fe3d0;
    --good:#7ee081; --bad:#ff5d5d;
    --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,Consolas,monospace;
    --disp:"Bahnschrift","DIN Alternate","Oswald","Arial Narrow",system-ui,sans-serif;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;overflow:hidden;background:var(--bg);color:var(--ink);
    font-family:var(--mono);-webkit-user-select:none;user-select:none;touch-action:none}
  #c{position:fixed;inset:0;display:block}
  .vignette{position:fixed;inset:0;pointer-events:none;z-index:2;
    background:radial-gradient(120% 90% at 50% 42%,transparent 45%,rgba(0,0,0,.55) 100%)}
  .scan{position:fixed;inset:0;pointer-events:none;z-index:2;opacity:.35;mix-blend-mode:overlay;
    background:repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 3px)}
  .hud{position:fixed;z-index:5;pointer-events:none}
  .top{top:14px;left:14px;right:14px;display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
  .brand{display:flex;gap:12px;align-items:center}
  .mark{width:44px;height:44px;border:1px solid var(--line);border-radius:9px;display:grid;place-items:center;
    background:linear-gradient(160deg,rgba(95,227,208,.14),rgba(244,193,90,.06));box-shadow:0 0 22px rgba(95,227,208,.18)}
  .mark svg{width:26px;height:26px}
  .brand h1{font-family:var(--disp);font-weight:700;letter-spacing:.14em;font-size:22px;margin:0;line-height:1}
  .brand small{display:block;color:var(--dim);font-size:10px;letter-spacing:.34em;margin-top:5px}
  .stats{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 12px;min-width:74px;
    backdrop-filter:blur(6px);position:relative;overflow:hidden}
  .stat::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--cyan);opacity:.7}
  .stat.g::before{background:var(--gold)} .stat.l::before{background:var(--life)}
  .stat.t::before{background:var(--good)} .stat.s::before{background:#c9a7ff}
  .stat .k{font-size:9px;letter-spacing:.28em;color:var(--dim)}
  .stat .v{font-family:var(--disp);font-weight:700;font-size:26px;line-height:1.05;margin-top:3px}
  .stat.g .v{color:var(--gold)} .stat.l .v{color:var(--life)} .stat.t .v{color:var(--good)} .stat.s .v{color:#d9c2ff}
  .stat .v.bump{animation:bump .35s ease}
  @keyframes bump{0%{transform:scale(1)}40%{transform:scale(1.28)}100%{transform:scale(1)}}
  .wavebar{position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:5;pointer-events:none;
    text-align:center;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 22px;
    backdrop-filter:blur(6px);min-width:230px}
  .wavebar .wl{font-family:var(--disp);font-weight:700;letter-spacing:.2em;font-size:15px}
  .wavebar .wl b{color:var(--cyan)}
  .wavebar .sub{font-size:10px;letter-spacing:.24em;color:var(--dim);margin-top:4px}
  .wavebar .track{height:5px;border-radius:3px;background:rgba(255,255,255,.08);margin-top:9px;overflow:hidden}
  .wavebar .fill{height:100%;width:0;background:linear-gradient(90deg,var(--cyan),var(--gold));transition:width .12s linear}
  .legend{position:fixed;left:14px;bottom:14px;z-index:5;pointer-events:none;background:var(--panel);
    border:1px solid var(--line);border-radius:10px;padding:10px 14px;backdrop-filter:blur(6px);font-size:10px;
    letter-spacing:.14em;color:var(--dim);line-height:1.9}
  .legend b{color:var(--ink);font-weight:600}
  .legend .dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:7px;vertical-align:middle}
  .controls{position:fixed;right:14px;bottom:14px;z-index:6;display:flex;gap:10px}
  .btn{pointer-events:auto;cursor:pointer;font-family:var(--disp);font-weight:700;letter-spacing:.16em;font-size:13px;
    color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:11px 18px;
    backdrop-filter:blur(6px);transition:transform .12s,box-shadow .2s,border-color .2s}
  .btn:hover{transform:translateY(-2px);border-color:var(--cyan);box-shadow:0 8px 24px rgba(95,227,208,.22)}
  .btn:active{transform:translateY(0)}
  .btn.warn{border-color:rgba(244,193,90,.4)} .btn.warn:hover{border-color:var(--gold);box-shadow:0 8px 24px rgba(244,193,90,.22)}
  .overlay{position:fixed;inset:0;z-index:8;display:none;place-items:center;background:rgba(6,14,17,.72);backdrop-filter:blur(4px)}
  .overlay.show{display:grid}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:34px 44px;text-align:center;
    box-shadow:0 30px 80px rgba(0,0,0,.5);animation:pop .4s cubic-bezier(.2,1.3,.4,1)}
  @keyframes pop{from{transform:scale(.85);opacity:0}to{transform:scale(1);opacity:1}}
  .card h2{font-family:var(--disp);font-weight:700;letter-spacing:.18em;font-size:34px;margin:0 0 6px}
  .card.win h2{color:var(--good)} .card.lose h2{color:var(--bad)}
  .card p{color:var(--dim);letter-spacing:.14em;font-size:12px;margin:0 0 20px}
  .card .big{font-family:var(--disp);font-weight:700;font-size:44px;color:var(--gold);margin-bottom:22px}
  .card .btn{pointer-events:auto}
  .paused{position:fixed;inset:0;z-index:7;display:none;place-items:center;pointer-events:none}
  .paused.show{display:grid}
  .paused span{font-family:var(--disp);font-weight:700;letter-spacing:.4em;font-size:30px;color:var(--cyan);
    text-shadow:0 0 30px rgba(95,227,208,.5)}
  @media (max-width:640px){.brand h1{font-size:17px}.stat{min-width:60px;padding:6px 9px}.stat .v{font-size:20px}
    .legend{display:none}.wavebar{min-width:180px;padding:8px 14px}}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="vignette"></div><div class="scan"></div>

<div class="hud top">
  <div class="brand">
    <div class="mark">
      <svg viewBox="0 0 24 24" fill="none"><path d="M12 2 21 7v10l-9 5-9-5V7z" stroke="#5fe3d0" stroke-width="1.4"/>
      <circle cx="12" cy="12" r="3.2" fill="#f4c15a"/></svg>
    </div>
    <div><h1>TOWER DEFENCE</h1><small>AUTO-PLACEMENT · 5 WAVES</small></div>
  </div>
  <div class="stats">
    <div class="stat g"><div class="k">GOLD</div><div class="v" id="sGold">200</div></div>
    <div class="stat l"><div class="k">LIVES</div><div class="v" id="sLives">20</div></div>
    <div class="stat"><div class="k">WAVE</div><div class="v" id="sWave">0/5</div></div>
    <div class="stat t"><div class="k">TOWERS</div><div class="v" id="sTowers">0</div></div>
    <div class="stat s"><div class="k">SCORE</div><div class="v" id="sScore">0</div></div>
  </div>
</div>

<div class="wavebar">
  <div class="wl">WAVE <b id="wNum">—</b></div>
  <div class="sub" id="wSub">STANDBY</div>
  <div class="track"><div class="fill" id="wFill"></div></div>
</div>

<div class="legend">
  <div><span class="dot" style="background:#5fe3d0"></span><b>TOWER</b> · auto-builds every 10 ticks</div>
  <div><span class="dot" style="background:#f4c15a"></span><b>UPGRADED</b> · range 3.5 · dmg 18</div>
  <div><span class="dot" style="background:#ff6f61"></span><b>UNIT</b> · walks the fixed path</div>
</div>

<div class="controls">
  <button class="btn" id="bPause">PAUSE</button>
  <button class="btn warn" id="bReset">RESTART</button>
</div>

<div class="paused" id="paused"><span>PAUSED</span></div>
<div class="overlay" id="overlay">
  <div class="card" id="card">
    <h2 id="oTitle">VICTORY</h2>
    <p id="oSub">ALL FIVE WAVES CLEARED</p>
    <div class="big" id="oScore">0</div>
    <button class="btn warn" id="oBtn">PLAY AGAIN</button>
  </div>
</div>

<script type="importmap">
{ "imports": { "three": "https://unpkg.com/three@0.160.0/build/three.module.js" } }
</script>
<script type="module">
import * as THREE from 'three';

/* ---------- deterministic RNG (mulberry32) ---------- */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);
  t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}

/* ---------- board + fixed path (16x10, 8 turns) ---------- */
const COLS=16, ROWS=10;
const PATH=[[0,4],[1,4],[2,4],[3,4],[3,3],[3,2],[3,1],[4,1],[5,1],[6,1],[6,2],[6,3],[6,4],[6,5],[6,6],[6,7],[7,7],[8,7],[9,7],[9,6],[9,5],[9,4],[9,3],[9,2],[9,1],[10,1],[11,1],[12,1],[12,2],[12,3],[12,4],[12,5],[12,6],[12,7],[12,8],[13,8],[14,8],[15,8]];
const pathSet=new Set(PATH.map(p=>p[0]+','+p[1]));
const START=PATH[0], END=PATH[PATH.length-1];
const WAVE_UNITS=[8,12,16,20,24];
const UNIT_SPEED=1.2, REWARD=5, BUILD_COST=50, UPG_COST=30;
const RANGE0=2.5, RANGE1=3.5, DMG0=12, DMG1=18, FIRE_EVERY=30, SPAWN_GAP=18;
const START_BREAK=90, BREAK=60;

/* ---------- three.js scene ---------- */
const canvas=document.getElementById('c');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
const scene=new THREE.Scene();
scene.background=new THREE.Color(0x0a1418);
scene.fog=new THREE.Fog(0x0a1418,20,46);
const camera=new THREE.PerspectiveCamera(42,1,0.1,200);
const camTarget=new THREE.Vector3(7.5,0,4.5);
const camDist=15, camAngle=0.95;
function placeCamera(){
  camera.position.set(camTarget.x+Math.sin(camAngle)*camDist, camDist*Math.cos(camAngle), camTarget.z+Math.cos(camAngle)*camDist);
  camera.lookAt(camTarget);
}
placeCamera();

scene.add(new THREE.HemisphereLight(0x9fd8d0,0x0a1418,0.85));
const dir=new THREE.DirectionalLight(0xfff2d8,0.9); dir.position.set(6,14,8); scene.add(dir);
const amb=new THREE.AmbientLight(0x22333a,0.6); scene.add(amb);

/* ground */
const ground=new THREE.Mesh(new THREE.PlaneGeometry(COLS+2,ROWS+2),
  new THREE.MeshStandardMaterial({color:0x0c1a1f,roughness:1,metalness:0}));
ground.rotation.x=-Math.PI/2; ground.position.set(7.5,-0.02,4.5); scene.add(ground);

/* instanced tiles */
const tileGeo=new THREE.BoxGeometry(0.94,0.16,0.94);
const tileMat=new THREE.MeshStandardMaterial({color:0xffffff,roughness:0.85,metalness:0.05});
const tiles=new THREE.InstancedMesh(tileGeo,tileMat,COLS*ROWS);
const _m=new THREE.Matrix4(), _c=new THREE.Color();
let ti=0;
for(let r=0;r<ROWS;r++)for(let x=0;x<COLS;x++){
  const onPath=pathSet.has(x+','+r);
  _m.makeTranslation(x+0.5,0.08,r+0.5); tiles.setMatrixAt(ti,_m);
  if(onPath) _c.set(0x2f6f68);
  else { const g=0.16+((x*7+r*13)%5)*0.012; _c.setRGB(g*0.55,g*0.95,g*0.9); }
  tiles.setColorAt(ti,_c); ti++;
}
tiles.instanceMatrix.needsUpdate=true; if(tiles.instanceColor) tiles.instanceColor.needsUpdate=true;
scene.add(tiles);

/* start / end markers */
function marker(x,y,col){const m=new THREE.Mesh(new THREE.CylinderGeometry(0.42,0.42,0.2,20),
  new THREE.MeshStandardMaterial({color:col,emissive:col,emissiveIntensity:0.5,roughness:0.4}));
  m.position.set(x+0.5,0.2,y+0.5); scene.add(m); return m;}
const startM=marker(START[0],START[1],0x5fe3d0), endM=marker(END[0],END[1],0xff6f61);

/* tower meshes */
const towerGeo=new THREE.CylinderGeometry(0.28,0.34,0.5,10);
const towerMat=new THREE.MeshStandardMaterial({color:0x5fe3d0,emissive:0x1c6b62,emissiveIntensity:0.5,roughness:0.4,metalness:0.3});
const towerTopGeo=new THREE.ConeGeometry(0.24,0.34,10);
const towerTopMat=new THREE.MeshStandardMaterial({color:0x9ff0e4,emissive:0x2f8f84,emissiveIntensity:0.6,roughness:0.3,metalness:0.4});
const upgMat=new THREE.MeshStandardMaterial({color:0xf4c15a,emissive:0x8a6a1e,emissiveIntensity:0.7,roughness:0.3,metalness:0.5});
const upgTopMat=new THREE.MeshStandardMaterial({color:0xffe08a,emissive:0xb08a2a,emissiveIntensity:0.8,roughness:0.25,metalness:0.5});
function makeTower(){const g=new THREE.Group();
  const b=new THREE.Mesh(towerGeo,towerMat); b.position.y=0.42; g.add(b);
  const t=new THREE.Mesh(towerTopGeo,towerTopMat); t.position.y=0.86; g.add(t);
  g.userData={body:b,top:t}; scene.add(g); return g;}
function setTowerLevel(g,lv){
  g.userData.body.material=lv>1?upgMat:towerMat;
  g.userData.top.material=lv>1?upgTopMat:towerTopMat;
  g.scale.setScalar(lv>1?1.18:1);
}

/* unit meshes */
const unitGeo=new THREE.IcosahedronGeometry(0.26,0);
const unitMat=new THREE.MeshStandardMaterial({color:0xff6f61,emissive:0x7a1f1a,emissiveIntensity:0.6,roughness:0.4,metalness:0.2});
function makeUnit(){const m=new THREE.Mesh(unitGeo,unitMat); m.position.y=0.34; scene.add(m); return m;}

/* tracers */
const tracerMat=new THREE.LineBasicMaterial({color:0xfff2b0,transparent:true,opacity:0.9});
const tracers=[];
function addTracer(a,b){const g=new THREE.BufferGeometry().setFromPoints([a,b]);
  const l=new THREE.Line(g,tracerMat); scene.add(l); tracers.push({l,life:1});}
function updateTracers(dt){for(let i=tracers.length-1;i>=0;i--){const t=tracers[i];t.life-=dt*6;
  if(t.life<=0){scene.remove(t.l);t.l.geometry.dispose();tracers.splice(i,1);}else t.l.material.opacity=t.life*0.9;}}

/* ---------- game state ---------- */
let seed=1234, rng=mulberry32(seed);
let gold,lives,wave,kills,towers,units,occupied,phase,phaseTimer,spawnLeft,spawnTimer,tick,paused,over,won;
let towerMeshes=[], unitMeshes=[];

function clearMeshes(){
  towerMeshes.forEach(m=>scene.remove(m)); towerMeshes=[];
  unitMeshes.forEach(m=>scene.remove(m)); unitMeshes=[];
  tracers.forEach(t=>{scene.remove(t.l);t.l.geometry.dispose();}); tracers.length=0;
}
function reset(seedArg){
  seed=seedArg|0; rng=mulberry32(seed);
  gold=200; lives=20; wave=0; kills=0; towers=[]; units=[]; occupied=new Set();
  phase='break'; phaseTimer=START_BREAK; spawnLeft=0; spawnTimer=0; tick=0; paused=false; over=false; won=false;
  clearMeshes();
  document.getElementById('overlay').classList.remove('show');
  document.getElementById('paused').classList.remove('show');
  document.getElementById('bPause').textContent='PAUSE';
  syncHUD();
}

function spawnUnit(){
  const hp=30+10*wave;
  const u={x:START[0],y:START[1],hp,maxhp:hp,wp:0,prog:0,dead:false,
    ox:(rng()-0.5)*0.12, oy:(rng()-0.5)*0.12, mesh:makeUnit()};
  units.push(u); unitMeshes.push(u.mesh);
}
function killUnit(u){
  u.dead=true; kills++; gold+=REWARD;
  scene.remove(u.mesh); const i=unitMeshes.indexOf(u.mesh); if(i>=0)unitMeshes.splice(i,1);
}
function placeTower(x,y){
  const g=makeTower(); g.position.set(x+0.5,0,y+0.5); setTowerLevel(g,1);
  towers.push({x,y,level:1,cost:BUILD_COST,cd:0,mesh:g}); towerMeshes.push(g);
  occupied.add(x+','+y);
}
function upgradeTower(t){
  t.level=2; t.cost+=UPG_COST; setTowerLevel(t.mesh,2);
}
function buildStep(){
  if(towers.length<6){
    if(gold>=BUILD_COST){
      for(let r=0;r<ROWS;r++)for(let x=0;x<COLS;x++){
        if(pathSet.has(x+','+r)) continue;
        if(x===START[0]&&r===START[1]) continue;
        if(x===END[0]&&r===END[1]) continue;
        if(occupied.has(x+','+r)) continue;
        gold-=BUILD_COST; placeTower(x,r); return;
      }
    }
  } else {
    if(gold>=UPG_COST){
      for(const t of towers){ if(t.level===1){ gold-=UPG_COST; upgradeTower(t); return; } }
    }
  }
}
function fire(t,u){
  const a=new THREE.Vector3(t.x+0.5,0.9,t.y+0.5);
  const b=new THREE.Vector3(u.x+0.5,0.34,u.y+0.5);
  addTracer(a,b);
  u.hp-=t.level>1?DMG1:DMG0;
  if(u.hp<=0) killUnit(u);
}
function step(dt){
  if(over||paused) return;
  tick++;
  if(tick%10===0) buildStep();

  if(phase==='break'){
    phaseTimer--;
    if(phaseTimer<=0){
      wave++; phase='active'; spawnLeft=WAVE_UNITS[wave-1]; spawnTimer=0;
    }
  } else {
    if(spawnLeft>0){
      spawnTimer--;
      if(spawnTimer<=0){ spawnUnit(); spawnLeft--; spawnTimer=SPAWN_GAP; }
    }
    for(const u of units){
      if(u.dead) continue;
      u.prog+=UNIT_SPEED*dt;
      while(u.wp<PATH.length-1 && u.prog>=1){ u.prog-=1; u.wp++; }
      if(u.wp>=PATH.length-1){ lives--; u.dead=true; scene.remove(u.mesh);
        const i=unitMeshes.indexOf(u.mesh); if(i>=0)unitMeshes.splice(i,1); }
    }
    for(const t of towers){
      t.cd--;
      if(t.cd<=0){
        const R=t.level>1?RANGE1:RANGE0, R2=R*R;
        let best=null,bp=-1;
        for(const u of units){ if(u.dead) continue;
          const dx=u.x-t.x, dy=u.y-t.y;
          if(dx*dx+dy*dy<=R2){ const p=u.wp+u.prog; if(p>bp){bp=p;best=u;} } }
        if(best){ fire(t,best); t.cd=FIRE_EVERY; }
      }
    }
    units=units.filter(u=>!u.dead);
    if(spawnLeft===0 && units.length===0){
      if(wave>=5){ over=true; won=true; }
      else { phase='break'; phaseTimer=BREAK; }
    }
  }
  if(lives<=0){ lives=0; over=true; won=false; }
  syncHUD();
}

/* ---------- HUD ---------- */
const el=id=>document.getElementById(id);
let lastScore=-1;
function bump(node){node.classList.remove('bump');void node.offsetWidth;node.classList.add('bump');}
function syncHUD(){
  el('sGold').textContent=gold;
  el('sLives').textContent=lives;
  el('sWave').textContent=wave+'/5';
  el('sTowers').textContent=towers.length;
  el('sScore').textContent=score();
  if(score()!==lastScore){ bump(el('sScore')); lastScore=score(); }
  const wn=el('wNum'), ws=el('wSub'), wf=el('wFill');
  if(over){
    wn.textContent=won?'5':'—';
    ws.textContent=won?'VICTORY':'DEFEAT';
    wf.style.width='100%';
    showOverlay();
  } else if(phase==='break'){
    wn.textContent=wave+1;
    ws.textContent='NEXT IN '+Math.ceil(phaseTimer/60)+'s';
    wf.style.width='0%';
  } else {
    const total=WAVE_UNITS[wave-1];
    const remaining=spawnLeft+units.length;
    wn.textContent=wave;
    ws.textContent='HOSTILES '+remaining;
    wf.style.width=(100*(1-remaining/total))+'%';
  }
}
function score(){ return 10*kills + 100*Math.min(wave,5) + 25*towers.length + (won?1000:0); }
function showOverlay(){
  const o=el('overlay'), card=el('card');
  card.className='card '+(won?'win':'lose');
  el('oTitle').textContent=won?'VICTORY':'DEFEAT';
  el('oSub').textContent=won?'ALL FIVE WAVES CLEARED':'THE BASE HAS FALLEN';
  el('oScore').textContent=score();
  o.classList.add('show');
}

/* ---------- contract ---------- */
window.__game={
  get ready(){return true;},
  get seed(){return seed;},
  get gold(){return gold;},
  get lives(){return lives;},
  get wave(){return wave;},
  get kills(){return kills;},
  get towers(){return towers.map(t=>({x:t.x,y:t.y,level:t.level,cost:t.cost}));},
  get units(){return units.map(u=>({x:u.x,y:u.y,hp:u.hp,wp:u.wp}));},
  get path(){return PATH.map(p=>[p[0],p[1]]);},
  get score(){return score();},
  get over(){return over;},
  get won(){return won;},
  step,
  reset,
  hash(){
    const u=units.map(x=>x.x+','+x.y+','+x.hp+','+x.wp).join(';');
    const t=towers.map(x=>x.x+','+x.y+','+x.level+','+x.cost).join(';');
    return [gold,lives,wave,score(),kills,over?1:0,won?1:0,u,t].join('|');
  }
};

/* ---------- input: pan / zoom / keys / buttons ---------- */
let panX=0,panY=0,zoom=1,dragging=false,px=0,py=0;
function applyCam(){
  const base=new THREE.Vector3(camTarget.x+Math.sin(camAngle)*camDist, camDist*Math.cos(camAngle), camTarget.z+Math.cos(camAngle)*camDist);
  camera.position.copy(base).add(new THREE.Vector3(panX,panY,0));
  camera.fov=42/zoom; camera.updateProjectionMatrix(); camera.lookAt(camTarget);
}
canvas.addEventListener('pointerdown',e=>{dragging=true;px=e.clientX;py=e.clientY;canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(!dragging)return;panX+=(e.clientX-px)*0.02;panY-=(e.clientY-py)*0.02;px=e.clientX;py=e.clientY;applyCam();});
canvas.addEventListener('pointerup',()=>dragging=false);
canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(0.6,Math.min(2.2,zoom*(e.deltaY<0?1.08:0.92)));applyCam();},{passive:false});

function togglePause(){ if(over) return; paused=!paused;
  el('paused').classList.toggle('show',paused); el('bPause').textContent=paused?'RESUME':'PAUSE'; }
function doReset(){ reset(seed); }
window.addEventListener('keydown',e=>{
  if(e.code==='Space'){ e.preventDefault(); togglePause(); }
  else if(e.key==='r'||e.key==='R'){ doReset(); }
});
el('bPause').addEventListener('pointerdown',e=>{e.preventDefault();togglePause();});
el('bReset').addEventListener('pointerdown',e=>{e.preventDefault();doReset();});
el('oBtn').addEventListener('pointerdown',e=>{e.preventDefault();doReset();});

/* ---------- resize ---------- */
function resize(){
  const w=innerWidth,h=innerHeight;
  renderer.setSize(w,h,false);
  camera.aspect=w/h; camera.updateProjectionMatrix();
}
addEventListener('resize',resize); resize();

/* ---------- render loop ---------- */
const clock=new THREE.Clock();
function animate(){
  requestAnimationFrame(animate);
  const dt=Math.min(clock.getDelta(),0.05);
  step(dt);
  const t=clock.elapsedTime;
  for(const u of units){
    const a=PATH[u.wp], b=PATH[Math.min(u.wp+1,PATH.length-1)];
    const f=Math.min(u.prog,1);
    u.mesh.position.set(a[0]+0.5+(b[0]-a[0])*f+u.ox, 0.34+Math.sin(t*6+u.wp)*0.05, a[1]+0.5+(b[1]-a[1])*f+u.oy);
    u.mesh.rotation.y+=dt*3;
  }
  for(const tw of towers){ tw.mesh.rotation.y+=dt*0.6; }
  startM.rotation.y+=dt; endM.rotation.y-=dt;
  updateTracers(dt);
  renderer.render(scene,camera);
}
reset(1234);
animate();
</script>
</body>
</html>
```