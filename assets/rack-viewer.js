/* The 3D stage of the rack configurator. Draws the plan's shapes straight away, then swaps in the exact CAD preview when
   the worker has made it. Renders on demand, reuses one funnel geometry per tube shape, redraws its shadow only when the
   model changes, and disposes everything it replaces. */
import * as THREE from 'three';
import {OrbitControls} from './vendor/three/OrbitControls.js';
import {GLTFLoader} from './vendor/three/GLTFLoader.js';
import {mergeGeometries} from './vendor/three/BufferGeometryUtils.js';

// Swatches are display colours; real filament reads darker and less saturated (same as viewer.js and product-visuals.js).
const filament = hex => { const c = new THREE.Color(hex), y = .2126 * c.r + .7152 * c.g + .0722 * c.b; for (const k of ['r', 'g', 'b']) c[k] = Math.min(.8, Math.max(.05, (y + (c[k] - y) * .8) * .85)); return c; };
// The default angle is the one the static renders use, so a thumbnail and the 3D model look like the same object.
const VIEWS = {iso: [-1.05, .95, 1.5], top: [0, 1, .0001], front: [0, .16, 1]};
const NEUTRAL = '#b8c4ca';
const CACHE_SIZE = 6;
const CREASE = THREE.MathUtils.degToRad(38);     // smooth across facets of one curved surface, crisp at a designed edge
const MARGIN = 1.2;                              // room around the model, as a share of what it needs to fit

const toPlan = ([x, y]) => new THREE.Vector2(x, y);
function bandGeometry(bands) {
  const parts = [];
  for (const band of bands) for (const poly of band.polys) {
    if (poly.outer.length < 3) continue;
    const shape = new THREE.Shape(poly.outer.map(toPlan));
    for (const hole of poly.holes) shape.holes.push(new THREE.Path(hole.map(toPlan)));
    const g = new THREE.ExtrudeGeometry(shape, {depth: band.z1 - band.z0, bevelEnabled: false, curveSegments: 1, steps: 1});
    g.translate(0, 0, band.z0); parts.push(g);
  }
  if (!parts.length) return null;
  const merged = parts.length > 1 ? mergeGeometries(parts) : parts[0];
  if (parts.length > 1) parts.forEach(p => p.dispose());
  merged.rotateX(-Math.PI / 2);      // CAD Z up to three.js Y up, as the exact preview is written
  return merged;
}
/** Normals that are smooth along a curved surface and sharp at a designed edge. Each face counts by the angle it makes at the
    vertex, not equally: a CAD mesh has long thin triangles beside tiny ones, and counting them equally makes a smooth edge shimmer. */
function creasedNormals(source, crease) {
  const geometry = source.index ? source.toNonIndexed() : source, p = geometry.attributes.position.array, count = p.length / 9;
  const faces = new Float32Array(count * 3), weights = new Float32Array(count * 3), corners = new Map(), limit = Math.cos(crease);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), ab = new THREE.Vector3(), ac = new THREE.Vector3(), bc = new THREE.Vector3(), n = new THREE.Vector3();
  for (let t = 0; t < count; t++) {
    a.fromArray(p, t * 9); b.fromArray(p, t * 9 + 3); c.fromArray(p, t * 9 + 6);
    ab.subVectors(b, a); ac.subVectors(c, a); bc.subVectors(c, b);
    n.crossVectors(ab, ac).normalize(); n.toArray(faces, t * 3);
    weights[t * 3] = ab.angleTo(ac); weights[t * 3 + 1] = Math.PI - ab.angleTo(bc); weights[t * 3 + 2] = Math.PI - weights[t * 3] - weights[t * 3 + 1];
    for (let k = 0; k < 3; k++) {
      const i = t * 9 + k * 3, key = (Math.round(p[i] * 500) + 131072) * 68719476736 + (Math.round(p[i + 1] * 500) + 131072) * 262144 + Math.round(p[i + 2] * 500) + 131072;     // a number: far quicker than a string, for a hundred thousand corners
      (corners.get(key) || corners.set(key, []).get(key)).push(t * 3 + k);
    }
  }
  const normals = new Float32Array(p.length);
  for (const list of corners.values()) for (const corner of list) {
    const f = Math.floor(corner / 3) * 3; let x = 0, y = 0, z = 0;
    for (const other of list) {
      const g = Math.floor(other / 3) * 3;
      if (faces[f] * faces[g] + faces[f + 1] * faces[g + 1] + faces[f + 2] * faces[g + 2] < limit) continue;
      x += faces[g] * weights[other]; y += faces[g + 1] * weights[other]; z += faces[g + 2] * weights[other];
    }
    const size = Math.hypot(x, y, z) || 1;
    normals[corner * 3] = x / size; normals[corner * 3 + 1] = y / size; normals[corner * 3 + 2] = z / size;
  }
  geometry.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  return geometry;
}
function tubeProfile(t) {
  // A tube as a revolved outline, tip at zero, to scale.
  const r = t.body / 2, tip = t.tip / 2, top = t.length - t.capHeight;
  return [new THREE.Vector2(0, 0), new THREE.Vector2(tip, 0), new THREE.Vector2(r, t.cone), new THREE.Vector2(r, top), new THREE.Vector2(0, top)];
}
function reduced() { return matchMedia('(prefers-reduced-motion: reduce)').matches; }

export function createRackViewer(host, {onLoadState, tubeInfo, lowPower = false}) {
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, lowPower ? 1.75 : 2));
  renderer.toneMapping = THREE.NeutralToneMapping; renderer.setClearColor(0x000000, 0);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.shadowMap.autoUpdate = false;
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute('aria-label', '3D model of your rack. Drag or use the arrow keys to rotate, right-drag to pan, pinch or scroll to zoom. The buttons change the view. Everything shown here is also listed in the summary.');
  host.prepend(renderer.domElement);
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(26, 1, 1, 5000);
  // A soft studio from lights alone: a generated environment map cost 600 ms of blocking at load for reflections that matte filament barely shows.
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8c95a0, 1.75));
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.listenToKeyEvents(renderer.domElement); controls.enableDamping = false; controls.maxPolarAngle = Math.PI * .62; controls.screenSpacePanning = true;
  const key = new THREE.DirectionalLight(0xffffff, 1.9), fill = new THREE.DirectionalLight(0xffffff, .55), rim = new THREE.DirectionalLight(0xffffff, .5);
  key.position.set(.55, 1, .62); fill.position.set(-1, .25, .8); rim.position.set(-.6, .35, -1); scene.add(key, key.target, fill, rim);
  key.castShadow = true; key.shadow.mapSize.set(lowPower ? 1024 : 1536, lowPower ? 1024 : 1536); key.shadow.bias = -.0004; key.shadow.normalBias = .35; key.shadow.radius = 5;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({opacity: .16}));
  ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);
  const material = new THREE.MeshStandardMaterial({color: filament(NEUTRAL), roughness: .52, metalness: 0});
  const tubeMaterial = new THREE.MeshStandardMaterial({color: 0xdfe8ef, roughness: .25, metalness: 0, transparent: true, opacity: .22, depthWrite: false});
  const capMaterial = new THREE.MeshStandardMaterial({color: 0x7f9ab2, roughness: .6, metalness: 0, transparent: true, opacity: .38, depthWrite: false});
  const cache = new Map();
  const overlay = document.createElement('div'); overlay.className = 'rk-dims'; overlay.setAttribute('aria-hidden', 'true'); host.append(overlay);
  let tubeTop = 0, mesh = null, funnelMeshes = [], decal = null, tubes = [], guides = null, guideLabels = [], showGuides = false, showTubes = false, shownKey = '', size = null, dims = null, wanted = '', disposed = false, framed = false, rafPending = false;

  const project = v => { const p = v.clone().project(camera); return [(p.x + 1) / 2 * host.clientWidth, (1 - p.y) / 2 * host.clientHeight]; };
  const draw = () => {
    if (disposed) return;
    renderer.render(scene, camera);
    for (const {node, at} of guideLabels) { const [x, y] = project(at); node.style.transform = `translate(-50%,-50%) translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`; }
  };
  const requestDraw = () => { if (rafPending) return; rafPending = true; requestAnimationFrame(() => { rafPending = false; draw(); }); };
  controls.addEventListener('change', requestDraw);
  const resize = () => { const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); if (dims) fit(); draw(); };
  const observer = new ResizeObserver(resize); observer.observe(host);

  /** Distance at which every corner of the model's box is in view, for a camera looking along this direction. */
  function distanceFor(direction, w, d, h, target) {
    const look = direction.clone().negate(), right = new THREE.Vector3().crossVectors(look, camera.up).normalize(), up = new THREE.Vector3().crossVectors(right, look);
    const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2), tanH = tanV * camera.aspect;
    let need = 0;
    for (const x of [-w / 2, w / 2]) for (const y of [0, h]) for (const z of [-d / 2, d / 2]) {
      const c = new THREE.Vector3(x, y, z).sub(target);
      const forward = c.dot(look);     // towards the far side the camera may be nearer for the same screen size
      need = Math.max(need, Math.abs(c.dot(right)) / tanH - forward, Math.abs(c.dot(up)) / tanV - forward);
    }
    return need * MARGIN;
  }
  function place(direction) {
    const [w, d, rack] = dims, h = showTubes ? Math.max(rack, tubeTop) : rack;
    controls.target.set(0, h / 2, 0);
    const distance = distanceFor(direction, w, d, h, controls.target), radius = Math.hypot(w, d, h) / 2;
    camera.position.copy(direction).multiplyScalar(distance).add(controls.target);
    camera.near = Math.max(1, distance / 40); camera.far = distance * 12; camera.updateProjectionMatrix();
    controls.minDistance = radius * .5; controls.maxDistance = distance * 3; controls.update();
  }
  function view(name = 'iso') { if (!dims) return; place(new THREE.Vector3(...VIEWS[name]).normalize()); draw(); }
  /** The rack changed size: fit it again from wherever the buyer has turned it to. */
  function fit() { if (dims) place(camera.position.clone().sub(controls.target).normalize()); }
  function stage() {
    // The shadow is drawn once per model, and only redrawn when the model changes.
    if (!dims) { renderer.shadowMap.needsUpdate = true; return; }
    const [w, d, h] = dims, span = Math.hypot(w, d, h), c = key.shadow.camera;
    key.position.set(.55, 1, .62).normalize().multiplyScalar(span * 2.2); key.target.position.set(0, h / 3, 0); key.target.updateMatrixWorld();
    c.left = -span * .8; c.right = span * .8; c.top = span * .8; c.bottom = -span * .8; c.near = span * .4; c.far = span * 4.4; c.updateProjectionMatrix();
    ground.scale.set(span * 5, span * 5, 1);
    rim.position.set(-.6, .35, -1).multiplyScalar(span);
    renderer.shadowMap.needsUpdate = true;
  }
  function clearFunnels() { for (const m of funnelMeshes) { scene.remove(m); m.geometry.dispose(); m.dispose(); } funnelMeshes = []; }
  function setMesh(geometry) {
    if (mesh) { scene.remove(mesh); if (![...cache.values()].includes(mesh.geometry)) mesh.geometry.dispose(); }
    mesh = geometry ? new THREE.Mesh(geometry, material) : null;
    if (mesh) { mesh.castShadow = mesh.receiveShadow = true; scene.add(mesh); }
  }
  function setFunnels(funnels) {
    clearFunnels();
    const matrix = new THREE.Matrix4();
    for (const funnel of funnels || []) {
      const geometry = bandGeometry(funnel.bands); if (!geometry) continue;
      const instanced = new THREE.InstancedMesh(geometry, material, funnel.at.length);
      funnel.at.forEach(([x, y], i) => { matrix.makeTranslation(x, 0, -y); instanced.setMatrixAt(i, matrix); });
      instanced.castShadow = instanced.receiveShadow = true; scene.add(instanced); funnelMeshes.push(instanced);
    }
  }
  function clearDecal() { if (decal) { scene.remove(decal); decal.geometry.dispose(); decal.material.map.dispose(); decal.material.dispose(); decal = null; } }
  function setDecal(label) {
    clearDecal();
    if (!label) return;
    const canvas = document.createElement('canvas'), scale = 16, family = {serif: 'serif', mono: 'monospace'}[label.font] || 'sans-serif';
    const w = (label.width + 2) * scale, h = label.size * 1.3 * scale;
    canvas.width = Math.min(2048, Math.ceil(w)); canvas.height = Math.min(512, Math.ceil(h));
    const c = canvas.getContext('2d');
    c.font = `700 ${label.size * scale}px ${family}`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillStyle = 'rgba(10,20,35,.72)';
    c.fillText(label.text, canvas.width / 2, canvas.height / 2);
    decal = new THREE.Mesh(new THREE.PlaneGeometry(label.width + 2, label.size * 1.3), new THREE.MeshBasicMaterial({map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false}));
    decal.rotation.order = 'YXZ';
    const [x, y, z] = label.anchor, out = .15, lean = -THREE.MathUtils.degToRad(label.rake || 0);
    if (label.position === 'front') { decal.position.set(x, z, -y + out); decal.rotation.x = lean; }
    else if (label.position === 'back') { decal.position.set(x, z, -y - out); decal.rotation.y = Math.PI; decal.rotation.x = lean; }
    else if (label.position === 'left') { decal.position.set(x - out, z, -y); decal.rotation.y = -Math.PI / 2; decal.rotation.x = lean; }
    else if (label.position === 'right') { decal.position.set(x + out, z, -y); decal.rotation.y = Math.PI / 2; decal.rotation.x = lean; }
    else { decal.position.set(x, z + out, -y); decal.rotation.x = -Math.PI / 2; }
    scene.add(decal);
  }
  function setTubes(list) {
    for (const m of tubes) { scene.remove(m); m.geometry.dispose(); m.dispose(); }
    tubes = [];
    const groups = new Map();
    for (const t of list) { (groups.get(t.profile_id) || groups.set(t.profile_id, []).get(t.profile_id)).push(t); }
    const matrix = new THREE.Matrix4();
    for (const [id, placed] of groups) {
      const info = tubeInfo(id, placed[0]);
      const body = new THREE.LatheGeometry(tubeProfile(info), 24), cap = new THREE.CylinderGeometry(info.cap / 2, info.cap / 2, info.capHeight, 24);
      cap.translate(0, info.length - info.capHeight / 2, 0);
      const bodies = new THREE.InstancedMesh(body, tubeMaterial, placed.length), caps = new THREE.InstancedMesh(cap, capMaterial, placed.length);
      placed.forEach((t, i) => { matrix.makeTranslation(t.x, t.floor, -t.y); bodies.setMatrixAt(i, matrix); caps.setMatrixAt(i, matrix); });
      bodies.renderOrder = caps.renderOrder = 2; bodies.visible = caps.visible = showTubes;
      scene.add(bodies, caps); tubes.push(bodies, caps);
    }
  }
  function setGuides() {
    if (guides) { scene.remove(guides); guides.geometry.dispose(); guides.material.dispose(); guides = null; }
    overlay.replaceChildren(); guideLabels = [];
    if (!showGuides || !dims) return draw();
    const [w, d, h] = dims, x = w / 2, z = d / 2, o = 6;
    const lines = [[-x, 0, z + o, x, 0, z + o], [x + o, 0, -z, x + o, 0, z], [x + o, 0, z + o, x + o, h, z + o]];
    guides = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(lines.flat(), 3)), new THREE.LineBasicMaterial({color: 0x457b9d}));
    scene.add(guides);
    const add = (text, at) => { const node = document.createElement('span'); node.textContent = text; overlay.append(node); guideLabels.push({node, at}); };
    add(`${w.toFixed(1)} mm`, new THREE.Vector3(0, 0, z + o)); add(`${d.toFixed(1)} mm`, new THREE.Vector3(x + o, 0, 0)); add(`${h.toFixed(1)} mm`, new THREE.Vector3(x + o, h / 2, z + o));
    draw();
  }

  return {
    /** Show a new plan at once, from the server's shapes. A rack seen before comes straight from the cache. */
    showPlan(plan) {
      if (disposed) return;
      wanted = plan.hash || '';
      tubeTop = Math.max(0, ...plan.tubes.map(t => t.floor + t.length));
      const previous = size; dims = plan.dims; size = dims.join() + '/' + tubeTop.toFixed(1);
      setTubes(plan.tubes);
      if (cache.has(wanted)) { useExact(wanted); }
      else {
        const signature = plan.hash || JSON.stringify(plan.bands).length + size;
        if (signature !== shownKey) { setMesh(bandGeometry(plan.bands)); setFunnels(plan.funnels); shownKey = signature; setDecal(plan.label); onLoadState?.('plan'); }
      }
      if (!framed) { framed = true; stage(); view('iso'); }
      else if (previous !== size) { stage(); fit(); }
      else stage();
      setGuides(); draw();
    },
    clear() { setMesh(null); clearFunnels(); setTubes([]); clearDecal(); shownKey = ''; size = null; dims = null; wanted = ''; stage(); setGuides(); draw(); },
    /** Replace the approximate shape with the exact CAD preview, if the design has not moved on meanwhile. */
    async showExact(hash, url) {
      if (cache.has(hash)) { if (hash === wanted) useExact(hash); return; }
      const gltf = await new GLTFLoader().loadAsync(url);
      let source = null;
      gltf.scene.traverse(o => { if (o.isMesh && !source) { source = o.geometry; for (const m of [].concat(o.material)) m.dispose(); } });
      if (disposed || !source) { source?.dispose(); return; }
      // Smooth along curved surfaces, sharp at the edges the design meant: from the CAD where the worker wrote its normals,
      // otherwise worked out once, when the model arrives.
      const exact = gltf.parser?.json?.asset?.extras?.exact_normals;
      const geometry = exact ? source : creasedNormals(source, CREASE);
      if (geometry !== source) source.dispose();
      cache.set(hash, geometry);
      if (cache.size > CACHE_SIZE) { const [oldest, stale] = cache.entries().next().value; cache.delete(oldest); if (mesh?.geometry !== stale) stale.dispose(); }
      if (hash === wanted) useExact(hash);
    },
    setColor(hex, name) { material.color.copy(filament(hex || NEUTRAL)); material.roughness = name === 'PETG' ? .36 : name === 'ABS' ? .48 : .56; draw(); },
    setTubesVisible(on) { showTubes = on; tubes.forEach(m => { m.visible = on; }); if (dims) fit(); draw(); },
    setGuidesVisible(on) { showGuides = on; setGuides(); },
    /** What is really on screen: the identity of the exact model if it is showing, and its measurements, in millimetres. */
    shown() {
      if (!mesh || funnelMeshes.length || !cache.has(shownKey) || mesh.geometry !== cache.get(shownKey)) return {kind: mesh || funnelMeshes.length ? 'plan' : 'none', hash: ''};
      const g = mesh.geometry; g.computeBoundingBox();
      const size = g.boundingBox.getSize(new THREE.Vector3()), p = g.attributes.position, index = g.index, a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
      let volume = 0;
      const triangles = (index ? index.count : p.count) / 3;
      for (let t = 0; t < triangles; t++) {
        const [i, j, k] = index ? [index.getX(t * 3), index.getX(t * 3 + 1), index.getX(t * 3 + 2)] : [t * 3, t * 3 + 1, t * 3 + 2];
        a.fromBufferAttribute(p, i); b.fromBufferAttribute(p, j); c.fromBufferAttribute(p, k);
        volume += a.dot(b.cross(c)) / 6;
      }
      return {kind: 'exact', hash: shownKey, dims: [size.x, size.z, size.y], volume: Math.abs(volume), triangles};
    },
    /** On a phone the compact preview does not take gestures: the page must scroll under a thumb. */
    setInteractive(on) { controls.enabled = on; },
    view, resize,
    info: () => ({calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures, shadowAutoUpdate: renderer.shadowMap.autoUpdate, motion: !reduced()}),
    dispose() {
      disposed = true; observer.disconnect(); controls.dispose(); clearDecal(); clearFunnels(); setTubes([]);
      for (const g of cache.values()) g.dispose();
      if (mesh && ![...cache.values()].includes(mesh.geometry)) mesh.geometry.dispose();
      material.dispose(); tubeMaterial.dispose(); capMaterial.dispose(); ground.geometry.dispose(); ground.material.dispose(); key.shadow.map?.dispose(); showGuides = false; setGuides();
      renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove(); overlay.remove();
    },
  };
  function useExact(hash) {
    const geometry = cache.get(hash);
    if (mesh?.geometry === geometry && !funnelMeshes.length) return;
    clearFunnels(); setMesh(geometry); clearDecal(); shownKey = hash; onLoadState?.('exact'); stage(); draw();
  }
}
