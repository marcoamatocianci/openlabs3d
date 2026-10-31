/* My Equipment: approved overview, contextual draft card and the five-step revision editor.
   Approved hosts edit one private draft revision; applicants use the same editor on #onboarding.
   The API keeps approved equipment active until an administrator approves a revision. */
const equipmentRender = render;
let printerCatalogue = [], materialCatalogue = [], approvedEquipment = [], equipmentRevision = null;
let hostDraft = null, hostStep = 0, equipmentBusy = false, editorDirty = false, editorSource = '';
// Materials & Colors tab: host-managed stock, saved immediately (no approval).
const stockUi = {printer:0, material:null, colorFor:null, busy:false};
const EDITOR_STEPS = ['Personal information', 'Printer equipment', 'Supported materials', 'Production capabilities', 'Review and submit'];
const STANDARD_COLORS = [['black', '#1b1b1b'], ['white', '#f5f5f2'], ['grey', '#8a8d91'], ['silver', '#c0c4c8'], ['natural', '#efe6d2'], ['cream', '#eeeecc'], ['beige', '#d9c7a7'], ['brown', '#6f4a2f'], ['red', '#d32f2f'], ['signal-red', '#c1121f'], ['orange', '#f57c00'], ['yellow', '#f6c700'], ['lime', '#9ccc3d'], ['green', '#2e7d32'], ['teal', '#00897b'], ['aqua-blue', '#4fb3c8'], ['sky-blue', '#64b5f6'], ['blue', '#1e5bc6'], ['navy', '#1d3557'], ['purple', '#6a3fb5'], ['pink', '#f06292'], ['magenta', '#c2185b'], ['gold', '#c9a227'], ['transparent', '#dfe9ee']];

/* Shared helpers */
const equipmentKey = () => 'host-equipment-' + account.id;
const techLabel = t => t === 'RESIN' ? 'Resin' : 'FDM';
const techLong = t => t === 'RESIN' ? 'Resin / vat photopolymerization' : 'FDM / FFF';
const printerName = p => `${p.manufacturer || ''} ${p.model || ''}`.trim() || 'Unnamed printer';
const volumeText = p => `${+p.x} × ${+p.y} × ${+p.z} mm`;
const colorTitle = name => colorName(name);
const catalogueModel = p => printerCatalogue.find(m => m.id === p.model_id);
const colorCount = p => (p.materials || []).reduce((n, m) => n + Object.keys(p.material_colors?.[m] || {}).length, 0);
const printerReady = p => p.materials?.length && p.materials.every(m => Object.keys(p.material_colors?.[m] || {}).length);
const longDate = value => { const d = parseServerDate(value); return isNaN(d) ? '—' : d.toLocaleDateString('en-GB', {day:'numeric', month:'long', year:'numeric'}); };
function newPrinter() { return {model_id:null, manufacturer:'', model:'', technology:'FDM', x:200, y:200, z:200, quantity:1, materials:[], material_colors:{}}; }
// Certified part of a printer, as the API compares it; stock (materials and colors) is never part of a revision.
const SPEC_KEYS = ['model_id', 'manufacturer', 'model', 'technology', 'x', 'y', 'z', 'quantity'];
const specOnly = p => Object.fromEntries(SPEC_KEYS.map(k => [k, p[k] ?? null]));
const canonicalPrinter = p => JSON.stringify(SPEC_KEYS.map(k => k === 'model_id' ? p[k] ?? null : ['x', 'y', 'z', 'quantity'].includes(k) ? +p[k] : p[k]));
// Supported materials as the API will resolve them: catalogue documentation, else capabilities an
// administrator already approved for the same printer, else nothing (never assumed).
function capabilityPreview(p) {
  const valid = materialCatalogue.filter(m => m.technology === p.technology).map(m => m.name), documented = catalogueModel(p)?.materials || [];
  if (documented.length) return {materials:valid.filter(m => documented.includes(m)), source:'catalogue'};
  const previous = approvedEquipment.find(q => q.manufacturer === p.manufacturer && q.model === p.model && q.technology === p.technology);
  return previous?.capabilities?.length ? {materials:valid.filter(m => previous.capabilities.includes(m)), source:'approved'} : {materials:[], source:'unknown'};
}
// Pairs proposed printers with approved ones: unchanged, modified (same model) or new; leftovers are removed.
function equipmentDiff(approved, proposed) {
  const left = approved.map(p => ({p, key:canonicalPrinter(p)}));
  const take = test => { const i = left.findIndex(test); return i < 0 ? null : left.splice(i, 1)[0]; };
  const status = proposed.map(p => take(a => a.key === canonicalPrinter(p)) ? 'unchanged' : null);
  proposed.forEach((p, i) => { if (!status[i]) status[i] = take(a => a.p.manufacturer === p.manufacturer && a.p.model === p.model) ? 'modified' : 'new'; });
  return {status, removed:left.map(a => a.p)};
}
function diffCounts(approved, proposal) {
  const {status, removed} = equipmentDiff(approved, proposal.printers);
  return {added:status.filter(s => s === 'new').length, modified:status.filter(s => s === 'modified').length, removed:removed.length};
}

/* Printer illustration: a neutral drawing per form factor (enclosed, open frame, resin). */
function printerKind(p) {
  if (p.technology === 'RESIN') return 'resin';
  return /open-frame/i.test(catalogueModel(p)?.limitations || '') || /(\ba1\b|neptune|mk\d|ender|giga)/i.test(printerName(p)) ? 'open' : 'enclosed';
}
const PRINTER_ART = {
  enclosed:'<rect class="a-body" x="15" y="6" width="50" height="52" rx="5"/><rect class="a-glass" x="20" y="12" width="40" height="35" rx="2"/><path class="a-rail" d="M20 18.5h40"/><rect class="a-head" x="27" y="15.5" width="11" height="6" rx="1.5"/><rect class="a-part" x="35" y="34" width="10" height="8" rx="1"/><rect class="a-bed" x="23" y="42" width="34" height="2.6" rx="1"/><circle class="a-led" cx="58" cy="52.5" r="1.6"/>',
  open:'<rect class="a-body" x="9" y="51" width="62" height="7" rx="2"/><rect class="a-body" x="15" y="9" width="4.5" height="44" rx="1.5"/><rect class="a-body" x="15" y="9" width="44" height="4.5" rx="1.5"/><rect class="a-head" x="38" y="13" width="10" height="9" rx="2"/><rect class="a-part" x="38" y="38" width="10" height="7" rx="1"/><rect class="a-bed" x="25" y="45" width="38" height="3" rx="1"/><rect class="a-glass" x="62" y="38" width="7" height="12" rx="1.5"/>',
  resin:'<rect class="a-body" x="16" y="40" width="48" height="18" rx="3"/><path class="a-hood" d="M20 40V14a4 4 0 0 1 4-4h32a4 4 0 0 1 4 4v26z"/><rect class="a-rail-solid" x="38" y="12" width="3" height="18"/><rect class="a-bed" x="28" y="21" width="23" height="3" rx="1"/><rect class="a-part" x="33" y="24" width="13" height="7" rx="1"/><rect class="a-vat" x="25" y="35" width="30" height="4" rx="1"/><rect class="a-glass" x="22" y="46" width="12" height="6" rx="1"/>'
};
const printerArt = (p, size='') => `<span class="eq-art ${size}" data-kind="${printerKind(p)}" aria-hidden="true"><svg viewBox="0 0 80 64">${PRINTER_ART[printerKind(p)]}</svg></span>`;

const colorDot = (hex, name) => `<span class="eq-dot" style="--c:${esc(hex)}" title="${esc(colorTitle(name))}"></span>`;
function materialChips(p, limit=4) {
  if (!p.materials?.length) return '<span class="eq-muted">No materials in stock</span>';
  const chips = p.materials.slice(0, limit).map(m => `<span class="eq-chip">${esc(m)}<span class="eq-dots">${Object.entries(p.material_colors?.[m] || {}).slice(0, 5).map(([n, h]) => colorDot(h, n)).join('')}</span></span>`).join('');
  return chips + (p.materials.length > limit ? `<span class="eq-chip eq-chip-more">+${p.materials.length - limit}</span>` : '');
}
// Read-only specification sheet shown in the printer popover.
function specSheet(p) {
  const model = catalogueModel(p), caps = p.capabilities || capabilityPreview(p).materials;
  const stock = (p.materials || []).length ? p.materials.map(m => { const colors = Object.entries(p.material_colors?.[m] || {}); return `<li><strong>${esc(m)}</strong><span>${colors.length ? colors.map(([n, h]) => `<span class="eq-color-name">${colorDot(h, n)}${esc(colorTitle(n))}</span>`).join('') : '<span class="eq-muted">No colors</span>'}</span></li>`; }).join('') : '<li class="eq-muted">Nothing in stock</li>';
  const capabilities = [`${p.quantity} identical unit${p.quantity === 1 ? '' : 's'}`, model?.limitations || (model ? '' : 'User-provided specifications — not verified')].filter(Boolean);
  return `<p class="eq-pop-title">${esc(printerName(p))}</p><dl class="eq-spec"><div><dt>Technology</dt><dd>${techLong(p.technology)}</dd></div><div><dt>Build volume</dt><dd>${volumeText(p)} <small>X × Y × Z</small></dd></div></dl><p class="eq-label">Approved materials</p><p class="eq-caps">${caps.length ? caps.map(m => `<span class="eq-cap">${esc(m)}</span>`).join('') : '<span class="eq-muted">Not documented for this model</span>'}</p>${p.id ? `<p class="eq-label">In stock now</p><ul class="eq-spec-materials">${stock}</ul>` : ''}<p class="eq-label">Production capabilities</p><ul class="eq-spec-notes">${capabilities.map(c => `<li>${esc(c)}</li>`).join('')}</ul>`;
}
/* Shared compact printer card. Hovering or focusing the image reveals the specification popover;
   click or tap pins it open for touch devices. */
function printerCard(p, id, {badge='', actions='', meta=true}={}) {
  return `<article class="eq-card" data-card="${id}"><div class="eq-card-main" data-spec-host><button type="button" class="eq-art-btn" data-spec-toggle aria-expanded="false" aria-controls="spec-${id}" aria-label="Specifications for ${esc(printerName(p))}">${printerArt(p)}</button><div class="eq-card-body"><h3 class="eq-card-title">${esc(printerName(p))}${p.quantity > 1 ? ` <span class="eq-qty">× ${p.quantity}</span>` : ''}</h3><p class="eq-card-meta"><span class="eq-tech">${techLabel(p.technology)}</span>${meta ? `<span>${volumeText(p)}</span>` : ''}</p>${badge}</div><div class="eq-pop" id="spec-${id}" role="region" aria-label="Specifications for ${esc(printerName(p))}">${specSheet(p)}</div></div>${p.capabilities ? `<p class="eq-card-caps"><span>Approved</span>${p.capabilities.length ? esc(p.capabilities.join(' · ')) : 'Not documented'}</p>` : ''}${p.id ? `<div class="eq-card-materials">${materialChips(p)}</div>` : ''}${actions ? `<div class="eq-card-actions">${actions}</div>` : ''}</article>`;
}

/* Popover and outside-click behaviour, registered once for every equipment page. */
function closeSpecPopovers(except) { document.querySelectorAll('[data-spec-host][data-open]').forEach(h => { if (h !== except) { h.removeAttribute('data-open'); h.querySelector('[data-spec-toggle]').setAttribute('aria-expanded', 'false'); } }); }
document.addEventListener('click', e => {
  const toggle = e.target.closest('[data-spec-toggle]');
  if (toggle) { const host = toggle.closest('[data-spec-host]'), open = !host.hasAttribute('data-open'); closeSpecPopovers(host); host.toggleAttribute('data-open', open); toggle.setAttribute('aria-expanded', open); return; }
  if (!e.target.closest('.eq-pop')) closeSpecPopovers();
  if (stockUi.colorFor && !e.target.closest('.eq-colorpop,[data-add-color]') && document.querySelector('.eq-colorpop')) { stockUi.colorFor = null; renderStock(); }
});
document.addEventListener('focusin', e => {
  const toggle = e.target.closest?.('[data-spec-toggle]');
  if (toggle && toggle.matches(':focus-visible')) { const host = toggle.closest('[data-spec-host]'); closeSpecPopovers(host); host.setAttribute('data-open', ''); toggle.setAttribute('aria-expanded', 'true'); }
  else if (!e.target.closest?.('[data-spec-host]')) closeSpecPopovers();
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const open = document.querySelector('[data-spec-host][data-open]');
  if (open) { closeSpecPopovers(); open.querySelector('[data-spec-toggle]').focus(); return; }
  if (stockUi.colorFor && document.querySelector('.eq-colorpop')) { const key = stockUi.colorFor; stockUi.colorFor = null; renderStock(); document.querySelector(`[data-add-color="${CSS.escape(key)}"]`)?.focus(); }
});
// Leaving the editor with unsaved changes asks first; saved drafts and approved equipment are never touched.
document.addEventListener('click', e => {
  const link = e.target.closest('a[href^="#"]');
  if (!link || !editorDirty || !document.getElementById('equipment-form') || link.getAttribute('href').startsWith('#my-printers/edit')) return;
  e.preventDefault(); leaveEditor(link.getAttribute('href').slice(1));
}, true);
addEventListener('beforeunload', e => { if (editorDirty && document.getElementById('equipment-form')) e.preventDefault(); });

/* Main page: two tabs. Printers holds certified equipment and the revision workflow;
   Materials & Colors holds host-managed stock, saved immediately without approval. */
async function equipmentOverview(route='my-printers') {
  const [printers, revision, catalogue, materials] = await Promise.all([api('/host/equipment'), api('/host/equipment-revision'), printerCatalogue.length ? printerCatalogue : api('/printer-catalogue'), materialCatalogue.length ? materialCatalogue : api('/materials')]);
  printerCatalogue = catalogue; materialCatalogue = materials; approvedEquipment = printers; equipmentRevision = revision;
  const tab = route === 'my-printers/materials' ? 'materials' : 'printers';
  const tabs = `<nav class="eq-tabs" aria-label="My equipment sections">${[['printers', 'my-printers', 'Printers'], ['materials', 'my-printers/materials', 'Materials & Colors']].map(([key, href, label]) => `<a class="eq-tab" href="#${href}" ${tab === key ? 'aria-current="page"' : ''}>${label}</a>`).join('')}</nav>`;
  if (tab === 'materials') {
    stockUi.printer = Math.min(stockUi.printer, Math.max(0, printers.length - 1)); stockUi.material = null; stockUi.colorFor = null;
    return {title:'My equipment', body:`<div class="eq">${tabs}<p class="muted ws-intro">Choose the materials and colors you currently stock. Changes are live for buyers and printing jobs immediately — no approval needed. Only materials your approved printers support can be selected.</p><div id="eq-stock"></div></div>`, bind:renderStock};
  }
  const units = printers.reduce((n, p) => n + p.quantity, 0), status = revision?.status;
  const approved = printers.length ? `<div class="eq-grid">${printers.map((p, i) => printerCard(p, 'approved-' + i, {badge:statusBadge('approved', 'Approved')})).join('')}</div>` : `<div class="eq-empty">${emptyState('No approved equipment', 'Register the printers you produce with. An administrator reviews them before they become active.')}</div>`;
  let context = '', locked = '';
  if (status === 'draft') {
    const c = diffCounts(printers, revision.proposal), changes = [[c.added, 'added'], [c.modified, 'modified'], [c.removed, 'removed']].filter(([n]) => n).map(([n, l]) => `${n} ${l}`).join(' · ') || 'No printer changes yet';
    context = `<section class="eq-section" aria-labelledby="eq-draft-title"><header class="eq-section-head"><h2 id="eq-draft-title">Equipment draft</h2></header><article class="eq-draft" data-continue-draft><span class="eq-draft-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/></svg></span><div class="eq-draft-body"><h3>Equipment update</h3><p class="eq-draft-meta">${statusBadge('neutral', 'Draft')}<span>Last modified ${esc(longDate(revision.updated_at))}</span></p><p class="eq-muted">${esc(changes)} · ${revision.proposal.printers.length} printer${revision.proposal.printers.length === 1 ? '' : 's'} proposed. Private until you submit it for approval.</p></div><div class="eq-draft-actions"><a class="btn btn-sm" href="#my-printers/edit" data-open-editor>Continue editing</a><button type="button" class="btn-ghost btn-sm" data-delete-draft>Delete draft</button></div></article></section>`;
    locked = 'An equipment draft already exists. Continue editing or delete it before starting a new update.';
  } else if (status === 'pending') {
    context = `<section class="eq-section" aria-labelledby="eq-pending-title"><header class="eq-section-head"><h2 id="eq-pending-title">Equipment update</h2></header><article class="eq-draft is-pending"><span class="eq-draft-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg></span><div class="eq-draft-body"><h3>Awaiting administrator review</h3><p class="eq-draft-meta">${statusBadge('pending', 'Pending approval')}<span>Submitted ${esc(longDate(revision.updated_at))}</span></p><details class="eq-proposed"><summary>View proposed equipment</summary><div class="eq-grid">${revision.proposal.printers.map((p, i) => printerCard(p, 'proposed-' + i)).join('') || '<p class="eq-muted">No printers proposed.</p>'}</div></details></div></article></section>`;
    locked = 'An equipment update is awaiting review. Your approved equipment stays active meanwhile.';
  } else if (status === 'rejected') {
    context = `<div class="banner danger eq-banner" role="status"><span><strong>Your last equipment update was not approved.</strong> ${esc(revision.rejection_reason)}</span><a class="btn-ghost btn-sm" href="#my-printers/edit?from=rejected" data-open-editor>Revise and resubmit</a></div>`;
  }
  const body = `${tabs}<p class="muted ws-intro">Approved printers and their supported materials are certified by an administrator. Stock is managed in <a class="textlink" href="#my-printers/materials">Materials &amp; Colors</a>.</p><section class="eq-section" aria-labelledby="eq-approved-title"><header class="eq-section-head"><h2 id="eq-approved-title">Approved equipment</h2>${printers.length ? `<span class="eq-count">${printers.length} printer${printers.length === 1 ? '' : 's'} · ${units} unit${units === 1 ? '' : 's'}</span>` : ''}</header>${approved}</section>${context}<div class="eq-modify"><button type="button" class="btn" data-modify ${locked ? 'disabled aria-describedby="eq-modify-help"' : ''}>${icon('plus')}Modify equipment</button>${locked ? `<p id="eq-modify-help" class="eq-muted">${esc(locked)}</p>` : '<p class="eq-muted">For printer specifications or new printers. Changes stay private until you submit them.</p>'}</div>`;
  const bind = () => {
    const openEditor = href => { try { sessionStorage.removeItem(equipmentKey()); } catch (e) {} hostStep = 0; location.hash = href; };
    $('[data-modify]')?.addEventListener('click', () => openEditor('my-printers/edit'));
    document.querySelectorAll('[data-open-editor]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); openEditor(a.getAttribute('href').slice(1)); }));
    $('[data-continue-draft]')?.addEventListener('click', e => { if (!e.target.closest('a,button')) openEditor('my-printers/edit'); });
    $('[data-delete-draft]')?.addEventListener('click', deleteDraftDialog);
  };
  return {title:'My equipment', body:`<div class="eq">${body}</div>`, bind};
}

/* Materials & Colors: stock editor. Every change is saved to the API at once; on failure the
   last saved state is shown again. Unsupported materials are listed but cannot be selected. */
function stockMaterialRow(p, n, m) {
  const supported = (p.capabilities || []).includes(m), on = supported && p.materials.includes(m), key = n + '|' + m, open = on && stockUi.material === key, colors = Object.entries(p.material_colors?.[m] || {});
  const summary = !supported ? '<span class="eq-mat-count">Not approved for this printer</span>' : on ? (colors.length ? `<span class="eq-dots">${colors.slice(0, 6).map(([c, h]) => colorDot(h, c)).join('')}</span><span class="eq-mat-count">${colors.length} color${colors.length === 1 ? '' : 's'}</span>` : '<span class="eq-mat-count is-warning">Add a color</span>') : '';
  const panel = open ? `<div class="eq-mat-colors"><p class="eq-label">${esc(m)} — available colors</p><div class="eq-swatches">${colors.map(([c, h]) => `<span class="eq-swatch-chip">${colorDot(h, c)}${esc(colorTitle(c))}<button type="button" data-remove-color="${esc(c)}" data-index="${n}" data-material="${esc(m)}" aria-label="Remove ${esc(colorTitle(c))} from ${esc(m)}">×</button></span>`).join('')}<span class="eq-add-wrap"><button type="button" class="eq-add-color" data-add-color="${esc(key)}" data-k="add-${esc(key)}" aria-expanded="${stockUi.colorFor === key}">${icon('plus')}Add color</button>${stockUi.colorFor === key ? colorPopover(p, m) : ''}</span></div>${colors.length ? '' : '<p class="eq-muted">Buyers can only order this material in colors you list here.</p>'}</div>` : '';
  return `<li class="eq-mat ${on ? 'is-on' : ''} ${open ? 'is-open' : ''} ${supported ? '' : 'is-unsupported'}"><div class="eq-mat-row"><label class="eq-check"><input type="checkbox" data-toggle-material="${esc(m)}" data-index="${n}" data-k="mat-${esc(key)}" ${on ? 'checked' : ''} ${supported ? '' : 'disabled'}><span>${esc(m)}</span></label>${summary}${on ? `<button type="button" class="eq-mat-toggle" data-open-material="${esc(key)}" data-k="open-${esc(key)}" aria-expanded="${open}" aria-label="${open ? 'Hide' : 'Show'} ${esc(m)} colors">${icon('chevron')}</button>` : ''}</div>${panel}</li>`;
}
function colorPopover(p, material) {
  const current = p.material_colors[material] || {}, usedHex = Object.values(current).map(h => h.toLowerCase());
  const options = STANDARD_COLORS.map(([name, hex]) => { const used = name in current || usedHex.includes(hex); return `<button type="button" role="option" class="eq-color-option" data-pick="${name}" data-hex="${hex}" data-search="${esc(colorTitle(name).toLowerCase())}" aria-selected="false" ${used ? 'disabled' : ''}>${colorDot(hex, name)}<span>${esc(colorTitle(name))}</span>${used ? '<small>Added</small>' : ''}</button>`; }).join('');
  return `<div class="eq-colorpop" role="dialog" aria-label="Add color to ${esc(material)}" data-mode="standard"><div class="eq-colorpop-standard"><label class="eq-field eq-field-compact"><span class="sr-only">Search standard colors</span><input type="search" data-color-search placeholder="Search standard colors" autocomplete="off"></label><div class="eq-color-options" role="listbox" aria-label="Standard filament colors">${options}<p class="eq-muted eq-no-match" hidden>No matching colors</p></div><button type="button" class="eq-link" data-custom-mode>${icon('plus')}Add custom color</button></div><div class="eq-colorpop-custom"><button type="button" class="eq-link" data-standard-mode>← Standard colors</button><label class="eq-field eq-field-compact">Color name<input data-custom-name maxlength="40" placeholder="e.g. Ocean teal" autocomplete="off"></label><div class="eq-custom-row"><label class="eq-field eq-field-compact">Swatch<input type="color" data-custom-hex value="#457b9d"></label><span class="eq-custom-preview"><span class="eq-dot eq-dot-lg" style="--c:#457b9d"></span><span data-custom-label>New color</span></span></div></div><p class="eq-pop-error" role="alert"></p><div class="eq-colorpop-actions"><button type="button" class="btn-ghost btn-sm" data-color-cancel>Cancel</button><button type="button" class="btn btn-sm" data-color-confirm>Confirm</button></div></div>`;
}
function renderStock() {
  const root = document.getElementById('eq-stock'); if (!root) return;
  const focusKey = document.activeElement?.dataset?.k, printers = approvedEquipment;
  if (!printers.length) { root.innerHTML = `<div class="eq-empty">${emptyState('No approved printers', 'Materials and colors can be stocked once a printer is approved.', '<a class="btn btn-sm" href="#my-printers">Go to Printers</a>')}</div>`; return; }
  root.innerHTML = `<div class="eq-acc" aria-busy="${stockUi.busy}">${printers.map((p, n) => {
    const open = stockUi.printer === n, all = materialCatalogue.filter(m => m.technology === p.technology).map(m => m.name);
    const ordered = [...all.filter(m => p.capabilities.includes(m)), ...all.filter(m => !p.capabilities.includes(m))];
    const panel = open ? `<div class="eq-acc-panel" id="stock-${n}"><p class="eq-label">Available materials</p>${p.capabilities.length ? '' : '<div class="banner warning"><span>Supported materials are not documented for this printer model, so no material can be stocked yet. Contact an administrator to verify its specifications.</span></div>'}<ul class="eq-mats">${ordered.map(m => stockMaterialRow(p, n, m)).join('')}</ul></div>` : '';
    return `<div class="eq-acc-item ${open ? 'is-open' : ''}"><button type="button" class="eq-acc-head" data-open-printer="${n}" data-k="printer-${n}" aria-expanded="${open}" aria-controls="stock-${n}">${printerArt(p, 'sm')}<span class="eq-acc-title"><strong>${esc(printerName(p))}</strong><small>${techLabel(p.technology)} · ${p.materials.length} of ${p.capabilities.length} material${p.capabilities.length === 1 ? '' : 's'} in stock · ${colorCount(p)} color${colorCount(p) === 1 ? '' : 's'}</small></span>${printerReady(p) ? statusBadge('approved', 'Offered') : statusBadge('neutral', p.materials.length ? 'Needs colors' : 'Not offered')}${icon('chevron')}</button>${panel}</div>`;
  }).join('')}</div><p class="eq-muted eq-stock-note" role="status" id="eq-stock-status">${stockUi.busy ? 'Saving…' : 'Changes save automatically and apply to new orders. Accepted printing jobs keep their original specifications.'}</p>`;
  bindStock();
  if (focusKey) document.querySelector(`[data-k="${CSS.escape(focusKey)}"]`)?.focus({preventScroll:true});
}
async function saveStock(n, change, message) {
  if (stockUi.busy) return;
  const printer = approvedEquipment[n], next = structuredClone({materials:printer.materials, material_colors:printer.material_colors});
  change(next);
  next.material_colors = Object.fromEntries(Object.entries(next.material_colors).filter(([m]) => next.materials.includes(m)));
  stockUi.busy = true; renderStock();
  try { approvedEquipment[n] = await api(`/host/printers/${printer.id}/availability`, {method:'PUT', body:JSON.stringify(next)}); if (message) toast(message); }
  catch (e) { toast(e.message); }
  finally { stockUi.busy = false; renderStock(); }
}
function bindStock() {
  document.querySelectorAll('#eq-stock [data-open-printer]').forEach(b => b.onclick = () => { const n = +b.dataset.openPrinter; stockUi.printer = stockUi.printer === n ? -1 : n; stockUi.material = null; stockUi.colorFor = null; renderStock(); });
  document.querySelectorAll('#eq-stock [data-toggle-material]').forEach(el => el.onchange = () => {
    const n = +el.dataset.index, m = el.dataset.toggleMaterial, key = n + '|' + m;
    if (el.checked) stockUi.material = key; else if (stockUi.material === key) stockUi.material = null;
    stockUi.colorFor = null;
    saveStock(n, s => { s.materials = el.checked ? [...new Set([...s.materials, m])] : s.materials.filter(x => x !== m); if (el.checked) s.material_colors[m] ||= {}; else delete s.material_colors[m]; }, el.checked ? `${m} is now in stock` : `${m} removed from stock`);
  });
  document.querySelectorAll('#eq-stock [data-open-material]').forEach(b => b.onclick = () => { const k = b.dataset.openMaterial; stockUi.material = stockUi.material === k ? null : k; stockUi.colorFor = null; renderStock(); });
  document.querySelectorAll('#eq-stock [data-remove-color]').forEach(b => b.onclick = () => {
    const n = +b.dataset.index, m = b.dataset.material, c = b.dataset.removeColor;
    saveStock(n, s => { delete s.material_colors[m][c]; }, `${colorTitle(c)} removed from ${m}`).then(() => document.querySelector(`[data-add-color="${CSS.escape(n + '|' + m)}"]`)?.focus());
  });
  document.querySelectorAll('#eq-stock [data-add-color]').forEach(b => b.onclick = () => { const k = b.dataset.addColor; stockUi.colorFor = stockUi.colorFor === k ? null : k; renderStock(); document.querySelector('.eq-colorpop [data-color-search]')?.focus(); });
  bindColorPopover();
}
function deleteDraftDialog() {
  const dialog = $('#modal'); dialog.className = '';
  dialog.innerHTML = `<form class="modal-form" method="dialog"><h2>Delete equipment draft?</h2><p>Your saved, unsubmitted changes will be removed. Approved equipment stays active and unchanged.</p><p class="form-error" role="alert"></p><div class="modal-actions"><button type="button" class="secondary" data-close-modal>Cancel</button><button type="button" class="danger" data-confirm>Delete draft</button></div></form>`;
  dialog.showModal();
  dialog.querySelector('[data-confirm]').onclick = async e => {
    e.target.disabled = true;
    try { await api('/host/equipment-revision', {method:'DELETE'}); try { sessionStorage.removeItem(equipmentKey()); } catch (err) {} dialog.close(); toast('Draft deleted. Approved equipment is unchanged.'); render(); }
    catch (err) { dialog.querySelector('.form-error').textContent = err.message; e.target.disabled = false; }
  };
}

/* Editor shell and persistence */
function persistEditor() {
  editorDirty = true;
  try { sessionStorage.setItem(equipmentKey(), JSON.stringify({source:editorSource, step:hostStep, data:hostDraft})); } catch (e) {}
}
function clearEditorSession() { editorDirty = false; try { sessionStorage.removeItem(equipmentKey()); } catch (e) {} }
function leaveEditor(target='my-printers') {
  if (!editorDirty) { location.hash = target; return; }
  const dialog = $('#modal'); dialog.className = '';
  dialog.innerHTML = `<form class="modal-form" method="dialog"><h2>Leave without saving?</h2><p>You have unsaved equipment changes. Save them as a private draft, or discard them. Approved equipment is never affected.</p><div class="modal-actions eq-leave-actions"><button type="button" class="secondary" data-close-modal>Keep editing</button><button type="button" class="secondary" data-discard>Discard changes</button><button type="button" class="primary" data-save>Save draft</button></div></form>`;
  dialog.showModal();
  dialog.querySelector('[data-discard]').onclick = () => { dialog.close(); clearEditorSession(); location.hash = target; };
  dialog.querySelector('[data-save]').onclick = () => { dialog.close(); saveEquipment(false, target); };
}
function editorShell(body) {
  if (account.role !== 'host') return layout(head('Become a printing host', 'Host application') + `<div class="eq eq-editor">${body}</div>`);
  const draft = equipmentRevision?.status === 'draft';
  return workspacePage('host', draft ? 'Edit equipment draft' : 'Modify equipment', `<div class="eq eq-editor"><div class="eq-editor-top"><button type="button" class="eq-back" data-leave>${icon('chevron')}My equipment</button><p class="eq-muted">${draft ? `Draft · last saved ${esc(longDate(equipmentRevision.updated_at))}` : 'New update'} · Approved equipment stays active until an administrator approves your changes.</p></div>${body}</div>`);
}

/* Editor steps */
function stepPersonal() {
  const incomplete = ['first_name', 'last_name', 'phone', 'country', 'city'].some(k => !account[k]);
  return `<section class="eq-step-panel"><h2>Personal information</h2><div class="eq-contact"><div><strong>${esc(account.first_name)} ${esc(account.last_name)}</strong><span>${esc(account.email)}</span><span>${esc(account.phone)} · ${esc(account.city)}, ${esc(account.country)}</span></div><a class="btn-ghost btn-sm" href="#account-contact">Edit in My account</a></div>${incomplete ? '<div class="banner warning"><span>Your contact information is incomplete. Complete it in My account; your changes here are preserved.</span></div>' : ''}<label class="eq-field">Company or workshop <span class="eq-optional">Optional</span><input id="host-company" data-k="company" value="${esc(hostDraft.company)}" maxlength="150" autocomplete="organization"></label></section>`;
}
function stepPrinters(diff) {
  const badge = (p, n) => { const caps = capabilityPreview(p).materials.length; return caps ? statusBadge('approved', `✓ ${caps} supported material${caps === 1 ? '' : 's'}`) : statusBadge('pending', 'Materials not documented'); };
  const badges = (p, n) => badge(p, n) + (diff && diff.status[n] !== 'unchanged' ? ' ' + statusBadge('accepted', diff.status[n] === 'new' ? 'New' : 'Modified') : '');
  const cards = hostDraft.printers.map((p, n) => printerCard(p, 'draft-' + n, {badge:`<p class="eq-badges">${badges(p, n)}</p>`, actions:`<button type="button" class="eq-link" data-spec-open="${n}">Specifications</button><button type="button" class="btn-ghost btn-sm" data-edit-printer="${n}" data-k="edit-${n}">Edit</button>`})).join('');
  const removed = diff?.removed.length ? `<p class="eq-muted eq-removed">Removed from approved equipment: ${diff.removed.map(p => `<s>${esc(printerName(p))}</s>`).join(', ')}</p>` : '';
  return `<section class="eq-step-panel"><header class="eq-step-head"><div><h2>Printer equipment</h2><p class="eq-muted">${hostDraft.printers.length} printer model${hostDraft.printers.length === 1 ? '' : 's'} · hover or focus an image for specifications.</p></div></header><div class="eq-grid">${cards}<button type="button" class="eq-add-card" data-add-printer data-k="add-printer">${icon('plus')}<span>Add printer</span><small>Choose from the printer catalogue or enter your own</small></button></div>${removed}</section>`;
}
// Read-only: supported materials belong to the printer definition, stock to the Materials & Colors tab.
function stepMaterials() {
  if (!hostDraft.printers.length) return `<section class="eq-step-panel"><h2>Supported materials</h2>${emptyState('No printers in this update', 'Add a printer in the previous step.')}</section>`;
  const rows = hostDraft.printers.map(p => {
    const {materials, source} = capabilityPreview(p);
    const note = {catalogue:'Supported by this printer model, according to the manufacturer specifications.', approved:'Not documented in the printer catalogue; keeps the materials an administrator already approved for this printer.', unknown:'Specifications incomplete: the manufacturer documentation does not list supported materials, so none are assumed. An administrator must verify them before you can stock materials for this printer.'}[source];
    return `<li class="eq-cap-row">${printerArt(p, 'sm')}<div><strong>${esc(printerName(p))}</strong><small>${techLabel(p.technology)} · ${volumeText(p)}</small>${materials.length ? `<ul class="eq-cap-list">${materials.map(m => `<li>✓ ${esc(m)}</li>`).join('')}</ul>` : ''}<p class="eq-muted ${source === 'unknown' ? 'is-warning' : ''}">${note}</p></div></li>`;
  }).join('');
  return `<section class="eq-step-panel"><header class="eq-step-head"><div><h2>Supported materials</h2><p class="eq-muted">Read-only. These come from each printer's technical specifications and are reviewed with this update. Choose the materials and colors you stock in <strong>My equipment → Materials &amp; Colors</strong>; that needs no approval.</p></div></header><ul class="eq-review eq-caps-review">${rows}</ul></section>`;
}
function stepCapabilities() {
  const units = hostDraft.printers.reduce((s, p) => s + p.quantity, 0), techs = [...new Set(hostDraft.printers.map(p => techLong(p.technology)))];
  const materials = [...new Set(hostDraft.printers.flatMap(p => p.materials))], largest = hostDraft.printers.reduce((a, p) => (!a || p.x * p.y * p.z > a.x * a.y * a.z) ? p : a, null);
  const stat = (label, value) => `<div class="eq-stat"><span>${label}</span><strong>${value}</strong></div>`;
  return `<section class="eq-step-panel"><h2>Production capabilities</h2><div class="eq-stats">${stat('Printers', units)}${stat('Technologies', esc(techs.join(', ') || '—'))}${stat('Materials', materials.length)}${stat('Largest build volume', largest ? volumeText(largest) : '—')}</div><label class="eq-field">Estimated available hours per week <span class="eq-optional">Optional</span><input id="weekly-hours" data-k="hours" type="number" min="1" max="168" inputmode="numeric" value="${hostDraft.weekly_hours || ''}"></label><p class="eq-muted">Printer count does not determine production throughput.</p></section>`;
}
function stepReview(diff) {
  const rows = hostDraft.printers.map((p, n) => `<li class="eq-review-row">${printerArt(p, 'sm')}<div><strong>${esc(printerName(p))}${p.quantity > 1 ? ` × ${p.quantity}` : ''}</strong><small>${techLabel(p.technology)} · ${volumeText(p)}</small><small>Supported: ${esc(capabilityPreview(p).materials.join(', ') || 'not documented')}</small></div>${diff ? statusBadge(diff.status[n] === 'unchanged' ? 'neutral' : 'accepted', {unchanged:'Unchanged', modified:'Modified', new:'New'}[diff.status[n]]) : ''}</li>`).join('');
  const removed = (diff?.removed || []).map(p => `<li class="eq-review-row is-removed">${printerArt(p, 'sm')}<div><strong>${esc(printerName(p))}</strong><small>${techLabel(p.technology)} · ${volumeText(p)}</small></div>${statusBadge('rejected', 'Removed')}</li>`).join('');
  const unchanged = diff && !diff.removed.length && diff.status.every(s => s === 'unchanged') && hostDraft.company === (approvedPayloadMeta.company || '') && (hostDraft.weekly_hours || null) === (approvedPayloadMeta.weekly_hours || null);
  return `<section class="eq-step-panel"><h2>Review and submit</h2><ul class="eq-review">${rows || '<li class="eq-muted">No printers proposed.</li>'}${removed}</ul>${unchanged ? '<div class="banner info"><span>This update has no changes compared with your approved equipment.</span></div>' : ''}<p class="eq-muted">${account.role === 'host' ? 'Submitting sends this revision to an administrator. Your approved equipment remains active and unchanged until it is approved.' : 'Applications require administrator approval.'}</p></section>`;
}
let approvedPayloadMeta = {};

function equipmentView() {
  const focusKey = document.activeElement?.dataset?.k;
  const diff = account.role === 'host' ? equipmentDiff(approvedEquipment, hostDraft.printers) : null;
  const steps = EDITOR_STEPS.map((s, i) => `<li><button type="button" class="eq-stepper-btn ${i < hostStep ? 'is-done' : ''}" data-step="${i}" ${i === hostStep ? 'aria-current="step"' : ''}><span class="eq-step-num">${i < hostStep ? '✓' : i + 1}</span><span class="eq-step-label">${s}</span></button></li>`).join('');
  const panels = [stepPersonal, () => stepPrinters(diff), stepMaterials, stepCapabilities, () => stepReview(diff)];
  const last = hostStep === EDITOR_STEPS.length - 1;
  $('#app').innerHTML = editorShell(`<ol class="eq-stepper" aria-label="Equipment update steps">${steps}</ol><form id="equipment-form" novalidate>${panels[hostStep]()}<div class="eq-footer"><p id="equipment-error" class="eq-error" role="alert"></p><div class="eq-footer-actions"><button type="button" class="btn-ghost" id="previous-step" ${hostStep === 0 ? 'disabled' : ''}>Back</button><span class="eq-spacer"></span><span class="eq-dirty" ${editorDirty ? '' : 'hidden'}>Unsaved changes</span><button type="button" class="secondary" id="save-draft" data-k="save">Save draft</button>${last ? '<button type="button" class="primary" id="submit-equipment" data-k="submit">Submit for approval</button>' : `<button type="button" class="primary" id="next-step" data-k="next">${hostStep === 2 ? 'Confirm &amp; continue' : 'Next'}</button>`}</div></div></form>`);
  bindEditor();
  if (focusKey) document.querySelector(`[data-k="${CSS.escape(focusKey)}"]`)?.focus({preventScroll:true});
}
function validateStep(step) {
  let message = '', fix = null;
  if (step === 0 && ['first_name', 'last_name', 'phone', 'country', 'city'].some(k => !account[k])) message = 'Complete your first name, last name, phone, country and city in My account.';
  if (step === 1) {
    const bad = hostDraft.printers.findIndex(p => !p.manufacturer.trim() || !p.model.trim());
    if (!hostDraft.printers.length && account.role !== 'host') message = 'Add at least one printer.';
    else if (bad >= 0) message = `Printer ${bad + 1}: enter the manufacturer and model.`;
  }
  if (step === 3) { const h = hostDraft.weekly_hours; if (h != null && !(Number.isInteger(h) && h >= 1 && h <= 168)) message = 'Weekly hours must be a whole number between 1 and 168.'; }
  return {ok:!message, message, fix};
}
function showStepError(step, result) {
  hostStep = step; result.fix?.(); equipmentView();
  $('#equipment-error').textContent = result.message;
}
function goToStep(target) {
  for (let s = hostStep; s < target; s++) { const r = validateStep(s); if (!r.ok) { showStepError(s, r); return; } }
  hostStep = target; persistStep(); equipmentView();
  $('#app .ws-main, #app')?.scrollIntoView?.({block:'start'});
  document.querySelector('.eq-stepper [aria-current]')?.focus({preventScroll:true});
}
function persistStep() { if (editorDirty) persistEditor(); }
async function saveEquipment(submit, target='my-printers') {
  if (equipmentBusy) return;
  if (submit) for (let s = 0; s < 4; s++) { const r = validateStep(s); if (!r.ok) { showStepError(s, r); return; } }
  equipmentBusy = true; const form = $('#equipment-form'); form?.setAttribute('aria-busy', 'true');
  const buttons = form ? [...form.querySelectorAll('button')].map(b => [b, b.disabled]) : []; buttons.forEach(([b]) => b.disabled = true);
  try {
    const r = await accountAction('/host/equipment-application', {company:hostDraft.company, weekly_hours:hostDraft.weekly_hours, printers:hostDraft.printers.map(specOnly), submit}, 'PUT');
    const wasHost = account.role === 'host';
    clearEditorSession();
    account = (await api('/auth/me')).user; updateAccount();
    toast(submit ? 'Submitted for approval. Approved equipment stays active until it is reviewed.' : 'Draft saved privately. Approved equipment is unchanged.');
    if (wasHost) { equipmentRevision = r; hostStep = 0; location.hash = target; }
    else if (submit) render();
    else equipmentView();
  } catch (e) { const error = $('#equipment-error'); if (error) error.textContent = e.message; else toast(e.message); }
  finally { equipmentBusy = false; form?.removeAttribute('aria-busy'); buttons.forEach(([b, d]) => { if (b.isConnected) b.disabled = d; }); }
}

/* Printer drawer: edits a working copy so Cancel never alters the draft. */
function printerDrawer(index) {
  const isNew = index == null, original = isNew ? newPrinter() : hostDraft.printers[index];
  let work = structuredClone(original), confirmRemove = false;
  const dialog = $('#modal'), trigger = document.activeElement;
  const draw = () => {
    const known = catalogueModel(work), manufacturers = [...new Set(printerCatalogue.map(m => m.manufacturer))], focus = dialog.querySelector(':focus')?.dataset.d;
    const dropped = false;
    const fields = known ? `<label class="eq-field">Model<select data-d="model_id">${printerCatalogue.filter(m => m.manufacturer === known.manufacturer).map(m => `<option value="${m.id}" ${m.id === work.model_id ? 'selected' : ''}>${esc(m.model)}</option>`).join('')}</select></label><div class="eq-drawer-spec">${printerArt(work)}<div><strong>${techLong(known.technology)}</strong><span>${volumeText(known)}</span><span class="eq-muted">${known.materials.length ? 'Documented: ' + esc(known.materials.join(', ')) : 'Material families not individually verified'}</span></div></div><p class="eq-muted eq-small">${esc(known.limitations)} ${known.source?.startsWith('http') ? `<a class="textlink" href="${esc(known.source)}" target="_blank" rel="noopener">Specification source ↗</a>` : ''}</p>`
      : `<p class="eq-muted eq-small">User-provided specifications are reviewed by an administrator.</p><div class="eq-field-grid">${['manufacturer', 'model'].map(k => `<label class="eq-field">${k === 'model' ? 'Model' : 'Manufacturer name'}<input data-d="${k}" value="${esc(work[k])}" maxlength="100" required></label>`).join('')}<label class="eq-field">Technology<select data-d="technology"><option value="FDM" ${work.technology === 'FDM' ? 'selected' : ''}>FDM / FFF</option><option value="RESIN" ${work.technology === 'RESIN' ? 'selected' : ''}>Resin / vat photopolymerization</option></select></label></div><fieldset class="eq-volume"><legend>Build volume (mm)</legend>${['x', 'y', 'z'].map(k => `<label class="eq-field">${k.toUpperCase()}<input data-d="${k}" type="number" step="0.01" min="0.01" max="5000" required value="${work[k]}"></label>`).join('')}</fieldset>`;
    const footer = confirmRemove ? `<p class="eq-remove-confirm">Remove ${esc(printerName(original))} from this update?</p><button type="button" class="btn-ghost" data-d-keep>Keep printer</button><button type="button" class="danger" data-d-remove-yes>Remove</button>`
      : `${isNew ? '' : '<button type="button" class="eq-link eq-danger-link" data-d-remove>Remove printer</button>'}<span class="eq-spacer"></span><button type="button" class="btn-ghost" data-d-cancel>Cancel</button><button type="button" class="primary" data-d-save>${isNew ? 'Add printer' : 'Save printer'}</button>`;
    dialog.innerHTML = `<form class="eq-drawer-form" novalidate><header class="eq-drawer-head"><div><p class="eq-label">${isNew ? 'New printer' : 'Edit printer'}</p><h2>${esc(isNew && !work.model ? 'Add printer' : printerName(work))}</h2></div><button type="button" class="icon-btn" data-d-cancel aria-label="Close">${icon('close')}</button></header><div class="eq-drawer-body"><label class="eq-field">Manufacturer<select data-d="brand"><option value="">Other — my printer is not listed</option>${manufacturers.map(m => `<option ${known?.manufacturer === m ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select></label>${fields}<label class="eq-field">Number of identical printers<input data-d="quantity" type="number" min="1" max="100" step="1" required value="${work.quantity}"></label>${dropped ? `<div class="banner warning"><span>Changing technology removes this printer's ${esc(original.materials.join(', '))} materials and colors from the draft.</span></div>` : ''}<p class="eq-error" role="alert"></p></div><footer class="eq-drawer-foot">${footer}</footer></form>`;
    bindDrawer();
    if (focus) dialog.querySelector(`[data-d="${focus}"]`)?.focus();
  };
  const choose = id => { const m = printerCatalogue.find(c => c.id === id); work = m ? {...work, model_id:m.id, manufacturer:m.manufacturer, model:m.model, technology:m.technology, x:m.x, y:m.y, z:m.z} : {...work, model_id:null, manufacturer:'', model:''}; draw(); };
  const bindDrawer = () => {
    const q = s => dialog.querySelector(s);
    q('[data-d="brand"]').onchange = e => choose(printerCatalogue.find(m => m.manufacturer === e.target.value)?.id);
    if (q('[data-d="model_id"]')) q('[data-d="model_id"]').onchange = e => choose(+e.target.value);
    dialog.querySelectorAll('input[data-d],select[data-d="technology"]').forEach(el => el.oninput = () => { const k = el.dataset.d; work[k] = el.type === 'number' ? Number(el.value) : el.value; if (k === 'technology') draw(); });
    dialog.querySelectorAll('[data-d-cancel]').forEach(b => b.onclick = () => dialog.close());
    if (q('[data-d-remove]')) q('[data-d-remove]').onclick = () => { confirmRemove = true; draw(); q('[data-d-keep]').focus(); };
    if (q('[data-d-keep]')) q('[data-d-keep]').onclick = () => { confirmRemove = false; draw(); };
    if (q('[data-d-remove-yes]')) q('[data-d-remove-yes]').onclick = () => { hostDraft.printers.splice(index, 1); persistEditor(); dialog.close(); equipmentView(); toast(`${printerName(original)} removed from the draft`); };
    q('[data-d-save]')?.addEventListener('click', () => {
      const invalid = [...dialog.querySelectorAll('input[data-d]')].find(el => !el.checkValidity());
      let message = invalid ? `${invalid.closest('label').firstChild.textContent.trim()}: ${invalid.validationMessage}` : '';
      if (!message && (!work.manufacturer.trim() || !work.model.trim())) message = 'Enter the manufacturer and model.';
      if (!message && !Number.isInteger(work.quantity)) message = 'Number of printers must be a whole number.';
      if (message) { q('.eq-error').textContent = message; (invalid || q('[data-d="brand"]')).focus(); return; }
      if (isNew) hostDraft.printers.push(work); else hostDraft.printers[index] = work;
      persistEditor(); dialog.close(); equipmentView();
      toast(isNew ? `${printerName(work)} added` : `${printerName(work)} updated`);
      document.querySelector(`[data-k="edit-${isNew ? hostDraft.printers.length - 1 : index}"]`)?.focus();
    });
  };
  dialog.className = 'eq-drawer'; draw(); dialog.showModal();
  dialog.addEventListener('close', () => { dialog.className = ''; if (trigger?.isConnected) trigger.focus(); }, {once:true});
  dialog.querySelector('[data-d="brand"]').focus();
}

function bindEditor() {
  const form = $('#equipment-form');
  document.querySelector('[data-leave]')?.addEventListener('click', () => leaveEditor());
  document.querySelectorAll('[data-step]').forEach(b => b.onclick = () => { const t = +b.dataset.step; if (t <= hostStep) { hostStep = t; equipmentView(); } else goToStep(t); });
  $('#previous-step').onclick = () => { hostStep = Math.max(0, hostStep - 1); persistStep(); equipmentView(); };
  $('#next-step')?.addEventListener('click', () => goToStep(hostStep + 1));
  $('#save-draft').onclick = () => saveEquipment(false);
  $('#submit-equipment')?.addEventListener('click', () => saveEquipment(true));
  form.onsubmit = e => e.preventDefault();
  const markDirty = () => { persistEditor(); document.querySelector('.eq-dirty')?.removeAttribute('hidden'); };
  $('#host-company')?.addEventListener('input', e => { hostDraft.company = e.target.value; markDirty(); });
  $('#weekly-hours')?.addEventListener('input', e => { hostDraft.weekly_hours = e.target.value ? Number(e.target.value) : null; markDirty(); });
  // Printers
  document.querySelector('[data-add-printer]')?.addEventListener('click', () => printerDrawer(null));
  document.querySelectorAll('[data-edit-printer]').forEach(b => b.onclick = () => printerDrawer(+b.dataset.editPrinter));
  document.querySelectorAll('[data-spec-open]').forEach(b => b.onclick = e => { e.stopPropagation(); b.closest('.eq-card').querySelector('[data-spec-toggle]').click(); });
}
function bindColorPopover() {
  const pop = document.querySelector('.eq-colorpop'); if (!pop) return;
  const key = stockUi.colorFor, split = key.indexOf('|'), n = +key.slice(0, split), material = key.slice(split + 1), p = approvedEquipment[n];
  const q = s => pop.querySelector(s), error = q('.eq-pop-error');
  let picked = null;
  const close = () => { stockUi.colorFor = null; renderStock(); document.querySelector(`[data-add-color="${CSS.escape(key)}"]`)?.focus(); };
  const setMode = mode => { pop.dataset.mode = mode; error.textContent = ''; (mode === 'custom' ? q('[data-custom-name]') : q('[data-color-search]')).focus(); };
  q('[data-custom-mode]').onclick = () => setMode('custom');
  q('[data-standard-mode]').onclick = () => setMode('standard');
  q('[data-color-search]').oninput = e => { const t = e.target.value.trim().toLowerCase(); let shown = 0; pop.querySelectorAll('[data-pick]').forEach(o => { o.hidden = !!t && !o.dataset.search.includes(t); shown += !o.hidden; }); q('.eq-no-match').hidden = shown > 0; };
  const options = [...pop.querySelectorAll('[data-pick]')];
  options.forEach(o => {
    o.onclick = () => { picked = o.dataset.pick; options.forEach(x => x.setAttribute('aria-selected', x === o)); error.textContent = ''; };
    o.ondblclick = () => q('[data-color-confirm]').click();
    o.onkeydown = e => { if (!['ArrowDown', 'ArrowUp'].includes(e.key)) return; e.preventDefault(); const list = options.filter(x => !x.hidden && !x.disabled), i = list.indexOf(o); list[(i + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length]?.focus(); };
  });
  const name = q('[data-custom-name]'), hex = q('[data-custom-hex]'), preview = () => { q('.eq-custom-preview .eq-dot').style.setProperty('--c', hex.value); q('[data-custom-label]').textContent = name.value.trim() || 'New color'; };
  name.oninput = preview; hex.oninput = preview;
  q('[data-color-cancel]').onclick = close;
  q('[data-color-confirm]').onclick = () => {
    const current = p.material_colors[material] || {};
    let slug, value;
    if (pop.dataset.mode === 'custom') { slug = name.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40); value = hex.value.toLowerCase(); if (!/^[a-z0-9][a-z0-9-]{0,39}$/.test(slug)) { error.textContent = 'Enter a color name using letters and numbers.'; name.focus(); return; } }
    else { if (!picked) { error.textContent = 'Choose a standard color, or add a custom color.'; return; } slug = picked; value = STANDARD_COLORS.find(([c]) => c === picked)[1]; }
    const sameHex = Object.entries(current).find(([, h]) => h.toLowerCase() === value);
    if (slug in current) { error.textContent = `${colorTitle(slug)} is already listed for ${material}.`; return; }
    if (sameHex) { error.textContent = `This shade is already listed as ${colorTitle(sameHex[0])}.`; return; }
    if (Object.keys(current).length >= 40) { error.textContent = 'A material can list at most 40 colors.'; return; }
    stockUi.colorFor = null;
    saveStock(n, s => { s.material_colors[material] = {...s.material_colors[material], [slug]:value}; }, `${colorTitle(slug)} added to ${material} · live for buyers`).then(() => document.querySelector(`[data-add-color="${CSS.escape(key)}"]`)?.focus());
  };
  pop.onkeydown = e => { if (e.key === 'Enter' && e.target.matches('input')) { e.preventDefault(); q('[data-color-confirm]').click(); } };
}

/* Editor entry: loads the draft (or approved equipment) and restores an unsaved session after reload. */
async function showEquipment() {
  if (!account || account.role === 'admin') { $('#app').innerHTML = panelMessage('Buyer or host account required', 'Sign in with a marketplace account.'); return; }
  try {
    [printerCatalogue, materialCatalogue] = await Promise.all([api('/printer-catalogue'), api('/materials')]);
    const application = await api('/host/application');
    if (application && ['pending', 'suspended'].includes(application.status)) { $('#app').innerHTML = layout(head('Printing host application', 'Host application') + `<div class="section-card access-card"><h2>Application ${statusBadge(application.status)}</h2><p>${esc(application.status === 'pending' ? 'Your application is awaiting administrator review. You will be able to accept printing jobs once it is approved.' : application.rejection_reason || 'Your host access is suspended. Contact the marketplace administrator.')}</p><div class="actions"><a class="btn light" href="#account-contact">Review contact details</a><a class="btn light" href="#catalogue">Back to the marketplace</a></div></div>`); return; }
    approvedEquipment = await api('/host/equipment');
    equipmentRevision = account.role === 'host' ? await api('/host/equipment-revision') : null;
    const status = equipmentRevision?.status;
    if (status === 'pending') { toast('An equipment update is already awaiting review.'); location.replace('#my-printers'); return; }
    const fromRejected = location.hash.includes('from=rejected') && status === 'rejected';
    const approvedState = {company:application?.additional || '', weekly_hours:Number(application?.capabilities?.match(/weekly availability: (\d+)/)?.[1]) || null, printers:approvedEquipment.map(specOnly)};
    approvedPayloadMeta = {company:approvedState.company, weekly_hours:approvedState.weekly_hours};
    editorSource = account.role !== 'host' ? 'application' : status === 'draft' ? `draft:${equipmentRevision.id}:${equipmentRevision.updated_at}` : fromRejected ? `rejected:${equipmentRevision.id}` : 'approved';
    const base = status === 'draft' || fromRejected ? equipmentRevision.proposal : approvedState;
    let saved = null; try { saved = JSON.parse(sessionStorage.getItem(equipmentKey())); } catch (e) {}
    if (saved?.source === editorSource && saved.data) { hostDraft = saved.data; hostStep = saved.step || 0; editorDirty = true; }
    else { hostDraft = structuredClone(base); editorDirty = false; if (saved) clearEditorSession(); }
    hostDraft.printers = hostDraft.printers.map(specOnly);
    if (!hostDraft.printers.length && account.role !== 'host') hostDraft.printers = [];
    equipmentView();
  } catch (e) { showError(e); }
}
// Read-only summary reused by the administrator's revision review: certified specifications only.
const equipmentSummary = printers => printers.map(p => `<li>${esc(p.manufacturer + ' ' + p.model)} × ${p.quantity} · ${p.technology} · ${p.x} × ${p.y} × ${p.z} mm<br>Supported materials: ${esc((p.capabilities || p.materials || []).join(', ') || 'not documented')}</li>`).join('');
render = function() { if (['onboarding', 'my-printers/edit'].includes(currentRoute())) { showEquipment(); return; } equipmentRender(); };
