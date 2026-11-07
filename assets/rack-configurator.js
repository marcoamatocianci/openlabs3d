/* Design Your Rack. One configuration object drives everything: the tube shelf, the top view and the 3D stage all read
   it and change it, so they cannot disagree. The server plans each change (layout, checks, price estimate), and the worker
   builds the exact CAD model of whatever the buyer settles on. Nothing here decides a price or a position for real. */
const DRAFT_KEY = 'ol3d-rack-draft';
const CLEARANCES = [[-.2, 'Tighter (0.2 mm less)'], [0, 'Recommended'], [.2, 'Looser (0.2 mm more)'], [.4, 'Loosest (0.4 mm more)']];
const SPACINGS = [['compact', 'Compact'], ['standard', 'Comfortable'], ['roomy', 'Roomy']];
const LAYOUTS = {balanced: ['Balanced', 'Tidy, easy to reach'], compact: ['Compact', 'Smallest footprint'], wide: ['Wide', 'Long and shallow']};
const ORIENTATIONS = [['auto', 'Auto', ''], ['landscape', 'Wide', 'M1 4h14v8H1z'], ['portrait', 'Deep', 'M4 1h8v14H4z']];
const FACES = [['front', 'Front'], ['back', 'Back'], ['left', 'Left side'], ['right', 'Right side'], ['top', 'Top edge (Premium)']];
const EDGES = [['sharp', 'Crisp'], ['soft', 'Soft'], ['rounded', 'Rounded']];
const SIZES = [['', 'As large as fits'], ['8', '8 mm'], ['10', '10 mm'], ['12', '12 mm'], ['14', '14 mm'], ['16', '16 mm']];
const TUBE_COLORS = {'conical-50': 'var(--rk-t50)', 'conical-15': 'var(--rk-t15)', 'micro-1.5': 'var(--rk-t15m)', 'micro-0.5': 'var(--rk-t05)'};
const STATUS_TEXT = {generic_unverified: 'Typical size, not measured', published_unmeasured: 'Size from a published sheet, not measured', measured: 'Measured'};
const CAP_HEIGHT = {conical: 12, micro: 5};
const POLL_MS = 1200, PLAN_DELAY = 110, BUILD_DELAY = 800, HISTORY = 60;

let catalog = null;
const S = {config: null, plan: null, build: null, buildHash: '', design: null, name: '', editing: false, suggestion: null, heightEdit: false, heightBefore: null, heightDragging: false, material: '', color: '', selected: new Set(), armed: '', undo: [], redo: [], viewer: null, viewerPromise: null, showTubes: false, guides: false, adding: false, mounted: false, advanced: false};
let planSeq = 0, planAbort = null, planTimer = 0, buildTimer = 0, pollTimer = 0, buildSeq = 0, drag = null, savedTitle = '', savedDescription = '';
/* A phone is a different way of working, not a narrower page: same configuration, other interactions. */
const PHONE = matchMedia('(max-width: 760px), (max-height: 480px) and (orientation: landscape)'), LANDSCAPE = matchMedia('(orientation: landscape)');
const q = selector => document.querySelector(selector);
const root = () => q('#rk-root');
const profile = id => catalog.profiles.find(p => p.id === id);
const familyOf = id => profile(id)?.family || 'conical-50';
const clone = value => JSON.parse(JSON.stringify(value));
const domId = family => family.replace('.', '_');     // a dot would not survive a CSS selector

function freshConfig(tubes = {'micro-1.5-generic': 24}, style = 'lightweight') {
  return {schema_version: 1, tubes: Object.entries(tubes).map(([profile_id, quantity]) => ({profile_id, quantity})), layout: {mode: 'auto', spacing: 'standard', arrangement: 'auto', orientation: 'auto', columns: null, outer_margin_mm: 0, positions: [], preference: 'balanced'}, style, edge: 'soft', corner_radius_mm: null, height_mm: null, clearance_adjust_mm: 0, overrides: {}, label: null};
}
const isManual = () => S.config.layout.mode === 'manual';
function countOf(family) {
  if (isManual()) return S.config.layout.positions.filter(p => familyOf(p.profile_id) === family).length;
  return S.config.tubes.filter(t => familyOf(t.profile_id) === family).reduce((n, t) => n + t.quantity, 0);
}
function profileOf(family) {
  const used = isManual() ? S.config.layout.positions.find(p => familyOf(p.profile_id) === family)?.profile_id : S.config.tubes.find(t => familyOf(t.profile_id) === family && t.quantity > 0)?.profile_id;
  return used || S.chosenProfiles?.[family] || catalog.families.find(f => f.id === family).default;
}

/* ---- Changing the configuration: every change passes through here ---- */
function change(mutator, {history = true} = {}) {
  if (history) { S.undo.push(JSON.stringify(S.config)); if (S.undo.length > HISTORY) S.undo.shift(); S.redo = []; }
  mutator(S.config);
  afterChange();
}
function afterChange() {
  S.stale = true;     // until the planner answers, what is on screen is the rack as it was
  S.heightEdit = false;
  saveDraft(); syncControls(); drawShelf(); drawAdvancedState(); schedulePlan(); updateHistoryButtons(); drawBuildState();
  if (S.editing) drawPlan();
}
function restore(from, to) {
  if (!from.length) return;
  to.push(JSON.stringify(S.config)); S.config = JSON.parse(from.pop()); S.selected.clear(); afterChange();
}
const draftKey = () => S.design ? `${DRAFT_KEY}-${S.design.id}` : DRAFT_KEY;
function saveDraft() {
  try { localStorage.setItem(draftKey(), JSON.stringify({config: S.config, material: S.material, color: S.color, name: S.name, advanced: S.advanced})); } catch (e) {}
}
function loadDraft(key = DRAFT_KEY) {
  try { const d = JSON.parse(localStorage.getItem(key) || 'null'); return d?.config?.schema_version === 1 ? d : null; } catch (e) { return null; }
}
function forgetDraft(key) { try { localStorage.removeItem(key); } catch (e) {} }

/* ---- Planning: quick, on every change, always answering the latest request ---- */
function schedulePlan() { clearTimeout(planTimer); planTimer = setTimeout(requestPlan, PLAN_DELAY); setBusy(true); }
async function requestPlan() {
  const seq = ++planSeq;
  planAbort?.abort(); planAbort = new AbortController();
  try {
    const plan = await api('/racks/plan', {method: 'POST', body: JSON.stringify(S.config), signal: planAbort.signal});
    if (seq !== planSeq || !root()) return;
    applyPlan(plan);
  } catch (e) {
    if (e.name === 'AbortError' || seq !== planSeq || !root()) return;
    setBusy(false);
    showProblems([{level: 'error', code: 'request', message: e.status === 422 ? 'Check the values you entered: one of them is outside what a rack can use.' : e.message, fix: ''}]);
    updateActions();
  }
}
function applyPlan(plan) {
  S.plan = plan; setBusy(false); S.stale = false;
  if (keepHeightPossible(plan)) return;
  if (plan.dims) ensureViewer().then(v => { if (v && S.plan === plan) v.showPlan(plan); }); else S.viewer?.clear();
  drawEnvelopes(); chooseFinish(); drawFinish(); showProblems(plan.issues); drawMetrics(); drawSummary(); drawLayouts(); drawHeight();
  if (S.editing) { drawPlan(); cancelBuild(); }     // no CAD on every move: the exact model is made when editing is done
  else if (plan.ok && plan.hash) scheduleBuild(plan.hash); else cancelBuild();
  updateActions();
}
/* Tubes changed and the height the buyer chose no longer suits them: move it to the nearest that does, and say so. Only a
   height typed on purpose is left out of range, to be explained. */
function keepHeightPossible(plan) {
  const h = plan.height, wanted = S.config.height_mm;
  if (!h || wanted === null || wanted === undefined || S.heightEdit || (wanted >= h.min && wanted <= h.max)) return false;
  S.config.height_mm = wanted < h.min ? h.min : h.max; saveDraft(); schedulePlan();
  announce(`Height changed to ${mm(S.config.height_mm)} mm to suit these tubes.`);
  S.heightNotice = `Changed to ${mm(S.config.height_mm)} mm to suit these tubes.`;
  return true;
}
function setBusy(on) { root()?.classList.toggle('is-planning', on); }

/* ---- The exact model ---- */
function cancelBuild() { clearTimeout(buildTimer); clearTimeout(pollTimer); buildSeq++; S.build = null; S.buildHash = ''; drawBuildState(); drawReport(); }
function scheduleBuild(hash) {
  if (hash === S.buildHash && S.build) { drawBuildState(); return; }
  clearTimeout(buildTimer); clearTimeout(pollTimer); const seq = ++buildSeq;
  S.build = {status: 'waiting'}; S.buildHash = hash; drawBuildState(); drawReport();
  buildTimer = setTimeout(() => startBuild(seq, hash), BUILD_DELAY);
}
async function startBuild(seq, hash) {
  try {
    const build = await api('/racks/builds', {method: 'POST', body: JSON.stringify(S.config)});
    if (seq !== buildSeq) return;
    receiveBuild(seq, hash, build);
  } catch (e) {
    if (seq !== buildSeq) return;
    S.build = {status: e.status === 429 || e.status === 503 ? 'busy' : 'failed', error: e.message};
    if (S.build.status === 'busy') buildTimer = setTimeout(() => startBuild(seq, hash), 20000);
    drawBuildState(); drawReport(); updateActions();
  }
}
function receiveBuild(seq, hash, build) {
  S.build = build; drawBuildState(); drawMetrics(); drawReport(); updateActions(); drawFinish();
  if (build.status === 'ready') {
    // "Exact model" is only ever said of what is on screen: the mesh made from the solid the STL and 3MF come from, and only
    // once it has arrived. Where the browser cannot show 3D there is nothing to contradict.
    ensureViewer().then(async v => {
      if (v) await v.showExact(hash, build.preview_url);
      if (seq !== buildSeq) return;
      S.shownHash = !v || v.shown().hash === hash ? hash : ''; S.previewFailed = false; drawBuildState();
    }).catch(() => { if (seq === buildSeq) { S.previewFailed = true; drawBuildState(); } });
    return;
  }
  if (build.status === 'failed') return;
  pollTimer = setTimeout(async () => {
    try {
      const next = await api('/racks/builds/' + hash);
      if (seq !== buildSeq) return;
      if (next.status === 'abandoned') { startBuild(seq, hash); return; }
      receiveBuild(seq, hash, next);
    } catch (e) { if (seq === buildSeq) pollTimer = setTimeout(() => startBuild(seq, hash), 4000); }
  }, POLL_MS);
}
function drawBuildState() {
  const node = q('#rk-state'); if (!node) return;
  const state = S.build?.status;
  const text = S.editing ? {t: 'Live preview', c: 'is-working is-quiet'}
    : S.stale ? {t: 'Updating…', c: 'is-working'}
    : !S.plan?.ok ? {t: 'Needs a change before it can be made', c: 'is-blocked'}
    : state === 'ready' && S.previewFailed ? {t: 'Model ready, but it could not be shown here', c: 'is-blocked'}
    : state === 'ready' && S.shownHash === S.buildHash ? {t: 'Exact model', c: 'is-exact'}
    : state === 'ready' ? {t: 'Loading the exact model…', c: 'is-working'}
    : state === 'failed' ? {t: 'The exact model could not be made', c: 'is-blocked'}
    : state === 'busy' ? {t: 'Generator busy, trying again shortly', c: 'is-working'}
    : {t: 'Quick preview, making the exact model…', c: 'is-working'};
  node.className = 'rk-state ' + text.c; node.textContent = text.t;
}

/* ---- Materials and colours come from what approved hosts really stock, for this rack's size ---- */
function offered() { return S.plan?.availability?.materials || {}; }
function chooseFinish() {
  const materials = offered(), before = `${S.material}/${S.color}`;
  if (!materials[S.material]) S.material = Object.keys(materials)[0] || '';
  const colors = materials[S.material]?.colors || {};
  if (!colors[S.color]) S.color = readableColor(colors);
  S.viewer?.setColor(colors[S.color], S.material);
  syncFinish(before !== `${S.material}/${S.color}` && before !== '/');
}
/* The server must plan for the finish on screen: it decides which printers count and how many hosts can make this. */
function syncFinish(changed) {
  if (S.config.material === S.material && S.config.color === S.color) return;
  S.config.material = S.material; S.config.color = S.color; saveDraft(); schedulePlan();
  if (changed && S.material) announce(`Now showing ${S.material}, ${colorName(S.color)}: your earlier choice is not available for this rack.`);
}
function setFinish(material, color) {
  S.material = material; S.color = color;
  S.viewer?.setColor(offered()[material]?.colors?.[color], material);
  syncFinish(false); drawFinish(); drawMetrics(); updateActions();
}
const envelopeValue = e => `${e.x},${e.y},${e.z}`;
function drawEnvelopes() {
  const select = q('#rk-envelope'); if (!select) return;
  const list = S.plan?.availability?.envelopes || [], chosen = S.config.layout.envelope;
  // A printing area the chosen material or colour no longer has is not on offer any more.
  if (chosen && S.plan && !list.some(e => envelopeValue(e) === envelopeValue(chosen))) {
    S.config.layout.envelope = null; saveDraft(); schedulePlan();
    announce('The printing area you chose is not available for this material and colour, so the choice was cleared.');
  }
  const size = e => `${mm(e.usable[0])} × ${mm(e.usable[1])} × ${mm(e.usable[2])} mm`;
  const who = e => `${e.printers} ${e.printers === 1 ? 'printer' : 'printers'}, ${e.hosts} ${e.hosts === 1 ? 'host' : 'hosts'}`;
  const signature = JSON.stringify(list);
  if (select.dataset.signature !== signature) {
    select.innerHTML = `<option value="">${list.length ? `Any available printer` : 'No printer available'}</option>` + list.map(e => `<option value="${esc(envelopeValue(e))}">Up to ${esc(size(e))} (${esc(who(e))})</option>`).join('');
    select.dataset.signature = signature;
  }
  select.value = S.config.layout.envelope ? envelopeValue(S.config.layout.envelope) : '';
  const finish = S.material ? ` for ${S.material}${S.color ? `, ${colorName(S.color)}` : ''}` : '';
  q('#rk-envelope-note').textContent = list.length ? `From the approved printers of hosts who stock this${finish}, less a margin at the edges. The rack stays within what you choose.` : `No approved printer can print this${finish} right now. Try another material.`;
}
function readableColor(colors) {
  // The calmest colour that still shows the model's shape: bright or near-black plastic hides it.
  const rgb = hex => { const n = parseInt(String(hex).slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
  const light = c => .2126 * c[0] + .7152 * c[1] + .0722 * c[2], saturation = c => Math.max(...c) - Math.min(...c);
  const readable = Object.keys(colors).filter(c => light(rgb(colors[c])) > 70);
  return readable.sort((a, b) => saturation(rgb(colors[a])) - saturation(rgb(colors[b])))[0] || Object.keys(colors)[0] || '';
}
function unitPrice(material = S.material) {
  const exact = S.build?.status === 'ready' ? S.build.estimates?.materials?.[material] : null;
  return (exact || S.plan?.estimates?.materials?.[material])?.unit_price_cents ?? null;
}
function drawFinish() {
  const host = q('#rk-finish'); if (!host) return;
  const materials = offered(), names = Object.keys(materials);
  if (!names.length) {
    const fit = S.plan?.fit?.state;
    const message = !S.plan?.dims ? 'Materials appear once the rack has tubes in it.'
      : S.plan?.availability?.own_printers_only ? 'Only your own printers can make this rack right now, and hosts cannot make their own orders.'
      : fit === 'too_large' ? 'No printer can make a rack this size. Reduce it to see materials.'
      : 'No approved host stocks a material for a rack this size at the moment. You can still save the design.';
    host.innerHTML = `<p class="rk-note">${esc(message)}</p>`; return;
  }
  const colors = materials[S.material]?.colors || {};
  host.innerHTML = `<fieldset class="rk-choice-row"><legend>Material</legend>${names.map(m => `<label class="rk-chip"><input type="radio" name="rk-material" value="${esc(m)}" ${m === S.material ? 'checked' : ''}><span><strong>${esc(m)}</strong><small>${unitPrice(m) === null ? '' : money(unitPrice(m) / 100)}</small></span></label>`).join('')}</fieldset>
    <fieldset class="rk-swatches"><legend>Colour <span class="rk-quiet">${esc(colorName(S.color))}</span></legend><div>${Object.entries(colors).map(([c, hex]) => `<label title="${esc(colorName(c))}"><input type="radio" name="rk-color" value="${esc(c)}" ${c === S.color ? 'checked' : ''}><span style="background:${esc(hex)}"></span><small class="sr-only">${esc(colorName(c))}</small></label>`).join('')}</div></fieldset>
    <p class="rk-note">${hostLine()}</p>`;
}

function hostLine() {
  const selection = S.plan?.availability?.selection;
  if (!selection) return 'Only what hosts with a large enough printer stock today.';
  if (!selection.ok) return esc(selection.message);
  return `${selection.hosts} ${selection.hosts === 1 ? 'host' : 'hosts'} can print this rack in ${esc(selection.material)}, ${esc(colorName(selection.color))} today.`;
}

/* ---- The tube shelf: every tube drawn to the same scale, so its size is obvious ---- */
function tubeFigure(p, active) {
  const s = .74, w = p.cap_diameter_mm * s, body = p.body_diameter_mm * s, tip = p.tip_diameter_mm * s, h = p.overall_length_mm * s, capH = (p.family.startsWith('micro') ? CAP_HEIGHT.micro : CAP_HEIGHT.conical) * s, cone = p.cone_length_mm * s;
  const cx = w / 2, l = cx - body / 2, r = cx + body / 2;
  return `<svg class="rk-tube ${active ? 'is-active' : ''}" viewBox="0 0 ${w.toFixed(1)} ${h.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" aria-hidden="true" style="--tube:${TUBE_COLORS[p.family]}"><path class="rk-tube-body" d="M${l.toFixed(1)} ${capH.toFixed(1)}V${(h - cone).toFixed(1)}L${(cx - tip / 2).toFixed(1)} ${h.toFixed(1)}H${(cx + tip / 2).toFixed(1)}L${r.toFixed(1)} ${(h - cone).toFixed(1)}V${capH.toFixed(1)}Z"/><rect class="rk-tube-cap" x="0" y="0" width="${w.toFixed(1)}" height="${capH.toFixed(1)}" rx="1.4"/></svg>`;
}
function drawShelf() {
  const shelf = q('#rk-shelf'); if (!shelf) return;
  for (const f of catalog.families) {
    const cell = shelf.querySelector(`[data-family="${f.id}"]`), n = countOf(f.id), p = profile(profileOf(f.id));
    cell.querySelector('.rk-figure').innerHTML = tubeFigure(p, n > 0);
    const input = cell.querySelector('input');
    if (document.activeElement !== input) input.value = n;
    cell.classList.toggle('has-tubes', n > 0);
    cell.querySelector('[data-step="-1"]').disabled = n <= 0;
  }
  const total = catalog.families.reduce((sum, f) => sum + countOf(f.id), 0);
  q('#rk-total').textContent = total === 1 ? '1 tube' : `${total} tubes`;
}
function setCount(family, value) {
  const id = profileOf(family), n = Math.max(0, Math.min(catalog.max_tubes, Math.floor(Number(value) || 0)));
  change(c => {
    if (c.layout.mode === 'manual') {
      const here = c.layout.positions.filter(p => familyOf(p.profile_id) === family);
      for (let k = here.length; k > n; k--) { const last = c.layout.positions.map(p => familyOf(p.profile_id)).lastIndexOf(family); c.layout.positions.splice(last, 1); }
      for (let k = here.length; k < n; k++) c.layout.positions.push({profile_id: id, ...freeSpot(c, id)});
      S.selected.clear();
    } else {
      c.tubes = c.tubes.filter(t => familyOf(t.profile_id) !== family);
      if (n) c.tubes.push({profile_id: id, quantity: n});
    }
  });
}
function freeSpot(c, id) {
  const positions = c.layout.positions, need = profile(id).cap_diameter_mm + 6;
  if (!positions.length) return {x: 0, y: 0};
  const right = Math.max(...positions.map(p => p.x + profile(p.profile_id).cap_diameter_mm / 2));
  return {x: Math.round(right + need / 2 + 1), y: Math.round(positions[positions.length - 1].y)};
}

/* ---- Keeping form controls in step with the configuration, without replacing them ---- */
const setChecked = (name, value) => { for (const el of document.getElementsByName(name)) el.checked = el.value === value; };
function syncControls() {
  const c = S.config, label = c.label || {};
  setChecked('rk-style', c.style); setChecked('rk-edge', c.edge); setChecked('rk-label-style', label.style || 'engraved'); setChecked('rk-spacing', c.layout.spacing); setChecked('rk-orientation', c.layout.orientation);
  for (const [id, value] of [['#rk-font', label.font || 'sans'], ['#rk-size', label.size_mm ? String(label.size_mm) : ''], ['#rk-face', label.position || 'front'], ['#rk-clearance', String(c.clearance_adjust_mm)]]) { const el = q(id); if (el) el.value = value; }
  const columns = q('#rk-columns'); if (columns && document.activeElement !== columns) columns.value = c.layout.columns || '';
  const margin = q('#rk-margin'); if (margin && document.activeElement !== margin) margin.value = c.layout.outer_margin_mm || 0;
  const text = q('#rk-text'); if (text && document.activeElement !== text) text.value = label.text || '';
  const named = !!(label.text || '').trim();
  q('#rk-label-style-row').hidden = !named;
  q('#rk-label-options').hidden = !named;
  q('#rk-label-options-empty').hidden = named;
  q('#rk-edge-row').hidden = c.style !== 'premium';
  q('#rk-corner-row').hidden = c.style !== 'premium';
  const corner = q('#rk-corner'); if (corner && document.activeElement !== corner) corner.value = c.corner_radius_mm ?? '';
  q('#rk-auto-options').hidden = c.layout.mode === 'manual';
  for (const f of catalog.families) {
    const select = q(`#rk-model-${domId(f.id)}`); if (select) select.value = profileOf(f.id);
    const p = profile(profileOf(f.id)), o = c.overrides[p.id] || {};
    for (const key of ['body_diameter_mm', 'cap_diameter_mm', 'overall_length_mm']) { const el = q(`#rk-${key}-${domId(f.id)}`); if (el) { el.placeholder = p[key]; if (document.activeElement !== el) el.value = o[key] ?? ''; } }
    const note = q(`#rk-source-${domId(f.id)}`); if (note) note.textContent = `${STATUS_TEXT[p.verification_status]}. ${p.source_reference}`;
  }
}
function updateHistoryButtons() {
  for (const el of document.querySelectorAll('[data-act=undo]')) el.disabled = !S.undo.length;
  for (const el of document.querySelectorAll('[data-act=redo]')) el.disabled = !S.redo.length;
}

/* ---- Problems, metrics, report, summary ---- */
function showProblems(issues) {
  const host = q('#rk-problems'); if (!host) return;
  const worst = [...issues].sort((a, b) => (a.level === 'error' ? 0 : 1) - (b.level === 'error' ? 0 : 1));
  // Twenty notes about the same layout tell the buyer nothing more than the first few.
  const shown = worst.slice(0, 6), more = worst.length - shown.length;
  host.innerHTML = shown.length ? `<ul class="rk-issues">${shown.map(i => `<li class="${i.level === 'error' ? 'is-error' : 'is-warning'}"><strong>${esc(i.message)}</strong>${i.fix ? `<span>${esc(i.fix)}</span>` : ''}${i.action ? `<button type="button" class="rk-issue-action" data-issue-kind="${esc(i.action.kind)}" data-issue-value="${esc(String(i.action.value))}">${esc(i.action.label)}</button>` : ''}</li>`).join('')}${more > 0 ? `<li class="is-more"><span>And ${more} more of the same kind, marked in the top view.</span></li>` : ''}</ul>` : '';
}
const mm = n => Number(n).toLocaleString('en', {maximumFractionDigits: 1});
function makerText() {
  const selection = S.plan?.availability?.selection;
  if (!S.plan?.dims) return ['—', ''];
  if (S.plan.fit?.state === 'too_large') return ['Too large', 'for the available printers'];
  if (!selection) return ['—', ''];
  if (!selection.ok) return ['No host yet', 'for this size and finish'];
  return [`${selection.hosts} ${selection.hosts === 1 ? 'host' : 'hosts'}`, 'can print this today'];
}
function drawMetrics() {
  const host = q('#rk-metrics'); if (!host) return;
  const plan = S.plan, ready = S.build?.status === 'ready', dims = ready ? S.build.metrics.dims_mm : plan?.dims;
  const total = plan?.tubes?.length || 0, grams = (ready ? S.build.estimates?.materials?.[S.material] : plan?.estimates?.materials?.[S.material])?.grams;
  const price = unitPrice(), prototype = (S.build?.estimates || plan?.estimates)?.pricing_status !== 'validated', [maker, makerNote] = makerText();
  const cell = (term, value, basis, title = '') => `<div${title ? ` title="${esc(title)}"` : ''}><dt>${term}</dt><dd>${value}${basis ? `<small>${basis}</small>` : ''}</dd></div>`;
  host.innerHTML = [
    cell('Size', dims ? `${Math.round(dims[0])} × ${Math.round(dims[1])} × ${Math.round(dims[2])} mm` : '—', dims ? (ready ? 'Measured on the model' : 'Planned') : ''),
    cell('Holds', total ? (total === 1 ? '1 tube' : `${total} tubes`) : '—', plan?.tubes?.length ? (plan.summary || []).map(p => `${p.quantity} × ${Number(p.nominal_ml)} mL`).join(', ') : ''),
    cell('Finish', S.material ? `${esc(S.material)}, ${esc(colorName(S.color))}` : '—', grams ? `About ${Math.round(grams)} g, an estimate` : ''),
    cell('Printing', esc(maker), esc(makerNote)),
    cell('Price', price !== null && S.material ? money(price / 100) : '—', price !== null && S.material ? (prototype ? 'Prototype price' : ready ? 'Confirmed at checkout' : 'Estimate') : '', price !== null && S.material ? `${prototype ? 'Estimated prototype manufacturing price' : 'Manufacturing price'}. ${ready ? 'For this exact model, confirmed at checkout' : 'Updates when the exact model is ready'}` : ''),
  ].join('');
  const review = q('#rk-review-metrics'); if (review) review.innerHTML = host.innerHTML;
  const strip = q('#rk-strip');
  if (strip) {
    const ok = S.plan?.availability?.selection?.ok && S.plan?.ok;
    q('#rk-strip-size').textContent = dims ? `${total === 1 ? '1 tube' : `${total} tubes`}, ${Math.round(dims[0])} × ${Math.round(dims[1])} × ${Math.round(dims[2])} mm` : 'No tubes yet';
    q('#rk-strip-state').textContent = ok ? `${maker} available` : (S.plan?.ok ? maker : 'Needs a change');
    strip.dataset.ok = ok ? 'true' : 'false';
  }
  drawRows();
  const barPrice = q('#rk-bar-price');
  if (barPrice) { barPrice.textContent = price !== null && S.material ? money(price / 100) : '—'; barPrice.closest('.rk-bar-price').dataset.basis = ready ? 'exact' : 'estimate'; q('#rk-bar-basis').textContent = prototype ? 'prototype price, each' : ready ? 'each' : 'estimate'; }
}
function drawReport() {
  const host = q('#rk-report'); if (!host) return;
  const report = S.build?.status === 'ready' ? S.build.report : null;
  if (!report) { host.innerHTML = S.build?.status === 'failed' ? `<p class="rk-note is-error" role="alert">${esc(S.build.error || 'The exact model could not be generated.')} Nothing invalid is ever offered for printing. Try another arrangement.</p>` : '<p class="rk-note">The checks appear when the exact model is ready.</p>'; return; }
  const list = (items, get) => `<ul>${items.map(i => `<li>${esc(get(i))}</li>`).join('')}</ul>`;
  host.innerHTML = `<details><summary>${report.geometry_checked.length} geometry checks passed on the exact model</summary>${list(report.geometry_checked, i => i.message)}</details>
    <details><summary>Estimated, against design rules for 3D printing</summary>${list(report.manufacturing_estimated, i => i.message)}<p class="rk-note">Print time is not shown: only the host's slicer can work it out reliably.</p></details>
    <details open><summary>Only a test print can confirm</summary>${list(report.requires_physical_test, i => i)}</details>`;
}
function drawSummary() {
  const host = q('#rk-summary'); if (!host) return;
  const plan = S.plan;
  if (!plan?.dims) { host.textContent = 'This rack holds no tubes yet.'; return; }
  const errors = plan.issues.filter(i => i.level === 'error').length;
  host.textContent = `${S.config.style === 'premium' ? 'Premium' : 'Lightweight'} rack, ${mm(plan.dims[0])} by ${mm(plan.dims[1])} by ${mm(plan.dims[2])} millimetres, holding ${(plan.summary || []).map(p => `${p.quantity} of ${Number(p.nominal_ml)} millilitres`).join(', ')}.${errors ? ` ${errors} problem${errors > 1 ? 's' : ''} to fix.` : ''}`;
  const table = q('#rk-positions tbody');
  // Not while someone is typing a coordinate in it.
  if (table && !table.contains(document.activeElement)) table.innerHTML = plan.tubes.map((t, n) => {
    const p = profile(t.profile_id), o = plan.offset || [0, 0], x = t.x + o[0], y = t.y + o[1];
    return `<tr class="${S.selected.has(n) ? 'is-selected' : ''}"><th scope="row">${n + 1}</th><td>${esc(p?.label || t.profile_id)}</td>${isManual() ? `<td><input class="rk-mini" type="number" step="0.5" aria-label="Position ${n + 1}, left to right, in millimetres" data-coord="x" data-i="${n}" value="${x.toFixed(1)}"></td><td><input class="rk-mini" type="number" step="0.5" aria-label="Position ${n + 1}, front to back, in millimetres" data-coord="y" data-i="${n}" value="${y.toFixed(1)}"></td><td><button type="button" class="link-button" data-remove="${n}" aria-label="Remove position ${n + 1}">Remove</button></td>` : `<td>${mm(x)}</td><td>${mm(y)}</td><td></td>`}</tr>`;
  }).join('');
}

/* ---- Actions ---- */
function whyDisabled() {
  if (account?.role === 'admin') return 'Administrators manage orders and do not buy.';
  if (S.editing) return 'Finish editing the layout to see the exact model and price.';
  if (!S.plan) return 'Planning your rack…';
  if (!S.plan.ok) return 'Fix the problem shown on the preview first.';
  if (S.build?.status === 'failed') return 'The exact model could not be made. Change the design to try again.';
  if (S.build?.status !== 'ready' || S.build?.hash !== S.plan.hash) return 'Ready when the exact model is. This takes a few seconds.';
  if (!S.material || !S.color || (S.plan.availability?.selection && !S.plan.availability.selection.ok)) return 'No Printing Host can make this size in this material and colour yet. Try a smaller rack or another finish.';
  if (S.plan.availability?.selection?.material !== S.material || S.plan.availability?.selection?.color !== S.color) return 'Checking which hosts can make this finish…';
  return '';
}
function updateActions() {
  const add = q('#rk-add'); if (!add) return;
  const why = whyDisabled();
  add.disabled = !!why || S.adding;
  q('#rk-buy').disabled = !!why || S.adding;
  q('#rk-why').textContent = why;
  // Waiting a moment is shown on the model itself: only a reason the buyer can act on takes a line in the bar.
  q('.rk-bar-note').classList.toggle('is-waiting', !S.plan || (S.plan.ok && S.build?.status !== 'failed' && !S.editing && S.build?.status !== 'ready'));
  q('#rk-save').disabled = !S.config;
}
function goToSignIn(message) {
  saveDraft();
  sessionStorage.setItem('ol3d-return-to', location.hash.slice(1) || 'design-rack');
  toast(message); location.hash = 'account';
}
async function saveDesign() {
  if (!account) return goToSignIn('Sign in to save your design. It will be waiting here.');
  const button = q('#rk-save'); button.disabled = true;
  try {
    const name = q('#rk-name').value.trim();
    const body = JSON.stringify({name, config: S.config});
    const saved = S.design ? await api('/racks/designs/' + S.design.id, {method: 'PUT', body}) : await api('/racks/designs', {method: 'POST', body});
    forgetDraft(draftKey());
    S.design = saved; S.name = saved.name; q('#rk-name').value = saved.name;
    toast('Design saved');
    if (location.hash !== '#design-rack/' + saved.id) history.replaceState(null, '', '#design-rack/' + saved.id);
    q('#rk-save-label').textContent = 'Save changes';
  } catch (e) { toast(e.message); }
  updateActions();
}
/* The server re-checks everything here: the exact model is ready, it fits a printer as measured, and a host other than
   this buyer stocks this exact finish. Its answer is the price; nothing on this page is. */
const purchaseLine = quantity => api('/racks/listing', {method: 'POST', body: JSON.stringify({config: S.config, design_id: S.design?.id || null, name: q('#rk-name').value.trim() || S.design?.name || '', material: S.material, color: S.color, quantity})});
const chosenQuantity = () => Math.max(1, Math.min(20, Math.floor(Number(q('#rk-quantity').value) || 1)));
function purchaseFailed(error, button, label, text) {
  button.classList.remove('is-loading'); label.textContent = text;
  q('#rk-add-error').textContent = error.message;
  if (error.detail?.code === 'build_pending') { S.build = null; S.buildHash = ''; }
  schedulePlan();      // hosts may have changed: show what is true now
}
async function addToCart() {
  if (!account) return goToSignIn('Sign in to add this rack to your basket. Your design will be waiting here.');
  const add = q('#rk-add'), error = q('#rk-add-error'), label = add.querySelector('span:last-child');
  S.adding = true; updateActions(); add.classList.add('is-loading'); label.textContent = 'Adding…'; error.textContent = '';
  try {
    const quantity = chosenQuantity(), line = await purchaseLine(quantity);
    await accountAction('/cart', {listing_id: line.listing_id, material: line.material, color: line.color, quantity, expected_unit_price_cents: line.unit_price_cents});
    if (typeof refreshCart === 'function') await refreshCart().catch(() => {});
    renderNavbar(currentRoute());
    add.classList.remove('is-loading'); add.classList.add('is-added'); label.textContent = 'Added';
    error.innerHTML = '<a class="textlink" href="#basket">Go to your basket</a>';
    setTimeout(() => { if (!add.isConnected) return; add.classList.remove('is-added'); label.textContent = 'Add to basket'; }, 2400);
  } catch (e) { purchaseFailed(e, add, label, 'Add to basket'); }
  S.adding = false; updateActions();
}
async function buyNow() {
  if (!account) return goToSignIn('Sign in to buy this rack. Your design will be waiting here.');
  const buy = q('#rk-buy'), label = buy.querySelector('span:last-child');
  S.adding = true; updateActions(); buy.classList.add('is-loading'); label.textContent = 'Preparing…'; q('#rk-add-error').textContent = '';
  try {
    const quantity = chosenQuantity(), line = await purchaseLine(quantity);
    // The site's own Buy Now path: the checkout page re-quotes this line, and the server refuses it if the price moved.
    sessionStorage.setItem('ol3d-direct', JSON.stringify({line: {listing_id: line.listing_id, material: line.material, color: line.color, quantity}, unit_price_cents: line.unit_price_cents, owner: account.id, key: uid(), title: line.title}));
    location.hash = 'checkout';
  } catch (e) { purchaseFailed(e, buy, label, 'Buy now'); S.adding = false; updateActions(); }
  S.adding = false;
}

/* ---- Layout and height: what the software proposes, and what the buyer adjusts ---- */
function layoutThumb(option) {
  const [w, d] = option.dims, pad = 3;
  const circles = option.tubes.map(([x, y, bore]) => `<circle cx="${x}" cy="${-y}" r="${(bore / 2).toFixed(1)}"/>`).join('');
  return `<svg viewBox="${(-w / 2 - pad).toFixed(1)} ${(-d / 2 - pad).toFixed(1)} ${(w + 2 * pad).toFixed(1)} ${(d + 2 * pad).toFixed(1)}" aria-hidden="true"><rect x="${(-w / 2).toFixed(1)}" y="${(-d / 2).toFixed(1)}" width="${w}" height="${d}" rx="${Math.min(10, d / 4).toFixed(1)}"/>${circles}</svg>`;
}
function drawLayouts() {
  const host = q('#rk-layouts'); if (!host) return;
  const plan = S.plan, manual = isManual(), options = plan?.layouts || [];
  q('#rk-auto-layout').hidden = !manual;
  const signature = manual ? `manual${S.config.layout.positions.length}` : JSON.stringify(options);
  q('#rk-layout-size').textContent = plan?.dims ? `${Math.round(plan.dims[0])} × ${Math.round(plan.dims[1])} mm` : '';
  if (host.dataset.signature === signature) return;
  host.dataset.signature = signature;
  if (manual) { host.innerHTML = `<p class="rk-layout-line">Arranged by hand, ${S.config.layout.positions.length} ${S.config.layout.positions.length === 1 ? 'position' : 'positions'}.</p>`; return; }
  if (!options.length) { host.innerHTML = '<p class="rk-layout-line">Arranged automatically to fit an available printer.</p>'; return; }
  host.innerHTML = `<fieldset class="rk-layout-options"><legend class="sr-only">Choose a layout</legend>${options.map(o => `<label class="rk-layout-option"><input type="radio" name="rk-layout" value="${o.id}" ${o.selected ? 'checked' : ''}><span>${layoutThumb(o)}<strong>${LAYOUTS[o.id][0]}</strong><small>${LAYOUTS[o.id][1]}</small><small class="rk-layout-dims">${Math.round(o.dims[0])} × ${Math.round(o.dims[1])} mm</small></span></label>`).join('')}</fieldset>`;
}
function drawHeight() {
  const slider = q('#rk-height'), h = S.plan?.height; if (!slider) return;
  const section = q('#rk-height-section');
  section.hidden = !h && !!S.plan;     // kept on the page until the first answer, so that nothing below it moves
  if (!h) return;
  const fixed = h.max - h.min < .5, typing = document.activeElement === q('#rk-height-mm');
  slider.min = h.min; slider.max = h.max; slider.disabled = fixed;
  if (!S.heightDragging) slider.value = Math.max(h.min, Math.min(h.max, h.value));
  fillSlider();
  if (!typing) q('#rk-height-mm').value = S.config.height_mm ?? h.value;
  q('#rk-height-mm').min = h.min; q('#rk-height-mm').max = h.max;
  slider.setAttribute('aria-valuetext', `${mm(h.value)} millimetres${h.value === h.recommended ? ', recommended' : ''}`);
  q('#rk-height-scale').hidden = fixed; q('#rk-height-track').hidden = fixed;
  q('#rk-height-mark').style.setProperty('--at', fixed ? '0' : String((h.recommended - h.min) / (h.max - h.min)));
  q('#rk-height-low').textContent = `${mm(h.min)} mm, lowest`; q('#rk-height-high').textContent = `${mm(h.max)} mm, most support`;
  const atRecommended = Math.abs(h.value - h.recommended) < .26;
  const reset = q('#rk-height-reset');
  reset.hidden = atRecommended; reset.textContent = `Use recommended ${mm(h.recommended)} mm`;
  q('#rk-height-note').textContent = S.heightNotice || `${heightNote()}${atRecommended ? ' Recommended for these tubes.' : ''}`; S.heightNotice = '';
}
function fillSlider() {
  const slider = q('#rk-height'); if (!slider) return;
  const min = Number(slider.min), max = Number(slider.max);
  slider.style.setProperty('--fill', `${max > min ? (Number(slider.value) - min) / (max - min) * 100 : 0}%`);
}
/* What the height means for the tube that matters most here, in plain measurements. */
function heightNote() {
  const tubes = S.plan?.tubes || [], first = [...tubes].sort((a, b) => b.bore_d - a.bore_d)[0];
  if (!first) return '';
  const held = first.deck - first.floor, above = first.length - held;
  return `A ${Number(profile(first.profile_id).nominal_capacity_ml)} mL tube sits ${Math.round(held)} mm deep, with ${Math.round(above)} mm left to hold.`;
}
/* The phone's short list of everything that is not on the first screen, each saying what it is set to. */
function drawRows() {
  const set = (id, text) => { const node = q(`#${id}`); if (node) node.textContent = text; };
  const options = S.plan?.layouts || [], chosen = options.find(o => o.selected), dims = S.plan?.dims;
  set('rk-row-layout', isManual() ? 'By hand' : chosen ? LAYOUTS[chosen.id][0] : 'Automatic');
  set('rk-row-name', (S.config?.label?.text || '').trim() || 'Add');
  set('rk-row-finish', S.material ? `${S.material}, ${colorName(S.color)}` : 'Choose');
  const swatch = q('#rk-row-swatch'), hex = offered()[S.material]?.colors?.[S.color];
  if (swatch) { swatch.hidden = !hex; if (hex) swatch.style.background = hex; }
  const changes = S.config ? advancedChanges().length : 0;
  set('rk-row-advanced', changes ? `${changes} changed` : '');
  set('rk-row-review', dims ? `${Math.round(dims[0])} × ${Math.round(dims[1])} mm` : '');
}
function applyDevice() {
  const page = root(); if (!page) return;
  const phone = PHONE.matches;
  page.classList.toggle('is-phone', phone); page.classList.toggle('is-landscape', phone && LANDSCAPE.matches);
  if (!phone && q('#rk-bs')?.open) closeSheet();
  if (!phone && q('#rk-focus')?.open) q('#rk-focus').close();
  document.documentElement.classList.toggle('rk-lock', phone && S.editing);
  S.viewer?.setInteractive(!phone || !!q('#rk-focus')?.open || (S.editing && page.classList.contains('show-model')));
  S.viewer?.resize();
}
/* Bottom sheets: real dialogs, so focus is held and restored and Escape closes them. A section moves in and moves back, so
   there is one copy of every control and one configuration. */
function openSheet(id, title) {
  const dialog = q('#rk-bs'), section = q(`#${id}`); if (!dialog || !section || dialog.open) return;
  S.sheetHome = {section, parent: section.parentNode, next: section.nextSibling};
  q('#rk-bs-title').textContent = title; q('#rk-bs-body').append(section);
  dialog.showModal(); q('#rk-bs-body').scrollTop = 0;
}
function closeSheet() { const dialog = q('#rk-bs'); if (dialog?.open) dialog.close(); }
function sheetClosed() {
  const home = S.sheetHome; if (!home) return;
  home.parent.insertBefore(home.section, home.next); S.sheetHome = null; drawRows();
}
function openFocus() {
  const dialog = q('#rk-focus'); if (!dialog || dialog.open) return;
  dialog.append(q('#rk-view-3d')); dialog.showModal();
  root().classList.add('is-focused'); S.viewer?.setInteractive(true); S.viewer?.resize();
}
function focusClosed() {
  (S.editing ? q('#rk-edit-rail') : q('.rk-stage')).prepend(q('#rk-view-3d'));
  root().classList.remove('is-focused'); applyDevice();
}
function setHeight(value) {
  change(c => { c.height_mm = value; });
  S.heightEdit = true;
}
function setLayoutPreference(value) { change(c => { c.layout.preference = value; if (value === 'compact' && c.layout.spacing === 'roomy') c.layout.spacing = 'standard'; }); }

/* ---- The layout editor: tubes as circles at their real size, moved directly ---- */
const SVG_PAD = 14;
function planTubes() {
  // In manual mode the configuration is the truth, also while dragging; automatic layouts come from the plan.
  if (isManual()) return S.config.layout.positions.map((p, i) => {
    const info = profile(p.profile_id), o = S.config.overrides[p.profile_id] || {}, body = o.body_diameter_mm || info.body_diameter_mm;
    return {i, profile_id: p.profile_id, x: p.x, y: p.y, bore: body + info.recommended_clearance_mm + S.config.clearance_adjust_mm, cap: o.cap_diameter_mm || info.cap_diameter_mm};
  });
  const offset = S.plan?.offset || [0, 0];
  return (S.plan?.tubes || []).map(t => ({i: t.i, profile_id: t.profile_id, x: t.x + offset[0], y: t.y + offset[1], bore: t.bore_d, cap: t.cap_d}));
}
function problemTubes() {
  const errors = new Set(), warnings = new Set();
  for (const issue of S.plan?.issues || []) for (const t of issue.tubes || []) (issue.level === 'error' ? errors : warnings).add(t);
  return {errors, warnings};
}
function conflicts(a, b) {
  const d = Math.hypot(a.x - b.x, a.y - b.y);
  return d < (a.bore + b.bore) / 2 + 2.4 || d < (a.cap + b.cap) / 2 + .5;
}
function livePairs(tubes) {
  // Immediate feedback while dragging, by the same distances the server checks when the tube is dropped.
  const bad = new Set();
  for (let a = 0; a < tubes.length; a++) for (let b = a + 1; b < tubes.length; b++) if (conflicts(tubes[a], tubes[b])) { bad.add(tubes[a].i); bad.add(tubes[b].i); }
  return bad;
}
/* The rack's outline as the tubes are now, without asking the server: its size follows the drag. */
function liveOutline(tubes) {
  if (!tubes.length) return null;
  const margin = t => S.plan?.margins?.[t.profile_id] ?? t.cap / 2 + 6;
  const x0 = Math.min(...tubes.map(t => t.x - margin(t))), x1 = Math.max(...tubes.map(t => t.x + margin(t))), y0 = Math.min(...tubes.map(t => t.y - margin(t))), y1 = Math.max(...tubes.map(t => t.y + margin(t)));
  return {x0, x1, y0, y1};
}
function showOutline(tubes) {
  const box = liveOutline(tubes), rect = q('.rk-outline'); if (!box) return;
  if (rect) { rect.setAttribute('x', box.x0.toFixed(1)); rect.setAttribute('y', (-box.y1).toFixed(1)); rect.setAttribute('width', (box.x1 - box.x0).toFixed(1)); rect.setAttribute('height', (box.y1 - box.y0).toFixed(1)); }
  const size = q('#rk-edit-size'); if (size) size.textContent = `${Math.round(box.x1 - box.x0)} × ${Math.round(box.y1 - box.y0)} mm`;
}
function drawPlan() {
  const svg = q('#rk-svg'); if (!svg || drag) return;
  const tubes = planTubes(), plan = S.plan, offset = plan?.offset || [0, 0];
  const fp = plan?.footprint ? [plan.footprint[0] + offset[0], plan.footprint[1] + offset[1], plan.footprint[2] + offset[0], plan.footprint[3] + offset[1]] : null;
  const suggestion = S.suggestion?.tubes || [];
  const xs = tubes.flatMap(t => [t.x - t.cap / 2, t.x + t.cap / 2]).concat(fp ? [fp[0], fp[2]] : [-60, 60]), ys = tubes.flatMap(t => [t.y - t.cap / 2, t.y + t.cap / 2]).concat(fp ? [fp[1], fp[3]] : [-40, 40]);
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  // The largest printer's usable area, when the rack is over it: the buyer sees exactly what does not fit.
  const limit = plan?.fit?.limit || null;
  if (limit) { const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2; x0 = Math.min(x0, cx - limit[0] / 2); x1 = Math.max(x1, cx + limit[0] / 2); y0 = Math.min(y0, cy - limit[1] / 2); y1 = Math.max(y1, cy + limit[1] / 2); }
  // Room around the rack to drag into, so a tube can be moved outward as easily as inward.
  const room = PHONE.matches ? 6 : Math.max(SVG_PAD, Math.min(30, (x1 - x0) * .12));
  const vx = x0 - room, vy = -y1 - room, vw = x1 - x0 + 2 * room, vh = y1 - y0 + 2 * room + 8;
  svg.setAttribute('viewBox', `${vx.toFixed(1)} ${vy.toFixed(1)} ${vw.toFixed(1)} ${vh.toFixed(1)}`);
  const {errors, warnings} = problemTubes();
  const focused = document.activeElement?.closest?.('.rk-pos')?.dataset.i;
  const number = t => t.bore >= 8 ? `<text class="rk-pos-n" y="1.2" font-size="${Math.min(t.bore * .32, 7).toFixed(1)}">${t.i + 1}</text>` : '';
  const scaleBar = `<g class="rk-scale" transform="translate(${(vx + 6).toFixed(1)} ${(vy + vh - 6).toFixed(1)})"><path d="M0 0h20"/><path d="M0 -1.5v3M20 -1.5v3"/><text x="10" y="-3">20 mm</text></g>`;
  svg.innerHTML = `<defs><pattern id="rk-grid" width="10" height="10" patternUnits="userSpaceOnUse" x="0" y="0"><path d="M10 0H0V10" fill="none" class="rk-grid-line"/></pattern></defs><rect x="${vx - 2000}" y="${vy - 2000}" width="${vw + 4000}" height="${vh + 4000}" fill="url(#rk-grid)" data-sheet="1"/>
    ${limit ? `<rect class="rk-limit" x="${((x0 + x1) / 2 - limit[0] / 2).toFixed(1)}" y="${(-(y0 + y1) / 2 - limit[1] / 2).toFixed(1)}" width="${limit[0]}" height="${limit[1]}" rx="1"/>` : ''}
    ${fp ? `<rect class="rk-outline" x="${fp[0].toFixed(1)}" y="${(-fp[3]).toFixed(1)}" width="${(fp[2] - fp[0]).toFixed(1)}" height="${(fp[3] - fp[1]).toFixed(1)}" rx="${S.config.style === 'premium' ? (plan.corner_r || 0) : 6}"/>` : ''}
    <text class="rk-front" x="${((x0 + x1) / 2).toFixed(1)}" y="${(-y0 + room * .62).toFixed(1)}">Front of the rack</text>
    ${suggestion.map(([x, y, bore]) => `<circle class="rk-suggested" cx="${x + (S.suggestion.cx || 0)}" cy="${-(y + (S.suggestion.cy || 0))}" r="${(bore / 2).toFixed(1)}"/>`).join('')}
    ${tubes.map(t => {
      const family = familyOf(t.profile_id), state = errors.has(t.i) ? 'is-bad' : warnings.has(t.i) ? 'is-tight' : '', picked = S.selected.has(t.i) ? 'is-picked' : '';
      return `<g class="rk-pos ${state} ${picked}" data-i="${t.i}" transform="translate(${t.x.toFixed(2)} ${(-t.y).toFixed(2)})" style="--tube:${TUBE_COLORS[family]}" tabindex="0" role="button" aria-pressed="${S.selected.has(t.i)}" aria-label="Position ${t.i + 1}: ${esc(profile(t.profile_id).label)}, ${mm(t.x)} across, ${mm(t.y)} back${state === 'is-bad' ? ', has a problem' : ''}"><circle class="rk-pos-cap" r="${(t.cap / 2).toFixed(2)}"/><circle class="rk-pos-bore" r="${(t.bore / 2).toFixed(2)}"/>${number(t)}</g>`;
    }).join('')}${scaleBar}<g id="rk-guides"></g>`;
  // The drawing was just replaced: whoever was moving a position by keyboard keeps their place.
  if (focused !== undefined) q(`.rk-pos[data-i="${focused}"]`)?.focus({preventScroll: true});
  svg.classList.toggle('is-arming', !!S.armed);
  const size = q('#rk-edit-size'); if (size) size.textContent = plan?.dims ? `${Math.round(plan.dims[0])} × ${Math.round(plan.dims[1])} mm` : '';
  for (const chip of document.querySelectorAll('[data-arm]')) chip.setAttribute('aria-pressed', String(chip.dataset.arm === S.armed));
  drawNudge(); drawSuggestion(); updateHistoryButtons();
}
function drawNudge() {
  const pad = q('#rk-nudge'); if (!pad) return;
  pad.hidden = !S.selected.size;
  root().classList.toggle('has-selection', !!S.selected.size);
  q('#rk-edit-hint').hidden = !!S.selected.size || !!S.armed || !!S.suggestion;
  q('#rk-arm-hint').hidden = !S.armed;
  if (S.armed) q('#rk-arm-hint').textContent = `Click an empty place to add a ${Number(profile(S.armed).nominal_capacity_ml)} mL tube. Press Escape when you have finished.`;
  const count = q('#rk-picked'); if (count) count.textContent = S.selected.size === 1 ? `Position ${[...S.selected][0] + 1}` : `${S.selected.size} positions`;
  q('#rk-align').hidden = S.selected.size < 2;
  const same = q('#rk-select-same');
  if (same) { const first = S.config.layout.positions[[...S.selected][0]]; same.hidden = S.selected.size !== 1 || !first; if (first) same.textContent = `Select all ${Number(profile(first.profile_id).nominal_capacity_ml)} mL`; }
}
function svgPoint(event) {
  const svg = q('#rk-svg'), point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
  const p = point.matrixTransform(svg.getScreenCTM().inverse()); return {x: p.x, y: -p.y};
}
const snapped = value => Math.round(value * 2) / 2;
function moveSelected(dx, dy) {
  if (!S.selected.size) return;
  change(c => { for (const i of S.selected) { const p = c.layout.positions[i]; if (p) { p.x = Math.round((p.x + dx) * 10) / 10; p.y = Math.round((p.y + dy) * 10) / 10; } } });
  announce(`Moved to ${[...S.selected].map(i => `${mm(S.config.layout.positions[i].x)}, ${mm(S.config.layout.positions[i].y)}`).join('; ')}`);
}
function removeSelected() {
  if (!S.selected.size) return;
  const gone = new Set(S.selected); S.selected.clear();
  change(c => { c.layout.positions = c.layout.positions.filter((_, i) => !gone.has(i)); });
  announce(`${gone.size} position${gone.size > 1 ? 's' : ''} removed`);
}
function announce(text) { const node = q('#rk-live'); if (node) node.textContent = text; }
/* Alignment with the other tubes is what a person is after, so that is what a dragged tube snaps to. */
function alignTo(others, x, y) {
  const across = others.find(o => Math.abs(o.x - x) < 2), along = others.find(o => Math.abs(o.y - y) < 2);
  return {x: across ? across.x : snapped(x), y: along ? along.y : snapped(y), across, along};
}
function drawGuides(guides) {
  const host = q('#rk-guides'); if (!host) return;
  host.innerHTML = guides.map(g => `<line class="rk-guide" x1="${g[0]}" y1="${-g[1]}" x2="${g[2]}" y2="${-g[3]}"/>`).join('');
}
function startDrag(event) {
  const svg = q('#rk-svg'), g = event.target.closest('.rk-pos');
  if (!isManual()) return;
  if (!g) {
    if (S.armed) {
      const at = svgPoint(event), id = S.armed, others = planTubes(), spot = alignTo(others, at.x, at.y);
      change(c => c.layout.positions.push({profile_id: id, x: spot.x, y: spot.y}));
      announce(`${profile(id).label} added`);
      return;
    }
    // On a free part of the sheet: drag a box to select several. A finger scrolls the page instead.
    if (event.pointerType === 'touch') { if (S.selected.size) { S.selected.clear(); drawPlan(); } return; }
    drag = {box: svgPoint(event), moved: false};
    svg.setPointerCapture(event.pointerId); event.preventDefault();
    return;
  }
  const i = Number(g.dataset.i);
  if (event.shiftKey || event.ctrlKey || event.metaKey) { S.selected.has(i) ? S.selected.delete(i) : S.selected.add(i); drawPlan(); return; }
  if (!S.selected.has(i)) { S.selected.clear(); S.selected.add(i); drawPlan(); }
  const start = svgPoint(event), before = JSON.stringify(S.config);
  drag = {start, before, moved: false, origin: new Map([...S.selected].map(n => [n, {...S.config.layout.positions[n]}])), tubes: planTubes(), swap: null};
  svg.setPointerCapture(event.pointerId);
  svg.classList.add('is-dragging');
  event.preventDefault();
}
function moveDrag(event) {
  if (!drag) { showGhost(event); return; }
  const at = svgPoint(event);
  if (drag.box) {
    drag.moved = true;
    const a = drag.box, host = q('#rk-guides');
    if (host) host.innerHTML = `<rect class="rk-marquee" x="${Math.min(a.x, at.x)}" y="${-Math.max(a.y, at.y)}" width="${Math.abs(at.x - a.x)}" height="${Math.abs(at.y - a.y)}"/>`;
    drag.end = at;
    return;
  }
  const dx = at.x - drag.start.x, dy = at.y - drag.start.y;
  if (!drag.moved && Math.hypot(dx, dy) < 1) return;
  drag.moved = true;
  const single = drag.origin.size === 1, guides = [];
  document.querySelectorAll('.rk-pos.is-swap').forEach(el => el.classList.remove('is-swap'));
  drag.swap = null;
  for (const [n, from] of drag.origin) {
    const p = S.config.layout.positions[n], tube = drag.tubes.find(t => t.i === n);
    let x = from.x + dx, y = from.y + dy;
    if (single) {
      const others = drag.tubes.filter(t => t.i !== n);
      // Dropped well inside another tube, the two change places.
      const target = others.find(o => Math.hypot(o.x - x, o.y - y) < Math.max(o.bore * .3, 3.5));
      if (target) { drag.swap = target.i; x = target.x; y = target.y; q(`.rk-pos[data-i="${target.i}"]`)?.classList.add('is-swap'); }
      else {
        const spot = alignTo(others, x, y);
        x = spot.x; y = spot.y;
        if (spot.across) guides.push([x, Math.min(y, spot.across.y) - 40, x, Math.max(y, spot.across.y) + 40]);
        if (spot.along) guides.push([Math.min(x, spot.along.x) - 40, y, Math.max(x, spot.along.x) + 40, y]);
      }
    } else { x = snapped(x); y = snapped(y); }
    p.x = x; p.y = y; tube.x = x; tube.y = y;
    q(`.rk-pos[data-i="${n}"]`)?.setAttribute('transform', `translate(${x.toFixed(2)} ${(-y).toFixed(2)})`);
  }
  drawGuides(guides);
  const bad = drag.swap === null ? livePairs(drag.tubes) : new Set();
  document.querySelectorAll('.rk-pos').forEach(el => el.classList.toggle('is-bad', bad.has(Number(el.dataset.i))));
  showOutline(drag.tubes);
}
function endDrag() {
  if (!drag) return;
  const was = drag; drag = null;
  q('#rk-svg').classList.remove('is-dragging');
  drawGuides([]);
  if (was.box) {
    if (was.moved && was.end) {
      const [a, b] = [was.box, was.end], x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
      S.selected = new Set(planTubes().filter(t => t.x >= x0 && t.x <= x1 && t.y >= y0 && t.y <= y1).map(t => t.i));
      if (S.selected.size) announce(`${S.selected.size} positions selected`);
    } else S.selected.clear();
    drawPlan(); return;
  }
  if (was.moved) {
    if (was.swap !== null) {
      const [n, from] = [...was.origin][0], other = S.config.layout.positions[was.swap], taken = {x: other.x, y: other.y};
      other.x = from.x; other.y = from.y; const p = S.config.layout.positions[n]; p.x = taken.x; p.y = taken.y;
      announce(`Positions ${n + 1} and ${was.swap + 1} changed places`);
    }
    S.undo.push(was.before); if (S.undo.length > HISTORY) S.undo.shift(); S.redo = []; afterChange();
  }
  else drawPlan();
}
/* A tube about to be placed shows where it would go, and whether it would fit there. */
function showGhost(event) {
  const host = q('#rk-guides'); if (!host) return;
  if (!S.armed || event.pointerType === 'touch') { if (host.firstChild) host.innerHTML = ''; return; }
  const at = svgPoint(event), info = profile(S.armed), others = planTubes(), spot = alignTo(others, at.x, at.y);
  const me = {x: spot.x, y: spot.y, bore: info.body_diameter_mm + info.recommended_clearance_mm, cap: info.cap_diameter_mm};
  const bad = others.some(o => conflicts(me, o));
  host.innerHTML = `<circle class="rk-ghost ${bad ? 'is-bad' : ''}" cx="${spot.x}" cy="${-spot.y}" r="${(me.bore / 2).toFixed(1)}"/>`;
}
function planKey(event) {
  const g = event.target.closest?.('.rk-pos');
  if (!g || !isManual()) return;
  const i = Number(g.dataset.i), step = event.shiftKey ? 5 : 1;
  const move = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step]}[event.key];
  if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); S.selected.has(i) ? S.selected.delete(i) : S.selected.add(i); drawPlan(); q(`.rk-pos[data-i="${i}"]`)?.focus(); }
  else if (move) { event.preventDefault(); if (!S.selected.has(i)) { S.selected.clear(); S.selected.add(i); } moveSelected(...move); requestAnimationFrame(() => q(`.rk-pos[data-i="${i}"]`)?.focus()); }
  else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); if (!S.selected.has(i)) { S.selected.clear(); S.selected.add(i); } removeSelected(); }
}
function alignSelected(axis) {
  const picked = [...S.selected].map(i => S.config.layout.positions[i]);
  const value = picked.reduce((sum, p) => sum + p[axis], 0) / picked.length;
  change(c => { for (const i of S.selected) c.layout.positions[i][axis] = Math.round(value * 2) / 2; });
}
function setEditing(on) {
  S.editing = on;
  root().classList.toggle('is-editing', on);
  q('#rk-view-plan').hidden = !on;
  root().classList.remove('show-model');
  // The same live model moves beside the sheet: nothing is reloaded, and it never covers a tube.
  const model = q('#rk-view-3d');
  if (on) q('#rk-edit-rail').prepend(model); else q('.rk-stage').prepend(model);
  if (on) { drawPlan(); q('.rk-stage').scrollIntoView({block: 'nearest'}); q('#rk-edit-title').focus({preventScroll: true}); announce('Editing the layout. Your rack stays in view in 3D.'); }
  else { S.selected.clear(); S.armed = ''; S.suggestion = null; }
  applyDevice();
  drawBuildState(); updateActions();
}
/* Editing starts from the rack as it is now, even if a change is still on its way to the planner. */
async function openEditor() {
  if (isManual()) { S.editBase = null; setEditing(true); return; }
  // A quantity still on its short timer counts: the editor opens on what the buyer last typed.
  for (const family of Object.keys(countTimers)) { clearTimeout(countTimers[family]); delete countTimers[family]; setCount(family, q(`input[data-count="${family}"]`).value); }
  let plan = S.plan;
  try { plan = await api('/racks/plan', {method: 'POST', body: JSON.stringify(S.config)}); } catch (e) {}
  if (!root() || !plan?.tubes?.length) { if (plan) toast('Add a tube first, then you can arrange it.'); return; }
  const offset = plan.offset || [0, 0];
  const positions = plan.tubes.map(t => ({profile_id: t.profile_id, x: t.x + offset[0], y: t.y + offset[1]}));
  S.editBase = JSON.stringify(S.config);
  S.editing = true;      // before the change, so that it does not start a build
  change(c => { c.layout.mode = 'manual'; c.layout.positions = positions; });
  S.editStart = JSON.stringify(S.config.layout.positions);
  setEditing(true);
}
/* Done. Opening the editor and changing nothing leaves the rack arranged automatically. */
function finishEditing() {
  const untouched = S.editBase && JSON.stringify(S.config.layout.positions) === S.editStart;
  if (untouched) { const finish = {material: S.material, color: S.color}; S.config = JSON.parse(S.editBase); S.config.material = finish.material; S.config.color = finish.color; S.undo.pop(); }
  S.editBase = null;
  setEditing(false);
  S.stale = true; saveDraft(); syncControls(); drawShelf(); drawAdvancedState(); updateHistoryButtons(); drawBuildState(); requestPlan();
}
function goAutomatic() {
  const counts = {};
  for (const p of S.config.layout.positions) counts[p.profile_id] = (counts[p.profile_id] || 0) + 1;
  S.selected.clear(); S.armed = ''; S.suggestion = null; S.editBase = null;
  if (S.editing) setEditing(false);
  change(c => { c.layout.mode = 'auto'; c.layout.positions = []; c.tubes = Object.entries(counts).map(([profile_id, quantity]) => ({profile_id, quantity})); });
  announce('Arranged automatically again.');
}
/* Asks the layout engine for its own answer and shows it as a suggestion: a hand-made layout is never replaced without asking. */
async function suggestLayout() {
  const counts = {};
  for (const p of S.config.layout.positions) counts[p.profile_id] = (counts[p.profile_id] || 0) + 1;
  const auto = clone(S.config);
  auto.layout.mode = 'auto'; auto.layout.positions = []; auto.tubes = Object.entries(counts).map(([profile_id, quantity]) => ({profile_id, quantity}));
  try {
    const plan = await api('/racks/plan', {method: 'POST', body: JSON.stringify(auto)});
    if (!plan.tubes?.length) { toast(plan.issues?.[0]?.message || 'There is nothing to arrange yet.'); return; }
    const mine = S.plan?.dims, offset = plan.offset || [0, 0], here = S.plan?.offset || [0, 0];
    const areaNow = mine ? mine[0] * mine[1] : 0, areaThen = plan.dims[0] * plan.dims[1], change_ = areaNow ? Math.round((1 - areaThen / areaNow) * 100) : 0;
    const why = change_ > 1 ? `${change_}% smaller than yours` : change_ < -1 ? `${-change_}% larger than yours, with tidier rows` : 'about the same size, with tidier rows';
    S.suggestion = {positions: plan.tubes.map(t => ({profile_id: t.profile_id, x: t.x + offset[0], y: t.y + offset[1]})), tubes: plan.tubes.map(t => [t.x, t.y, t.bore_d]), cx: here[0], cy: here[1], text: `A suggested layout is ${Math.round(plan.dims[0])} × ${Math.round(plan.dims[1])} mm, ${why}.`, tubesConfig: auto.tubes};
    drawPlan();
  } catch (e) { toast(e.message); }
}
function drawSuggestion() {
  const host = q('#rk-suggest'); if (!host) return;
  host.hidden = !S.suggestion;
  if (S.suggestion) q('#rk-suggest-text').textContent = S.suggestion.text;
}
function useSuggestion() {
  const next = S.suggestion; S.suggestion = null; S.selected.clear();
  change(c => { c.tubes = next.tubesConfig; c.layout.positions = next.positions; });
  announce('Suggested layout applied. Undo brings yours back.');
}

/* ---- The page ---- */
const options = (list, selected = '') => list.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(selected) ? 'selected' : ''}>${esc(l)}</option>`).join('');
function pageHtml() {
  const familyLabel = {'conical-50': ['50 mL', 'conical'], 'conical-15': ['15 mL', 'conical'], 'micro-1.5': ['1.5 mL', 'micro'], 'micro-0.5': ['0.5 mL', 'micro']};
  const shelf = catalog.families.map(f => { const [size, kind] = familyLabel[f.id] || [f.label, '']; return `<div class="rk-cell" data-family="${f.id}"><div class="rk-figure"></div><label for="rk-count-${domId(f.id)}"><strong>${esc(size)}</strong> <span>${esc(kind)}</span></label><div class="rk-stepper"><button type="button" data-step="-1" aria-label="One fewer ${esc(f.label)} tube">−</button><input id="rk-count-${domId(f.id)}" data-count="${f.id}" type="number" inputmode="numeric" min="0" max="${catalog.max_tubes}" step="1" autocomplete="off"><button type="button" data-step="1" aria-label="One more ${esc(f.label)} tube">+</button></div></div>`; }).join('');
  const sizes = catalog.families.map(f => {
    const models = catalog.profiles.filter(p => p.family === f.id);
    return `<fieldset class="rk-size-row"><legend>${esc(f.label)}</legend><label>Tube<select id="rk-model-${domId(f.id)}" data-model="${f.id}">${models.map(p => `<option value="${p.id}">${esc(p.manufacturer === 'Generic' ? 'Typical tube' : p.model)}</option>`).join('')}</select></label><div class="rk-size-fields"><label>Body Ø <span class="rk-quiet">mm</span><input id="rk-body_diameter_mm-${domId(f.id)}" data-override="body_diameter_mm" data-family="${f.id}" type="number" step="0.1" inputmode="decimal" autocomplete="off"></label><label>Cap Ø <span class="rk-quiet">mm</span><input id="rk-cap_diameter_mm-${domId(f.id)}" data-override="cap_diameter_mm" data-family="${f.id}" type="number" step="0.1" inputmode="decimal" autocomplete="off"></label><label>Length <span class="rk-quiet">mm</span><input id="rk-overall_length_mm-${domId(f.id)}" data-override="overall_length_mm" data-family="${f.id}" type="number" step="0.5" inputmode="decimal" autocomplete="off"></label></div><p class="rk-note" id="rk-source-${domId(f.id)}"></p></fieldset>`;
  }).join('');
  const styleCard = (value, title, text) => `<label class="rk-style"><input type="radio" name="rk-style" value="${value}"><span><img src="assets/products/rack-style-${value}.webp?v=3" alt="" width="320" height="240" decoding="async"><strong>${title}</strong><small>${text}</small></span></label>`;
  return `<div id="rk-root" class="rk">
  <header class="rk-head"><div><h1>Design your rack</h1><p>A rack built around your experiment. Choose your tubes and a style, and the software works out the rest.</p></div>
    <div class="rk-presets" role="group" aria-label="Start from an example">${catalog.presets.map(p => `<button type="button" data-preset="${p.id}"><strong>${esc(p.name)}</strong><small>${esc(p.summary)}</small></button>`).join('')}</div></header>
  <div class="rk-work">
   <form class="rk-sheet" id="rk-form" novalidate>
    <section aria-labelledby="rk-h-tubes"><div class="rk-section-head"><h2 id="rk-h-tubes">Your tubes</h2><span id="rk-total" class="rk-quiet"></span></div>
      <div class="rk-shelf" id="rk-shelf">${shelf}</div>
</section>
    <section aria-labelledby="rk-h-design"><h2 id="rk-h-design">Design</h2>
      <div class="rk-styles">${styleCard('lightweight', 'Lightweight', 'Less material, open structure.')}${styleCard('premium', 'Premium', 'A soft, full body with smooth edges.')}</div></section>
    <section aria-labelledby="rk-h-layout" id="rk-layout-section"><div class="rk-section-head"><h2 id="rk-h-layout">Layout</h2><span id="rk-layout-size" class="rk-quiet"></span></div>
      <div id="rk-layouts"></div>
      <div class="rk-layout-actions"><button type="button" class="btn-ghost" id="rk-edit-layout">Edit layout</button><button type="button" class="link-button" id="rk-auto-layout" hidden>Back to automatic</button></div></section>
    <section aria-labelledby="rk-h-height" id="rk-height-section"><div class="rk-section-head"><h2 id="rk-h-height"><label for="rk-height">Rack height</label></h2><label class="rk-height-value"><span class="sr-only">Rack height in millimetres</span><input id="rk-height-mm" type="number" step="0.5" inputmode="decimal" autocomplete="off"><span aria-hidden="true">mm</span></label></div>
      <div class="rk-height-track" id="rk-height-track"><input id="rk-height" class="rk-height" type="range" step="0.5"><i id="rk-height-mark" title="Recommended"></i></div>
      <div class="rk-height-scale" id="rk-height-scale"><span id="rk-height-low"></span><span id="rk-height-high"></span></div>
      <p class="rk-note" id="rk-height-note" aria-live="polite"></p><button type="button" id="rk-height-reset" class="link-button rk-height-reset" hidden></button></section>
    <nav class="rk-rows" aria-label="More options">
      <button type="button" data-sheet="rk-layout-section" data-sheet-title="Layout"><span>Layout</span><b id="rk-row-layout"></b></button>
      <button type="button" data-sheet="rk-label-section" data-sheet-title="Laboratory name"><span>Laboratory name</span><b id="rk-row-name"></b></button>
      <button type="button" data-sheet="rk-finish-section" data-sheet-title="Material and colour"><span>Material and colour</span><b><i id="rk-row-swatch" hidden></i><span id="rk-row-finish"></span></b></button>
      <button type="button" data-sheet="rk-advanced-section" data-sheet-title="Advanced options"><span>Advanced options</span><b id="rk-row-advanced"></b></button>
      <button type="button" data-sheet="rk-check-section" data-sheet-title="Review"><span>Review and save</span><b id="rk-row-review"></b></button>
    </nav>
    <section aria-labelledby="rk-h-label" id="rk-label-section"><h2 id="rk-h-label"><label for="rk-text">Laboratory name</label> <span class="rk-quiet">optional</span></h2>
      <input id="rk-text" name="rack-label" type="text" maxlength="${catalog.text.max_chars}" placeholder="Molecular Biology Lab…" autocomplete="off" spellcheck="false">
      <fieldset class="rk-segmented" id="rk-label-style-row" hidden><legend class="sr-only">Letters are</legend><label><input type="radio" name="rk-label-style" value="engraved"><span>Engraved</span></label><label><input type="radio" name="rk-label-style" value="embossed"><span>Raised</span></label></fieldset></section>
    <section aria-labelledby="rk-h-finish" id="rk-finish-section"><h2 id="rk-h-finish">Material and colour</h2><div id="rk-finish"></div></section>
    <section class="rk-advanced-wrap" id="rk-advanced-section">
      <button type="button" class="rk-advanced-toggle" id="rk-advanced-toggle" aria-expanded="false" aria-controls="rk-advanced"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M5 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span>Advanced options</span><small id="rk-advanced-changed" class="rk-quiet"></small></button>
      <div id="rk-advanced" class="rk-advanced" hidden>
        <fieldset class="rk-group" id="rk-auto-options"><legend>Automatic layout</legend>
          <fieldset class="rk-inline"><legend>Tube spacing</legend><div class="rk-segmented-row">${SPACINGS.map(([v, l]) => `<label><input type="radio" name="rk-spacing" value="${v}"><span>${l}</span></label>`).join('')}</div></fieldset>
          <fieldset class="rk-inline"><legend>Orientation</legend><div class="rk-segmented-row">${ORIENTATIONS.map(([v, l, d]) => `<label><input type="radio" name="rk-orientation" value="${v}"><span>${d ? `<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="${d}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>` : ''}${l}</span></label>`).join('')}</div></fieldset>
          <label class="rk-field rk-narrow">Tubes per row<input id="rk-columns" type="number" min="1" max="60" inputmode="numeric" autocomplete="off" placeholder="Automatic"></label></fieldset>
        <fieldset class="rk-group"><legend>Size</legend>
          <label class="rk-field">Available printing area<select id="rk-envelope"></select></label><p class="rk-note" id="rk-envelope-note"></p>
          <label class="rk-field rk-narrow"><span>Extra margin <span class="rk-quiet">mm</span></span><input id="rk-margin" type="number" min="0" max="15" step="1" inputmode="numeric" autocomplete="off"></label></fieldset>
        <fieldset class="rk-group"><legend>Tube sizes and fit</legend>
          <p class="rk-note">Sizes are typical and vary between makers. Compare yours before relying on the fit.</p>
          <label class="rk-field">Fit in the hole<select id="rk-clearance">${options(CLEARANCES.map(([v, l]) => [String(v), l]))}</select></label>
          <details class="rk-more"><summary>Tube profiles and dimensions</summary>${sizes}</details></fieldset>
        <fieldset class="rk-group" id="rk-geometry-group"><legend>Edges</legend>
          <p class="rk-note" id="rk-edge-empty">Lightweight racks have a fixed structure. Edge options apply to Premium.</p>
          <div class="rk-choice-row" id="rk-edge-row" role="radiogroup" aria-label="Edges" hidden>${EDGES.map(([v, l]) => `<label class="rk-chip"><input type="radio" name="rk-edge" value="${v}"><span><strong>${l}</strong></span></label>`).join('')}</div>
          <label class="rk-field rk-narrow" id="rk-corner-row" hidden><span>Corner radius <span class="rk-quiet">mm</span></span><input id="rk-corner" type="number" min="0" max="60" step="0.5" inputmode="decimal" autocomplete="off" placeholder="Automatic"></label></fieldset>
        <fieldset class="rk-group"><legend>Name lettering</legend>
          <p class="rk-note" id="rk-label-options-empty">Add a laboratory name to set its placement and lettering.</p>
          <div id="rk-label-options" class="rk-fields" hidden><label class="rk-field">Where<select id="rk-face">${options(FACES)}</select></label><label class="rk-field">Lettering<select id="rk-font">${options(catalog.fonts.map(f => [f.id, f.label]))}</select></label><label class="rk-field">Size<select id="rk-size">${options(SIZES)}</select></label></div></fieldset>
        <fieldset class="rk-group"><legend>Preview</legend><label class="rk-toggle"><input type="checkbox" id="rk-show-guides"> Show dimensions on the model</label></fieldset>
        <details class="rk-more rk-list"><summary>Positions as a list</summary><div class="rk-table-wrap" tabindex="0" role="region" aria-label="Positions as a list"><table id="rk-positions"><thead><tr><th scope="col">#</th><th scope="col">Tube</th><th scope="col">Across (mm)</th><th scope="col">Back (mm)</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead><tbody></tbody></table></div></details>
        <div class="rk-reset"><button type="button" class="btn-ghost" id="rk-reset-advanced">Reset advanced settings</button><span class="rk-note">Your tubes, style and name stay as they are.</span></div>
      </div></section>
    <section aria-labelledby="rk-h-check" id="rk-check-section"><h2 id="rk-h-check">Before you order</h2><dl class="rk-metrics rk-review-metrics" id="rk-review-metrics"></dl><p class="rk-prototype">Prototype design: tube dimensions are based on preliminary profiles and have not yet been physically validated.</p><div id="rk-report" class="rk-report"></div>
      <label class="rk-field rk-name"><span>Name this design <span class="rk-quiet">optional</span></span><input id="rk-name" name="design-name" type="text" maxlength="80" placeholder="Named for you when saved…" autocomplete="off"></label><button type="button" class="btn-ghost rk-save-inline" data-act="save">Save design</button></section>
   </form>
   <div class="rk-right">
    <div class="rk-stage">
     <div id="rk-view-3d" class="rk-panel">
       <div class="rk-viewport"><div id="rk-canvas" class="rk-canvas"></div>
         <span id="rk-state" class="rk-state is-working" role="status"></span>
         <div class="rk-tools rk-viewtools" role="group" aria-label="3D view"><button type="button" data-view="iso">Angled</button><button type="button" data-view="top">Top</button><button type="button" data-view="front" class="rk-adv-only">Front</button><button type="button" data-view="iso" aria-label="Reset view">Reset</button><label class="rk-toggle"><input type="checkbox" id="rk-show-tubes"> Tubes</label><button type="button" id="rk-fullscreen" class="rk-end"><span class="rk-for-wide">Full screen</span><span class="rk-for-phone">Expand</span></button></div></div>
       <button type="button" class="rk-strip" id="rk-strip" data-sheet="rk-check-section" data-sheet-title="Review"><span id="rk-strip-size"></span><b id="rk-strip-state"></b></button>
     </div>
     <section id="rk-view-plan" class="rk-editor" aria-labelledby="rk-edit-title" hidden>
       <header class="rk-edit-head"><h2 id="rk-edit-title" tabindex="-1">Edit layout <span class="rk-quiet" id="rk-edit-size"></span></h2><button type="button" class="rk-edit-3d" id="rk-edit-3d" aria-pressed="false">3D</button><button type="button" class="btn rk-done" id="rk-done">Done<span class="rk-for-wide"> editing</span></button></header>
       <div class="rk-edit-bar">
         <div class="rk-add-row" role="group" aria-label="Add a tube"><span>Add</span>${catalog.families.map(f => `<button type="button" class="rk-add-chip" data-arm="${profileOfDefault(f.id)}" aria-pressed="false" style="--tube:${TUBE_COLORS[f.id]}"><i></i>${esc(f.label.split(' ').slice(0, 2).join(' '))}</button>`).join('')}</div>
         <div class="rk-edit-actions"><button type="button" data-act="undo" aria-label="Undo">Undo</button><button type="button" data-act="redo" aria-label="Redo">Redo</button><button type="button" data-act="optimize">Suggest<span class="rk-for-wide"> a layout</span></button><button type="button" class="link-button" data-act="automatic"><span class="rk-for-wide">Back to automatic</span><span class="rk-for-phone">Automatic</span></button></div>
       </div>
       <div class="rk-sheet-wrap">
         <svg id="rk-svg" class="rk-svg is-manual" role="group" aria-label="Top view of the rack. Each circle is one tube position at its real size." preserveAspectRatio="xMidYMid meet"></svg>
         <div class="rk-rail" id="rk-edit-rail">
           <div id="rk-nudge" class="rk-nudge" hidden><span id="rk-picked" class="rk-picked"></span><div class="rk-pad" role="group" aria-label="Move selected positions"><button type="button" data-move="0,1" aria-label="Move back">↑</button><button type="button" data-move="-1,0" aria-label="Move left">←</button><button type="button" data-move="1,0" aria-label="Move right">→</button><button type="button" data-move="0,-1" aria-label="Move forward">↓</button></div><span id="rk-align" hidden><button type="button" data-align="x">Line up in a row</button><button type="button" data-align="y">Line up in a column</button></span><button type="button" id="rk-select-same"></button><button type="button" class="danger-text" data-act="remove">Remove</button></div>
           <p class="rk-note" id="rk-edit-hint"><span class="rk-for-mouse">Drag a tube to move it, or onto another to swap them. Shift-click, or drag across empty space, to select several.</span><span class="rk-for-touch">Tap a tube, then use the arrows to move it.</span></p>
           <p class="rk-note" id="rk-arm-hint" hidden></p>
           <div class="rk-suggest" id="rk-suggest" hidden><span id="rk-suggest-text"></span><div><button type="button" class="btn-ghost" data-act="use-suggestion">Use it</button> <button type="button" class="link-button" data-act="keep-mine">Keep mine</button></div></div>
         </div>
       </div>
     </section>
     <div id="rk-problems" class="rk-problems" aria-live="polite"></div>
    </div>
    <dl class="rk-metrics" id="rk-metrics"></dl>
    <p id="rk-summary" class="sr-only" role="status"></p>
   </div>
  </div>
  <div class="rk-bar"><div class="rk-bar-inner"><div class="rk-bar-price" data-basis="estimate"><strong id="rk-bar-price">—</strong><small id="rk-bar-basis">estimate</small></div><div class="rk-bar-note"><span id="rk-why"></span><span id="rk-add-error" role="alert"></span></div><label class="rk-qty"><span>Quantity</span><input id="rk-quantity" name="quantity" type="number" min="1" max="20" value="1" inputmode="numeric" autocomplete="off"></label><button type="button" class="btn-ghost rk-save" id="rk-save"><span id="rk-save-label">${S.design ? 'Save changes' : 'Save design'}</span></button><button type="button" class="purchase-button purchase-button-secondary rk-add" id="rk-add" aria-describedby="rk-why"><span class="purchase-icon">${icon('cart')}</span><span>Add to basket</span></button><button type="button" class="purchase-button purchase-button-primary rk-buy" id="rk-buy" aria-describedby="rk-why"><span>Buy now</span></button></div></div>
  <div id="rk-live" class="sr-only" aria-live="polite"></div>
  <dialog class="rk-bs" id="rk-bs" aria-labelledby="rk-bs-title"><header class="rk-bs-head" id="rk-bs-head"><i aria-hidden="true"></i><h2 id="rk-bs-title"></h2><button type="button" class="link-button" id="rk-bs-close">Done</button></header><div class="rk-bs-body" id="rk-bs-body"></div></dialog>
  <dialog class="rk-focus" id="rk-focus" aria-label="3D model of your rack"><button type="button" class="rk-focus-close" id="rk-focus-close">Close</button></dialog>
 </div>`;
}
function profileOfDefault(family) { return catalog.families.find(f => f.id === family).default; }

function bindPage() {
  const page = root();
  page.addEventListener('click', onClick);
  page.addEventListener('input', onInput);
  page.addEventListener('change', onChangeEvent);
  document.addEventListener('keydown', onUndoKey);     // also when focus has fallen back to the page itself
  q('#rk-form').addEventListener('submit', e => e.preventDefault());
  const svg = q('#rk-svg');
  svg.addEventListener('pointerdown', startDrag); svg.addEventListener('pointermove', moveDrag); svg.addEventListener('pointerup', endDrag); svg.addEventListener('pointercancel', endDrag); svg.addEventListener('keydown', planKey);
  svg.addEventListener('pointerleave', () => { if (!drag) { const host = q('#rk-guides'); if (host) host.innerHTML = ''; } });
  document.addEventListener('keydown', onEditorKey);
  PHONE.addEventListener('change', applyDevice); LANDSCAPE.addEventListener('change', applyDevice);
  const sheet = q('#rk-bs'), focus = q('#rk-focus');
  sheet.addEventListener('close', sheetClosed); focus.addEventListener('close', focusClosed);
  sheet.addEventListener('click', event => { if (event.target === sheet) closeSheet(); });
  bindSheetSwipe();
  q('.rk-viewport').addEventListener('click', event => { if (PHONE.matches && !focus.open && !S.editing && !event.target.closest('button, label')) openFocus(); });
  page.addEventListener('focusin', event => { if (event.target.matches('input[type=text], input[type=number]')) page.classList.add('is-typing'); });
  page.addEventListener('focusout', () => page.classList.remove('is-typing'));
  q('#rk-add').addEventListener('click', addToCart);
  q('#rk-buy').addEventListener('click', buyNow);
  q('#rk-save').addEventListener('click', saveDesign);
}
/* Pull the sheet down by its heading to dismiss it. */
function bindSheetSwipe() {
  const head = q('#rk-bs-head'), sheet = q('#rk-bs'); let start = null;
  head.addEventListener('pointerdown', e => { if (e.target.closest('button')) return; start = e.clientY; head.setPointerCapture(e.pointerId); });
  head.addEventListener('pointermove', e => { if (start !== null) sheet.style.transform = `translateY(${Math.max(0, e.clientY - start)}px)`; });
  const end = e => { if (start === null) return; const moved = e.clientY - start; start = null; sheet.style.transform = ''; if (moved > 70) closeSheet(); };
  head.addEventListener('pointerup', end); head.addEventListener('pointercancel', end);
}
function onClick(event) {
  const t = event.target.closest('button'); if (!t) return;
  if (t.dataset.sheet) { openSheet(t.dataset.sheet, t.dataset.sheetTitle); return; }
  if (t.id === 'rk-bs-close') { closeSheet(); return; }
  if (t.id === 'rk-focus-close') { q('#rk-focus').close(); return; }
  if (t.id === 'rk-edit-3d') {
    const on = root().classList.toggle('show-model'); t.setAttribute('aria-pressed', String(on)); t.textContent = on ? 'Top view' : '3D';
    if (!on) drawPlan();
    applyDevice(); return;
  }
  if (t.dataset.step) { const cell = t.closest('[data-family]'); setCount(cell.dataset.family, countOf(cell.dataset.family) + Number(t.dataset.step)); return; }
  if (t.dataset.preset) {
    const preset = catalog.presets.find(p => p.id === t.dataset.preset);
    const next = freshConfig(preset.tubes, preset.style);
    delete next.label;     // the lab name stays: a preset is about tubes, not whose rack it is
    S.selected.clear();
    change(c => Object.assign(c, next));
    announce(`Started from ${preset.name}`);
    return;
  }
  if (t.dataset.issueKind) {
    if (t.dataset.issueKind === 'height') setHeight(Number(t.dataset.issueValue));
    else if (t.dataset.issueKind === 'layout') setLayoutPreference(t.dataset.issueValue);
    return;
  }
  if (t.dataset.arm) { S.armed = S.armed === t.dataset.arm ? '' : t.dataset.arm; S.selected.clear(); drawPlan(); if (S.armed) announce(q('#rk-arm-hint').textContent); return; }
  if (t.id === 'rk-edit-layout') { closeSheet(); openEditor(); return; }
  if (t.id === 'rk-auto-layout') { closeSheet(); goAutomatic(); return; }
  if (t.id === 'rk-done') { finishEditing(); q('#rk-edit-layout')?.focus({preventScroll: true}); return; }
  if (t.id === 'rk-height-reset') { setHeight(null); S.heightEdit = false; return; }
  if (t.id === 'rk-select-same') { const first = S.config.layout.positions[[...S.selected][0]]; if (first) { S.selected = new Set(S.config.layout.positions.flatMap((p, i) => familyOf(p.profile_id) === familyOf(first.profile_id) ? [i] : [])); drawPlan(); announce(`${S.selected.size} positions selected`); } return; }
  if (t.dataset.view) { S.viewer?.view(t.dataset.view); return; }
  if (t.dataset.move) { const [x, y] = t.dataset.move.split(',').map(Number); moveSelected(x * 2.5, y * 2.5); return; }
  if (t.dataset.align) { alignSelected(t.dataset.align === 'x' ? 'y' : 'x'); return; }
  if (t.dataset.remove !== undefined) { S.selected = new Set([Number(t.dataset.remove)]); removeSelected(); return; }
  if (t.id === 'rk-fullscreen') { toggleFullscreen(); return; }
  if (t.id === 'rk-advanced-toggle') { setAdvanced(!S.advanced); return; }
  if (t.id === 'rk-reset-advanced') { resetAdvanced(); return; }
  const act = t.dataset.act;
  if (act === 'undo') restore(S.undo, S.redo);
  else if (act === 'redo') restore(S.redo, S.undo);
  else if (act === 'save') saveDesign();
  else if (act === 'optimize') suggestLayout();
  else if (act === 'use-suggestion') useSuggestion();
  else if (act === 'keep-mine') { S.suggestion = null; drawPlan(); }
  else if (act === 'automatic') goAutomatic();
  else if (act === 'remove') removeSelected();
}
function toggleFullscreen() {
  if (PHONE.matches) { const focus = q('#rk-focus'); if (focus.open) focus.close(); else openFocus(); return; }
  const panel = q('#rk-view-3d');
  if (document.fullscreenElement) { document.exitFullscreen(); return; }
  if (panel.requestFullscreen) panel.requestFullscreen().then(() => S.viewer?.resize()).catch(() => panel.classList.toggle('is-expanded'));
  else panel.classList.toggle('is-expanded');
  setTimeout(() => S.viewer?.resize(), 80);
}
let textTimer = 0; const countTimers = {};
function setLabel(patch) {
  change(c => { c.label = {text: '', font: 'sans', size_mm: null, position: 'front', style: 'engraved', ...(c.label || {}), ...patch}; });
}
function onInput(event) {
  const el = event.target;
  if (el.id === 'rk-height') {
    // The slider moves the rack as it goes. One undo step for the whole movement.
    S.heightBefore ||= JSON.stringify(S.config); S.heightDragging = true; S.heightEdit = true;
    S.config.height_mm = Number(el.value); q('#rk-height-mm').value = el.value; fillSlider();
    S.stale = true; saveDraft(); schedulePlan(); drawBuildState();
    return;
  }
  if (el.dataset.count) {     // each field on its own timer: changing two quickly must not lose the first
    const family = el.dataset.count; clearTimeout(countTimers[family]);
    countTimers[family] = setTimeout(() => { delete countTimers[family]; setCount(family, el.value); }, 180);
  }
  else if (el.id === 'rk-text') {
    clearTimeout(textTimer); textTimer = setTimeout(() => setLabel({text: el.value.replace(/\s+/g, ' ').replace(/^\s/, '')}), 220);
  }
  else if (el.dataset.coord && el.value !== '') {
    const i = Number(el.dataset.i), value = Number(el.value);
    if (Number.isFinite(value)) { clearTimeout(textTimer); textTimer = setTimeout(() => change(c => { if (c.layout.positions[i]) c.layout.positions[i][el.dataset.coord] = value; }), 300); }
  }
  else if (el.id === 'rk-name') S.name = el.value;
}
function onChangeEvent(event) {
  const el = event.target, name = el.name, id = el.id;
  if (id === 'rk-height') { if (S.heightBefore) { S.undo.push(S.heightBefore); if (S.undo.length > HISTORY) S.undo.shift(); S.redo = []; S.heightBefore = null; updateHistoryButtons(); } S.heightDragging = false; }
  else if (id === 'rk-height-mm') setHeight(el.value === '' ? null : Number(el.value));
  else if (name === 'rk-layout') setLayoutPreference(el.value);
  else if (name === 'rk-spacing') change(c => { c.layout.spacing = el.value; });
  else if (name === 'rk-orientation') change(c => { c.layout.orientation = el.value; });
  else if (name === 'rk-style') change(c => { c.style = el.value; });
  else if (name === 'rk-edge') change(c => { c.edge = el.value; });
  else if (name === 'rk-label-style') setLabel({style: el.value});
  else if (name === 'rk-material') { const colors = offered()[el.value]?.colors || {}; setFinish(el.value, colors[S.color] ? S.color : readableColor(colors)); q(`input[name=rk-material][value="${CSS.escape(S.material)}"]`)?.focus(); }
  else if (name === 'rk-color') { setFinish(S.material, el.value); q(`input[name=rk-color][value="${CSS.escape(S.color)}"]`)?.focus(); }
  else if (id === 'rk-envelope') { const [x, y, z] = el.value.split(',').map(Number); change(c => { c.layout.envelope = el.value ? {x, y, z} : null; }); }
  else if (id === 'rk-columns') change(c => { c.layout.columns = el.value ? Math.max(1, Math.min(60, Math.floor(Number(el.value)))) : null; });
  else if (id === 'rk-margin') change(c => { c.layout.outer_margin_mm = Math.max(0, Math.min(15, Number(el.value) || 0)); });
  else if (id === 'rk-corner') change(c => { c.corner_radius_mm = el.value === '' ? null : Math.max(0, Math.min(60, Number(el.value) || 0)); });
  else if (id === 'rk-clearance') change(c => { c.clearance_adjust_mm = Number(el.value); });
  else if (id === 'rk-face') setLabel({position: el.value});
  else if (id === 'rk-font') setLabel({font: el.value});
  else if (id === 'rk-size') setLabel({size_mm: el.value ? Number(el.value) : null});
  else if (id === 'rk-show-tubes') { S.showTubes = el.checked; S.viewer?.setTubesVisible(el.checked); }
  else if (id === 'rk-show-guides') { S.guides = el.checked; S.viewer?.setGuidesVisible(el.checked); }
  else if (el.dataset.model) {
    const family = el.dataset.model, next = el.value;
    S.chosenProfiles = {...S.chosenProfiles, [family]: next};
    change(c => { for (const t of c.tubes) if (familyOf(t.profile_id) === family) t.profile_id = next; for (const p of c.layout.positions) if (familyOf(p.profile_id) === family) p.profile_id = next; });
  }
  else if (el.dataset.override) {
    const target = profileOf(el.dataset.family), key = el.dataset.override, value = el.value === '' ? null : Number(el.value);
    change(c => { const o = {...(c.overrides[target] || {})}; if (value === null) delete o[key]; else o[key] = value; if (Object.keys(o).length) c.overrides[target] = o; else delete c.overrides[target]; });
  }
}
function onUndoKey(event) {
  if (!root() || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z' || event.target.matches?.('input[type=text], textarea')) return;
  event.preventDefault(); event.shiftKey ? restore(S.redo, S.undo) : restore(S.undo, S.redo);
}
function onEditorKey(event) {
  if (!S.editing || event.key !== 'Escape') return;
  if (S.armed) { S.armed = ''; drawPlan(); }
  else if (S.selected.size) { S.selected.clear(); drawPlan(); }
}
function ensureViewer() {
  if (S.viewerPromise) return S.viewerPromise;
  const host = q('#rk-canvas'); if (!host) return Promise.resolve(null);
  if (!document.createElement('canvas').getContext('webgl2') && !document.createElement('canvas').getContext('webgl')) { host.innerHTML = '<p class="rk-note">Your browser cannot show the 3D model here. The top view and the list of positions show the same rack.</p>'; S.viewerPromise = Promise.resolve(null); return S.viewerPromise; }
  S.viewerPromise = import('./rack-viewer.js?v=9').then(m => {
    if (!q('#rk-canvas')) return null;
    S.viewer = m.createRackViewer(host, {lowPower: PHONE.matches, tubeInfo: (id, t) => { const p = profile(id); return {body: t.bore_d - p.recommended_clearance_mm, tip: p.tip_diameter_mm, cone: p.cone_length_mm, length: t.length, cap: t.cap_d, capHeight: p.family.startsWith('micro') ? CAP_HEIGHT.micro : CAP_HEIGHT.conical}; }});
    S.viewer.setTubesVisible(S.showTubes); S.viewer.resize(); applyDevice();
    window.__rackViewer = S.viewer;
    return S.viewer;
  }).catch(() => { host.innerHTML = '<p class="rk-note" role="alert">The 3D model could not be shown. The top view and the list of positions show the same rack.</p>'; return null; });
  return S.viewerPromise;
}

/* ---- Basic and Advanced: one configuration, two amounts of it on show. Hiding a control never changes a value. ---- */
function setAdvanced(on, {focus = false} = {}) {
  S.advanced = on;
  const toggle = q('#rk-advanced-toggle'), panel = q('#rk-advanced'); if (!toggle) return;
  toggle.setAttribute('aria-expanded', String(on)); panel.hidden = !on;
  root().classList.toggle('is-advanced', on);
  if (focus && on) panel.querySelector('input,select,button')?.focus({preventScroll: true});
  saveDraft(); drawAdvancedState();
}
/** Which values differ from what Basic would choose, so that nothing hidden is ever a surprise. */
function advancedChanges() {
  const c = S.config, l = c.layout, label = c.label || {}, changes = [];
  if (l.spacing !== 'standard' || l.arrangement !== 'auto' || l.orientation !== 'auto' || l.columns) changes.push('layout');
  if (l.envelope) changes.push('printing area');
  if (l.outer_margin_mm) changes.push('margin');
  if (c.clearance_adjust_mm || Object.keys(c.overrides).length) changes.push('tube fit');
  if (c.tubes.concat(l.positions).some(t => catalog.families.find(f => f.id === familyOf(t.profile_id))?.default !== t.profile_id)) changes.push('tube profile');
  if (c.edge !== 'soft' || c.corner_radius_mm !== null && c.corner_radius_mm !== undefined) changes.push('edges');
  if ((label.position && label.position !== 'front') || (label.font && label.font !== 'sans') || label.size_mm) changes.push('lettering');
  return changes;
}
function drawAdvancedState() {
  const note = q('#rk-advanced-changed'); if (!note) return;
  const changes = advancedChanges();
  note.textContent = changes.length ? `${changes.length} changed` : '';
  q('#rk-reset-advanced').disabled = !changes.length;
  q('#rk-edge-empty').hidden = S.config.style === 'premium';
}
function resetAdvanced() {
  const counts = {};
  for (const t of (isManual() ? S.config.layout.positions.map(p => ({profile_id: p.profile_id, quantity: 1})) : S.config.tubes)) { const family = familyOf(t.profile_id); counts[family] = (counts[family] || 0) + t.quantity; }
  S.selected.clear(); S.armed = ''; S.chosenProfiles = {};
  change(c => {
    c.tubes = Object.entries(counts).map(([family, quantity]) => ({profile_id: catalog.families.find(f => f.id === family).default, quantity}));
    c.layout = {mode: 'auto', spacing: 'standard', arrangement: 'auto', orientation: 'auto', columns: null, outer_margin_mm: 0, positions: [], preference: c.layout.preference || 'balanced'};
    c.edge = 'soft'; c.corner_radius_mm = null; c.clearance_adjust_mm = 0; c.overrides = {};
    if (c.label) c.label = {...c.label, font: 'sans', size_mm: null, position: 'front'};
  });
  if (S.editing) setEditing(false);
  announce('Advanced settings reset. Your tubes, style and name are unchanged.');
}

/* ---- Routes ---- */
function setMeta() {
  savedTitle ||= document.title;
  document.title = 'Design Your Rack: custom 3D-printed laboratory tube racks | OpenLabs3D';
  const meta = q('meta[name=description]');
  if (meta) { savedDescription ||= meta.content; meta.content = 'Design a laboratory tube rack around the tubes you use: mix 0.5, 1.5, 15 and 50 mL tubes, choose Lightweight or Premium, add your lab name, and have it 3D printed by an independent host.'; }
}
export function leave() {
  clearTimeout(planTimer); clearTimeout(buildTimer); clearTimeout(pollTimer); clearTimeout(textTimer); planAbort?.abort(); planSeq++; buildSeq++;
  document.removeEventListener('keydown', onUndoKey); document.removeEventListener('keydown', onEditorKey);
  PHONE.removeEventListener('change', applyDevice); LANDSCAPE.removeEventListener('change', applyDevice);
  document.documentElement.classList.remove('rk-lock');
  S.editing = false; S.suggestion = null;
  S.viewer?.dispose(); S.viewer = null; S.viewerPromise = null; S.mounted = false; drag = null;
  window.__rackViewer = undefined;
  if (savedTitle) { document.title = savedTitle; savedTitle = ''; }
  const meta = q('meta[name=description]'); if (meta && savedDescription) { meta.content = savedDescription; savedDescription = ''; }
}
async function ensureCatalog() { return catalog ||= await api('/racks/catalog'); }
function mount() {
  $('#app').innerHTML = `<div class="rk-page">${pageHtml()}</div>`;
  S.mounted = true; bindPage(); syncControls(); drawShelf(); updateHistoryButtons(); drawFinish(); drawMetrics(); drawReport(); drawBuildState(); updateActions();
  q('#rk-name').value = S.name || '';
  setAdvanced(S.advanced);
  applyDevice();
  ensureViewer();
  requestPlan();
  if (S.restored) { S.restored = false; toast('Your unsaved changes to this design were restored. Save them to keep them.'); }
}
export async function showRoute(route) {
  try {
    await ensureCatalog();
    if (currentRoute() !== route) return;
    if (route === 'my-designs') { leave(); await showDesigns(); return; }
    const id = route.startsWith('design-rack/') ? Number(route.split('/')[1]) : null;
    setMeta();
    if (root() && S.mounted && (id === null ? !S.design : S.design?.id === id)) return;     // the same design, already on screen
    leave(); setMeta();
    S.plan = null; S.build = null; S.buildHash = ''; S.undo = []; S.redo = []; S.selected = new Set(); S.editing = false; S.armed = ''; S.suggestion = null; S.chosenProfiles = {};
    if (id) {
      if (!account) { sessionStorage.setItem('ol3d-return-to', route); $('#app').innerHTML = layout('<div class="banner"><span>Sign in to open your saved designs.</span> <a class="btn-ghost btn-sm" href="#account">Sign in</a></div>'); return; }
      const design = await api('/racks/designs/' + id);
      if (currentRoute() !== route) return;
      S.design = design; S.config = design.config; S.name = design.name; S.material = design.config.material || ''; S.color = design.config.color || ''; S.advanced = false;
      const unsaved = loadDraft(draftKey());
      if (unsaved && JSON.stringify(unsaved.config) !== JSON.stringify(design.config)) { S.config = unsaved.config; S.material = unsaved.material || S.material; S.color = unsaved.color || S.color; S.advanced = !!unsaved.advanced; S.restored = true; }
    } else {
      const draft = loadDraft();
      S.design = null; S.config = draft?.config || freshConfig(); S.name = draft?.name || ''; S.material = draft?.material || ''; S.color = draft?.color || ''; S.advanced = !!draft?.advanced;
    }
    mount();
  } catch (e) {
    if (currentRoute() === route) $('#app').innerHTML = layout(`<div class="banner danger" role="alert"><span>${esc(e.status === 404 ? 'This design does not exist, or it belongs to another account.' : e.message)}</span> <a class="btn-ghost btn-sm" href="#design-rack">Start a new design</a></div>`);
  }
}

/* ---- My designs ---- */
const designSummary = d => {
  const config = d.config, counts = {};
  if (config.layout.mode === 'manual') for (const p of config.layout.positions) counts[p.profile_id] = (counts[p.profile_id] || 0) + 1;
  else for (const t of config.tubes) if (t.quantity) counts[t.profile_id] = t.quantity;
  const parts = Object.entries(counts).map(([id, n]) => `${n} × ${profile(id) ? Number(profile(id).nominal_capacity_ml) : '?'} mL`);
  return `${parts.join(', ') || 'No tubes yet'}, ${config.style === 'premium' ? 'Premium' : 'Lightweight'}`;
};
function designCard(d) {
  const updated = new Intl.DateTimeFormat(undefined, {dateStyle: 'medium'}).format(new Date(d.updated_at));
  const ordered = d.purchased?.length ? `<details class="rk-ordered"><summary>Ordered ${d.purchased.length === 1 ? 'once' : `${d.purchased.length} times`}</summary><ul>${d.purchased.map(o => `<li><span>${esc(o.order_reference)}: ${esc(o.material)}, ${esc(colorName(o.color))}, ${money(o.price_cents / 100)} each</span><span class="rk-row-actions"><button type="button" class="link-button" data-reorder="${o.item_id}">Order again</button><button type="button" class="link-button" data-from-order="${o.item_id}">New draft from this</button></span></li>`).join('')}</ul><p class="rk-note">An order keeps exactly what was bought. Editing this design never changes it.</p></details>` : '';
  return `<li class="rk-design" data-id="${d.id}"><a class="rk-design-pic" href="#design-rack/${d.id}" aria-hidden="true" tabindex="-1">${d.thumbnail_url ? `<img src="${esc(d.thumbnail_url)}" alt="" width="640" height="640" loading="lazy" decoding="async">` : '<span class="rk-design-empty"></span>'}</a><div class="rk-design-copy"><h2><a href="#design-rack/${d.id}">${esc(d.name)}</a></h2><p>${esc(designSummary(d))}</p><p class="rk-quiet">Saved ${esc(updated)}</p>${ordered}</div><div class="rk-row-actions"><a class="btn-ghost btn-sm" href="#design-rack/${d.id}">Open</a><button type="button" class="btn-ghost btn-sm" data-rename="${d.id}">Rename</button><button type="button" class="btn-ghost btn-sm" data-duplicate="${d.id}">Duplicate</button><button type="button" class="btn-ghost btn-sm danger-text" data-delete="${d.id}">Delete</button></div></li>`;
}
async function showDesigns() {
  document.title = 'My designs | OpenLabs3D';
  if (!account) { sessionStorage.setItem('ol3d-return-to', 'my-designs'); $('#app').innerHTML = layout(`<div class="rk-designs" id="rk-designs"><h1>My designs</h1><p>Sign in to keep your rack designs in your account. You can try the configurator without an account.</p><p><a class="btn" href="#account">Sign in</a> <a class="btn-ghost" href="#design-rack">Design a rack</a></p></div>`); return; }
  const designs = await api('/racks/designs');
  if (currentRoute() !== 'my-designs') return;
  $('#app').innerHTML = layout(`<div class="rk-designs" id="rk-designs"><header class="rk-designs-head"><h1>My designs</h1><a class="btn btn-sm" href="#design-rack">${icon('plus')} New design</a></header>${designs.length ? `<ul class="rk-design-list">${designs.map(designCard).join('')}</ul>` : `<div class="rk-empty"><p>No saved designs yet. Design a rack and choose <em>Save design</em> to keep it here.</p><a class="btn" href="#design-rack">Design a rack</a></div>`}</div>`);
  q('#rk-designs').addEventListener('click', onDesignClick);
}
async function onDesignClick(event) {
  const t = event.target.closest('button'); if (!t) return;
  try {
    if (t.dataset.duplicate) { await api(`/racks/designs/${t.dataset.duplicate}/duplicate`, {method: 'POST'}); toast('Design duplicated'); await showDesigns(); }
    else if (t.dataset.rename) renameInline(t);
    else if (t.dataset.delete) confirmDelete(t);
    else if (t.dataset.confirmDelete) { await api('/racks/designs/' + t.dataset.confirmDelete, {method: 'DELETE'}); toast('Design deleted'); await showDesigns(); }
    else if (t.dataset.cancelDelete) await showDesigns();
    else if (t.dataset.reorder) {
      const line = await api(`/racks/orders/${t.dataset.reorder}/reorder`, {method: 'POST'});
      await accountAction('/cart', {listing_id: line.listing_id, material: line.material, color: line.color, quantity: 1, expected_unit_price_cents: line.unit_price_cents});
      if (typeof refreshCart === 'function') await refreshCart().catch(() => {});
      toast('Added to your basket'); renderNavbar(currentRoute());
    }
    else if (t.dataset.fromOrder) { const d = await api(`/racks/orders/${t.dataset.fromOrder}/design`, {method: 'POST'}); location.hash = 'design-rack/' + d.id; }
  } catch (e) { toast(e.message); }
}
function confirmDelete(button) {
  const row = button.closest('.rk-row-actions'), id = button.dataset.delete;
  row.innerHTML = `<span class="rk-quiet">Delete this design?</span><button type="button" class="btn-ghost btn-sm danger-text" data-confirm-delete="${id}">Delete</button><button type="button" class="btn-ghost btn-sm" data-cancel-delete="1">Keep</button>`;
  row.querySelector('[data-cancel-delete]').focus();
}
function renameInline(button) {
  const card = button.closest('.rk-design'), heading = card.querySelector('h2'), id = button.dataset.rename, current = heading.textContent;
  heading.innerHTML = `<form class="rk-rename"><label class="sr-only" for="rk-rename-${id}">Design name</label><input id="rk-rename-${id}" maxlength="80" required value="${esc(current)}" autocomplete="off"><button class="btn-ghost btn-sm">Save name</button></form>`;
  const form = heading.querySelector('form'), input = form.querySelector('input'); input.focus(); input.select();
  form.onsubmit = async e => { e.preventDefault(); try { await api('/racks/designs/' + id, {method: 'PATCH', body: JSON.stringify({name: input.value.trim()})}); toast('Design renamed'); await showDesigns(); } catch (err) { toast(err.message); } };
}
