/* Custom requests: one shared page for buyers and printing hosts (acting as customers), plus the
   administrator review list. Requests are reviewed and quoted individually; they never create orders. */
Object.assign(iconPaths, {
  clip:'<path d="m20 11.5-7.8 7.8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8"/>',
  cube:'<path d="M12 3 4 7.5v9L12 21l8-4.5v-9z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
  doc:'<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
  upload:'<path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><circle cx="12" cy="7.8" r=".6" fill="currentColor"/>'
});
const CR_STATUS = {submitted:['Submitted', 'info', 'Waiting for an administrator to review your requirements.'], under_review:['Under review', 'warning', 'An administrator is assessing feasibility and may contact you with questions.'], quoted:['Quoted', 'success', 'A quotation has been prepared and is sent to you separately. Nothing is charged automatically.'], closed:['Closed', 'neutral', 'This request is closed.']};
const CR_CONDITIONS = [['heat', 'Heat resistance', 'Above 60 °C, near hot plates or incubators'], ['cold', 'Cold storage', 'Fridge, freezer or −80 °C'], ['chemicals', 'Chemical exposure', 'Solvents, acids, bleach'], ['cleaning', 'Frequent cleaning', 'Ethanol wipes or disinfectants'], ['sterilization', 'Sterilization', 'Autoclave or other sterilization'], ['mechanical', 'Mechanical load', 'Weight, clamping or impacts'], ['uv', 'UV exposure', 'Sunlight or UV cabinets']];
const CR_FILES = {kinds:{stl:'model', '3mf':'model', png:'image', jpg:'image', jpeg:'image', webp:'image', pdf:'document'}, limits:{model:20, image:10, document:10}, max:6, total:25};
const crStatus = (s, label) => `<span class="status status-${(CR_STATUS[s] || [])[1] || 'neutral'}">${esc(label || (CR_STATUS[s] || [statusText(s)])[0])}</span>`;
// What a customer sees: a quoted request is the accepted one (the quotation follows separately).
const CR_CUSTOMER_LABELS = {quoted:'Accepted · quote sent'};
// My requests: Active requests (submitted, under review, accepted) and Request history (closed), split by
// the API (app/lifecycle.py). An accepted request stays active: quotation or production work follows.
inPageRoutes.add('#my-requests');
const CR_SCOPE_NAMES = {active:'Active requests', history:'Request history'};
const crSize = bytes => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const crDate = value => parseServerDate(value).toLocaleDateString(undefined, {day:'numeric', month:'short', year:'numeric'});
const crKindIcon = kind => icon(kind === 'model' ? 'cube' : kind === 'image' ? 'camera' : 'doc');
const crConditionLabels = list => list.map(c => (CR_CONDITIONS.find(([k]) => k === c) || [c, c])[1]);
const crKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
let crMaterials = null, crFiles = [], crSubmitting = false, crRequest = 0;

/* Navigation: guests and buyers see it in the topbar; hosts in their account menu, beside My orders. */
const customRequestsItem = {href:'custom', label:'Custom requests', match:route => routeIn(route, 'custom', 'my-requests')};
NAVIGATION.guest.primary.push(customRequestsItem); NAVIGATION.buyer.primary.push(customRequestsItem); NAVIGATION.host.menu.push(customRequestsItem);
WORKSPACES.admin.groups.find(g => g.label === 'Operations').items.push({href:'admin/requests', label:'Custom requests', count:'requests'});
signedInRoutes.push('my-requests');
adminRedirects.splice(adminRedirects.indexOf('custom'), 1);
const customSignInPrompt = signInPrompt;
signInPrompt = route => routeIn(route, 'my-requests') ? (sessionStorage.setItem('ol3d-return-to', route), accessPage('Sign in to continue', 'Sign in to follow the review of your custom requests.', '<a class="btn" href="#account">Sign in</a><a class="btn light" href="#account?mode=register">Create account</a>')) : customSignInPrompt(route);
const customWorkspaceRoute = workspaceRoute;
workspaceRoute = function(route) {
  if (routeIn(route, 'custom', 'my-requests')) return () => account?.role === 'admin' ? location.replace('#admin/requests') : renderCustomRequests(route);
  return customWorkspaceRoute(route);
};

/* Shared page shell: heading, tabs for signed-in customers, and the review notice. */
function crShell(route, body, count) {
  document.title = `Custom requests · ${publicSettings.marketplace_name || 'OpenLabs3D'}`;
  const tabs = account ? filterChips('Custom requests', [{value:'custom', label:'New request', href:'custom'}, {value:'my-requests', label:'My requests', href:'my-requests', count}], routeIn(route, 'my-requests') ? 'my-requests' : 'custom') : '';
  return layout(`<div class="cr-page"><header class="cr-head"><p class="eyebrow eyebrow-dot">Custom requests</p><h1>Have a laboratory tool in mind?</h1><p class="cr-lead">Describe your idea or laboratory challenge. We'll review your requirements and help you explore a custom 3D-printed solution.</p>${tabs}</header>${body}</div>`);
}
const crNotice = `<div class="cr-notice" role="note">${icon('info')}<p><strong>Review and quotation required.</strong> Custom requests require individual review and quotation. Submitting a request does not place an order or initiate payment.</p></div>`;
const crSteps = `<ol class="cr-steps"><li><strong>Describe the problem</strong><span>What the tool should do, where it is used and what it must fit.</span></li><li><strong>Add references</strong><span>Photos, sketches, drawings or an existing STL/3MF help us understand it.</span></li><li><strong>Review</strong><span>An administrator assesses feasibility and may contact you with questions.</span></li><li><strong>Quotation</strong><span>You receive a quote for design and manufacture. You decide whether to proceed.</span></li></ol>`;
const crAside = `<aside class="cr-aside">${crNotice}<section class="cr-aside-card"><h2>How it works</h2>${crSteps}<p class="cr-aside-foot">No CAD or 3D-printing knowledge needed. Describe the task in your own words.</p></section></aside>`;

async function renderCustomRequests(route) {
  const request = ++crRequest, mine = routeIn(route, 'my-requests');
  const stale = () => request !== crRequest || currentRoute() !== route;
  if (!authChecked) { $('#app').innerHTML = layout('<div class="ws-loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading…</div>'); return; }
  if (!account) { $('#app').innerHTML = crShell(route, `<div class="cr-layout">${crAside}<section class="cr-intro le-panel"><h2>What we'll ask you</h2><ul class="cr-outline">${['Project description: the task the tool should perform', 'Dimensions and the equipment it must fit, in millimetres', 'Quantity, preferred material and lab conditions', 'Optional reference files: STL, 3MF, images or PDF'].map(t => `<li>${esc(t)}</li>`).join('')}</ul><p class="le-note">Sign in or create a free account to submit a request and follow its review.</p><div class="actions"><a class="btn" href="#account" data-return="custom">Sign in to submit a request</a><a class="btn light" href="#account?mode=register" data-return="custom">Create account</a></div></section></div>`); $('#app').querySelectorAll('[data-return]').forEach(a => a.onclick = () => sessionStorage.setItem('ol3d-return-to', 'custom')); return; }
  const old = $('#app .cr-page');
  if (!old) $('#app').innerHTML = crShell(route, '<div class="ws-loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading…</div>');
  try {
    const q = hashQuery(), view = {scope:q.scope === 'history' ? 'history' : 'active', group:q.group || 'all'};
    let data;
    try { [data] = await Promise.all([api('/custom-requests?' + new URLSearchParams(mine ? view : {scope:'active'})), mine ? null : crLoadMaterials()]); }
    catch (e) { if (mine && e.status === 422 && view.group !== 'all') { location.replace('#' + scopeHref('my-requests', {scope:view.scope}, {})); return; } throw e; }
    if (stale()) return;
    // The tab counts the requests still in progress.
    $('#app').innerHTML = crShell(route, mine ? crList(data) : crForm(), data.scopes.active.total);
    if (mine) crBindList(); else crBindForm();
  } catch (e) {
    if (!stale()) $('#app').innerHTML = crShell(route, `<div class="banner danger" role="alert"><span>${esc(e.message)}</span><button type="button" class="btn-ghost btn-sm" onclick="render()">Try again</button></div>`);
  }
}
async function crLoadMaterials() { if (!crMaterials) crMaterials = await api('/materials').catch(() => []); return crMaterials; }

/* The request form: five clearly separated sections on one page. */
function crDraft() { try { return JSON.parse(sessionStorage.getItem('ol3d-request-draft-' + account.id) || '{}'); } catch (e) { return {}; } }
function crForm() {
  const d = crDraft(), field = (label, control, hint = '', required = false) => `<label class="le-field"><span class="cr-label">${label}${required ? ' <span class="le-req" aria-hidden="true">*</span>' : ' <span class="eq-optional">Optional</span>'}</span>${control}${hint ? `<small>${hint}</small>` : ''}<span class="cr-error" data-error></span></label>`;
  const groups = ['FDM', 'RESIN'].map(t => [t, (crMaterials || []).filter(m => m.technology === t)]).filter(([, m]) => m.length);
  const materials = `<select name="material"><option value="">No preference: recommend a material</option>${groups.map(([t, list]) => `<optgroup label="${t === 'FDM' ? 'FDM filaments' : 'Resins'}">${list.map(m => `<option ${d.material === m.name ? 'selected' : ''}>${esc(m.name)}</option>`).join('')}</optgroup>`).join('')}</select>`;
  const chips = CR_CONDITIONS.map(([key, label, hint]) => `<button type="button" class="le-chip cr-chip" data-condition="${key}" aria-pressed="${(d.conditions || []).includes(key)}" title="${esc(hint)}">${esc(label)}</button>`).join('');
  const verify = account.email_verified ? '' : `<div class="banner warning" role="status"><span>Verify your email address before submitting. You can still prepare your request now.</span><a class="btn-ghost btn-sm" href="#account">Verify email</a></div>`;
  const section = (n, title, body) => `<section class="le-panel cr-section" aria-labelledby="cr-s${n}"><h2 id="cr-s${n}"><span class="cr-num" aria-hidden="true">${n}</span>${title}</h2>${body}</section>`;
  return `<div class="cr-layout">${crAside}<form id="cr-form" class="cr-form" novalidate data-bound="1">${verify}
    ${section(1, 'Project description', field('Request title', `<input name="title" maxlength="120" required value="${esc(d.title || '')}" placeholder="e.g. Cryovial rack for a −80 °C freezer box" autocomplete="off">`, 'A short name for your request.', true)
      + field('What should the tool help you do?', `<textarea name="application" maxlength="5000" required rows="5" placeholder="Describe the laboratory problem, the procedure it supports and what you use today.">${esc(d.application || '')}</textarea>`, 'At least 20 characters. Mention how it is used and anything that frustrates you about current solutions.', true))}
    ${section(2, 'Dimensions &amp; technical requirements', field('Required dimensions', `<textarea name="dimensions" maxlength="2000" required rows="3" placeholder="e.g. Footprint no larger than 130 × 130 mm, height under 50 mm">${esc(d.dimensions || '')}</textarea>`, 'Use millimetres. Exact sizes unknown? Describe the space or the items it must hold, e.g. “fits inside a standard freezer box”.', true)
      + field('Compatible equipment', `<textarea name="compatibility" maxlength="2000" rows="2" placeholder="e.g. Corning 2 mL cryovials, Eppendorf 5424 centrifuge">${esc(d.compatibility || '')}</textarea>`, 'Brands, models or consumables it must fit or work with.'))}
    ${section(3, 'Quantity &amp; materials', `<div class="cr-row">${field('Quantity', `<input name="quantity" type="number" inputmode="numeric" min="1" max="10000" step="1" required value="${esc(d.quantity || 1)}">`, 'Units needed.', true)}${field('Preferred material', materials, 'Not sure? Leave it open and we will recommend one.')}</div>
      <fieldset class="cr-conditions"><legend>Lab conditions <span class="eq-optional">Optional · select all that apply</span></legend><div class="le-chips">${chips}</div></fieldset>`
      + field('Other requirements', `<textarea name="requirements" maxlength="3000" rows="3" placeholder="e.g. Must survive daily 70% ethanol wipes; contact with cell-culture media; needs to stack">${esc(d.requirements || '')}</textarea>`, 'Temperatures, chemicals, cleaning or sterilization, mechanical loads, tolerances, or anything else we should know.'))}
    ${section(4, 'Reference files', `<div class="le-field"><span class="cr-label">Supporting files <span class="eq-optional">Optional</span></span><label class="le-drop cr-drop" data-drop><input type="file" id="cr-files" multiple accept=".stl,.3mf,.png,.jpg,.jpeg,.webp,.pdf"><span class="le-drop-main">${icon('upload')}<strong>Drop files here or browse</strong><small>STL, 3MF, PNG, JPEG, WebP or PDF · up to ${CR_FILES.max} files · models ${CR_FILES.limits.model} MB, images and PDFs ${CR_FILES.limits.image} MB · ${CR_FILES.total} MB in total</small></span></label><span class="cr-error" id="cr-file-error" role="alert"></span><ul class="cr-files" id="cr-file-list" aria-label="Selected files"></ul></div>`)}
    ${section(5, 'Review &amp; submit', `<dl class="le-summary cr-summary" id="cr-summary"></dl>${crNotice}<p class="form-error" id="cr-submit-error" role="alert"></p><div class="cr-submit"><span class="le-note">An administrator reviews every request. You can follow its status in My requests.</span><button class="primary cr-submit-btn" ${account.email_verified ? '' : 'disabled'}><span class="cr-submit-label">Submit Request for Review</span></button></div>`)}
  </form></div>`;
}
function crBindForm() {
  const form = $('#cr-form'), list = $('#cr-file-list'), drop = form.querySelector('[data-drop]'), input = $('#cr-files'), fileError = $('#cr-file-error');
  crFiles.forEach(f => f.url && URL.revokeObjectURL(f.url)); crFiles = [];
  const values = () => { const d = Object.fromEntries(new FormData(form)); d.conditions = [...form.querySelectorAll('[data-condition][aria-pressed=true]')].map(b => b.dataset.condition); return d; };
  const saveDraft = () => { try { const {title, application, dimensions, compatibility, quantity, material, requirements, conditions} = values(); sessionStorage.setItem('ol3d-request-draft-' + account.id, JSON.stringify({title, application, dimensions, compatibility, quantity, material, requirements, conditions})); } catch (e) {} };
  const summary = () => {
    const d = values(), row = (label, value, required) => `<div><dt>${label}</dt><dd>${value ? esc(value) : required ? '<span class="le-missing">Required</span>' : '<span class="muted">Not specified</span>'}</dd></div>`;
    $('#cr-summary').innerHTML = row('Title', d.title.trim(), 1) + row('Application', d.application.trim().slice(0, 140) + (d.application.trim().length > 140 ? '…' : ''), 1) + row('Dimensions', d.dimensions.trim().slice(0, 140), 1)
      + row('Quantity', Number(d.quantity) >= 1 ? `${d.quantity} ${Number(d.quantity) === 1 ? 'unit' : 'units'}` : '', 1) + row('Material', d.material || 'No preference') + row('Conditions', crConditionLabels(d.conditions).join(', '))
      + row('Reference files', crFiles.length ? `${crFiles.length} ${crFiles.length === 1 ? 'file' : 'files'} · ${crSize(crFiles.reduce((n, f) => n + f.file.size, 0))}` : '');
  };
  const drawFiles = () => {
    list.innerHTML = crFiles.map((f, i) => `<li class="cr-file">${f.kind === 'image' ? `<img src="${f.url}" alt="">` : `<span class="cr-file-icon">${crKindIcon(f.kind)}</span>`}<span class="cr-file-name"><strong>${esc(f.file.name)}</strong><small>${f.kind === 'model' ? '3D model' : f.kind === 'image' ? 'Image' : 'PDF document'} · ${crSize(f.file.size)}</small></span><button type="button" class="icon-btn" data-remove="${i}" aria-label="Remove ${esc(f.file.name)}">${icon('close')}</button></li>`).join('');
    summary();
  };
  const addFiles = files => {
    const problems = [];
    for (const file of files) {
      const kind = CR_FILES.kinds[file.name.split('.').pop().toLowerCase()];
      if (!kind) problems.push(`${file.name}: unsupported type`);
      else if (file.size > CR_FILES.limits[kind] * 1024 * 1024) problems.push(`${file.name}: larger than ${CR_FILES.limits[kind]} MB`);
      else if (!file.size) problems.push(`${file.name}: empty file`);
      else if (crFiles.length >= CR_FILES.max) problems.push(`${file.name}: at most ${CR_FILES.max} files`);
      else if (crFiles.reduce((n, f) => n + f.file.size, 0) + file.size > CR_FILES.total * 1024 * 1024) problems.push(`${file.name}: total exceeds ${CR_FILES.total} MB`);
      else if (crFiles.some(f => f.file.name === file.name && f.file.size === file.size)) problems.push(`${file.name}: already added`);
      else crFiles.push({file, kind, url:kind === 'image' ? URL.createObjectURL(file) : ''});
    }
    fileError.textContent = problems.join(' · '); drawFiles();
  };
  input.onchange = () => { addFiles([...input.files]); input.value = ''; };
  ['dragenter', 'dragover'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add('is-over'); }));
  ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove('is-over'); }));
  drop.addEventListener('drop', e => addFiles([...e.dataTransfer.files]));
  list.onclick = e => { const b = e.target.closest('[data-remove]'); if (!b) return; const [f] = crFiles.splice(+b.dataset.remove, 1); if (f.url) URL.revokeObjectURL(f.url); fileError.textContent = ''; drawFiles(); };
  form.querySelectorAll('[data-condition]').forEach(b => b.onclick = () => { b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') !== 'true'); saveDraft(); summary(); });
  form.addEventListener('input', e => { const f = e.target.closest('.le-field'); if (f && e.target.getAttribute('aria-invalid')) { e.target.removeAttribute('aria-invalid'); f.querySelector('[data-error]').textContent = ''; } $('#cr-submit-error').textContent = ''; saveDraft(); summary(); });
  const invalid = (name, message) => { const el = form.elements[name]; el.setAttribute('aria-invalid', 'true'); el.closest('.le-field').querySelector('[data-error]').textContent = message; return el; };
  form.onsubmit = async e => {
    e.preventDefault(); if (crSubmitting) return;
    const d = values(), error = $('#cr-submit-error'), quantity = Number(d.quantity); error.textContent = '';
    const problems = [d.title.trim().length < 3 && invalid('title', 'Enter a title of at least 3 characters.'), d.application.trim().length < 20 && invalid('application', 'Describe the task in at least 20 characters.'),
      d.dimensions.trim().length < 3 && invalid('dimensions', 'Describe the required dimensions, even approximately.'), !(Number.isInteger(quantity) && quantity >= 1 && quantity <= 10000) && invalid('quantity', 'Enter a whole number from 1 to 10,000.')].filter(Boolean);
    if (problems.length) { problems[0].focus(); error.textContent = 'Please complete the highlighted fields.'; return; }
    let key = sessionStorage.getItem('ol3d-request-key'); if (!key) { key = crKey(); sessionStorage.setItem('ol3d-request-key', key); }
    const body = new FormData();
    body.append('payload', JSON.stringify({idempotency_key:key, title:d.title.trim(), application:d.application.trim(), dimensions:d.dimensions.trim(), compatibility:d.compatibility.trim(), quantity, material:d.material, conditions:d.conditions, requirements:d.requirements.trim()}));
    crFiles.forEach(f => body.append('files', f.file, f.file.name));
    const button = form.querySelector('.cr-submit-btn'); crSubmitting = true; button.disabled = true; form.setAttribute('aria-busy', 'true');
    button.querySelector('.cr-submit-label').innerHTML = `<span class="spinner" aria-hidden="true"></span>${crFiles.length ? 'Uploading files…' : 'Submitting…'}`;
    try {
      const created = await api('/custom-requests', {method:'POST', body});
      sessionStorage.removeItem('ol3d-request-key'); sessionStorage.removeItem('ol3d-request-draft-' + account.id);
      crFiles.forEach(f => f.url && URL.revokeObjectURL(f.url)); crFiles = [];
      toast(`Request ${created.reference} submitted for review`); location.hash = 'my-requests?created=' + created.id;
    } catch (err) {
      error.textContent = err.message; button.disabled = !account.email_verified; button.querySelector('.cr-submit-label').textContent = 'Submit Request for Review'; form.removeAttribute('aria-busy');
    } finally { crSubmitting = false; }
  };
  summary();
}

/* My requests: compact cards; details expand in place with every submitted specification. */
function crDetails(r, staff = false) {
  const item = (label, value) => `<div><dt>${esc(label)}</dt><dd>${value ? esc(value) : '<span class="muted">Not specified</span>'}</dd></div>`;
  const images = r.files.filter(f => f.kind === 'image');
  const files = r.files.length ? `${images.length ? `<div class="cr-gallery">${images.map(f => `<a href="${esc(f.url)}" target="_blank" rel="noopener"><img src="${esc(f.url)}" alt="${esc(f.filename)}" loading="lazy"></a>`).join('')}</div>` : ''}<ul class="cr-files">${r.files.map(f => `<li class="cr-file"><span class="cr-file-icon">${crKindIcon(f.kind)}</span><span class="cr-file-name"><strong>${esc(f.filename)}</strong><small>${f.kind === 'model' ? '3D model' : f.kind === 'image' ? 'Image' : 'PDF document'} · ${crSize(f.size)}</small></span>${staff && f.kind === 'model' && /\.stl$/i.test(f.filename) ? `<button type="button" class="btn-ghost btn-sm" data-preview-stl="${esc(f.url)}">Preview 3D</button>` : ''}<a class="btn-ghost btn-sm" href="${esc(f.url)}?download=true" download>Download</a></li>`).join('')}</ul>${staff ? '<div class="review-viewer" data-cad-viewer hidden><p role="status">Loading 3D model…</p></div>' : ''}` : '<p class="muted">No reference files attached.</p>';
  return reviewSection('Application', `<p class="cr-text">${esc(r.application)}</p>`)
    + reviewSection('Dimensions & compatibility', `<dl class="detail-grid wide">${item('Required dimensions', r.dimensions)}${item('Compatible equipment', r.compatibility)}</dl>`)
    + reviewSection('Quantity & materials', `<dl class="detail-grid">${item('Quantity', `${r.quantity} ${r.quantity === 1 ? 'unit' : 'units'}`)}${item('Preferred material', r.material || 'No preference')}${item('Lab conditions', crConditionLabels(r.conditions).join(', '))}</dl><dl class="detail-grid wide">${item('Other requirements', r.requirements)}</dl>`)
    + reviewSection(`Reference files (${r.files.length})`, files);
}
function crCard(r, open) {
  const files = r.files.length ? `${icon('clip')}${r.files.length} ${r.files.length === 1 ? 'file' : 'files'}` : `${icon('clip')}No files`;
  return `<article class="section-card cr-card ${open ? 'is-new' : ''}" id="request-${r.id}" data-status="${esc(r.status)}" aria-labelledby="cr-title-${r.id}"><header class="cr-card-head"><div class="cr-card-title"><p class="cr-meta"><span class="mono">${esc(r.reference)}</span><span>Submitted <time datetime="${esc(r.created_at)}">${esc(crDate(r.created_at))}</time></span></p><h2 id="cr-title-${r.id}">${esc(r.title)}</h2></div>${crStatus(r.status, CR_CUSTOMER_LABELS[r.status])}</header>
    <p class="cr-excerpt">${esc(r.application.length > 180 ? r.application.slice(0, 180) + '…' : r.application)}</p>
    <ul class="cr-facts"><li>${r.quantity} ${r.quantity === 1 ? 'unit' : 'units'}</li><li>${esc(r.material || 'Material open')}</li><li class="cr-facts-files">${files}</li></ul>
    <p class="cr-status-note cr-tone-${(CR_STATUS[r.status] || [])[1] || 'neutral'}">${esc(CR_STATUS[r.status]?.[2] || '')}</p>
    <details class="bo-details" ${open ? 'open' : ''}><summary aria-label="View details for ${esc(r.reference)}"><span class="bo-open-label">View details</span><span class="bo-close-label">Hide details</span>${icon('chevron')}</summary><div class="bo-detail-body cr-detail">${crDetails(r)}</div></details></article>`;
}
function crList(data) {
  const created = Number(hashQuery().created), items = data.items;
  if (!data.scopes.active.total && !data.scopes.history.total) return `<div class="section-card">${emptyState('No custom requests yet', 'Describe a laboratory problem or a tool you need. Your submitted requests and their review status appear here.', '<a class="btn btn-sm" href="#custom">Start a request</a>')}</div>`;
  const nav = scopeNav({label:'My requests', base:'my-requests', data, names:CR_SCOPE_NAMES});
  const label = (data.scopes[data.scope].groups.find(g => g.key === data.group) || {}).label;
  const empty = data.scope === 'active' && !data.scopes.active.total ? emptyState("You're all caught up", 'No requests in review at the moment. Closed requests are in Request history.', '<a class="btn btn-sm" href="#custom">Start a request</a>')
    : data.scope === 'history' && !data.scopes.history.total ? emptyState('No request history yet', 'Requests move here once they are closed.')
    : emptyState(`No ${(label || '').toLowerCase()} requests`, 'None of these requests is at this stage.');
  return `${created && items.some(r => r.id === created) ? `<div class="banner info" role="status"><span>Your request was submitted. An administrator will review it; no order or payment has been created.</span></div>` : ''}<div class="cr-scope">${nav.primary}${nav.secondary}</div><div class="cr-list">${items.length ? items.map(r => crCard(r, r.id === created)).join('') : `<div class="section-card">${empty}</div>`}</div>`;
}
function crBindList() { $('#app .cr-card.is-new')?.scrollIntoView({block:'nearest'}); }

/* Administrator review: compact list, read-only specification dialog, status and internal notes. */
let crAdminCache = {};
adminPages['admin/requests'] = async function(route) {
  // Active requests (still to review, quote or produce) by default; closed ones in Request history.
  const q = hashQuery(), legacy = route.split('/')[2], view = legacy ? {scope:legacy === 'closed' ? 'history' : 'active', group:legacy} : {scope:q.scope === 'history' ? 'history' : 'active', group:q.group || 'all'};
  let data;
  try { data = await api('/admin/custom-requests?' + new URLSearchParams(view)); }
  catch (e) { if (e.status === 422 && view.group !== 'all') { location.replace('#' + scopeHref('admin/requests', {scope:view.scope}, {})); return {title:'Custom requests', body:''}; } throw e; }
  const items = data.items;
  crAdminCache = {...crAdminCache, ...Object.fromEntries(items.map(r => [r.id, r]))}; setNavCount('requests', data.scopes.active.groups.find(g => g.key === 'submitted').count);
  // Administrators see the internal status name ("Quoted"); customers see it as "Accepted".
  data.scopes.active.groups.forEach(g => { if (g.key === 'quoted') g.label = CR_STATUS.quoted[0]; });
  const nav = scopeNav({label:'Custom requests', base:'admin/requests', data, names:{active:'Active requests', history:'Request history'}});
  const row = r => `<article class="list-row" data-search="${esc([r.reference, r.title, r.user.username, r.user.email, r.material].join(' ').toLowerCase())}"><div class="row-main"><span class="row-title">${esc(r.title)}</span><span class="row-meta"><span class="mono">${esc(r.reference)}</span> · ${esc(userName(r.user))} · ${esc(roleLabel(r.user.role))} · ${esc(crDate(r.created_at))}</span></div><span class="row-value">${r.quantity} ${r.quantity === 1 ? 'unit' : 'units'}<small>${r.files.length ? `${r.files.length} ${r.files.length === 1 ? 'file' : 'files'}` : 'No files'}</small></span><span class="row-status">${crStatus(r.status)}</span><div class="row-actions"><button type="button" class="btn-ghost btn-sm" onclick="crReview(${r.id})">Review</button></div></article>`;
  const empty = data.scope === 'active' ? ['No requests to handle', 'Submitted, in-review and accepted requests appear here.'] : ['No closed requests', 'Requests move here once they are closed; reopening one brings it back.'];
  return {title:'Custom requests', body:`<p class="muted ws-intro">Requests for custom tools from buyers and printing hosts. They are separate from marketplace orders: updating a status never creates an order, price, listing or host assignment.</p>` + nav.primary + toolbar(nav.secondary, items.length ? searchBox('request-list', 'Search title, reference or requester') : '') + filteredList('request-list', items.map(row), ...empty, 'No requests match your search.')};
};
function crReview(id) {
  const r = crAdminCache[id]; if (!r) return;
  const u = r.user, item = (label, value) => reviewItem(label, value ? esc(value) : '');
  const body = reviewSection('Request', `<dl class="detail-grid">${item('Reference', r.reference)}${reviewItem('Status', crStatus(r.status))}${item('Submitted', safeDate(r.created_at))}${item('Last updated', safeDate(r.updated_at))}</dl>`)
    + crDetails(r, true)
    + reviewSection('Requested by', `<dl class="detail-grid">${item('Username', '@' + u.username)}${item('Email', u.email)}${item('Phone', u.phone)}${item('Location', [u.city, u.country].filter(Boolean).join(', '))}${item('Role', roleLabel(u.role))}</dl>`)
    + reviewSection('Review', `<form id="cr-review-form" class="cr-review-form"><label class="le-field">Status<select name="status">${Object.entries(CR_STATUS).map(([k, [label]]) => `<option value="${k}" ${k === r.status ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select><small>The requester sees the status, not the notes.</small></label><label class="le-field">Internal notes <span class="eq-optional">Administrators only</span><textarea name="admin_notes" maxlength="5000" rows="4" placeholder="Feasibility, questions for the requester, quotation reference…">${esc(r.admin_notes)}</textarea></label><p class="form-error" role="alert"></p></form>`);
  const dialog = openReview(r.title, `Custom request · ${r.reference}`, body, '<button type="submit" form="cr-review-form" class="btn btn-sm">Save review</button>');
  const form = dialog.querySelector('#cr-review-form');
  form.onsubmit = async e => {
    e.preventDefault(); const button = dialog.querySelector('[form=cr-review-form]'); button.disabled = true;
    try { await api('/admin/custom-requests/' + id, {method:'PATCH', body:JSON.stringify(Object.fromEntries(new FormData(form)))}); dialog.close(); toast('Request updated'); refreshNavBadges(true); render(); }
    catch (err) { form.querySelector('.form-error').textContent = err.message; button.disabled = false; }
  };
  dialog.querySelectorAll('[data-preview-stl]').forEach(b => b.onclick = () => {
    const host = dialog.querySelector('[data-cad-viewer]'); dialog.querySelectorAll('[data-preview-stl]').forEach(x => x.disabled = true); host.hidden = false;
    import('./viewer.js?v=studio-3').then(m => m.mountViewer(host, b.dataset.previewStl + '?download=true#model.stl', '#b8c4ca', 'PLA')).catch(() => { if (host.isConnected) host.innerHTML = '<p role="alert">3D preview unavailable. Download the file to inspect it.</p>'; });
  });
}

// Loaded after the workspaces: draw the page again now that these routes exist.
render();
