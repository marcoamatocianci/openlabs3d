/* Marketplace filter bar: listbox dropdowns, maximum-price slider, applied-filter chips.
   Field names stay q / category / material / sort / max, so the existing filter() request is unchanged.
   Applied filters are kept for the browser session; the price range comes from the full catalogue. */
const CF_KEY = 'ol3d-catalogue-filters', CF_MIN = 5;
const CF_SORTS = [['newest', 'Newest first'], ['oldest', 'Oldest first'], ['price_asc', 'Price: low to high'], ['price_desc', 'Price: high to low']];
const CF_MATERIALS = [['', 'All materials'], ['PETG', 'PETG'], ['PLA', 'PLA']];
const cfDefaults = {q:'', category:'', material:'', sort:'newest', max:''};
let cfApplied = {...cfDefaults}, cfRange = null;

function cfLoad() {
  let saved = {}; try { saved = JSON.parse(sessionStorage.getItem(CF_KEY)) || {}; } catch (e) {}
  const par = new URLSearchParams(location.hash.split('?')[1]);
  cfApplied = {...cfDefaults, ...saved};
  for (const k of ['q', 'category']) if (par.has(k)) cfApplied[k] = par.get(k);
  return cfApplied;
}
const cfOptions = name => name === 'category' ? [['', 'All categories'], ...categories.map(c => [c, c])] : name === 'material' ? CF_MATERIALS : CF_SORTS;
function cfSelect(name, label, value) {
  return uiSelect({name, label, value, options:cfOptions(name), id:'cf-' + name, attrs:`data-cf-select="${name}"`});
}
/* Markup used by catalogue() in app.js. */
function catalogueFilterBar() {
  const a = cfLoad();
  return `<div class="cf-bar"><div class="cf-group">${cfSelect('category', 'Category', a.category)}${cfSelect('material', 'Material', a.material)}<div class="cf-select" data-select="price" data-select-popover data-cf-select="price"><span class="cf-label" id="cf-l-price">Price</span><button type="button" class="cf-trigger" id="cf-t-price" aria-expanded="false" aria-controls="cf-price-pop" aria-labelledby="cf-l-price cf-t-price"><span class="cf-value" id="cf-price-value">${esc(cfPriceLabel(a.max))}</span><svg class="cf-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button><div class="cf-menu cf-price-pop" id="cf-price-pop" role="group" aria-label="Maximum price" hidden><div class="cf-price-head"><label class="cf-label" for="cf-range">Maximum price</label><output id="cf-price-out" for="cf-range">Loading…</output></div><input type="range" id="cf-range" min="${CF_MIN}" max="${CF_MIN + 1}" step="1" value="${CF_MIN + 1}" disabled aria-valuetext="Loading price range"><div class="cf-scale" aria-hidden="true"><span id="cf-min-label">€${CF_MIN}</span><span id="cf-max-label"></span></div><button type="button" class="cf-any" data-cf-any>Any price</button></div><input type="hidden" name="max" value="${esc(a.max)}"></div>${cfSelect('sort', 'Sort by', a.sort)}</div><div class="cf-actions"><button type="button" class="cf-clear" data-cf-clear>Clear filters</button><button type="submit" class="cf-apply" id="cf-apply" aria-describedby="cf-dirty">Apply filters</button><span id="cf-dirty" class="sr-only"></span></div></div><div class="cf-chips" id="cf-chips" aria-live="polite"></div>`;
}

/* Current control values, as the form would submit them. */
function cfCurrent() {
  const form = $('#filters'); if (!form) return cfApplied;
  const d = Object.fromEntries(new FormData(form));
  return {q:(d.q || '').trim(), category:d.category || '', material:d.material || '', sort:d.sort || 'newest', max:d.max || ''};
}
function cfSyncDirty() {
  const now = cfCurrent(), dirty = Object.keys(cfDefaults).some(k => String(now[k]) !== String(cfApplied[k]));
  $('#cf-apply')?.classList.toggle('is-dirty', dirty);
  const note = $('#cf-dirty'); if (note) note.textContent = dirty ? 'Filters changed but not applied yet' : '';
}
function cfSetValue(name, value) { uiSelectSet(document.querySelector(`[data-cf-select="${name}"]`), value); cfSyncDirty(); }
function cfPriceLabel(cents) { return cents === '' ? 'Any price' : 'Up to ' + money(+cents / 100); }
function cfSetPrice(value) {
  const range = $('#cf-range'), hidden = document.querySelector('#filters [name=max]'); if (!range || !hidden || !cfRange) return;
  const euros = Math.min(cfRange.max, Math.max(cfRange.min, Math.round(value)));
  range.value = euros; hidden.value = euros >= cfRange.max ? '' : String(euros * 100);
  $('#cf-price-value').textContent = $('#cf-price-out').textContent = cfPriceLabel(hidden.value);
  range.setAttribute('aria-valuetext', cfPriceLabel(hidden.value));
  range.style.setProperty('--fill', ((euros - cfRange.min) / Math.max(1, cfRange.max - cfRange.min) * 100) + '%');
  cfSyncDirty();
}
// The slider maximum is the highest price in the whole published catalogue, never the filtered results.
async function cfLoadRange() {
  const range = $('#cf-range'); if (!range) return;
  try {
    const top = (await api('/listings?sort=price_desc&per_page=1')).items[0];
    if (!range.isConnected) return;
    const highest = top ? Math.ceil(top.price_cents / 100) : 0;
    if (highest <= CF_MIN) {
      cfRange = null; range.disabled = true; $('#cf-max-label').textContent = '';
      $('#cf-price-value').textContent = $('#cf-price-out').textContent = highest ? `All under €${CF_MIN}` : 'No prices yet';
      document.querySelector('#filters [name=max]').value = ''; cfApplied.max = ''; cfRenderChips(); return;
    }
    cfRange = {min:CF_MIN, max:highest}; range.min = CF_MIN; range.max = highest; range.disabled = false;
    $('#cf-max-label').textContent = '€' + highest;
    // Keep the chosen maximum unless the catalogue no longer reaches it.
    const chosen = cfApplied.max === '' ? highest : Math.round(+cfApplied.max / 100);
    if (chosen >= highest && cfApplied.max !== '') { cfApplied.max = ''; cfStore(); cfRenderChips(); }
    cfSetPrice(chosen);
  } catch (e) { $('#cf-price-out').textContent = 'Unavailable'; }
}
function cfStore() { try { sessionStorage.setItem(CF_KEY, JSON.stringify(cfApplied)); } catch (e) {} }
function cfRenderChips() {
  const box = $('#cf-chips'); if (!box) return;
  const a = cfApplied, chips = [a.q && ['q', `“${a.q}”`], a.category && ['category', a.category], a.material && ['material', a.material], a.max && ['max', cfPriceLabel(a.max)]].filter(Boolean);
  box.innerHTML = chips.map(([k, l]) => `<button type="button" class="cf-chip" data-cf-remove="${k}" aria-label="Remove filter ${esc(l)}">${esc(l)}<span aria-hidden="true">×</span></button>`).join('');
  box.hidden = !chips.length;
}
// Called when the form is submitted (Apply filters or Search), before the request runs.
function cfCommit() { cfApplied = cfCurrent(); cfStore(); cfRenderChips(); cfSyncDirty(); }
function cfApply() { $('#filters')?.requestSubmit(); }
function cfClear() {
  const q = document.querySelector('#filters [name=q]'); if (q) q.value = '';
  ['category', 'material'].forEach(n => cfSetValue(n, '')); cfSetValue('sort', 'newest');
  if (cfRange) cfSetPrice(cfRange.max);
  cfApply();
}

/* Opening, closing and keyboard handling of the dropdowns live in select.js; these are the filter bar's own buttons. */
document.addEventListener('click', e => {
  if (e.target.closest('[data-cf-any]')) {
    if (cfRange) cfSetPrice(cfRange.max);
    uiSelectClose(e.target.closest('[data-select]'), true);
    return;
  }
  if (e.target.closest('[data-cf-clear]')) cfClear();
  const chip = e.target.closest('[data-cf-remove]');
  if (chip) {
    const k = chip.dataset.cfRemove;
    if (k === 'q') document.querySelector('#filters [name=q]').value = ''; else if (k === 'max') { if (cfRange) cfSetPrice(cfRange.max); } else cfSetValue(k, '');
    cfApply();
  }
});
document.addEventListener('input', e => {
  if (e.target.id === 'cf-range') cfSetPrice(+e.target.value);
  else if (e.target.closest?.('#filters')) cfSyncDirty();
});
// Commit before app.js runs the submit handler that requests the filtered listings.
document.addEventListener('submit', e => { if (e.target.id === 'filters') cfCommit(); }, true);

/* Wire-up after the catalogue renders. */
function initCatalogueFilters() { cfRenderChips(); cfSyncDirty(); cfLoadRange(); }
