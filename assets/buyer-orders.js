/* Buyer order presentation. All commercial details come from persisted order snapshots. */
const buyerOrdersRenderOperations = renderOperations;
let buyerOrdersRequest = 0, buyerOrdersShown = null;
// Filters, sort and pages change only the hash query: keep the scroll position (see app.js).
inPageRoutes.add('#orders');
const buyerOrderLabels = {pending:'Awaiting host acceptance',accepted:'Accepted · awaiting printing',printing:'Production in progress',ready:'Ready for delivery',shipped:'Shipped',completed:'Completed',cancelled:'Cancelled',available:'Awaiting host acceptance'};
const buyerOrderTone = {pending:'warning',accepted:'warning',printing:'info',ready:'info',shipped:'info',completed:'success',cancelled:'danger',available:'warning'};
const buyerOrderBadge = status => `<span class="status status-${buyerOrderTone[status] || 'neutral'}">${esc(buyerOrderLabels[status] || 'Status unavailable')}</span>`;
const buyerOrderDate = value => parseServerDate(value).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'});
const buyerOrderMoney = (cents,currency) => new Intl.NumberFormat(undefined,{style:'currency',currency}).format(cents/100);
// My Orders shows Current orders by default (scope=active) and Previous orders on request (scope=history).
// The address holds the view (scope, status group, search, page, sort), so Back and Forward restore it;
// only the sort order is remembered for the session.
const buyerOrderHref = (filters, params={}) => '#' + scopeHref('orders', {scope:filters.scope, group:filters.group, q:filters.q, sort:filters.sort === 'newest' ? '' : filters.sort}, params);
function buyerOrderFilters() {
  let saved={};try{saved=JSON.parse(sessionStorage.getItem('ol3d-orders-'+account.id)||'{}')}catch(e){}
  const params=new URLSearchParams(location.hash.split('?')[1]||''), sort=params.get('sort')||saved.sort||'newest';
  return {scope:params.get('scope')==='history'?'history':'active', group:params.get('group')||'all', q:(params.get('q')||'').slice(0,80), sort:sort==='oldest'?'oldest':'newest', page:Math.max(1,parseInt(params.get('page')||'1',10)||1)};
}
// The purchased configuration comes only from the order line: material, colour name and the colour
// snapshot taken at checkout. Lines from before snapshots existed show their recorded name, no swatch.
const buyerOrderHex = item => /^#[0-9a-f]{6}$/i.test(item.color_hex || '') ? item.color_hex.toLowerCase() : '';
const buyerOrderColor = color => color ? colorTitle(color) : '';
function buyerOrderConfig(item) {
  const hex = buyerOrderHex(item), text = [item.material, buyerOrderColor(item.color)].filter(Boolean).join(' · ');
  return text ? `<span class="bo-config">${hex ? `<span class="bo-swatch" style="--swatch:${hex}" aria-hidden="true"></span>` : ''}${esc(text)}</span>` : '';
}
// The current neutral product render, recoloured in the browser with the purchased filament colour by
// the catalogue's tintProductImage (no new renders). Tinted results are cached per image and colour, so
// switching filters reuses them instead of flashing the grey render again.
function buyerOrderThumb(item) {
  if (!item.thumbnail) return `<span class="row-thumb bo-thumb" role="img" aria-label="Product preview unavailable">${icon('camera')}</span>`;
  const hex = buyerOrderHex(item), cached = hex && tintCache.get(tintKey(item.thumbnail, hex, 160));
  return `<span class="row-thumb bo-thumb"><img ${cached ? 'class="is-ready" ' : ''}src="${esc(cached || item.thumbnail)}" data-source="${esc(item.thumbnail)}" ${hex ? `data-color="${hex}" data-tint-size="160"` : ''} ${cached ? `data-tinted="${hex}"` : ''} alt="" width="640" height="640" loading="lazy" decoding="async" onload="buyerOrderThumbLoaded(this)" onerror="buyerOrderThumbFailed(this)"></span>`;
}
function buyerOrderThumbLoaded(img) {
  if (img.dataset.color && img.dataset.tinted !== img.dataset.color) { tintProductImage(img); if (img.src.startsWith('data:')) return; }
  img.classList.add('is-ready');
}
function buyerOrderThumbFailed(img) {
  const box = img.parentElement; box.setAttribute('role', 'img'); box.setAttribute('aria-label', 'Product preview unavailable'); box.innerHTML = icon('camera');
}
function buyerOrderLine(item,currency,detail=false) {
  return `<li class="bo-product">${buyerOrderThumb(item)}<div class="bo-product-copy"><h3>${esc(item.title)}</h3>${buyerOrderConfig(item)}<span class="bo-meta">Quantity: ${item.quantity}${detail?' · '+buyerOrderMoney(item.price_cents,currency)+' each':''}</span></div><strong class="bo-line-price">${buyerOrderMoney(item.price_cents*item.quantity,currency)}</strong></li>`;
}
const buyerOrderEvents = {'order.created':'Order requested','order.cancelled':'Order cancelled','job.accepted':'A printing host accepted a product','job.printing':'Printing started for a product','job.ready':'A product is ready for delivery','job.shipped':'A product was shipped','job.completed':'A product was received','order.completed':'Order completed','job.reopened':'A product is awaiting a new host'};
// Shipped products: tracking details and the receipt confirmation that completes them.
function buyerOrderShipment(order, job) {
  const s = job.shipment || {}, tracking = s.tracking_url ? `<a class="textlink" href="${esc(s.tracking_url)}" target="_blank" rel="noopener noreferrer">${esc(s.tracking_number)}</a>` : esc(s.tracking_number || '');
  return `<li class="bo-shipment"><div class="bo-shipment-copy"><strong>${esc(job.item.title)}</strong><span class="bo-meta">${esc(s.carrier || 'Carrier not provided')}${tracking ? ' · Tracking ' + tracking : ''}</span>${s.note ? `<span class="bo-meta">${esc(s.note)}</span>` : ''}${s.shipped_at ? `<span class="bo-meta">Shipped ${esc(safeDate(s.shipped_at))}</span>` : ''}</div><button type="button" class="btn btn-sm" data-received="${order.id}:${job.id}">Mark as received</button></li>`;
}
const buyerOrderJson = value => { try { const data = JSON.parse(value); return data && typeof data === 'object' ? data : {}; } catch (e) { return {}; } };
// The address may change until any product of the order has shipped (the server enforces the same rule).
const buyerOrderAddressLocked = order => order.status === 'cancelled' || order.jobs.some(j => ['shipped', 'completed'].includes(j.status));
function buyerOrderContact(order) {
  const c = buyerOrderJson(order.contact), lines = [[c.first_name, c.last_name].filter(Boolean).join(' '), c.email, c.phone].filter(Boolean);
  return `<div class="bo-fact"><h3>Order contact</h3><p>${lines.map(esc).join('<br>') || 'Not provided'}</p></div>`;
}
function buyerOrderAddress(order) {
  const lines = addressLines(buyerOrderJson(order.address)), locked = buyerOrderAddressLocked(order), hint = `bo-address-hint-${order.id}`;
  const reason = order.status === 'cancelled' ? 'Cancelled orders cannot be changed.' : 'The address is fixed once a product has shipped.';
  return `<div class="bo-fact"><div class="bo-fact-head"><h3>Delivery address</h3><button type="button" class="bo-address-edit" data-change-address="${order.id}" aria-label="Change delivery address"${locked ? ` disabled aria-describedby="${hint}"` : ''} title="${locked ? esc(reason) : 'Change delivery address'}">${icon('edit')}</button></div><address>${lines.map(esc).join('<br>') || 'Not provided'}</address>${locked ? `<p class="bo-meta" id="${hint}">${esc(reason)}</p>` : ''}</div>`;
}
// Progress: requested → accepted → in production → shipped → received; cancelled orders show no tracker.
const BUYER_STEPS = [['pending', 'Requested'], ['accepted', 'Accepted'], ['printing', 'In production'], ['shipped', 'Shipped'], ['completed', 'Received']];
function buyerOrderProgress(order) {
  if (order.status === 'cancelled') return '';
  const reached = BUYER_STEPS.findIndex(([s]) => s === (order.status === 'ready' ? 'printing' : order.status)), partly = order.status !== 'shipped' && order.status !== 'completed' && order.jobs.some(j => ['shipped', 'completed'].includes(j.status));
  return `<ol class="bo-progress" aria-label="Order progress">${BUYER_STEPS.map(([s, label], n) => `<li class="${n < reached ? 'done' : n === reached ? 'current' : ''}${partly && s === 'shipped' ? ' partly' : ''}"${n === reached ? ' aria-current="step"' : ''}><span aria-hidden="true"></span>${label}${partly && s === 'shipped' ? ' (partly)' : ''}</li>`).join('')}</ol>`;
}
const buyerOrderHeadBadge = order => order.status !== 'shipped' && order.status !== 'completed' && order.status !== 'cancelled' && order.jobs.some(j => j.status === 'shipped') ? `<span class="status status-info">Partly shipped</span>` : buyerOrderBadge(order.status);
function buyerOrderCard(order) {
  const count=order.items.reduce((sum,i)=>sum+i.quantity,0),preview=order.items.slice(0,2);
  const shipped=order.jobs.filter(j=>j.status==='shipped');
  const jobs=order.jobs.map(j=>`<li class="bo-job"><div><strong>${esc(j.item.title)}</strong>${buyerOrderConfig(j.item)}<span class="bo-meta">Quantity: ${j.item.quantity}</span><span class="bo-meta">${j.host_id?'Assigned printing host #'+j.host_id:j.status==='cancelled'?'No active assignment':'Waiting for a printing host'}</span>${j.shipment?`<span class="bo-meta">${esc(j.shipment.carrier)} · ${esc(j.shipment.tracking_number)}</span>`:''}</div><div>${buyerOrderBadge(j.status)}<span class="bo-meta">Updated ${esc(safeDate(j.updated_at))}</span></div></li>`).join('');
  return `<article class="section-card bo-card" data-order-id="${order.id}" data-address="${esc(order.address)}" aria-labelledby="bo-title-${order.id}">
    <header class="bo-card-head"><div><h2 id="bo-title-${order.id}">${esc(order.reference)}</h2><time class="bo-meta" datetime="${esc(order.created_at)}">${esc(buyerOrderDate(order.created_at))}</time></div>${buyerOrderHeadBadge(order)}</header>
    ${buyerOrderProgress(order)}
    <ul class="bo-products">${preview.map(i=>buyerOrderLine(i,order.currency)).join('')}</ul>
    ${order.items.length>2?`<p class="bo-more">+ ${order.items.length-2} more ${order.items.length===3?'product':'products'} in order details</p>`:''}
    ${shipped.length?`<section class="bo-shipments" aria-label="Shipped products"><h3>On its way</h3><p class="bo-meta">Confirm each product once it arrives; the order completes when everything is received.</p><ul>${shipped.map(j=>buyerOrderShipment(order,j)).join('')}</ul></section>`:''}
    <div class="bo-total"><span class="bo-meta">${count} ${count===1?'item':'items'} · ${order.items.length} ${order.items.length===1?'product':'products'}</span><span>Total <strong>${buyerOrderMoney(order.total_cents,order.currency)}</strong></span></div>
    <details class="bo-details"><summary aria-label="View details for ${esc(order.reference)}"><span class="bo-open-label">View details</span><span class="bo-close-label">Hide details</span>${icon('chevron')}</summary><div class="bo-detail-body">
      <section class="bo-fulfilment"><div class="bo-delivery">${buyerOrderContact(order)}${buyerOrderAddress(order)}</div><div class="bo-fulfilment-jobs"><h3>Fulfillment</h3><p class="bo-meta">Products may be handled by different printing hosts. Payment and delivery are arranged directly with your host.</p><ul class="bo-jobs">${jobs||'<li>No fulfillment updates yet.</li>'}</ul></div></section>
      <section><h3>Order updates</h3><ol class="bo-history">${order.history.map(e=>`<li><span>${esc(buyerOrderEvents[e.action]||'Order updated')}</span><time datetime="${esc(e.created_at)}">${esc(safeDate(e.created_at))}</time></li>`).join('')||'<li>No updates yet.</li>'}</ol></section>
    </div></details>
  </article>`;
}
function buyerOrdersShell(body) {
  return layout(`<div class="bo-page"><header class="bo-page-head"><div><p class="ws-crumb eyebrow-dot">Buyer workspace</p><h1>My orders</h1><p class="muted">Track your current purchases and manufacturing progress.</p></div><a class="btn-ghost btn-sm" href="#catalogue">Explore products</a></header>${body}</div>`);
}
const BUYER_SCOPE_NAMES = {active:'Current orders', history:'Previous orders'};
function buyerOrdersBody(data, filters) {
  const nav=scopeNav({label:'My orders', base:'orders', query:{sort:filters.sort === 'newest' ? '' : filters.sort}, data, names:BUYER_SCOPE_NAMES, all:{active:'All active', history:'All previous'}});
  const sort=uiSelect({id:'bo-sort',label:'Sort by',value:filters.sort,options:[['newest','Newest first'],['oldest','Oldest first']],className:'bo-sort'});
  // Search by order reference or product name, in Previous orders (where the list grows).
  const search=data.scope==='history'?`<form class="search-field bo-search" id="bo-search" role="search">${icon('search')}<label class="sr-only" for="bo-q">Search previous orders</label><input id="bo-q" type="search" name="q" value="${esc(filters.q)}" placeholder="Order number or product" autocomplete="off" maxlength="80"></form>`:'';
  const scopeTotal=data.scopes[data.scope].total, groupLabel=(data.scopes[data.scope].groups.find(g=>g.key===data.group)||{}).label;
  let empty;
  if(data.scope==='active'&&!scopeTotal) empty=emptyState("You're all caught up", 'No active orders at the moment.', `<div class="empty-actions"><a class="btn btn-sm" href="#catalogue">Explore catalogue</a>${data.scopes.history.total?`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{scope:'history',group:'all',q:'',page:1})}">Previous orders</a>`:''}</div>`);
  else if(data.scope==='history'&&!scopeTotal) empty=emptyState('No previous orders yet','Completed and cancelled orders move here automatically.',`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{scope:'active',group:'all',q:'',page:1})}">Current orders</a>`);
  else if(filters.q) empty=emptyState('No orders match your search',`Nothing in ${groupLabel?groupLabel.toLowerCase()+' ':''}previous orders matches “${filters.q}”.`,`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{q:'',page:1})}">Clear search</a>`);
  else empty=emptyState(data.scope==='active'?'No orders at this stage':'No orders with this status',data.scope==='active'?`None of your current orders is ${(groupLabel||'').toLowerCase()} right now.`:`None of your previous orders is ${(groupLabel||'').toLowerCase()}.`,`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{group:'all',page:1})}">${data.scope==='active'?'All active orders':'All previous orders'}</a>`);
  const content=data.items.length?`<div class="bo-list">${data.items.map(buyerOrderCard).join('')}</div>`:`<div class="section-card">${empty}</div>`;
  const noun=data.scope==='active'?'current':'previous';
  return {toolbar:`${nav.primary}<div class="bo-filters">${nav.secondary}<div class="bo-tools">${search}${sort}</div></div>`,
    results:`<p class="bo-results">${data.total?`${(data.page-1)*data.per_page+1}–${Math.min(data.page*data.per_page,data.total)} of ${data.total} ${noun} ${data.total===1?'order':'orders'}`:`0 ${noun} orders`}</p>${content}${pager(page=>buyerOrderHref(filters,{page}).slice(1),data.page,data.pages)}`};
}
// Highlight the chosen view at once, before its orders arrive.
function buyerOrdersMarkTab(filters) {
  document.querySelectorAll('#bo-toolbar .segment, #bo-toolbar .chip').forEach(link=>{
    const q=new URLSearchParams(link.hash.split('?')[1]||''), scope=q.get('scope')||'active', group=q.get('group')||'all';
    const on=link.classList.contains('segment')?scope===filters.scope:scope===filters.scope&&group===filters.group;
    link.classList.toggle('active',on&&link.classList.contains('chip'));
    if(on)link.setAttribute('aria-current',link.classList.contains('segment')?'page':'true');else link.removeAttribute('aria-current');
  });
}
async function renderBuyerOrders() {
  if(!account||account.role==='admin')return buyerOrdersRenderOperations('orders');
  const request=++buyerOrdersRequest,owner=account.id,hash=location.hash,filters=buyerOrderFilters();
  const current=()=>request===buyerOrdersRequest&&account?.id===owner&&location.hash===hash;
  try{sessionStorage.setItem('ol3d-orders-'+owner,JSON.stringify(filters))}catch(e){}
  // Changing filter, sort or page updates the toolbar and the order list in place: the heading, the
  // layout and the scroll position stay, and the previous orders stay visible (dimmed) while loading.
  const region=$('#app #bo-results'),inPlace=!!(region&&buyerOrdersShown?.owner===owner);
  if(inPlace){buyerOrdersMarkTab(filters);region.setAttribute('aria-busy','true');$('#bo-status').textContent='Updating orders…';}
  else{buyerOrdersShown=null;$('#app').innerHTML=buyerOrdersShell('<div class="bo-toolbar" id="bo-toolbar"></div><div id="bo-results" aria-busy="true"><div class="bo-skeletons" role="status" aria-label="Loading orders"><span class="sr-only">Loading orders…</span>'+Array.from({length:3},()=>'<div class="bo-skeleton" aria-hidden="true"><span></span><span></span><span></span></div>').join('')+'</div></div><p id="bo-status" class="sr-only" role="status"></p>');}
  try{
    // Country names for the delivery addresses; a code is shown if the list cannot be loaded.
    const [data]=await Promise.all([api('/orders?'+new URLSearchParams({...filters,paginated:true,per_page:10})),ensureCountries().catch(()=>[])]);
    if(!current())return;
    const body=buyerOrdersBody(data,filters),toolbar=$('#bo-toolbar'),results=$('#bo-results');
    if(toolbar.innerHTML!==body.toolbar){
      // Keep keyboard focus on the same chip or control when the toolbar's counts change.
      const focused=toolbar.contains(document.activeElement)?document.activeElement.getAttribute('href')||document.activeElement.id:null;
      toolbar.innerHTML=body.toolbar;
      if(focused)toolbar.querySelector(`[href="${CSS.escape(focused)}"],[id="${CSS.escape(focused)}"]`)?.focus();
    }
    results.innerHTML=body.results;results.removeAttribute('aria-busy');
    $('#bo-status').textContent=`${data.total} ${data.total===1?'order':'orders'}`;
    // A new page starts at its first order; filters and sort keep the reader where they are.
    if(inPlace&&buyerOrdersShown.page!==filters.page&&buyerOrdersShown.scope===filters.scope&&buyerOrdersShown.group===filters.group&&buyerOrdersShown.sort===filters.sort&&toolbar.getBoundingClientRect().top<0)toolbar.scrollIntoView({block:'start'});
    buyerOrdersShown={owner,...filters};
    $('[data-select=bo-sort] input[type=hidden]').onchange=e=>{location.hash=buyerOrderHref({...filters,sort:e.target.value},{page:1})};
    const search=$('#bo-search');
    if(search)search.onsubmit=e=>{e.preventDefault();location.hash=buyerOrderHref(filters,{q:search.elements.q.value.trim(),page:1})};
  }catch(e){
    if(!current())return;
    // An unknown status group (an old bookmark, for example) shows the whole scope instead of an error.
    if(e.status===422&&filters.group!=='all'){location.replace(buyerOrderHref(filters,{group:'all',page:1}));return;}
    buyerOrdersShown=null;
    $('#app').innerHTML=buyerOrdersShell(`<div class="section-card bo-error" role="alert"><h2>Unable to load orders</h2><p>${esc(e.message)}</p><button type="button" class="secondary" id="bo-retry">Retry</button></div>`);
    $('#bo-retry').onclick=renderBuyerOrders;
  }
}
// Change delivery address: the current address prefilled, a saved address can be copied in.
const ORDER_ADDRESS_KEYS = ['first_name', 'last_name', 'phone', 'street', 'additional', 'postal_code', 'city', 'region', 'country'];
async function changeOrderAddress(button) {
  const orderId = button.dataset.changeAddress, card = button.closest('.bo-card');
  let saved = [], current = {};
  try { [saved] = await Promise.all([api('/addresses'), ensureCountries()]); current = buyerOrderJson(card.dataset.address); } catch (e) { showError(e); return; }
  const picker = saved.length ? uiSelect({id:'order-address-saved', label:'Use a saved address', className:'cf-select-field', value:'', options:[['', 'Keep the details below'], ...saved.map(a => [String(a.id), [a.label || 'Address', addressLines(a).slice(1, 3).join(', ')].filter(Boolean).join(' · ')])]}) : '';
  const body = `${picker}<form class="ad-form" id="order-address-form" novalidate><div class="fields">${textField('first_name', current.first_name)}${textField('last_name', current.last_name)}${textField('phone', current.phone, {wide:true})}${textField('street', current.street, {required:true, wide:true})}${textField('additional', current.additional, {optional:true, wide:true})}${countryField(current.country, true)}${regionField(current.region)}${cityField(current.city, {required:true})}${textField('postal_code', current.postal_code)}</div></form><ul class="ad-notes"><li>Your printing host sees the new address straight away.</li><li>It can be changed until a product of this order has shipped.</li></ul>`;
  const ok = await actionDialog({title:'Change delivery address', confirm:'Save address', busy:'Saving…', body, run:() => {
    const form = $('#order-address-form');
    if (!form.reportValidity()) throw Error('Enter the street, city and country.');
    const d = Object.fromEntries(new FormData(form));
    return api(`/orders/${orderId}/address`, {method:'PUT', body:JSON.stringify(Object.fromEntries(ORDER_ADDRESS_KEYS.map(k => [k, (d[k] || '').trim()])))});
  }, setup:dialog => {
    bindAccountFields(dialog);
    dialog.querySelector('[data-select=order-address-saved] input[type=hidden]')?.addEventListener('change', e => {
      const a = saved.find(x => String(x.id) === e.target.value); if (!a) return;
      const form = dialog.querySelector('#order-address-form');
      // Country first (it resets region and city), then region, then city.
      for (const k of ['country', 'region', 'city', ...ORDER_ADDRESS_KEYS.filter(k => !['country', 'region', 'city'].includes(k))]) { const select = form.querySelector(`[data-location=${k}]`); if (select) uiSelectSet(select, a[k] || ''); else if (form.elements[k]) form.elements[k].value = a[k] || ''; }
    });
  }});
  if (!ok) { if (button.isConnected) button.focus(); return; }
  toast('Delivery address updated'); renderBuyerOrders();
}
document.addEventListener('click', e => { const button = e.target.closest('[data-change-address]'); if (button && !button.disabled) changeOrderAddress(button); });
// Mark as received: confirmed in the site dialog, then the list refreshes in place.
document.addEventListener('click', async e => {
  const button = e.target.closest('[data-received]'); if (!button) return;
  const [orderId, jobId] = button.dataset.received.split(':'), title = button.closest('.bo-shipment').querySelector('strong').textContent;
  let completed = false;
  const ok = await actionDialog({title:'Mark as received?', confirm:'Mark as received', busy:'Saving…',
    body:`<div class="ad-job"><div class="ad-job-main"><strong>${esc(title)}</strong></div></div><ul class="ad-notes"><li>Confirm the product arrived in good condition.</li><li>The printing job is completed; the order completes once every product is received.</li></ul>`,
    run:async () => { completed = (await api(`/orders/${orderId}/jobs/${jobId}/received`, {method:'POST'})).status === 'completed'; }});
  if (!ok) { if (button.isConnected) button.focus(); return; }
  // When this was the last product, the order is complete: it leaves Current orders for Previous orders.
  toast(completed ? 'Order completed: you can find it in Previous orders' : 'Marked as received'); renderBuyerOrders();
});
renderOperations=function(route){if(route==='orders')return renderBuyerOrders();return buyerOrdersRenderOperations(route)};
