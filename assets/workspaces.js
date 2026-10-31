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
    admin ? `<button type="button" class="menu-item" onclick="setListingType(${p.id},'${p.listing_type === 'official' ? 'community' : 'official'}')">Mark as ${p.listing_type === 'official' ? 'community' : 'official'}</button>` : '',
    admin ? `<button type="button" class="menu-item danger-text" onclick="manageProduct(${p.id},'remove')">Remove from marketplace</button>` : ''].join('');
  const review = (admin ? `<button type="button" class="btn-ghost btn-sm" onclick="productDetails(${p.id})">View details</button>` : '') + (admin && p.status === 'pending' ? `<button type="button" class="btn btn-sm" onclick="moderateListing(${p.id},'approve')">Approve</button><button type="button" class="btn-ghost btn-sm" onclick="moderateListing(${p.id},'reject')">Reject</button>` : '');
  const meta = [admin ? p.seller : '', p.category || 'No category'].filter(Boolean).join(' · ');
  const typeBadge = `<span class="listing-type listing-type-${p.listing_type === 'official' ? 'official' : 'community'}">${p.listing_type === 'official' ? 'Official' : 'Community'}</span>`;
  return `<article class="list-row" data-search="${esc([p.title, p.seller, p.category, p.listing_type].join(' ').toLowerCase())}">${listingThumb(p)}<div class="row-main"><span class="row-title">${esc(p.title || 'Untitled draft')}${typeBadge}</span><span class="row-meta">${esc(meta)}</span>${p.rejection_reason ? `<span class="row-note">Review note: ${esc(p.rejection_reason)}</span>` : ''}</div><span class="row-value">${money(p.price_cents / 100)}</span><span class="row-status">${statusBadge(p.status, statusLabel(p.status))}</span><div class="row-actions">${review}${p.status !== 'archived' ? `<a class="btn-ghost btn-sm" href="#edit-listing/${p.id}">Edit</a>` : ''}${menu ? rowMenu('product-menu-' + p.id, menu) : ''}</div></article>`;
}
function hostRow(h) {
  adminHostsCache[h.id] = h;
  const actions = `<button type="button" class="btn-ghost btn-sm" onclick="hostDetails(${h.id})">View details</button>` + (h.status === 'pending' ? `<button type="button" class="btn btn-sm" onclick="adminAction('/admin/hosts/${h.id}/approve','Approve this printing host?',{})">Approve</button><button type="button" class="btn-ghost btn-sm" onclick="rejectHost(${h.id})">Reject</button>`
    : h.status === 'approved' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/hosts/${h.id}/suspend','Suspend this host? They stop receiving printing jobs.',{})">Suspend</button>`
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
function activityList(items, index) {
  return items.length ? `<ul class="activity-list">${items.map(a => `<li data-search="${esc([personName(index, a.actor_id), activityText(a), a.subject, a.detail].join(' ').toLowerCase())}"><p><strong>${esc(personName(index, a.actor_id))}</strong> ${esc(activityText(a).toLowerCase())} <span class="muted">${esc(subjectText(a.subject, index))}</span>${a.detail ? `<span class="activity-detail">${esc(a.detail)}</span>` : ''}</p><time datetime="${esc(a.created_at)}" title="${esc(safeDate(a.created_at))}">${timeAgo(a.created_at)}</time></li>`).join('')}${listEmpty('No activity matches your search.')}</ul>` : emptyState('No activity yet', 'Marketplace events will be recorded here.');
}
const statusFilters = (base, values, items, field='status') => [{value:'', label:'All', href:base, count:items.length}, ...values.map(([value, label]) => ({value, label, href:`${base}/${value}`, count:items.filter(i => i[field] === value).length}))];
const filteredList = (id, rows, emptyTitle, emptyText, searchText) => rows.length ? `<div class="list" id="${id}">${rows.join('')}${listEmpty(searchText)}</div>` : `<div class="list">${emptyState(emptyTitle, emptyText)}</div>`;

/* Administrator workspace */
const adminPages = {
  async 'admin'() {
    const [o, activity, users] = await Promise.all([api('/admin/overview'), api('/admin/activity'), api('/admin/users')]), approvals = o.pending_hosts + o.products_pending + (o.pending_equipment || 0);
    setNavCount('approvals', approvals);
    const attention = [[o.pending_equipment, 'equipment update awaiting review', 'equipment updates awaiting review', 'admin/pending'], [o.pending_hosts, 'host application', 'host applications', 'admin/pending'], [o.products_pending, 'product listing awaiting review', 'product listings awaiting review', 'admin/pending'], [o.available_jobs, 'printing job without a host', 'printing jobs without a host', 'admin/orders/pending'], [o.custom_requests_new, 'new custom request', 'new custom requests', 'admin/requests/submitted']].filter(([n]) => n);
    setNavCount('requests', o.custom_requests_new || 0);
    const stats = [statCard('Total orders', o.orders, 'admin/orders', `${o.orders_completed} completed`), statCard('Pending orders', o.orders_pending, 'admin/orders/pending', 'Waiting for a printing host'), statCard('Active printing hosts', o.hosts, 'admin/hosts/approved', o.pending_hosts ? `${o.pending_hosts} awaiting review` : ''), statCard('Pending approvals', approvals, 'admin/pending', 'Hosts and products'), statCard('Published products', o.products_approved, 'admin/products/approved', `${o.products} in total`)];
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
    const [hosts, listings, revisions] = await Promise.all([api('/admin/hosts?status=pending'), api('/admin/listings'), api('/admin/equipment-revisions'), ensureCountries()]), products = listings.filter(p => p.status === 'pending' && !p.removed);
    setNavCount('approvals', hosts.length + products.length + revisions.length);
    const section = (title, rows, empty) => `<section class="section-card"><header class="card-head"><h2>${title} <span class="count">${rows.length}</span></h2></header>${rows.length ? `<div class="list">${rows.join('')}</div>` : emptyState(...empty)}</section>`;
    return {title:'Approvals', body:section('Equipment update requests', revisions.map(equipmentRevisionRow), ['No equipment updates waiting', 'Submitted equipment revisions appear here.']) + section('New Host Applications', hosts.map(hostRow), ['No applications waiting', 'New printing host applications appear here.']) + section('Product listings', products.map(p => productRow(p)), ['No listings waiting', 'Listings submitted by printing hosts appear here.'])};
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
    const row = u => `<article class="list-row" data-search="${esc([u.username, u.email, u.role].join(' ').toLowerCase())}"><span class="row-avatar">${avatarHtml(u, 36)}</span><div class="row-main"><a class="row-title row-link" href="#admin/users/${u.id}">${esc(userName(u))}${u.id === account.id ? ' <span class="muted">(you)</span>' : ''}</a><span class="row-meta">@${esc(u.username)} · ${esc(u.email)}</span></div><span class="row-value"><small>Joined ${parseServerDate(u.created_at).toLocaleDateString()}</small></span><span class="row-status">${statusBadge(u.role, roleLabel(u.role))}${u.active ? '' : statusBadge('suspended', 'Suspended')}${u.email_verified ? '' : statusBadge('pending', 'Unverified')}</span><div class="row-actions">${u.role !== 'admin' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/users/${u.id}/${u.active ? 'suspend' : 'restore'}','${u.active ? 'Suspend this account? The user is signed out.' : 'Restore this account?'}')">${u.active ? 'Suspend' : 'Restore'}</button>` : ''}${rowMenu('user-menu-' + u.id, `<button type="button" class="menu-item danger-text" onclick="deleteUserDialog(${u.id})">Delete account…</button>`)}</div></article>`;
    return {title:'Users', body:toolbar(filterChips('Role', filters, selected), searchBox('user-list', 'Search name, username or email')) + filteredList('user-list', items.map(row), 'No users here', 'No accounts have this role.', 'No users match your search.')};
  },
  async 'admin/orders'(route) {
    const selected = route.split('/')[2] || '', [all, users] = await Promise.all([api('/admin/orders'), api('/admin/users')]), index = userIndex(users), items = all.filter(o => !selected || o.status === selected);
    const filters = statusFilters('admin/orders', [['pending', 'Pending'], ['accepted', 'Accepted'], ['printing', 'Printing'], ['ready', 'Ready'], ['shipped', 'Shipped'], ['completed', 'Completed'], ['cancelled', 'Cancelled']], all);
    const row = o => {
      const titles = o.items.map(i => `${i.quantity} × ${i.title}`);
      const jobs = o.jobs.map(j => `<li><span>${esc(j.item.title)}</span>${statusBadge(j.status)}<span class="muted">${j.host_id ? 'Host: ' + esc(personName(index, j.host_id)) : 'No host yet'}</span>${jobModel(j)}${j.status === 'accepted' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/jobs/${j.id}/reopen','Return this job to the available pool?')">Reopen job</button>` : ''}</li>`).join('');
      return `<article class="list-row" data-search="${esc([o.reference, personName(index, o.buyer_id), ...titles].join(' ').toLowerCase())}"><div class="row-main"><span class="row-title mono">${esc(o.reference)}</span><span class="row-meta">${esc(personName(index, o.buyer_id))} · ${safeDate(o.created_at)}</span></div><span class="row-main row-summary">${esc(titles[0] || '')}${titles.length > 1 ? ` <span class="muted">+${titles.length - 1} more</span>` : ''}</span><span class="row-value">${money(o.total_cents / 100)}</span><span class="row-status">${statusBadge(o.status)}</span><div class="row-actions">${['pending', 'accepted'].includes(o.status) ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/orders/${o.id}/cancel','Cancel order ${esc(o.reference)}? Jobs that have not started printing are cancelled.')">Cancel order</button>` : ''}</div><details class="row-details"><summary>Jobs, delivery and history</summary><ul class="job-list">${jobs}</ul><dl class="detail-grid"><div><dt>Contact</dt><dd>${esc(deliveryText(o.contact))}</dd></div><div><dt>Delivery address</dt><dd>${esc(deliveryText(o.address))}</dd></div><div><dt>History</dt><dd>${o.history.map(e => `${esc(safeDate(e.created_at))} · ${esc(e.action)}`).join('<br>') || 'No events yet.'}</dd></div></dl></details></article>`;
    };
    return {title:'Orders', body:toolbar(filterChips('Order status', filters, selected), searchBox('order-list', 'Search reference, buyer or product')) + filteredList('order-list', items.map(row), 'No orders here', 'Order requests with this status appear here.', 'No orders match your search.')};
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
    const tile = t => `<li class="ap-tile" tabindex="0" aria-describedby="ap-tip-${esc(t.manufacturer + t.model).replace(/[^a-z0-9]/gi, '')}">${printerArt(t, 'sm')}<span class="ap-tile-copy"><strong>${esc(t.manufacturer + ' ' + t.model)}</strong><small>${t.technology === 'FDM' ? 'FDM' : 'Resin'}${t.verified ? '' : ' · unverified'}</small></span><span class="ap-tile-count" aria-label="${t.units} units">${t.units}</span><span class="ap-tip" role="tooltip" id="ap-tip-${esc(t.manufacturer + t.model).replace(/[^a-z0-9]/gi, '')}"><span class="ap-tip-row"><span>Utilisation</span><strong>${Math.round(t.utilisation * 100)}%</strong></span><span class="ap-bar"><span style="width:${busiest ? Math.round(t.utilisation / busiest * 100) : 0}%"></span></span><span class="ap-tip-note">${busiest ? `Share of active printing jobs, relative to the busiest type` : 'No active printing jobs yet'}</span><span class="ap-tip-row"><span>Registered hosts</span><strong>${t.hosts}</strong></span></span></li>`;
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
async function setListingType(id, type) { try { await accountAction(`/admin/products/${id}/${type}`, {}); render(); } catch (e) { showError(e); } }
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
const JOB_LABELS = {available:'Available', accepted:'Accepted', printing:'Printing', ready:'Ready', shipped:'Shipped · awaiting buyer confirmation', completed:'Completed', cancelled:'Cancelled'};
const jobBadge = status => `<span class="status job-status job-${JOB_CATEGORY[status] || 'cancelled'}">${esc(JOB_LABELS[status] || statusText(status))}</span>`;
const shipmentDetails = s => s ? `<div><dt>Shipment</dt><dd>${esc(s.carrier)} · ${s.tracking_url ? `<a class="textlink" href="${esc(s.tracking_url)}" target="_blank" rel="noopener noreferrer">${esc(s.tracking_number)}</a>` : esc(s.tracking_number)}${s.note ? `<br><span class="muted">${esc(s.note)}</span>` : ''}<br><span class="muted">Shipped ${esc(safeDate(s.shipped_at))}</span></dd></div>` : '';
// The model sold with this order line (never the listing's newer uploads). The server re-checks the
// assignment on every download, so the link stops working once the job is completed or reassigned.
const jobModel = j => ['pinned', 'unverified'].includes(j.item.cad_status) ? `<a class="btn-ghost btn-sm" href="/api/jobs/${j.id}/cad" download>Download ${esc(j.item.cad_format || 'model')}</a>` : '';
const jobModelNote = j => j.item.cad_status === 'unverified' ? '<span class="row-meta">Model version not recorded at purchase: this is the model on file when versioning began.</span>' : '';
function jobRow(j) {
  const i = j.item, step = j.host_id === account.id && nextJobStep[j.status];
  const action = (j.host_id === account.id && ['accepted', 'printing', 'ready'].includes(j.status) ? jobModel(j) : '') + (j.status === 'available' ? `<button type="button" class="btn btn-sm" data-job="${j.id}" aria-haspopup="dialog" onclick="jobAction(${j.id},'accept')">Accept job</button>` : step ? `<button type="button" class="btn btn-sm" data-job="${j.id}" aria-haspopup="dialog" onclick="jobAction(${j.id},'${step[0]}')">${step[1]}</button>` : '');
  return `<article class="list-row" data-search="${esc([i.title, i.material, colorName(i.color), 'order ' + j.order_id].join(' ').toLowerCase())}"><div class="row-main"><span class="row-title">${esc(i.title)} × ${i.quantity}</span><span class="row-meta">${esc([i.material, colorName(i.color), i.dimensions, 'Order #' + j.order_id].filter(Boolean).join(' · '))}</span>${j.host_id === account.id && ['accepted', 'printing', 'ready'].includes(j.status) ? jobModelNote(j) : ''}</div><span class="row-value">${money(i.price_cents * i.quantity / 100)}<small>${money(i.price_cents / 100)} / unit</small></span><span class="row-status">${jobBadge(j.status)}</span><div class="row-actions">${action}</div>${j.fulfillment ? `<details class="row-details"><summary>Buyer contact and delivery</summary><dl class="detail-grid"><div><dt>Contact</dt><dd>${esc(deliveryText(j.fulfillment.contact))}</dd></div><div><dt>Delivery address</dt><dd>${esc(deliveryText(j.fulfillment.address))}</dd></div>${shipmentDetails(j.shipment)}</dl></details>` : ''}</article>`;
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
function actionDialog({title, body, confirm, busy, run, setup}) {
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
    d.showModal(); (d.querySelector('.ad-body input:not([type=hidden]), .ad-body .cf-trigger') || button).focus();
  });
}
// Overrides the browser confirm box from operations.js.
jobAction = async function(id, action) {
  const step = JOB_STEPS[action], trigger = document.activeElement;
  if (!step) return;
  const ok = await actionDialog({title:step.title, confirm:step.confirm, busy:step.busy,
    body:`${jobSummary(hostJobs[id], action)}<ul class="ad-notes">${step.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>${step.form ? shipmentForm() : ''}`,
    run:() => {
      const extra = step.form ? shipmentInput($('#shipment-form')) : {};
      return api(`/host/jobs/${id}/${action === 'accept' ? 'accept' : 'status'}`, {method:'POST', ...(action === 'accept' ? {} : {body:JSON.stringify({status:action, ...extra})})});
    }});
  if (!ok) { if (trigger?.isConnected) trigger.focus(); return; }
  toast(step.done);
  // Return focus to the same job once the list has refreshed (its next step, or the selected filter).
  const app = $('#app'), watch = new MutationObserver(() => { const next = app.querySelector(`[data-job="${id}"]`) || app.querySelector('.ws-main .chip.active'); if (next && !app.querySelector('.ws-main[aria-busy]')) { watch.disconnect(); next.focus(); } });
  watch.observe(app, {childList:true, subtree:true}); setTimeout(() => watch.disconnect(), 3000);
  render();
};
function jobGroups(jobs) {
  const mine = jobs.filter(j => j.host_id === account.id);
  return {available:jobs.filter(j => j.status === 'available'), accepted:mine.filter(j => j.status === 'accepted'), 'in-progress':mine.filter(j => ['printing', 'ready', 'shipped'].includes(j.status)), completed:mine.filter(j => j.status === 'completed')};
}
const hostPages = {
  async 'host'() {
    const [jobs, listings] = await Promise.all([api('/host/jobs'), api('/listings/mine')]), g = jobGroups(jobs); rememberJobs(jobs);
    setNavCount('jobs', g.available.length);
    const active = [...g.accepted, ...g['in-progress']], rejected = listings.filter(p => p.status === 'rejected').length, pending = listings.filter(p => p.status === 'pending').length;
    const stats = [statCard('Available jobs', g.available.length, 'host/jobs/available', 'Matching your materials'), statCard('Accepted', g.accepted.length, 'host/jobs/accepted', 'Ready to start printing'), statCard('In progress', g['in-progress'].length, 'host/jobs/in-progress', 'Printing, ready or shipped'), statCard('Completed', g.completed.length, 'host/jobs/completed'), statCard('Published listings', listings.filter(p => p.status === 'approved').length, 'my-listings', pending ? `${pending} awaiting review` : '')];
    const notices = [rejected ? `<div class="banner warning"><span>${rejected === 1 ? 'One listing was' : rejected + ' listings were'} returned by an administrator with review notes.</span><a class="btn-ghost btn-sm" href="#my-listings">Review listings</a></div>` : ''].join('');
    return {title:'Overview', action:g.available.length ? `<a class="btn btn-sm" href="#host/jobs/available">View available jobs</a>` : '', body:`${notices}<div class="stat-grid">${stats.join('')}</div><section class="section-card"><header class="card-head"><div><h2>Your active jobs</h2><p class="muted">Agree payment and delivery directly with the buyer before printing.</p></div>${active.length > 5 ? '<a class="textlink" href="#host/jobs">View all</a>' : ''}</header>${active.length ? `<div class="list">${active.slice(0, 5).map(jobRow).join('')}</div>` : emptyState('No active jobs', g.available.length ? 'Accept an available job to start printing.' : 'New jobs matching your materials will appear in Printing jobs.', g.available.length ? '<a class="btn btn-sm" href="#host/jobs/available">Browse available jobs</a>' : '')}</section>`};
  },
  async 'host/jobs'(route) {
    const selected = route.split('/')[2] || '', jobs = await api('/host/jobs'), g = jobGroups(jobs); rememberJobs(jobs);
    setNavCount('jobs', g.available.length);
    const all = jobs.filter(j => j.status === 'available' || j.host_id === account.id).sort((a, b) => jobOrder.indexOf(a.status) - jobOrder.indexOf(b.status));
    const items = selected ? g[selected] || [] : all;
    const filters = [{value:'', label:'All', href:'host/jobs', count:all.length}, ...[['available', 'Available'], ['accepted', 'Accepted'], ['in-progress', 'In progress'], ['completed', 'Completed']].map(([value, label]) => ({value, label, href:'host/jobs/' + value, count:g[value].length}))];
    return {title:'Printing jobs', body:`<p class="muted ws-intro">Jobs are matched to the materials in your approved profile. Check the dimensions before accepting; buyer contact and delivery details appear once a job is yours.</p>` + toolbar(filterChips('Job status', filters, selected), searchBox('job-list', 'Search jobs')) + filteredList('job-list', items.map(jobRow), selected === 'available' ? 'No available jobs' : 'No jobs here', selected === 'available' ? 'New order requests matching your materials will appear here.' : 'Jobs move here as you accept and print them.', 'No jobs match your search.')};
  },
  async 'my-listings'() {
    const items = (await api('/listings/mine')).filter(p => !p.removed);
    return {title:'My listings', action:`<a class="btn btn-sm" href="#create-listing">${icon('plus')}New listing</a>`, body:`<p class="muted ws-intro">An administrator reviews every listing before it is published. Changing a published listing sends it back for review.</p>` + (items.length ? `<div class="list">${items.map(p => productRow(p, false)).join('')}</div>` : `<div class="list">${emptyState('No listings yet', 'Create a listing with photographs and a 3D model, then submit it for review.', '<a class="btn btn-sm" href="#create-listing">Create listing</a>')}</div>`)};
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
const reviewItem = (label, value) => `<div><dt>${esc(label)}</dt><dd>${value || '<span class="muted">—</span>'}</dd></div>`;
const reviewSection = (title, body) => `<section class="review-section"><h3>${esc(title)}</h3>${body}</section>`;
function openReview(title, subtitle, body, actions) {
  const dialog = $('#modal'); dialog.className = 'review-dialog';
  dialog.innerHTML = `<div class="review-frame"><header class="review-head"><div><p class="ws-crumb">${esc(subtitle)}</p><h2>${esc(title)}</h2></div><button type="button" class="icon-btn" data-close-modal aria-label="Close">${icon('close')}</button></header><div class="review-body">${body}</div><footer class="review-foot"><button type="button" class="btn-ghost btn-sm" data-close-modal>Close</button>${actions}</footer></div>`;
  dialog.addEventListener('close', () => { dialog.querySelector('[data-cad-viewer]')?.disposeViewer?.(); dialog.className = ''; }, {once:true});
  dialog.showModal();
  return dialog;
}
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
