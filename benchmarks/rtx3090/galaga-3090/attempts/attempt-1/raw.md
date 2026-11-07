```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>NEBULA STRIKE</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#05060f;font-family:'Segoe UI',system-ui,sans-serif;touch-action:none;-webkit-user-select:none;user-select:none}
  #c{position:fixed;inset:0;display:block}
  #hud{position:fixed;top:0;left:0;right:0;padding:14px 18px;display:flex;justify-content:space-between;align-items:flex-start;pointer-events:none;z-index:5}
  .panel{background:rgba(8,12,26,.55);border:1px solid rgba(120,220,255,.25);border-radius:10px;padding:8px 14px;backdrop-filter:blur(4px)}
  .lbl{font-size:10px;letter-spacing:3px;color:#7fdcff;opacity:.8}
  .val{font-size:26px;font-weight:800;color:#eaf6ff;line-height:1;text-shadow:0 0 12px rgba(120,220,255,.6)}
  #lives{display:flex;gap:6px;margin-top:6px}
  .ship{width:16px;height:16px;background:linear-gradient(180deg,#7fdcff,#2f6bff);clip-path:polygon(50% 0,100% 100%,50% 78%,0 100%);box-shadow:0 0 8px rgba(120,220,255,.7)}
  .ship.off{background:#2a3350;box-shadow:none;opacity:.5}
  #wave{font-size:18px;font-weight:700;color:#ff9e6b;text-shadow:0 0 10px rgba(255,120,80,.5)}
  #msg{position:fixed;top:38%;left:0;right:0;text-align:center;pointer-events:none;z-index:6}
  #msg h1{margin:0;font-size:44px;font-weight:900;letter-spacing:6px;color:#eaf6ff;text-shadow:0 0 24px rgba(120,220,255,.8)}
  #msg p{margin:8px 0 0;font-size:14px;letter-spacing:2px;color:#9fd8ff}
  #flash{position:fixed;inset:0;background:radial-gradient(circle,rgba(255,80,60,.5),rgba(255,40,40,.15));opacity:0;pointer-events:none;z-index:4}
  #touch{position:fixed;bottom:0;left:0;right:0;display:flex;justify-content:space-between;align-items:flex-end;padding:16px;z-index:7;pointer-events:none}
  .pad{display:flex;gap:12px;pointer-events:auto}
  .btn{width:64px;height:64px;border-radius:50%;background:rgba(20,30,60,.5);border:2px solid rgba(120,220,255,.4);color:#cfeeff;font-size:26px;display:flex;align-items:center;justify-content:center;touch-action:none;pointer-events:auto}
  .btn:active{background:rgba(60,120,220,.5)}
  #fire{width:84px;height:84px;background:rgba(60,20,30,.5);border-color:rgba(255,120,80,.5);color:#ffb08a;font-size:14px;font-weight:800;letter-spacing:1px}
  @media (min-width:700px){#touch{display:none}}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="hud">
  <div class="panel"><div class="lbl">SCORE</div><div class="val" id="score">0</div></div>
  <div class="panel" style="text-align:center"><div class="lbl">WAVE</div><div id="wave">1</div></div>
  <div class="panel" style="text-align:right"><div class="lbl">SHIPS</div><div id="lives"></div></div>
</div>
<div id="msg"><h1>NEBULA STRIKE</h1><p>MOVE &nbsp;·&nbsp; SHOOT &nbsp;·&nbsp; SURVIVE</p></div>
<div id="flash"></div>
<div id="touch">
  <div class="pad"><div class="btn" id="l">◀</div><div class="btn" id="r">▶</div></div>
  <div class="pad"><div class="btn" id="fire">FIRE</div></div>
</div>
<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js"}}</script>
<script type="module">
import * as THREE from 'three';

// ---------- palette ----------
const C={bgTop:0x1a1030,bgBot:0x05060f,neb1:0x3a1a5c,neb2:0x0a2a4a,neb3:0x5c1a3a,
  player:0x7fdcff,playerCore:0xeaf6ff,bullet:0x9fe8ff,
  enemy:0xff5a3c,enemyCore:0xffb08a,enemyGlow:0xff3a2a,
  hit:0xffffff,star:0xcfe8ff};

// ---------- world ----------
const W=16,H=30;
let scene,camera,renderer,player,playerGlow,playerCore,playerThruster;
let stars=[],nebulae=[],bullets=[],enemies=[],particles=[],pools={};
let score=0,lives=3,wave=1,over=false,ready=false,spawnTimer=0,spawnInterval=1.2,
  shake=0,flash=0,fireCd=0,invuln=0,playerX=0,playerY=-12.5,playerVX=0,
  keys={},touchL=false,touchR=false,touchF=false,elapsed=0;

// ---------- helpers ----------
const rand=(a,b)=>a+Math.random()*(b-a);
const ease=(a,b,t)=>a+(b-a)*(1-Math.pow(1-t,3));
function glowTex(){
  const s=64,cv=document.createElement('canvas');cv.width=cv.height=s;
  const g=cv.getContext('2d'),gr=g.createRadialGradient(s/2,s/2,0,s/2,s/2,s/2);
  gr.addColorStop(0,'rgba(255,255,255,1)');gr.addColorStop(.35,'rgba(255,255,255,.5)');gr.addColorStop(1,'rgba(255,255,255,0)');
  g.fillStyle=gr;g.fillRect(0,0,s,s);
  const t=new THREE.CanvasTexture(cv);t.needsUpdate=true;return t;
}
const GLOW=glowTex();
function pool(n,make){const a=[];for(let i=0;i<n;i++){const o=make();o.active=false;a.push(o);}return a;}
function get(pool){for(const o of pool)if(!o.active){o.active=true;return o;}return null;}

// ---------- setup ----------
function init(){
  scene=new THREE.Scene();
  camera=new THREE.PerspectiveCamera(50,innerWidth/innerHeight,0.1,200);
  camera.position.set(0,0,26);
  renderer=new THREE.WebGLRenderer({canvas:document.getElementById('c'),antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.setSize(innerWidth,innerHeight);
  renderer.setClearColor(C.bgBot,1);

  // gradient background
  const bg=new THREE.Mesh(new THREE.PlaneGeometry(120,120),
    new THREE.ShaderMaterial({
      uniforms:{top:{value:new THREE.Color(C.bgTop)},bot:{value:new THREE.Color(C.bgBot)}},
      vertexShader:`varying vec2 v;void main(){v=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
      fragmentShader:`uniform vec3 top,bot;varying vec2 v;void main(){gl_FragColor=vec4(mix(bot,top,v.y),1.);}`,
      depthWrite:false}));
  bg.position.z=-40;scene.add(bg);

  // nebula blobs
  for(let i=0;i<6;i++){
    const col=[C.neb1,C.neb2,C.neb3][i%3];
    const m=new THREE.Mesh(new THREE.PlaneGeometry(1,1),
      new THREE.MeshBasicMaterial({map:GLOW,color:col,transparent:true,opacity:rand(.12,.22),
        blending:THREE.AdditiveBlending,depthWrite:false}));
    m.position.set(rand(-14,14),rand(-14,14),-30);
    const s=rand(20,40);m.scale.set(s,s,1);
    m.userData={vx:rand(-.15,.15),vy:rand(-.1,.1)};
    scene.add(m);nebulae.push(m);
  }
  // stars
  for(let i=0;i<140;i++){
    const m=new THREE.Mesh(new THREE.PlaneGeometry(1,1),
      new THREE.MeshBasicMaterial({map:GLOW,color:C.star,transparent:true,opacity:rand(.3,.9),
        blending:THREE.AdditiveBlending,depthWrite:false}));
    m.position.set(rand(-W/2,W/2),rand(-H/2,H/2),-20);
    const s=rand(.05,.2);m.scale.set(s,s,1);
    m.userData={vy:rand(.5,2.5)};
    scene.add(m);stars.push(m);
  }

  // player ship
  player=new THREE.Group();
  const body=new THREE.Mesh(new THREE.ConeGeometry(.55,1.6,4),
    new THREE.MeshStandardMaterial({color:C.player,emissive:C.player,emissiveIntensity:.6,metalness:.3,roughness:.4}));
  body.rotation.x=Math.PI/2;body.rotation.z=Math.PI/4;player.add(body);
  playerCore=new THREE.Mesh(new THREE.SphereGeometry(.22,12,12),
    new THREE.MeshBasicMaterial({color:C.playerCore}));player.add(playerCore);
  playerGlow=new THREE.Mesh(new THREE.PlaneGeometry(3,3),
    new THREE.MeshBasicMaterial({map:GLOW,color:C.player,transparent:true,opacity:.5,blending:THREE.AdditiveBlending,depthWrite:false}));
  playerGlow.position.z=-.2;player.add(playerGlow);
  playerThruster=new THREE.Mesh(new THREE.ConeGeometry(.3,.9,8),
    new THREE.MeshBasicMaterial({color:C.enemyCore,transparent:true,opacity:.8,blending:THREE.AdditiveBlending,depthWrite:false}));
  playerThruster.rotation.x=-Math.PI/2;playerThruster.position.y=-.9;player.add(playerThruster);
  player.position.set(0,playerY,0);scene.add(player);

  // pools
  pools.bullet=pool(40,()=>{
    const g=new THREE.Group();
    const m=new THREE.Mesh(new THREE.CylinderGeometry(.12,.12,.9,8),
      new THREE.MeshBasicMaterial({color:C.bullet}));m.rotation.x=Math.PI/2;g.add(m);
    const gl=new THREE.Mesh(new THREE.PlaneGeometry(1.4,1.4),
      new THREE.MeshBasicMaterial({map:GLOW,color:C.bullet,transparent:true,opacity:.7,blending:THREE.AdditiveBlending,depthWrite:false}));
    g.add(gl);scene.add(g);return g;});
  pools.enemy=pool(30,()=>{
    const g=new THREE.Group();
    const m=new THREE.Mesh(new THREE.ConeGeometry(.6,1.2,4),
      new THREE.MeshStandardMaterial({color:C.enemy,emissive:C.enemyGlow,emissiveIntensity:.7,metalness:.2,roughness:.5}));
    m.rotation.x=-Math.PI/2;m.rotation.z=Math.PI/4;g.add(m);
    const core=new THREE.Mesh(new THREE.SphereGeometry(.2,10,10),
      new THREE.MeshBasicMaterial({color:C.enemyCore}));g.add(core);
    const gl=new THREE.Mesh(new THREE.PlaneGeometry(2.6,2.6),
      new THREE.MeshBasicMaterial({map:GLOW,color:C.enemyGlow,transparent:true,opacity:.5,blending:THREE.AdditiveBlending,depthWrite:false}));
    gl.position.z=-.2;g.add(gl);scene.add(g);return g;});
  pools.particle=pool(220,()=>{
    const m=new THREE.Mesh(new THREE.PlaneGeometry(1,1),
      new THREE.MeshBasicMaterial({map:GLOW,color:C.hit,transparent:true,opacity:1,blending:THREE.AdditiveBlending,depthWrite:false}));
    scene.add(m);return m;});

  addEventListener('resize',onResize);
  ready=true;
  window.__game={ready:true,score:0,lives:3,over:false,player:{x:0,y:playerY},enemies:[],bullets:[],reset:reset};
  updateHUD();
}

function onResize(){camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);}

// ---------- actions ----------
function fire(){
  if(fireCd>0||over)return;
  const b=get(pools.bullet);if(!b)return;
  b.position.set(playerX,playerY+1,0);b.userData.vy=28;b.userData.life=1;
  fireCd=0.16;
}
function burst(x,y,color,n,spd){
  for(let i=0;i<n;i++){
    const p=get(pools.particle);if(!p)return;
    const a=Math.random()*Math.PI*2,s=rand(spd*.3,spd);
    p.position.set(x,y,0);
    p.userData={vx:Math.cos(a)*s,vy:Math.sin(a)*s,life:rand(.4,.8),max:.8,
      size:rand(.3,.7),color:new THREE.Color(color)};
    p.material.color.copy(p.userData.color);
  }
}
function spawnEnemy(){
  const e=get(pools.enemy);if(!e)return;
  e.position.set(rand(-W/2+1,W/2-1),H/2+1,0);
  e.userData={vy:rand(3,4)+wave*.35,life:1,flash:0,sway:rand(0,6.28),swayAmp:rand(.3,.8)};
  e.scale.set(1,1,1);
}
function loseLife(){
  if(invuln>0||over)return;
  lives--;invuln=1.6;shake=1.2;flash=1;
  burst(playerX,playerY,C.player,26,9);
  if(lives<=0){lives=0;over=true;}
  updateHUD();
}
function reset(){
  score=0;lives=3;wave=1;over=false;spawnTimer=0;spawnInterval=1.2;
  shake=0;flash=0;fireCd=0;invuln=0;playerX=0;playerVX=0;
  for(const p of pools.bullet)p.active=false;
  for(const p of pools.enemy){p.active=false;p.visible=false;}
  for(const p of pools.particle)p.active=false;
  player.position.set(0,playerY,0);
  document.getElementById('msg').style.display='none';
  updateHUD();
}

// ---------- HUD ----------
function updateHUD(){
  document.getElementById('score').textContent=score;
  document.getElementById('wave').textContent=wave;
  const L=document.getElementById('lives');L.innerHTML='';
  for(let i=0;i<3;i++){const d=document.createElement('div');d.className='ship'+(i<lives?'':' off');L.appendChild(d);}
  const msg=document.getElementById('msg');
  if(over){msg.style.display='block';msg.querySelector('h1').textContent='GAME OVER';
    msg.querySelector('p').textContent='SCORE '+score+'  ·  TAP FIRE TO RESTART';}
  else if(!ready){msg.style.display='block';}
  else msg.style.display='none';
}

// ---------- update ----------
function update(dt){
  elapsed+=dt;
  // background
  for(const s of stars){s.position.y+=s.userData.vy*dt;if(s.position.y>H/2)s.position.y=-H/2;}
  for(const n of nebulae){n.position.x+=n.userData.vx*dt;n.position.y+=n.userData.vy*dt;
    if(n.position.x>16)n.position.x=-16;if(n.position.x<-16)n.position.x=16;
    if(n.position.y>16)n.position.y=-16;if(n.position.y<-16)n.position.y=16;}

  if(!over){
    // player
    let dir=0;
    if(keys.ArrowLeft||keys.a)dir-=1;
    if(keys.ArrowRight||keys.d)dir+=1;
    if(touchL)dir-=1;if(touchR)dir+=1;
    playerVX=ease(playerVX,dir*14,1-Math.pow(.001,dt));
    playerX+=playerVX*dt;
    playerX=Math.max(-W/2+1,Math.min(W/2-1,playerX));
    player.position.x=playerX;
    player.rotation.z=-playerVX*.03;
    playerThruster.scale.y=1+Math.sin(elapsed*30)*.3+Math.abs(playerVX)*.05;
    playerGlow.material.opacity=.4+Math.sin(elapsed*6)*.1;
    if(invuln>0){invuln-=dt;player.visible=Math.floor(elapsed*12)%2===0;}else player.visible=true;
    if((keys.Space||touchF)&&!over)fire();
    fireCd-=dt;

    // spawn
    spawnTimer-=dt;
    if(spawnTimer<=0){spawnEnemy();spawnTimer=spawnInterval;}

    // bullets
    for(const b of pools.bullet){if(!b.active)continue;
      b.position.y+=b.userData.vy*dt;
      if(b.position.y>H/2+1){b.active=false;continue;}
      for(const e of pools.enemy){if(!e.active)continue;
        const dx=b.position.x-e.position.x,dy=b.position.y-e.position.y;
        if(dx*dx+dy*dy<1.1){b.active=false;e.userData.flash=1;
          burst(e.position.x,e.position.y,C.enemy,14,7);
          score+=10;updateHUD();
          if(Math.random()<.35)wave++;
          e.active=false;e.visible=false;break;}
      }
    }
    // enemies
    for(const e of pools.enemy){if(!e.active)continue;
      e.position.y-=e.userData.vy*dt;
      e.userData.sway+=dt*2;
      e.position.x+=Math.sin(e.userData.sway)*e.userData.swayAmp*dt;
      e.rotation.z=Math.sin(e.userData.sway)*.2;
      if(e.userData.flash>0)e.userData.flash-=dt*4;
      const sc=1+e.userData.flash*.4;e.scale.set(sc,sc,sc);
      if(e.position.y<-H/2+1){e.active=false;e.visible=false;loseLife();}
    }
  }
  // particles (always)
  for(const p of pools.particle){if(!p.active)continue;
    const u=p.userData;u.life-=dt;
    if(u.life<=0){p.active=false;continue;}
    p.position.x+=u.vx*dt;p.position.y+=u.vy*dt;
    u.vx*=.94;u.vy*=.94;
    const t=u.life/u.max;p.material.opacity=t;
    const s=u.size*t;p.scale.set(s,s,1);
  }
  // shake & flash
  shake=Math.max(0,shake-dt*2.5);
  flash=Math.max(0,flash-dt*2);
  const sx=(Math.random()-.5)*shake*.6,sy=(Math.random()-.5)*shake*.6;
  camera.position.x=sx;camera.position.y=sy;
  document.getElementById('flash').style.opacity=flash*.6;

  // machine state
  const g=window.__game;
  g.ready=ready;g.score=score;g.lives=lives;g.over=over;
  g.player={x:playerX,y:playerY};
  g.bullets=[];for(const b of pools.bullet)if(b.active)g.bullets.push({x:b.position.x,y:b.position.y});
  g.enemies=[];for(const e of pools.enemy)if(e.active)g.enemies.push({x:e.position.x,y:e.position.y});
}

// ---------- loop ----------
let last=performance.now();
function loop(now){
  const dt=Math.min(.05,(now-last)/1000);last=now;
  if(ready)update(dt);
  renderer.render(scene,camera);
  requestAnimationFrame(loop);
}

// ---------- input ----------
addEventListener('keydown',e=>{
  const k=e.key.toLowerCase();
  if(['arrowleft','arrowright','arrowup','arrowdown',' '].includes(k))e.preventDefault();
  keys[k]=true;
  if(k===' '&&!over)fire();
  if(k==='r')reset();
});
addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false;});
function bind(id,down,up){
  const el=document.getElementById(id);
  el.addEventListener('pointerdown',e=>{e.preventDefault();down();});
  el.addEventListener('pointerup',e=>{e.preventDefault();up();});
  el.addEventListener('pointerleave',up);
  el.addEventListener('pointercancel',up);
}
bind('l',()=>touchL=true,()=>touchL=false);
bind('r',()=>touchR=true,()=>touchR=false);
bind('fire',()=>{touchF=true;if(over)reset();},()=>touchF=false);
document.getElementById('fire').addEventListener('pointerdown',e=>{e.preventDefault();if(over)reset();});

init();
requestAnimationFrame(loop);
</script>
</body>
</html>
```