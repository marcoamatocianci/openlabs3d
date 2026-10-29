/* Shared navigation: one topbar, account menu, mobile menu and workspace layout for every role.
   Visibility only mirrors permissions; the API enforces them independently. */
const iconPaths = {
  menu:'<path d="M4 7h16M4 12h16M4 17h16"/>', close:'<path d="M6 6l12 12M18 6 6 18"/>', chevron:'<path d="m6 9 6 6 6-6"/>',
  cart:'<path d="M3 4h2l2.3 10.1a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 1.9-1.4L21 8H6.1"/><circle cx="10" cy="20" r="1.3"/><circle cx="17" cy="20" r="1.3"/>',
  more:'<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
  plus:'<path d="M12 5v14M5 12h14"/>', search:'<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  camera:'<path d="M4 8.5h3.2L9 6h6l1.8 2.5H20V19H4z"/><circle cx="12" cy="13.2" r="3.4"/>', logout:'<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10"/>'
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
const NAVIGATION = {
  guest:{primary:[marketplaceItem('Explore')]},
  buyer:{primary:[marketplaceItem('Explore'), ordersItem], cart:true, menu:[accountItem, {href:'onboarding', label:'Become a printing host'}]},
  host:{primary:[marketplaceItem('Marketplace'), {href:'host', label:'Host workspace', match:isHostRoute, count:'jobs'}], cart:true, menu:[accountItem, ordersItem]},
  admin:{primary:[marketplaceItem('Marketplace'), {href:'admin', label:'Admin workspace', match:isAdminRoute, count:'approvals'}], menu:[accountItem]}
};
const WORKSPACES = {
  admin:{label:'Admin workspace', groups:[
    {items:[{href:'admin', label:'Overview', match:route => route === 'admin'}]},
    {label:'Marketplace', items:[{href:'admin/products', label:'Products', match:route => routeIn(route, 'admin/products', 'admin/create-official', 'edit-listing')}, {href:'admin/printers', label:'Printers'}, {href:'admin/materials', label:'Materials'}, {href:'admin/categories', label:'Categories'}]},
    {label:'People', items:[{href:'admin/users', label:'Users'}, {href:'admin/hosts', label:'Printing hosts'}, {href:'admin/pending', label:'Approvals', count:'approvals'}]},
    {label:'Operations', items:[{href:'admin/orders', label:'Orders'}]},
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

/* Avatar with initials fallback; other users' pictures are private, so pass avatar:'' for them. */
function initials(user) {
  const named = [user.first_name, user.last_name].filter(Boolean).map(s => s[0]).join('');
  return (named || String(user.display_name || user.username || '?').replace(/[^A-Za-z0-9]/g, '').slice(0, 2) || '?').toUpperCase().slice(0, 2);
}
function avatarHtml(user, size=32, extra='') {
  const hue = [...String(user.username || user.email || '')].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 200);
  return `<span class="avatar ${extra}" style="--size:${size}px;--hue:${hue}" aria-hidden="true"><span class="avatar-initials">${esc(initials(user))}</span>${user.avatar ? `<img src="/api/profile/avatar?v=${encodeURIComponent(user.avatar)}" alt="" onerror="this.remove()">` : ''}</span>`;
}

/* Topbar: brand · primary navigation · actions · account menu. */
function navbarHtml(route) {
  const config = NAVIGATION[navRole()], count = opsCart.reduce((n, i) => n + i.quantity, 0);
  const primary = config.primary.map(item => { const active = itemActive(item, route); return `<a class="nav-link ${active ? 'active' : ''}" href="#${item.href}" ${active ? 'aria-current="page"' : ''}>${esc(item.label)}${countBadge(item.count)}</a>`; }).join('');
  const cartActive = routeIn(route, 'basket', 'checkout', 'checkout-cart');
  const cart = `<a class="nav-icon cart-link ${cartActive ? 'active' : ''}" href="#basket" ${cartActive ? 'aria-current="page"' : ''} ${config.cart ? '' : 'hidden'}>${icon('cart')}<span class="sr-only">Basket</span><b id="count" class="count-badge" ${count ? '' : 'hidden'}>${count}</b></a>`;
  // Until the session check returns, leave the account area empty instead of flashing "Sign in".
  const actions = !authChecked ? '' : account ? userMenuHtml(config, route) : `<a class="nav-link ${route === 'account' ? 'active' : ''}" href="#account" ${route === 'account' ? 'aria-current="page"' : ''}>Sign in</a><a class="btn btn-sm nav-cta" href="#account?mode=register">Create account</a>`;
  return `<div class="topbar-inner"><button type="button" class="nav-icon nav-toggle" data-nav-toggle aria-controls="primary-nav" aria-expanded="${navState.mobile}" aria-label="${navState.mobile ? 'Close menu' : 'Open menu'}">${icon(navState.mobile ? 'close' : 'menu')}</button><a class="brand" href="#home"><span class="logo-image"><img src="openlabs3d-logo.png" alt=""></span><span id="brand">${esc(publicSettings.marketplace_name || 'OpenLabs3D')}</span></a><nav id="primary-nav" class="primary-nav ${navState.mobile ? 'open' : ''}" aria-label="Main">${primary}</nav><div class="topbar-actions">${cart}${actions}</div></div>`;
}
function userMenuHtml(config, route) {
  const active = config.menu.some(item => itemActive(item, route));
  const items = config.menu.map(item => { const current = itemActive(item, route); return `<a class="menu-item ${current ? 'active' : ''}" href="#${item.href}" ${current ? 'aria-current="page"' : ''}>${esc(item.label)}</a>`; }).join('');
  return `<div class="dropdown user-menu"><button type="button" class="user-trigger ${active ? 'active' : ''}" id="user-menu-button" data-dropdown aria-expanded="false" aria-controls="user-menu">${avatarHtml(account, 28)}<span class="user-name">${esc(account.username)}</span>${icon('chevron')}<span class="sr-only">Account menu</span></button><div class="dropdown-menu align-end" id="user-menu" hidden><div class="menu-header">${avatarHtml(account, 36)}<div><strong>${esc(account.display_name || account.username)}</strong><span>${esc(account.email)}</span></div></div>${items}<hr class="menu-separator"><button type="button" class="menu-item" data-logout>${icon('logout')}Log out</button></div></div>`;
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
    if (account.role === 'admin') { const o = await api('/admin/overview'); if (account?.id === owner) setNavCount('approvals', o.pending_hosts + o.products_pending); }
    else { const jobs = await api('/host/jobs'); if (account?.id === owner) setNavCount('jobs', jobs.filter(j => j.status === 'available').length); }
    renderNavbar();
  } catch (e) { console.warn('Navigation counts unavailable', e); }
}

/* Dropdowns follow the disclosure pattern: Escape closes, arrows move between entries. */
const dropdownItems = menu => [...menu.querySelectorAll('a[href],button:not([disabled])')];
function setDropdown(trigger, open) {
  const menu = document.getElementById(trigger.getAttribute('aria-controls')); if (!menu) return;
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
  return `<div class="workspace">${sidebarHtml(kind, route)}<section class="ws-main" aria-labelledby="ws-title"><header class="ws-head"><div>${group?.label ? `<p class="ws-crumb">${esc(group.label)}</p>` : ''}<h1 id="ws-title">${esc(title)}</h1></div>${action ? `<div class="ws-actions">${action}</div>` : ''}</header>${body}</section></div>`;
}

/* Small building blocks reused by workspace and account pages. */
const statusTones = {approved:'success', published:'success', completed:'success', active:'success', pending:'warning', available:'warning', rejected:'danger', cancelled:'danger', suspended:'danger', accepted:'info', printing:'info', ready:'info'};
const statusText = status => { const text = String(status).replaceAll('_', ' '); return text.charAt(0).toUpperCase() + text.slice(1); };
const statusBadge = (status, label) => `<span class="status status-${statusTones[status] || 'neutral'}">${esc(label || statusText(status))}</span>`;
function filterChips(label, options, selected) { return `<nav class="chips" aria-label="${esc(label)}">${options.map(o => { const on = o.value === selected; return `<a class="chip ${on ? 'active' : ''}" href="#${o.href}" ${on ? 'aria-current="true"' : ''}>${esc(o.label)}${o.count != null ? `<span>${o.count}</span>` : ''}</a>`; }).join('')}</nav>`; }
const searchBox = (list, placeholder) => `<label class="search-field">${icon('search')}<span class="sr-only">${esc(placeholder)}</span><input type="search" placeholder="${esc(placeholder)}" data-filter-list="${list}" autocomplete="off"></label>`;
const toolbar = (...parts) => `<div class="ws-toolbar">${parts.filter(Boolean).join('')}</div>`;
const emptyState = (title, text, action='') => `<div class="empty-state"><h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;
const statCard = (label, value, href, hint='', tone='') => `<a class="stat-card ${tone}" href="#${href}"><span>${esc(label)}</span><strong>${value}</strong>${hint ? `<small>${esc(hint)}</small>` : ''}</a>`;
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
});

/* Light/dark switch: applies immediately, then persists to the account when signed in. */
const effectiveTheme = () => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
const themeToggle = () => `<button type="button" class="switch" role="switch" aria-checked="${effectiveTheme() === 'dark'}" data-theme-toggle><span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span><span>Dark mode</span></button>`;
async function toggleTheme() {
  const previous = account?.theme, next = effectiveTheme() === 'dark' ? 'light' : 'dark';
  applyTheme(next); document.querySelectorAll('[data-theme-toggle]').forEach(b => b.setAttribute('aria-checked', next === 'dark'));
  if (!account) return;
  try { account = await api('/preferences', {method:'PUT', body:JSON.stringify({theme:next})}); }
  catch (e) { applyTheme(previous || 'system'); document.querySelectorAll('[data-theme-toggle]').forEach(b => b.setAttribute('aria-checked', effectiveTheme() === 'dark')); showError(e); }
}
