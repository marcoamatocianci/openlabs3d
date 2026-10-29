/* Product configuration and server-authoritative quotes, integrated with existing cart. */
const priorProduct=product,priorRender=render;
let viewer=null,activeHost=null,quoteSequence=0;
product=function(id){const p=state.products.find(x=>x.id===id);if(!p?.configurator)return priorProduct(id);const o=p.configurator,saved=(savedConfiguration(id)||{});const material=o.materials[saved.material]?saved.material:Object.keys(o.materials)[0],color=o.colors_by_material?.[material]?.[saved.color]?saved.color:Object.keys(o.colors_by_material?.[material]||{})[0]||'';
 return layout(`<a class="textlink" href="#catalogue">← Catalogue / ${esc(p.category)}</a><div class="config-layout"><div class="config-title"><span class="eyebrow">${esc(p.source)} · Made to order</span><h1>${esc(p.name)}</h1><p class="product-intro">${esc(p.compat||p.category)}</p></div><section class="config-media"><div id="model-viewer" class="model-viewer">${imageMarkup(p,true)}${o.model_url?'<p role="status">Loading 3D model…</p>':''}</div>${o.model_url?'<div class="viewer-tools"><span>Drag to rotate · Pinch to zoom</span><button type="button" id="zoom-in" aria-label="Zoom in">+</button><button type="button" id="zoom-out" aria-label="Zoom out">−</button><button type="button" id="reset-view">Reset View</button></div>':`<div class="gallery">${p.images.map(i=>`<button type="button" onclick="document.querySelector('#gallery-main').src=this.dataset.src" data-src="${esc(i.url)}"><img src="${esc(i.thumbnail_url)}" alt="Product photograph"></button>`).join('')}</div>`}<p class="muted">${o.model_url?'3D preview · Verify tube fit and material suitability before laboratory use.':'Seller-supplied product images.'}</p></section><form id="configurator" data-id="${p.id}" class="config-panel"><header class="configuration-heading"><h2>Make it yours</h2><p>Choose your finish and quantity.</p></header><div id="live-price" aria-live="polite" aria-atomic="true">Calculating price…</div><fieldset class="material-options"><legend>1. Choose material</legend><div class="material-grid">${Object.entries(o.materials).map(([m,factor])=>`<label class="material-choice"><input type="radio" name="material" value="${esc(m)}" ${m===material?'checked':''} required><span><strong>${esc(m)}</strong><small>${money(Math.round(p.price*100*factor/10000)/100)} / unit</small></span></label>`).join('')}</div></fieldset><fieldset class="color-options"><legend>2. Color <span id="selected-color"></span></legend><div class="swatches"></div></fieldset><p class="availability-message" role="status"></p><label class="quantity-label">3. Quantity<div class="quantity-control"><button type="button" id="quantity-minus" aria-label="Decrease quantity">−</button><input name="quantity" aria-label="Quantity" type="number" min="1" max="${o.max_quantity}" step="1" value="${Math.min(o.max_quantity,Math.max(1,saved.quantity||1))}" required><button type="button" id="quantity-plus" aria-label="Increase quantity">+</button></div></label><p id="config-error" role="alert"></p><div class="purchase-actions"><button id="config-add" class="purchase-button purchase-button-primary" disabled><span class="purchase-icon">${icon('cart')}</span><span>Add to Cart</span></button><button type="button" id="buy-now" class="purchase-button purchase-button-secondary" disabled>Buy Now</button></div><p class="muted">Payment and delivery are arranged with your printing host.</p></form><section class="product-details"><details open><summary>About this product</summary><p>${esc(p.description)}</p></details><details><summary>Specifications & compatibility</summary><dl>${[['Dimensions',p.dimensions],['Compatibility',p.compat],['Designed by',p.designer]].filter(([,v])=>v).map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl></details><details><summary>Laboratory use & care</summary><p>Confirm fit, cleaning requirements and material suitability with your printing host before use. Autoclaving, chemical resistance, sterility and diagnostic suitability have not been verified for this product.</p></details></section></div>`)};
function currentConfiguration(form){return {material:form.querySelector('[name="material"]:checked')?.value||'',color:form.querySelector('[name="color"]:checked')?.value||'',quantity:Number(form.elements.quantity.value)}}
async function obtainQuote(id,c){return api(`/listings/${id}/quote`,{method:'POST',body:JSON.stringify(c)})}
let configurationCleanup=()=>{};
function bindConfigurator(){
 configurationCleanup();
 const form=$('#configurator');if(!form)return;
 const p=state.products.find(p=>p.id===form.dataset.id),o=p.configurator;
 const add=form.querySelector('#config-add'),buy=form.querySelector('#buy-now'),price=form.querySelector('#live-price'),error=form.querySelector('#config-error'),message=form.querySelector('.availability-message');
 let first=true,refreshing=false,needsSelection=false;
 const update=async()=>{
  const seq=++quoteSequence,previous=currentConfiguration(form);
  price.dataset.ready='';add.disabled=buy.disabled=true;price.textContent='Checking availability…';error.textContent='';
  try{
   const fresh=await api('/listings/'+p.id.slice(4)+'/availability');
   if(seq!==quoteSequence||!form.isConnected)return;
   if(fresh.visual?.status==='ready'&&o.visual?.status!=='ready'){Object.assign(o,fresh);render();return;}
   Object.assign(o,fresh);
   const saved=savedConfiguration(p.id)||{};
   const desired=first||needsSelection?{...previous,...saved}:previous;first=false;
   const material=o.materials[desired.material]?desired.material:desired.material?'':Object.keys(o.materials)[0]||'';
   const colors=o.colors_by_material?.[material]||{};
   const materialChanged=previous.material!==saved.material && !first;
   const color=colors[desired.color]?desired.color:desired.color&&!materialChanged?'':Object.keys(colors)[0]||'';
   const materialMarkup=Object.entries(o.materials).map(([m,factor])=>`<label class="material-choice"><input type="radio" name="material" value="${esc(m)}" ${m===material?'checked':''} required><span><strong>${esc(m)}</strong><small>${money(Math.round(p.price*100*factor/10000)/100)} / unit</small></span></label>`).join('');
   const grid=form.querySelector('.material-grid');
   // Preserve focus when the choices themselves have not changed.
   const signature=JSON.stringify(o.materials);
   if(grid.dataset.signature!==signature){grid.innerHTML=materialMarkup;grid.dataset.signature=signature;}
   grid.querySelectorAll('input').forEach(el=>el.checked=el.value===material);
   const swatches=form.querySelector('.swatches'),colorSignature=JSON.stringify(colors);
   if(swatches.dataset.signature!==colorSignature){swatches.innerHTML=Object.entries(colors).map(([c,hex])=>`<label title="${esc(colorLabels[c]||c)}"><input type="radio" name="color" value="${esc(c)}"><span style="background:${hex}"></span><small>${esc(colorLabels[c]||c)}</small></label>`).join('');swatches.dataset.signature=colorSignature;}
   swatches.querySelectorAll('input').forEach(el=>el.checked=el.value===color);
   form.querySelector('.color-options').hidden=!Object.keys(colors).length;
   form.querySelector('#selected-color').textContent=colorLabels[color]||color;
   const changed=desired.material&&desired.material!==material||desired.color&&desired.color!==color;
   message.textContent=(!material||!color)&&desired.material?'Your saved configuration is no longer available. Choose an available material and color before purchasing.':!material?'Currently unavailable. No approved host has confirmed equipment, dimensions and colors for this product.':changed?'Choose your preferred available configuration.':'Available from compatible printing hosts.';
   if(!material||!color){needsSelection=!!desired.material;price.textContent='Choose an available configuration';return;}
   needsSelection=false;
   const c=currentConfiguration(form);
   form.elements.quantity.max=o.max_quantity;
   $('#quantity-minus').disabled=c.quantity<=1;$('#quantity-plus').disabled=c.quantity>=o.max_quantity;
   if(!Number.isInteger(c.quantity)||c.quantity<1||c.quantity>o.max_quantity){price.textContent='Choose a quantity';error.textContent=`Choose 1–${o.max_quantity} whole units.`;return;}
   saveConfiguration(p.id,c);updateProductPreview(p,c);
   const photo=$('#gallery-main');if(photo&&!o.visual?.image&&p.colorImages?.[c.color])photo.src=p.colorImages[c.color];
   viewer?.update(colors[c.color],c.material);
   const q=await obtainQuote(p.id.slice(4),c);
   if(seq!==quoteSequence||!form.isConnected)return;
   price.dataset.ready='1';
   price.innerHTML=`<div class="config-total"><span>Total <small>${q.quantity} ${q.quantity===1?'unit':'units'} · ${money(q.unit_price_cents/100)} each</small></span><strong>${money(q.total_cents/100)}</strong></div><details class="price-breakdown"><summary>Price breakdown</summary><dl><div><dt>Base unit price</dt><dd>${money(q.base_price_cents/100)}</dd></div><div><dt>Material adjustment</dt><dd>${money(q.material_adjustment_cents/100)}</dd></div><div><dt>Quantity discount</dt><dd>${q.discount_bps/100}%</dd></div></dl></details>`;
   add.disabled=!!form.dataset.purchasing;buy.disabled=!!form.dataset.purchasing;
  }catch(e){if(seq===quoteSequence&&form.isConnected){price.textContent='Configuration unavailable';error.textContent=e.message;}}
 };
 form.refreshAvailability=update;
 form.oninput=()=>{needsSelection=false;const c=currentConfiguration(form);updateProductPreview(p,c);update()};
 for(const [id,delta] of [['quantity-minus',-1],['quantity-plus',1]])form.querySelector('#'+id).onclick=()=>{form.elements.quantity.value=Number(form.elements.quantity.value)+delta;update()};
 const refresh=async()=>{if(!form.isConnected||document.hidden||refreshing||form.dataset.purchasing)return;refreshing=true;try{await update()}finally{refreshing=false}};
 const timer=setInterval(refresh,15000);window.addEventListener('focus',refresh);
 configurationCleanup=()=>{clearInterval(timer);window.removeEventListener('focus',refresh)};
 update();const host=$('#model-viewer');activeHost=host;if(o.model_url)import('./viewer.js?v=studio-3').then(m=>m.mountViewer(host,o.model_url,o.colors[currentConfiguration(form).color],currentConfiguration(form).material)).then(v=>{if(!host.isConnected){v?.dispose();return}viewer=v;if(v){host.querySelector('img')?.remove();const c=currentConfiguration(form);v.update(o.colors[c.color],c.material);$('#reset-view').onclick=()=>v.reset();$('#zoom-in').onclick=()=>v.zoom(.85);$('#zoom-out').onclick=()=>v.zoom(1.15)}}).catch(()=>{if(host.isConnected){document.querySelectorAll('.viewer-tools button').forEach(b=>b.disabled=true);host.querySelector('[role=status]')?.remove();host.insertAdjacentHTML('beforeend','<p role="alert">3D preview unavailable. You can still choose a configuration.</p>')}})
}
render=function(){viewer?.dispose();activeHost?.disposeViewer?.();viewer=null;quoteSequence++;priorRender();bindConfigurator()};
changeCart=async function(index,value){const item=opsCart[index],quantity=Number(value);try{const q=await obtainQuote(item.id,{material:item.material,color:item.color||'',quantity});item.quantity=quantity;item.price_cents=q.unit_price_cents;sessionStorage.removeItem('ol3d-order-key');saveOpsCart();render()}catch(e){toast(e.message);render()}};
const priorCart=cartPage;
cartPage=function(){let html=priorCart();for(const i of opsCart){html=html.replace(`<h3>${esc(i.title)}</h3>`,`${i.image?`<img class="cart-thumbnail" src="${esc(i.image)}" alt="${esc(i.title)}">`:''}<h3>${esc(i.title)}</h3><p>Line total ${money(i.price_cents*i.quantity/100)}</p>`)}return html};
render();
const customerProduct=product;
product=function(id){let html=customerProduct(id);const p=state.products.find(p=>p.id===id);if(account?.role==='admin'&&p?.configurator){const {discounts,max_quantity}=p.configurator,materials=p.configurator.pricing_materials||p.configurator.materials;html+=layout(`<details class="panel"><summary>Administrator pricing rules</summary><p>Material factors use basis points: 10000 keeps the stored base price. Discounts also use basis points. Enable only materials your fulfillment partners support.</p><form id="pricing-editor" data-id="${id.slice(4)}"><label>Product pricing rules<textarea name="rules" rows="8">${esc(JSON.stringify({materials,discounts,max_quantity},null,2))}</textarea></label><button class="secondary">Save pricing rules</button><p role="alert" id="pricing-error"></p></form></details>`)}return html};
const configuredRender=render;
render=function(){configuredRender();const f=$('#pricing-editor');if(f)f.onsubmit=async e=>{e.preventDefault();try{const p=await api(`/listings/${f.dataset.id}/pricing`,{method:'PUT',body:f.elements.rules.value});state.products=state.products.filter(x=>x.id!=='api-'+p.id);state.products.push(asProduct(p));render();toast('Pricing rules saved')}catch(e){$('#pricing-error').textContent=e.message}}};
const configuredOperations=renderOperations;
let cartRequest=0;
renderOperations=async function(route){if(route!=='basket')return configuredOperations(route);const request=++cartRequest;$('#app').innerHTML=layout('<p role="status">Validating cart prices…</p>');try{const quotes=await Promise.all(opsCart.map(i=>obtainQuote(i.id,{material:i.material,color:i.color||'',quantity:i.quantity})));if(request!==cartRequest||location.hash!=='#basket')return;quotes.forEach((q,n)=>{opsCart[n].price_cents=q.unit_price_cents;opsCart[n].material=q.material});saveOpsCart();return configuredOperations(route)}catch(e){if(location.hash!=='#basket')return;await configuredOperations(route);$('#order-error').textContent=e.message;$('#order-form button').disabled=true}};
