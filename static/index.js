import * as THREE from 'three';
import { GLTFLoader } from 'three-gltf';
import { OrbitControls } from 'three-ctrl';
import GUI from 'https://cdn.jsdelivr.net/npm/lil-gui@0.18/+esm';

// Avatar Widget Sizing
const AVATAR_W = document.querySelector('.avatar-widget')?.offsetWidth || 310;
const AVATAR_H = document.querySelector('.avatar-widget')?.offsetHeight || 390;

// Scene
const scene = new THREE.Scene();

// Camera
const camera = new THREE.PerspectiveCamera(
  36,
  AVATAR_W / AVATAR_H,
  0.1,
  1000
);
camera.position.set(0, 1.6, 2.1);
camera.lookAt(0, 1.45, 0);

// Renderer
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(AVATAR_W, AVATAR_H);
renderer.setClearAlpha(0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
document.getElementById('avatar-container').appendChild(renderer.domElement);

// Controls
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.enableZoom = false;
controls.enablePan = false;
controls.enableRotate = false;

// Lighting
scene.add(new THREE.AmbientLight(0xffffff, 0.30));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.50);
dirLight.position.set(2.5, 10, 8);
scene.add(dirLight);

// Avatar
let avatar = null;
let mouthShapeKey = null;

const gltfLoader = new GLTFLoader();
gltfLoader.load(
  '/static/avatar.glb',
  (gltf) => {
    avatar = gltf.scene;
    avatar.traverse((obj) => {
      if (obj.isMesh && obj.morphTargetDictionary) {
        mouthShapeKey = Object.keys(obj.morphTargetDictionary)
          .find(k => /mouth|jaw|open|aa|A/i.test(k));
      }
    });

    avatar.position.set(0, -1.1, 0);
    avatar.scale.set(1.6, 1.6, 1.6);
    avatar.rotation.y = 0;
    scene.add(avatar);

    animate();
    setupGUI();
  },
  undefined,
  (err) => {
    console.error('Error loading avatar.glb:', err);
    alert('Could not load avatar.glb – see console.');
  }
);

// LIPSYNC (unchanged)
window.avatarLipSync = function(text) {
  if (!window.speechSynthesis || !avatar || mouthShapeKey == null) return;
  let voices = window.speechSynthesis.getVoices();
  let selectedVoice = voices.find(v =>
    v.lang === 'it-IT' && v.name.toLowerCase().includes("google italiano")
  ) || voices.find(v => v.lang === 'it-IT');

  const utter = new window.SpeechSynthesisUtterance(text);
  utter.lang = 'it-IT';
  if (selectedVoice) utter.voice = selectedVoice;
  utter.pitch = 1.03;
  utter.rate = 1.0;

  utter.onstart = () => {
    let t0 = performance.now();
    function loop() {
      let t = (performance.now() - t0) * 0.014;
      setMouth(0.35 + 0.44 * Math.abs(Math.sin(t)));
      if (window.speechSynthesis.speaking) requestAnimationFrame(loop);
      else setMouth(0);
    }
    loop();
  };
  window.speechSynthesis.speak(utter);
};

function setMouth(val) {
  if (!avatar || mouthShapeKey == null) return;
  avatar.traverse(obj => {
    if (obj.isMesh && obj.morphTargetDictionary && obj.morphTargetInfluences) {
      const idx = obj.morphTargetDictionary[mouthShapeKey];
      if (idx !== undefined) obj.morphTargetInfluences[idx] = val;
    }
  });
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

// Responsive
window.addEventListener('resize', () => {
  const widget = document.querySelector('.avatar-widget');
  if (widget) {
    const w = widget.offsetWidth, h = widget.offsetHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
});

// --- dat.GUI for interactive adjustment ---
function setupGUI() {
  if (!avatar) return;
  const gui = new GUI({ container: document.getElementById('avatar-container'), width: 220 });

  const camFolder = gui.addFolder('Camera');
  camFolder.add(camera.position, 'x', -2, 2, 0.01).name('cam.x').onChange(()=>{});
  camFolder.add(camera.position, 'y', 0.5, 3, 0.01).name('cam.y').onChange(()=>{});
  camFolder.add(camera.position, 'z', 0.5, 4, 0.01).name('cam.z').onChange(()=>{});
  camFolder.add({lookY: 1.45}, 'lookY', 0, 2.5, 0.01)
    .name('look at y')
    .onChange((v) => camera.lookAt(0, v, 0));
  camFolder.open();

  const avFolder = gui.addFolder('Avatar');
  avFolder.add(avatar.position, 'y', -2, 0, 0.01).name('av.pos.y').onChange(()=>{});
  avFolder.add(avatar.scale, 'x', 1, 2.5, 0.01).name('scale').onChange((v)=>{
    avatar.scale.set(v, v, v);
  });
  avFolder.add(avatar.rotation, 'y', -Math.PI, Math.PI, 0.01).name('rotate y');
  avFolder.open();
}
