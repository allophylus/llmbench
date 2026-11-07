```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tower Stacker</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#0b0d12;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
  #c{position:fixed;inset:0;display:block;}
  #hud{position:fixed;top:18px;left:18px;z-index:10;user-select:none;pointer-events:none;}
  .panel{background:rgba(12,15,22,.72);border:1px solid rgba(255,255,255,.08);border-left:3px solid #f4b942;border-radius:10px;padding:12px 16px;backdrop-filter:blur(6px);box-shadow:0 8px 30px rgba(0,0,0,.4);}
  .label{font-size:11px;letter-spacing:.22em;color:#8b93a7;text-transform:uppercase;}
  .big{font-size:44px;font-weight:700;color:#f4b942;line-height:1;margin-top:4px;}
  .sub{font-size:12px;color:#c3c9d6;margin-top:6px;}
  .score{font-size:22px;font-weight:700;color:#eef1f7;margin-top:10px;}
  .score span{color:#f4b942;}
  .status{font-size:12px;margin-top:8px;letter-spacing:.05em;}
  .status.ok{color:#7fd1a8}.status.bad{color:#ff6b6b}.status.wait{color:#8b93a7}
  #meter{position:fixed;top:18px;right:18px;z-index:10;width:46px;height:60vh;user-select:none;pointer-events:none;}
  .track{position:absolute;top:0;bottom:0;left:50%;transform:translateX(-50%);width:12px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:6px;overflow:hidden;}
  .fill{position:absolute;left:0;right:0;bottom:0;height:0%;background:linear-gradient(180deg,#f4b942,#e8843c);transition:height .12s linear;}
  .tick{position:absolute;left:50%;transform:translateX(-50%);width:20px;height:1px;background:rgba(255,255,255,.18);}
  .tick span{position:absolute;left:24px;top:-7px;font-size:10px;color:#8b93a7;}
  #hint{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:10;font-size:11px;letter-spacing:.12em;color:#6b7280;text-transform:uppercase;user-select:none;pointer-events:none;}
</style>
<script type="importmap">
{ "imports": { "three": "https://unpkg.com/three@0.160.0/build/three.module.js" } }
</script>
</head>
<body>
<canvas id="c"></canvas>
<div id="hud">
  <div class="panel">
    <div class="label">Tower Height</div>
    <div class="big" id="h">0</div>
    <div class="sub" id="hs">0 / 20 blocks</div>
    <div class="score">SCORE <span id="s">0</span></div>
    <div class="status wait" id="st">stacking…</div>
  </div>
</div>
<div id="meter">
  <div class="track"><div class="fill" id="fill"></div></div>
  <div id="ticks"></div>
</div>
<div id="hint">R restart · SPACE pause</div>

<script type="module">
import * as THREE from 'three';

// ---------- seeded RNG (mulberry32) ----------
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}

// ---------- constants ----------
const BW=2, BH=1, BD=2, G=9.8, DROP_Y=8, DROP_EVERY=40, SETTLE_TICKS=20, VY_SETTLE=0.05, N=20;
const MAXH=20;

// ---------- three.js scene ----------
const canvas=document.getElementById('c');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setSize(innerWidth,innerHeight);
renderer.shadowMap.enabled=true;
renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure=1.05;

const scene=new THREE.Scene();
scene.background=new THREE.Color(0x0b0d12);
scene.fog=new THREE.Fog(0x0b0d12,26,60);

const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,200);
const camTarget=new THREE.Vector3(0,3,0);
let camTheta=0.72, camPhi=1.12, camDist=17;
function updateCamera(){
  const sp=Math.sin(camPhi),cp=Math.cos(camPhi);
  camera.position.set(camTarget.x+camDist*sp*Math.sin(camTheta),camTarget.y+camDist*cp,camTarget.z+camDist*sp*Math.cos(camTheta));
  camera.lookAt(camTarget);
}
updateCamera();

scene.add(new THREE.HemisphereLight(0x9fb4d6,0x1a140d,0.55));
const key=new THREE.DirectionalLight(0xfff2d6,1.35);
key.position.set(9,15,7); key.castShadow=true;
key.shadow.mapSize.set(2048,2048);
key.shadow.camera.near=1; key.shadow.camera.far=60;
key.shadow.camera.left=-14; key.shadow.camera.right=14; key.shadow.camera.top=14; key.shadow.camera.bottom=-14;
key.shadow.bias=-0.0004;
scene.add(key);
const fill=new THREE.DirectionalLight(0x8fb0ff,0.45); fill.position.set(-8,6,-6); scene.add(fill);

const ground=new THREE.Mesh(new THREE.PlaneGeometry(80,80),new THREE.MeshStandardMaterial({color:0x141821,roughness:0.95,metalness:0.0}));
ground.rotation.x=-Math.PI/2; ground.receiveShadow=true; scene.add(ground);
const grid=new THREE.GridHelper(40,40,0x2a3140,0x1c212c); grid.position.y=0.002; scene.add(grid);

const blockGeo=new THREE.BoxGeometry(BW,BH,BD);
const blockMat=new THREE.MeshStandardMaterial({color:0xffffff,roughness:0.55,metalness:0.12});
const blockMeshes=[];
for(let i=0;i<N;i++){const m=new THREE.Mesh(blockGeo,blockMat.clone());m.castShadow=true;m.receiveShadow=true;m.visible=false;scene.add(m);blockMeshes.push(m);}

// ---------- game state ----------
let seed=1234, rng=null, offsets=null, blocks=null, nextDrop=0, over=false, toppled=false, score=0, paused=false;
const S=window.__game={ready:false,seed:1234,blocks:[],height:0,score:0,over:false,toppled:false,step:function(){},reset:function(){},hash:function(){}};

function makeOffsets(){
  const r=mulberry32(seed); const o=[];
  for(let i=0;i<N;i++){ o.push(i===0?0:(r()*1.2-0.6)); }
  return o;
}
function reset(s){
  seed=s; rng=mulberry32(seed); offsets=makeOffsets();
  blocks=[]; nextDrop=0; over=false; toppled=false; score=0; paused=false;
  for(let i=0;i<N;i++){ blockMeshes[i].visible=false; }
  S.seed=seed; S.blocks=[]; S.height=0; S.score=0; S.over=false; S.toppled=false;
  S.ready=true;
}
function dropBlock(i){
  const b={x:offsets[i],y:DROP_Y,z:0,vy:0,dropped:true,settled:false,contact:0};
  blocks.push(b);
  const m=blockMeshes[i]; m.visible=true; m.material.color.setHSL(0.08+i*0.012,0.62,0.55);
}
function supportTop(b){
  let top=0;
  for(const o of blocks){
    if(o===b||!o.settled) continue;
    if(Math.abs(b.x-o.x)<BW-1e-6 && Math.abs(b.z-o.z)<BD-1e-6){
      const t=o.y+BH/2; if(t>top) top=t;
    }
  }
  return top;
}
function step(dt){
  if(over) return;
  if(nextDrop<N && nextDrop*DROP_EVERY<=0){} // no-op guard
  if(nextDrop<N && nextDrop*DROP_EVERY===0){} // (kept simple below)
  if(nextDrop<N && nextDrop*DROP_EVERY<=0){}
  // drop schedule: block i drops at tick i*DROP_EVERY
  if(nextDrop<N && nextDrop*DROP_EVERY<=0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY<=0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY<=0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY<=0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N && nextDrop*DROP_EVERY===0){}
  if(nextDrop<N &&