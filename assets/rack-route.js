/* Design Your Rack: routes and entry points. The configurator itself (its script, styles and three.js) loads only when
   someone opens it, so no other page pays for it. */
const rackRender = render;
let rackModule = null;
const isRackRoute = route => route === 'design-rack' || route.startsWith('design-rack/') || route === 'my-designs';
// The footer stays below the fold while this tall page loads, so it does not jump down twice as the page fills in.
const reserveRackHeight = on => { document.getElementById('app').style.minHeight = on ? '100vh' : ''; };
if (isRackRoute(currentRoute())) reserveRackHeight(true);
function loadRackModule() {
  if (!document.querySelector('link[data-rack-styles]')) document.head.insertAdjacentHTML('beforeend', '<link rel="stylesheet" data-rack-styles href="assets/rack-configurator.css?v=11">');
  return rackModule ||= import('./rack-configurator.js?v=10');
}
// How a custom rack appears on an order line, for its buyer and its host: what it holds, its style and its label.
function rackLineNote(item) {
  const rack = item?.rack; if (!rack) return '';
  const tubes = (rack.tubes || []).map(t => `${t.quantity} × ${Number(t.nominal_ml)} mL`).join(', ');
  const label = rack.label ? `, labelled "${esc(rack.label.text)}" (${esc(rack.label.style)}, ${esc(rack.label.position)})` : '';
  return `<span class="row-meta bo-meta">Custom rack, ${esc(rack.style === 'premium' ? 'Premium' : 'Lightweight')}: ${esc(tubes)}${label}. Prints upright.</span>`;
}
// The whole specification, as sold: everything a host needs to make it and a buyer needs to recognise it.
function rackSpecification(item, forHost = false) {
  const rack = item?.rack; if (!rack) return '';
  const row = (term, value) => value ? `<div><dt>${esc(term)}</dt><dd>${esc(value)}</dd></div>` : '';
  const tubes = (rack.tubes || []).map(t => `${t.quantity} × ${t.label}`).join(', ');
  const label = rack.label ? `"${rack.label.text}" (${rack.label.style}, ${rack.label.position})` : 'None';
  const size = rack.dims_mm ? `${rack.dims_mm.map(v => Number(v).toFixed(1)).join(' × ')} mm` : item.dimensions;
  return `<dl class="detail-grid">${row('Design name', rack.name)}${row('Holds', tubes)}${row('Design', rack.style === 'premium' ? 'Premium' : 'Lightweight')}${row('Text on the rack', label)}${row('Measured size', size)}${row('Material and colour', [item.material, item.color ? colorName(item.color) : ''].filter(Boolean).join(', '))}${forHost ? row('Estimated plastic', rack.estimated_grams ? `About ${rack.estimated_grams} g per rack. Your slicer sets the real amount.` : '') : ''}</dl>${forHost ? '<p class="muted">Print upright with the base on the bed, as one piece. The model is designed to need no supports; check your slicer preview. Starting point: 0.2 mm layers, 3 perimeters, 15% infill.</p>' : ''}<p class="muted">Prototype design: tube dimensions are based on preliminary profiles and have not yet been physically validated.</p>`;
}
document.addEventListener('click', async event => {
  const again = event.target.closest?.('[data-rack-reorder]'), redraft = event.target.closest?.('[data-rack-redraft]');
  if (!again && !redraft) return;
  try {
    if (redraft) { const design = await api(`/racks/orders/${redraft.dataset.rackRedraft}/design`, {method: 'POST'}); document.querySelector('dialog[open]')?.close(); location.hash = 'design-rack/' + design.id; return; }
    // Today's hosts and today's price, confirmed in the basket: an old order's price is never reused.
    const line = await api(`/racks/orders/${again.dataset.rackReorder}/reorder`, {method: 'POST'});
    await accountAction('/cart', {listing_id: line.listing_id, material: line.material, color: line.color, quantity: 1, expected_unit_price_cents: line.unit_price_cents});
    if (typeof refreshCart === 'function') await refreshCart().catch(() => {});
    renderNavbar(currentRoute()); toast(`Added to your basket at today's price, ${money(line.unit_price_cents / 100)}`);
  } catch (e) { toast(e.message); }
});
const rackOrderActions = item => item?.rack ? `<div class="actions rack-order-actions"><button type="button" class="btn-ghost btn-sm" data-rack-reorder="${item.id}">Reorder</button><button type="button" class="btn-ghost btn-sm" data-rack-redraft="${item.id}">New design from this</button></div>` : '';
// Administrators set the rates a custom rack is priced from.
async function rackPricingForm() {
  const r = await api('/admin/rack-pricing');
  const number = (name, label, value, step = '0.01') => `<label>${label}<input name="${name}" type="number" min="0" step="${step}" required value="${esc(value)}"></label>`;
  return `<form id="rack-pricing-form" class="section-card settings-form"><header class="card-head"><div><h2>Custom rack pricing</h2><p class="muted">What Design Your Rack charges for each rack. New rates apply the next time a rack is added to a basket; placed orders keep their price. The starting values are prototype values, not validated commercial rates.</p></div></header><div class="fields">${Object.entries(r.material_eur_per_kg).map(([m, v]) => number('material:' + m, `${esc(m)} (EUR per kg)`, v)).join('')}${number('setup_eur', 'Setup, per rack (EUR)', r.setup_eur)}${number('machine_eur_per_hour', 'Printer time (EUR per hour)', r.machine_eur_per_hour)}${number('deposition_mm3_s', 'Assumed print speed (mm³ per second)', r.deposition_mm3_s, '0.1')}${number('per_hole_eur', 'Per tube position (EUR)', r.per_hole_eur)}${number('label_eur', 'Label (EUR)', r.label_eur)}${number('premium_factor', 'Premium design factor', r.premium_factor)}${number('marketplace_fee_pct', 'Marketplace fee (%)', r.marketplace_fee_pct, '0.1')}</div><label class="check"><input type="checkbox" name="commercially_validated" ${r.commercially_validated ? 'checked' : ''}> These rates are commercially validated (removes the "prototype price" wording)</label><div class="actions"><button class="primary">Save pricing</button></div><p class="form-error" role="alert" id="rack-pricing-error"></p></form>`;
}
function bindRackPricing() {
  const form = document.getElementById('rack-pricing-form'); if (!form) return;
  form.onsubmit = async event => {
    event.preventDefault();
    const body = {material_eur_per_kg: {}, commercially_validated: form.elements.commercially_validated.checked};
    for (const el of form.querySelectorAll('input[type=number]')) { if (el.name.startsWith('material:')) body.material_eur_per_kg[el.name.slice(9)] = Number(el.value); else body[el.name] = Number(el.value); }
    try { await api('/admin/rack-pricing', {method: 'PUT', body: JSON.stringify(body)}); document.getElementById('rack-pricing-error').textContent = ''; toast('Rack pricing saved'); }
    catch (e) { document.getElementById('rack-pricing-error').textContent = e.message; }
  };
}
// A rack also has a 3MF of the same geometry, from the same protected route.
const rackThreeMf = (job, className) => job.item.rack?.has_3mf ? ` <a class="${className}" href="/api/jobs/${job.id}/cad?format=3mf" download>Download 3MF</a>` : '';
const RACK_PROMO = `<aside class="rack-promo"><div><h2>Need a rack for your exact tubes?</h2><p>Choose the tubes you use, mix any sizes, and have one rack printed to fit them.</p></div><a class="btn" href="#design-rack">Design your rack</a></aside>`;
render = function() {
  const route = currentRoute();
  reserveRackHeight(isRackRoute(route));
  if (isRackRoute(route)) {
    renderNavbar(route);
    if (!$('#rk-root') && !$('#rk-designs')) $('#app').innerHTML = layout('<div class="ws-loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading the configurator…</div>');
    loadRackModule().then(m => { if (isRackRoute(currentRoute())) m.showRoute(currentRoute()); }).catch(() => { $('#app').innerHTML = layout('<div class="banner danger" role="alert"><span>The configurator could not load. Check your connection and reload the page.</span></div>'); });
    return;
  }
  rackModule?.then(m => m.leave());
  rackRender();
  if (route === 'catalogue' && !$('.rack-promo')) $('#app .page-head')?.insertAdjacentHTML('afterend', RACK_PROMO);
};
