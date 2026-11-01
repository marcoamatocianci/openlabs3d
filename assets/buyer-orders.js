/* Buyer order presentation. All commercial details come from persisted order snapshots.
   Current orders: a board with one column per stage (Pending, In progress, Shipping), the shared
   workflow board (navigation.js). Previous orders: completed and cancelled orders, a compact searchable
   list. Both open the same order details dialog. */
const buyerOrdersRenderOperations = renderOperations;
let buyerOrdersRequest = 0, buyerOrdersShown = null, buyerOrdersById = {};
// Filters, sort and pages change only the hash query: keep the scroll position (see app.js).
inPageRoutes.add('#orders');
// The order's stage in the buyer's words; the same words as each product's own stage (buyerItemStages).
const buyerOrderLabels = {pending:'Awaiting a host',accepted:'Accepted',printing:'In production',ready:'Ready to ship',shipped:'Shipped',completed:'Completed',cancelled:'Cancelled',available:'Awaiting a host'};
// Waiting for someone to take it (amber), being made or delivered (blue), done (green), cancelled (red):
// the same tones as the printing jobs behind the order.
const buyerOrderTone = {pending:'warning',available:'warning',accepted:'info',printing:'info',ready:'info',shipped:'info',completed:'success',cancelled:'danger'};
const buyerOrderBadge = (status, label) => `<span class="status status-${buyerOrderTone[status] || 'neutral'}">${esc(label || buyerOrderLabels[status] || 'Status unavailable')}</span>`;
// Each product's own stage, in the buyer's words (an order can hold products at different stages).
const buyerItemStages = {available:'Awaiting a host',accepted:'Accepted',printing:'In production',ready:'Ready to ship',shipped:'Shipped',completed:'Received',cancelled:'Cancelled'};
const buyerOrderDate = value => parseServerDate(value).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'});
const buyerOrderMoney = (cents,currency) => new Intl.NumberFormat(undefined,{style:'currency',currency}).format(cents/100);
// My Orders shows Current orders by default (scope=active) and Previous orders on request (scope=history).
// The address holds the view (scope, status group, search, page, sort), so Back and Forward restore it;
// only the sort order is remembered for the session. In Current orders a group only scrolls the board to it.
const buyerOrderHref = (filters, params={}) => '#' + scopeHref('orders', {scope:filters.scope, group:filters.group, q:filters.q, sort:filters.sort === 'newest' ? '' : filters.sort}, params);
function buyerOrderFilters() {
  let saved={};try{saved=JSON.parse(sessionStorage.getItem('ol3d-orders-'+account.id)||'{}')}catch(e){}
  const params=new URLSearchParams(location.hash.split('?')[1]||''), sort=params.get('sort')||saved.sort||'newest';
  return {scope:params.get('scope')==='history'?'history':'active', group:params.get('group')||'all', q:(params.get('q')||'').slice(0,80), sort:sort==='oldest'?'oldest':'newest', page:Math.max(1,parseInt(params.get('page')||'1',10)||1)};
}
// The purchased configuration comes only from the order line: material, colour name and the colour
// snapshot taken at checkout (shared helpers in navigation.js).
const buyerOrderConfig = item => orderLineConfig(item);
const buyerOrderThumb = item => orderLineThumb(item, 'bo-thumb');
// Order lines with the printing job that makes each one (one job per line).
function buyerOrderLines(order) {
  const jobs = Object.fromEntries(order.jobs.map(j => [j.item_id, j]));
  return order.items.map((item, n) => ({item, job:jobs[item.id] || order.jobs[n]}));
}
const buyerOrderEvents = {'order.created':'Order requested','order.cancelled':'Order cancelled','job.accepted':'A printing host accepted a product','job.printing':'Printing started for a product','job.ready':'A product is ready for delivery','job.shipped':'A product was shipped','job.completed':'A product was received','order.completed':'Order completed','job.reopened':'A product is awaiting a new host','order.address_changed':'Delivery address changed'};
const buyerTracking = s => s.tracking_url ? `<a class="textlink" href="${esc(s.tracking_url)}" target="_blank" rel="noopener noreferrer">${esc(s.tracking_number)}<span class="sr-only"> (opens the carrier’s tracking page)</span> ↗</a>` : esc(s.tracking_number || '');
// Shipped products: tracking details and the receipt confirmation that completes them.
function buyerOrderShipment(order, job) {
  const s = job.shipment || {};
  return `<li class="bo-shipment"><div class="bo-shipment-copy"><strong>${esc(job.item.title)}</strong><span class="bo-meta">${esc(s.carrier || 'Carrier not provided')}${s.tracking_number ? ' · Tracking ' + buyerTracking(s) : ''}</span>${s.note ? `<span class="bo-meta">${esc(s.note)}</span>` : ''}${s.shipped_at ? `<span class="bo-meta">Shipped ${esc(buyerOrderDate(s.shipped_at))}</span>` : ''}</div><button type="button" class="btn btn-sm" data-received="${order.id}:${job.id}">Mark as received<span class="sr-only">: ${esc(job.item.title)}</span></button></li>`;
}
const buyerOrderShipments = (order, shipped) => shipped.length ? `<section class="bo-shipments" aria-label="Shipped products to confirm"><p class="bo-shipments-title">${shipped.length === 1 ? 'On its way' : `${shipped.length} products on their way`}</p><p class="bo-meta">Confirm each product once it arrives; the order completes when everything is received.</p><ul>${shipped.map(j => buyerOrderShipment(order, j)).join('')}</ul></section>` : '';
const buyerOrderJson = value => { try { const data = JSON.parse(value); return data && typeof data === 'object' ? data : {}; } catch (e) { return {}; } };
// The address may change until any product of the order has shipped (the server enforces the same rule).
const buyerOrderAddressLocked = order => order.status === 'cancelled' || order.jobs.some(j => ['shipped', 'completed'].includes(j.status));
function buyerOrderContact(order) {
  const c = buyerOrderJson(order.contact), lines = [[c.first_name, c.last_name].filter(Boolean).join(' '), c.email, c.phone].filter(Boolean);
  return `<div class="bo-fact"><h4>Order contact</h4><p>${lines.map(esc).join('<br>') || 'Not provided'}</p></div>`;
}
function buyerOrderAddress(order) {
  const lines = addressLines(buyerOrderJson(order.address)), locked = buyerOrderAddressLocked(order), hint = `bo-address-hint-${order.id}`;
  const reason = order.status === 'cancelled' ? 'Cancelled orders cannot be changed.' : 'The address is fixed once a product has shipped.';
  return `<div class="bo-fact"><div class="bo-fact-head"><h4>Delivery address</h4><button type="button" class="bo-address-edit" data-change-address="${order.id}" aria-label="Change delivery address"${locked ? ` disabled aria-describedby="${hint}"` : ''} title="${locked ? esc(reason) : 'Change delivery address'}">${icon('edit')}</button></div><address>${lines.map(esc).join('<br>') || 'Not provided'}</address>${locked ? `<p class="bo-meta" id="${hint}">${esc(reason)}</p>` : ''}</div>`;
}
/* Progress: requested → accepted → in production → shipped → received; cancelled orders show none.
   The order's stage is the server's (operations.sync_order): it reaches a stage once every product has,
   except production, which starts with the first product printed. Products ahead of the order (one
   already shipped, for example) are marked "partly" and listed with their own stage. */
const BUYER_STEPS = [['pending', 'Requested'], ['accepted', 'Accepted'], ['printing', 'In production'], ['shipped', 'Shipped'], ['completed', 'Received']];
const buyerOrderPartly = order => order.status !== 'shipped' && order.status !== 'completed' && order.status !== 'cancelled' && order.jobs.some(j => ['shipped', 'completed'].includes(j.status));
function buyerOrderProgress(order, labels = true) {
  if (order.status === 'cancelled') return '';
  const reached = BUYER_STEPS.findIndex(([s]) => s === (order.status === 'ready' ? 'printing' : order.status)), partly = buyerOrderPartly(order);
  const step = ([s, label], n) => `<li class="${n < reached ? 'done' : n === reached ? 'current' : ''}${partly && s === 'shipped' ? ' partly' : ''}"${n === reached ? ' aria-current="step"' : ''}><span aria-hidden="true"></span>${labels ? `${label}${partly && s === 'shipped' ? ' (partly)' : ''}` : `<b class="sr-only">${label}${n < reached ? ', done' : ''}</b>`}</li>`;
  return `<ol class="bo-progress${labels ? '' : ' bo-progress-bar'}" aria-label="Order progress">${BUYER_STEPS.map(step).join('')}</ol>`;
}
// Products ahead of the order name the badge: "Partly shipped", or "Partly received" when nothing is being
// printed any more (the server counts the order as in production as soon as one product has started).
function buyerOrderHeadBadge(order) {
  if (buyerOrderPartly(order) && order.jobs.some(j => j.status === 'shipped')) return buyerOrderBadge('shipped', 'Partly shipped');
  if (buyerOrderPartly(order) && !order.jobs.some(j => ['printing', 'ready'].includes(j.status))) return buyerOrderBadge('shipped', 'Partly received');
  return buyerOrderBadge(order.status);
}
// Several products at different stages: each shown product names its own; with more products than the
// card shows, a summary line counts them all, so no stage is hidden behind the order's.
function buyerOrderMix(order) {
  const stages = new Set(order.jobs.map(j => j.status));
  if (order.jobs.length < 3 || stages.size < 2) return '';
  const counts = ['completed', 'shipped', 'ready', 'printing', 'accepted', 'available'].filter(s => stages.has(s)).map(s => `${order.jobs.filter(j => j.status === s).length} ${buyerItemStages[s].toLowerCase()}`);
  return `<p class="bo-mix">${esc(counts.join(' · '))}</p>`;
}
/* One card per order on the board: what was ordered (with the colour bought), where it stands, and
   what the buyer can do now (confirm a delivery). Everything else is in the details dialog. */
function buyerOrderCard(order, level = 3) {
  const lines = buyerOrderLines(order), shipped = order.jobs.filter(j => j.status === 'shipped'), multi = order.jobs.length > 1;
  const line = ({item, job}) => `<li class="bo-line">${buyerOrderThumb(item)}<div class="bo-line-copy"><span class="bo-line-title">${esc(item.title)}</span>${buyerOrderConfig(item)}<span class="bo-meta">Quantity ${item.quantity}${multi && job ? ` · ${esc(buyerItemStages[job.status] || '')}` : ''}</span></div></li>`;
  return `<li class="wf-card bo-card${shipped.length ? ' needs-action' : ''}" data-order-id="${order.id}" aria-labelledby="bo-title-${order.id}"><div class="bo-card-top"><h${level} class="bo-ref" id="bo-title-${order.id}">${esc(order.reference)}</h${level}><time class="bo-meta" datetime="${esc(order.created_at)}">${esc(buyerOrderDate(order.created_at))}</time></div><div class="bo-card-stage">${buyerOrderHeadBadge(order)}${buyerOrderProgress(order, false)}</div><ul class="bo-lines">${lines.slice(0, 2).map(line).join('')}</ul>${lines.length > 2 ? `<p class="bo-more">+ ${lines.length - 2} more ${lines.length === 3 ? 'product' : 'products'}</p>` : ''}${buyerOrderMix(order)}${buyerOrderShipments(order, shipped)}<div class="bo-card-foot"><span class="bo-total">Total <strong>${buyerOrderMoney(order.total_cents, order.currency)}</strong></span><button type="button" class="wf-link" data-order-details="${order.id}" aria-haspopup="dialog">View details<span class="sr-only"> for ${esc(order.reference)}</span></button></div></li>`;
}
// Previous orders: one compact row each; the details dialog holds the rest.
function buyerOrderRow(order) {
  const lines = buyerOrderLines(order), first = lines[0]?.item || {}, count = order.items.reduce((n, i) => n + i.quantity, 0);
  return `<article class="list-row bo-row bo-card" data-order-id="${order.id}">${buyerOrderThumb(first)}<div class="row-main"><span class="row-title">${esc(first.title || 'Order')}${lines.length > 1 ? ` <span class="muted">+ ${lines.length - 1} more</span>` : ''}</span><span class="row-meta">${buyerOrderConfig(first)}</span><span class="row-meta"><span class="bo-ref">${esc(order.reference)}</span> · ${esc(buyerOrderDate(order.created_at))} · ${count} ${count === 1 ? 'item' : 'items'}</span></div><span class="row-value">${buyerOrderMoney(order.total_cents, order.currency)}</span><span class="row-status">${buyerOrderHeadBadge(order)}</span><div class="row-actions"><button type="button" class="btn-ghost btn-sm" data-order-details="${order.id}" aria-haspopup="dialog">View details<span class="sr-only"> for ${esc(order.reference)}</span></button></div></article>`;
}
// A pending order nobody has accepted yet can still be deleted (the server checks the same rule).
const buyerOrderDeletable = order => order.status === 'pending' && order.jobs.every(j => j.status === 'available' && !j.host_id) && !order.history.some(e => e.action === 'job.accepted');
const BIN = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5"/></svg>';
/* Order details: every product with its own stage and shipment, delivery details (the address can be
   changed until something ships), the order's history and, while nobody has accepted it, deletion. */
function buyerOrderDetails(id) {
  const order = buyerOrdersById[id]; if (!order) return;
  const lines = buyerOrderLines(order), count = order.items.reduce((n, i) => n + i.quantity, 0);
  const product = ({item, job}) => `<li class="bo-detail-line">${buyerOrderThumb(item)}<div class="bo-line-copy"><span class="bo-line-title">${esc(item.title)}</span>${buyerOrderConfig(item)}<span class="bo-meta">Quantity ${item.quantity} · ${buyerOrderMoney(item.price_cents, order.currency)} each</span><span class="bo-meta">${job ? (job.host_id ? 'Made by a printing host' : job.status === 'cancelled' ? 'No active assignment' : 'Waiting for a printing host') : ''}${job?.shipment ? ` · ${esc(job.shipment.carrier)} · Tracking ${buyerTracking(job.shipment)}` : ''}</span></div><div class="bo-detail-side">${job ? buyerOrderBadge(job.status, buyerItemStages[job.status]) : ''}<strong>${buyerOrderMoney(item.price_cents * item.quantity, order.currency)}</strong></div></li>`;
  const shipped = order.jobs.filter(j => j.status === 'shipped');
  const body = (order.status === 'cancelled' ? '' : reviewSection('Progress', buyerOrderProgress(order)))
    + buyerOrderShipments(order, shipped)
    + reviewSection(`Products (${lines.length})`, `<ul class="bo-detail-lines">${lines.map(product).join('')}</ul><p class="bo-detail-total"><span class="bo-meta">${count} ${count === 1 ? 'item' : 'items'} · Payment and delivery are arranged directly with your printing host.</span><span>Total <strong>${buyerOrderMoney(order.total_cents, order.currency)}</strong></span></p>`)
    + reviewSection('Delivery', `<div class="bo-delivery">${buyerOrderContact(order)}${buyerOrderAddress(order)}</div>`)
    + reviewSection('Order updates', `<ol class="bo-history">${order.history.map(e => `<li><span>${esc(buyerOrderEvents[e.action] || 'Order updated')}</span><time datetime="${esc(e.created_at)}">${esc(safeDate(e.created_at))}</time></li>`).join('') || '<li>No updates yet.</li>'}</ol>`)
    + (buyerOrderDeletable(order) ? `<div class="bo-delete-row"><span>No host has accepted this order yet, so you can still delete it.</span><button type="button" class="bo-delete" data-delete-order="${order.id}" aria-label="Delete order ${esc(order.reference)}">${BIN}Delete order</button></div>` : '');
  const dialog = openReview(order.reference, `Order · placed ${buyerOrderDate(order.created_at)}`, `<div class="bo-detail" data-order-id="${order.id}">${buyerOrderHeadBadge(order)}${body}</div>`, '');
  dialog.dataset.order = order.id;
  dialog.addEventListener('close', () => { delete dialog.dataset.order; }, {once:true});
}
// After an action, show the refreshed order in the dialog that is still open (or close it if the order left this view).
function refreshOpenOrder(id) {
  const dialog = $('#modal'); if (!dialog.open || dialog.dataset.order !== String(id)) return;
  if (buyerOrdersById[id]) buyerOrderDetails(id); else dialog.close();
}
document.addEventListener('click', e => { const b = e.target.closest('[data-order-details]'); if (b) buyerOrderDetails(+b.dataset.orderDetails); });
function buyerOrdersShell(body) {
  return layout(`<div class="bo-page"><header class="bo-page-head"><div><p class="ws-crumb eyebrow-dot">Buyer workspace</p><h1>My orders</h1><p class="muted">Track your purchases and their progress.</p></div><a class="btn-ghost btn-sm" href="#catalogue">Explore products</a></header>${body}</div>`);
}
const BUYER_SCOPE_NAMES = {active:'Current orders', history:'Previous orders'};
const BUYER_STAGE_HINTS = {pending:'Waiting for a printing host to accept.', 'in-progress':'Accepted by a host and being made.', shipping:'On its way. Confirm each product when it arrives.'};
function buyerOrdersBody(data, filters) {
  const nav=scopeNav({label:'My orders', base:'orders', query:{sort:filters.sort === 'newest' ? '' : filters.sort}, data, names:BUYER_SCOPE_NAMES, all:{active:'All active', history:'All previous'}});
  const sort=uiSelect({id:'bo-sort',label:'Sort by',value:filters.sort,options:[['newest','Newest first'],['oldest','Oldest first']],className:'bo-sort'});
  if (data.scope === 'active') {
    const empty = emptyState("You're all caught up", 'No current orders at the moment.', `<div class="empty-actions"><a class="btn btn-sm" href="#catalogue">Explore catalogue</a>${data.scopes.history.total?`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{scope:'history',group:'all',q:'',page:1})}">Previous orders</a>`:''}</div>`);
    const board = workflowBoard({id:'bo-board', label:'Current orders', stages:data.scopes.active.groups.map(g => ({...g, hint:BUYER_STAGE_HINTS[g.key] || ''})), items:data.items, card:buyerOrderCard, level:2, focus:filters.group,
      empty:c => c.key === 'shipping' ? 'Nothing on its way right now.' : 'No orders at this stage.'});
    return {toolbar:`<div class="wf-toolbar">${nav.primary}<div class="bo-tools">${sort}</div></div>`, results:data.items.length ? board : `<div class="section-card">${empty}</div>`};
  }
  // Search by order reference or product name, in Previous orders (where the list grows).
  const search=`<form class="search-field bo-search" id="bo-search" role="search">${icon('search')}<label class="sr-only" for="bo-q">Search previous orders</label><input id="bo-q" type="search" name="q" value="${esc(filters.q)}" placeholder="Order number or product" autocomplete="off" maxlength="80"></form>`;
  const scopeTotal=data.scopes.history.total, groupLabel=(data.scopes.history.groups.find(g=>g.key===data.group)||{}).label;
  let empty;
  if(!scopeTotal) empty=emptyState('No previous orders yet','Completed and cancelled orders move here automatically.',`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{scope:'active',group:'all',q:'',page:1})}">Current orders</a>`);
  else if(filters.q) empty=emptyState('No orders match your search',`Nothing in ${groupLabel?groupLabel.toLowerCase()+' ':''}previous orders matches “${filters.q}”.`,`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{q:'',page:1})}">Clear search</a>`);
  else empty=emptyState('No orders with this status',`None of your previous orders is ${(groupLabel||'').toLowerCase()}.`,`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters,{group:'all',page:1})}">All previous orders</a>`);
  const content=data.items.length?`<div class="list bo-history-list">${data.items.map(buyerOrderRow).join('')}</div>`:`<div class="section-card">${empty}</div>`;
  return {toolbar:`${nav.primary}<div class="bo-filters">${nav.secondary}<div class="bo-tools">${search}${sort}</div></div>`,
    results:`<p class="bo-results">${data.total?`${(data.page-1)*data.per_page+1}–${Math.min(data.page*data.per_page,data.total)} of ${data.total} previous ${data.total===1?'order':'orders'}`:'0 previous orders'}</p>${content}${pager(page=>buyerOrderHref(filters,{page}).slice(1),data.page,data.pages)}`};
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
// Current orders are bounded by work in progress: load them all (in pages of 50) so every column is complete.
async function buyerOrdersData(filters) {
  if (filters.scope === 'history') return api('/orders?'+new URLSearchParams({...filters,paginated:true,per_page:10}));
  const query = page => api('/orders?'+new URLSearchParams({scope:'active',sort:filters.sort,paginated:true,per_page:50,page}));
  const first = await query(1), rest = await Promise.all(Array.from({length:first.pages - 1}, (_, n) => query(n + 2)));
  return {...first, items:[first, ...rest].flatMap(p => p.items)};
}
async function renderBuyerOrders() {
  if(!account||account.role==='admin')return buyerOrdersRenderOperations('orders');
  const request=++buyerOrdersRequest,owner=account.id,hash=location.hash,filters=buyerOrderFilters();
  const current=()=>request===buyerOrdersRequest&&account?.id===owner&&location.hash===hash;
  try{sessionStorage.setItem('ol3d-orders-'+owner,JSON.stringify(filters))}catch(e){}
  // Changing scope, filter, sort or page updates the toolbar and the results in place: the heading, the
  // layout and the scroll position stay, and the previous orders stay visible (dimmed) while loading.
  const region=$('#app #bo-results'),inPlace=!!(region&&buyerOrdersShown?.owner===owner);
  if(inPlace){buyerOrdersMarkTab(filters);region.setAttribute('aria-busy','true');$('#bo-status').textContent='Updating orders…';}
  else{buyerOrdersShown=null;$('#app').innerHTML=buyerOrdersShell('<div class="bo-toolbar" id="bo-toolbar"></div><div id="bo-results" aria-busy="true"><div class="bo-skeletons" role="status" aria-label="Loading orders"><span class="sr-only">Loading orders…</span>'+Array.from({length:3},()=>'<div class="bo-skeleton" aria-hidden="true"><span></span><span></span><span></span></div>').join('')+'</div></div><p id="bo-status" class="sr-only" role="status"></p>');}
  try{
    // Country names for the delivery addresses; a code is shown if the list cannot be loaded.
    const [data]=await Promise.all([buyerOrdersData(filters),ensureCountries().catch(()=>[])]);
    if(!current())return;
    buyerOrdersById=Object.fromEntries(data.items.map(o=>[o.id,o]));
    const body=buyerOrdersBody(data,filters),toolbar=$('#bo-toolbar'),results=$('#bo-results');
    if(toolbar.innerHTML!==body.toolbar){
      // Keep keyboard focus on the same chip or control when the toolbar's counts change.
      const focused=toolbar.contains(document.activeElement)?document.activeElement.getAttribute('href')||document.activeElement.id:null;
      toolbar.innerHTML=body.toolbar;
      if(focused)toolbar.querySelector(`[href="${CSS.escape(focused)}"],[id="${CSS.escape(focused)}"]`)?.focus();
    }
    results.innerHTML=body.results;results.removeAttribute('aria-busy');bindWorkflowBoards(results);
    $('#bo-status').textContent=`${data.items.length} ${data.scope==='active'?'current':'previous'} ${data.items.length===1?'order':'orders'}`;
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
  const orderId = button.dataset.changeAddress;
  let saved = [], current = {};
  try { [saved] = await Promise.all([api('/addresses'), ensureCountries()]); current = buyerOrderJson(buyerOrdersById[orderId]?.address); } catch (e) { showError(e); return; }
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
  toast('Delivery address updated'); await renderBuyerOrders(); refreshOpenOrder(orderId);
  $(`#modal [data-change-address="${orderId}"]`)?.focus();
}
document.addEventListener('click', e => { const button = e.target.closest('[data-change-address]'); if (button && !button.disabled) changeOrderAddress(button); });
// Mark as received: confirmed in the site dialog, then the board and any open details refresh in place.
document.addEventListener('click', async e => {
  const button = e.target.closest('[data-received]'); if (!button) return;
  const [orderId, jobId] = button.dataset.received.split(':'), title = button.closest('.bo-shipment').querySelector('strong').textContent;
  let completed = false;
  const ok = await actionDialog({title:'Mark as received?', confirm:'Mark as received', busy:'Saving…',
    body:`<div class="ad-job"><div class="ad-job-main"><strong>${esc(title)}</strong></div></div><ul class="ad-notes"><li>Confirm the product arrived in good condition.</li><li>The printing job is completed; the order completes once every product is received.</li></ul>`,
    run:async () => { completed = (await api(`/orders/${orderId}/jobs/${jobId}/received`, {method:'POST'})).status === 'completed'; }});
  if (!ok) { if (button.isConnected) button.focus(); return; }
  // When this was the last product, the order is complete: it leaves Current orders for Previous orders.
  toast(completed ? 'Order completed: you can find it in Previous orders' : 'Marked as received'); await renderBuyerOrders(); refreshOpenOrder(orderId);
});
document.addEventListener('click', async e => {
  const button = e.target.closest('[data-delete-order]'); if (!button) return;
  const order = buyerOrdersById[button.dataset.deleteOrder], reference = order?.reference || '';
  const ok = await actionDialog({title:'Delete this order?', confirm:'Delete order', busy:'Deleting…', initialFocus:'.ad-foot [data-ad-cancel]',
    body:`<div class="bo-delete-confirm"><span class="bo-delete-reference">${esc(reference)}</span><p>This permanently deletes the order and withdraws all its printing requests. It will disappear from your order history, and hosts will no longer be able to accept it.</p><p class="bo-delete-note">This cannot be undone. You can place a new order later.</p></div>`,
    run:() => api(`/orders/${button.dataset.deleteOrder}`, {method:'DELETE'})});
  if (!ok) { if (button.isConnected) button.focus(); return; }
  if ($('#modal').open) $('#modal').close();
  toast('Order deleted'); renderBuyerOrders();
});
renderOperations=function(route){if(route==='orders')return renderBuyerOrders();return buyerOrdersRenderOperations(route)};
