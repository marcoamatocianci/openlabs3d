/* Shared navigation: one topbar, account menu, mobile menu and workspace layout for every role.
   Visibility only mirrors permissions; the API enforces them independently. */
const iconPaths = {
  menu:'<path d="M4 7h16M4 12h16M4 17h16"/>', close:'<path d="M6 6l12 12M18 6 6 18"/>', chevron:'<path d="m6 9 6 6 6-6"/>',
  cart:'<path d="M3 4h2l2.3 10.1a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 1.9-1.4L21 8H6.1"/><circle cx="10" cy="20" r="1.3"/><circle cx="17" cy="20" r="1.3"/>',
  more:'<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
  expand:'<path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7"/>', collapse:'<path d="m6 15 6-6 6 6"/>', plus:'<path d="M12 5v14M5 12h14"/>', search:'<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>', edit:'<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m13.5 6.5 4 4"/>', history:'<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3.5 4.5v4h4"/><path d="M12 8v4.2l2.8 1.8"/>',
  camera:'<path d="M4 8.5h3.2L9 6h6l1.8 2.5H20V19H4z"/><circle cx="12" cy="13.2" r="3.4"/>', logout:'<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10"/>',
  arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>', back:'<path d="M19 12H5M11 6l-6 6 6 6"/>',
  // Printing job stages: new work, in production, packed, on its way.
  inbox:'<path d="M4 13.5 6.3 6h11.4l2.3 7.5V19H4z"/><path d="M4 13.5h4.6l1.3 2.2h4.2l1.3-2.2H20"/>', layers:'<path d="m12 4 8 4-8 4-8-4z"/><path d="m4 12 8 4 8-4M4 16l8 4 8-4"/>',
  // Finished work, review queues and requests.
  check:'<path d="m5 12.5 4.5 4.5L19 7.5"/>', ban:'<circle cx="12" cy="12" r="8.5"/><path d="m6 6 12 12"/>',
  user:'<circle cx="12" cy="8.5" r="3.6"/><path d="M5 20c.8-3.6 3.6-5.6 7-5.6s6.2 2 7 5.6"/>',
  printer:'<path d="M7 9V4h10v5"/><rect x="4" y="9" width="16" height="7" rx="1.5"/><path d="M7 14h10v6H7z"/>',
  tag:'<path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1 1 0 0 1 0 1.4l-7.3 7.3a1 1 0 0 1-1.4 0z"/><circle cx="8" cy="8" r="1.4"/>',
  wrench:'<path d="M14.5 6.2a4 4 0 0 0 5 5l-8.8 8.8a2.1 2.1 0 0 1-3-3z"/><path d="M14.5 6.2 17 3.7"/>',
  send:'<path d="M20.5 3.5 3.5 10.6l6.8 3.1 3.1 6.8z"/><path d="m10.3 13.7 4.6-4.6"/>',
  clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  box:'<path d="M4 7.6 12 4l8 3.6v8.8L12 20l-8-3.6z"/><path d="M4 7.6 12 11l8-3.4M12 11v9"/>', truck:'<path d="M3 6.5h11v9.5H3zM14 9.5h3.6L21 13v3h-7"/><circle cx="7" cy="17.6" r="1.7"/><circle cx="17.2" cy="17.6" r="1.7"/>'
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${iconPaths[name]}</svg>`;
const currentRoute = () => (location.hash || '#home').slice(1).split('?')[0];
const routeIn = (route, ...prefixes) => prefixes.some(p => route === p || route.startsWith(p + '/'));
const navState = {mobile:false, sidebar:false};
let navCounts = {}, navbarHtmlCache = '';

/* Role configuration: every role shares the same components, only the entries differ. */
const isAdminRoute = route => routeIn(route, 'admin', 'moderation') || (account?.role === 'admin' && routeIn(route, 'edit-listing'));
const isHostRoute = route => routeIn(route, 'host', 'my-listings', 'my-printers', 'production', 'create-listing') || (account?.role === 'host' && routeIn(route, 'edit-listing'));
const marketplaceItem = label => ({href:'catalogue', label, match:route => routeIn(route, 'catalogue', 'product')});
const accountItem = {href:'account', label:'My account', match:route => route.startsWith('account')};
const ordersItem = {href:'orders', label:'My orders'};
const rackItem = {href:'design-rack', label:'Design your rack'};
const designsItem = {href:'my-designs', label:'My designs'};
const NAVIGATION = {
  guest:{primary:[marketplaceItem('Explore'), rackItem]},
  buyer:{primary:[marketplaceItem('Explore'), rackItem, ordersItem], cart:true, menu:[accountItem, designsItem, {href:'onboarding', label:'Become a printing host'}]},
  host:{primary:[marketplaceItem('Marketplace'), rackItem, {href:'host', label:'Host workspace', match:isHostRoute, count:'jobs'}], cart:true, menu:[accountItem, ordersItem, designsItem]},
  admin:{primary:[marketplaceItem('Marketplace'), {href:'admin', label:'Admin workspace', match:isAdminRoute, count:'approvals'}], menu:[accountItem]}
};
const WORKSPACES = {
  admin:{label:'Admin workspace', groups:[
    {items:[{href:'admin', label:'Overview', match:route => route === 'admin'}]},
    {label:'Marketplace', items:[{href:'admin/products', label:'Products', match:route => routeIn(route, 'admin/products', 'admin/create-official', 'edit-listing')}, {href:'admin/printers', label:'Printers'}, {href:'admin/materials', label:'Materials'}, {href:'admin/categories', label:'Categories'}]},
    {label:'People', items:[{href:'admin/users', label:'Users'}, {href:'admin/hosts', label:'Printing hosts'}]},
    {label:'Operations', items:[{href:'admin/pending', label:'Approvals', count:'approvals'}, {href:'admin/orders', label:'Orders'}]},
    {label:'System', items:[{href:'admin/activity', label:'Activity logs'}, {href:'admin/settings', label:'Settings'}]}]},
  host:{label:'Host workspace', groups:[{items:[
    {href:'host', label:'Overview', match:route => route === 'host'}, {href:'host/jobs', label:'Printing jobs', count:'jobs'},
    {href:'my-listings', label:'My listings', match:route => routeIn(route, 'my-listings', 'create-listing', 'edit-listing')},
    {href:'my-printers', label:'My equipment'}, {href:'host/profile', label:'Host profile'}]}]}
};
const roleLabel = role => ({buyer:'Buyer', host:'Printing host', admin:'Administrator'}[role] || role);
const navRole = () => !account ? 'guest' : ['admin', 'host'].includes(account.role) ? account.role : 'buyer';
const itemActive = (item, route) => item.match ? item.match(route) : routeIn(route, item.href);
const countBadge = key => key ? `<span class="nav-badge" data-count-key="${key}" ${navCounts[key] ? '' : 'hidden'}>${navCounts[key] || 0}</span>` : '';

/* Shared renderer: exactly one active picture in every account and workspace surface. */
// One public name: the username (display_name only for records that predate it).
const userName = user => user?.username || user?.display_name || '';
function initials(user) {
  const words = String(userName(user) || '?').trim().split(/[\s_\-]+/u).filter(Boolean);
  return (words.length > 1 ? Array.from(words[0])[0] + Array.from(words.at(-1))[0] : Array.from(words[0] || '?').slice(0, 2).join('')).toLocaleUpperCase();
}
function avatarHtml(user, size=32, extra='') {
  const picture = profilePictureFor(user), letters = esc(initials(user));
  const content = picture.kind === 'avatar' ? labAvatarSvg(picture.style) : picture.kind === 'photo' ? `${letters}<img src="${esc(profilePhotoUrl(user))}" alt="" onerror="this.remove()">` : letters;
  return `<span class="avatar ${esc(extra)}" data-profile-user="${esc(user.id)}" data-profile-size="${size}" data-profile-extra="${esc(extra)}" style="--size:${size}px" aria-hidden="true">${content}</span>`;
}
function refreshProfilePictures(user) {
  for (const element of document.querySelectorAll('[data-profile-user]')) {
    if (element.dataset.profileUser === String(user.id)) element.outerHTML = avatarHtml(user, Number(element.dataset.profileSize), element.dataset.profileExtra);
  }
}

/* Topbar: brand · primary navigation · actions · account menu. */
// The supplied lockup already spells the name, so the text is kept for assistive technology only.
// Both theme variants are tiny WebPs; CSS shows the one matching [data-theme].
const BRAND_LOGO = '<img class="brand-logo brand-logo-light" src="assets/brand/openlabs3d-logo.webp" width="431" height="96" alt="" decoding="async"><img class="brand-logo brand-logo-dark" src="assets/brand/openlabs3d-logo-dark.webp" width="431" height="96" alt="" decoding="async">';
function navbarHtml(route) {
  const config = NAVIGATION[navRole()], count = opsCart.reduce((n, i) => n + i.quantity, 0);
  const primary = config.primary.map(item => { const active = itemActive(item, route); return `<a class="nav-link ${active ? 'active' : ''}" href="#${item.href}" ${active ? 'aria-current="page"' : ''}>${esc(item.label)}${countBadge(item.count)}</a>`; }).join('');
  const cartActive = routeIn(route, 'basket', 'checkout', 'checkout-cart');
  const cart = `<a class="nav-icon cart-link ${cartActive ? 'active' : ''}" href="#basket" ${cartActive ? 'aria-current="page"' : ''} ${config.cart ? '' : 'hidden'}>${icon('cart')}<span class="sr-only">Basket</span><b id="count" class="count-badge" ${count ? '' : 'hidden'}>${count}</b></a>`;
  // Until the session check returns, leave the account area empty instead of flashing "Sign in".
  const actions = !authChecked ? '' : account ? userMenuHtml(config, route) : `<a class="nav-link ${route === 'account' ? 'active' : ''}" href="#account" ${route === 'account' ? 'aria-current="page"' : ''}>Sign in</a><a class="btn btn-sm nav-cta" href="#account?mode=register">Create account</a>`;
  return `<div class="topbar-inner"><button type="button" class="nav-icon nav-toggle" data-nav-toggle aria-controls="primary-nav" aria-expanded="${navState.mobile}" aria-label="${navState.mobile ? 'Close menu' : 'Open menu'}">${icon(navState.mobile ? 'close' : 'menu')}</button><a class="brand" href="#home">${BRAND_LOGO}<span id="brand" class="sr-only">${esc(publicSettings.marketplace_name || 'OpenLabs3D')}</span></a><nav id="primary-nav" class="primary-nav ${navState.mobile ? 'open' : ''}" aria-label="Main">${primary}</nav><div class="topbar-actions">${cart}${actions}</div></div>`;
}
function userMenuHtml(config, route) {
  const active = config.menu.some(item => itemActive(item, route));
  const items = config.menu.map(item => { const current = itemActive(item, route); return `<a class="menu-item ${current ? 'active' : ''}" href="#${item.href}" ${current ? 'aria-current="page"' : ''}>${esc(item.label)}</a>`; }).join('');
  return `<div class="dropdown user-menu"><button type="button" class="user-trigger ${active ? 'active' : ''}" id="user-menu-button" data-dropdown aria-expanded="false" aria-controls="user-menu">${avatarHtml(account, 36)}<span class="user-name">${esc(account.username)}</span>${icon('chevron')}<span class="sr-only">Account menu</span></button><div class="dropdown-menu align-end" id="user-menu" hidden><div class="menu-header">${avatarHtml(account, 42)}<div><strong>${esc(account.username || account.display_name)}</strong><span>${esc(account.email)}</span></div></div>${items}<hr class="menu-separator"><button type="button" class="menu-item" data-logout>${icon('logout')}Log out</button></div></div>`;
}
function renderNavbar(route=currentRoute()) {
  const header = $('#topbar'); if (!header) return;
  const html = navbarHtml(route); if (html === navbarHtmlCache) return;
  // Keep keyboard focus on the same control when counts or the active page change.
  const focused = header.contains(document.activeElement) ? document.activeElement.id || document.activeElement.getAttribute('href') : null;
  header.innerHTML = html; navbarHtmlCache = html; header.classList.toggle('nav-open', navState.mobile);
  if (focused) header.querySelector(`[id="${CSS.escape(focused)}"],[href="${CSS.escape(focused)}"]`)?.focus();
}
function setNavCount(key, value) {
  navCounts[key] = value;
  document.querySelectorAll(`[data-count-key="${key}"]`).forEach(el => { el.textContent = value; el.hidden = !value; });
}
let navCountsAt = 0;
async function refreshNavBadges(force=false) {
  if (!account || !['admin', 'host'].includes(account.role)) { navCounts = {}; renderNavbar(); return; }
  if (!force && Date.now() - navCountsAt < 15000) return;
  navCountsAt = Date.now(); const owner = account.id;
  try {
    if (account.role === 'admin') { const [o, suggestions] = await Promise.all([api('/admin/overview'), api('/admin/printer-suggestions')]); if (account?.id === owner) { setNavCount('approvals', o.pending_hosts + o.products_pending + (o.pending_equipment || 0) + suggestions.length); setNavCount('requests', o.custom_requests_new || 0); } }
    else { const jobs = await api('/host/jobs?scope=active&group=available'); if (account?.id === owner) setNavCount('jobs', jobs.total); }
    renderNavbar();
  } catch (e) { console.warn('Navigation counts unavailable', e); }
}

/* Modal dialogs: native <dialog> keeps the page inert, but lets Tab leave to the browser after the
   last control. This keeps keyboard focus cycling inside the dialog. */
/* A dialog is announced by its heading: every dialog names itself from the first one it holds. */
function nameDialog(dialog) {
  const heading = dialog?.querySelector('h1,h2,h3');
  if (!heading) return dialog?.removeAttribute('aria-labelledby');
  heading.id ||= dialog.id + '-title';
  dialog.setAttribute('aria-labelledby', heading.id);
}
function keepFocusInside(dialog) {
  dialog.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const items = [...dialog.querySelectorAll('button,input,select,textarea,summary,[href],[tabindex]:not([tabindex="-1"])')].filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length && !el.closest('[hidden]') && (el.type !== 'radio' || el.checked || !dialog.querySelector(`input[name="${el.name}"]:checked`)));
    const first = items[0], last = items.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
}

/* Dropdowns follow the disclosure pattern: Escape closes, arrows move between entries. */
const dropdownItems = menu => [...menu.querySelectorAll('a[href],button:not([disabled])')];
function setDropdown(trigger, open) {
  const menu = document.getElementById(trigger.getAttribute('aria-controls')); if (!menu) return;
  if (open && trigger.closest('#topbar') && navState.mobile) setMobileNav(false);
  trigger.setAttribute('aria-expanded', open); menu.hidden = !open;
}
function closeDropdowns(except) { document.querySelectorAll('[data-dropdown][aria-expanded="true"]').forEach(t => { if (t !== except) setDropdown(t, false); }); }
function setMobileNav(open) {
  navState.mobile = open; const header = $('#topbar'), toggle = header?.querySelector('[data-nav-toggle]');
  if (!toggle) return;
  header.classList.toggle('nav-open', open); $('#primary-nav').classList.toggle('open', open);
  toggle.setAttribute('aria-expanded', open); toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu'); toggle.innerHTML = icon(open ? 'close' : 'menu');
  navbarHtmlCache = '';
}
document.addEventListener('click', e => {
  const trigger = e.target.closest('[data-dropdown]');
  if (trigger) { const open = trigger.getAttribute('aria-expanded') !== 'true'; closeDropdowns(trigger); setDropdown(trigger, open); return; }
  if (!e.target.closest('.dropdown-menu') || e.target.closest('a,button')) closeDropdowns();
  if (e.target.closest('[data-nav-toggle]')) { setMobileNav(!navState.mobile); return; }
  if (navState.mobile && (!e.target.closest('#primary-nav') || e.target.closest('a'))) setMobileNav(false);
  if (e.target.closest('[data-logout]')) logout();
  if (e.target.closest('[data-theme-toggle]')) toggleTheme();
  if (e.target.closest('[data-close-modal]')) e.target.closest('dialog')?.close();
  const sidebarToggle = e.target.closest('[data-ws-toggle]');
  if (sidebarToggle) { navState.sidebar = !navState.sidebar; sidebarToggle.setAttribute('aria-expanded', navState.sidebar); sidebarToggle.closest('.ws-sidebar').classList.toggle('open', navState.sidebar); }
  const group = e.target.closest('[data-ws-group]');
  if (group) { const open = group.getAttribute('aria-expanded') !== 'true'; group.setAttribute('aria-expanded', open); document.getElementById(group.getAttribute('aria-controls')).hidden = !open; saveGroupState(group.dataset.wsGroup, open); }
});
document.addEventListener('keydown', e => {
  const openTrigger = document.querySelector('[data-dropdown][aria-expanded="true"]');
  if (e.key === 'Escape') {
    if (openTrigger) { setDropdown(openTrigger, false); openTrigger.focus(); }
    else if (navState.mobile) { setMobileNav(false); $('[data-nav-toggle]')?.focus(); }
    return;
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
  const trigger = e.target.closest('[data-dropdown]'), menu = e.target.closest('.dropdown-menu');
  if (trigger && e.key === 'ArrowDown') { e.preventDefault(); closeDropdowns(trigger); setDropdown(trigger, true); dropdownItems(document.getElementById(trigger.getAttribute('aria-controls')))[0]?.focus(); }
  else if (menu) {
    e.preventDefault(); const items = dropdownItems(menu), index = items.indexOf(document.activeElement);
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (index + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  }
});
// Tabbing out of an open dropdown closes it; widening the window closes the mobile menu.
document.addEventListener('focusin', e => { const open = document.querySelector('[data-dropdown][aria-expanded="true"]'); if (open && !open.parentElement.contains(e.target)) setDropdown(open, false); });
matchMedia('(min-width: 761px)').addEventListener('change', e => { if (e.matches && navState.mobile) setMobileNav(false); });

/* Workspace layout shared by the host and administrator workspaces. */
function groupState() { try { return JSON.parse(localStorage.getItem('ol3d-workspace-groups') || '{}'); } catch (e) { return {}; } }
function saveGroupState(key, open) { try { localStorage.setItem('ol3d-workspace-groups', JSON.stringify({...groupState(), [key]:open})); } catch (e) {} }
function activeWorkspaceItem(kind, route=currentRoute()) {
  for (const group of WORKSPACES[kind].groups) for (const item of group.items) if (itemActive(item, route)) return {group, item};
  return {};
}
function sidebarHtml(kind, route) {
  const ws = WORKSPACES[kind], saved = groupState(), {group:activeGroup, item:activeItem} = activeWorkspaceItem(kind, route);
  const link = item => { const active = item === activeItem; return `<li><a class="ws-link ${active ? 'active' : ''}" href="#${item.href}" ${active ? 'aria-current="page"' : ''}><span>${esc(item.label)}</span>${countBadge(item.count)}</a></li>`; };
  const groups = ws.groups.map((group, n) => {
    if (!group.label) return `<ul class="ws-list">${group.items.map(link).join('')}</ul>`;
    const key = kind + ':' + group.label, open = group === activeGroup || saved[key] === true, id = `ws-group-${kind}-${n}`;
    const counted = group.items.find(item => item.count)?.count;
    return `<div class="ws-group"><button type="button" class="ws-group-toggle" data-ws-group="${key}" aria-expanded="${open}" aria-controls="${id}"><span>${esc(group.label)}</span>${counted ? `<span class="group-count">${countBadge(counted)}</span>` : ''}${icon('chevron')}</button><ul class="ws-list" id="${id}" ${open ? '' : 'hidden'}>${group.items.map(link).join('')}</ul></div>`;
  }).join('');
  return `<aside class="ws-sidebar ${navState.sidebar ? 'open' : ''}"><button type="button" class="ws-switch" data-ws-toggle aria-expanded="${navState.sidebar}" aria-controls="ws-nav"><span><small>${esc(ws.label)}</small>${esc(activeItem?.label || ws.label)}</span>${icon('chevron')}</button><nav id="ws-nav" class="ws-nav" aria-label="${esc(ws.label)}">${groups}</nav></aside>`;
}
function workspacePage(kind, title, body, action='') {
  const route = currentRoute(), {group} = activeWorkspaceItem(kind, route);
  document.title = `${title} · ${WORKSPACES[kind].label} · ${publicSettings.marketplace_name || 'OpenLabs3D'}`;
  return `<div class="workspace">${sidebarHtml(kind, route)}<section class="ws-main" aria-labelledby="ws-title"><header class="ws-head"><div>${group?.label ? `<p class="ws-crumb eyebrow-dot">${esc(group.label)}</p>` : ''}<h1 id="ws-title">${esc(title)}</h1></div>${action ? `<div class="ws-actions">${action}</div>` : ''}</header>${body}</section></div>`;
}

/* Small building blocks reused by workspace and account pages. */
const statusTones = {approved:'success', published:'success', completed:'success', active:'success', pending:'warning', available:'warning', rejected:'danger', cancelled:'danger', suspended:'danger', accepted:'info', printing:'info', ready:'info', shipped:'info'};
const statusText = status => { const text = String(status).replaceAll('_', ' '); return text.charAt(0).toUpperCase() + text.slice(1); };
const statusBadge = (status, label) => `<span class="status status-${statusTones[status] || 'neutral'}">${esc(label || statusText(status))}</span>`;
function filterChips(label, options, selected) { return `<nav class="chips" aria-label="${esc(label)}">${options.map(o => { const on = o.value === selected; return `<a class="chip ${on ? 'active' : ''}" href="#${o.href}" ${on ? 'aria-current="true"' : ''}>${esc(o.label)}${o.count != null ? `<span>${o.count}</span>` : ''}</a>`; }).join('')}</nav>`; }
/* Current / History pages. Level 1 switches between work still in progress and finished work; level 2
   filters the selected one by status. Which statuses belong where comes from the API (app/lifecycle.py),
   with each scope's counts, so the two levels never disagree with the server.
   query: the page's other hash parameters (kept when switching); names: {active, history} labels. */
function scopeHref(base, query, params) {
  // Defaults (scope active, group all, page 1, empty search) stay out of the address.
  const q = new URLSearchParams(Object.entries({...query, ...params}).filter(([k, v]) => v !== '' && v != null && v !== 'all' && !(k === 'scope' && v === 'active') && !(k === 'page' && +v === 1)));
  return base + (q.toString() ? '?' + q : '');
}
function scopeNav({label, base, query = {}, data, names, all = {active:'All active', history:'All'}}) {
  const go = params => scopeHref(base, query, {group:'all', page:1, q:'', ...params});
  const primary = `<nav class="segmented scope-nav" aria-label="${esc(label)}">${['active', 'history'].map(scope => { const on = data.scope === scope; return `<a class="segment ${scope === 'history' ? 'scope-history' : ''}" href="#${go({scope})}" ${on ? 'aria-current="page"' : ''}>${scope === 'history' ? icon('history') : ''}${esc(names[scope])}<span class="segment-count">${data.scopes[scope].total}</span></a>`; }).join('')}</nav>`;
  const groups = data.scopes[data.scope].groups;
  const secondary = filterChips(`${names[data.scope]} by status`, [{value:'all', label:all[data.scope], href:go({scope:data.scope}), count:data.scopes[data.scope].total}, ...groups.map(g => ({value:g.key, label:g.label, href:go({scope:data.scope, group:g.key}), count:g.count}))], data.group || 'all');
  return {primary, secondary};
}
// Page links for a scoped list; hrefFor(page) builds each link.
const pager = (hrefFor, page, pages) => pages > 1 ? `<nav class="bo-pagination" aria-label="Pages">${page > 1 ? `<a class="btn-ghost btn-sm" href="#${hrefFor(page - 1)}">Previous</a>` : '<span></span>'}<span>Page ${page} of ${pages}</span>${page < pages ? `<a class="btn-ghost btn-sm" href="#${hrefFor(page + 1)}">Next</a>` : '<span></span>'}</nav>` : '';
// The hash query of the current page as an object (scope, group, page, q, …).
const hashQuery = () => Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || ''));
const searchBox = (list, placeholder) => `<label class="search-field">${icon('search')}<span class="sr-only">${esc(placeholder)}</span><input type="search" placeholder="${esc(placeholder)}" data-filter-list="${list}" autocomplete="off"></label>`;
const toolbar = (...parts) => `<div class="ws-toolbar">${parts.filter(Boolean).join('')}</div>`;
const emptyState = (title, text, action='') => `<div class="empty-state"><h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;
const statCard = (label, value, href, hint='', tone='') => `<a class="stat-card ${tone}" href="#${href}"><span>${esc(label)}</span><strong>${value}</strong>${hint ? `<small>${esc(hint)}</small>` : ''}</a>`;
/* Stage boards: every Active/History list (Printing jobs, Job history, My orders, My requests, admin Orders,
   Approvals and Custom requests). The stages and the statuses each one holds come from the API
   (app/lifecycle.py groups), so a board never disagrees with the server; finished work lives in the History
   scope. Three states:
   A. Overview (open is STAGE_NONE): no stage open. Every stage is a tile of one proportional mosaic, all at the
      same level of hierarchy, their areas following their workloads (overviewPlan). A tile opens its stage.
   B. Focus: one stage is open, about two thirds of the row with its full cards; the others share a muted mosaic
      on the right, each panel sized by its workload (mosaicPlan). Clicking another panel switches; clicking the
      open stage's own header collapses back to A. Narrower boards use stage pills above the open stage instead
      of the mosaic. A scope with a single stage is one full-width column, and never collapses.
   C. Expand section: the open stage's own action shows all its items in a large dialog (openSection).
   Moving between A and B is local: no request, no re-render. The page decides what to remember (a 'stagechange'
   event, see rememberStage).
   stages: [{key, label, statuses, hint, tone, icon, count, total, page, pages, error}] · open: the stage to show
   first, or STAGE_NONE (falls back to the first stage with work) · peek(item): a small preview for a panel.
   Server-paged columns: a stage's items are its first page (page/pages/total from the API); load(key, page,
   extra) returns {items, page, pages, total} for "Load more", for retrying a column that failed (error) and for
   the dialog (extra overrides q or per_page), and onLoad(items) lets the page keep what it needs (details
   dialogs) about the cards that were added. section: what the dialog needs to know ({one, many, sorts,
   serverSearch}; see sectionSorts). */
const stageBoardConfig = {}, STAGE_NONE = 'none';
/* A refresh keeps what the reader had loaded. A page asks for its stages with stagePageSize(), so after an action the
   stage comes back as deep as it was, with whatever replaced the item that moved on, and nothing beyond that is
   fetched. Remembered per list (view: its scope, search and sort), and capped by the API's largest page. */
const stageDepths = {}, STAGE_MAX_PAGE = 50;
function stagePageSize(id, base, view = '') {
  const depth = stageDepths[id];
  return depth && depth.view === view ? Math.min(STAGE_MAX_PAGE, Math.max(base, ...Object.values(depth.loaded))) : base;
}
function rememberDepth(id, view = '', key, count) {
  if (stageDepths[id]?.view !== view) stageDepths[id] = {view, loaded:{}};
  stageDepths[id].loaded[key] = count;
}
// The state a board opens in: what the address asks for (a stage, or all collapsed), else what the page remembers.
const stageFromAddress = (stages, asked, otherwise) => asked === STAGE_NONE || stages.some(s => s.key === asked) ? asked : otherwise;
function stageBoard({id, label, stages, items = [], card, statusOf = i => i.status, level = 2, open = '', empty = 'Nothing here right now.', peek, load, onLoad, section = {}, depthView = ''}) {
  const columns = stages.map(s => ({...s, items:s.items || items.filter(i => s.statuses.includes(statusOf(i)))}));
  const counted = c => c.count ?? c.total ?? c.items.length, single = columns.length === 1;
  const overview = !single && open === STAGE_NONE;
  const current = overview ? STAGE_NONE : (columns.find(c => c.key === open) || columns.find(c => counted(c)) || columns[0]).key;
  const conf = stageBoardConfig[id] = {card, level, empty, load, onLoad, section, columns, depthView};
  const collapsed = columns.filter(c => c.key !== current), plan = single ? {} : overview ? overviewPlan(collapsed.map(counted)) : mosaicPlan(collapsed.map(counted));
  const placed = new Map(collapsed.map((c, i) => [c.key, overview ? {shown:5, more:0, tile:plan.tiles[i]} : plan.panels?.[i]]));
  const count = c => `<span class="segment-count"><span data-sb-count data-total="${counted(c)}">${counted(c)}</span><span class="sr-only"> ${counted(c) === 1 ? 'item' : 'items'}</span></span>`;
  const pills = single ? '' : `<nav class="chips sb-pills" aria-label="${esc(label)} stages">${columns.map(c => `<button type="button" class="chip" data-sb-open="${c.key}" data-tone="${c.tone || ''}" aria-controls="${id}-${c.key}" aria-pressed="${c.key === current}"><i class="sb-dot" aria-hidden="true"></i>${esc(c.label)}<span data-sb-count data-total="${counted(c)}">${counted(c)}</span></button>`).join('')}</nav>`;
  const column = (c, index) => {
    const on = c.key === current, place = placed.get(c.key);
    // Panels carry up to five previews; the plan shows as many as fit on one row of the panel.
    const previews = !peek || !c.items.length ? '' : `<span class="sb-peek" aria-hidden="true">${c.items.slice(0, 5).map((item, k) => `<span class="sb-peek-item"${k >= (place?.shown ?? 0) ? ' hidden' : ''}>${peek(item)}</span>`).join('')}<span class="sb-peek-more"${place?.more > 0 ? '' : ' hidden'}>+${place?.more || 0}</span></span>`;
    const inner = `<span class="sb-head-row"><span class="sb-icon" aria-hidden="true">${c.icon ? icon(c.icon) : ''}</span><span class="sb-title" id="${id}-${c.key}-title">${esc(c.label)}</span>${count(c)}<span class="sb-chevron" aria-hidden="true">${icon('collapse')}</span></span>${c.hint ? `<span class="sb-hint">${esc(c.hint)}</span>` : ''}${previews}`;
    const head = single ? `<div class="sb-head">${inner}</div>` : `<button type="button" class="sb-head" data-sb-open="${c.key}" aria-expanded="${on}" aria-controls="${id}-${c.key}-body"${on ? ' title="Collapse this stage"' : ''}>${inner}</button>`;
    const expand = `<button type="button" class="sb-expand" data-sb-expand="${c.key}" aria-haspopup="dialog" aria-label="Expand section: ${esc(c.label)}">${icon('expand')}<span class="sb-expand-label">Expand section</span></button>`;
    const layout = place?.tile ? ` style="${place.tile}"` : place ? ` data-size="${place.size}" data-span="${place.span}"` : '';
    return `<section class="sb-col${on ? ' is-open' : ''}" id="${id}-${c.key}" data-stage="${c.key}" data-tone="${c.tone || ''}" data-index="${index}" data-count="${counted(c)}"${layout} aria-labelledby="${id}-${c.key}-title"><div class="sb-top"><h${level} class="sb-heading">${head}</h${level}>${expand}</div><div class="sb-body" id="${id}-${c.key}-body">${stageBody(c, conf)}</div></section>`;
  };
  const drawn = columns.map(column);
  const track = single ? drawn.join('')
    : `<div class="sb-main">${drawn.filter((_, i) => columns[i].key === current).join('')}</div><div class="sb-mosaic" role="group" aria-label="Other stages" style="${overview ? plan.style : mosaicStyle(plan)}">${drawn.filter((_, i) => columns[i].key !== current).join('')}</div>`;
  return `<div class="sb${single ? ' sb-single' : ''}${overview ? ' is-overview' : ''}" id="${id}" data-stage-board data-open="${current}">${pills}<div class="sb-track">${track}</div></div>`;
}
/* The mosaic: the collapsed stages, in workflow order, as rows of a two-column grid, each row one panel across
   both columns or two side by side, so it is always a full rectangle. Panels are sized on a bounded scale, not by
   raw counts: none, 1–2, 3–5, 6–10, more. A busy stage takes more of the mosaic without crowding the others.
   - Empty stages are slim bars (fixed height), and the two largest sizes always span the grid.
   - Row heights give each panel an area in proportion to its weight (one across both columns: weight / 2).
   - Of the possible arrangements the plan takes the one closest to those proportions, with the fewest rows
     and then the busiest stage across the grid. Two panels simply stack: side by side they would be too narrow.
   - The rows fill the height of the open stage, up to a maximum that grows with the workload (so a few jobs
     never stretch into big empty tiles), and stay in view while a long stage scrolls.
   Returns {panels:[{size, span, shown, more}], rows, rows1, max, max1}: rows as grid tracks, for two columns
   and for one; max in px, likewise. */
const mosaicSize = n => n === 0 ? 'xs' : n <= 2 ? 's' : n <= 5 ? 'm' : n <= 10 ? 'l' : 'xl';
const MOSAIC_WEIGHT = {s:2, m:3, l:4, xl:5};
const MOSAIC_MAX = {xs:40, s:92, m:112, l:148, xl:172}, MOSAIC_MAX_PAIR = {s:120, m:140}, MOSAIC_GAP = 8;
function mosaicPlan(counts) {
  const sizes = counts.map(mosaicSize), pairable = i => sizes[i] === 's' || sizes[i] === 'm';
  const weight = i => MOSAIC_WEIGHT[sizes[i]] || 0, score = rows => {
    // Row height (fr): a panel across two columns needs half the height of one in a single column.
    const fr = row => row.length === 2 ? Math.max(weight(row[0]), weight(row[1])) : weight(row[0]) / 2;
    const area = i => { const row = rows.find(r => r.includes(i)); return fr(row) * (row.length === 2 ? 1 : 2); };
    const held = sizes.map((_, i) => i).filter(i => weight(i)), used = held.reduce((n, i) => n + area(i), 0) || 1, wanted = held.reduce((n, i) => n + weight(i), 0) || 1;
    const off = held.reduce((n, i) => n + Math.abs(area(i) / used - weight(i) / wanted), 0);
    return {cost:off + .2 * rows.length, across:rows.reduce((n, r) => n + (r.length === 1 ? counts[r[0]] : 0), 0)};
  };
  let best = null, bestScore = null;
  const visit = (i, rows) => {
    if (i >= sizes.length) { const now = score(rows); if (!best || now.cost < bestScore.cost - 1e-9 || (Math.abs(now.cost - bestScore.cost) < 1e-9 && now.across > bestScore.across)) { best = rows; bestScore = now; } return; }
    visit(i + 1, [...rows, [i]]);
    if (sizes.length > 2 && i + 1 < sizes.length && pairable(i) && pairable(i + 1)) visit(i + 2, [...rows, [i, i + 1]]);
  };
  visit(0, []);
  const track = fr => fr ? `minmax(min-content,${fr}fr)` : 'auto';
  const panels = sizes.map((size, i) => {
    const span = best.find(r => r.includes(i)).length === 2 ? 1 : 2, limit = span === 2 ? 5 : 3, shown = counts[i] > limit ? limit - 1 : counts[i];
    return {size, span, shown, more:counts[i] - shown};
  });
  const gaps = n => Math.max(0, n - 1) * MOSAIC_GAP;
  return {panels,
    rows:best.map(r => track(r.length === 2 ? Math.max(weight(r[0]), weight(r[1])) : weight(r[0]) / 2)).join(' '),
    rows1:sizes.map((_, i) => track(weight(i))).join(' '),
    max:best.reduce((n, r) => n + (r.length === 2 ? Math.max(MOSAIC_MAX_PAIR[sizes[r[0]]], MOSAIC_MAX_PAIR[sizes[r[1]]]) : MOSAIC_MAX[sizes[r[0]]]), 0) + gaps(best.length),
    max1:sizes.reduce((n, size) => n + MOSAIC_MAX[size], 0) + gaps(sizes.length)};
}
const mosaicStyle = plan => `--mosaic-rows:${plan.rows};--mosaic-rows-1:${plan.rows1};--mosaic-max:${plan.max}px;--mosaic-max-1:${plan.max1}px`;
/* The overview: every stage a tile of one mosaic, areas in proportion to a bounded, nonlinear weight. An ordered
   treemap: the stages keep their workflow order, and of every way to cut the rectangle (side by side or stacked,
   recursively) it takes the one with the most comfortable tiles and every tile above its minimum size. It is
   worked out for three board widths and applied by container queries (style.css), so resizing needs no script.
   Returns {style, tiles}: the grid's tracks and height, and each tile's grid area, per width. */
const overviewWeight = n => n === 0 ? 1 : Math.min(9, 1.6 + 1.5 * Math.log2(n + 1));
const OVERVIEW_WIDTHS = [{name:'s', width:300, unit:5200, minW:112, minH:84, maxH:520}, {name:'m', width:540, unit:9000, minW:130, minH:84, maxH:420}, {name:'l', width:800, unit:10500, minW:150, minH:84, maxH:360}];
// A near-empty stage gets a minimum share of the mosaic, enough to fit one row of tiles, rather than exact proportion:
// otherwise the whole mosaic would have to grow just to give that one tile its minimum size.
function overviewShares(weights, floor) {
  const limit = Math.min(floor, .8 / weights.length), floored = new Set();
  for (;;) {
    const rest = weights.reduce((sum, w, i) => floored.has(i) ? sum : sum + w, 0), total = rest / (1 - floored.size * limit);
    const next = weights.findIndex((w, i) => !floored.has(i) && w < limit * total);
    if (next < 0) return weights.map((w, i) => floored.has(i) ? limit * total : w);
    floored.add(next);
  }
}
function overviewCut(weights, W, H, minW, minH) {
  const total = (i, j) => weights.slice(i, j).reduce((a, b) => a + b, 0);
  const cost = (w, h) => Math.abs(Math.log(w / h / 1.7)) + (w < minW ? 8 * (minW - w) / minW : 0) + (h < minH ? 8 * (minH - h) / minH : 0);
  const fit = (i, j, x, y, w, h) => {
    if (j - i === 1) return {cost:cost(w, h), rects:[{x, y, w, h}]};
    let best = null;
    for (let k = i + 1; k < j; k++) {
      const share = total(i, k) / total(i, j);
      for (const beside of [true, false]) {
        const a = beside ? fit(i, k, x, y, w * share, h) : fit(i, k, x, y, w, h * share);
        const b = beside ? fit(k, j, x + w * share, y, w * (1 - share), h) : fit(k, j, x, y + h * share, w, h * (1 - share));
        if (!best || a.cost + b.cost < best.cost - 1e-6) best = {cost:a.cost + b.cost, rects:[...a.rects, ...b.rects]};
      }
    }
    return best;
  };
  return fit(0, weights.length, 0, 0, W, H).rects;
}
function overviewPlan(counts) {
  const weights = counts.map(overviewWeight), sum = weights.reduce((a, b) => a + b, 0), tiles = counts.map(() => []), style = [];
  for (const {name, width, unit, minW, minH, maxH} of OVERVIEW_WIDTHS) {
    const shares = overviewShares(weights, minW / width);
    let height = Math.min(maxH, Math.max(minH, sum * unit / width)), rects = overviewCut(shares, width, height, minW, minH);
    // A tile still too small to hold its name and count: grow the mosaic until every tile can, within its maximum.
    for (let tries = 0; tries < 10 && height < maxH && rects.some(r => r.h < minH - .5 || r.w < minW - .5); tries++) { height = Math.min(maxH, height * 1.15); rects = overviewCut(shares, width, height, minW, minH); }
    const lines = values => [...new Set(values.map(v => +v.toFixed(2)))].sort((a, b) => a - b);
    const xs = lines(rects.flatMap(r => [r.x, r.x + r.w])), ys = lines(rects.flatMap(r => [r.y, r.y + r.h]));
    const tracks = list => list.slice(1).map((v, i) => `minmax(0,${(v - list[i]).toFixed(2)}fr)`).join(' ');
    const at = (list, v) => list.indexOf(+v.toFixed(2)) + 1;
    style.push(`--ov-cols-${name}:${tracks(xs)};--ov-rows-${name}:${tracks(ys)};--ov-h-${name}:${Math.round(height)}px`);
    rects.forEach((r, i) => tiles[i].push(`--ov-area-${name}:${at(ys, r.y)} / ${at(xs, r.x)} / ${at(ys, r.y + r.h)} / ${at(xs, r.x + r.w)}`));
  }
  return {style:style.join(';'), tiles:tiles.map(t => t.join(';'))};
}
// After a switch or a search: the open stage (if any) in the main area, the others back in the mosaic in workflow
// order, laid out again for what they now hold (the stage's matches while searching). Nodes move only when their place
// changed. Previews follow the search as well: a stage shows the first ones whose cards still match.
function arrangeMosaic(board) {
  const main = board.querySelector('.sb-main'), mosaic = board.querySelector('.sb-mosaic'); if (!mosaic) return;
  const cols = [...board.querySelectorAll('.sb-col')].sort((a, b) => a.dataset.index - b.dataset.index);
  const open = cols.find(c => c.classList.contains('is-open')), rest = cols.filter(c => c !== open);
  if (open && open.parentElement !== main) main.append(open);
  if (rest.some((c, i) => mosaic.children[i] !== c)) rest.forEach(c => mosaic.append(c));
  const matching = c => { const cards = c.querySelectorAll('.sb-list > *'); return [...c.querySelectorAll('.sb-peek-item')].filter((_, k) => !cards[k]?.hidden); };
  if (!open) {
    const plan = overviewPlan(rest.map(c => +(c.dataset.matches ?? c.dataset.count)));
    mosaic.style.cssText = plan.style;
    rest.forEach((c, i) => {
      c.style.cssText = plan.tiles[i]; delete c.dataset.size; delete c.dataset.span;
      // A tile shows the previews that fit on one row (style.css); its count already says how many there are.
      const shown = matching(c); c.querySelectorAll('.sb-peek-item').forEach(t => { t.hidden = !shown.includes(t); });
      const extra = c.querySelector('.sb-peek-more'); if (extra) extra.hidden = true;
    });
    return;
  }
  open.removeAttribute('style');
  const plan = mosaicPlan(rest.map(c => +(c.dataset.matches ?? c.dataset.count)));
  mosaic.style.cssText = mosaicStyle(plan);
  rest.forEach((c, i) => {
    const {size, span, shown} = plan.panels[i], count = +(c.dataset.matches ?? c.dataset.count), extra = c.querySelector('.sb-peek-more');
    const thumbs = [...c.querySelectorAll('.sb-peek-item')], wanted = matching(c);
    c.removeAttribute('style'); c.dataset.size = size; c.dataset.span = span;
    thumbs.forEach(t => { t.hidden = wanted.indexOf(t) < 0 || wanted.indexOf(t) >= shown; });
    if (extra) { const left = count - Math.min(shown, wanted.length); extra.textContent = '+' + left; extra.hidden = left <= 0; }
  });
  delete open.dataset.size; delete open.dataset.span;
}
// Panels slide from where they were to where they are now; one that grows is revealed from its old size rather
// than stretched, so text never distorts. Measured as drawn, so a switch during a switch carries on smoothly.
function slideStages(board, change) {
  const cols = [...board.querySelectorAll('.sb-col')], drawn = c => c.getClientRects().length > 0;
  const before = new Map(cols.filter(drawn).map(c => [c, c.getBoundingClientRect()]));
  cols.forEach(c => c.getAnimations().filter(a => !(a instanceof CSSAnimation)).forEach(a => a.cancel()));
  change();
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !board.querySelector('.sb-mosaic')?.getClientRects().length) return;
  // Switching from far down a long stage: bring the board's top back into view first.
  const top = board.getBoundingClientRect().top, bar = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--topbar-h')) || 64;
  if (top < bar) window.scrollBy(0, top - bar - 12);
  cols.forEach(c => {
    const a = before.get(c); if (!a || !drawn(c)) return;
    const b = c.getBoundingClientRect(), dx = a.left - b.left, dy = a.top - b.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(a.width - b.width) < 1 && Math.abs(a.height - b.height) < 1) return;
    const clip = `inset(0 ${Math.max(0, b.width - a.width)}px ${Math.max(0, b.height - a.height)}px 0 round 12px)`;
    c.animate([{transform:`translate(${dx}px, ${dy}px)`, clipPath:clip}, {transform:'none', clipPath:'inset(0 0 0 0 round 12px)'}], {duration:320, easing:'cubic-bezier(.2,.7,.2,1)'});
  });
}
// A stage's cards, then "Load more" while the server has more of them; or why the stage could not load.
const stageMore = (c, shown) => c.pages > c.page ? `<div class="sb-more"><span class="sb-more-note">${shown} of ${c.total} shown</span><button type="button" class="btn-ghost btn-sm" data-sb-more="${c.page + 1}">Load more</button></div>` : '';
function stageBody(c, conf) {
  if (c.error) return `<div class="sb-error" role="alert"><p>${esc(c.error)}</p><button type="button" class="btn-ghost btn-sm" data-sb-retry>Try again</button></div>`;
  if (!c.items.length) return `<p class="wf-empty">${esc(typeof conf.empty === 'function' ? conf.empty(c) : conf.empty)}</p>`;
  return `<ul class="sb-list">${c.items.map(i => conf.card(i, conf.level + 1)).join('')}</ul>${stageMore(c, c.items.length)}<p class="sb-nomatch" hidden>Nothing in this stage matches your search.</p>`;
}
// Load more appends the next page and moves focus to the first new card; Try again reloads a failed stage.
// Either way a failure stays inside the stage, with its reason, and the button can be used again.
document.addEventListener('click', async e => {
  const control = e.target.closest('[data-sb-more], [data-sb-retry]'), board = control?.closest('[data-stage-board]'), conf = board && stageBoardConfig[board.id];
  if (!conf?.load || control.disabled) return;
  const col = control.closest('.sb-col'), body = col.querySelector('.sb-body'), more = control.matches('[data-sb-more]'), label = control.textContent;
  control.disabled = true; control.setAttribute('aria-busy', 'true'); control.textContent = 'Loading…';
  body.querySelector('.sb-more-error')?.remove();
  try {
    const data = await conf.load(col.dataset.stage, more ? +control.dataset.sbMore : 1);
    if (!control.isConnected) return;
    conf.onLoad?.(data.items);
    const stage = conf.columns.find(c => c.key === col.dataset.stage);
    Object.assign(stage, {items:more ? [...stage.items, ...data.items] : data.items, page:data.page, pages:data.pages, total:data.total, error:''});
    if (!more) { body.innerHTML = stageBody(stage, conf); const first = body.querySelector('.sb-list > *'); if (first) { first.tabIndex = -1; first.focus(); } return; }
    const list = body.querySelector('.sb-list'), before = list.children.length;
    list.insertAdjacentHTML('beforeend', data.items.map(i => conf.card(i, conf.level + 1)).join(''));
    control.closest('.sb-more').outerHTML = stageMore(stage, list.children.length);
    rememberDepth(board.id, conf.depthView, stage.key, list.children.length);
    const first = list.children[before]; if (first) { first.tabIndex = -1; first.focus(); }
  } catch (err) {
    if (!control.isConnected) return;
    control.disabled = false; control.removeAttribute('aria-busy'); control.textContent = more ? 'Try again' : label;
    control.insertAdjacentHTML('beforebegin', `<span class="sb-more-error" role="alert">${esc(err.message || 'Could not load more.')}</span>`);
  }
});
// The open stage survives a refresh and a return from another page: in the address (replaced, so Back
// still leaves the page) and for the session. hrefFor(key) is the page's address with that stage open.
const rememberedStage = storageKey => { try { return sessionStorage.getItem(storageKey) || ''; } catch (e) { return ''; } };
let stageBumpNext = null;
function rememberStage(board, storageKey, hrefFor) {
  if (!board) return;
  // An item that moved to another stage (stageBumpNext, set before the page is drawn again): that stage
  // lights up once, with its new count.
  if (stageBumpNext?.board === board.id) { board.querySelectorAll(`.sb-col[data-stage="${stageBumpNext.stage}"], .sb-pills [data-sb-open="${stageBumpNext.stage}"]`).forEach(el => { el.classList.add('sb-bump'); setTimeout(() => el.classList.remove('sb-bump'), 1600); }); stageBumpNext = null; }
  const save = (key, address) => { try { sessionStorage.setItem(storageKey, key); } catch (e) {} if (address) history.replaceState(history.state, '', '#' + hrefFor(key)); };
  save(board.dataset.open, false);
  board.addEventListener('stagechange', e => save(e.detail.key, true));
}
/* One card on a stage board, the same anatomy everywhere: preview · what it is (title, details, reference) ·
   value and time on the right; an optional note; then Details on the left and at most one main action on the
   right (secondary actions, destructive ones included, sit beside Details). A card without a main action
   (finished work, read-only) has no footer: its links sit under the value, which keeps it compact. */
function boardCard({tag = 'li', level = 3, thumb = '', kicker = '', title, titleHtml = '', lines = [], side = [], note = '', noteTone = '', links = '', primary = '', search = '', attrs = '', className = ''}) {
  return `<${tag} class="wf-card jc ${className}" ${attrs} ${search ? `data-search="${esc(search.toLowerCase())}"` : ''}>${thumb || '<span class="jc-thumb jc-icon" aria-hidden="true"></span>'}<div class="jc-main">${kicker ? `<p class="jc-ref jc-kicker">${kicker}</p>` : ''}<h${level} class="jc-title">${titleHtml || esc(title)}</h${level}>${lines.filter(Boolean).map(l => `<p class="jc-spec">${l}</p>`).join('')}</div><div class="jc-side">${side.filter(Boolean).join('')}${links && !primary ? `<div class="wf-card-links jc-side-links">${links}</div>` : ''}</div>${note ? `<p class="jc-note${noteTone ? ' jc-note-' + noteTone : ''}">${note}</p>` : ''}${primary ? `<div class="jc-foot"><div class="wf-card-links">${links}</div>${primary}</div>` : ''}</${tag}>`;
}
// An icon tile in place of a product preview (requests without images, decisions, printers).
const cardIcon = name => `<span class="jc-thumb jc-icon" aria-hidden="true">${icon(name)}</span>`;
function openStage(board, key) {
  const collapsing = key === STAGE_NONE, target = collapsing ? null : board.querySelector(`.sb-col[data-stage="${key}"]`);
  if ((!collapsing && !target) || board.dataset.open === key) return false;
  const focused = board.contains(document.activeElement) ? document.activeElement : null, last = board.querySelector('.sb-col.is-open');
  slideStages(board, () => {
    board.dataset.open = key; board.classList.toggle('is-overview', collapsing);
    board.querySelectorAll('.sb-col').forEach(col => {
      const on = col === target, head = col.querySelector('.sb-head');
      col.classList.toggle('is-open', on); head.setAttribute('aria-expanded', String(on));
      if (on) head.title = 'Collapse this stage'; else head.removeAttribute('title');
    });
    arrangeMosaic(board);
  });
  board.querySelectorAll('.sb-pills [data-sb-open]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.sbOpen === key)));
  // A moved node loses focus, and the pills are hidden in the overview: focus stays with the stage concerned.
  if (focused?.isConnected && document.activeElement !== focused) focused.focus({preventScroll:true});
  if (focused && !focused.checkVisibility()) (target || last)?.querySelector('.sb-head').focus({preventScroll:true});
  board.dispatchEvent(new CustomEvent('stagechange', {bubbles:true, detail:{key}}));
  return true;
}
// A closed stage opens; the open stage's own header (or pressed pill) collapses the board into its overview.
document.addEventListener('click', e => {
  const control = e.target.closest('[data-sb-open]'), board = control?.closest('[data-stage-board]');
  if (board) openStage(board, control.dataset.sbOpen === board.dataset.open ? STAGE_NONE : control.dataset.sbOpen);
});
// While searching, each stage counts its matching cards, and the open stage says when none of its own match.
function syncStageMatches(board, query) {
  board.querySelectorAll('.sb-col').forEach(col => {
    const cards = [...col.querySelectorAll('[data-search]')], shown = cards.filter(c => !c.hidden).length;
    board.querySelectorAll(`[data-sb-open="${col.dataset.stage}"] [data-sb-count], #${CSS.escape(col.id)} .sb-head [data-sb-count]`).forEach(n => { n.textContent = query ? shown : n.dataset.total ?? cards.length; });
    col.classList.toggle('no-match', !!query && !shown);
    board.querySelector(`.sb-pills [data-sb-open="${col.dataset.stage}"]`)?.classList.toggle('no-match', !!query && !shown);
    col.querySelector('.sb-nomatch')?.toggleAttribute('hidden', !query || shown > 0);
    if (query) col.dataset.matches = shown; else delete col.dataset.matches;
  });
  arrangeMosaic(board);
}
/* Expand section: the open stage's items in a large dialog, the same cards with the same actions. It holds no
   copy of the state: its items come from the board's own columns (stageBoardConfig), and when a page redraws
   after any action the dialog redraws from the new columns, so a job that moved on leaves it and the count
   follows. The other dialogs (Details, a step's confirmation) open above it, under one scrim: Escape closes the
   top one and focus returns to the control that opened it.
   - Stages the browser holds completely search and sort locally, without a request.
   - Paged stages show their pages with Show more; a search goes to the server (section.serverSearch) or, where
     the API has none, loads every page first. A sort other than the server's order also needs every page.
   - Cards are drawn in batches, so hundreds of them never reach the page at once. */
const SECTION_BATCH = 24, sectionWhen = value => +parseServerDate(value);
// The dialog's sort options. recent: when an item was created (or, for finished work, closed); stage: when it
// entered its stage, for stages where the wait matters; reference: its order or request number. server names what
// the API sorts by itself, so a paged stage asks for a page in that order instead of downloading everything.
function sectionSorts({recent, stage, reference, referenceLabel = 'Order reference'}) {
  const number = (of, direction) => (a, b) => direction * (of(a) - of(b));
  return [{key:'recent', server:'newest', label:'Most recent', by:number(recent, -1)}, {key:'oldest', server:'oldest', label:'Oldest', by:number(recent, 1)},
    ...(stage ? [{key:'stage', label:'Longest in this stage', by:number(stage, 1)}] : []),
    ...(reference ? [{key:'reference', server:'reference', label:referenceLabel, by:(a, b) => String(reference(a)).localeCompare(String(reference(b)))}] : [])];
}
let section = null;
const sectionDialog = () => document.getElementById('section-dialog');
const sectionColumn = () => section.conf.columns.find(c => c.key === section.stage);
const sectionPaged = () => { const c = sectionColumn(); return !!(c && section.conf.load && c.pages > 1); };
const sectionNoun = n => { const {one = 'item', many = one + 's'} = section.conf.section; return n === 1 ? one : many; };
// A card's own search text (data-search), or its words when it has none.
const sectionDecode = document.createElement('textarea');
function sectionSearchText(html) {
  const found = /data-search="([^"]*)"/.exec(html);
  sectionDecode.innerHTML = found ? found[1] : html.replace(/<svg[\s\S]*?<\/svg>|<[^>]+>/g, ' ');
  return sectionDecode.value.toLowerCase();
}
// One item as a card, drawn once for as long as the page's data lasts.
function sectionEntry(item) {
  let entry = section.cards.get(item);
  if (!entry) { const html = section.conf.card(item, 3); let text = null; entry = {item, html, search:() => (text ??= sectionSearchText(html))}; section.cards.set(item, entry); }
  return entry;
}
// What the dialog shows now: its items filtered (locally held stages) and sorted, as card markup.
function sectionVisible() {
  const {view, q, sort, conf} = section, sorts = conf.section.sorts || [], chosen = sorts.find(s => s.key === sort);
  const entries = view.items.map(sectionEntry);
  const query = q.trim().toLowerCase(), filtered = query && !section.searchedOnServer ? entries.filter(e => e.search().includes(query)) : entries;
  // A page the server already sorted stays as it came; the same goes for the first sort, the server's own order.
  return chosen && !view.sortedOnServer && (sort !== sorts[0].key || !view.partial) ? [...filtered].sort((a, b) => chosen.by(a.item, b.item)) : filtered;
}
const sectionKey = item => item?.id ?? '';
function sectionInsert(entries, list) {
  const start = list.children.length;
  list.insertAdjacentHTML('beforeend', entries.map(e => e.html).join(''));
  [...list.children].slice(start).forEach((card, k) => {
    card.dataset.sectionKey = sectionKey(entries[k].item);
    // The board holds the same card: ids must stay unique, and what points at them must follow.
    [card, ...card.querySelectorAll('[id]')].filter(e => e.id).forEach(e => { e.id += '-section'; });
    [card, ...card.querySelectorAll('[aria-labelledby]')].filter(e => e.getAttribute('aria-labelledby')).forEach(e => e.setAttribute('aria-labelledby', e.getAttribute('aria-labelledby').split(' ').map(t => t + '-section').join(' ')));
  });
  return list.children[start];
}
function sectionDraw() {
  const d = sectionDialog(), entries = sectionVisible(), list = d.querySelector('.ss-list'), column = sectionColumn(), query = section.q.trim();
  const all = column ? column.total ?? column.items.length : 0, matching = section.searchedOnServer ? section.view.total : entries.length;
  list.innerHTML = ''; sectionInsert(entries.slice(0, section.limit), list);
  d.querySelector('#ss-count').textContent = query ? `${matching} of ${all} ${sectionNoun(all)}` : `${all} ${sectionNoun(all)}`;
  d.querySelector('#ss-status').textContent = query ? `${matching} ${matching === 1 ? 'match' : 'matches'}` : '';
  const none = d.querySelector('.ss-empty'), label = column?.label || 'this stage';
  none.hidden = !!entries.length;
  none.textContent = query ? `Nothing in ${label} matches “${query}”.` : `Nothing in ${label} right now.`;
  sectionMoreButton(entries);
}
function sectionMoreButton(entries) {
  const d = sectionDialog(), more = d.querySelector('.ss-more'), shown = d.querySelector('.ss-list').children.length, {view} = section;
  const left = entries.length > shown || view.partial;
  more.hidden = !left;
  if (left) { more.querySelector('.ss-more-note').textContent = `${shown} of ${view.partial ? view.total : entries.length} shown`; const b = more.querySelector('[data-ss-more]'); b.disabled = false; b.textContent = 'Show more'; }
}
// Fetches what the current search and sort need. Without either, the board's own data, with no request at all.
// keepDepth: an action refreshed the page, so bring back as many items as were showing, not just the first page.
async function sectionFetch(keepDepth = false) {
  const s = section, c = sectionColumn(); if (!c) return;
  const request = ++s.request, sorts = s.conf.section.sorts || [], paged = sectionPaged(), query = s.q.trim(), shownBefore = s.view.items.length;
  const load = (page, extra) => s.conf.load(s.stage, page, extra), onServer = paged && query && s.conf.section.serverSearch;
  const chosen = sorts.find(o => o.key === s.sort), custom = sorts.length && s.sort !== sorts[0].key;
  const serverSort = paged && custom && s.conf.section.serverSearch && chosen?.server ? chosen.server : '';
  // Only what the API cannot do itself still needs every page: a local search, or "longest in this stage" (active work, so bounded).
  const everything = paged && ((query && !onServer) || (custom && !serverSort));
  const extra = {...(onServer && {q:query}), ...(serverSort && {sort:serverSort})};
  s.searchedOnServer = !!onServer;
  if (!paged) { s.view = {items:c.items, total:c.items.length, page:1, pages:1, partial:false}; return; }
  if (!everything && !Object.keys(extra).length) { s.view = {items:c.items, total:c.total ?? c.items.length, page:c.page || 1, pages:c.pages || 1, partial:(c.page || 1) < (c.pages || 1)}; return; }
  const body = sectionDialog().querySelector('.ss-body'); body.setAttribute('aria-busy', 'true');
  const perPage = everything ? STAGE_MAX_PAGE : keepDepth && shownBefore ? Math.min(STAGE_MAX_PAGE, shownBefore) : 0;
  const sized = perPage ? {...extra, per_page:perPage} : extra;
  try {
    const data = await load(1, sized);
    if (request !== s.request || section !== s) return false;
    let items = data.items;
    if (everything) for (let page = 2; page <= data.pages; page++) { const next = await load(page, sized); if (request !== s.request || section !== s) return false; items = [...items, ...next.items]; }
    s.conf.onLoad?.(items);
    s.view = {items, total:data.total, page:everything ? data.pages : data.page, pages:data.pages, partial:!everything && data.page < data.pages, sortedOnServer:!!serverSort, extra:everything ? null : sized};
    sectionError('');
  } catch (e) {
    if (request !== s.request || section !== s) return false;
    sectionError(e.message || 'Could not load this stage.');
    return false;
  } finally { if (request === s.request && section === s) body.removeAttribute('aria-busy'); }
}
function sectionError(message) { const box = sectionDialog().querySelector('.ss-error'); box.hidden = !message; box.querySelector('p').textContent = message; }
async function sectionUpdate() {
  const s = section; s.limit = SECTION_BATCH;
  if (await sectionFetch() !== false && section === s) { sectionDraw(); sectionDialog().querySelector('.ss-body').scrollTop = 0; }
}
function openSection(board, key) {
  const conf = stageBoardConfig[board.id], column = conf?.columns.find(c => c.key === key); if (!column) return;
  let d = sectionDialog();
  if (!d) {
    d = document.createElement('dialog'); d.id = 'section-dialog'; d.className = 'ss-dialog'; d.setAttribute('aria-labelledby', 'ss-title'); d.setAttribute('aria-describedby', 'ss-count');
    document.body.append(d); keepFocusInside(d);
    d.addEventListener('cancel', e => { e.preventDefault(); closeSection(); });   // Escape
    d.addEventListener('close', sectionClosed);
    let outside = false; d.addEventListener('pointerdown', e => { outside = e.target === d; });
    d.addEventListener('click', e => { if (e.target === d && outside) closeSection(); if (e.target.closest('[data-ss-close]')) closeSection(); if (e.target.closest('[data-ss-more]')) sectionShowMore(e.target.closest('[data-ss-more]')); if (e.target.closest('[data-ss-retry]')) sectionUpdate(); });
    d.addEventListener('input', e => { if (!e.target.matches('#ss-q')) return; section.q = e.target.value; clearTimeout(section.typing); section.typing = setTimeout(sectionUpdate, 220); });
    d.addEventListener('submit', e => e.preventDefault());
    d.addEventListener('focusin', e => { const card = e.target.closest('[data-section-key]'); if (card && section) section.lastCard = card.dataset.sectionKey; });
  }
  const sorts = conf.section.sorts || [];
  section = {board:board.id, stage:key, conf, q:'', sort:sorts[0]?.key || '', limit:SECTION_BATCH, request:0, view:{items:[], total:0, page:1, pages:1, partial:false}, searchedOnServer:false, cards:new WeakMap()};
  d.dataset.tone = column.tone || ''; d.classList.remove('is-closing');
  const sortControl = sorts.length > 1 ? uiSelect({id:'ss-sort', label:'Sort by', value:section.sort, options:sorts.map(o => [o.key, o.label]), className:'ss-sort'}) : '';
  d.innerHTML = `<div class="ss"><header class="ss-head"><span class="sb-icon" aria-hidden="true">${column.icon ? icon(column.icon) : ''}</span><div class="ss-titles"><h2 id="ss-title">${esc(column.label)}</h2><p id="ss-count"></p></div><button type="button" class="icon-btn ss-close" data-ss-close aria-label="Close">${icon('close')}</button></header><form class="ss-tools" role="search"><label class="search-field">${icon('search')}<span class="sr-only">Search ${esc(column.label)}</span><input type="search" id="ss-q" placeholder="${esc(conf.section.search || 'Search ' + sectionNoun(2))}" autocomplete="off" maxlength="80"></label>${sortControl}</form><div class="ss-body"><div class="ss-error sb-error" role="alert" hidden><p></p><button type="button" class="btn-ghost btn-sm" data-ss-retry>Try again</button></div><ul class="ss-list sb-list"></ul><p class="ss-empty wf-empty" hidden></p><div class="ss-more sb-more" hidden><span class="ss-more-note sb-more-note"></span><button type="button" class="btn-ghost btn-sm" data-ss-more>Show more</button></div></div><p class="sr-only" id="ss-status" role="status"></p></div>`;
  const hidden = d.querySelector('[data-select=ss-sort] input[type=hidden]');
  if (hidden) hidden.onchange = e => { section.sort = e.target.value; sectionUpdate(); };
  document.documentElement.classList.add('section-open');
  const note = document.getElementById('toast'); if (note) d.append(note);   // the top layer covers everything else
  section.view = {items:column.items, total:column.total ?? column.items.length, page:column.page || 1, pages:column.pages || 1, partial:(column.page || 1) < (column.pages || 1)};
  sectionDraw();
  d.showModal();
  // The search field on a desktop; on a touch screen, not the keyboard over half the list.
  (matchMedia('(pointer:coarse)').matches ? d.querySelector('[data-ss-close]') : d.querySelector('#ss-q')).focus();
  // Any redraw of the page (an action, wherever it was made) brings the dialog up to date.
  section.watch = new MutationObserver(sectionSync);
  section.watch.observe(document.getElementById('app'), {childList:true, subtree:true});
}
// Reveals the next batch; then, for paged stages, the next page. Focus moves to the first new card.
async function sectionShowMore(button) {
  const s = section, list = sectionDialog().querySelector('.ss-list'), shown = list.children.length, entries = sectionVisible();
  let added = null;
  if (entries.length > shown) added = sectionInsert(entries.slice(shown, shown + SECTION_BATCH), list);
  else if (s.view.partial) {
    button.disabled = true; button.textContent = 'Loading…';
    try {
      const own = s.view.extra || null, data = await s.conf.load(s.stage, s.view.page + 1, own || {});
      if (section !== s) return;
      s.conf.onLoad?.(data.items);
      // Without a search or sort of its own these are the board's next page as well: both show the same list.
      const column = sectionColumn();
      if (!own && column) { Object.assign(column, {items:[...column.items, ...data.items], page:data.page, pages:data.pages, total:data.total}); stageRedrawColumn(s.board, column, s.conf); rememberDepth(s.board, s.conf.depthView, s.stage, column.items.length); }
      s.view = {...s.view, items:own ? [...s.view.items, ...data.items] : column.items, total:data.total, page:data.page, pages:data.pages, partial:data.page < data.pages};
      added = sectionInsert(data.items.map(item => ({item, html:s.conf.card(item, 3)})), list);
      sectionError('');
    } catch (e) { sectionError(e.message || 'Could not load more.'); }
  }
  s.limit = list.children.length;
  sectionMoreButton(sectionVisible());
  if (added) { added.tabIndex = -1; added.focus(); }
}
// The board's column after the dialog loaded its next page.
function stageRedrawColumn(id, column, conf) {
  const body = document.querySelector(`#${CSS.escape(id)} .sb-col[data-stage="${column.key}"] .sb-body`);
  if (body) body.innerHTML = stageBody(column, conf);
}
// The page behind was redrawn: new columns, or the board is gone (no work left, or an error page).
function sectionSync() {
  if (!section) return;
  const s = section, conf = stageBoardConfig[s.board], board = document.getElementById(s.board);
  if (conf === s.conf && board) return;
  // Mid-redraw: the page's frame is back and its content is not, yet.
  if (document.querySelector('#app .ws-loading, #app #bo-results[aria-busy=true] .bo-skeletons')) return;
  if (!board) { closeSection(); return; }
  s.conf = conf;
  sectionRefresh();
}
async function sectionRefresh() {
  const s = section, d = sectionDialog(), list = d.querySelector('.ss-list'), body = d.querySelector('.ss-body'), active = document.activeElement;
  // Focus stays with the same card, or the one now in its place.
  const card = list.contains(active) ? active.closest('[data-section-key]') : null, place = card ? [...list.children].indexOf(card) : -1, key = card?.dataset.sectionKey;
  s.cards = new WeakMap();
  if (await sectionFetch(true) === false || section !== s) return;
  s.conf.onLoad?.(s.view.items);
  s.limit = Math.max(SECTION_BATCH, list.children.length);
  const scroll = body.scrollTop;
  sectionDraw();
  body.scrollTop = scroll;
  if (place < 0 || document.querySelector('dialog[open]:not(#section-dialog)')) return;
  sectionFocusCard(key, place);
}
function sectionFocusCard(key, place = 0) {
  const d = sectionDialog(), list = d.querySelector('.ss-list'), cards = [...list.children];
  const card = cards.find(c => c.dataset.sectionKey === key) || cards[Math.min(place, cards.length - 1)];
  (card?.querySelector('[data-job],button:not([disabled]),a[href]') || d.querySelector('#ss-q')).focus({preventScroll:true});
}
// A dialog above this one closed, and what opened it was redrawn meanwhile: focus must not fall out.
document.addEventListener('close', e => {
  if (!section || e.target === sectionDialog() || document.querySelector('dialog[open]:not(#section-dialog)')) return;
  if (!sectionDialog().contains(document.activeElement) || document.activeElement === sectionDialog()) sectionFocusCard(section.lastCard);
}, true);
function closeSection() {
  const d = sectionDialog(); if (!d?.open || d.classList.contains('is-closing')) return;
  clearTimeout(section?.typing);
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return d.close();
  d.classList.add('is-closing'); setTimeout(() => { if (d.open) d.close(); }, 130);
}
function sectionClosed() {
  const d = sectionDialog(), s = section; d.classList.remove('is-closing');
  document.documentElement.classList.remove('section-open');
  if (!s) return;
  s.watch?.disconnect(); section = null;
  const note = document.getElementById('toast'); if (note) document.body.append(note);
  d.innerHTML = '';
  // Back to the control that opened it; the page may have been redrawn, or the stage emptied, meanwhile.
  const col = document.querySelector(`#${CSS.escape(s.board)} .sb-col[data-stage="${s.stage}"]`), expand = col?.querySelector('[data-sb-expand]');
  const target = expand?.checkVisibility() ? expand : (col?.checkVisibility() ? col.querySelector('.sb-head') : document.querySelector(`#${CSS.escape(s.board)} .sb-col.is-open .sb-head`));
  (target || document.querySelector('#app .ws-main .empty-state a, #app .ws-main a, #app a'))?.focus({preventScroll:true});
}
const sectionIsOpen = () => !!section;
document.addEventListener('click', e => {
  const control = e.target.closest('[data-sb-expand]'), board = control?.closest('[data-stage-board]');
  if (board) openSection(board, control.dataset.sbExpand);
});
// Leaving the page (Back, a link): the dialog belongs to the page it was opened from.
addEventListener('hashchange', () => { const d = sectionDialog(); if (d?.open) d.close(); });
/* Ordered products, wherever they appear (orders, jobs, history): the current neutral product render,
   recoloured in the browser with the purchased colour (product-visuals.js, no new renders), and the
   material and colour as bought. Lines from before colour snapshots show their name without a swatch. */
const orderLineHex = item => /^#[0-9a-f]{6}$/i.test(item.color_hex || '') ? item.color_hex.toLowerCase() : '';
function orderLineConfig(item) {
  const hex = orderLineHex(item), text = [item.material, item.color ? colorName(item.color) : ''].filter(Boolean).join(' · ');
  return text ? `<span class="line-config">${hex ? `<span class="line-swatch" style="--swatch:${hex}" title="${esc(hex)}" aria-hidden="true"></span>` : ''}${esc(text)}</span>` : '';
}
function orderLineThumb(item, className = '') {
  if (!item.thumbnail) return `<span class="row-thumb line-thumb ${className}" role="img" aria-label="Product preview unavailable">${icon('camera')}</span>`;
  const hex = orderLineHex(item), cached = hex && tintCache.get(tintKey(item.thumbnail, hex, 160));
  return `<span class="row-thumb line-thumb ${className}"><img ${cached ? 'class="is-ready" ' : ''}src="${esc(cached || item.thumbnail)}" data-source="${esc(item.thumbnail)}" ${hex ? `data-color="${hex}" data-tint-size="160"` : ''} ${cached ? `data-tinted="${hex}"` : ''} alt="" width="640" height="640" loading="lazy" decoding="async" onload="orderLineThumbLoaded(this)" onerror="orderLineThumbFailed(this)"></span>`;
}
function orderLineThumbLoaded(img) {
  if (img.dataset.color && img.dataset.tinted !== img.dataset.color) { tintProductImage(img); if (img.src.startsWith('data:')) return; }
  img.classList.add('is-ready');
}
function orderLineThumbFailed(img) {
  const box = img.parentElement; box.setAttribute('role', 'img'); box.setAttribute('aria-label', 'Product preview unavailable'); box.innerHTML = icon('camera');
}
/* Read-only detail dialogs (approvals, printing jobs, orders): a header, scrolling sections and a footer. */
const reviewItem = (label, value) => `<div><dt>${esc(label)}</dt><dd>${value || '<span class="muted">—</span>'}</dd></div>`;
const reviewSection = (title, body) => `<section class="review-section"><h3>${esc(title)}</h3>${body}</section>`;
function openReview(title, subtitle, body, actions) {
  const dialog = $('#modal'); dialog.className = 'review-dialog';
  dialog.innerHTML = `<div class="review-frame"><header class="review-head"><div><p class="ws-crumb">${esc(subtitle)}</p><h2>${esc(title)}</h2></div><button type="button" class="icon-btn" data-close-modal aria-label="Close">${icon('close')}</button></header><div class="review-body">${body}</div><footer class="review-foot"><button type="button" class="btn-ghost btn-sm" data-close-modal>Close</button>${actions || ''}</footer></div>`;
  dialog.addEventListener('close', () => { dialog.querySelector('[data-cad-viewer]')?.disposeViewer?.(); dialog.className = ''; }, {once:true});
  nameDialog(dialog);
  if (!dialog.open) dialog.showModal();
  return dialog;
}
// The shared dialog (details, reviews, confirmations): focus stays inside it, whoever opens it.
keepFocusInside(document.getElementById('modal'));
const rowMenu = (id, items) => `<div class="dropdown row-menu"><button type="button" class="icon-btn" id="${id}-button" data-dropdown aria-expanded="false" aria-controls="${id}" aria-label="More actions">${icon('more')}</button><div class="dropdown-menu align-end" id="${id}" hidden>${items}</div></div>`;
// The API stores UTC timestamps without an offset; read them as UTC rather than local time.
const parseServerDate = value => new Date(typeof value === 'string' && !/(Z|[+-]\d\d:?\d\d)$/.test(value) ? value + 'Z' : value);
function timeAgo(value) {
  const seconds = (Date.now() - parseServerDate(value)) / 1000;
  if (!Number.isFinite(seconds)) return '—';
  for (const [limit, size, unit] of [[60, 1, 'second'], [3600, 60, 'minute'], [86400, 3600, 'hour'], [2592000, 86400, 'day']]) if (seconds < limit) return new Intl.RelativeTimeFormat('en', {numeric:'auto'}).format(-Math.floor(seconds / size), unit);
  return parseServerDate(value).toLocaleDateString();
}
// Client-side search for any list marked with data-search rows.
document.addEventListener('input', e => {
  const list = e.target.dataset?.filterList && document.getElementById(e.target.dataset.filterList); if (!list) return;
  const query = e.target.value.trim().toLowerCase(); let shown = 0;
  list.querySelectorAll('[data-search]').forEach(row => { row.hidden = !!query && !row.dataset.search.includes(query); shown += !row.hidden; });
  list.querySelector('[data-filter-empty]')?.toggleAttribute('hidden', shown > 0 || !query);
  list.querySelectorAll('[data-stage-board]').forEach(board => syncStageMatches(board, query));
});

/* Light/dark switch: applies immediately, then persists to the account when signed in. */
const effectiveTheme = () => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
const themeToggle = () => `<button type="button" class="theme-toggle" role="switch" aria-label="Dark appearance" aria-checked="${effectiveTheme() === 'dark'}" data-theme-toggle><span class="theme-toggle-track" aria-hidden="true"><span class="theme-toggle-thumb"><svg class="theme-icon theme-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="3.7"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/></svg><svg class="theme-icon theme-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.1A8 8 0 0 1 9.9 4a8 8 0 1 0 10.1 10.1Z"/></svg></span></span><span class="theme-toggle-label" aria-hidden="true">${effectiveTheme() === 'dark' ? 'Dark' : 'Bright'}</span></button>`;
function syncThemeToggle() {
  const dark = effectiveTheme() === 'dark';
  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
    button.setAttribute('aria-checked', String(dark));
    button.querySelector('.theme-toggle-label').textContent = dark ? 'Dark' : 'Bright';
  });
}
let themeSaving = false;
async function toggleTheme() {
  if (themeSaving) return;
  const previous = account?.theme, next = effectiveTheme() === 'dark' ? 'light' : 'dark';
  applyTheme(next); syncThemeToggle();
  if (!account) return;
  themeSaving = true;
  try { account = await api('/preferences', {method:'PUT', body:JSON.stringify({theme:next})}); }
  catch (e) { applyTheme(previous || 'system'); syncThemeToggle(); showError(e); }
  finally { themeSaving = false; }
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncThemeToggle);
