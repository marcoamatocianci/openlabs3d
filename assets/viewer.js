import * as THREE from 'three';
import {OrbitControls} from './vendor/three/OrbitControls.js';
import {GLTFLoader} from './vendor/three/GLTFLoader.js';
import {STLLoader} from './vendor/three/STLLoader.js';
export async function mountViewer(host,url,color,material){
 const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
 const scene=new THREE.Scene();scene.background=new THREE.Color('#edf1f2');const camera=new THREE.PerspectiveCamera(38,1,.1,10000);
 const controls=new OrbitControls(camera,renderer.domElement);controls.enablePan=false;controls.listenToKeyEvents(renderer.domElement);renderer.domElement.tabIndex=0;renderer.domElement.setAttribute('aria-label','3D product: drag to rotate, pinch or scroll to zoom');
 scene.add(new THREE.HemisphereLight(0xffffff,0x83949e,2.6));const key=new THREE.DirectionalLight(0xffffff,3);key.position.set(150,240,180);key.castShadow=true;key.shadow.mapSize.set(1024,1024);Object.assign(key.shadow.camera,{left:-200,right:200,top:200,bottom:-200,far:1000});key.shadow.bias=-.001;scene.add(key);
 const fill=new THREE.DirectionalLight(0xc7e7ff,1.5);fill.position.set(-150,80,-100);scene.add(fill);
 let model,disposed=false;const materials=new Set();let observer;
 const render=()=>{if(!disposed)renderer.render(scene,camera)};
 const dispose=()=>{disposed=true;observer?.disconnect();controls.dispose();scene.traverse(o=>{o.geometry?.dispose();if(o.material)for(const m of [].concat(o.material))m.dispose()});renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()};
 host.disposeViewer=dispose;
 try{
 const progress=e=>{const status=host.querySelector('[role=status]');if(status)status.textContent=e.total?`Loading 3D model ${Math.round(e.loaded/e.total*100)}%`:'Loading 3D model…'};
 model=url.endsWith('.stl')?new THREE.Mesh(await new STLLoader().loadAsync(url,progress),new THREE.MeshStandardMaterial()):(await new GLTFLoader().loadAsync(url,progress)).scene;
 if(disposed||!host.isConnected){model.traverse(o=>{o.geometry?.dispose();if(o.material)[].concat(o.material).forEach(m=>m.dispose())});return null}
 model.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;for(const m of [].concat(o.material)){m.metalness=0;materials.add(m)}}});
 let box=new THREE.Box3().setFromObject(model),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());model.position.sub(center);scene.add(model);const radius=size.length()/2;
 const floor=new THREE.Mesh(new THREE.PlaneGeometry(radius*8,radius*8),new THREE.ShadowMaterial({opacity:.15}));floor.rotation.x=-Math.PI/2;floor.position.y=-size.y/2-.2;floor.receiveShadow=true;scene.add(floor);
 const reset=()=>{const distance=radius/Math.sin(THREE.MathUtils.degToRad(camera.fov)/2)*Math.max(1,1/camera.aspect)*1.1;camera.position.copy(new THREE.Vector3(1,.85,1.2).normalize().multiplyScalar(distance));controls.target.set(0,0,0);controls.minDistance=radius*1.15;controls.maxDistance=distance*3;controls.update();render()};
 const update=(color,material)=>{materials.forEach(m=>{m.color.set(color);m.roughness=material==='PETG'?.32:material==='ABS'?.42:.65});render()};
 host.querySelector('[role=status]')?.remove();host.prepend(renderer.domElement);host.dataset.loaded='true';
 const resize=()=>{const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();render()};observer=new ResizeObserver(resize);observer.observe(host);resize();reset();update(color,material);controls.addEventListener('change',render);
 return {update,reset,dispose,zoom(factor){camera.position.multiplyScalar(factor);controls.update();render()}};
 }catch(e){dispose();throw e}
}
