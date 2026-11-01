/* Role-aware routing plus the administrator and printing-host workspaces. */
const workspaceRender = render, defaultTitle = document.title;
// Earlier routes stay valid: they redirect to the page that now owns their content.
const routeRedirects = {dashboard:'catalogue', moderation:'admin/pending', 'admin/':'admin', production:'my-printers'};
const signedInRoutes = ['orders', 'basket', 'checkout', 'checkout-cart', 'host', 'admin', 'my-listings', 'my-printers', 'create-listing', 'edit-listing', 'onboarding'];
const hostOnlyRoutes = ['host', 'my-listings', 'my-printers', 'create-listing', 'edit-listing'];
const adminRedirects = ['custom', 'onboarding', 'orders', 'basket', 'checkout', 'checkout-cart', 'create-listing', 'my-listings', 'my-printers', 'host'];
let workspaceRequest = 0, lastWorkspaceRoute = null, adminUsersCache = {}, adminHostsCache = {};

function accessPage(title, text, actions) { return layout(`<div class="section-card access-card"><h1>${esc(title)}</h1><p>${esc(text)}</p><div class="actions">${actions}</div></div>`); }
function signInPrompt(route) {
  try { sessionStorage.setItem('ol3d-return-to', route); } catch (e) {}
  const text = routeIn(route, 'orders') ? 'Sign in to follow your order requests.' : routeIn(route, 'basket', 'checkout', 'checkout-cart') ? 'Your basket is saved privately in your account.' : routeIn(route, 'admin') ? 'Sign in with an administrator account.' : 'Sign in to apply as a printing host or open your workspace.';
  return accessPage('Sign in to continue', text, '<a class="btn" href="#account">Sign in</a><a class="btn light" href="#account?mode=register">Create account</a>');
}
const userIndex = users => Object.fromEntries(users.map(u => [u.id, u]));
const personName = (index, id) => index[id] ? userName(index[id]) : id ? `User #${id}` : 'System';
const listEmpty = text => `<p class="list-empty" data-filter-empty hidden>${esc(text)}</p>`;

render = function() {
  const route = currentRoute();
  if (routeRedirects[route]) { location.replace('#' + routeRedirects[route]); return; }
  navState.mobile = false; navState.sidebar = false; closeDropdowns(); document.title = defaultTitle;
  renderNavbar(route);
  if (account?.role === 'admin' && (adminRedirects.includes(route) || routeIn(route, 'host'))) { location.replace('#admin'); return; }
  if (!account && signedInRoutes.some(r => routeIn(route, r))) { lastWorkspaceRoute = null; $('#app').innerHTML = authChecked ? signInPrompt(route) : layout('<div class="ws-loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading…</div>'); return; }
  if (account && account.role !== 'admin' && routeIn(route, 'admin')) { $('#app').innerHTML = accessPage('Administrator access required', 'This workspace is only available to marketplace administrators.', '<a class="btn" href="#catalogue">Back to the marketplace</a>'); return; }
  if (account && !['admin', 'host'].includes(account.role) && hostOnlyRoutes.some(r => routeIn(route, r))) { $('#app').innerHTML = accessPage('Printing host access required', 'The host workspace opens once an administrator approves your printing host application.', '<a class="btn" href="#onboarding">Printing host application</a><a class="btn light" href="#catalogue">Back to the marketplace</a>'); return; }
  const page = workspaceRoute(route);
  if (page) { page(); return; }
  lastWorkspaceRoute = null;
  workspaceRender();
};
function workspaceRoute(route) {
  if (account?.role === 'admin' && routeIn(route, 'admin')) {
    if (route === 'admin/create-official') return () => { lastWorkspaceRoute = null; editListing = null; $('#app').innerHTML = listingEditor({listing_type:'official'}); bindMarketplace(); };
    const loader = adminPages[route.split('/').slice(0, 2).join('/')];
    return loader ? () => showWorkspace('admin', route, loader) : () => location.replace('#admin');
  }
  if (account?.role === 'host') {
    const loader = hostPages[routeIn(route, 'host/jobs') ? 'host/jobs' : route];
    if (loader) return () => showWorkspace('host', route, loader);
  }
}
async function showWorkspace(kind, route, loader) {
  const request = ++workspaceRequest, main = $('#app .ws-main');
  // Refreshing the same page after an action keeps its content visible instead of flashing a loader.
  if (lastWorkspaceRoute === route && main) main.setAttribute('aria-busy', 'true');
  else $('#app').innerHTML = workspacePage(kind, activeWorkspaceItem(kind, route).item?.label || WORKSPACES[kind].label, '<div class="ws-loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading…</div>');
  try {
    const page = await loader(route);
    if (request !== workspaceRequest || currentRoute() !== route) return;
    $('#app').innerHTML = workspacePage(kind, page.title, page.body, page.action);
    lastWorkspaceRoute = route; page.bind?.();
  } catch (e) {
    if (request !== workspaceRequest || currentRoute() !== route) return;
    lastWorkspaceRoute = null;
    $('#app').innerHTML = workspacePage(kind, activeWorkspaceItem(kind, route).item?.label || 'Workspace', `<div class="banner danger" role="alert"><span>${esc(e.message)}</span><button type="button" class="btn-ghost btn-sm" onclick="render()">Try again</button></div>`);
  }
}
const updateWorkspaceAccount = updateAccount;
updateAccount = function() { updateWorkspaceAccount(); renderNavbar(); refreshNavBadges(true); };

/* Shared rows */
// Same source as the marketplace card: the CAD render tinted to the first available finish, else photographs.
function listingThumb(p) {
  const o = p.configurator || {}, visual = o.visual;
  if (visual?.status === 'ready') {
    const material = Object.keys(o.colors_by_material || {})[0], hex = Object.values(o.colors_by_material?.[material] || {})[0] || '#b8c4ca';
    return `<span class="row-thumb"><img src="${esc(visual.thumbnail)}" data-source="${esc(visual.thumbnail)}" data-color="${esc(hex)}" alt="" loading="lazy" decoding="async" onload="tintProductImage(this)"></span>`;
  }
  if (visual && visual.status !== 'none') return `<span class="row-thumb row-thumb-status" title="${visual.status === 'failed' ? 'Preview unavailable' : 'Preparing product preview…'}" role="img" aria-label="${visual.status === 'failed' ? 'Preview unavailable' : 'Preparing product preview'}">${visual.status === 'failed' ? '!' : '<span class="spinner" aria-hidden="true"></span>'}</span>`;
  const src = p.images?.[0]?.thumbnail_url || Object.values(p.color_images || {})[0];
  return `<span class="row-thumb">${src ? `<img src="${esc(src)}" alt="" loading="lazy">` : ''}</span>`;
}
function productRow(p, admin=true) {
  const menu = [p.status === 'approved' ? `<a class="menu-item" href="#product/api-${p.id}">View in marketplace</a>` : '',
    admin && p.status === 'approved' ? `<button type="button" class="menu-item" onclick="manageProduct(${p.id},'unpublish')">Unpublish</button>` : '',
    p.status !== 'archived' ? `<button type="button" class="menu-item" onclick="archiveListing(${p.id})">Archive</button>` : '',
    admin ? `<button type="button" class="menu-item danger-text" onclick="manageProduct(${p.id},'remove')">Remove from marketplace</button>` : ''].join('');
  const review = (admin ? `<button type="button" class="btn-ghost btn-sm" onclick="productDetails(${p.id})">View details</button>` : '') + (admin && p.status === 'pending' ? `<button type="button" class="btn btn-sm" onclick="moderateListing(${p.id},'approve')">Approve</button><button type="button" class="btn-ghost btn-sm" onclick="moderateListing(${p.id},'reject')">Reject</button>` : '');
  const meta = [admin ? p.seller : '', p.category || 'No category'].filter(Boolean).join(' · ');
  const typeBadge = `<span class="listing-type listing-type-${p.listing_type === 'official' ? 'official' : 'community'}">${p.listing_type === 'official' ? 'Official' : 'Community'}</span>`;
  return `<article class="list-row" data-search="${esc([p.title, p.seller, p.category, p.listing_type].join(' ').toLowerCase())}">${listingThumb(p)}<div class="row-main"><span class="row-title">${esc(p.title || 'Untitled draft')}${typeBadge}</span><span class="row-meta">${esc(meta)}</span>${p.rejection_reason ? `<span class="row-note">Review note: ${esc(p.rejection_reason)}</span>` : ''}</div><span class="row-value">${money(p.price_cents / 100)}</span><span class="row-status">${statusBadge(p.status, statusLabel(p.status))}</span><div class="row-actions">${review}${p.status !== 'archived' ? `<a class="btn-ghost btn-sm" href="#edit-listing/${p.id}">Edit</a>` : ''}${menu ? rowMenu('product-menu-' + p.id, menu) : ''}</div></article>`;
}
function hostRow(h) {
  adminHostsCache[h.id] = h;
  const actions = `<button type="button" class="btn-ghost btn-sm" onclick="hostDetails(${h.id})">View details</button>` + (h.status === 'pending' ? `<button type="button" class="btn btn-sm" onclick="adminAction('/admin/hosts/${h.id}/approve','Approve this printing host?',{})">Approve</button><button type="button" class="btn-ghost btn-sm" onclick="rejectHost(${h.id})">Reject</button>`
    : h.status === 'approved' ? `<button type="button" class="btn-ghost btn-sm danger-text" onclick="adminAction('/admin/hosts/${h.id}/suspend','Suspend this host? They stop receiving printing jobs.',{})">Suspend</button>`
    : h.status === 'suspended' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/hosts/${h.id}/restore','Restore this host?',{})">Restore</button>` : '');
  const details = [['Printers', h.printers], ['Technologies', h.technologies], ['Capabilities', h.capabilities], ['Workshop', h.additional], ['Contact', h.contact], ['Submitted', h.submitted_at && safeDate(h.submitted_at)], ['Review note', h.rejection_reason]].filter(([, v]) => v);
  return `<article class="list-row" data-search="${esc([h.name, userName(h.user), h.user.email, h.region, h.materials].join(' ').toLowerCase())}"><span class="row-avatar">${avatarHtml(h.user, 36)}</span><div class="row-main"><span class="row-title">${esc(h.name || userName(h.user))}</span><span class="row-meta">${esc([h.user.email, [h.region, countryLabel(h.country)].filter(Boolean).join(', ')].filter(Boolean).join(' · '))}</span></div><span class="row-value">${esc(h.materials || '—')}${h.active_jobs != null ? `<small>${h.active_jobs} active · ${h.completed_jobs} completed</small>` : ''}</span><span class="row-status">${statusBadge(h.status)}</span><div class="row-actions">${actions}</div><details class="row-details"><summary>Details</summary><dl class="detail-grid">${details.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl></details></article>`;
}
function equipmentRevisionRow(r){
 const before=r.before.printers,after=r.proposal.printers;
 const fingerprint=p=>JSON.stringify(p);
 const removed=before.filter(p=>!after.some(q=>fingerprint(q)===fingerprint(p)));
 const added=after.filter(p=>!before.some(q=>fingerprint(q)===fingerprint(p)));
 return `<article class="panel"><h3>Equipment Update Request · ${esc(r.host)}</h3><p>${esc(r.email)} · Pending Approval</p><div class="ws-columns"><section><h4>Before / Currently approved</h4><ul>${equipmentSummary(before)}</ul></section><section><h4>After / Proposed equipment</h4><ul>${equipmentSummary(after)}</ul></section></div><details><summary>Added, removed or modified specifications</summary><h4>Removed / Previous versions</h4><ul>${equipmentSummary(removed)||'<li>None</li>'}</ul><h4>Added / Modified versions</h4><ul>${equipmentSummary(added)||'<li>None</li>'}</ul></details><div class="actions"><button class="btn btn-sm" onclick="reviewEquipment(${r.id},'approve')">Approve equipment update</button><button class="btn-ghost btn-sm" onclick="reviewEquipment(${r.id},'reject')">Reject equipment update</button></div></article>`;
}
function reviewEquipment(id,decision){const reason=decision==='reject'?prompt('Reason for rejecting this equipment update:'):'';if(reason===null)return;adminAction(`/admin/equipment-revisions/${id}/${decision}`,`${decision==='approve'?'Approve':'Reject'} this equipment update?`,{reason})}
/* Approvals: Pending (the review queues) and Approval history (each past decision, from the activity log).
   Approved hosts, products and printers are still managed in their own pages; history only records decisions. */
const approvalScopeNav = (scope, pending, decided) => `<nav class="segmented scope-nav" aria-label="Approvals"><a class="segment" href="#admin/pending" ${scope === 'active' ? 'aria-current="page"' : ''}>Pending<span class="segment-count">${pending}</span></a><a class="segment scope-history" href="#admin/pending?scope=history" ${scope === 'history' ? 'aria-current="page"' : ''}>${icon('history')}Approval history<span class="segment-count">${decided}</span></a></nav>`;
const APPROVAL_TYPES = [['all', 'All decisions'], ['hosts', 'Host applications'], ['equipment', 'Equipment updates'], ['listings', 'Listings'], ['printers', 'Printers']];
const DECISION_TONES = {approved:['approved', 'Approved'], rejected:['rejected', 'Rejected'], verified:['approved', 'Specs verified'], added:['neutral', 'Added unverified']};
async function approvalHistoryPage() {
  const q = hashQuery(), type = APPROVAL_TYPES.some(([k]) => k === q.type) ? q.type : 'all', page = Math.max(1, parseInt(q.page || '1', 10) || 1);
  const [data, o, suggestions] = await Promise.all([api('/admin/approvals/history?' + new URLSearchParams({type, page})), api('/admin/overview'), api('/admin/printer-suggestions')]);
  const pending = o.pending_hosts + o.products_pending + (o.pending_equipment || 0) + suggestions.length;
  setNavCount('approvals', pending);
  const href = (params) => scopeHref('admin/pending', {scope:'history', type}, params);
  const chips = filterChips('Approval history by type', APPROVAL_TYPES.map(([k, label]) => ({value:k, label, href:href({type:k, page:1}), count:k === 'all' ? Object.values(data.counts).reduce((a, b) => a + b, 0) : data.counts[k]})), type);
  const typeLabel = Object.fromEntries(APPROVAL_TYPES);
  const row = d => `<article class="list-row decision-row"><div class="row-main"><span class="row-title">${d.link ? `<a class="row-link" href="#${esc(d.link)}">${esc(d.title)}</a>` : esc(d.title)}</span><span class="row-meta">${esc(typeLabel[d.type])}${d.submitter ? ` · submitted by ${esc(d.submitter)}` : ''} · reviewed by ${esc(d.reviewer)}</span>${d.reason ? `<span class="row-note">Reason: ${esc(d.reason)}</span>` : ''}</div><span class="row-status">${statusBadge(...DECISION_TONES[d.decision])}</span><time class="decision-time" datetime="${esc(d.created_at)}">${esc(safeDate(d.created_at))}</time></article>`;
  const list = data.items.length ? `<div class="list">${data.items.map(row).join('')}</div>` : `<div class="list">${emptyState('No decisions yet', 'Approvals and rejections are recorded here as soon as they are made.')}</div>`;
  return {title:'Approvals', body:approvalScopeNav('history', pending, Object.values(data.counts).reduce((a, b) => a + b, 0)) + `<p class="muted ws-intro">Every review decision, newest first. Approved hosts, products and printers stay managed in their own pages.</p>` + chips + list + pager(p => href({page:p}), data.page, data.pages)};
}
/* Equipment update review: one row per printer, before → after, changed values highlighted. */
function revisionOtherChanges(r) {
  const out = [];
  if ((r.before.company || '') !== (r.proposal.company || '')) out.push(`Workshop name: ${r.before.company || '—'} → ${r.proposal.company || '—'}`);
  if ((r.before.weekly_hours || null) !== (r.proposal.weekly_hours || null)) out.push(`Weekly hours: ${r.before.weekly_hours || '—'} → ${r.proposal.weekly_hours || '—'}`);
  return out;
}
function revisionTable(r) {
  const {status, removed} = equipmentDiff(r.before.printers, r.proposal.printers);
  const label = {unchanged:['neutral', 'Unchanged'], modified:['pending', 'Modified'], new:['approved', 'Added'], removed:['rejected', 'Removed']};
  const spec = p => `${+p.x} × ${+p.y} × ${+p.z} mm`, mats = p => (p.capabilities || []).join(', ') || 'Not documented';
  const cell = (before, after) => before == null ? esc(after) : before === after ? esc(after) : `<span class="rv-old">${esc(before)}</span> <span class="rv-new">${esc(after)}</span>`;
  const rows = [...r.proposal.printers.map((p, i) => { const old = status[i] === 'modified' ? r.before.printers.find(q => q.manufacturer === p.manufacturer && q.model === p.model) : null; return [status[i], p, old]; }), ...removed.map(p => ['removed', p, null])];
  return `<table class="review-table rv-table"><thead><tr><th>Change</th><th>Printer</th><th>Units</th><th>Build volume</th><th>Approved materials</th></tr></thead><tbody>${rows.map(([st, p, old]) => `<tr class="rv-${st}"><td>${statusBadge(label[st][0], label[st][1])}</td><td><strong>${esc(p.manufacturer + ' ' + p.model)}</strong><small>${p.technology === 'FDM' ? 'FDM' : 'Resin'}${p.model_id ? '' : ' · not in catalogue'}</small></td><td>${cell(old && String(old.quantity), String(p.quantity))}</td><td>${cell(old && spec(old), spec(p))}</td><td>${cell(old && mats(old), mats(p))}</td></tr>`).join('')}</tbody></table>${revisionOtherChanges(r).map(t => `<p class="rv-other">${esc(t)}</p>`).join('')}`;
}
/* Approvals: one card per item with its submitter, how long it has waited and inline decisions. */
function waitingText(value) {
  if (!value) return 'Waiting';
  const hours = Math.max(0, (Date.now() - parseServerDate(value)) / 36e5);
  return hours < 1 ? 'Waiting less than an hour' : hours < 48 ? `Waiting ${Math.round(hours)} hour${Math.round(hours) === 1 ? '' : 's'}` : `Waiting ${Math.round(hours / 24)} days`;
}
function approvalCard({who, since, title, summary, actions, thumb='', details=''}) {
  const old = since && (Date.now() - parseServerDate(since)) / 864e5 >= 3;
  return `<article class="section-card approval-card"><div class="approval-main">${thumb || `<span class="row-avatar">${avatarHtml(who, 40)}</span>`}<div class="approval-copy"><h3>${esc(title)}</h3><p class="approval-summary">${esc(summary)}</p><p class="approval-meta"><span>Submitted by <strong>${esc(userName(who) || 'unknown')}</strong></span><span class="approval-wait ${old ? 'is-old' : ''}">${esc(waitingText(since))}</span></p></div><div class="approval-actions">${actions}</div></div>${details ? `<details class="approval-details"><summary>Compare with the approved equipment</summary>${details}</details>` : ''}</article>`;
}
/* Admin user profile: read-only account settings, printing specs for hosts, filterable activity. */
const USER_ACTIVITY_FILTERS = [['all', 'All activity'], ['purchases', 'Marketplace purchases'], ['completions', 'Order completions'], ['cancellations', 'Cancellations'], ['custom_requests', 'Custom requests'], ['printing', 'Printing log']];
async function adminUserProfile(id) {
  const type = new URLSearchParams(location.hash.split('?')[1] || '').get('type') || 'all';
  const filters = USER_ACTIVITY_FILTERS;
  const [profile, activity, users] = await Promise.all([api('/admin/users/' + id), api(`/admin/users/${id}/activity?type=${encodeURIComponent(filters.some(([k]) => k === type) ? type : 'all')}`), api('/admin/users'), ensureCountries()]);
  const u = profile.user, h = profile.host, index = userIndex(users), item = (k, v) => `<div><dt>${esc(k)}</dt><dd>${v || '<span class="muted">Not provided</span>'}</dd></div>`;
  const available = filters.filter(([k]) => k !== 'printing' || h);
  const account = `<section class="section-card up-card"><header class="card-head"><h2>Account</h2>${statusBadge(u.active ? 'active' : 'suspended', u.active ? 'Active' : 'Suspended')}</header><div class="up-identity">${avatarHtml(u, 56)}<div><strong>${esc(userName(u))}</strong><span class="muted">@${esc(u.username)} · ${esc(roleLabel(u.role))}</span></div></div><dl class="detail-grid">${item('Email', esc(u.email) + ' ' + (u.email_verified ? statusBadge('approved', 'Verified') : statusBadge('pending', 'Not verified')))}${item('Name', esc([u.first_name, u.last_name].filter(Boolean).join(' ')))}${item('Phone', esc(u.phone))}${item('Location', esc([u.city, u.region, countryLabel(u.country)].filter(Boolean).join(', ')))}${item('Member since', esc(safeDate(u.created_at)))}${item('Records', esc(`${profile.counts.orders} orders · ${profile.counts.jobs} printing jobs · ${profile.counts.requests} custom requests · ${profile.counts.listings} listings`))}</dl>${profile.addresses.length ? `<p class="eq-label">Saved addresses</p><div class="up-addresses">${profile.addresses.map(a => `<address class="up-address">${a.is_default ? statusBadge('approved', 'Default') + '<br>' : ''}${addressLines(a).map(esc).join('<br>')}</address>`).join('')}</div>` : ''}</section>`;
  const printers = h ? `<section class="section-card up-card"><header class="card-head"><h2>Printing specs</h2>${statusBadge(h.status)}</header>${h.printers.length ? `<ul class="es-list">${h.printers.map(p => `<li class="es-printer">${printerArt(p, 'sm')}<span><strong>${esc(printerName(p))}${p.quantity > 1 ? ` <span class="eq-qty">× ${p.quantity}</span>` : ''}</strong><small><span class="eq-tech">${techLabel(p.technology)}</span> ${volumeText(p)} · approved for ${esc(p.capabilities.join(', ') || 'no documented materials')}</small></span></li>`).join('')}</ul>` : '<p class="muted">No registered printers.</p>'}<p class="eq-label">Materials &amp; colors</p>${Object.keys(h.inventory).length ? `<ul class="es-list">${Object.entries(h.inventory).map(([m, c]) => `<li class="es-material"><strong>${esc(m)}</strong><span class="eq-dots">${Object.entries(c).map(([n, x]) => colorDot(x, n)).join('') || '<span class="eq-muted">No colors</span>'}</span></li>`).join('')}</ul>` : '<p class="muted">No materials listed.</p>'}</section>` : '';
  const tabs = `<nav class="segmented up-filter" aria-label="Activity type">${available.map(([k, l]) => `<a class="segment" href="#admin/users/${id}${k === 'all' ? '' : '?type=' + k}" aria-pressed="${k === type}" ${k === type ? 'aria-current="true"' : ''}>${esc(l)}</a>`).join('')}</nav>`;
  const log = `<section class="section-card up-card up-activity"><header class="card-head"><h2>Activity</h2><span class="count">${activity.length}</span></header>${tabs}${activityList(activity, index)}</section>`;
  return {title:userName(u), action:'<a class="btn-ghost btn-sm" href="#admin/users">← All users</a>', body:`<div class="up-grid">${account}${printers}</div>${log}`};
}
const activityVerbs = {created:'created', registered:'registered', approved:'approved', approve:'approved', rejected:'rejected', reject:'rejected', archived:'archived', submitted:'submitted', published:'published', accepted:'accepted', printing:'started printing', ready:'marked ready', shipped:'shipped', completed:'completed', cancelled:'cancelled', reopened:'reopened', saved:'saved', updated:'updated', suspend:'suspended', restore:'restored', deleted:'deleted', unpublish:'unpublished', remove:'removed'};
const activityKinds = {profile:'Profile', address:'Address', equipment:'Equipment', printer:'Printer', user:'Account', listing:'Listing', product:'Product', order:'Order', job:'Printing job', host:'Host application', category:'Category', settings:'Settings', request:'Custom request'};
function activityText(a) { const [kind, verb] = a.action.split('.'); return `${activityKinds[kind] || kind} ${activityVerbs[verb] || verb || ''}`.trim(); }
function subjectText(subject, index) { const [kind, id] = String(subject).split(':'); return kind === 'user' && id ? personName(index, Number(id)) : id ? '#' + id : subject; }
/* Activity: one readable sentence per event, a colour per area, grouped by day, the first 40 shown. */
const ACTIVITY_SENTENCES = {
  'order.created':'placed order', 'order.cancelled':'cancelled order', 'order.completed':'completed order (everything received)', 'order.address_changed':'changed the delivery address of order',
  'job.accepted':'accepted printing job', 'job.printing':'started printing job', 'job.ready':'marked ready printing job', 'job.shipped':'shipped printing job', 'job.completed':'confirmed receipt of printing job', 'job.reopened':'returned to the pool printing job',
  'equipment.submitted':'submitted an equipment update', 'equipment.approve':'approved the equipment update of', 'equipment.reject':'rejected the equipment update of', 'equipment.stock_updated':'updated their materials & colors',
  'host.submitted':'applied as a printing host', 'host.approve':'approved the host application of', 'host.reject':'rejected the host application of', 'host.suspend':'suspended host', 'host.restore':'restored host',
  'listing.submitted':'submitted listing', 'listing.approved':'approved listing', 'listing.rejected':'rejected listing', 'listing.archived':'archived listing', 'listing.published':'published listing',
  'product.unpublish':'unpublished product', 'product.remove':'removed product', 'product.cad_attached':'attached a model to product',
  'request.submitted':'submitted custom request', 'request.updated':'updated custom request',
  'profile.updated':'updated their profile', 'address.saved':'saved a delivery address', 'address.deleted':'deleted a delivery address',
  'user.registered':'created an account', 'user.suspend':'suspended', 'user.restore':'restored', 'user.deleted':'deleted account',
  'printer.verified':'verified the specifications of printer', 'printer.suggestion_approved':'added to the catalogue printer', 'category.saved':'saved category', 'settings.updated':'updated marketplace settings'};
const ACTIVITY_AREA = {order:'orders', job:'printing', equipment:'equipment', host:'people', user:'people', profile:'people', address:'people', listing:'listings', product:'listings', request:'requests', printer:'equipment', category:'listings', settings:'people'};
function activitySubject(a, index) {
  const [kind, id] = String(a.subject).split(':');
  if (kind === 'user') return a.action.startsWith('profile.') || a.action.startsWith('address.') || a.action === 'equipment.stock_updated' || a.action === 'equipment.submitted' || (a.action === 'host.submitted') ? '' : personName(index, Number(id));
  if (!id) return a.action === 'category.saved' ? a.subject : '';
  return ({order:'#', job:'#', listing:'#', request:'#'})[kind] ? '#' + id : ['printer_model'].includes(kind) ? '' : '#' + id;
}
const activityDay = value => { const d = parseServerDate(value), today = new Date(); today.setHours(0, 0, 0, 0); const diff = Math.round((today - new Date(d).setHours(0, 0, 0, 0)) / 864e5); return diff === 0 ? 'Today' : diff === 1 ? 'Yesterday' : d.toLocaleDateString(undefined, {weekday:'long', day:'numeric', month:'long', year:diff > 300 ? 'numeric' : undefined}); };
function activityList(items, index) {
  if (!items.length) return emptyState('No activity yet', 'Marketplace events will be recorded here.');
  let day = '', n = 0;
  const rows = items.map(a => {
    const sentence = ACTIVITY_SENTENCES[a.action] || activityText(a).toLowerCase(), area = ACTIVITY_AREA[a.action.split('.')[0]] || 'people', heading = activityDay(a.created_at), more = n++ >= 40 ? ' is-more' : '';
    const head = heading !== day ? `<li class="activity-day${more}" aria-hidden="true">${esc(day = heading)}</li>` : '';
    return head + `<li class="activity-item${more}" data-area="${area}" data-search="${esc([personName(index, a.actor_id), sentence, a.subject, a.detail].join(' ').toLowerCase())}"><span class="activity-dot" aria-hidden="true"></span><p><strong>${esc(personName(index, a.actor_id))}</strong> ${esc(sentence)} <span class="activity-subject">${esc(activitySubject(a, index))}</span>${a.detail ? `<span class="activity-detail">${esc(a.detail)}</span>` : ''}</p><time datetime="${esc(a.created_at)}" title="${esc(safeDate(a.created_at))}">${esc(parseServerDate(a.created_at).toLocaleTimeString(undefined, {hour:'2-digit', minute:'2-digit'}))}</time></li>`;
  }).join('');
  return `<ul class="activity-list${items.length > 40 ? ' is-collapsed' : ''}">${rows}${listEmpty('No activity matches your search.')}</ul>${items.length > 40 ? `<button type="button" class="btn-ghost btn-sm activity-more" onclick="this.previousElementSibling.classList.remove('is-collapsed');this.remove()">Show all ${items.length} events</button>` : ''}`;
}
const statusFilters = (base, values, items, field='status') => [{value:'', label:'All', href:base, count:items.length}, ...values.map(([value, label]) => ({value, label, href:`${base}/${value}`, count:items.filter(i => i[field] === value).length}))];
const filteredList = (id, rows, emptyTitle, emptyText, searchText) => rows.length ? `<div class="list" id="${id}">${rows.join('')}${listEmpty(searchText)}</div>` : `<div class="list">${emptyState(emptyTitle, emptyText)}</div>`;

/* Administrator workspace */
inPageRoutes.add('#admin/orders'); inPageRoutes.add('#admin/pending'); inPageRoutes.add('#admin/requests');
// Available jobs: which approved hosts can take each one now, and why each other one cannot.
function jobEligibility(j, index) {
  if (!j.eligibility) return '';
  const able = j.eligibility.filter(h => !h.reason), unable = j.eligibility.filter(h => h.reason);
  const why = unable.map(h => `${esc(personName(index, h.host_id))}: ${esc(h.reason)}`).join(' · ');
  return `${able.length ? `<span class="muted">Can be made by ${able.map(h => esc(personName(index, h.host_id))).join(', ')}</span>` : statusBadge('rejected', 'No eligible host')}${why ? `<small class="job-ineligible muted">Not eligible: ${why}</small>` : ''}`;
}
// Overview warnings that open the orders behind them (admin/orders?attention=…).
const ORDER_ATTENTION = {'own-order':'Orders with a job accepted by its own buyer, before hosts were barred from their own orders. Nothing is changed automatically: review each job below.',
  unassigned:'Orders with a printing job still waiting for a host, whatever stage the rest of the order has reached.',
  unmatched:'Orders with an available job that no approved host can make with its current printers and stock. The reasons are listed per host below.'};
const adminPages = {
  async 'admin'() {
    const [o, activity, users, suggestions] = await Promise.all([api('/admin/overview'), api('/admin/activity'), api('/admin/users'), api('/admin/printer-suggestions')]), approvals = o.pending_hosts + o.products_pending + (o.pending_equipment || 0) + suggestions.length;
    setNavCount('approvals', approvals);
    const attention = [[o.pending_equipment, 'equipment update awaiting review', 'equipment updates awaiting review', 'admin/pending'], [o.pending_hosts, 'host application', 'host applications', 'admin/pending'], [o.products_pending, 'product listing awaiting review', 'product listings awaiting review', 'admin/pending'], [suggestions.length, 'printer suggestion to review', 'printer suggestions to review', 'admin/pending?type=printers'], [o.available_jobs, 'printing job without a host', 'printing jobs without a host', 'admin/orders?attention=unassigned'], [o.unmatched_jobs, 'available job no approved host can make', 'available jobs no approved host can make', 'admin/orders?attention=unmatched'], [o.self_assigned_jobs, 'job accepted by its own buyer', 'jobs accepted by their own buyer', 'admin/orders?attention=own-order'], [o.custom_requests_new, 'new custom request', 'new custom requests', 'admin/requests/submitted']].filter(([n]) => n);
    setNavCount('requests', o.custom_requests_new || 0);
    const stats = [statCard('Active orders', o.orders_active, 'admin/orders', `${o.orders_history} in Order history`), statCard('Pending orders', o.orders_pending, 'admin/orders/pending', 'Waiting for a printing host'), statCard('Active printing hosts', o.hosts, 'admin/hosts/approved', o.pending_hosts ? `${o.pending_hosts} awaiting review` : ''), statCard('Pending approvals', approvals, 'admin/pending', 'Hosts, equipment, products and printers'), statCard('Published products', o.products_approved, 'admin/products/approved', `${o.products} in total`)];
    return {title:'Overview', body:`<div class="stat-grid">${stats.join('')}</div><div class="ws-columns"><section class="section-card"><header class="card-head"><h2>Needs attention</h2></header>${attention.length ? `<ul class="attention-list">${attention.map(([n, one, many, href]) => `<li><a href="#${href}"><strong>${n}</strong><span>${esc(n === 1 ? one : many)}</span><span class="textlink">Review →</span></a></li>`).join('')}</ul>` : emptyState('All clear', 'Nothing is waiting for an administrator right now.')}</section><section class="section-card"><header class="card-head"><h2>Recent activity</h2><a class="textlink" href="#admin/activity">View all</a></header>${activityList(activity.slice(0, 8), userIndex(users))}</section></div>`};
  },
  async 'admin/products'(route) {
    // Status chips, plus an Official / Community switch (kept in the hash query, so links and reloads keep it).
    const type = new URLSearchParams(location.hash.split('?')[1] || '').get('type') || '', ofType = p => !type || (p.listing_type === 'official' ? 'official' : 'community') === type;
    const selected = route.split('/')[2] || '', every = (await api('/admin/listings')).filter(p => !p.removed), all = every.filter(ofType), items = all.filter(p => !selected || p.status === selected);
    const filters = statusFilters('admin/products', [['pending', 'Pending review'], ['approved', 'Published'], ['draft', 'Draft'], ['rejected', 'Rejected'], ['archived', 'Archived']], all).map(f => ({...f, href:f.href + (type ? '?type=' + type : '')}));
    const base = 'admin/products' + (selected ? '/' + selected : ''), typeSwitch = `<nav class="segmented" aria-label="Listing type">${[['', 'All'], ['official', 'Official'], ['community', 'Community']].map(([v, l]) => `<a class="segment" href="#${base}${v ? '?type=' + v : ''}" aria-pressed="${v === type}" ${v === type ? 'aria-current="true"' : ''}>${l}<span class="segment-count">${v ? every.filter(p => (p.listing_type === 'official' ? 'official' : 'community') === v).length : every.length}</span></a>`).join('')}</nav>`;
    return {title:'Products', action:`<a class="btn btn-sm" href="#admin/create-official">${icon('plus')}Official product</a>`, body:typeSwitch + toolbar(filterChips('Product status', filters, selected), searchBox('product-list', 'Search products')) + filteredList('product-list', items.map(p => productRow(p)), 'No products here', selected ? 'No products have this status.' : 'Create an official product to start the catalogue.', 'No products match your search.')};
  },
  async 'admin/pending'() {
    if (hashQuery().scope === 'history') return approvalHistoryPage();
    const [hosts, listings, revisions, suggestions, users, past] = await Promise.all([api('/admin/hosts?status=pending'), api('/admin/listings'), api('/admin/equipment-revisions'), api('/admin/printer-suggestions'), api('/admin/users'), api('/admin/approvals/history?per_page=1'), ensureCountries()]);
    const products = listings.filter(p => p.status === 'pending' && !p.removed), index = userIndex(users);
    printerSuggestions = suggestions; hosts.forEach(h => { adminHostsCache[h.id] = h; });
    setNavCount('approvals', hosts.length + products.length + revisions.length + suggestions.length);
    const groups = [
      ['hosts', 'Host applications', hosts.map(h => approvalCard({who:h.user, since:h.submitted_at || h.updated_at, title:h.name || userName(h.user), summary:[h.printers, h.technologies, [h.region, countryLabel(h.country)].filter(Boolean).join(', ')].filter(Boolean).join(' · ') || 'No equipment details',
        actions:`<button type="button" class="btn-ghost btn-sm" onclick="hostDetails(${h.id})">View details</button><button type="button" class="btn-ghost btn-sm" onclick="rejectHost(${h.id})">Reject</button><button type="button" class="btn btn-sm" onclick="adminAction('/admin/hosts/${h.id}/approve','Approve this printing host?',{})">Approve</button>`})), ['No applications waiting', 'New printing host applications appear here.']],
      ['equipment', 'Equipment updates', revisions.map(r => { const c = diffCounts(r.before.printers, r.proposal), other = revisionOtherChanges(r); return approvalCard({who:index[r.user_id] || {username:r.host}, since:r.updated_at, title:`Equipment update · ${r.host}`, summary:[...[[c.added, 'added'], [c.modified, 'modified'], [c.removed, 'removed']].filter(([n]) => n).map(([n, l]) => `${n} printer${n === 1 ? '' : 's'} ${l}`), ...other].join(' · ') || 'No changes compared with the approved equipment',
        details:revisionTable(r), actions:`<button type="button" class="btn-ghost btn-sm" aria-label="Reject equipment update" onclick="reviewEquipment(${r.id},'reject')">Reject</button><button type="button" class="btn btn-sm" aria-label="Approve equipment update" onclick="reviewEquipment(${r.id},'approve')">Approve</button>`}); }), ['No equipment updates waiting', 'Equipment revisions that hosts submit appear here.']],
      ['listings', 'Listings', products.map(p => approvalCard({who:index[p.owner_id] || {username:p.seller}, since:p.updated_at || p.created_at, title:p.title || 'Untitled listing', thumb:listingThumb(p), summary:[p.category, money(p.price_cents / 100), p.listing_type === 'official' ? 'Official' : 'Community'].filter(Boolean).join(' · '),
        actions:`<button type="button" class="btn-ghost btn-sm" onclick="productDetails(${p.id})">View details</button><button type="button" class="btn-ghost btn-sm" onclick="moderateListing(${p.id},'reject')">Reject</button><button type="button" class="btn btn-sm" onclick="moderateListing(${p.id},'approve')">Approve</button>`})), ['No listings waiting', 'Listings submitted for review appear here.']],
      ['printers', 'Printer suggestions', suggestions.map((p, n) => approvalCard({who:users.find(u => u.username === p.suggested_by) || {username:p.suggested_by || 'A host'}, since:null, title:`${p.manufacturer} ${p.model}`, summary:`${p.x} × ${p.y} × ${p.z} mm · ${p.technology === 'FDM' ? 'FDM' : 'Resin'} · ${p.origin === 'revision' ? 'from an equipment update' : 'from a host application'}`,
        actions:`<button type="button" class="btn-ghost btn-sm" onclick="approvePrinterSuggestion(${n})">Add as unverified</button><button type="button" class="btn btn-sm" onclick="verifyPrinterSuggestion(${n})">Verify specs</button>`})), ['No printer suggestions', 'Printers typed by hand in applications or equipment updates appear here.']]];
    const asked = new URLSearchParams(location.hash.split('?')[1] || '').get('type'), type = groups.some(([k]) => k === asked) ? asked : (groups.find(([, , rows]) => rows.length) || groups[0])[0];
    const tabs = `<nav class="chips approvals-tabs" aria-label="Pending approvals by type">${groups.map(([k, l, rows]) => `<a class="chip ${k === type ? 'active' : ''}" href="#admin/pending?type=${k}" ${k === type ? 'aria-current="true"' : ''}>${esc(l)}<span>${rows.length}</span></a>`).join('')}</nav>`;
    const [, label, rows, empty] = groups.find(([k]) => k === type), pending = groups.reduce((n, [, , r]) => n + r.length, 0);
    return {title:'Approvals', body:approvalScopeNav('active', pending, past.total) + tabs + `<section class="approvals" aria-label="${esc(label)}">${rows.length ? rows.join('') : `<div class="section-card">${emptyState(...empty)}</div>`}</section>`};
  },
  async 'admin/hosts'(route) {
    const selected = route.split('/')[2] || '', [all] = await Promise.all([api('/admin/hosts'), ensureCountries()]), items = all.filter(h => !selected || h.status === selected);
    const filters = statusFilters('admin/hosts', [['approved', 'Approved'], ['pending', 'Pending'], ['suspended', 'Suspended'], ['rejected', 'Rejected'], ['draft', 'Draft']], all);
    return {title:'Printing hosts', body:toolbar(filterChips('Host status', filters, selected), searchBox('host-list', 'Search hosts')) + filteredList('host-list', items.map(hostRow), 'No printing hosts here', 'Host applications with this status appear here.', 'No hosts match your search.')};
  },
  async 'admin/users'(route) {
    if (/^\d+$/.test(route.split('/')[2] || '')) return adminUserProfile(+route.split('/')[2]);
    const selected = route.split('/')[2] || '', all = await api('/admin/users'), items = all.filter(u => !selected || u.role === selected);
    adminUsersCache = userIndex(all);
    const filters = statusFilters('admin/users', [['buyer', 'Buyers'], ['host', 'Hosts'], ['admin', 'Admins']], all, 'role');
    const row = u => `<article class="list-row" data-search="${esc([u.username, u.email, u.role].join(' ').toLowerCase())}"><span class="row-avatar">${avatarHtml(u, 36)}</span><div class="row-main"><a class="row-title row-link" href="#admin/users/${u.id}">${esc(userName(u))}${u.id === account.id ? ' <span class="muted">(you)</span>' : ''}</a><span class="row-meta">@${esc(u.username)} · ${esc(u.email)}</span></div><span class="row-value"><small>Joined ${parseServerDate(u.created_at).toLocaleDateString()}</small></span><span class="row-status">${statusBadge(u.role, roleLabel(u.role))}${u.active ? '' : statusBadge('suspended', 'Suspended')}${u.email_verified ? '' : statusBadge('pending', 'Unverified')}</span><div class="row-actions">${u.role !== 'admin' ? `<button type="button" class="btn-ghost btn-sm${u.active ? ' danger-text' : ''}" onclick="adminAction('/admin/users/${u.id}/${u.active ? 'suspend' : 'restore'}','${u.active ? 'Suspend this account? The user is signed out.' : 'Restore this account?'}')">${u.active ? 'Suspend' : 'Restore'}</button>` : ''}${rowMenu('user-menu-' + u.id, `<button type="button" class="menu-item danger-text" onclick="deleteUserDialog(${u.id})">Delete account…</button>`)}</div></article>`;
    return {title:'Users', body:toolbar(filterChips('Role', filters, selected), searchBox('user-list', 'Search name, username or email')) + filteredList('user-list', items.map(row), 'No users here', 'No accounts have this role.', 'No users match your search.')};
  },
  async 'admin/orders'(route) {
    // Active orders by default; Order history (completed and cancelled) on request, both by page.
    const q = hashQuery(), legacy = {pending:['active', 'pending'], completed:['history', 'completed'], cancelled:['history', 'cancelled']}[route.split('/')[2]];
    const view = {scope:legacy ? legacy[0] : q.scope === 'history' ? 'history' : 'active', group:legacy ? legacy[1] : q.group || 'all', q:(q.q || '').slice(0, 80), page:Math.max(1, parseInt(q.page || '1', 10) || 1)};
    // attention: only the orders behind an overview warning (switching scope or status shows every order again).
    const attention = ORDER_ATTENTION[q.attention] ? q.attention : '';
    const href = (params = {}) => scopeHref('admin/orders', {scope:view.scope, group:view.group, q:view.q, attention}, params);
    let data;
    try { data = await api('/admin/orders?' + new URLSearchParams({paginated:true, ...view, ...(attention && {attention})})); }
    catch (e) { if (e.status === 422 && view.group !== 'all') { location.replace('#' + href({group:'all', page:1})); return {title:'Orders', body:''}; } throw e; }
    const users = await api('/admin/users'), index = userIndex(users), items = data.items;
    const nav = scopeNav({label:'Orders', base:'admin/orders', data, names:{active:'Active orders', history:'Order history'}});
    const row = o => {
      const titles = o.items.map(i => `${i.quantity} × ${i.title}`);
      const ownOrder = o.jobs.some(j => j.conflict === 'own_order'), unmatched = o.jobs.some(j => j.eligibility && !j.eligibility.some(h => !h.reason));
      const jobs = o.jobs.map(j => `<li><span>${esc(j.item.title)}</span>${statusBadge(j.status)}<span class="muted">${j.host_id ? 'Host: ' + esc(personName(index, j.host_id)) : 'No host yet'}</span>${j.conflict === 'own_order' ? statusBadge('rejected', 'Host is the buyer') : ''}${jobEligibility(j, index)}${jobModel(j)}${j.status === 'accepted' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/jobs/${j.id}/reopen','Return this job to the available pool?')">Reopen job</button>` : ''}</li>`).join('');
      return `<article class="list-row order-row" data-search="${esc([o.reference, personName(index, o.buyer_id), ...titles].join(' ').toLowerCase())}"><div class="row-main"><span class="row-title mono">${esc(o.reference)}</span><span class="row-meta">${esc(personName(index, o.buyer_id))} · ${safeDate(o.created_at)}</span></div><span class="row-main row-summary">${esc(titles[0] || '')}${titles.length > 1 ? ` <span class="muted">+${titles.length - 1} more</span>` : ''}</span><span class="row-value">${money(o.total_cents / 100)}</span><span class="row-status">${statusBadge(o.status)}${ownOrder ? statusBadge('rejected', 'Host is the buyer') : ''}${unmatched ? statusBadge('rejected', 'No eligible host') : ''}</span><div class="row-actions">${['pending', 'accepted'].includes(o.status) ? `<button type="button" class="btn-ghost btn-sm danger-text" onclick="adminAction('/admin/orders/${o.id}/cancel','Cancel order ${esc(o.reference)}? Jobs that have not started printing are cancelled.')">Cancel order</button>` : ''}</div><details class="row-details" ${attention ? 'open' : ''}><summary>Jobs, delivery and history</summary><ul class="job-list">${jobs}</ul><dl class="detail-grid"><div><dt>Contact</dt><dd>${esc(deliveryText(o.contact))}</dd></div><div><dt>Delivery address</dt><dd>${esc(deliveryText(o.address))}</dd></div><div><dt>History</dt><dd>${o.history.map(e => `${esc(safeDate(e.created_at))} · ${esc(e.action)}`).join('<br>') || 'No events yet.'}</dd></div></dl></details></article>`;
    };
    const label = (data.scopes[data.scope].groups.find(g => g.key === data.group) || {}).label;
    const empty = attention ? ['Nothing needs attention', 'No order has this problem any more.'] : data.scope === 'active' && !data.scopes.active.total ? ['No active orders', 'Every order is completed or cancelled. Past orders are in Order history.'] : data.scope === 'history' && !data.scopes.history.total ? ['No order history yet', 'Completed and cancelled orders move here automatically.'] : view.q ? ['No orders match your search', `Nothing here matches “${view.q}”.`] : [`No ${(label || '').toLowerCase()} orders`, 'No order is at this stage right now.'];
    const search = `<form class="search-field" id="admin-order-search" role="search">${icon('search')}<label class="sr-only" for="admin-order-q">Search orders</label><input id="admin-order-q" type="search" name="q" value="${esc(view.q)}" placeholder="Reference or product" autocomplete="off" maxlength="80"></form>`;
    const notice = attention ? `<div class="banner warning attention-filter"><span>${esc(ORDER_ATTENTION[attention])}</span><a class="btn-ghost btn-sm" href="#${scopeHref('admin/orders', {}, {scope:view.scope})}">Show all orders</a></div>` : '';
    return {title:'Orders', body:nav.primary + toolbar(nav.secondary, search) + notice + (items.length ? `<div class="list" id="order-list">${items.map(row).join('')}</div>` : `<div class="list">${emptyState(...empty)}</div>`) + pager(page => href({page}), data.page, data.pages),
      bind:() => { const form = $('#admin-order-search'); form.onsubmit = e => { e.preventDefault(); location.hash = '#' + href({q:form.elements.q.value.trim(), page:1}); }; }};
  },
  async 'admin/categories'() {
    const cats = await api('/admin/categories');
    const row = c => `<form class="list-row category-edit" data-id="${c.id}"><label class="row-main"><span class="sr-only">Name</span><input name="name" required maxlength="100" value="${esc(c.name)}"></label><label class="row-narrow"><span class="sr-only">Display order</span><input name="sort_order" type="number" min="0" max="10000" value="${c.sort_order}"></label><label class="row-narrow"><span class="sr-only">Visibility</span><select name="active"><option value="true" ${c.active ? 'selected' : ''}>Active</option><option value="false" ${c.active ? '' : 'selected'}>Disabled</option></select></label><div class="row-actions"><button class="btn-ghost btn-sm">Save</button></div></form>`;
    return {title:'Categories', bind:bindOperations, body:`<section class="section-card"><header class="card-head"><div><h2>Product categories</h2><p class="muted">Active categories are offered when listings are created. Renaming a category updates its listings.</p></div></header><div class="list"><div class="list-head" aria-hidden="true"><span class="row-main">Name</span><span class="row-narrow">Order</span><span class="row-narrow">Visibility</span><span class="row-actions"></span></div>${cats.map(row).join('')}<form id="category-form" class="list-row add-row"><label class="row-main"><span class="sr-only">New category name</span><input name="name" required maxlength="100" placeholder="New category name"></label><label class="row-narrow"><span class="sr-only">Display order</span><input name="sort_order" type="number" min="0" max="10000" value="0"></label><span class="row-narrow"></span><div class="row-actions"><button class="btn btn-sm">${icon('plus')}Add</button></div></form></div></section>`};
  },
  async 'admin/settings'() {
    const s = await api('/settings');
    return {title:'Settings', bind:bindOperations, body:`<form id="settings-form" class="section-card settings-form"><header class="card-head"><div><h2>Marketplace</h2><p class="muted">Shown across the site. Currency is EUR and product approval is always required.</p></div></header><div class="fields"><label>Marketplace name<input name="marketplace_name" required maxlength="100" value="${esc(s.marketplace_name)}"></label><label>Public contact information<input name="contact" maxlength="200" value="${esc(s.contact)}"></label><label>Printing host applications<select name="host_applications_open"><option value="true" ${s.host_applications_open ? 'selected' : ''}>Open</option><option value="false" ${s.host_applications_open ? '' : 'selected'}>Closed</option></select></label></div><div class="form-footer"><button class="primary">Save settings</button></div></form>`};
  },
  async 'admin/activity'() {
    const [events, users] = await Promise.all([api('/admin/activity'), api('/admin/users')]);
    return {title:'Activity logs', body:toolbar(`<p class="muted">The latest ${events.length} events, newest first.</p>`, searchBox('activity-list', 'Search activity')) + `<section class="section-card" id="activity-list">${activityList(events, userIndex(users))}</section>`};
  },
  async 'admin/printers'() {
    const [models, suggestions, stats] = await Promise.all([api('/printer-catalogue'), api('/admin/printer-suggestions'), api('/admin/printer-stats')]);
    const volume = p => `${p.x} × ${p.y} × ${p.z} mm`;
    const model = p => `<article class="list-row" data-search="${esc([p.manufacturer, p.model, p.technology].join(' ').toLowerCase())}"><div class="row-main"><span class="row-title">${esc(p.manufacturer + ' ' + p.model)}</span><span class="row-meta">${esc(p.limitations || '')}</span></div><span class="row-value">${esc(volume(p))}<small>${p.technology === 'FDM' ? 'FDM / FFF' : 'Resin'}</small></span><span class="row-status">${p.verified ? statusBadge('approved', 'Verified specs') : statusBadge('pending', 'Unverified')}</span><div class="row-actions">${p.source?.startsWith('http') ? `<a class="btn-ghost btn-sm" href="${esc(p.source)}" target="_blank" rel="noopener">Source ↗</a>` : ''}</div></article>`;
    printerSuggestions = suggestions;
    const suggestion = (p, n) => `<article class="list-row"><div class="row-main"><span class="row-title">${esc(p.manufacturer + ' ' + p.model)}</span><span class="row-meta">${esc([p.origin === 'revision' ? 'Equipment update' : 'Host application', p.suggested_by ? 'by ' + p.suggested_by : '', 'user-provided specifications'].filter(Boolean).join(' · '))}</span></div><span class="row-value">${esc(volume(p))}<small>${p.technology === 'FDM' ? 'FDM / FFF' : 'Resin'}</small></span><div class="row-actions"><button type="button" class="btn-ghost btn-sm" onclick="approvePrinterSuggestion(${n})">Add as unverified</button><button type="button" class="btn btn-sm" onclick="verifyPrinterSuggestion(${n})">Verify specs</button></div></article>`;
    // 1. Available printers: one tile per registered type; hover or focus shows its relative utilisation.
    const busiest = Math.max(0, ...stats.map(t => t.utilisation)), units = stats.reduce((n, t) => n + t.units, 0);
    const tile = t => `<li class="ap-tile" tabindex="0" aria-describedby="ap-tip-${esc(t.manufacturer + t.model).replace(/[^a-z0-9]/gi, '')}">${printerArt(t, 'sm')}<span class="ap-tile-count" aria-label="${t.units} units">${t.units}<small>unit${t.units === 1 ? '' : 's'}</small></span><span class="ap-tile-copy"><small class="ap-maker">${esc(t.manufacturer)}</small><strong>${esc(t.model)}</strong><small>${t.technology === 'FDM' ? 'FDM' : 'Resin'} · ${t.hosts} host${t.hosts === 1 ? '' : 's'}${t.verified ? '' : ' · unverified'}</small></span><span class="ap-tip" role="tooltip" id="ap-tip-${esc(t.manufacturer + t.model).replace(/[^a-z0-9]/gi, '')}"><span class="ap-tip-row"><span>Utilisation</span><strong>${Math.round(t.utilisation * 100)}%</strong></span><span class="ap-bar"><span style="width:${busiest ? Math.round(t.utilisation / busiest * 100) : 0}%"></span></span><span class="ap-tip-note">${busiest ? `Share of active printing jobs, relative to the busiest type` : 'No active printing jobs yet'}</span><span class="ap-tip-row"><span>Registered hosts</span><strong>${t.hosts}</strong></span></span></li>`;
    const available = `<section class="section-card ap-available"><header class="card-head"><h2>Available printers <span class="count">${units} unit${units === 1 ? '' : 's'}</span></h2></header>${stats.length ? `<ul class="ap-tiles">${stats.map(tile).join('')}</ul>` : emptyState('No registered printers', 'Printers of approved hosts appear here.')}</section>`;
    // 2–3. Collapsible sections, closed by default: title, count and arrow highlight together.
    const collapse = (key, title, count, body) => `<details class="ap-collapse section-card" data-collapse="${key}"><summary><span class="ap-collapse-title">${title}</span><span class="ap-collapse-count">· (${count})</span><span class="ap-collapse-arrow" aria-hidden="true">▸</span></summary><div class="ap-collapse-body">${body}</div></details>`;
    const suggested = collapse('suggestions', 'Suggested by hosts', suggestions.length, suggestions.length ? `<div class="list" data-suggestions>${suggestions.map(suggestion).join('')}</div>` : `<div data-suggestions>${emptyState('No suggestions', 'Printers that hosts enter manually, in applications or equipment updates, appear here for review.')}</div>`);
    const catalogue = collapse('catalogue', 'Catalogue', models.length, toolbar('', searchBox('printer-list', 'Search printers')) + filteredList('printer-list', models.map(model), 'No printers', 'The printer catalogue is empty.', 'No printers match your search.'));
    return {title:'Printers', body:available + suggested + catalogue};
  },
  async 'admin/materials'() {
    const items = await api('/materials');
    const group = (tech, label) => `<section class="section-card"><header class="card-head"><h2>${label} <span class="count">${items.filter(m => m.technology === tech).length}</span></h2></header><div class="tag-list">${items.filter(m => m.technology === tech).map(m => `<span class="tag">${esc(m.name)}</span>`).join('')}</div></section>`;
    return {title:'Materials', body:`<p class="muted ws-intro">Hosts choose from these materials when they register equipment; listings and printing jobs are matched by material.</p><div class="ws-columns">${group('FDM', 'FDM / FFF filaments')}${group('RESIN', 'Resins')}</div>`};
  }
};
function deleteUserDialog(id) {
  const u = adminUsersCache[id], self = id === account.id, dialog = $('#modal');
  dialog.innerHTML = `<form id="delete-user-form" class="modal-form"><h2>Delete ${esc(userName(u))}?</h2><p>The account, its host application and its sessions are removed permanently. Accounts with listings, orders, printing jobs or custom requests cannot be deleted.${self ? ' <strong>This is your own account.</strong>' : ''}</p><label>Your administrator password<input name="password" type="password" maxlength="128" autocomplete="current-password" required></label><p class="form-error" role="alert"></p><div class="modal-actions"><button type="button" class="secondary" data-close-modal>Cancel</button><button class="danger">Delete account</button></div></form>`;
  dialog.showModal();
  const form = $('#delete-user-form');
  form.onsubmit = async e => {
    e.preventDefault(); const button = form.querySelector('.danger'); button.disabled = true;
    try {
      await api(self ? '/profile' : `/admin/users/${id}`, {method:'DELETE', body:JSON.stringify({password:new FormData(form).get('password')})});
      dialog.close(); toast('Account deleted');
      if (self) { account = null; csrf = ''; updateAccount(); location.hash = 'account'; }
      render();
    } catch (err) { form.querySelector('.form-error').textContent = err.message; button.disabled = false; }
  };
}
async function manageProduct(id, action) { if (!confirm(action === 'remove' ? 'Remove this product from the marketplace? Historical orders and assets are kept.' : 'Unpublish this product? It returns to draft.')) return; try { const r = await accountAction(`/admin/products/${id}/${action}`, {}); toast(r.message); await refreshPublic(); render(); } catch (e) { showError(e); } }
let printerSuggestions = [];
async function approvePrinterSuggestion(n) {
  const p = printerSuggestions[n];
  const ok = await actionDialog({title:'Add as unverified?', confirm:'Add to catalogue', busy:'Adding…', body:`<div class="ad-job"><div class="ad-job-main"><strong>${esc(p.manufacturer + ' ' + p.model)}</strong><span class="ad-job-meta">${esc(`${p.x} × ${p.y} × ${p.z} mm · ${p.technology}`)}</span></div></div><ul class="ad-notes"><li>The printer joins the catalogue with the host's specifications, marked unverified.</li><li>No materials are assumed: hosts cannot offer any until the specifications are verified.</li></ul>`, run:() => api(p.approve, {method:'POST'})});
  if (ok) { toast('Printer added to the catalogue'); render(); }
}
// Verify specs: the administrator checks every field; the entry is saved as verified.
async function verifyPrinterSuggestion(n) {
  const p = printerSuggestions[n], materials = await api('/materials');
  const checks = tech => materials.filter(m => m.technology === tech).map(m => `<label class="check"><input type="checkbox" name="materials" value="${esc(m.name)}"> ${esc(m.name)}</label>`).join('');
  const body = `<form class="ad-form" id="verify-printer" novalidate><p class="muted">${esc(p.manufacturer + ' ' + p.model)} · suggested ${p.origin === 'revision' ? 'in an equipment update' : 'in a host application'}${p.suggested_by ? ' by ' + esc(p.suggested_by) : ''}</p><div class="fields">${uiSelect({name:'technology', label:'Technology', value:p.technology, className:'cf-select-field wide', options:[['FDM', 'FDM / FFF'], ['RESIN', 'Resin']]})}<label>Build volume X (mm)<input name="x" type="number" min="1" max="5000" step="0.01" required value="${p.x}"></label><label>Y (mm)<input name="y" type="number" min="1" max="5000" step="0.01" required value="${p.y}"></label><label>Z (mm)<input name="z" type="number" min="1" max="5000" step="0.01" required value="${p.z}"></label><label class="wide">Source<input name="source" type="url" required placeholder="https://manufacturer.example/specs"></label><fieldset class="wide verify-materials"><legend>Supported materials</legend><div data-material-checks>${checks(p.technology)}</div></fieldset><label class="wide">Limitations <span class="optional">(optional)</span><textarea name="limitations" rows="2" maxlength="2000"></textarea></label></div></form>`;
  const ok = await actionDialog({title:'Verify printer specifications', confirm:'Save as verified', busy:'Saving…', body, setup:d => {
    d.querySelector('[data-select=technology] input[type=hidden]').addEventListener('change', e => { d.querySelector('[data-material-checks]').innerHTML = checks(e.target.value); });
  }, run:() => {
    const form = $('#verify-printer'); if (!form.reportValidity()) throw Error('Enter the build volume and the source of the specifications.');
    const d = new FormData(form);
    return api(p.approve, {method:'POST', body:JSON.stringify({verify:true, technology:uiSelectValue(form.querySelector('[data-select=technology]')), x:+d.get('x'), y:+d.get('y'), z:+d.get('z'), source:d.get('source').trim(), limitations:d.get('limitations').trim(), materials:d.getAll('materials')})});
  }});
  if (ok) { toast('Printer verified and added to the catalogue'); render(); }
}

/* Printing host workspace */
const nextJobStep = {accepted:['printing', 'Start printing'], printing:['ready', 'Mark ready'], ready:['shipped', 'Mark shipped']};
// "All" lists the categories left to right as the filter chips do: available, accepted, in progress, completed.
const jobOrder = ['available', 'accepted', 'printing', 'ready', 'shipped', 'completed', 'cancelled'];
// One colour per category: available, everything the host is working on, completed (tokens in style.css).
const JOB_CATEGORY = {available:'available', accepted:'active', printing:'active', ready:'active', shipped:'active', completed:'completed', cancelled:'cancelled'};
const JOB_LABELS = {available:'Available', accepted:'Accepted', printing:'Printing', ready:'Ready', shipped:'Shipped', completed:'Completed', cancelled:'Cancelled'};
const jobBadge = (status, note = true) => `<span class="status job-status job-${JOB_CATEGORY[status] || 'cancelled'}">${esc(JOB_LABELS[status] || statusText(status))}</span>${note && status === 'shipped' ? '<small class="job-status-note">Awaiting buyer confirmation</small>' : ''}`;
const shipmentDetails = s => s ? `<div><dt>Shipment</dt><dd>${esc(s.carrier)} · ${s.tracking_url ? `<a class="textlink" href="${esc(s.tracking_url)}" target="_blank" rel="noopener noreferrer">${esc(s.tracking_number)}</a>` : esc(s.tracking_number)}${s.note ? `<br><span class="muted">${esc(s.note)}</span>` : ''}<br><span class="muted">Shipped ${esc(safeDate(s.shipped_at))}</span></dd></div>` : '';
// The model sold with this order line (never the listing's newer uploads). The server re-checks the
// assignment on every download, so the link stops working once the job is completed or reassigned.
const jobModel = j => ['pinned', 'unverified'].includes(j.item.cad_status) ? `<a class="btn-ghost btn-sm" href="/api/jobs/${j.id}/cad" download>Download ${esc(j.item.cad_format || 'model')}</a>` : '';
const jobModelNote = j => j.item.cad_status === 'unverified' ? '<span class="row-meta">Model version not recorded at purchase: this is the model on file when versioning began.</span>' : '';
// The order as both sides name it: the reference the buyer sees on My orders.
const jobOrderRef = j => j.order_reference || `Order #${j.order_id}`;
const jobSearchText = j => [j.item.title, j.item.material, colorName(j.item.color), jobOrderRef(j), 'order ' + j.order_id].join(' ').toLowerCase();
// The host's next step on a job: accept it, or move it one stage on. Steps always go through jobAction's dialog.
const jobStep = j => j.status === 'available' ? ['accept', 'Accept job'] : j.host_id === account.id && nextJobStep[j.status];
const jobStepButton = (j, className = 'btn btn-sm') => { const step = jobStep(j); return step ? `<button type="button" class="${className}" data-job="${j.id}" aria-haspopup="dialog" onclick="jobAction(${j.id},'${step[0]}')">${step[1]}</button>` : ''; };
const jobDownload = (j, className) => j.host_id === account.id && ['accepted', 'printing', 'ready'].includes(j.status) && ['pinned', 'unverified'].includes(j.item.cad_status) ? `<a class="${className}" href="/api/jobs/${j.id}/cad" download>Download ${esc(j.item.cad_format || 'model')}</a>` : '';
const jobTracking = s => s ? (s.tracking_url ? `<a class="textlink" href="${esc(s.tracking_url)}" target="_blank" rel="noopener noreferrer">${esc(s.tracking_number)}</a>` : esc(s.tracking_number)) : '';
// When the job reached its current stage: the closest thing to a deadline the marketplace records.
const JOB_SINCE = {available:'Listed', accepted:'Accepted', printing:'Printing started', ready:'Printed', shipped:'Shipped', completed:'Completed', cancelled:'Cancelled'};
const jobSince = j => JOB_SINCE[j.status] ? `${JOB_SINCE[j.status]} ${timeAgo(j.status === 'shipped' && j.shipment?.shipped_at || j.updated_at)}` : '';
/* Job card, shared by the Printing jobs board and the overview: what to make, in which material and
   colour, for which order, since when, and the one next step. Everything else is in Details. */
function jobCard(j, level = 3) {
  const i = j.item, shipped = j.status === 'shipped' && j.shipment;
  return `<li class="wf-card job-card" data-job-card="${j.id}" data-search="${esc(jobSearchText(j))}"><div class="wf-card-main">${orderLineThumb(i)}<div class="wf-card-copy"><h${level} class="wf-card-title">${esc(i.title)}</h${level}></div></div><p class="wf-card-config">${orderLineConfig(i)}<span class="wf-qty">× ${i.quantity}</span></p><p class="wf-card-ref">Order ${esc(jobOrderRef(j))}</p><p class="wf-card-meta"><span>${money(i.price_cents * i.quantity / 100)}</span><span>${esc(jobSince(j))}</span></p>${shipped ? `<p class="wf-card-note">${esc(j.shipment.carrier)} · Tracking ${jobTracking(j.shipment)}</p>` : ''}<div class="wf-card-links"><button type="button" class="wf-link" data-job-details="${j.id}" aria-haspopup="dialog">Details<span class="sr-only"> for ${esc(i.title)}</span></button>${jobDownload(j, 'wf-link')}</div>${jobStepButton(j, 'btn btn-sm wf-primary')}</li>`;
}
// Job history: one compact row per job, with the product, its configuration and the outcome.
function jobRow(j) {
  const i = j.item;
  return `<article class="list-row job-row" data-search="${esc(jobSearchText(j))}">${orderLineThumb(i)}<div class="row-main"><span class="row-title">${esc(i.title)} × ${i.quantity}</span><span class="row-meta job-meta">${orderLineConfig(i)}<span>${esc([i.dimensions, jobOrderRef(j)].filter(Boolean).join(' · '))}</span></span></div><span class="row-value">${money(i.price_cents * i.quantity / 100)}<small>${money(i.price_cents / 100)} / unit</small></span><span class="row-status">${jobBadge(j.status)}<small class="job-status-note">${esc(safeDate(j.updated_at))}</small></span><div class="row-actions"><button type="button" class="btn-ghost btn-sm" data-job-details="${j.id}" aria-haspopup="dialog">Details<span class="sr-only"> for ${esc(i.title)}</span></button></div></article>`;
}
/* Job steps are confirmed in a site-styled dialog (not the browser's confirm box) that shows which
   job changes and what the step means for the buyer. */
let hostJobs = {};
const rememberJobs = jobs => { hostJobs = Object.fromEntries(jobs.map(j => [j.id, j])); };
const JOB_STEPS = {
  accept:{title:'Accept this printing job?', confirm:'Accept job', busy:'Accepting…', done:'Job accepted', notes:['You commit to printing this item in the material and colour shown.', 'The buyer’s contact and delivery details become visible to you.', 'Agree payment and delivery directly with the buyer before printing.']},
  printing:{title:'Start printing?', confirm:'Start printing', busy:'Updating…', done:'Printing started', notes:['The buyer sees that production has started.', 'Use the model from this job: it is the exact version the buyer ordered.']},
  ready:{title:'Mark as ready for delivery?', confirm:'Mark ready', busy:'Updating…', done:'Marked ready for delivery', notes:['The buyer is told the item is ready.', 'Pack it, then mark it shipped with the tracking details.']},
  shipped:{title:'Mark as shipped?', confirm:'Mark shipped', busy:'Updating…', done:'Marked as shipped', notes:['The buyer sees the carrier and tracking details below.', 'The job completes when the buyer confirms they received it.', 'The model download is no longer available.'], form:true}
};
// Shipped sits under "In progress"; the last step completes only when the buyer confirms receipt.
const JOB_FLOW = [['accepted', 'Accepted'], ['printing', 'Printing'], ['ready', 'Ready'], ['shipped', 'Shipped'], ['completed', 'Completed']];
const shipmentForm = () => `<form class="ad-form" id="shipment-form" novalidate><div class="fields"><label>Carrier or delivery method<input name="carrier" required maxlength="80" autocomplete="off" placeholder="e.g. DHL, Poste Italiane, courier"></label><label>Tracking number<input name="tracking_number" required maxlength="80" autocomplete="off"></label><label class="wide"><span>Tracking link <span class="optional">(optional)</span></span><input name="tracking_url" type="url" maxlength="500" placeholder="https://"></label><label class="wide"><span>Note for the buyer <span class="optional">(optional)</span></span><textarea name="note" rows="2" maxlength="500"></textarea></label></div></form>`;
function shipmentInput(form) {
  if (!form.reportValidity()) throw Error('Enter the carrier and tracking number.');
  const d = Object.fromEntries(new FormData(form));
  if (d.tracking_url && !/^https?:\/\//i.test(d.tracking_url.trim())) { form.elements.tracking_url.focus(); throw Error('The tracking link must start with http:// or https://'); }
  return Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.trim()]));
}
function jobSummary(j, action) {
  if (!j) return '';
  const i = j.item, hex = /^#[0-9a-f]{6}$/i.test(i.color_hex || '') ? i.color_hex : '';
  const target = action === 'accept' ? 'accepted' : action, reached = JOB_FLOW.findIndex(([s]) => s === target);
  return `<div class="ad-job"><div class="ad-job-main"><strong>${esc(i.title)} × ${i.quantity}</strong><span class="ad-job-meta">${hex ? `<span class="ad-swatch" style="--swatch:${hex}" aria-hidden="true"></span>` : ''}${esc([i.material, colorName(i.color)].filter(Boolean).join(' · '))}</span><span class="ad-job-meta">${esc([i.dimensions, 'Order #' + j.order_id].filter(Boolean).join(' · '))}</span></div><strong class="ad-job-value">${money(i.price_cents * i.quantity / 100)}</strong></div>
    <ol class="ad-flow" aria-label="Job progress">${JOB_FLOW.map(([s, label], n) => `<li class="${n < reached ? 'done' : n === reached ? 'next' : ''}"${n === reached ? ' aria-current="step"' : ''}><span aria-hidden="true"></span>${label}${s === 'completed' ? '<small>Awaiting buyer confirmation</small>' : ''}</li>`).join('')}</ol>`;
}
/** A themed confirmation. run() does the work; errors stay in the dialog. Resolves true on success. */
function actionDialog({title, body, confirm, busy, run, setup, initialFocus}) {
  return new Promise(resolve => {
    let d = $('#action-dialog');
    if (!d) { d = document.createElement('dialog'); d.id = 'action-dialog'; d.className = 'ad-dialog'; d.setAttribute('aria-labelledby', 'ad-title'); document.body.append(d); keepFocusInside(d); }
    d.innerHTML = `<div class="ad"><header class="ad-head"><h2 id="ad-title">${esc(title)}</h2><button type="button" class="icon-btn" data-ad-cancel aria-label="Close">${icon('close')}</button></header><div class="ad-body">${body}<p class="ad-error" role="alert"></p></div><div class="ad-foot"><button type="button" class="btn-ghost" data-ad-cancel>Cancel</button><button type="button" class="primary" data-ad-confirm>${esc(confirm)}</button></div></div>`;
    let working = false, result = false;
    const button = d.querySelector('[data-ad-confirm]'), error = d.querySelector('.ad-error');
    const finish = ok => { result = ok; document.documentElement.classList.remove('dialog-open'); d.close(); };
    d.onclose = () => resolve(result);
    d.oncancel = e => { e.preventDefault(); if (!working) finish(false); };   // Escape
    let outside = false; d.onpointerdown = e => { outside = e.target === d; };
    d.onclick = async e => {
      if (working) return;
      if ((e.target === d && outside) || e.target.closest('[data-ad-cancel]')) return finish(false);
      if (!e.target.closest('[data-ad-confirm]')) return;
      working = true; button.disabled = true; button.textContent = busy; error.textContent = '';
      try { await run(); finish(true); }
      catch (err) { working = false; button.disabled = false; button.textContent = confirm; error.textContent = err.message || 'Something went wrong. Please try again.'; }
    };
    document.documentElement.classList.add('dialog-open');
    // Enter inside a form in the dialog confirms instead of submitting the page.
    d.querySelector('form')?.addEventListener('submit', e => { e.preventDefault(); button.click(); });
    d.querySelector('form')?.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.matches('input:not(.cf-input):not(.country-search)')) { e.preventDefault(); button.click(); } });
    setup?.(d);
    d.showModal(); ((initialFocus && d.querySelector(initialFocus)) || d.querySelector('.ad-body input:not([type=hidden]), .ad-body .cf-trigger') || button).focus();
  });
}
// Overrides the browser confirm box from operations.js.
jobAction = async function(id, action) {
  const step = JOB_STEPS[action], trigger = document.activeElement, stage = $(`[data-job-card="${id}"]`)?.closest('.wf-column')?.dataset.stage;
  if (!step) return;
  let refused = false;
  const ok = await actionDialog({title:step.title, confirm:step.confirm, busy:step.busy,
    body:`${jobSummary(hostJobs[id], action)}<ul class="ad-notes">${step.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>${step.form ? shipmentForm() : ''}`,
    run:async () => {
      const extra = step.form ? shipmentInput($('#shipment-form')) : {};
      try { return await api(`/host/jobs/${id}/${action === 'accept' ? 'accept' : 'status'}`, {method:'POST', ...(action === 'accept' ? {} : {body:JSON.stringify({status:action, ...extra})})}); }
      // Taken meanwhile, or no longer one this host may accept (stock or equipment changed):
      // the reason stays in the dialog, and the list is refreshed when it closes.
      catch (e) { refused = action === 'accept' && [403, 404, 409].includes(e.status); throw e; }
    }});
  if (!ok && !refused) { if (trigger?.isConnected) trigger.focus(); return; }
  if (ok) toast(step.done);
  // Return focus to the same job once the board has refreshed: its next step, or its card when it has
  // none left (shipped); a job that left the board (taken meanwhile) hands focus to the column it was in,
  // or to the selected view when the board is now empty.
  const app = $('#app'), watch = new MutationObserver(() => { const next = app.querySelector(`[data-job="${id}"]`) || app.querySelector(`[data-job-details="${id}"]`) || (stage && app.querySelector(`.wf-column[data-stage="${stage}"]`)) || app.querySelector('.ws-main .scope-nav [aria-current]'); if (next && !app.querySelector('.ws-main[aria-busy]')) { watch.disconnect(); next.focus(); } });
  watch.observe(app, {childList:true, subtree:true}); setTimeout(() => watch.disconnect(), 3000);
  render();
};
/* Host jobs: Active jobs (what to accept, make and ship) and Job history (completed and cancelled),
   split by the API (app/lifecycle.py). A shipped job stays active until its buyer confirms receipt. */
inPageRoutes.add('#host/jobs');
const HOST_SCOPE_NAMES = {active:'Active jobs', history:'Job history'};
// Earlier links named the status in the path (#host/jobs/accepted); they open the same view.
const LEGACY_JOB_PATHS = {available:['active', 'available'], accepted:['active', 'accepted'], 'in-progress':['active', 'in-progress'], ready:['active', 'ready'], shipped:['active', 'shipped'], completed:['history', 'completed'], cancelled:['history', 'cancelled']};
function hostJobsView(route) {
  const q = hashQuery(), legacy = LEGACY_JOB_PATHS[route.split('/')[2]];
  return {scope:legacy ? legacy[0] : q.scope === 'history' ? 'history' : 'active', group:legacy ? legacy[1] : q.group || 'all', q:(q.q || '').slice(0, 80), page:Math.max(1, parseInt(q.page || '1', 10) || 1)};
}
const hostJobsHref = (view, params = {}) => scopeHref('host/jobs', {scope:view.scope, group:view.group, q:view.q}, params);
// One sentence per stage under its column title (the stages themselves come from the API).
const HOST_STAGE_HINTS = {available:'Fits one of your approved printers and a colour you stock.', accepted:'Start printing when you are ready.', 'in-progress':'Mark it ready once printed.', ready:'Pack it, then add the tracking details.', shipped:'Completes when the buyer confirms receipt. Nothing to do.'};
const hostStages = data => data.scopes.active.groups.map(g => ({...g, hint:HOST_STAGE_HINTS[g.key] || ''}));
// Job progress as the buyer will see it, with the current stage marked.
function jobFlow(j) {
  const reached = j.status === 'completed' ? JOB_FLOW.length : JOB_FLOW.findIndex(([s]) => s === j.status);
  return `<ol class="ad-flow" aria-label="Job progress">${JOB_FLOW.map(([s, label], n) => `<li class="${n < reached ? 'done' : n === reached ? 'next' : ''}"${n === reached ? ' aria-current="step"' : ''}><span aria-hidden="true"></span>${label}${s === 'completed' ? '<small>Buyer confirms receipt</small>' : ''}</li>`).join('')}</ol>`;
}
// Everything about one job, read-only, with its next step in the footer.
function jobDetails(id) {
  const j = hostJobs[id]; if (!j) return;
  const i = j.item, step = jobStep(j), dimensions = i.dimensions ? reviewItem('Dimensions', esc(i.dimensions)) : '';
  const product = `<div class="detail-product">${orderLineThumb(i, 'detail-thumb')}<div><strong>${esc(i.title)}</strong>${orderLineConfig(i)}<span class="muted">Quantity ${i.quantity} · ${money(i.price_cents / 100)} each · ${money(i.price_cents * i.quantity / 100)} in total</span></div></div><dl class="detail-grid">${reviewItem('Order', esc(jobOrderRef(j)))}${reviewItem('Status', jobBadge(j.status, false))}${dimensions}${reviewItem('Last update', esc(safeDate(j.updated_at)))}</dl>`;
  const model = jobDownload(j, 'btn-ghost btn-sm') ? reviewSection('Model', `<p class="muted">The exact model version the buyer ordered.</p><div class="actions">${jobDownload(j, 'btn-ghost btn-sm')}</div>${jobModelNote(j)}`) : '';
  const delivery = j.fulfillment ? reviewSection('Buyer contact and delivery', `<dl class="detail-grid"><div><dt>Contact</dt><dd>${esc(deliveryText(j.fulfillment.contact))}</dd></div><div><dt>Delivery address</dt><dd>${esc(deliveryText(j.fulfillment.address))}</dd></div>${shipmentDetails(j.shipment)}</dl><p class="muted">Agree payment and delivery directly with the buyer before printing.</p>`)
    : j.status === 'available' ? reviewSection('Before you accept', '<ul class="ad-notes"><li>You commit to printing this item in the material and colour shown.</li><li>The buyer’s contact and delivery details become visible once the job is yours.</li><li>Agree payment and delivery directly with the buyer before printing.</li></ul>') : '';
  const dialog = openReview(i.title, `Printing job · ${jobOrderRef(j)}`, reviewSection('Product', product) + reviewSection('Progress', jobFlow(j)) + model + delivery, step ? `<button type="button" class="btn btn-sm" data-details-step>${step[1]}</button>` : '');
  // The confirmation replaces the details, so only one dialog is open at a time.
  dialog.querySelector('[data-details-step]')?.addEventListener('click', () => { dialog.close(); jobAction(j.id, step[0]); });
}
document.addEventListener('click', e => { const b = e.target.closest('[data-job-details]'); if (b) jobDetails(+b.dataset.jobDetails); });
const hostPages = {
  async 'host'() {
    const [data, listings] = await Promise.all([api('/host/jobs?scope=active'), api('/listings/mine')]), jobs = data.items; rememberJobs(jobs);
    const mine = jobs.filter(j => j.host_id === account.id), available = jobs.filter(j => j.status === 'available');
    setNavCount('jobs', available.length);
    const rejected = listings.filter(p => p.status === 'rejected').length, pending = listings.filter(p => p.status === 'pending').length, done = data.scopes.history.groups.find(g => g.key === 'completed')?.count || 0;
    const stats = [statCard('Available jobs', available.length, 'host/jobs?group=available', 'Matching your printers and materials'), statCard('Active jobs', mine.length, 'host/jobs', 'Accepted, in production or shipped'), statCard('Completed', done, 'host/jobs?scope=history&group=completed', 'In your job history'), statCard('Published listings', listings.filter(p => p.status === 'approved').length, 'my-listings', pending ? `${pending} awaiting review` : '')];
    const notices = [rejected ? `<div class="banner warning"><span>${rejected === 1 ? 'One listing was' : rejected + ' listings were'} returned by an administrator with review notes.</span><a class="btn-ghost btn-sm" href="#my-listings">Review listings</a></div>` : ''].join('');
    // The same stages and cards as Printing jobs, without the available pool: a summary of the host's own work.
    const board = workflowBoard({id:'host-overview-board', label:'Your active jobs', stages:hostStages(data).filter(s => s.key !== 'available'), items:mine, card:jobCard, level:3, limit:3, className:'wf-compact',
      more:(c, n) => `<a class="wf-more" href="#host/jobs?group=${c.key}">${n} more in Printing jobs</a>`});
    return {title:'Overview', action:available.length ? `<a class="btn btn-sm" href="#host/jobs?group=available">View ${available.length} available job${available.length === 1 ? '' : 's'}</a>` : '', body:`${notices}<div class="stat-grid">${stats.join('')}</div><section class="wf-section" aria-labelledby="host-overview-title"><header class="wf-section-head"><div><h2 id="host-overview-title">Your active jobs</h2><p class="muted">Agree payment and delivery directly with the buyer before printing.</p></div><a class="textlink" href="#host/jobs?scope=history">${icon('history')} Job history</a></header>${mine.length ? board : `<div class="section-card">${emptyState('No active jobs', available.length ? 'Accept an available job to start printing.' : 'New jobs matching your printers and materials will appear in Printing jobs.', available.length ? '<a class="btn btn-sm" href="#host/jobs?group=available">Browse available jobs</a>' : '')}</div>`}</section>`,
      bind:() => bindWorkflowBoards()};
  },
  async 'host/jobs'(route) {
    const view = hostJobsView(route), active = view.scope === 'active';
    let data;
    // The board shows every active stage at once (a stage in the address only scrolls to it); history is filtered by page.
    try { data = await api('/host/jobs?' + new URLSearchParams(active ? {scope:'active'} : {scope:'history', group:view.group, q:view.q, page:view.page})); }
    catch (e) { if (e.status === 422 && view.group !== 'all') { location.replace('#' + hostJobsHref(view, {group:'all', page:1})); return {title:'Printing jobs', body:''}; } throw e; }
    rememberJobs(data.items);
    setNavCount('jobs', data.scopes.active.groups.find(g => g.key === 'available').count);
    const nav = scopeNav({label:'Printing jobs', base:'host/jobs', data, names:HOST_SCOPE_NAMES});
    if (active) {
      const intro = '<p class="muted ws-intro">Accept jobs that fit your approved printers and stocked colours, then move each one through production to shipping. Jobs from your own orders are never listed. Completed and cancelled jobs move to Job history.</p>';
      if (!data.items.length) return {title:'Printing jobs', body:`${intro}${nav.primary}<div class="section-card">${emptyState("You're all caught up", 'No jobs to accept or make right now. New order requests matching your printers and materials appear here.', data.scopes.history.total ? `<a class="btn-ghost btn-sm" href="#${hostJobsHref(view, {scope:'history', group:'all', q:'', page:1})}">Job history</a>` : '')}</div>`};
      const board = workflowBoard({id:'host-jobs-board', label:'Active jobs', stages:hostStages(data), items:data.items, card:jobCard, level:2, lane:['shipped'], focus:view.group,
        empty:c => c.key === 'available' ? 'No new jobs match your printers and stock right now.' : 'Nothing here right now.'});
      return {title:'Printing jobs', body:`${intro}<div class="wf-toolbar">${nav.primary}${searchBox('host-jobs-search', 'Search active jobs')}</div><div id="host-jobs-search">${board}${listEmpty('No active jobs match your search.')}</div>`, bind:() => bindWorkflowBoards()};
    }
    const label = (data.scopes.history.groups.find(g => g.key === data.group) || {}).label;
    const empty = !data.scopes.history.total ? ['No job history yet', 'Jobs move here once their buyer confirms receipt, or if they are cancelled.']
      : view.q ? ['No jobs match your search', `Nothing in your job history matches “${view.q}”.`] : [`No ${(label || '').toLowerCase()} jobs`, 'None of your past jobs has this status.'];
    const tools = `<form class="search-field" id="job-history-search" role="search">${icon('search')}<label class="sr-only" for="job-q">Search job history</label><input id="job-q" type="search" name="q" value="${esc(view.q)}" placeholder="Search by product" autocomplete="off" maxlength="80"></form>`;
    const list = data.items.length ? `<div class="list job-history" id="job-list">${data.items.map(jobRow).join('')}</div>` : `<div class="list">${emptyState(...empty)}</div>`;
    return {title:'Printing jobs', body:`<p class="muted ws-intro">Completed and cancelled jobs, with the product, material, colour and shipment they had. Nothing here can be changed.</p>${nav.primary}${toolbar(nav.secondary, tools)}${list}${pager(page => hostJobsHref(view, {page}), data.page, data.pages)}`,
      bind:() => { const form = $('#job-history-search'); form.onsubmit = e => { e.preventDefault(); location.hash = '#' + hostJobsHref(view, {q:form.elements.q.value.trim(), page:1}); }; }};
  },
  async 'my-listings'() {
    const items = (await api('/listings/mine')).filter(p => !p.removed);
    // One way to start a listing: the header action, or the empty state's when there is nothing yet.
    return {title:'My listings', action:items.length ? `<a class="btn btn-sm" href="#create-listing">${icon('plus')}New listing</a>` : '', body:`<p class="muted ws-intro">An administrator reviews every listing before it is published. Changing a published listing sends it back for review.</p>` + (items.length ? `<div class="list">${items.map(p => productRow(p, false)).join('')}</div>` : `<div class="list">${emptyState('No listings yet', 'Create a listing with photographs and a 3D model, then submit it for review.', `<a class="btn btn-sm" href="#create-listing">${icon('plus')}New listing</a>`)}</div>`)};
  },
  'my-printers': equipmentOverview, 'my-printers/materials': equipmentOverview,
  async 'host/profile'() {
    const [h] = await Promise.all([api('/host/application'), ensureCountries()]);
    if (!h) return {title:'Host profile', body:`<div class="list">${emptyState('No host profile', 'Your printing host application could not be found.')}</div>`};
    const rows = [['Status', statusBadge(h.status)], ['Workshop', esc(h.additional || '—')], ['Name', esc(h.name || '—')], ['Contact', esc(h.contact || '—')], ['Service area', esc([h.region, countryLabel(h.country)].filter(Boolean).join(', ') || '—')], ['Technologies', esc(h.technologies || '—')], ['Materials', esc(h.materials || '—')], ['Printers', esc(h.printers || '—')], ['Capacity', esc(h.capabilities || '—')], ['Last review', esc(h.reviewed_at ? safeDate(h.reviewed_at) : '—')]];
    return {title:'Host profile', action:'<a class="btn-ghost btn-sm" href="#account-contact">Edit contact details</a>', body:`<p class="muted ws-intro">Your host profile is built from your account contact details and registered equipment. Update them in <a class="textlink" href="#account-contact">My account</a> and <a class="textlink" href="#my-printers">My equipment</a>.</p><section class="section-card"><dl class="detail-grid wide">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl></section>`};
  }
};

/* Listing editor inside the workspace of the signed-in role. */
listingPage = function(title, body) { return ['admin', 'host'].includes(account?.role) ? workspacePage(account.role, title, body) : layout(head(title, 'Your products') + body); };
// All scripts are loaded: draw the final navigation and page once.
render();


/* Read-only review dialogs for Approvals: everything submitted, before Approve or Reject. */
// reviewItem, reviewSection and openReview are shared building blocks (navigation.js).
async function productDetails(id) {
  try {
    const [listings, users] = await Promise.all([api('/admin/listings'), api('/admin/users')]);
    const p = listings.find(x => x.id === id); if (!p) throw Error('Listing not found');
    const owner = users.find(u => u.id === p.owner_id) || {}, o = p.configurator || {}, visual = o.visual || {};
    let dims = []; try { dims = JSON.parse(p.cad_dimensions || '[]'); } catch (e) {}
    const images = [...(visual.status === 'ready' ? [{url:visual.image, label:'Generated CAD render'}] : []), ...p.images.map((i, n) => ({url:i.url, label:`Photograph ${n + 1}`}))];
    const gallery = images.length ? `<div class="review-gallery">${images.map(i => `<a href="${esc(i.url)}" target="_blank" rel="noopener"><img src="${esc(i.url)}" alt="${esc(i.label)}" loading="lazy"><span>${esc(i.label)}</span></a>`).join('')}</div>` : `<p class="muted">${visual.status && visual.status !== 'none' ? (visual.status === 'failed' ? 'Preview generation failed.' : 'Preview is still being generated.') : 'No images submitted.'}</p>`;
    // Preview the generated GLB when ready; otherwise an STL can be shown directly. 3MF needs the render.
    const previewUrl = visual.status === 'ready' ? visual.model : p.cad_format === 'STL' ? `/api/listings/${p.id}/cad#model.stl` : '';
    const cad = p.has_cad ? `<dl class="detail-grid">${reviewItem('File', esc(p.cad_format + ' model'))}${reviewItem('Measured size (X × Y × Z)', dims.length === 3 ? esc(dims.map(v => +(+v).toFixed(1)).join(' × ') + ' mm') : '')}${reviewItem('Preview status', esc(statusText(visual.status || 'none')))}</dl><div class="actions review-cad-actions">${previewUrl ? '<button type="button" class="btn-ghost btn-sm" data-preview-cad>Preview 3D model</button>' : ''}<a class="btn-ghost btn-sm" href="/api/listings/${p.id}/cad" download>Download ${esc(p.cad_format)}</a></div><div class="review-viewer" data-cad-viewer hidden><p role="status">Loading 3D model…</p></div>` : '<p class="muted">No STL/3MF file uploaded.</p>';
    const factors = o.pricing_materials || {}, base = p.price_cents / 100;
    const pricing = `<table class="review-table"><thead><tr><th>Material</th><th>Unit price</th><th>Currently offered</th></tr></thead><tbody>${Object.entries(factors).map(([m, f]) => `<tr><td>${esc(m)}</td><td>${money(Math.round(p.price_cents * f / 10000) / 100)}</td><td>${o.materials?.[m] ? `Yes · ${Object.keys(o.colors_by_material?.[m] || {}).length} colors` : 'No eligible host'}</td></tr>`).join('')}</tbody></table><dl class="detail-grid">${reviewItem('Base price', money(base) + ' ' + esc(p.currency))}${reviewItem('Quantity discounts', esc(Object.entries(o.discounts || {}).map(([q, d]) => `${q}+ units: −${d / 100}%`).join(', ')))}${reviewItem('Maximum quantity', esc(o.max_quantity))}</dl>`;
    const body = reviewSection('Product', `<dl class="detail-grid wide">${reviewItem('Name', esc(p.title))}${reviewItem('Category', esc(p.category))}${reviewItem('Type', esc(statusText(p.listing_type)))}${reviewItem('Stated dimensions', esc(p.dimensions))}${reviewItem('Compatibility', esc(p.compatibility))}</dl><p class="review-description">${esc(p.description) || '<span class="muted">No description.</span>'}</p>`)
      + reviewSection('Images and previews', gallery) + reviewSection('CAD file', cad) + reviewSection('Materials and pricing', pricing)
      + reviewSection('Submitted by', `<dl class="detail-grid">${reviewItem('Host', esc(userName(owner) || p.seller))}${reviewItem('Email', esc(owner.email))}${reviewItem('Phone', esc(owner.phone))}${reviewItem('Location', esc([owner.city, owner.country].filter(Boolean).join(', ')))}${reviewItem('Role', esc(owner.role ? roleLabel(owner.role) : ''))}</dl>`)
      + reviewSection('Submission', `<dl class="detail-grid">${reviewItem('Status', statusBadge(p.status))}${reviewItem('Created', esc(safeDate(p.created_at)))}${reviewItem('Last updated', esc(safeDate(p.updated_at)))}${reviewItem('Review note', esc(p.rejection_reason))}</dl>`);
    const actions = p.status === 'pending' ? `<button type="button" class="btn-ghost btn-sm" data-review="reject">Reject</button><button type="button" class="btn btn-sm" data-review="approve">Approve</button>` : '';
    const dialog = openReview(p.title || 'Untitled listing', 'Product listing review', body, actions);
    dialog.querySelectorAll('[data-review]').forEach(b => b.onclick = () => { dialog.close(); moderateListing(p.id, b.dataset.review); });
    const previewButton = dialog.querySelector('[data-preview-cad]');
    if (previewButton) previewButton.onclick = () => {
      const host = dialog.querySelector('[data-cad-viewer]'); previewButton.disabled = true; host.hidden = false;
      const material = Object.keys(o.pricing_materials || {})[0], hex = Object.values(o.colors_by_material?.[material] || {})[0] || '#b8c4ca';
      import('./viewer.js?v=studio-3').then(m => m.mountViewer(host, previewUrl, hex, material)).catch(() => { if (host.isConnected) host.innerHTML = '<p role="alert">3D preview unavailable. Download the file to inspect it.</p>'; });
    };
  } catch (e) { showError(e); }
}
function hostDetails(id) {
  const h = adminHostsCache[id]; if (!h) return;
  const u = h.user || {}, printers = h.equipment || [];
  const cards = printers.length ? `<div class="eq eq-grid">${printers.map((p, i) => printerCard(p, 'review-' + id + '-' + i, {badge:p.verified ? statusBadge('approved', 'Verified specs') : statusBadge('pending', 'User-provided specs')})).join('')}</div>` : '<p class="muted">No structured printers registered.</p>';
  const table = printers.length ? `<table class="review-table"><thead><tr><th>Printer</th><th>Technology</th><th>Build volume</th><th>Units</th><th>Supported materials</th><th>Colors in stock</th></tr></thead><tbody>${printers.map(p => `<tr><td>${esc(p.manufacturer + ' ' + p.model)}</td><td>${esc(p.technology)}</td><td>${esc(`${p.x} × ${p.y} × ${p.z} mm`)}</td><td>${p.quantity}</td><td>${esc((p.capabilities || []).join(', ') || 'Not documented')}</td><td>${Object.entries(p.material_colors || {}).map(([m, c]) => `<div><strong>${esc(m)}</strong>: ${Object.keys(c).map(n => esc(colorName(n))).join(', ') || '—'}</div>`).join('') || '<span class="muted">None yet</span>'}</td></tr>`).join('')}</tbody></table>` : '';
  const body = reviewSection('Applicant', `<dl class="detail-grid wide">${reviewItem('Name', esc(h.name || [u.first_name, u.last_name].filter(Boolean).join(' ')))}${reviewItem('Account', esc(userName(u)))}${reviewItem('Email', esc(u.email))}${reviewItem('Phone', esc(u.phone))}${reviewItem('Contact on application', esc(h.contact))}</dl>`)
    + reviewSection('Facility', `<dl class="detail-grid wide">${reviewItem('Workshop / company', esc(h.additional))}${reviewItem('Service area', esc([h.region, countryLabel(h.country)].filter(Boolean).join(', ')))}${reviewItem('Technologies', esc(h.technologies))}${reviewItem('Production capabilities', esc(h.capabilities))}${reviewItem('Build dimensions', esc(h.dimensions))}</dl>`)
    + reviewSection(`Registered printers (${printers.length})`, cards + table + (h.printers ? `<p class="muted">Summary: ${esc(h.printers)}</p>` : ''))
    + reviewSection('Application', `<dl class="detail-grid">${reviewItem('Status', statusBadge(h.status))}${reviewItem('Submitted', esc(h.submitted_at ? safeDate(h.submitted_at) : ''))}${reviewItem('Last updated', esc(h.updated_at ? safeDate(h.updated_at) : ''))}${reviewItem('Review note', esc(h.rejection_reason))}</dl>`);
  const actions = h.status === 'pending' ? `<button type="button" class="btn-ghost btn-sm" data-review="reject">Reject</button><button type="button" class="btn btn-sm" data-review="approve">Approve</button>` : '';
  const dialog = openReview(h.name || userName(u) || 'Host application', 'Printing host application', body, actions);
  dialog.querySelectorAll('[data-review]').forEach(b => b.onclick = () => { dialog.close(); if (b.dataset.review === 'approve') adminAction(`/admin/hosts/${h.id}/approve`, 'Approve this printing host?', {}); else rejectHost(h.id); });
}
