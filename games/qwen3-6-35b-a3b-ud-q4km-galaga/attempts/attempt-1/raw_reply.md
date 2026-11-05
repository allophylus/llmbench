```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Neon Void Shooter</title>
    <style>
        body { margin: 0; overflow: hidden; background: #050510; font-family: 'Courier New', Courier, monospace; touch-action: none; user-select: none; }
        canvas { display: block; }
        #ui { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; display: flex; flex-direction: column; justify-content: space-between; }
        .hud { padding: 20px; color: #fff; text-shadow: 0 0 10px #0ff; font-size: 20px; font-weight: bold; display: flex; justify-content: space-between; }
        #overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: auto; transition: opacity 0.3s; }
        h1 { color: #f0f; font-size: 40px; margin: 0 0 20px 0; text-shadow: 0 0 20px #f0f; text-align: center; }
        p { color: #fff; font-size: 18px; margin-bottom: 30px; text-align: center; max-width: 80%; }
        button { background: transparent; border: 2px solid #0ff; color: #0ff; padding: 15px 40px; font-size: 24px; font-family: inherit; cursor: pointer; text-transform: uppercase; box-shadow: 0 0 15px #0ff; transition: all 0.2s; }
        button:hover { background: #0ff; color: #000; }
        #controls { position: absolute; bottom: 20px; width: 100%; height: 150px; display: flex; justify-content: space-between; padding: 0 20px; box-sizing: border-box; pointer-events: none; }
        .touch-btn { width: 80px; height: 80px; border-radius: 50%; background: rgba(255,255,255,0.1); border: 2px solid rgba(255,255,255,0.3); pointer-events: auto; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,0.5); font-size: 24px; }
        .touch-btn:active { background: rgba(0,255,255,0.3); border-color: #0ff; }
        .d-pad { display: flex; gap: 10px; }
        .action-pad { display: flex; align-items: flex-end; }
        #fire-btn { width: 90px; height: 90px; background: rgba(255,0,0,0.1); border-color: rgba(255,0,0,0.3); }
        #fire-btn:active { background: rgba(255,0,0,0.3); border-color: #f00; }
        .hidden { opacity: 0; pointer-events: none !important; }
    </style>
    <script type="importmap">
        { "imports": { "three": "https://unpkg.com/three@0.160.0/build/three.module.js" } }
    </script>
</head>
<body>
    <div id="ui">
        <div class="hud">
            <span id="scoreEl">SCORE: 0</span>
            <span id="livesEl">LIVES: 3</span>
        </div>
        <div id="controls">
            <div class="d-pad">
                <div class="touch-btn" id="left-btn">←</div>
                <div class="touch-btn" id="right-btn">→</div>
            </div>
            <div class="action-pad">
                <div class="touch-btn" id="fire-btn">FIRE</div>
            </div>
        </div>
    </div>
    <div id="overlay">
        <h1>NEON VOID</h1>
        <p>Arrows/WASD to Move. Space to Shoot.<br>Don't let them pass.</p>
        <button id="start-btn">START MISSION</button>
    </div>

    <script type="module">
        import * as THREE from 'three';

        // --- CONFIGURATION ---
        const COLORS = {
            bg: 0x050510,
            player: 0x00ffff,
            enemy: 0xff00ff,
            bullet: 0xffff00,
            particle: 0xffaa00,
            grid: 0x220033
        };

        // --- STATE ---
        const state = {
            ready: false,
            score: 0,
            lives: 3,
            over: false,
            player: { x: 0, y: 0 },
            enemies: [],
            bullets: [],
            lastShot: 0,
            spawnTimer: 0,
            difficulty: 1
        };

        // --- THREE.JS SETUP ---
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(COLORS.bg);
        scene.fog = new THREE.FogExp2(COLORS.bg, 0.02);

        const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
        camera.position.set(0, 10, 15);
        camera.lookAt(0, 0, 0);

        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        document.body.appendChild(renderer.domElement);

        // Lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        scene.add(ambientLight);
        const dirLight = new THREE.DirectionalLight(0xffffff, 1);
        dirLight.position.set(5, 10, 7);
        scene.add(dirLight);

        // --- ASSETS (Procedural) ---
        // Player Ship
        const playerGeo = new THREE.ConeGeometry(0.5, 1.5, 4);
        playerGeo.rotateX(Math.PI / 2);
        playerGeo.rotateY(Math.PI / 4);
        const playerMat = new THREE.MeshStandardMaterial({ color: COLORS.player, emissive: COLORS.player, emissiveIntensity: 0.5, roughness: 0.2 });
        const playerMesh = new THREE.Mesh(playerGeo, playerMat);
        scene.add(playerMesh);

        // Enemy Geometry
        const enemyGeo = new THREE.OctahedronGeometry(0.6);
        const enemyMat = new THREE.MeshStandardMaterial({ color: COLORS.enemy, emissive: COLORS.enemy, emissiveIntensity: 0.8, wireframe: true });

        // Bullet Geometry
        const bulletGeo = new THREE.BoxGeometry(0.2, 0.2, 1);
        const bulletMat = new THREE.MeshBasicMaterial({ color: COLORS.bullet });

        // Background Grid
        const gridHelper = new THREE.GridHelper(40, 40, COLORS.grid, 0x110022);
        gridHelper.position.y = -5;
        scene.add(gridHelper);

        // Stars
        const starGeo = new THREE.BufferGeometry();
        const starCount = 500;
        const starPos = new Float32Array(starCount * 3);
        for(let i=0; i<starCount*3; i++) starPos[i] = (Math.random() - 0.5) * 100;
        starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
        const starMat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.1 });
        const stars = new THREE.Points(starGeo, starMat);
        scene.add(stars);

        // --- GAME LOGIC ---
        const keys = { ArrowUp: false, ArrowDown: false, ArrowLeft: false, ArrowRight: false, w: false, a: false, s: false, d: false, " ": false };
        
        // Input Listeners
        window.addEventListener('keydown', e => keys[e.key] = true);
        window.addEventListener('keyup', e => keys[e.key] = false);

        // Touch Controls
        const setupTouch = (id, key) => {
            const el = document.getElementById(id);
            el.addEventListener('pointerdown', (e) => { e.preventDefault(); keys[key] = true; });
            el.addEventListener('pointerup', (e) => { e.preventDefault(); keys[key] = false; });
            el.addEventListener('pointerleave', (e) => { keys[key] = false; });
        };
        setupTouch('left-btn', 'ArrowLeft');
        setupTouch('right-btn', 'ArrowRight');
        setupTouch('fire-btn', ' ');

        // Particle System
        const particles = [];
        function createExplosion(pos, color) {
            const count = 15;
            const geo = new THREE.BoxGeometry(0.2, 0.2, 0.2);
            const mat = new THREE.MeshBasicMaterial({ color: color });
            for(let i=0; i<count; i++) {
                const mesh = new THREE.Mesh(geo, mat);
                mesh.position.copy(pos);
                mesh.position.x += (Math.random()-0.5);
                mesh.position.y += (Math.random()-0.5);
                const vel = new THREE.Vector3((Math.random()-0.5)*0.5, (Math.random()-0.5)*0.5, (Math.random()-0.5)*0.5);
                scene.add(mesh);
                particles.push({ mesh, vel, life: 1.0 });
            }
        }

        // Screen Shake
        let shakeIntensity = 0;
        function triggerShake(amount) { shakeIntensity = amount; }

        // Reset Game
        window.__game = {
            ready: true,
            get score() { return state.score; },
            get lives() { return state.lives; },
            get over() { return state.over; },
            get player() { return { x: playerMesh.position.x, y: playerMesh.position.y }; },
            get enemies() { return state.enemies.map(e => ({ x: e.mesh.position.x, y: e.mesh.position.y })); },
            get bullets() { return state.bullets.map(b => ({ x: b.mesh.position.x, y: b.mesh.position.y })); },
            reset: () => {
                state.score = 0;
                state.lives = 3;
                state.over = false;
                state.difficulty = 1;
                state.enemies.forEach(e => scene.remove(e.mesh));
                state.enemies = [];
                state.bullets.forEach(b => scene.remove(b.mesh));
                state.bullets = [];
                playerMesh.position.set(0, -4, 0);
                document.getElementById('overlay').classList.add('hidden');
                updateHUD();
            }
        };

        function updateHUD() {
            document.getElementById('scoreEl').innerText = `SCORE: ${state.score}`;
            document.getElementById('livesEl').innerText = `LIVES: ${state.lives}`;
        }

        function gameOver() {
            state.over = true;
            document.querySelector('#overlay h1').innerText = "GAME OVER";
            document.querySelector('#overlay p').innerText = `Final Score: ${state.score}`;
            document.getElementById('start-btn').innerText = "TRY AGAIN";
            document.getElementById('overlay').classList.remove('hidden');
        }

        document.getElementById('start-btn').addEventListener('click', () => window.__game.reset());

        // --- MAIN LOOP ---
        const clock = new THREE.Clock();
        const BOUNDS_X = 8;
        const BOUNDS_Y = 6;

        function animate() {
            requestAnimationFrame(animate);
            const dt = Math.min(clock.getDelta(), 0.1); // Cap dt

            if (!state.over && state.ready) {
                // Player Movement (Eased)
                const speed = 15;
                let moveX = 0;
                if (keys.ArrowLeft || keys.a) moveX = -1;
                if (keys.ArrowRight || keys.d) moveX = 1;
                
                playerMesh.position.x += moveX * speed * dt;
                playerMesh.position.x = Math.max(-BOUNDS_X, Math.min(BOUNDS_X, playerMesh.position.x));
                
                // Tilt effect
                playerMesh.rotation.z = -moveX * 0.5;

                // Shooting
                if (keys[" "] && state.lastShot < 0) {
                    const bMesh = new THREE.Mesh(bulletGeo, bulletMat);
                    bMesh.position.copy(playerMesh.position);
                    bMesh.position.y += 1;
                    scene.add(bMesh);
                    state.bullets.push({ mesh: bMesh, active: true });
                    state.lastShot = 0.2; // Fire rate
                }
                state.lastShot -= dt;

                // Spawning Enemies
                state.spawnTimer -= dt;
                if (state.spawnTimer <= 0) {
                    const eMesh = new THREE.Mesh(enemyGeo, enemyMat);
                    eMesh.position.set((Math.random()-0.5)*16, 10, 0);
                    scene.add(eMesh);
                    state.enemies.push({ mesh: eMesh, speed: 2 + state.difficulty });
                    state.spawnTimer = Math.max(0.2, 1.5 - state.difficulty * 0.1);
                }

                // Update Bullets
                for (let i = state.bullets.length - 1; i >= 0; i--) {
                    const b = state.bullets[i];
                    b.mesh.position.y += 20 * dt;
                    if (b.mesh.position.y > 15) {
                        scene.remove(b.mesh);
                        state.bullets.splice(i, 1);
                    }
                }

                // Update Enemies & Collision
                for (let i = state.enemies.length - 1; i >= 0; i--) {
                    const e = state.enemies[i];
                    e.mesh.position.y -= e.speed * dt;
                    e.mesh.rotation.x += dt;
                    e.mesh.rotation.y += dt;

                    // Check Player Collision
                    if (e.mesh.position.distanceTo(playerMesh.position) < 1.5) {
                        createExplosion(e.mesh.position, COLORS.enemy);
                        scene.remove(e.mesh);
                        state.enemies.splice(i, 1);
                        state.lives--;
                        triggerShake(0.5);
                        updateHUD();
                        if (state.lives <= 0) gameOver();
                        continue;
                    }

                    // Check Bullet Collision
                    let hit = false;
                    for (let j = state.bullets.length - 1; j >= 0; j--) {
                        if (e.mesh.position.distanceTo(state.bullets[j].mesh.position) < 1.2) {
                            createExplosion(e.mesh.position, COLORS.particle);
                            scene.remove(state.bullets[j].mesh);
                            state.bullets.splice(j, 1);
                            hit = true;
                            break;
                        }
                    }

                    if (hit) {
                        scene.remove(e.mesh);
                        state.enemies.splice(i, 1);
                        state.score += 100;
                        state.difficulty += 0.05;
                        updateHUD();
                        continue;
                    }

                    // Check Floor Collision
                    if (e.mesh.position.y < -8) {
                        scene.remove(e.mesh);
                        state.enemies.splice(i, 1);
                        state.lives--;
                        triggerShake(0.5);
                        updateHUD();
                        if (state.lives <= 0) gameOver();
                    }
                }
            }

            // Particles Update
            for (let i = particles.length - 1; i >= 0; i--) {
                const p = particles[i];
                p.life -= dt * 2;
                p.mesh.position.add(p.vel);
                p.mesh.scale.setScalar(p.life);
                if (p.life <= 0) {
                    scene.remove(p.mesh);
                    particles.splice(i, 1);
                }
            }

            // Camera Shake
            if (shakeIntensity > 0) {
                camera.position.x = (Math.random() - 0.5) * shakeIntensity;
                camera.position.y = 10 + (Math.random() - 0.5) * shakeIntensity;
                shakeIntensity -= dt * 2;
                if (shakeIntensity < 0) shakeIntensity = 0;
            } else {
                camera.position.set(0, 10, 15);
            }

            // Background Animation
            stars.rotation.z += 0.05 * dt;
            gridHelper.position.z = (gridHelper.position.z + 10 * dt) % 2;

            renderer.render(scene, camera);
        }

        // Handle Resize
        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });

        animate();
    </script>
</body>
</html>
```