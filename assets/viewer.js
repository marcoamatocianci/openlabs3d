import * as THREE from 'three';
import {OrbitControls} from './vendor/three/OrbitControls.js';
import {GLTFLoader} from './vendor/three/GLTFLoader.js';
import {STLLoader} from './vendor/three/STLLoader.js';
export async function mountViewer(host,url,color,material){
 const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
 const scene=new THREE.Scene();renderer.setClearColor(0x000000,0);const camera=new THREE.PerspectiveCamera(38,1,.1,10000);
 const controls=new OrbitControls(camera,renderer.domElement);controls.enablePan=false;controls.listenToKeyEvents(renderer.domElement);renderer.domElement.tabIndex=0;renderer.domElement.setAttribute('aria-label','3D product: drag to rotate, pinch or scroll to zoom');
 // Neutral studio matching the still renders: no floor, soft key, broad fill, rim, grey room; shadows only self-cast (bores).
 renderer.toneMapping=THREE.NeutralToneMapping;renderer.toneMappingExposure=1;
 scene.add(new THREE.HemisphereLight(0xffffff,0x9a9a9a,1.4));const key=new THREE.DirectionalLight(0xffffff,2.6);key.position.set(-150,240,90);key.castShadow=true;key.shadow.mapSize.set(2048,2048);key.shadow.radius=8;Object.assign(key.shadow.camera,{left:-200,right:200,top:200,bottom:-200,far:1000});key.shadow.bias=-.0005;key.shadow.normalBias=.4;scene.add(key);
 const fill=new THREE.DirectionalLight(0xffffff,.7);fill.position.set(220,90,-90);scene.add(fill);const rim=new THREE.DirectionalLight(0xffffff,1.1);rim.position.set(60,130,-240);scene.add(rim);
 let model,disposed=false;const materials=new Set();let observer;
 const render=()=>{if(!disposed)renderer.render(scene,camera)};
 const dispose=()=>{disposed=true;observer?.disconnect();controls.dispose();scene.traverse(o=>{o.geometry?.dispose();if(o.material)for(const m of [].concat(o.material))m.dispose()});renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()};
 host.disposeViewer=dispose;
 try{
 const progress=e=>{const status=host.querySelector('[role=status]');if(status)status.textContent=e.total?`Loading 3D model ${Math.round(e.loaded/e.total*100)}%`:'Loading 3D model…'};
 model=url.endsWith('.stl')?new THREE.Mesh(await new STLLoader().loadAsync(url,progress),new THREE.MeshStandardMaterial()):(await new GLTFLoader().loadAsync(url,progress)).scene;
 if(disposed||!host.isConnected){model.traverse(o=>{o.geometry?.dispose();if(o.material)[].concat(o.material).forEach(m=>m.dispose())});return null}
 model.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;for(const m of [].concat(o.material)){m.metalness=0;materials.add(m)}}});
 let box=new THREE.Box3().setFromObject(model),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());model.position.sub(center);scene.add(model);const radius=size.length()/2;camera.near=radius/100;camera.far=radius*100;camera.updateProjectionMatrix();key.position.set(-radius*1.4,radius*3.2,-radius*.7);fill.position.set(radius*2.2,radius*.9,radius*.9);rim.position.set(radius*.6,radius*1.3,-radius*2.4);Object.assign(key.shadow.camera,{left:-radius*2,right:radius*2,top:radius*2,bottom:-radius*2,far:radius*10});key.shadow.camera.updateProjectionMatrix();
 const reset=()=>{const distance=radius/Math.sin(THREE.MathUtils.degToRad(camera.fov)/2)*Math.max(1,1/camera.aspect)*1.1;camera.position.copy(new THREE.Vector3(1.2,1.15,1.5).normalize().multiplyScalar(distance));controls.target.set(0,0,0);controls.minDistance=radius*1.15;controls.maxDistance=distance*3;controls.update();render()};
 // Swatches are display colors; real filament reads darker and less saturated (same as product-visuals.js).
 const filament=hex=>{const c=new THREE.Color(hex),y=.2126*c.r+.7152*c.g+.0722*c.b;for(const k of ['r','g','b'])c[k]=Math.min(.8,Math.max(.012,(y+(c[k]-y)*.8)*.85));return c};
 const update=(color,material)=>{materials.forEach(m=>{m.color.copy(filament(color));m.roughness=material==='PETG'?.38:material==='ABS'?.5:.58;m.envMapIntensity=0});render()};
 host.querySelector('[role=status]')?.remove();host.prepend(renderer.domElement);host.dataset.loaded='true';
 const resize=()=>{const w=host.clientWidth,h=host.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();render()};observer=new ResizeObserver(resize);observer.observe(host);resize();reset();update(color,material);controls.addEventListener('change',render);
 return {update,reset,dispose,zoom(factor){camera.position.multiplyScalar(factor);controls.update();render()}};
 }catch(e){dispose();throw e}
}
