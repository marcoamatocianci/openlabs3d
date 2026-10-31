/* Buyer order presentation. All commercial details come from persisted order snapshots. */
const buyerOrdersRenderOperations = renderOperations;
let buyerOrdersRequest = 0, buyerOrdersShown = null;
// Filters, sort and pages change only the hash query: keep the scroll position (see app.js).
inPageRoutes.add('#orders');
const buyerOrderCategories = [['all','All orders'],['pending','Pending'],['in-progress','In progress'],['completed','Completed'],['cancelled','Cancelled']];
const buyerOrderLabels = {pending:'Awaiting host acceptance',accepted:'Accepted · awaiting printing',printing:'Production in progress',ready:'Ready for delivery',completed:'Completed',cancelled:'Cancelled',available:'Awaiting host acceptance'};
const buyerOrderTone = {pending:'warning',accepted:'warning',printing:'info',ready:'info',completed:'success',cancelled:'danger',available:'warning'};
const buyerOrderBadge = status => `<span class="status status-${buyerOrderTone[status] || 'neutral'}">${esc(buyerOrderLabels[status] || 'Status unavailable')}</span>`;
const buyerOrderDate = value => parseServerDate(value).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'});
const buyerOrderMoney = (cents,currency) => new Intl.NumberFormat(undefined,{style:'currency',currency}).format(cents/100);
const buyerOrderHref = (category,sort,page=1) => '#orders?'+new URLSearchParams({category,sort,page});
function buyerOrderFilters() {
  let saved={};try{saved=JSON.parse(sessionStorage.getItem('ol3d-orders-'+account.id)||'{}')}catch(e){}
  const params=new URLSearchParams(location.hash.split('?')[1]||'');
  const category=params.get('category')||saved.category||'all',sort=params.get('sort')||saved.sort||'newest';
  return {category:buyerOrderCategories.some(([key])=>key===category)?category:'all',sort:sort==='oldest'?'oldest':'newest',page:Math.max(1,parseInt(params.get('page')||'1',10)||1)};
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
const buyerOrderEvents = {'order.created':'Order requested','order.cancelled':'Order cancelled','job.accepted':'A printing host accepted a product','job.printing':'Printing started for a product','job.ready':'A product is ready for delivery','job.completed':'A product was completed','job.reopened':'A product is awaiting a new host'};
function buyerOrderCard(order) {
  const count=order.items.reduce((sum,i)=>sum+i.quantity,0),preview=order.items.slice(0,2);
  const jobs=order.jobs.map(j=>`<li class="bo-job"><div><strong>${esc(j.item.title)}</strong>${buyerOrderConfig(j.item)}<span class="bo-meta">Quantity: ${j.item.quantity}</span><span class="bo-meta">${j.host_id?'Assigned printing host #'+j.host_id:j.status==='cancelled'?'No active assignment':'Waiting for a printing host'}</span></div><div>${buyerOrderBadge(j.status)}<span class="bo-meta">Updated ${esc(safeDate(j.updated_at))}</span></div></li>`).join('');
  return `<article class="section-card bo-card" data-order-id="${order.id}" aria-labelledby="bo-title-${order.id}">
    <header class="bo-card-head"><div><h2 id="bo-title-${order.id}">${esc(order.reference)}</h2><time class="bo-meta" datetime="${esc(order.created_at)}">${esc(buyerOrderDate(order.created_at))}</time></div>${buyerOrderBadge(order.status)}</header>
    <ul class="bo-products">${preview.map(i=>buyerOrderLine(i,order.currency)).join('')}</ul>
    ${order.items.length>2?`<p class="bo-more">+ ${order.items.length-2} more ${order.items.length===3?'product':'products'} in order details</p>`:''}
    <div class="bo-total"><span class="bo-meta">${count} ${count===1?'item':'items'} · ${order.items.length} ${order.items.length===1?'product':'products'}</span><span>Total <strong>${buyerOrderMoney(order.total_cents,order.currency)}</strong></span></div>
    <details class="bo-details"><summary aria-label="View details for ${esc(order.reference)}"><span class="bo-open-label">View details</span><span class="bo-close-label">Hide details</span>${icon('chevron')}</summary><div class="bo-detail-body">
      <section><h3>Ordered products</h3><ul class="bo-products">${order.items.map(i=>buyerOrderLine(i,order.currency,true)).join('')}</ul></section>
      <section><h3>Fulfillment</h3><p class="bo-meta">Products may be handled by different printing hosts. Payment and delivery are arranged directly with your host.</p><ul class="bo-jobs">${jobs||'<li>No fulfillment updates yet.</li>'}</ul></section>
      <section><h3>Delivery & contact</h3><dl class="detail-grid"><div><dt>Order contact</dt><dd>${esc(deliveryText(order.contact))||'Not provided'}</dd></div><div><dt>Delivery address</dt><dd>${esc(deliveryText(order.address))||'Not provided'}</dd></div></dl></section>
      <section><h3>Order updates</h3><ol class="bo-history">${order.history.map(e=>`<li><span>${esc(buyerOrderEvents[e.action]||'Order updated')}</span><time datetime="${esc(e.created_at)}">${esc(safeDate(e.created_at))}</time></li>`).join('')||'<li>No updates yet.</li>'}</ol></section>
    </div></details>
  </article>`;
}
function buyerOrdersShell(body) {
  return layout(`<div class="bo-page"><header class="bo-page-head"><div><p class="ws-crumb eyebrow-dot">Buyer workspace</p><h1>My orders</h1><p class="muted">Your laboratory tools, from request to completion.</p></div><a class="btn-ghost btn-sm" href="#catalogue">Explore products</a></header>${body}</div>`);
}
function buyerOrdersBody(data, filters) {
  const tabs=filterChips('Order status',buyerOrderCategories.map(([value,label])=>({value,label,href:buyerOrderHref(value,filters.sort).slice(1),count:data.counts[value]})),filters.category);
  const sort=`<label class="bo-sort">Sort by<select id="bo-sort"><option value="newest" ${filters.sort==='newest'?'selected':''}>Newest first</option><option value="oldest" ${filters.sort==='oldest'?'selected':''}>Oldest first</option></select></label>`;
  const emptyTitle={all:'No orders yet',pending:'No pending orders','in-progress':'No orders in progress',completed:'No completed orders',cancelled:'No cancelled orders'};
  const emptyText={pending:'Orders awaiting host acceptance or printing will appear here.','in-progress':'Orders being printed or ready for delivery will appear here.',completed:'Your fulfilled orders will appear here.',cancelled:'Cancelled order requests will appear here.'};
  const content=data.items.length?`<div class="bo-list">${data.items.map(buyerOrderCard).join('')}</div>`:`<div class="section-card">${emptyState(data.counts.all?emptyTitle[filters.category]:'No orders yet',data.counts.all?emptyText[filters.category]||'Your order requests appear here.':'Explore laboratory tools and place your first order request.',data.counts.all?`<a class="btn btn-sm" href="${buyerOrderHref('all',filters.sort)}">View all orders</a>`:'<a class="btn btn-sm" href="#catalogue">Explore products</a>')}</div>`;
  const pageLink=(page,label)=>`<a class="btn-ghost btn-sm" href="${buyerOrderHref(filters.category,filters.sort,page)}">${label}</a>`;
  const pagination=data.pages>1?`<nav class="bo-pagination" aria-label="Order pages">${data.page>1?pageLink(data.page-1,'Previous'):'<span></span>'}<span>Page ${data.page} of ${data.pages}</span>${data.page<data.pages?pageLink(data.page+1,'Next'):'<span></span>'}</nav>`:'';
  return {toolbar:`${tabs}${sort}`, results:`<p class="bo-results">${data.total?`${(data.page-1)*data.per_page+1}–${Math.min(data.page*data.per_page,data.total)} of ${data.total} orders`:'0 orders'}</p>${content}${pagination}`};
}
// Highlight the chosen status at once, before its orders arrive.
function buyerOrdersMarkTab(category) {
  document.querySelectorAll('#bo-toolbar .chip').forEach(chip=>{const on=new URLSearchParams(chip.hash.split('?')[1]).get('category')===category;chip.classList.toggle('active',on);on?chip.setAttribute('aria-current','true'):chip.removeAttribute('aria-current')});
}
async function renderBuyerOrders() {
  if(!account||account.role==='admin')return buyerOrdersRenderOperations('orders');
  const request=++buyerOrdersRequest,owner=account.id,hash=location.hash,filters=buyerOrderFilters();
  const current=()=>request===buyerOrdersRequest&&account?.id===owner&&location.hash===hash;
  try{sessionStorage.setItem('ol3d-orders-'+owner,JSON.stringify(filters))}catch(e){}
  // Changing filter, sort or page updates the toolbar and the order list in place: the heading, the
  // layout and the scroll position stay, and the previous orders stay visible (dimmed) while loading.
  const region=$('#app #bo-results'),inPlace=!!(region&&buyerOrdersShown?.owner===owner);
  if(inPlace){buyerOrdersMarkTab(filters.category);region.setAttribute('aria-busy','true');$('#bo-status').textContent='Updating orders…';}
  else{buyerOrdersShown=null;$('#app').innerHTML=buyerOrdersShell('<div class="bo-toolbar" id="bo-toolbar"></div><div id="bo-results" aria-busy="true"><div class="bo-skeletons" role="status" aria-label="Loading orders"><span class="sr-only">Loading orders…</span>'+Array.from({length:3},()=>'<div class="bo-skeleton" aria-hidden="true"><span></span><span></span><span></span></div>').join('')+'</div></div><p id="bo-status" class="sr-only" role="status"></p>');}
  try{
    const data=await api('/orders?'+new URLSearchParams({...filters,paginated:true,per_page:10}));
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
    if(inPlace&&buyerOrdersShown.page!==filters.page&&buyerOrdersShown.category===filters.category&&buyerOrdersShown.sort===filters.sort&&toolbar.getBoundingClientRect().top<0)toolbar.scrollIntoView({block:'start'});
    buyerOrdersShown={owner,...filters};
    $('#bo-sort').onchange=e=>{location.hash=buyerOrderHref(filters.category,e.target.value)};
  }catch(e){
    if(!current())return;
    buyerOrdersShown=null;
    $('#app').innerHTML=buyerOrdersShell(`<div class="section-card bo-error" role="alert"><h2>Unable to load orders</h2><p>${esc(e.message)}</p><button type="button" class="secondary" id="bo-retry">Retry</button></div>`);
    $('#bo-retry').onclick=renderBuyerOrders;
  }
}
renderOperations=function(route){if(route==='orders')return renderBuyerOrders();return buyerOrdersRenderOperations(route)};
