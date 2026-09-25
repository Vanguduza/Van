// DEBUG ONLY. VAN's live state driving an owner-supplied VRM test model.
//
// The Android side (VrmTestRenderer) calls window.van.set({...}) with VAN's visual state and
// window.van.pause(bool) when the overlay should not animate. The model is served from
// /model/van_test.vrm; nothing here is VAN's identity or ships in a release build.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const params = new URLSearchParams(location.search);
const MODEL = params.get('model') || '/model/van_test.vrm';
const FRAMING = params.get('framing') || 'full'; // full | bust

const bridge = window.VanBridge || { ready() {}, failed(m) { console.error(m); } };

const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
renderer.setClearColor(0x000000, 0);
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(20, 1, 0.05, 50);
const key = new THREE.DirectionalLight(0xffffff, 2.6);
key.position.set(0.6, 1.4, 2.0);
scene.add(key);
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.1));

const state = { state: 'IDLE', speaking: false, listening: false, mouth: 0, action: 0, ax: 0, ay: 0 };
let paused = false;
let vrm = null;
let actionStart = 0;
let lastAction = 0;
let nextBlink = 2;
// VRM 0.x models are turned 180 degrees to face the camera (VRMUtils.rotateVRM0), which flips
// the sign of every X and Z bone rotation; Y is unchanged. Set once the model has loaded.
let S = 1;

window.van = {
  set(next) {
    Object.assign(state, next);
    if (state.action !== lastAction) {
      lastAction = state.action;
      actionStart = clock.elapsedTime;
    }
  },
  pause(p) {
    paused = !!p;
    if (!paused) loop();
  },
};

function resize() {
  const w = window.innerWidth || 1;
  const h = window.innerHeight || 1;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', () => { resize(); frame(); });
resize();

/** Frames the whole figure, or head and shoulders, from the model's own bones. */
function frame() {
  if (!vrm) return;
  const head = vrm.humanoid.getNormalizedBoneNode('head');
  const headPos = new THREE.Vector3();
  head.getWorldPosition(headPos);
  const box = new THREE.Box3().setFromObject(vrm.scene);
  const top = Math.max(box.max.y, headPos.y + 0.12);
  const bottom = FRAMING === 'bust' ? headPos.y - 0.45 : Math.min(box.min.y, 0);
  const height = (top - bottom) * 1.06;
  const centreY = (top + bottom) / 2;
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const fitH = height / 2 / Math.tan(fov / 2);
  const fitW = (height * 0.62) / 2 / Math.tan(fov / 2) / camera.aspect;
  const dist = Math.max(fitH, fitW);
  camera.position.set(0, centreY, dist);
  camera.lookAt(0, centreY, 0);
}

const clock = new THREE.Clock();
const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));
loader.load(
  MODEL,
  (gltf) => {
    vrm = gltf.userData.vrm;
    if (!vrm) { bridge.failed('not a VRM file'); return; }
    VRMUtils.removeUnnecessaryVertices(gltf.scene);
    VRMUtils.combineSkeletons(gltf.scene);
    VRMUtils.rotateVRM0(vrm);
    S = vrm.meta && vrm.meta.metaVersion === '0' ? -1 : 1;
    vrm.scene.traverse((o) => { o.frustumCulled = false; });
    scene.add(vrm.scene);
    restPose(0);
    vrm.update(0);
    frame();
    bridge.ready();
    loop();
  },
  undefined,
  (err) => bridge.failed(String(err && err.message || err)),
);

function bone(name) { return vrm.humanoid.getNormalizedBoneNode(name); }
/** Sets a bone's rotation in VRM 1.0 terms, whichever version the model is. */
function rot(name, x, y, z) { const b = bone(name); if (b) b.rotation.set(S * x, y, S * z); }
/** Adds to a bone's X (nod) or Z (tilt/raise) rotation in VRM 1.0 terms. */
function addX(name, v) { const b = bone(name); if (b) b.rotation.x += S * v; }
function lerpZ(name, target, w) { const b = bone(name); if (b) b.rotation.z = THREE.MathUtils.lerp(b.rotation.z, S * target, w); }
function expr(name, v) { if (vrm.expressionManager) vrm.expressionManager.setValue(name, v); }

/** Arms down from the T-pose every VRM is authored in, with a little life. */
function restPose(t) {
  const breath = Math.sin(t * Math.PI * 2 / 4.2);
  const sway = Math.sin(t * Math.PI * 2 / 7.3);
  rot('leftUpperArm', 0, 0, -1.22 + breath * 0.02);
  rot('rightUpperArm', 0, 0, 1.22 - breath * 0.02);
  rot('leftLowerArm', 0, -0.25, 0);
  rot('rightLowerArm', 0, 0.25, 0);
  rot('spine', breath * 0.015, 0, sway * 0.012);
  rot('chest', breath * 0.02, 0, 0);
  rot('hips', 0, sway * 0.03, 0);
  bone('hips').position.y = breath * 0.003;
}

function headPose(t) {
  const s = state.state;
  let x = -state.ay * 0.18;
  let y = state.ax * 0.35 + Math.sin(t * 0.9) * 0.04;
  let z = 0;
  if (state.listening || s === 'LISTENING' || s === 'ATTENTIVE') z = 0.12;
  if (s === 'THINKING' || s === 'SEARCHING') { x -= 0.12; y += 0.2; }
  if (s === 'SLEEPING') x += 0.35;
  if (s === 'ERROR' || s === 'WARNING' || s === 'DEGRADED') x += 0.08;
  rot('neck', x * 0.4, y * 0.4, z * 0.5);
  rot('head', x * 0.6, y * 0.6, z * 0.5);
}

function blinkAndMouth(t) {
  let blink = 0;
  if (state.state === 'SLEEPING') {
    blink = 1;
  } else {
    if (t > nextBlink + 0.18) nextBlink = t + 2.5 + Math.random() * 3;
    if (t >= nextBlink) blink = Math.sin(((t - nextBlink) / 0.18) * Math.PI);
  }
  expr('blink', Math.max(0, blink));
  let mouth = state.mouth || 0;
  if (state.speaking && mouth <= 0.01) mouth = 0.35 + 0.35 * Math.abs(Math.sin(t * 11));
  expr('aa', Math.min(1, mouth));
  expr('happy', state.state === 'SUCCESS' ? 0.7 : 0);
}

/** VAN's finite actions, played for ~2 s after the code arrives; 0 is none. */
function actionPose(t) {
  const a = state.action;
  if (!a) return;
  const k = t - actionStart;
  const w = Math.min(1, k / 0.25) * Math.min(1, Math.max(0, (2.2 - k) / 0.3));
  if (w <= 0) return;
  switch (a) {
    case 1: // HELLO_WAVE: right hand up beside the head, waving from the elbow
      lerpZ('rightUpperArm', -1.05, w);
      rot('rightLowerArm', 0, 0, (-0.9 + Math.sin(k * 12) * 0.35) * w);
      break;
    case 2: // ACK_NOD
      addX('head', Math.sin(k * 7) * 0.18 * w);
      break;
    case 3: case 4: case 5: case 6: case 7: { // POINT_*
      const up = a === 5 ? -0.5 : a === 6 ? 0.5 : 0;
      if (a === 3) {
        lerpZ('leftUpperArm', 0.05 + up, w);
      } else {
        lerpZ('rightUpperArm', -0.05 - up, w);
        rot('rightLowerArm', 0, 0, 0);
      }
      break;
    }
    case 8: // CELEBRATE: both arms up
      lerpZ('rightUpperArm', -1.0, w);
      lerpZ('leftUpperArm', 1.0, w);
      expr('happy', w);
      break;
    case 11: // SHRUG
      lerpZ('rightUpperArm', 0.7, w);
      lerpZ('leftUpperArm', -0.7, w);
      rot('rightLowerArm', 0, 1.0 * w, 0);
      rot('leftLowerArm', 0, -1.0 * w, 0);
      break;
    default: // the rest: a small acknowledging nod
      addX('head', Math.sin(k * 6) * 0.1 * w);
  }
}

function loop() {
  if (paused || !vrm) return;
  requestAnimationFrame(loop);
  const dt = Math.min(clock.getDelta(), 0.1);
  const t = clock.elapsedTime;
  restPose(t);
  headPose(t);
  blinkAndMouth(t);
  actionPose(t); // last, so a celebration's smile is not reset by the resting face
  vrm.update(dt);
  renderer.render(scene, camera);
}
