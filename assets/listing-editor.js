/* Product listing editor: details → CAD model → materials & pricing → review.
   Reuses the listing, CAD, pricing and approval APIs. Prices are stored as the existing pricing rules:
   the lowest material price is the base price and each material is a basis-point factor of it. */
const LE_STEPS = ['Product information', 'CAD model', 'Materials & pricing', 'Review & submit'];
let le = null, leViewer = null, lePoll = null, leResume = 0;
const leKey = id => `ol3d-listing-${account?.id}-${id || 'new'}`;
const leCents = value => Math.round(Number(value) * 100);
const leDims = d => d?.length === 3 ? d.map(v => +(+v).toFixed(2)).join(' × ') + ' mm' : '';

// Price in cents → stored factor; the quote rounds (base × factor + 5000) // 10000, so pick the factor that reproduces it.
function leFactor(base, price) {
  const exact = f => Math.floor((base * f + 5000) / 10000) === price;
  const f = Math.round(price * 10000 / base);
  return [f, f - 1, f + 1].find(exact) ?? f;
}
const leEffective = (base, factor) => Math.floor((base * factor + 5000) / 10000);
function lePricing() {
  const entries = le.form.order.filter(m => le.form.prices[m] !== undefined).map(m => [m, leCents(le.form.prices[m])]);
  const valid = entries.filter(([, c]) => Number.isFinite(c) && c > 0);
  const base = valid.length ? Math.min(...valid.map(([, c]) => c)) : 0;
  return {base, rows:entries.map(([m, cents]) => { const factor = base && cents > 0 ? leFactor(base, cents) : 0; return {material:m, cents, factor, effective:factor ? leEffective(base, factor) : 0}; })};
}

function leFromListing(p) {
  const o = p.configurator || {}, rules = o.pricing_materials || (p.material ? {[p.material]:10000} : {});
  let dims = []; try { dims = JSON.parse(p.cad_dimensions || '[]'); } catch (e) {}
  const prices = {};
  for (const [m, f] of Object.entries(rules)) if (p.price_cents) prices[m] = (leEffective(p.price_cents, f) / 100).toFixed(2);
  return {title:p.title || '', description:p.description || '', category:p.category || '', compatibility:p.compatibility || '', featured:!!p.featured,
    listing_type:p.listing_type || (account?.role === 'admin' ? 'official' : 'community'), order:Object.keys(rules), prices,
    dims:dims.length === 3 ? dims.map(Number) : null, dimsSource:p.cad_path || p.has_cad ? 'cad' : dims.length === 3 ? 'manual' : null};
}

/* Shell returned to the router; the editor fills itself in once categories and materials load. */
function listingEditor(p={}) {
  if (!p.id && account?.role === 'admin') p = {...p, listing_type:'official'};
  le = {listing:p, id:p.id || null, step:0, dirty:false, busy:false, cad:null, photos:[], catalogue:[], categories:[], form:leFromListing(p)};
  try { const saved = JSON.parse(sessionStorage.getItem(leKey(p.id))); if (saved?.form) { le.form = saved.form; le.step = saved.step || 0; le.dirty = true; } } catch (e) {}
  if (leResume) { le.step = leResume; leResume = 0; }
  const title = p.id ? 'Edit listing' : account?.role === 'admin' ? 'New official product' : 'New listing';
  return listingPage(title, `<div class="le" id="listing-editor"><div class="ws-loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading editor…</div></div>`);
}
const leBaseBind = bindMarketplace;
bindMarketplace = function() {
  leBaseBind();
  if (!document.getElementById('listing-editor')) return;
  const current = le;
  Promise.all([api('/categories'), api('/materials')]).then(([categories, materials]) => {
    if (le !== current || !document.getElementById('listing-editor')) return;
    le.categories = categories.map(c => c.name); le.catalogue = materials;
    if (le.form.category && !le.categories.includes(le.form.category)) le.categories.push(le.form.category);
    leRender();
  }).catch(showError);
};
function lePersist() {
  le.dirty = true;
  try { sessionStorage.setItem(leKey(le.id), JSON.stringify({form:le.form, step:le.step, updated:le.listing.updated_at || ''})); } catch (e) {}
  document.querySelector('.le-dirty')?.removeAttribute('hidden');
}
function leClear() { le.dirty = false; try { sessionStorage.removeItem(leKey(le.id)); } catch (e) {} }

/* Status rules: drafts are private; pending listings are already under review; any change to an approved
   listing takes it off the marketplace until re-approved, so approved listings get no draft action. */
function leMode() {
  const p = le.listing, admin = account?.role === 'admin' && le.form.listing_type === 'official';
  if (p.status === 'approved') return {draft:false, submit:admin ? 'Publish changes' : 'Submit changes for review', notice:admin ? 'This product is published. Saving takes it off the marketplace until you publish again.' : 'This listing is published. Submitting changes takes it off the marketplace until an administrator approves them again.'};
  if (p.status === 'pending') return {draft:true, draftLabel:'Save changes', submit:null, notice:'This listing is awaiting review. Saved changes are included in the review.'};
  return {draft:true, draftLabel:'Save draft', submit:admin ? 'Publish product' : 'Submit for approval', notice:p.status === 'rejected' && p.rejection_reason ? 'Review note: ' + p.rejection_reason : ''};
}

/* Steps */
function leStepInfo() {
  const f = le.form, p = le.listing, images = p.images || [];
  const field = (label, html, required=true, hint='') => `<label class="le-field">${esc(label)}${required ? ' <span class="le-req" aria-hidden="true">*</span>' : ' <span class="eq-optional">Optional</span>'}${html}${hint ? `<small>${esc(hint)}</small>` : ''}</label>`;
  return `<section class="le-panel"><h2>Product information</h2><div class="le-grid">${field('Product name', `<input data-f="title" maxlength="160" required value="${esc(f.title)}" placeholder="e.g. 24-position microtube rack">`)}${field('Category', `<select data-f="category" required><option value="">Choose a category</option>${le.categories.map(c => `<option ${f.category === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>`)}</div>${field('Compatibility', `<input data-f="compatibility" maxlength="300" required value="${esc(f.compatibility)}" placeholder="e.g. 1.5 ml and 2 ml microtubes">`, true, 'Equipment, tubes or consumables this product fits.')}${field('Description', `<textarea data-f="description" maxlength="10000" required rows="5" placeholder="What it is for, how it is used, cleaning and care…">${esc(f.description)}</textarea>`)}${account?.role === 'admin' ? `<label class="le-check"><input type="checkbox" data-f="featured" ${f.featured ? 'checked' : ''}> Featured on homepage</label>` : ''}
  <div class="le-field">Photographs <span class="eq-optional">Optional · JPEG, PNG or WebP · up to 5, 5 MB each</span><label class="le-drop le-drop-sm"><input type="file" id="listing-files" accept="image/jpeg,image/png,image/webp" multiple><span>${icon('camera')}Add photographs</span></label><div class="le-thumbs">${images.map((i, n) => `<figure><img src="${esc(i.thumbnail_url)}" alt="Photograph ${n + 1}"><figcaption>${n ? `<button type="button" class="icon-btn" aria-label="Move photograph ${n + 1} earlier" onclick="movePhoto(${p.id},${n},-1)">←</button>` : ''}<button type="button" class="icon-btn" aria-label="Remove photograph ${n + 1}" onclick="removePhoto(${p.id},${i.id})">×</button>${n < images.length - 1 ? `<button type="button" class="icon-btn" aria-label="Move photograph ${n + 1} later" onclick="movePhoto(${p.id},${n},1)">→</button>` : ''}</figcaption></figure>`).join('')}${le.photos.map(f => `<figure class="is-new"><img src="${esc(f.url)}" alt="New photograph"><figcaption>New</figcaption></figure>`).join('')}</div></div></section>`;
}
function leStepCad() {
  const f = le.form, p = le.listing, visual = p.configurator?.visual || {}, cad = le.cad, community = f.listing_type === 'community';
  let status;
  if (cad?.state === 'checking') status = `<p class="le-status" role="status"><span class="spinner" aria-hidden="true"></span>Measuring ${esc(cad.name)}…</p>`;
  else if (cad?.state === 'error') status = `<div class="banner danger" role="alert"><span><strong>${esc(cad.name)} could not be processed.</strong> ${esc(cad.error)}</span></div>`;
  else if (cad?.state === 'ready') status = `<p class="le-status is-ok" role="status">✓ ${esc(cad.name)} · ${esc(cad.format)} · ${esc(cad.units)} · uploaded when you save</p>${cad.warnings.map(w => `<div class="banner warning"><span>${esc(w)}</span></div>`).join('')}`;
  else if (p.cad_format) status = `<p class="le-status is-ok">✓ Current model: ${esc(p.cad_format)} file · preview ${esc(visual.status === 'ready' ? 'ready' : visual.status === 'failed' ? 'failed' : 'being generated')}</p>`;
  else status = `<p class="le-status">${community ? 'A CAD model is required before submission.' : 'Optional for official products.'}</p>`;
  const hasCad = cad?.state === 'ready' || (p.cad_format && cad?.state !== 'error');
  const auto = hasCad && f.dims ? `<div class="le-dims is-auto">${['X — Width', 'Y — Depth', 'Z — Height'].map((l, i) => `<div><span>${l}</span><strong>${(+f.dims[i]).toFixed(2)} <small>mm</small></strong></div>`).join('')}</div><p class="le-note">✓ Automatically extracted from CAD (bounding box). ${(cad?.format || p.cad_format) === '3MF' ? 'Units are read from the 3MF file and converted to millimetres.' : 'STL files carry no units, so OpenLabs3D reads them as millimetres.'}</p>` : '';
  const manual = hasCad ? '' : `<fieldset class="le-dims-manual"><legend>Dimensions (mm) <span class="le-req" aria-hidden="true">*</span></legend><p class="le-note">${cad?.state === 'error' ? 'Automatic extraction failed. ' : 'No CAD model yet. '}Enter the bounding box manually.${community ? ' Upload a valid CAD model before submitting.' : ''}</p><div class="le-dims">${['X — Width', 'Y — Depth', 'Z — Height'].map((l, i) => `<label class="le-field">${l}<input type="number" inputmode="decimal" min="0.01" max="5000" step="0.01" data-dim="${i}" value="${f.dimsSource === 'manual' && f.dims ? f.dims[i] : ''}"></label>`).join('')}</div></fieldset>`;
  const canPreview = cad?.state === 'ready' && cad.file.name.toLowerCase().endsWith('.stl') || !cad && visual.status === 'ready';
  const preview = cad?.state === 'ready' && !canPreview ? '<p class="le-note">Preview is generated after saving (3MF).</p>'
    : !cad && visual.status === 'ready' ? `<img class="le-render" src="${esc(visual.image)}" alt="Generated product preview">`
    : !cad && p.cad_format && visual.status !== 'failed' ? '<p class="le-status" role="status"><span class="spinner" aria-hidden="true"></span>Generating product preview…</p>'
    : !cad && visual.status === 'failed' ? `<p class="le-note">Preview generation failed. <button type="button" class="eq-link" onclick="regenerateProductRender(${p.id},this)">Try again</button></p>` : '';
  return `<section class="le-panel"><h2>CAD model</h2><label class="le-drop"><input type="file" id="listing-cad" accept=".stl,.3mf"><span class="le-drop-main">${icon('plus')}<strong>${hasCad ? 'Replace model' : 'Upload STL or 3MF'}</strong><small>Up to 20 MB · dimensions are measured automatically</small></span></label>${status}${auto}${manual}${preview || canPreview ? `<div class="le-preview">${preview}${canPreview ? `<button type="button" class="btn-ghost btn-sm" data-le-3d>Interactive 3D preview</button><div class="le-viewer" hidden data-le-viewer><p role="status">Loading 3D model…</p></div>` : ''}</div>` : ''}</section>`;
}
function leStepMaterials() {
  const f = le.form, {base, rows} = lePricing(), groups = ['FDM', 'RESIN'];
  const chips = groups.map(t => { const items = le.catalogue.filter(m => m.technology === t); return items.length ? `<div class="le-chip-group"><p class="eq-label">${t === 'FDM' ? 'FDM / FFF filaments' : 'Resins'}</p><div class="le-chips">${items.map(m => { const on = f.order.includes(m.name); return `<button type="button" class="le-chip" aria-pressed="${on}" data-material="${esc(m.name)}">${on ? '✓ ' : ''}${esc(m.name)}</button>`; }).join('')}</div></div>` : ''; }).join('');
  const table = rows.length ? `<table class="le-prices"><thead><tr><th>Material</th><th>Unit price (€)</th><th></th></tr></thead><tbody>${rows.map(r => { const bad = !(r.cents > 0) || r.cents > 100000000, far = base && r.factor > 100000, off = r.factor && r.effective !== r.cents; return `<tr><td><strong>${esc(r.material)}</strong>${base && r.cents === base ? ' <span class="le-base">Base price</span>' : ''}</td><td><input type="number" min="0.01" max="1000000" step="0.01" inputmode="decimal" data-price="${esc(r.material)}" value="${esc(f.prices[r.material] ?? '')}" aria-label="${esc(r.material)} unit price in euros" ${bad || far ? 'aria-invalid="true"' : ''}>${bad ? '<small class="le-err">Enter a price above €0.00</small>' : far ? '<small class="le-err">Must be at most 10× the lowest price</small>' : off ? `<small>Charged as ${money(r.effective / 100)}</small>` : ''}</td><td><button type="button" class="icon-btn" data-material="${esc(r.material)}" aria-label="Remove ${esc(r.material)}">×</button></td></tr>`; }).join('')}</tbody></table>` : '<p class="le-note">Select at least one material to set prices.</p>';
  return `<section class="le-panel"><h2>Materials &amp; pricing</h2><p class="le-note">Choose every material this product can be made in. Buyers can order a material once an approved host stocks it, so your own current stock does not limit this list.</p>${chips}<p class="eq-label le-price-label">Prices per unit</p>${table}${le.listing.configurator?.discounts && Object.keys(le.listing.configurator.discounts).length ? `<p class="le-note">Existing quantity discounts are kept.</p>` : ''}</section>`;
}
function leStepReview() {
  const f = le.form, {rows} = lePricing(), p = le.listing, visual = p.configurator?.visual || {}, mode = leMode();
  const row = (k, v, step) => `<div><dt>${esc(k)}</dt><dd>${v || '<span class="le-missing">Missing</span>'}</dd><button type="button" class="eq-link" data-step="${step}">Edit</button></div>`;
  const cadText = le.cad?.state === 'ready' ? `${esc(le.cad.name)} (uploaded on save)` : p.cad_format ? `${esc(p.cad_format)} file` : '';
  return `<section class="le-panel"><h2>Review &amp; submit</h2><div class="le-review">${!le.cad && visual.status === 'ready' ? `<img class="le-render le-review-img" src="${esc(visual.thumbnail)}" alt="Product preview">` : ''}<dl class="le-summary">${row('Product name', esc(f.title), 0)}${row('Category', esc(f.category), 0)}${row('Compatibility', esc(f.compatibility), 0)}${row('Description', esc(f.description.slice(0, 160)) + (f.description.length > 160 ? '…' : ''), 0)}${row('CAD model', cadText || (f.listing_type === 'official' ? 'None (optional)' : ''), 1)}${row('Dimensions', f.dims ? esc(leDims(f.dims)) + (f.dimsSource === 'manual' ? ' · entered manually' : ' · from CAD') : '', 1)}${row('Materials & prices', rows.map(r => `${esc(r.material)} ${r.cents > 0 ? money(r.cents / 100) : '—'}`).join(' · '), 2)}</dl></div>${mode.notice ? `<div class="banner info"><span>${esc(mode.notice)}</span></div>` : ''}<p class="le-note">${mode.draft ? 'Saving a draft keeps it private. ' : ''}${f.listing_type === 'official' ? 'Publishing makes the product visible immediately.' : 'Submitting sends the listing to an administrator for review.'}</p></section>`;
}

function leRender() {
  const root = document.getElementById('listing-editor'); if (!root) return;
  leViewer?.dispose?.(); leViewer = null; clearTimeout(lePoll);
  const focus = document.activeElement?.dataset?.f || document.activeElement?.dataset?.price;
  const mode = leMode(), last = le.step === LE_STEPS.length - 1;
  const steps = LE_STEPS.map((s, i) => `<li><button type="button" class="eq-stepper-btn ${i < le.step ? 'is-done' : ''}" data-step="${i}" ${i === le.step ? 'aria-current="step"' : ''}><span class="eq-step-num">${i < le.step ? '✓' : i + 1}</span><span class="eq-step-label">${s}</span></button></li>`).join('');
  const panel = [leStepInfo, leStepCad, leStepMaterials, leStepReview][le.step]();
  root.innerHTML = `<div class="eq">${mode.notice && le.step !== 3 ? `<div class="banner ${le.listing.status === 'approved' ? 'warning' : 'info'}"><span>${esc(mode.notice)}</span></div>` : ''}<ol class="eq-stepper" aria-label="Listing steps">${steps}</ol><form id="listing-form" class="le-form" novalidate data-id="${le.id || ''}">${panel}<div class="eq-footer"><p id="listing-error" class="eq-error" role="alert"></p><div class="eq-footer-actions"><button type="button" class="btn-ghost" data-le-back ${le.step === 0 ? 'disabled' : ''}>Back</button><span class="eq-spacer"></span><span class="eq-dirty le-dirty" ${le.dirty ? '' : 'hidden'}>Unsaved changes</span>${mode.draft ? `<button type="button" class="secondary" data-le-save>${mode.draftLabel}</button>` : ''}${last ? (mode.submit ? `<button type="button" class="primary" data-le-submit>${mode.submit}</button>` : '') : '<button type="button" class="primary" data-le-next>Next</button>'}</div></div></form></div>`;
  leBind();
  if (focus) root.querySelector(`[data-f="${CSS.escape(focus)}"],[data-price="${CSS.escape(focus)}"]`)?.focus();
  // Keep checking while the server renders the preview of a saved model.
  const visual = le.listing.configurator?.visual;
  if (le.step === 1 && le.id && !le.cad && le.listing.cad_format && visual?.status === 'pending') lePoll = setTimeout(async () => { try { const p = await api('/listings/' + le.id); if (le?.id === p.id && document.getElementById('listing-editor')) { le.listing = p; leRender(); } } catch (e) {} }, 4000);
}
function leValidate(step) {
  const f = le.form;
  if (step === 0) {
    const missing = [['title', 'product name'], ['category', 'category'], ['compatibility', 'compatibility'], ['description', 'description']].filter(([k]) => !String(f[k]).trim()).map(([, l]) => l);
    if (missing.length) return 'Complete the ' + missing.join(', ') + '.';
  }
  if (step === 1) {
    if (le.cad?.state === 'checking') return 'Wait until the CAD model has been measured.';
    const hasCad = le.cad?.state === 'ready' || (le.listing.cad_format && le.cad?.state !== 'error');
    if (f.listing_type === 'community' && !hasCad) return 'Upload a valid STL or 3MF model.';
    if (!f.dims || f.dims.some(v => !(Number.isFinite(v) && v > 0 && v <= 5000))) return 'Enter X, Y and Z as positive numbers up to 5000 mm.';
  }
  if (step === 2) {
    const {base, rows} = lePricing();
    if (!rows.length) return 'Select at least one material.';
    if (rows.some(r => !(r.cents > 0) || r.cents > 100000000)) return 'Enter a unit price above €0.00 for every selected material.';
    if (rows.some(r => r.factor > 100000)) return 'Material prices can be at most 10× the lowest price.';
    if (!base) return 'Enter material prices.';
  }
  return '';
}
function leGo(target) {
  for (let s = le.step; s < target; s++) { const message = leValidate(s); if (message) { le.step = s; leRender(); $('#listing-error').textContent = message; return; } }
  le.step = target; lePersist(); leRender(); document.querySelector('.eq-stepper [aria-current]')?.focus({preventScroll:true});
}
async function leInspect(file) {
  le.cad = {state:'checking', name:file.name, file}; leRender();
  try {
    const data = new FormData(); data.append('file', file);
    const r = await api('/cad/inspect', {method:'POST', body:data});
    le.cad = {state:'ready', name:file.name, file, format:r.format, units:r.units, warnings:r.warnings};
    le.form.dims = r.dimensions_mm; le.form.dimsSource = 'cad'; lePersist();
  } catch (e) { le.cad = {state:'error', name:file.name, file, error:e.message}; if (le.form.dimsSource === 'cad' && !le.listing.cad_format) le.form.dims = null; }
  if (document.getElementById('listing-editor')) leRender();
}
function leBind() {
  const root = document.getElementById('listing-editor'), f = le.form;
  root.querySelectorAll('[data-step]').forEach(b => b.onclick = () => { const t = +b.dataset.step; if (t <= le.step) { le.step = t; leRender(); } else leGo(t); });
  root.querySelector('[data-le-back]').onclick = () => { le.step = Math.max(0, le.step - 1); leRender(); };
  root.querySelector('[data-le-next]')?.addEventListener('click', () => leGo(le.step + 1));
  root.querySelector('[data-le-save]')?.addEventListener('click', () => leSave(false));
  root.querySelector('[data-le-submit]')?.addEventListener('click', () => leSave(true));
  root.querySelectorAll('[data-f]').forEach(el => el.addEventListener(el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input', () => { f[el.dataset.f] = el.type === 'checkbox' ? el.checked : el.value; lePersist(); }));
  root.querySelector('#listing-files')?.addEventListener('change', e => { le.photos.forEach(p => URL.revokeObjectURL(p.url)); le.photos = [...e.target.files].slice(0, 5).map(file => ({file, url:URL.createObjectURL(file)})); lePersist(); leRender(); });
  root.querySelector('#listing-cad')?.addEventListener('change', e => { const file = e.target.files[0]; if (file) leInspect(file); });
  root.querySelectorAll('[data-dim]').forEach(el => el.addEventListener('input', () => {
    const values = [...root.querySelectorAll('[data-dim]')].map(i => i.value === '' ? NaN : Number(i.value));
    f.dims = values; f.dimsSource = 'manual'; lePersist();
    el.setAttribute('aria-invalid', String(!(Number.isFinite(+el.value) && +el.value > 0 && +el.value <= 5000)));
  }));
  root.querySelectorAll('[data-material]').forEach(b => b.onclick = () => {
    const m = b.dataset.material;
    if (f.order.includes(m)) { f.order = f.order.filter(x => x !== m); delete f.prices[m]; }
    else { f.order.push(m); const {base} = lePricing(); f.prices[m] = base ? (base / 100).toFixed(2) : ''; }
    lePersist(); leRender(); root.querySelector(`.le-chip[data-material="${CSS.escape(m)}"]`)?.focus();
  });
  root.querySelectorAll('[data-price]').forEach(el => {
    el.addEventListener('input', () => { f.prices[el.dataset.price] = el.value; lePersist(); });
    el.addEventListener('change', () => leRender());
  });
  root.querySelector('[data-le-3d]')?.addEventListener('click', e => {
    const host = root.querySelector('[data-le-viewer]'); e.target.disabled = true; host.hidden = false;
    const url = le.cad?.state === 'ready' ? URL.createObjectURL(le.cad.file) + '#model.stl' : le.listing.configurator.visual.model;
    import('./viewer.js?v=studio-3').then(m => m.mountViewer(host, url, '#b8c4ca', le.form.order[0] || 'PLA')).then(v => { leViewer = v; }).catch(() => { if (host.isConnected) host.innerHTML = '<p role="alert">3D preview unavailable.</p>'; });
  });
}

/* Save writes fields, manual dimensions, pricing, photographs and the CAD model, then submits if asked. */
async function leSave(submit) {
  if (le.busy) return;
  const f = le.form, mode = leMode(), error = $('#listing-error');
  if (submit) for (let s = 0; s < 3; s++) { const message = leValidate(s); if (message) { le.step = s; leRender(); $('#listing-error').textContent = message; return; } }
  else if (le.cad?.state === 'checking') { error.textContent = 'Wait until the CAD model has been measured.'; return; }
  const official = account?.role === 'admin' && f.listing_type === 'official';
  if (submit && official && !await confirmOfficial()) return;
  le.busy = true; const buttons = [...document.querySelectorAll('#listing-form button')]; buttons.forEach(b => b.disabled = true);
  try {
    const {base, rows} = lePricing(), priced = rows.filter(r => r.cents > 0 && r.factor <= 100000);
    const payload = {title:f.title, description:f.description, category:f.category, compatibility:f.compatibility, dimensions:f.dims?.every(v => v > 0) ? leDims(f.dims) : '', material:priced[0]?.material || '', price_cents:base};
    if (account?.role === 'admin') payload.featured = !!f.featured;
    if (!le.id && account?.role === 'admin') payload.listing_type = 'official';
    const manual = f.dimsSource === 'manual' && !le.listing.cad_format && le.cad?.state !== 'ready' && f.dims?.every(v => Number.isFinite(v) && v > 0 && v <= 5000);
    if (manual) payload.cad_dimensions = f.dims;
    let p = await api(le.id ? '/listings/' + le.id : '/listings', {method:le.id ? 'PATCH' : 'POST', body:JSON.stringify(payload)});
    le.id = p.id;
    if (priced.length) p = await api(`/listings/${p.id}/pricing`, {method:'PUT', body:JSON.stringify({materials:Object.fromEntries(priced.map(r => [r.material, r.factor])), discounts:p.configurator?.discounts || {}, max_quantity:p.configurator?.max_quantity || 50})});
    if (le.photos.length) { const data = new FormData(); le.photos.forEach(x => data.append('files', x.file)); await api(`/listings/${p.id}/images`, {method:'POST', body:data}); }
    if (le.cad?.state === 'ready') { const data = new FormData(); data.append('file', le.cad.file); const r = await api(`/listings/${p.id}/cad`, {method:'POST', body:data}); p = r.listing; if (r.warning?.includes('exceed')) toast(r.warning); }
    if (submit && (official || ['draft', 'rejected'].includes(p.status))) p = await api(`/listings/${p.id}/${official ? 'publish' : 'submit'}`, {method:'POST'});
    sessionStorage.removeItem(leKey(null)); leClear();
    await refreshPublic();
    if (submit) { toast(official ? 'Product published' : p.status === 'pending' ? 'Submitted for approval' : 'Listing saved'); location.hash = account?.role === 'admin' ? 'admin/products' : 'my-listings'; }
    else { toast(mode.draftLabel === 'Save changes' ? 'Changes saved' : 'Draft saved privately. Not submitted for review.'); leResume = le.step; if (location.hash === '#edit-listing/' + p.id) render(); else location.hash = 'edit-listing/' + p.id; }
  } catch (e) { const el = $('#listing-error'); if (el) el.textContent = e.message; else showError(e); }
  finally { le.busy = false; buttons.forEach(b => { if (b.isConnected) b.disabled = false; }); }
}
// Leaving with unsaved edits: the form is kept in this browser session and restored when you return.
addEventListener('beforeunload', e => { if (le?.dirty && document.getElementById('listing-editor')) e.preventDefault(); });
