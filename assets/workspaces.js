/* Role-aware routing plus the administrator and printing-host workspaces. */
const workspaceRender = render, defaultTitle = document.title;
// Earlier routes stay valid: they redirect to the page that now owns their content.
const routeRedirects = {dashboard:'catalogue', moderation:'admin/pending', 'admin/':'admin', production:'my-printers'};
const signedInRoutes = ['orders', 'basket', 'checkout', 'checkout-cart', 'host', 'admin', 'my-listings', 'my-printers', 'create-listing', 'edit-listing', 'onboarding'];
const hostOnlyRoutes = ['host', 'my-listings', 'my-printers', 'create-listing', 'edit-listing'];
const adminRedirects = ['custom', 'onboarding', 'orders', 'basket', 'checkout', 'checkout-cart', 'create-listing', 'my-listings', 'my-printers', 'host'];
let workspaceRequest = 0, lastWorkspaceRoute = null, adminUsersCache = {};

function accessPage(title, text, actions) { return layout(`<div class="section-card access-card"><h1>${esc(title)}</h1><p>${esc(text)}</p><div class="actions">${actions}</div></div>`); }
function signInPrompt(route) {
  try { sessionStorage.setItem('ol3d-return-to', route); } catch (e) {}
  const text = routeIn(route, 'orders') ? 'Sign in to follow your order requests.' : routeIn(route, 'basket', 'checkout', 'checkout-cart') ? 'Your basket is saved privately in your account.' : routeIn(route, 'admin') ? 'Sign in with an administrator account.' : 'Sign in to apply as a printing host or open your workspace.';
  return accessPage('Sign in to continue', text, '<a class="btn" href="#account">Sign in</a><a class="btn light" href="#account?mode=register">Create account</a>');
}
const userIndex = users => Object.fromEntries(users.map(u => [u.id, u]));
const personName = (index, id) => index[id] ? index[id].display_name || index[id].username : id ? `User #${id}` : 'System';
const colorName = c => c ? colorLabels[c] || c : '';
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
function listingThumb(p) { const src = p.images?.[0]?.thumbnail_url || Object.values(p.color_images || {})[0]; return `<span class="row-thumb">${src ? `<img src="${esc(src)}" alt="" loading="lazy">` : ''}</span>`; }
function productRow(p, admin=true) {
  const menu = [p.status === 'approved' ? `<a class="menu-item" href="#product/api-${p.id}">View in marketplace</a>` : '',
    admin && p.status === 'approved' ? `<button type="button" class="menu-item" onclick="manageProduct(${p.id},'unpublish')">Unpublish</button>` : '',
    p.status !== 'archived' ? `<button type="button" class="menu-item" onclick="archiveListing(${p.id})">Archive</button>` : '',
    admin ? `<button type="button" class="menu-item danger-text" onclick="manageProduct(${p.id},'remove')">Remove from marketplace</button>` : ''].join('');
  const review = admin && p.status === 'pending' ? `<button type="button" class="btn btn-sm" onclick="moderateListing(${p.id},'approve')">Approve</button><button type="button" class="btn-ghost btn-sm" onclick="moderateListing(${p.id},'reject')">Reject</button>` : '';
  const meta = [admin ? p.seller : '', p.category || 'No category', p.listing_type === 'official' ? 'Official' : 'Community'].filter(Boolean).join(' · ');
  return `<article class="list-row" data-search="${esc([p.title, p.seller, p.category, p.listing_type].join(' ').toLowerCase())}">${listingThumb(p)}<div class="row-main"><span class="row-title">${esc(p.title || 'Untitled draft')}</span><span class="row-meta">${esc(meta)}</span>${p.rejection_reason ? `<span class="row-note">Review note: ${esc(p.rejection_reason)}</span>` : ''}</div><span class="row-value">${money(p.price_cents / 100)}</span><span class="row-status">${statusBadge(p.status, statusLabel(p.status))}</span><div class="row-actions">${review}${p.status !== 'archived' ? `<a class="btn-ghost btn-sm" href="#edit-listing/${p.id}">Edit</a>` : ''}${menu ? rowMenu('product-menu-' + p.id, menu) : ''}</div></article>`;
}
function hostRow(h) {
  const actions = h.status === 'pending' ? `<button type="button" class="btn btn-sm" onclick="adminAction('/admin/hosts/${h.id}/approve','Approve this printing host?',{})">Approve</button><button type="button" class="btn-ghost btn-sm" onclick="rejectHost(${h.id})">Reject</button>`
    : h.status === 'approved' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/hosts/${h.id}/suspend','Suspend this host? They stop receiving printing jobs.',{})">Suspend</button>`
    : h.status === 'suspended' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/hosts/${h.id}/restore','Restore this host?',{})">Restore</button>` : '';
  const details = [['Printers', h.printers], ['Technologies', h.technologies], ['Capabilities', h.capabilities], ['Workshop', h.additional], ['Contact', h.contact], ['Submitted', h.submitted_at && safeDate(h.submitted_at)], ['Review note', h.rejection_reason]].filter(([, v]) => v);
  return `<article class="list-row" data-search="${esc([h.name, h.user.display_name, h.user.email, h.region, h.materials].join(' ').toLowerCase())}"><span class="row-avatar">${avatarHtml({...h.user, avatar:''}, 36)}</span><div class="row-main"><span class="row-title">${esc(h.name || h.user.display_name)}</span><span class="row-meta">${esc([h.user.email, [h.region, countryLabel(h.country)].filter(Boolean).join(', ')].filter(Boolean).join(' · '))}</span></div><span class="row-value">${esc(h.materials || '—')}${h.active_jobs != null ? `<small>${h.active_jobs} active · ${h.completed_jobs} completed</small>` : ''}</span><span class="row-status">${statusBadge(h.status)}</span><div class="row-actions">${actions}</div><details class="row-details"><summary>Details</summary><dl class="detail-grid">${details.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl></details></article>`;
}
function equipmentRevisionRow(r){
 const before=r.before.printers,after=r.proposal.printers;
 const fingerprint=p=>JSON.stringify(p);
 const removed=before.filter(p=>!after.some(q=>fingerprint(q)===fingerprint(p)));
 const added=after.filter(p=>!before.some(q=>fingerprint(q)===fingerprint(p)));
 return `<article class="panel"><h3>Equipment Update Request · ${esc(r.host)}</h3><p>${esc(r.email)} · Pending Approval</p><div class="ws-columns"><section><h4>Before / Currently approved</h4><ul>${equipmentSummary(before)}</ul></section><section><h4>After / Proposed equipment</h4><ul>${equipmentSummary(after)}</ul></section></div><details><summary>Added, removed or modified specifications</summary><h4>Removed / Previous versions</h4><ul>${equipmentSummary(removed)||'<li>None</li>'}</ul><h4>Added / Modified versions</h4><ul>${equipmentSummary(added)||'<li>None</li>'}</ul></details><div class="actions"><button class="btn btn-sm" onclick="reviewEquipment(${r.id},'approve')">Approve equipment update</button><button class="btn-ghost btn-sm" onclick="reviewEquipment(${r.id},'reject')">Reject equipment update</button></div></article>`;
}
function reviewEquipment(id,decision){const reason=decision==='reject'?prompt('Reason for rejecting this equipment update:'):'';if(reason===null)return;adminAction(`/admin/equipment-revisions/${id}/${decision}`,`${decision==='approve'?'Approve':'Reject'} this equipment update?`,{reason})}
const activityVerbs = {created:'created', registered:'registered', approved:'approved', approve:'approved', rejected:'rejected', reject:'rejected', archived:'archived', submitted:'submitted', published:'published', accepted:'accepted', printing:'started printing', ready:'marked ready', completed:'completed', cancelled:'cancelled', reopened:'reopened', saved:'saved', updated:'updated', suspend:'suspended', restore:'restored', deleted:'deleted', unpublish:'unpublished', remove:'removed'};
const activityKinds = {user:'Account', listing:'Listing', product:'Product', order:'Order', job:'Printing job', host:'Host application', category:'Category', settings:'Settings'};
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
    const attention = [[o.pending_equipment, 'equipment update awaiting review', 'equipment updates awaiting review', 'admin/pending'], [o.pending_hosts, 'host application', 'host applications', 'admin/pending'], [o.products_pending, 'product listing awaiting review', 'product listings awaiting review', 'admin/pending'], [o.available_jobs, 'printing job without a host', 'printing jobs without a host', 'admin/orders/pending']].filter(([n]) => n);
    const stats = [statCard('Total orders', o.orders, 'admin/orders', `${o.orders_completed} completed`), statCard('Pending orders', o.orders_pending, 'admin/orders/pending', 'Waiting for a printing host'), statCard('Active printing hosts', o.hosts, 'admin/hosts/approved', o.pending_hosts ? `${o.pending_hosts} awaiting review` : ''), statCard('Pending approvals', approvals, 'admin/pending', 'Hosts and products', approvals ? 'attention' : ''), statCard('Published products', o.products_approved, 'admin/products/approved', `${o.products} in total`)];
    return {title:'Overview', body:`<div class="stat-grid">${stats.join('')}</div><div class="ws-columns"><section class="section-card"><header class="card-head"><h2>Needs attention</h2></header>${attention.length ? `<ul class="attention-list">${attention.map(([n, one, many, href]) => `<li><a href="#${href}"><strong>${n}</strong><span>${esc(n === 1 ? one : many)}</span><span class="textlink">Review →</span></a></li>`).join('')}</ul>` : emptyState('All clear', 'Nothing is waiting for an administrator right now.')}</section><section class="section-card"><header class="card-head"><h2>Recent activity</h2><a class="textlink" href="#admin/activity">View all</a></header>${activityList(activity.slice(0, 8), userIndex(users))}</section></div>`};
  },
  async 'admin/products'(route) {
    const selected = route.split('/')[2] || '', all = (await api('/admin/listings')).filter(p => !p.removed), items = all.filter(p => !selected || p.status === selected);
    const filters = statusFilters('admin/products', [['pending', 'Pending review'], ['approved', 'Published'], ['draft', 'Draft'], ['rejected', 'Rejected'], ['archived', 'Archived']], all);
    return {title:'Products', action:`<a class="btn btn-sm" href="#admin/create-official">${icon('plus')}Official product</a>`, body:toolbar(filterChips('Product status', filters, selected), searchBox('product-list', 'Search products')) + filteredList('product-list', items.map(p => productRow(p)), 'No products here', selected ? 'No products have this status.' : 'Create an official product to start the catalogue.', 'No products match your search.')};
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
    const selected = route.split('/')[2] || '', all = await api('/admin/users'), items = all.filter(u => !selected || u.role === selected);
    adminUsersCache = userIndex(all);
    const filters = statusFilters('admin/users', [['buyer', 'Buyers'], ['host', 'Hosts'], ['admin', 'Admins']], all, 'role');
    const row = u => `<article class="list-row" data-search="${esc([u.display_name, u.username, u.email, u.role].join(' ').toLowerCase())}"><span class="row-avatar">${avatarHtml({...u, avatar:''}, 36)}</span><div class="row-main"><span class="row-title">${esc(u.display_name)}${u.id === account.id ? ' <span class="muted">(you)</span>' : ''}</span><span class="row-meta">@${esc(u.username)} · ${esc(u.email)}</span></div><span class="row-value"><small>Joined ${parseServerDate(u.created_at).toLocaleDateString()}</small></span><span class="row-status">${statusBadge(u.role, roleLabel(u.role))}${u.active ? '' : statusBadge('suspended', 'Suspended')}${u.email_verified ? '' : statusBadge('pending', 'Unverified')}</span><div class="row-actions">${u.role !== 'admin' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/users/${u.id}/${u.active ? 'suspend' : 'restore'}','${u.active ? 'Suspend this account? The user is signed out.' : 'Restore this account?'}')">${u.active ? 'Suspend' : 'Restore'}</button>` : ''}${rowMenu('user-menu-' + u.id, `<button type="button" class="menu-item danger-text" onclick="deleteUserDialog(${u.id})">Delete account…</button>`)}</div></article>`;
    return {title:'Users', body:toolbar(filterChips('Role', filters, selected), searchBox('user-list', 'Search name, username or email')) + filteredList('user-list', items.map(row), 'No users here', 'No accounts have this role.', 'No users match your search.')};
  },
  async 'admin/orders'(route) {
    const selected = route.split('/')[2] || '', [all, users] = await Promise.all([api('/admin/orders'), api('/admin/users')]), index = userIndex(users), items = all.filter(o => !selected || o.status === selected);
    const filters = statusFilters('admin/orders', [['pending', 'Pending'], ['accepted', 'Accepted'], ['printing', 'Printing'], ['ready', 'Ready'], ['completed', 'Completed'], ['cancelled', 'Cancelled']], all);
    const row = o => {
      const titles = o.items.map(i => `${i.quantity} × ${i.title}`);
      const jobs = o.jobs.map(j => `<li><span>${esc(j.item.title)}</span>${statusBadge(j.status)}<span class="muted">${j.host_id ? 'Host: ' + esc(personName(index, j.host_id)) : 'No host yet'}</span>${j.status === 'accepted' ? `<button type="button" class="btn-ghost btn-sm" onclick="adminAction('/admin/jobs/${j.id}/reopen','Return this job to the available pool?')">Reopen job</button>` : ''}</li>`).join('');
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
    const [models, suggestions] = await Promise.all([api('/printer-catalogue'), api('/admin/printer-suggestions')]);
    const volume = p => `${p.x} × ${p.y} × ${p.z} mm`;
    const model = p => `<article class="list-row" data-search="${esc([p.manufacturer, p.model, p.technology].join(' ').toLowerCase())}"><div class="row-main"><span class="row-title">${esc(p.manufacturer + ' ' + p.model)}</span><span class="row-meta">${esc(p.limitations || '')}</span></div><span class="row-value">${esc(volume(p))}<small>${p.technology === 'FDM' ? 'FDM / FFF' : 'Resin'}</small></span><span class="row-status">${p.verified ? statusBadge('approved', 'Verified specs') : statusBadge('pending', 'Unverified')}</span><div class="row-actions">${p.source?.startsWith('http') ? `<a class="btn-ghost btn-sm" href="${esc(p.source)}" target="_blank" rel="noopener">Source ↗</a>` : ''}</div></article>`;
    const suggestion = p => `<article class="list-row"><div class="row-main"><span class="row-title">${esc(p.manufacturer + ' ' + p.model)}</span><span class="row-meta">Suggested by a printing host · user-provided specifications</span></div><span class="row-value">${esc(volume(p))}</span><div class="row-actions"><button type="button" class="btn-ghost btn-sm" onclick="approvePrinterSuggestion(${p.id})">Add as unverified</button></div></article>`;
    return {title:'Printers', body:`<section class="section-card"><header class="card-head"><h2>Suggested by hosts <span class="count">${suggestions.length}</span></h2></header>${suggestions.length ? `<div class="list">${suggestions.map(suggestion).join('')}</div>` : emptyState('No suggestions', 'Printers that hosts enter manually appear here for review.')}</section>` + toolbar(`<h2 class="toolbar-title">Catalogue <span class="count">${models.length}</span></h2>`, searchBox('printer-list', 'Search printers')) + filteredList('printer-list', models.map(model), 'No printers', 'The printer catalogue is empty.', 'No printers match your search.')};
  },
  async 'admin/materials'() {
    const items = await api('/materials');
    const group = (tech, label) => `<section class="section-card"><header class="card-head"><h2>${label} <span class="count">${items.filter(m => m.technology === tech).length}</span></h2></header><div class="tag-list">${items.filter(m => m.technology === tech).map(m => `<span class="tag">${esc(m.name)}</span>`).join('')}</div></section>`;
    return {title:'Materials', body:`<p class="muted ws-intro">Hosts choose from these materials when they register equipment; listings and printing jobs are matched by material.</p><div class="ws-columns">${group('FDM', 'FDM / FFF filaments')}${group('RESIN', 'Resins')}</div>`};
  }
};
function deleteUserDialog(id) {
  const u = adminUsersCache[id], self = id === account.id, dialog = $('#modal');
  dialog.innerHTML = `<form id="delete-user-form" class="modal-form"><h2>Delete ${esc(u.display_name)}?</h2><p>The account, its host application and its sessions are removed permanently. Accounts with listings, orders or printing jobs cannot be deleted.${self ? ' <strong>This is your own account.</strong>' : ''}</p><label>Your administrator password<input name="password" type="password" maxlength="128" autocomplete="current-password" required></label><p class="form-error" role="alert"></p><div class="modal-actions"><button type="button" class="secondary" data-close-modal>Cancel</button><button class="danger">Delete account</button></div></form>`;
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
async function approvePrinterSuggestion(id) { if (!confirm('Add this printer to the catalogue as user-provided and unverified?')) return; try { await accountAction('/admin/printer-suggestions/' + id + '/approve', {}); toast('Printer added to the catalogue'); render(); } catch (e) { showError(e); } }

/* Printing host workspace */
const nextJobStep = {accepted:['printing', 'Start printing'], printing:['ready', 'Mark ready'], ready:['completed', 'Mark completed']};
const jobOrder = ['accepted', 'printing', 'ready', 'available', 'completed', 'cancelled'];
function jobRow(j) {
  const i = j.item, step = j.host_id === account.id && nextJobStep[j.status];
  const action = j.status === 'available' ? `<button type="button" class="btn btn-sm" onclick="jobAction(${j.id},'accept')">Accept job</button>` : step ? `<button type="button" class="btn btn-sm" onclick="jobAction(${j.id},'${step[0]}')">${step[1]}</button>` : '';
  return `<article class="list-row" data-search="${esc([i.title, i.material, colorName(i.color), 'order ' + j.order_id].join(' ').toLowerCase())}"><div class="row-main"><span class="row-title">${esc(i.title)} × ${i.quantity}</span><span class="row-meta">${esc([i.material, colorName(i.color), i.dimensions, 'Order #' + j.order_id].filter(Boolean).join(' · '))}</span></div><span class="row-value">${money(i.price_cents * i.quantity / 100)}<small>${money(i.price_cents / 100)} / unit</small></span><span class="row-status">${statusBadge(j.status)}</span><div class="row-actions">${action}</div>${j.fulfillment ? `<details class="row-details"><summary>Buyer contact and delivery</summary><dl class="detail-grid"><div><dt>Contact</dt><dd>${esc(deliveryText(j.fulfillment.contact))}</dd></div><div><dt>Delivery address</dt><dd>${esc(deliveryText(j.fulfillment.address))}</dd></div></dl></details>` : ''}</article>`;
}
function jobGroups(jobs) {
  const mine = jobs.filter(j => j.host_id === account.id);
  return {available:jobs.filter(j => j.status === 'available'), accepted:mine.filter(j => j.status === 'accepted'), 'in-progress':mine.filter(j => ['printing', 'ready'].includes(j.status)), completed:mine.filter(j => j.status === 'completed')};
}
const hostPages = {
  async 'host'() {
    const [jobs, listings] = await Promise.all([api('/host/jobs'), api('/listings/mine')]), g = jobGroups(jobs);
    setNavCount('jobs', g.available.length);
    const active = [...g.accepted, ...g['in-progress']], rejected = listings.filter(p => p.status === 'rejected').length, pending = listings.filter(p => p.status === 'pending').length;
    const stats = [statCard('Available jobs', g.available.length, 'host/jobs/available', 'Matching your materials', g.available.length ? 'attention' : ''), statCard('Accepted', g.accepted.length, 'host/jobs/accepted', 'Ready to start printing'), statCard('In progress', g['in-progress'].length, 'host/jobs/in-progress', 'Printing or ready'), statCard('Completed', g.completed.length, 'host/jobs/completed'), statCard('Published listings', listings.filter(p => p.status === 'approved').length, 'my-listings', pending ? `${pending} awaiting review` : '')];
    const notices = [rejected ? `<div class="banner warning"><span>${rejected === 1 ? 'One listing was' : rejected + ' listings were'} returned by an administrator with review notes.</span><a class="btn-ghost btn-sm" href="#my-listings">Review listings</a></div>` : ''].join('');
    return {title:'Overview', action:g.available.length ? `<a class="btn btn-sm" href="#host/jobs/available">View available jobs</a>` : '', body:`${notices}<div class="stat-grid">${stats.join('')}</div><section class="section-card"><header class="card-head"><div><h2>Your active jobs</h2><p class="muted">Agree payment and delivery directly with the buyer before printing.</p></div>${active.length > 5 ? '<a class="textlink" href="#host/jobs">View all</a>' : ''}</header>${active.length ? `<div class="list">${active.slice(0, 5).map(jobRow).join('')}</div>` : emptyState('No active jobs', g.available.length ? 'Accept an available job to start printing.' : 'New jobs matching your materials will appear in Printing jobs.', g.available.length ? '<a class="btn btn-sm" href="#host/jobs/available">Browse available jobs</a>' : '')}</section>`};
  },
  async 'host/jobs'(route) {
    const selected = route.split('/')[2] || '', jobs = await api('/host/jobs'), g = jobGroups(jobs);
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
  async 'my-printers'() {
    const printers = await api('/host/equipment'), total = printers.reduce((n, p) => n + p.quantity, 0), materials = [...new Set(printers.flatMap(p => p.materials))];
    const card = p => `<article class="section-card equipment-card"><header class="card-head"><div><h2>${esc(p.manufacturer + ' ' + p.model)}</h2><p class="muted">${p.technology === 'FDM' ? 'FDM / FFF' : 'Resin / vat photopolymerization'}</p></div>${p.verified ? statusBadge('approved', 'Verified specs') : statusBadge('pending', 'User-provided')}</header><dl class="detail-grid"><div><dt>Quantity</dt><dd>${p.quantity}</dd></div><div><dt>Build volume</dt><dd>${p.x} × ${p.y} × ${p.z} mm</dd></div></dl><div class="tag-list">${p.materials.map(m => `<span class="tag">${esc(m)}</span>`).join('') || '<span class="muted">No materials selected</span>'}</div></article>`;
    return {title:'My equipment', action:'<a class="btn btn-sm" href="#my-printers/edit">Update equipment</a>', body:`<div class="banner info"><span>Equipment changes are reviewed by an administrator. Saving changes, even as a draft, pauses your host access until the update is approved.</span></div>${printers.length ? `<p class="muted ws-intro">${total} printer${total === 1 ? '' : 's'} · ${esc(materials.join(', ') || 'no materials')}</p><div class="equipment-grid">${printers.map(card).join('')}</div>` : `<div class="list">${emptyState('No equipment registered', 'Register your printers and the materials you can print.', '<a class="btn btn-sm" href="#my-printers/edit">Register equipment</a>')}</div>`}`};
  },
  async 'host/profile'() {
    const [h] = await Promise.all([api('/host/application'), ensureCountries()]);
    if (!h) return {title:'Host profile', body:`<div class="list">${emptyState('No host profile', 'Your printing host application could not be found.')}</div>`};
    const rows = [['Status', statusBadge(h.status)], ['Workshop', esc(h.additional || '—')], ['Name', esc(h.name || '—')], ['Contact', esc(h.contact || '—')], ['Service area', esc([h.region, countryLabel(h.country)].filter(Boolean).join(', ') || '—')], ['Technologies', esc(h.technologies || '—')], ['Materials', esc(h.materials || '—')], ['Printers', esc(h.printers || '—')], ['Capacity', esc(h.capabilities || '—')], ['Last review', esc(h.reviewed_at ? safeDate(h.reviewed_at) : '—')]];
    return {title:'Host profile', action:'<a class="btn-ghost btn-sm" href="#account-contact">Edit contact details</a>', body:`<p class="muted ws-intro">Your host profile is built from your account contact details and registered equipment. Update them in <a class="textlink" href="#account-contact">My account</a> and <a class="textlink" href="#my-printers">My equipment</a>.</p><section class="section-card"><dl class="detail-grid wide">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl></section>`};
  }
};

/* Listing editor inside the workspace of the signed-in role. */
listingPage = function(title, body) { return ['admin', 'host'].includes(account?.role) ? workspacePage(account.role, title, body) : layout(head(title, 'Your products') + body); };
const workspaceListingEditor = listingEditor;
listingEditor = function(p={}) {
  let html = workspaceListingEditor(p);
  if (account?.role === 'admin') html = html.replace(/<label>Listing type<select name="listing_type">.*?<\/select><\/label>/, `<input type="hidden" name="listing_type" value="${p.listing_type || 'official'}">`);
  if (account?.role === 'admin' && p.listing_type === 'community') html = html.replace(/<button class="secondary" name="action" value="submit">.*?<\/button>/, '');
  return html.replace('<label>Product photographs', `<label>CAD model (STL or 3MF, maximum 20 MB; required for host submission)<input id="listing-cad" type="file" accept=".stl,.3mf"></label>${p.has_cad ? `<p>Model uploaded · Dimensions: ${esc(p.cad_dimensions)} mm · Printability not verified.</p><button type="button" class="secondary" onclick="regenerateProductRender(${p.id},this)">Regenerate preview</button>` : ''}<label>Product photographs`);
};
const workspaceBindMarketplace = bindMarketplace;
bindMarketplace = function() { workspaceBindMarketplace(); const form = $('#listing-form'); if (!form) return; api('/materials').then(items => { if (!form.isConnected) return; const input = form.elements.material; const current = input.value; const selected = editListing?.configurator?.materials || {[current]:10000}; const fieldset = document.createElement('fieldset'); fieldset.innerHTML = '<legend>Available materials (pricing adjustments configured separately)</legend>' + items.map(m => `<label class="material-choice"><span><input data-listing-material type="checkbox" value="${esc(m.name)}" ${Object.hasOwn(selected, m.name) ? 'checked' : ''}> ${esc(m.name)}</span></label>`).join(''); input.closest('label').after(fieldset); fieldset.onchange = () => { const checked = fieldset.querySelector('[data-listing-material]:checked'); if (checked) input.value = checked.value; }; }).catch(showError); };

// All scripts are loaded: draw the final navigation and page once.
render();
