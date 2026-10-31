/* Shared, per-product browsing preference. Signed-in choices are isolated per account. */
function configurationKey(id){return `ol3d-config-${account?.id||'guest'}-${id}`}
function savedConfiguration(id){try{return JSON.parse(localStorage.getItem(configurationKey(id))||'null')}catch(e){return null}}
function saveConfiguration(id,c){try{localStorage.setItem(configurationKey(id),JSON.stringify({product_id:id,...c}))}catch(e){}}
function configurationFor(p){
 const o=p.configurator||{},saved=savedConfiguration(p.id);
 if(saved){const valid=!!o.colors_by_material?.[saved.material]?.[saved.color];return {...saved,valid,saved:true}}
 const material=Object.keys(o.materials||{})[0]||'',color=Object.keys(o.colors_by_material?.[material]||{})[0]||'';
 return {material,color,quantity:1,valid:!!color,saved:false};
}
const originalImageMarkup=imageMarkup;
const tintCache=new Map();
// Must match ALBEDO in backend/app/studio_scene.py.
const RENDER_ALBEDO=.55,REFLECTION=.06,LINEAR=Array.from({length:256},(_,v)=>{const c=v/255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4});
// Swatch hex values are display colors; real filament reads slightly darker and less saturated.
function filamentAlbedo(hex){const a=hex.slice(1).match(/../g).map(v=>LINEAR[parseInt(v,16)]),y=.2126*a[0]+.7152*a[1]+.0722*a[2];return a.map(c=>Math.min(.8,Math.max(.012,(y+(c-y)*.8)*.85)))}
// data-tint-size caps the recoloured image (in px) for small thumbnails: same look, far fewer pixels.
const tintKey=(source,color,size)=>source+color+(size?'@'+size:'');
function tintProductImage(img){
 const color=img.dataset.color,source=img.dataset.source,size=+img.dataset.tintSize||0;
 if(!color||!source||img.dataset.tinted===color)return;
 const key=tintKey(source,color,size);
 try{
  let tinted=tintCache.get(key);
  if(!tinted){const scale=size?Math.min(1,size/Math.max(img.naturalWidth,img.naturalHeight)):1,canvas=document.createElement('canvas');canvas.width=Math.round(img.naturalWidth*scale);canvas.height=Math.round(img.naturalHeight*scale);const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,canvas.width,canvas.height);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height),albedo=filamentAlbedo(color);
   // Linear-light recolor of the neutral render: diffuse light scales with the filament albedo, while a
   // small achromatic share (dielectric reflection) stays grey, so dark plastics keep their sheen.
   const gain=albedo.map(a=>REFLECTION+(1-REFLECTION)*a/RENDER_ALBEDO),encode=new Uint8ClampedArray(4096);for(let k=0;k<4096;k++){const c=k/4095;encode[k]=255*(c<=.0031308?c*12.92:1.055*c**(1/2.4)-.055)}
   for(let i=0;i<pixels.data.length;i+=4){const light=LINEAR[pixels.data[i]];for(let j=0;j<3;j++)pixels.data[i+j]=encode[Math.min(4095,Math.round(light*gain[j]*4095))]}
   ctx.putImageData(pixels,0,0);tinted=canvas.toDataURL('image/webp',.9);if(tintCache.size>40)tintCache.clear();tintCache.set(key,tinted);
  }
  img.dataset.tinted=color;img.src=tinted;
 }catch(e){img.dataset.tinted=color}
}
imageMarkup=function(p,main=false){
 const visual=p.configurator?.visual;if(visual&&visual.status!=='none'&&visual.status!=='ready')return '<span class="image-fallback" role="status">'+(visual.status==='failed'?'Preview unavailable':'Preparing product preview…')+'</span>';if(visual?.status!=='ready')return originalImageMarkup(p,main);
 const c=configurationFor(p),hex=c.valid?p.configurator.colors_by_material[c.material][c.color]:'#b8c4ca',source=main?visual.image:visual.thumbnail;
 return `<img ${main?'id="gallery-main"':''} class="${main?'listing-main-image':'listing-card-image'}" data-product="${p.id}" data-source="${esc(source)}" data-color="${esc(hex)}" src="${esc(source)}" alt="${esc(p.name)}${c.valid?' — '+esc(c.material+' '+colorName(c.color)):''}" width="1200" height="1200" decoding="async" ${main?'':'loading="lazy"'} onload="tintProductImage(this)" onerror="this.outerHTML='<span class=&quot;image-fallback&quot;>Preview unavailable</span>'">`;
};
function updateProductPreview(p,c){
 const hex=p.configurator.colors_by_material?.[c.material]?.[c.color];if(!hex)return;
 document.querySelectorAll('img[data-product="'+p.id+'"]').forEach(img=>{img.dataset.color=hex;if(img.dataset.tinted!==hex){delete img.dataset.tinted;img.src=img.dataset.source}});
 viewer?.update(hex,c.material);
}
card=function(p){
 const c=configurationFor(p),available=Object.keys(p.configurator?.materials||{}).length>0;
 const config=c.saved?(c.valid?`${c.material} · ${colorName(c.color)}`:'Saved configuration unavailable'):'Choose your finish';
 const factor=c.valid?p.configurator.materials[c.material]:Math.min(...Object.values(p.configurator?.materials||{base:10000}));
 return `<article class="card product-card"><a class="product-card-link" href="#product/${p.id}"><div class="product-art">${imageMarkup(p)}</div><div class="card-body"><span class="eyebrow">${esc(p.category)}</span><h3>${esc(p.name)}</h3><p class="product-card-spec">${esc(p.compat)}</p><p class="product-card-selection ${c.saved&&!c.valid?'unavailable':''}">${esc(config)}</p><div class="card-bottom"><span class="price">${available?money(Math.round(p.price*100*factor/10000)/100):'Currently unavailable'}</span><span class="textlink">View product →</span></div></div></a><div class="card-actions"><button type="button" class="purchase-button purchase-button-primary" onclick="quickAddCard(${Number(p.id.slice(4))},this)" ${!available||!c.valid?'disabled':''}><span class="purchase-icon">${icon('cart')}</span><span>Add to Cart</span></button></div></article>`;
};
cardConfiguration=function(id){const p=state.products.find(x=>x.id==='api-'+id),c=p&&configurationFor(p);if(!c?.valid)throw Error('Choose an available material and color on the product page.');return {listing_id:id,material:c.material,color:c.color,quantity:1}};

async function regenerateProductRender(id,button){button.disabled=true;try{await api('/listings/'+id+'/render',{method:'POST'});toast('Preview generation queued. It will appear when ready.')}catch(e){showError(e)}finally{button.disabled=false}}
