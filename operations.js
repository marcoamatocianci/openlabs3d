/* Server-backed host applications, order requests and administration. */
const marketplaceRender = render;
const marketplaceProduct = product;
const marketplaceHome = home;
const opsCartKey = 'openlabs3d-cart-v2';
let opsCart = [];
let publicSettings = {marketplace_name:'OpenLabs3D',contact:''};
const saveOpsCart = () => { const count=opsCart.reduce((n,i)=>n+i.quantity,0), badge=$('#count'); if(badge){badge.textContent=count;badge.hidden=!count;} };
function deliveryText(value){try{const data=JSON.parse(value);return ['first_name','last_name','email','phone','street','additional','postal_code','city','region','country'].map(k=>data[k]).filter(Boolean).join(', ')}catch(e){return value}}
const safeDate = value => value ? parseServerDate(value).toLocaleString() : '—';
const badge = value => statusBadge(value);
const panelMessage = (title, text, href='#account', label='Sign in') => layout(empty(title,text,href,label));

home = function() { return marketplaceHome().replace('Browse laboratory accessories from the community, or create a listing for review. Printing host and checkout workflows are currently demonstrations.','Browse laboratory accessories from the community, create a listing for review, or apply to print products for customers.').replace('Explore the demonstration host workspace; real manufacturing orders are not yet connected.','Approved hosts can accept matching printing jobs and report their progress.').replace('Review the simulated order timeline. Shipping and payment are not connected.','Follow your order request as work progresses. Payment and shipping are arranged separately.').replace('Request a custom tool ↗','Try a custom request demo ↗'); };
about = function() { return layout(head('How OpenLabs3D works','Marketplace information')+`<div class="panel"><h2>Order requests and printing jobs</h2><p>Published listings can be added to a basket and submitted as order requests. Approved hosts may accept jobs matching their listed materials and update their progress. Orders, applications and listings are stored by this self-hosted installation.</p><p>Payments, shipping integrations, notifications and medical or sterility verification are not provided. Agree on payment and delivery outside the application.</p><h2>Sample tools and prototypes</h2><p>The sample catalogue and custom-request demo remain separate from published products. Sample orders and attachments are stored only in this browser and are not sent to a host.</p><a class="btn light" href="#demo-basket">View sample basket</a> <a class="btn light" href="#custom">Try the custom request demo</a></div>`); };

product = function(id) {
  const p=state.products.find(item=>item.id===id);
  let html=marketplaceProduct(id);
  if (p?.api) return html.replace('id="configure"','id="real-configure"').replace(/<label>Variant<select name="variant">.*?<\/select><\/label>/,'').replace('Add to demo basket →','Add to basket →').replace('This basket and checkout are demonstrations. Real orders, host matching, delivery and payment are not connected.','Submit an order request to an approved host. No payment or shipping integration is connected.');
  if (p) html=html.replace('Add to basket →','Add to sample basket →').replace('</form><div class="notice">','</form><p><a class="textlink" href="#demo-basket">View sample basket</a></p><div class="notice">');
  return html;
};

const orderSteps=['pending','accepted','printing','ready','shipped','completed'], stepLabels={pending:'Requested',accepted:'Accepted',printing:'Printing',ready:'Ready',shipped:'Shipped',completed:'Completed'};
function orderCards(orders) {
  if(!orders.length) return `<div class="list">${emptyState('No orders yet','Order requests you submit appear here with their printing progress.','<a class="btn btn-sm" href="#catalogue">Explore products</a>')}</div>`;
  return `<div class="order-list">${orders.map(o=>{const reached=orderSteps.indexOf(o.status);return `<article class="section-card order-card"><header class="order-head"><div><span class="order-ref mono">${esc(o.reference)}</span><span class="muted">${safeDate(o.created_at)}</span></div><strong class="order-total">${money(o.total_cents/100)}</strong>${badge(o.status)}</header>${o.status==='cancelled'?'':`<ol class="progress-steps" aria-label="Order progress">${orderSteps.map((s,n)=>`<li class="${n<=reached?'done':''}" ${n===reached?'aria-current="step"':''}>${stepLabels[s]}</li>`).join('')}</ol>`}<ul class="order-items">${o.items.map(i=>`<li><span>${i.quantity} × ${esc(i.title)}</span><span class="muted">${esc([i.material,i.color?colorLabels[i.color]||i.color:''].filter(Boolean).join(' · '))}</span><span>${money(i.price_cents*i.quantity/100)}</span></li>`).join('')}</ul><details class="row-details"><summary>Delivery and history</summary><dl class="detail-grid"><div><dt>Contact</dt><dd>${esc(deliveryText(o.contact))}</dd></div><div><dt>Delivery address</dt><dd>${esc(deliveryText(o.address))}</dd></div><div><dt>History</dt><dd>${o.history.map(e=>`${esc(safeDate(e.created_at))} · ${esc(e.action)}`).join('<br>')||'No events yet.'}</dd></div></dl></details></article>`}).join('')}</div>`;
}
function cartPage() {
  const total=opsCart.reduce((n,i)=>n+i.price_cents*i.quantity,0);
  if (!opsCart.length) return layout(head('Your basket','Order request')+empty('Your basket is empty','Browse published listings to start an order request.'));
  return layout(head('Your basket','Order request')+`<div class="two-col"><div class="panel">${opsCart.map((i,index)=>`<div class="row"><div><h3>${esc(i.title)}</h3><p>${esc(i.material)} · ${esc(i.color||'')} · ${money(i.price_cents/100)} each</p></div><label>Quantity<input type="number" min="1" max="50" value="${i.quantity}" aria-label="Quantity for ${esc(i.title)}" onchange="changeCart(${index},this.value)"></label><button class="secondary" onclick="removeCart(${index})">Remove</button></div>`).join('')}</div><form id="order-form" class="panel"><h2>Order request</h2><p>Estimated total <strong>${money(total/100)}</strong></p><p>Prices and availability are checked when you submit. No payment is collected; delivery and shipping are not integrated. Your contact and address are shared with assigned hosts.</p><label>Name and contact (email or phone)<input name="contact" maxlength="200" required></label><label>Delivery address<textarea name="address" maxlength="1000" required></textarea></label><button class="primary">Submit order request</button><p id="order-error" role="alert"></p></form></div><p><a class="textlink" href="#demo-basket">Open the separate sample basket</a></p>`);
}
function changeCart(id,value) { const item=opsCart[id], quantity=Number(value); if(!Number.isInteger(quantity)||quantity<1||quantity>50){toast('Choose a quantity from 1 to 50');render();return} item.quantity=quantity;saveOpsCart();render(); }
function removeCart(id) { opsCart.splice(id,1);saveOpsCart();render(); }
function addRealProduct(form) {
  const p=state.products.find(item=>item.id===form.dataset.id), qty=Number(new FormData(form).get('quantity'));
  if (!p || !Number.isInteger(qty) || qty<1 || qty>50) return toast('Choose a quantity from 1 to 50');
  const id=Number(p.id.slice(4)), color=new FormData(form).get('colour')||'', existing=opsCart.find(i=>i.id===id&&(i.color||'')===color);
  if(existing && existing.quantity+qty>50) return toast('Maximum 50 of each product per order');
  if(existing) existing.quantity+=qty; else opsCart.push({id,color,title:p.name,material:p.materials[0],price_cents:Math.round(p.price*100),quantity:qty});
  saveOpsCart();toast('Added to basket');
}
function hostForm(host) {
  const fields=[['name','Name or company'],['contact','Contact information'],['country','Country'],['region','City or service area'],['printers','Printer models'],['technologies','Printing technologies'],['materials','Supported materials, separated by commas'],['dimensions','Maximum printable dimensions']];
  if(host && !['draft','rejected'].includes(host.status)) return layout(head('Printing host application','Your workspace')+`<div class="panel"><h2>${esc(host.name)}</h2>${badge(host.status)}<p>${esc(host.region)}, ${esc(host.country)} · ${esc(host.materials)}</p>${host.status==='approved'?'<a class="btn" href="#host">Open host dashboard</a>':''}</div>`);
  return layout(head('Apply as a printing host','Your workspace')+`<form id="host-application" class="panel"><p>Tell us about your equipment and where you can provide service. Applications require administrator review.</p>${host?.rejection_reason?`<div class="notice">Review: ${esc(host.rejection_reason)}</div>`:''}<div class="fields">${fields.map(([name,label])=>`<label>${label}<input name="${name}" value="${esc(host?.[name]||'')}" maxlength="${name==='printers'?1000:200}"></label>`).join('')}</div><label>Production capabilities<textarea name="capabilities" maxlength="3000">${esc(host?.capabilities||'')}</textarea></label><label>Additional information<textarea name="additional" maxlength="3000">${esc(host?.additional||'')}</textarea></label><p id="host-error" role="alert"></p><button class="secondary" name="action" value="draft">Save draft</button> <button class="primary" name="action" value="submit">Submit application</button></form>`);
}
const jobQuestions={accept:'Accept this printing job? Agree payment and delivery with the buyer before printing.',printing:'Start printing this job?',ready:'Mark this job as ready for the buyer?',completed:'Mark this job as completed?'};
async function jobAction(id,action) { if(!confirm(jobQuestions[action])) return;try{await api(`/host/jobs/${id}/${action==='accept'?'accept':'status'}`,{method:'POST',...(action==='accept'?{}:{body:JSON.stringify({status:action})})});toast(action==='accept'?'Job accepted':'Job updated');render()}catch(e){showError(e)} }
async function adminAction(path,message,body) { if(!confirm(message))return;try{await api(path,{method:'POST',...(body?{body:JSON.stringify(body)}:{})});toast('Saved');render()}catch(e){showError(e)} }
function rejectHost(id) { const reason=prompt('Optional reason for rejection:');if(reason!==null)adminAction(`/admin/hosts/${id}/reject`,'Reject this application?',{reason}); }
async function renderOperations(route) {
  if(route==='basket'){ $('#app').innerHTML=cartPage();bindOperations();return; }
  if(route==='demo-basket'){ $('#app').innerHTML=basket();bind();return; }
  if(!account){$('#app').innerHTML=panelMessage('Sign in to continue','Sign in or register to use this workspace.');return;}
  if(route.startsWith('admin')&&account.role!=='admin'){$('#app').innerHTML=panelMessage('Administrator access required','Only administrators can use this workspace.','#home','Return home');return;}
  $('#app').innerHTML=layout('<div class="panel" role="status">Loading…</div>');
  try {
    let html='';
    if(route==='onboarding') html=hostForm(await api('/host/application'));
    else if(route==='orders') html=layout(head('My orders','Your order requests')+orderCards(await api('/orders')));
    if ((location.hash||'#home').slice(1).split('?')[0]!==route) return;
    $('#app').innerHTML=html;bindOperations();
  } catch(e){if((location.hash||'#home').slice(1).split('?')[0]===route)$('#app').innerHTML=layout(`<div class="panel" role="alert"><h2>Unable to load this page</h2><p>${esc(e.message)}</p><button class="secondary" onclick="render()">Try again</button></div>`);}
}
function bindOperations() {
  const profile=$('#profile-form');if(profile)profile.onsubmit=async e=>{e.preventDefault();try{account=await api('/profile',{method:'PATCH',body:JSON.stringify(Object.fromEntries(new FormData(profile)))});toast('Profile saved');render()}catch(err){showError(err)}};
  for(const form of document.querySelectorAll('.delete-account-form')) form.onsubmit=async e=>{e.preventDefault();if(!confirm('Permanently delete this account? This cannot be undone.'))return;const self=form.dataset.self==='true', button=form.querySelector('button');button.disabled=true;try{await api(self?'/profile':`/admin/users/${form.dataset.id}`,{method:'DELETE',body:JSON.stringify({password:new FormData(form).get('password')})});if(self){account=null;csrf='';updateAccount();location.hash='account'}toast('Account deleted');render()}catch(err){form.querySelector('.delete-account-error').textContent=err.message;button.disabled=false}};
  const configure=$('#real-configure');if(configure)configure.onsubmit=e=>{e.preventDefault();addRealProduct(configure)};
  const application=$('#host-application');if(application)application.onsubmit=async e=>{e.preventDefault();try{const body=Object.fromEntries(new FormData(application));body.submit=e.submitter.value==='submit';await api('/host/application',{method:'PUT',body:JSON.stringify(body)});toast(body.submit?'Application submitted':'Draft saved');render()}catch(err){$('#host-error').textContent=err.message}};
  const order=$('#order-form');if(order)order.onsubmit=async e=>{e.preventDefault();if(!account){location.hash='account';return}const button=order.querySelector('button');button.disabled=true;try{let key=sessionStorage.getItem('ol3d-order-key');if(!key){key=uid();sessionStorage.setItem('ol3d-order-key',key)}const fields=Object.fromEntries(new FormData(order));await api('/orders',{method:'POST',body:JSON.stringify({...fields,idempotency_key:key,items:opsCart.map(i=>({listing_id:i.id,material:i.material,color:i.color||'',quantity:i.quantity,expected_price_cents:i.price_cents}))})});opsCart=[];saveOpsCart();sessionStorage.removeItem('ol3d-order-key');toast('Order request submitted');location.hash='orders';render()}catch(err){$('#order-error').textContent=err.message;button.disabled=false}};
  for(const form of document.querySelectorAll('#category-form,.category-edit')) form.onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(form));try{await api('/admin/categories/'+(form.dataset.id||0),{method:'PUT',body:JSON.stringify({name:d.name,sort_order:Number(d.sort_order),active:d.active!=='false'})});await refreshCategories();toast('Category saved');render()}catch(err){showError(err)}};
  const settings=$('#settings-form');if(settings)settings.onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(settings));d.host_applications_open=d.host_applications_open==='true';try{await api('/admin/settings',{method:'PUT',body:JSON.stringify(d)});await refreshPublicSettings();toast('Settings saved');render()}catch(err){showError(err)}};
}
async function refreshCategories(){try{const data=await api('/categories');categories.splice(0,categories.length,...data.map(c=>c.name))}catch(e){console.warn('Categories unavailable',e)}}
async function refreshPublicSettings(){try{publicSettings=await api('/settings');renderNavbar();$('.footername').textContent=publicSettings.marketplace_name;let contact=$('#public-contact');if(!contact){contact=document.createElement('p');contact.id='public-contact';document.querySelector('footer').appendChild(contact)}contact.textContent=publicSettings.contact?'Contact: '+publicSettings.contact:''}catch(e){console.warn('Settings unavailable',e)}}
render = function() {
  const route=(location.hash||'#home').slice(1).split('?')[0];
  if(['basket','demo-basket','orders','onboarding'].includes(route)){renderOperations(route);saveOpsCart();return;}
  marketplaceRender();saveOpsCart();$('.footername').textContent=publicSettings.marketplace_name;
  if(route==='account' || route.startsWith('product/')) bindOperations();
};
refreshCategories().then(()=>{if((location.hash||'#home').startsWith('#home')||(location.hash||'').startsWith('#catalogue'))render()});
refreshPublicSettings();
