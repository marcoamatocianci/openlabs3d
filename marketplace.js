/* Persistent marketplace. The original host, cart and order simulations remain local demos. */
let account = null, csrf = '', marketplacePage = 1, editListing = null, catalogueRequest = 0, authChecked = false;
const originalRender = render, originalCard = card, originalProduct = product, originalFilter = filter;
async function api(path, options={}) {
  const headers = {...options.headers};
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type']='application/json';
  if (csrf) headers['X-CSRF-Token']=csrf;
  const res=await fetch('/api'+path,{credentials:'same-origin',...options,headers});
  if (!res.ok) {
    const data=await res.json().catch(()=>({}));
    // Structured conflicts (e.g. price changes) carry a message plus details for the page.
    let message=typeof data.detail==='string'?data.detail:data.detail?.message||'Please check the form fields.';
    if (path==='/auth/login' && res.status===429) {
      const seconds=Number(res.headers.get('Retry-After'));
      message += seconds > 0 ? ` Try again in ${Math.ceil(seconds / 60)} minute${seconds > 60 ? 's' : ''}.` : ' Please try again later.';
    }
    throw Object.assign(new Error(message),{status:res.status,detail:data.detail});
  }
  return res.json();
}
function showError(e) { toast(e.message || 'Unable to contact the server'); }
function asProduct(p) { return {api:true,id:'api-'+p.id,name:p.title,category:p.category,price:p.price_cents/100,compat:p.compatibility,dimensions:p.dimensions,color:'teal',source:p.listing_type,state:'approved',designer:p.seller,materials:[p.material],lead:'to be confirmed',tolerance:'Not specified',inspection:'Contact the seller for details.',description:p.description,width:parseInt(p.dimensions)||0,permission:'contact the seller',images:p.images, configurator:p.configurator,colorImages:p.color_images||{},featured:p.featured}; }
function mergeProducts(items) { state.products=[]; state.products.push(...items.map(asProduct)); }
async function refreshPublic() { try { const data=await api('/listings?per_page=50'); mergeProducts(data.items); } catch(e) { console.warn('Catalogue unavailable',e); } }
card = function(p) {
  if (!p.api) return originalCard(p);
  let html=originalCard(p);
  if(p.images.length) html=html.replace(art(p), `<img class="listing-card-image" src="${esc(p.images[0].thumbnail_url)}" alt="${esc(p.name)}">`);
  if (!p.configurator) return html;
  const id=Number(p.id.slice(4));
  html=html.replace(`<a class="card" href="#product/${p.id}">`,`<article class="card">`)
    .replace('</div></a>',`<div class="card-actions"><button type="button" class="purchase-button purchase-button-primary" data-card-add="${id}" onclick="quickAddCard(${id},this)"><span class="purchase-icon">${icon('cart')}</span><span>Add to Cart</span></button><button type="button" class="purchase-button purchase-button-secondary" onclick="quickBuyCard(${id},this)">Buy Now</button><a class="purchase-details" href="#product/${p.id}">View details</a></div></div></article>`);
  return html;
};
function cardConfiguration(id) {
  const p=state.products.find(x=>x.id==='api-'+id), config=p?.configurator;
  if(!config) throw Error('This listing needs more setup before it can be purchased.');
  return {listing_id:id,material:Object.keys(config.materials)[0],color:Object.keys(config.colors)[0]||'',quantity:1};
}
function setCardButton(button,busy,label) {
  if(!button) return;
  button.disabled=busy;
  button.classList.toggle('is-loading',busy);
  const text=button.querySelector('span:last-child');
  if(text) text.textContent=label; else button.textContent=label;
}
async function quickAddCard(id,button) {
  if(button.disabled)return;
  if(!account){toast('Sign in to use your persistent basket');location.hash='account';return;}
  setCardButton(button,true,'Adding…');
  try { await accountAction('/cart',{...cardConfiguration(id),expected_unit_price_cents:typeof cardShownPrice==='function'?cardShownPrice(id):undefined},'POST');await refreshCart();setCardButton(button,false,'Added!');button.classList.add('is-added');setTimeout(()=>{if(button.isConnected){setCardButton(button,false,'Add to Cart');button.classList.remove('is-added')}},1600); }
  catch(e){setCardButton(button,false,'Add to Cart');showError(e);}
}
async function quickBuyCard(id,button) {
  if(button.disabled)return;
  setCardButton(button,true,'Preparing…');
  try { const line=cardConfiguration(id);await obtainQuote(id,line);sessionStorage.setItem('ol3d-direct',JSON.stringify({line,owner:account?.id??null,key:uid()}));location.hash=account?'checkout':'account';if(!account)toast('Sign in to continue your purchase'); }
  catch(e){setCardButton(button,false,'Buy Now');showError(e);}
}
const originalHome = home;
home = function() {
  return originalHome()
    .replace('Discover practical tools for your lab, choose your specifications, and connect with a qualified 3D-printing host.', 'Browse laboratory accessories from the community, or create a listing for review. Printing host and checkout workflows are currently demonstrations.')
    .replace('Sample catalogue · All product images are illustrative renders. Prices and specifications are for demonstration.', 'Sample tools use illustrative renders and demo prices. Published listings may also appear here with seller-supplied details.')
    .replace('An eligible printing host accepts your complete order and starts manufacturing.', 'Explore the demonstration host workspace; real manufacturing orders are not yet connected.')
    .replace('Follow quality checks and shipping from one clear order timeline.', 'Review the simulated order timeline. Shipping and payment are not connected.');
};
product = function(id) { const p=state.products.find(x=>x.id===id); let html=originalProduct(id); if(p?.api) { if(p.images.length) html=html.replace(art(p,true),`<img id="gallery-main" class="listing-main-image" src="${esc(p.images[0].url)}" alt="${esc(p.name)}">`).replace('<p class="muted">Illustrative render · Sample design · Geometry may differ from manufacture</p>',`<div class="gallery">${p.images.map(i=>`<button type="button" onclick="document.querySelector('#gallery-main').src=this.dataset.src" data-src="${esc(i.url)}"><img src="${esc(i.thumbnail_url)}" alt="View product photograph"></button>`).join('')}</div>`); html=html.replace('per unit · sample final price','per unit').replace('Estimated manufacture:','Estimated manufacture:'); } return html; };
const productWithGallery = product;
product = function(id) {
  const p=state.products.find(x=>x.id===id), html=productWithGallery(id);
  if (!p?.api) return html;
  return html.replace('Add to basket →','Add to demo basket →')
    .replace('Estimated manufacture: to be confirmed after host acceptance. Shipping estimate: 2–5 business days in Italy. Neither estimate is a confirmed delivery commitment.', 'This basket and checkout are demonstrations. Real orders, host matching, delivery and payment are not connected.')
    .replace('No cleaning protocol has been reviewed for this sample design.', 'No cleaning protocol has been verified by OpenLabs3D for this listing.');
};
filter = async function(keepPage=false) {
  if (!$('#filters')) return;
  if (!keepPage) marketplacePage=1;
  const request=++catalogueRequest, f=new FormData($('#filters')), q=new URLSearchParams({q:f.get('q')||'',category:f.get('category')||'',sort:f.get('sort')||'newest',page:String(marketplacePage),per_page:'12'});
  if (f.get('material')) q.set('material',f.get('material'));
  if (f.get('max')) q.set('max_price_cents',f.get('max'));
  $('#results').innerHTML='<p role="status">Loading published listings…</p>';
  try {
    const data=await api('/listings?'+q); const products=data.items.map(asProduct);
    if(request!==catalogueRequest || !$('#results')) return;
    // Keep server listings in memory for detail and the demonstration basket only.
    for (const p of products) { const i=state.products.findIndex(x=>x.id===p.id); if(i<0) state.products.push(p); else state.products[i]=p; }
    const match=p=>(!f.get('material')||p.materials.includes(f.get('material')))&&(!f.get('max')||p.price*100<=+f.get('max'));
    const samples=state.products.filter(p=>!p.api&&p.state==='approved'&&(!f.get('category')||p.category===f.get('category'))&&(p.name+' '+p.compat).toLowerCase().includes((f.get('q')||'').toLowerCase())&&match(p));
    if (!$('#results')) return;
    $('#results').innerHTML=products.map(card).join('') || `<div class="cf-empty">${emptyState('No products match these filters','Try a higher maximum price, another material or category, or clear the filters.','<button type="button" class="btn btn-sm" data-cf-clear>Clear filters</button>')}</div>`;
    $('#marketplace-pages').innerHTML=`<button class="secondary" ${marketplacePage<=1?'disabled':''} onclick="marketplacePage--;filter(true)">Previous</button> <span>Page ${marketplacePage} · ${data.total} matching published listings</span> <button class="secondary" ${marketplacePage*data.per_page>=data.total?'disabled':''} onclick="marketplacePage++;filter(true)">Next</button>`;

  } catch(e) { if(request!==catalogueRequest || !$('#results')) return; $('#results').innerHTML='<p>Marketplace unavailable. Please try again later.</p>'; showError(e); }
};
function accountPage() { if(account) return layout(head('Your account','OpenLabs3D')+`<div class="panel"><h2>${esc(account.display_name)}</h2><p>${esc(account.email)} · ${esc(account.role)}</p><a class="btn" href="#my-listings">Manage listings</a> <button class="secondary" onclick="logout()">Sign out</button></div>`); return layout(head('Welcome to OpenLabs3D','Your account')+`<div class="two-col"><form id="real-login" class="panel"><h2>Sign in</h2><label>Email<input name="email" type="email" required autocomplete="email"></label><label>Password<input name="password" type="password" required autocomplete="current-password"></label><button class="primary">Sign in</button></form><form id="real-register" class="panel"><h2>Create an account</h2><label>Display name<input name="display_name" required maxlength="100"></label><label>Email<input name="email" type="email" required autocomplete="email"></label><label>Password (at least 12 characters)<input name="password" type="password" minlength="12" maxlength="128" required autocomplete="new-password"></label><button class="primary">Register</button></form></div>`); }
async function logout(){ try { await api('/auth/logout',{method:'POST'}); account=null;csrf='';updateAccount();location.hash='account';render(); } catch(e){showError(e);} }
// Extended by later modules (theme, basket, navigation).
function updateAccount(){}
const statusLabel=s=>({draft:'Draft',pending:'Pending approval',approved:'Published',rejected:'Rejected',archived:'Archived'}[s]||s);
function listingEditor(p={}) { if(!p.id&&account?.role==='admin')p={...p,listing_type:'official'}; const images=p.images||[]; return listingPage(p.id?'Edit listing':account?.role==='admin'?'New official product':'New listing',`<form id="listing-form" class="panel" data-id="${p.id||''}"><div class="fields"><label>Product name<input name="title" maxlength="160" value="${esc(p.title||'')}"></label><label>Category<select name="category"><option value="">Choose a category</option>${categories.map(c=>`<option ${p.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label><label>Price (€)<input name="price" type="number" min="0" max="1000000" step="0.01" value="${p.price_cents?p.price_cents/100:''}"></label><label>Material<input name="material" maxlength="200" value="${esc(p.material||'')}"></label><label>Dimensions<input name="dimensions" maxlength="200" value="${esc(p.dimensions||'')}"></label><label>Compatibility<input name="compatibility" maxlength="300" value="${esc(p.compatibility||'')}"></label></div><label>Description<textarea name="description" maxlength="10000">${esc(p.description||'')}</textarea></label>${account?.role==='admin'?`<label>Listing type<select name="listing_type"><option value="community" ${p.listing_type!=='official'?'selected':''}>Community</option><option value="official" ${p.listing_type==='official'?'selected':''}>Official</option></select></label><label><input type="checkbox" name="featured" ${p.featured?'checked':''}> Featured on homepage</label>`:''}<label>Product photographs (JPEG, PNG, WebP; up to 5, 5 MB each)<input id="listing-files" type="file" accept="image/jpeg,image/png,image/webp" multiple></label><div id="previews" class="gallery"></div><p class="muted">Save a draft first to manage and reorder existing photographs. Changing a published listing sends it back for review.</p><div class="gallery">${images.map((i,n)=>`<div><img src="${esc(i.thumbnail_url)}" alt="Listing photograph"><br><button type="button" onclick="removePhoto(${p.id},${i.id})">Remove</button> ${n?`<button type="button" onclick="movePhoto(${p.id},${n},-1)">←</button>`:''} ${n<images.length-1?`<button type="button" onclick="movePhoto(${p.id},${n},1)">→</button>`:''}</div>`).join('')}</div><p id="listing-error" role="alert"></p><button class="primary" name="action" value="save">Save draft / changes</button> <button class="secondary" name="action" value="submit">${account?.role==='admin'?'Publish Product':'Submit for Approval'}</button></form>`); }
function listingPage(title, body) { return layout(head(title,'Your products')+body); }
async function removePhoto(id,image){try{await api(`/listings/${id}/images/${image}`,{method:'DELETE'});editListing=await api('/listings/'+id);render();}catch(e){showError(e)}}
async function movePhoto(id,index,step){try{let ids=editListing.images.map(i=>i.id);[ids[index],ids[index+step]]=[ids[index+step],ids[index]];editListing=await api(`/listings/${id}/images/order`,{method:'PUT',body:JSON.stringify({image_ids:ids})});render();}catch(e){showError(e)}}
async function archiveListing(id){if(!confirm('Archive this listing?'))return;try{await api('/listings/'+id,{method:'DELETE'});render();}catch(e){showError(e)}}
async function moderateListing(id,action){let reason='';if(action==='reject'){reason=prompt('Reason for rejection (optional):');if(reason===null)return;}if(!confirm(`${action==='approve'?'Approve':'Reject'} this listing?`))return;try{const body=action==='reject'?JSON.stringify({reason}):undefined;await api(`/admin/listings/${id}/${action}`,{method:'POST',body});render();toast('Listing updated');}catch(e){showError(e)}}
function rows(items, adminView=false){return items.map(p=>`<div class="panel"><div class="row"><div><h3>${esc(p.title||'Untitled draft')}</h3><span class="status">${esc(statusLabel(p.status))}</span><p>${esc(p.seller)} · ${esc(p.category)} · ${money(p.price_cents/100)} · ${esc(p.listing_type)}</p><p>${esc(p.description)}</p><p>${esc(p.material)} · ${esc(p.dimensions)} · ${esc(p.compatibility)}</p>${p.rejection_reason?`<p>Review: ${esc(p.rejection_reason)}</p>`:''}<div class="gallery">${p.images.map(i=>`<a href="${esc(i.url)}" target="_blank" rel="noopener"><img src="${esc(i.thumbnail_url)}" alt="Listing photograph"></a>`).join('')}</div></div><div>${!adminView&&p.status!=='archived'?`<a class="btn light" href="#edit-listing/${p.id}">Edit</a> <button onclick="archiveListing(${p.id})">Archive</button>`:''}${adminView&&p.status==='pending'?`<button onclick="moderateListing(${p.id},'approve')">Approve</button> <button onclick="moderateListing(${p.id},'reject')">Reject</button>`:''}${adminView&&p.status!=='archived'?`<button onclick="archiveListing(${p.id})">Archive</button>`:''}</div></div></div>`).join('')||'<p>No listings yet.</p>';}
async function renderMarketplace(route){
  if(route==='account') {$('#app').innerHTML=accountPage(); bindMarketplace(); return;}
  if(!account) {$('#app').innerHTML=layout(empty('Sign in to continue','Create an account or sign in to manage listings.','#account','Account'));return;}
  if(route==='my-listings'){try{let items=await api('/listings/mine');if(location.hash!=='#my-listings')return;$('#app').innerHTML=layout(head('Your listings','Your workspace','<a class="btn" href="#create-listing">+ Create listing</a>')+rows(items));}catch(e){showError(e)}return;}
  if(route==='moderation'){if(account.role!=='admin'){$('#app').innerHTML=layout(empty('Administrator access required','Only administrators can moderate listings.'));return}try{let items=await api('/admin/listings');if(location.hash!=='#moderation')return;$('#app').innerHTML=layout(head('Marketplace operations','Administrator workspace','<a class="btn" href="#create-listing">+ Create official listing</a>')+rows(items,true));}catch(e){showError(e)}return;}
  if(route==='create-listing'){editListing=null;$('#app').innerHTML=listingEditor();bindMarketplace();return;}
  if(route.startsWith('edit-listing/')){try{let p=await api('/listings/'+route.split('/')[1]);if(location.hash!=='#'+route)return; editListing=p;$('#app').innerHTML=listingEditor(p);bindMarketplace();}catch(e){showError(e)}return;}
}
function bindMarketplace(){
  for(const id of ['real-login','real-register']) {let form=$('#'+id);if(form) form.onsubmit=async e=>{e.preventDefault();try{let data=await api('/auth/'+(id==='real-login'?'login':'register'),{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});account=data.user;csrf=data.csrf_token;updateAccount();const destination=sessionStorage.getItem('ol3d-after-login'),back=sessionStorage.getItem('ol3d-return-to');sessionStorage.removeItem('ol3d-after-login');sessionStorage.removeItem('ol3d-return-to');location.hash=destination||back||(account.role==='admin'?'admin':account.role==='host'?'host':'catalogue');render();if(data.verification_delivery)toast(data.verification_delivery);}catch(err){showError(err)}};}
  const files=$('#listing-files'); if(files)files.onchange=()=>{const div=$('#previews');div.innerHTML='';Array.from(files.files).forEach(file=>{let img=document.createElement('img');let url=URL.createObjectURL(file);img.src=url;img.alt='New photograph preview';img.onload=()=>URL.revokeObjectURL(url);div.appendChild(img)});};
  let form=$('#listing-form');if(form)form.onsubmit=async e=>{e.preventDefault(); const error=$('#listing-error');try{const d=Object.fromEntries(new FormData(form));if(e.submitter.value==='submit'&&account?.role==='admin'&&d.listing_type==='official'&&!await confirmOfficial())return;const price=Number(d.price||0);if(!Number.isFinite(price)||price<0)throw Error('Enter a valid price.');let payload={title:d.title,description:d.description,category:d.category,price_cents:Math.round(price*100),material:d.material,dimensions:d.dimensions,compatibility:d.compatibility};if(d.listing_type)payload.listing_type=d.listing_type;if(account?.role==='admin')payload.featured=!!d.featured;let id=form.dataset.id;let p=await api(id?'/listings/'+id:'/listings',{method:id?'PATCH':'POST',body:JSON.stringify(payload)});form.dataset.id=p.id;const chosenMaterials=[...form.querySelectorAll('[data-listing-material]:checked')].map(el=>el.value);if(chosenMaterials.length){p=await api(`/listings/${p.id}/pricing`,{method:'PUT',body:JSON.stringify({materials:Object.fromEntries(chosenMaterials.map(m=>[m,p.configurator?.pricing_materials?.[m]||p.configurator?.materials?.[m]||10000])),discounts:p.configurator?.discounts||{},max_quantity:p.configurator?.max_quantity||50})});}const chosen=Array.from(files.files);if(chosen.length){let data=new FormData();chosen.forEach(f=>data.append('files',f));await api(`/listings/${p.id}/images`,{method:'POST',body:data});files.value='';}const cadFile=document.querySelector('#listing-cad')?.files[0];if(cadFile){const cadData=new FormData();cadData.append('file',cadFile);const inspection=await api(`/listings/${p.id}/cad`,{method:'POST',body:cadData});toast(inspection.warning);}if(e.submitter.value==='submit'&&(account?.role==='admin'&&d.listing_type==='official'||['draft','rejected'].includes(p.status)))p=await api(`/listings/${p.id}/${account?.role==='admin'&&d.listing_type==='official'?'publish':'submit'}`,{method:'POST'});await refreshPublic();toast(p.status==='approved'?'Product published successfully':'Listing saved');location.hash=account?.role==='admin'?'admin/products':'my-listings';render();}catch(err){error.textContent=err.message;}}
}
render = function(){const route=(location.hash||'#home').slice(1).split('?')[0];if(['account','my-listings','moderation','create-listing'].includes(route)||route.startsWith('edit-listing/')){renderMarketplace(route);return;}if(route==='admin')return;/* The admin workspace (workspaces.js) owns this route; if sign-in finishes before it loads, the final render() draws it. */if(route==='design'){location.hash=account?'create-listing':'account';return;}originalRender();if(route==='catalogue') {initCatalogueFilters();$('#results').insertAdjacentHTML('afterend','<div id="marketplace-pages" class="pagination"></div>');filter();}if(route.startsWith('product/api-')&&!state.products.some(p=>p.id===route.split('/')[1])){let id=route.split('/')[1].slice(4);api('/listings/'+id).then(p=>{state.products.push(asProduct(p));if(location.hash==='#'+route)render()}).catch(()=>{});} };
(async()=>{try{const data=await api('/auth/me');account=data.user;csrf=data.csrf_token}catch(e){}authChecked=true;updateAccount();await refreshPublic();render()})();
