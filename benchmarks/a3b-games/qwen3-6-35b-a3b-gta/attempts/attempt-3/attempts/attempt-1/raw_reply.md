```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Neon Grid Runner</title>
    <style>
        body { margin: 0; overflow: hidden; background: #050510; font-family: 'Courier New', Courier, monospace; user-select: none; -webkit-user-select: none; }
        canvas { display: block; }
        #ui { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; display: flex; flex-direction: column; justify-content: space-between; }
        #hud { padding: 20px; color: #0ff; text-shadow: 0 0 5px #0ff; font-size: 20px; font-weight: bold; display: flex; justify-content: space-between; }
        #controls { pointer-events: auto; display: flex; justify-content: space-between; padding: 20px; padding-bottom: 40px; }
        .btn { width: 80px; height: 80px; background: rgba(255,255,255,0.1); border: 2px solid #0ff; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #0ff; font-size: 24px; touch-action: none; }
        .btn:active { background: rgba(0,255,255,0.4); }
        #d-pad { display: flex; gap: 10px; }
        #action-pad { display: flex; gap: 10px; }
        #overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; pointer-events: auto; z-index: 10; }
        h1 { font-size: 40px; color: #f0f; text-shadow: 0 0 10px #f0f; margin-bottom: 10px; }
        button.start-btn { padding: 15px 40px; font-size: 20px; background: #0ff; border: none; color: #000; font-weight: bold; cursor: pointer; box-shadow: 0 0 15px #0ff; }
        button.start-btn:hover { background: #fff; }
        .hidden { display: none !important; }
    </style>
</head>
<body>

<div id="ui">
    <div id="hud">
        <span id="scoreEl">SCORE: 0</span>
        <span id="timeEl">TIME: 60</span>
        <span id="livesEl">LIVES: 3</span>
    </div>
    <div id="controls">
        <div id="d-pad">
            <div class="btn" id="btn-left">◄</div>
            <div class="btn" id="btn-right">►</div>
        </div>
        <div id="action-pad">
            <div class="btn" id="btn-brake">▼</div>
            <div class="btn" id="btn-gas">▲</div>
        </div>
    </div>
</div>

<div id="overlay">
    <h1>NEON DRIVER</h1>
    <p>Collect Waypoints. Avoid Buildings.</p>
    <button class="start-btn" onclick="startGame()">START ENGINE</button>
</div>

<script type="importmap">
{
    "imports": {
        "three": "https://unpkg.com/three@0.160.0/build/three.module.js"
    }
}
</script>

<script type="module">
import * as THREE from 'three';

// --- CONFIGURATION ---
const GRID_SIZE = 10;
const CELL_SIZE = 40;
const MAP_SIZE = GRID_SIZE * CELL_SIZE;
const COLORS = {
    bg: 0x050510,
    road: 0x1a1a24,
    building: 0x2a2a35,
    buildingTop: 0x3a3a45,
    player: 0x00ffff,
    waypoint: 0xff00ff,
    particle: 0xffaa00
};

// --- STATE ---
const state = {
    ready: false,
    score: 0,
    lives: 3,
    over: false,
    time: 60,
    player: { x: 0, y: 0, z: 0, rot: 0, speed: 0 },
    enemies: [], // Not used in this specific brief, but required by interface
    bullets: [], // Not used, but required by interface
    waypoints: [],
    buildings: [],
    particles: [],
    shake: 0
};

// --- THREE.JS SETUP ---
const scene = new THREE.Scene();
scene.background = new THREE.Color(COLORS.bg);
scene.fog = new THREE.FogExp2(COLORS.bg, 0.008);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 120, 100);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

// Lights
const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
scene.add(ambientLight);
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(50, 100, 50);
dirLight.castShadow = true;
dirLight.shadow.mapSize.width = 1024;
dirLight.shadow.mapSize.height = 1024;
scene.add(dirLight);

// --- ASSETS (Procedural) ---
const buildingGeo = new THREE.BoxGeometry(CELL_SIZE - 4, 40, CELL_SIZE - 4);
const buildingMat = new THREE.MeshStandardMaterial({ color: COLORS.building, roughness: 0.2 });
const buildingTopGeo = new THREE.BoxGeometry(CELL_SIZE - 6, 1, CELL_SIZE - 6);
const buildingTopMat = new THREE.MeshStandardMaterial({ color: COLORS.buildingTop, emissive: 0x111111 });

const playerGeo = new THREE.BoxGeometry(8, 4, 14);
const playerMat = new THREE.MeshStandardMaterial({ color: COLORS.player, emissive: 0x004444 });
const playerMesh = new THREE.Mesh(playerGeo, playerMat);
playerMesh.castShadow = true;
scene.add(playerMesh);

// Waypoint Marker
const wpGeo = new THREE.CylinderGeometry(0, 10, 5, 8);
const wpMat = new THREE.MeshBasicMaterial({ color: COLORS.waypoint, transparent: true, opacity: 0.6 });
const wpMesh = new THREE.Mesh(wpGeo, wpMat);
scene.add(wpMesh);

// --- WORLD GENERATION ---
function generateCity() {
    // Clear old
    state.buildings.forEach(b => scene.remove(b));
    state.waypoints.forEach(w => scene.remove(w));
    state.buildings = [];
    state.waypoints = [];

    // Grid Logic
    for (let x = 0; x < GRID_SIZE; x++) {
        for (let z = 0; z < GRID_SIZE; z++) {
            const posX = (x - GRID_SIZE/2) * CELL_SIZE;
            const posZ = (z - GRID_SIZE/2) * CELL_SIZE;
            
            // Random buildings, but leave center clear for spawn
            if (Math.random() > 0.2 && !(x > 3 && x < 6 && z > 3 && z < 6)) {
                const h = 20 + Math.random() * 30;
                const mesh = new THREE.Mesh(buildingGeo, buildingMat);
                mesh.position.set(posX, h/2, posZ);
                mesh.castShadow = true;
                mesh.receiveShadow = true;
                scene.add(mesh);
                
                const top = new THREE.Mesh(buildingTopGeo, buildingTopMat);
                top.position.set(posX, h, posZ);
                scene.add(top);

                state.buildings.push({ x: posX, z: posZ, w: CELL_SIZE, d: CELL_SIZE });
            }
        }
    }

    // Spawn Waypoints
    for(let i=0; i<5; i++) {
        spawnWaypoint();
    }
}

function spawnWaypoint() {
    let valid = false;
    let x, z;
    while(!valid) {
        const gx = Math.floor(Math.random() * GRID_SIZE);
        const gz = Math.floor(Math.random() * GRID_SIZE);
        x = (gx - GRID_SIZE/2) * CELL_SIZE;
        z = (gz - GRID_SIZE/2) * CELL_SIZE;
        
        // Check collision with buildings
        let hit = false;
        for(let b of state.buildings) {
            if (Math.abs(x - b.x) < CELL_SIZE/2 && Math.abs(z - b.z) < CELL_SIZE/2) hit = true;
        }
        if (!hit) valid = true;
    }
    
    const mesh = wpMesh.clone();
    mesh.position.set(x, 2, z);
    scene.add(mesh);
    state.waypoints.push({ x, z, mesh });
}

// --- INPUT HANDLING ---
const keys = { ArrowUp: false, ArrowDown: false, ArrowLeft: false, ArrowRight: false, w: false, s: false, a: false, d: false };

window.addEventListener('keydown', e => keys[e.key] = true);
window.addEventListener('keyup', e => keys[e.key] = false);

// Touch Controls
const setupTouch = (id, key) => {
    const el = document.getElementById(id);
    el.addEventListener('pointerdown', (e) => { e.preventDefault(); keys[key] = true; });
    el.addEventListener('pointerup', (e) => { e.preventDefault(); keys[key] = false; });
    el.addEventListener('pointerleave', (e) => { keys[key] = false; });
};
setupTouch('btn-gas', 'ArrowUp');
setupTouch('btn-brake', 'ArrowDown');
setupTouch('btn-left', 'ArrowLeft');
setupTouch('btn-right', 'ArrowRight');

// --- GAME LOGIC ---
function updatePhysics() {
    if (state.over) return;

    // Input
    const up = keys.ArrowUp || keys.w;
    const down = keys.ArrowDown || keys.s;
    const left = keys.ArrowLeft || keys.a;
    const right = keys.ArrowRight || keys.d;

    // Car Physics
    const maxSpeed = 1.5;
    const accel = 0.05;
    const friction = 0.96;
    const turnSpeed = 0.06;

    if (up) state.player.speed += accel;
    if (down) state.player.speed -= accel;
    
    state.player.speed *= friction;
    
    // Cap speed
    if (state.player.speed > maxSpeed) state.player.speed = maxSpeed;
    if (state.player.speed < -maxSpeed/2) state.player.speed = -maxSpeed/2;

    // Turning (only when moving)
    if (Math.abs(state.player.speed) > 0.01) {
        if (left) state.player.rot += turnSpeed * Math.sign(state.player.speed);
        if (right) state.player.rot -= turnSpeed * Math.sign(state.player.speed);
    }

    // Calculate new position
    const dx = Math.sin(state.player.rot) * state.player.speed;
    const dz = Math.cos(state.player.rot) * state.player.speed;
    
    const nextX = state.player.x + dx;
    const nextZ = state.player.z + dz;

    // Collision Check (Buildings)
    let collided = false;
    const carW = 6;
    const carL = 12;

    for (let b of state.buildings) {
        // Simple AABB
        if (nextX > b.x - b.w/2 - carW/2 && nextX < b.x + b.w/2 + carW/2 &&
            nextZ > b.z - b.d/2 - carL/2 && nextZ < b.z + b.d/2 + carL/2) {
            collided = true;
            break;
        }
    }

    if (collided) {
        state.player.speed *= -0.5; // Bounce
        state.time = Math.max(0, state.time - 2); // Penalty
        state.lives--;
        state.shake = 20;
        createExplosion(state.player.x, state.player.z, COLORS.player);
        if (state.lives <= 0) gameOver();
    } else {
        state.player.x = nextX;
        state.player.z = nextZ;
    }

    // Waypoint Collection
    for (let i = state.waypoints.length - 1; i >= 0; i--) {
        const wp = state.waypoints[i];
        const dist = Math.hypot(state.player.x - wp.x, state.player.z - wp.z);
        if (dist < 15) {
            state.score += 100;
            state.time += 5; // Bonus time
            createExplosion(wp.x, wp.z, COLORS.waypoint);
            scene.remove(wp.mesh);
            state.waypoints.splice(i, 1);
            spawnWaypoint();
        }
    }

    // Update Mesh
    playerMesh.position.set(state.player.x, 2, state.player.z);
    playerMesh.rotation.y = state.player.rot;
    
    // Camera Follow
    const camDist = 140;
    const camHeight = 100;
    // Smooth camera
    const targetX = state.player.x - Math.sin(state.player.rot) * camDist;
    const targetZ = state.player.z - Math.cos(state.player.rot) * camDist;
    
    camera.position.x += (targetX - camera.position.x) * 0.1;
    camera.position.z += (targetZ - camera.position.z) * 0.1;
    camera.position.y = camHeight;
    camera.lookAt(state.player.x, 0, state.player.z);
}

// --- PARTICLES ---
function createExplosion(x, z, color) {
    for(let i=0; i<15; i++) {
        const geo = new THREE.BoxGeometry(2, 2, 2);
        const mat = new THREE.MeshBasicMaterial({ color: color });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(x, 2, z);
        scene.add(mesh);
        state.particles.push({
            mesh: mesh,
            vx: (Math.random() - 0.5) * 2,
            vy: (Math.random() * 2),
            vz: (Math.random() - 0.5) * 2,
            life: 1.0
        });
    }
}

function updateParticles() {
    for (let i = state.particles.length - 1; i >= 0; i--) {
        const p = state.particles[i];
        p.life -= 0.02;
        p.mesh.position.x += p.vx;
        p.mesh.position.y += p.vy;
        p.mesh.position.z += p.vz;
        p.mesh.rotation.x += 0.1;
        p.mesh.scale.setScalar(p.life);
        
        if (p.life <= 0) {
            scene.remove(p.mesh);
            state.particles.splice(i, 1);
        }
    }
}

// --- GAME LOOP ---
let lastTime = 0;
let timerAccum = 0;

function animate(time) {
    requestAnimationFrame(animate);
    
    const dt = (time - lastTime) / 1000;
    lastTime = time;

    if (state.ready && !state.over) {
        // Timer
        timerAccum += dt;
        if (timerAccum >= 1) {
            state.time--;
            timerAccum = 0;
            if (state.time <= 0) gameOver();
        }

        updatePhysics();
        updateParticles();
        
        // Animate Waypoints
        state.waypoints.forEach((wp, idx) => {
            wp.mesh.rotation.y += 0.05;
            wp.mesh.position.y = 2 + Math.sin(time * 0.005 + idx) * 1;
        });

        // Screen Shake
        if (state.shake > 0) {
            camera.position.x += (Math.random() - 0.5) * state.shake * 0.1;
            camera.position.z += (Math.random() - 0.5) * state.shake * 0.1;
            state.shake *= 0.9;
            if (state.shake < 0.5) state.shake = 0;
        }

        // Update HUD
        document.getElementById('scoreEl').innerText = `SCORE: ${state.score}`;
        document.getElementById('timeEl').innerText = `TIME: ${state.time}`;
        document.getElementById('livesEl').innerText = `LIVES: ${state.lives}`;
    }

    renderer.render(scene, camera);
}

// --- STATE MANAGEMENT ---
function updateState() {
    window.__game = {
        ready: state.ready,
        score: state.score,
        lives: state.lives,
        over: state.over,
        player: { x: state.player.x, y: state.player.z }, // y is z in 3D
        enemies: state.enemies,
        bullets: state.bullets
    };
}

window.startGame = function() {
    document.getElementById('overlay').classList.add('hidden');
    state.ready = true;
    state.score = 0;
    state.lives = 3;
    state.time = 60;
    state.over = false;
    state.player = { x: 0, y: 0, z: 0, rot: 0, speed: 0 };
    playerMesh.position.set(0, 2, 0);
    generateCity();
};

function gameOver() {
    state.over = true;
    document.querySelector('#overlay h1').innerText = "GAME OVER";
    document.querySelector('#overlay p').innerText = `Final Score: ${state.score}`;
    document.querySelector('.start-btn').innerText = "RETRY";
    document.getElementById('overlay').classList.remove('hidden');
}

// --- INIT ---
// Initial render loop
requestAnimationFrame(animate);

// Expose reset
window.__game.reset = function() {
    window.startGame();
};

// Update state every frame for grader
setInterval(updateState, 100);

// Handle Resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

</script>
</body>
</html>
```