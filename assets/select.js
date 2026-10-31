/* Reusable dropdown in the marketplace filter style (.cf-select / .cf-trigger / .cf-menu).
   uiSelect() returns the markup; one set of document listeners drives every [data-select] root on the page.
   Modes: a listbox button (default), a searchable combobox (searchable:true) and a popover holding any
   controls ([data-select-popover], e.g. the catalogue price slider).
   Choosing an option writes the hidden input and dispatches input + change on it, so forms and listeners see it. */
let uiSelectSeq = 0;
const uiEsc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const uiFold = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const UI_CHEVRON = '<svg class="cf-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';

function uiSelectOptionsMarkup(id, options, value) {
  return options.map(([v, l], i) => `<li role="option" id="${id}-o-${i}" data-value="${uiEsc(v)}" aria-selected="${String(v) === String(value)}">${uiEsc(l)}</li>`).join('');
}
/* options: [[value, label], ...]. A searchable select may start empty (value not in options); a plain one falls back to the first option. */
function uiSelect({name, label = '', ariaLabel = '', options, value = '', id, searchable = false, placeholder = 'Search…', required = false, className = '', attrs = ''}) {
  id = id || `sel-${name || 'x'}-${++uiSelectSeq}`;
  const current = options.find(([v]) => String(v) === String(value)) || (searchable ? null : options[0]);
  const labelled = label ? `aria-labelledby="${id}-l"` : `aria-label="${uiEsc(ariaLabel)}"`;
  const menu = `<ul class="cf-menu" id="${id}-m" role="listbox" tabindex="-1" ${labelled} hidden>${uiSelectOptionsMarkup(id, options, current?.[0])}${searchable ? '<li class="cf-no-match" role="presentation" hidden>No matches</li>' : ''}</ul>`;
  const hidden = `<input type="hidden"${name ? ` name="${uiEsc(name)}"` : ''} value="${uiEsc(current?.[0] ?? '')}">`;
  if (searchable) {
    return `<div class="cf-select is-searchable ${className}" data-select="${uiEsc(name || id)}" data-searchable ${attrs}>${label ? `<label class="cf-label" id="${id}-l" for="${id}-i">${uiEsc(label)}</label>` : ''}<div class="cf-combo"><input id="${id}-i" class="cf-input" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${id}-m" ${label ? '' : `aria-label="${uiEsc(ariaLabel)}"`} placeholder="${uiEsc(placeholder)}" value="${uiEsc(current?.[1] ?? '')}" autocomplete="off" spellcheck="false"${required ? ' required' : ''}><button type="button" class="cf-combo-toggle" tabindex="-1" aria-label="Show options" aria-controls="${id}-m">${UI_CHEVRON}</button></div>${menu}${hidden}</div>`;
  }
  return `<div class="cf-select ${className}" data-select="${uiEsc(name || id)}" ${attrs}>${label ? `<span class="cf-label" id="${id}-l">${uiEsc(label)}</span>` : ''}<button type="button" class="cf-trigger" id="${id}-t" aria-haspopup="listbox" aria-expanded="false" aria-controls="${id}-m" ${label ? `aria-labelledby="${id}-l ${id}-t"` : `aria-label="${uiEsc(ariaLabel)}"`}><span class="cf-value">${uiEsc(current?.[1] ?? '')}</span>${UI_CHEVRON}</button>${menu}${hidden}</div>`;
}

const uiSelectRoot = target => typeof target === 'string' ? document.querySelector(`[data-select="${target}"]`) : target;
const uiSelectFocusOwner = root => root.querySelector('.cf-input') || root.querySelector('.cf-trigger');
const uiSelectOptions = root => [...root.querySelectorAll('.cf-menu [role=option]:not([hidden])')];
function uiSelectValue(target) { return uiSelectRoot(target)?.querySelector('input[type=hidden]').value ?? ''; }

/* Programmatic selection; silent skips the input/change events. */
function uiSelectSet(target, value, {silent = false} = {}) {
  const root = uiSelectRoot(target); if (!root) return;
  const all = [...root.querySelectorAll('.cf-menu [role=option]')];
  const option = all.find(o => o.dataset.value === String(value)) || (root.hasAttribute('data-searchable') ? null : all[0]);
  all.forEach(o => o.setAttribute('aria-selected', String(o === option)));
  const text = option?.textContent ?? '', input = root.querySelector('.cf-input');
  if (input) input.value = text; else root.querySelector('.cf-value').textContent = text;
  const hidden = root.querySelector('input[type=hidden]'), changed = hidden.value !== (option?.dataset.value ?? '');
  hidden.value = option?.dataset.value ?? '';
  if (!silent && changed) { hidden.dispatchEvent(new Event('input', {bubbles:true})); hidden.dispatchEvent(new Event('change', {bubbles:true})); }
}
/* Replace the options, e.g. for a list that depends on another field. Keeps the value when it is still offered. */
function uiSelectSetOptions(target, options, value = uiSelectValue(target)) {
  const root = uiSelectRoot(target); if (!root) return;
  const menu = root.querySelector('.cf-menu'), id = menu.id.replace(/-m$/, ''), empty = menu.querySelector('.cf-no-match');
  menu.innerHTML = uiSelectOptionsMarkup(id, options, value); if (empty) menu.append(empty);
  uiSelectSet(root, value, {silent:String(value) === uiSelectValue(root)});
}

function uiSelectClose(root, focus = false) {
  if (!root || !root.classList.contains('is-open')) { if (focus && root) uiSelectFocusOwner(root).focus(); return; }
  root.querySelector('.cf-menu').hidden = true; root.classList.remove('is-open');
  const owner = uiSelectFocusOwner(root); owner.setAttribute('aria-expanded', 'false'); owner.removeAttribute('aria-activedescendant');
  // A searchable select never keeps half-typed text: it shows the chosen option again.
  const input = root.querySelector('.cf-input');
  if (input) { input.value = root.querySelector('[role=option][aria-selected=true]')?.textContent ?? ''; uiSelectFilter(root, ''); }
  if (focus) owner.focus();
}
function uiSelectOpen(root) {
  if (root.classList.contains('is-open')) return;
  document.querySelectorAll('[data-select].is-open').forEach(r => r !== root && uiSelectClose(r));
  const menu = root.querySelector('.cf-menu'), owner = uiSelectFocusOwner(root);
  menu.hidden = false; root.classList.add('is-open'); owner.setAttribute('aria-expanded', 'true');
  // Open upwards when there is no room below, so the menu is never clipped by the viewport.
  const rect = root.getBoundingClientRect(); root.classList.toggle('opens-up', innerHeight - rect.bottom < menu.offsetHeight + 12 && rect.top > menu.offsetHeight + 12);
  if (root.hasAttribute('data-select-popover')) { (menu.querySelector('input:not([disabled]),button:not([disabled]),select,textarea,[tabindex="0"]') || menu).focus(); return; }
  const selected = menu.querySelector('[role=option][aria-selected=true]') || uiSelectOptions(root)[0];
  if (selected) uiSelectActivate(root, selected);
  if (!root.hasAttribute('data-searchable')) menu.focus();
}
function uiSelectActivate(root, option) {
  root.querySelectorAll('.cf-menu .is-active').forEach(o => o.classList.remove('is-active'));
  const owner = root.hasAttribute('data-searchable') ? root.querySelector('.cf-input') : root.querySelector('.cf-menu');
  if (!option) { owner.removeAttribute('aria-activedescendant'); return; }
  option.classList.add('is-active'); owner.setAttribute('aria-activedescendant', option.id); option.scrollIntoView({block:'nearest'});
}
function uiSelectChoose(root, option) {
  uiSelectSet(root, option.dataset.value); uiSelectClose(root, true);
  root.querySelector('.cf-input')?.select(); // typing again starts a new search instead of appending to the label
}
// Live filter for the searchable mode; accents and case are ignored.
function uiSelectFilter(root, query) {
  const q = uiFold(query.trim()), options = [...root.querySelectorAll('.cf-menu [role=option]')];
  options.forEach(o => { o.hidden = !!q && !uiFold(o.textContent).includes(q); });
  const visible = uiSelectOptions(root), empty = root.querySelector('.cf-no-match');
  if (empty) empty.hidden = visible.length > 0;
  if (root.classList.contains('is-open')) uiSelectActivate(root, q ? visible[0] : (visible.find(o => o.getAttribute('aria-selected') === 'true') || visible[0]));
}
function uiSelectMove(root, key) {
  const options = uiSelectOptions(root); if (!options.length) return;
  const index = options.findIndex(o => o.classList.contains('is-active'));
  const next = key === 'Home' ? 0 : key === 'End' ? options.length - 1 : Math.min(options.length - 1, Math.max(0, index + (key === 'ArrowDown' ? 1 : -1)));
  uiSelectActivate(root, options[next]);
}

// Keep focus where it is while pressing the trigger of an open select, an option, or the combobox chevron;
// otherwise the blur would close the menu before the click lands.
document.addEventListener('pointerdown', e => {
  if (e.target.closest?.('[data-select].is-open > .cf-trigger, [data-searchable] .cf-menu, [data-searchable] .cf-combo-toggle')) e.preventDefault();
});
document.addEventListener('click', e => {
  const toggle = e.target.closest('.cf-combo-toggle');
  if (toggle) {
    const root = toggle.closest('[data-select]'), input = root.querySelector('.cf-input');
    if (document.activeElement !== input) input.focus(); else root.classList.contains('is-open') ? uiSelectClose(root) : uiSelectOpen(root);
    return;
  }
  const input = e.target.closest('[data-searchable] .cf-input');
  if (input) { uiSelectOpen(input.closest('[data-select]')); return; }
  const trigger = e.target.closest('[data-select] > .cf-trigger');
  if (trigger) { const root = trigger.closest('[data-select]'); root.classList.contains('is-open') ? uiSelectClose(root, true) : uiSelectOpen(root); return; }
  const option = e.target.closest('[data-select] .cf-menu [role=option]');
  if (option) { uiSelectChoose(option.closest('[data-select]'), option); return; }
  // Any other click closes the open selects it is not inside.
  document.querySelectorAll('[data-select].is-open').forEach(r => !r.contains(e.target) && uiSelectClose(r));
});
document.addEventListener('focusin', e => {
  const input = e.target.closest?.('[data-searchable] .cf-input'); if (!input) return;
  uiSelectOpen(input.closest('[data-select]'));
  // The current value becomes editable: select it so typing replaces it.
  requestAnimationFrame(() => { if (document.activeElement === input) input.select(); });
});
document.addEventListener('input', e => {
  const input = e.target.closest?.('[data-searchable] .cf-input'); if (!input) return;
  const root = input.closest('[data-select]'); uiSelectOpen(root); uiSelectFilter(root, input.value);
});
document.addEventListener('keydown', e => {
  const input = e.target.closest?.('[data-searchable] .cf-input');
  if (input) {
    const root = input.closest('[data-select]'), open = root.classList.contains('is-open');
    if (['ArrowDown', 'ArrowUp'].includes(e.key)) { e.preventDefault(); if (open) uiSelectMove(root, e.key); else uiSelectOpen(root); }
    else if (e.key === 'Enter' && open) { e.preventDefault(); const active = root.querySelector('.cf-menu .is-active:not([hidden])'); if (active) uiSelectChoose(root, active); }
    else if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); uiSelectClose(root); }
    else if (e.key === 'Tab') uiSelectClose(root);
    return;
  }
  const trigger = e.target.closest?.('[data-select] > .cf-trigger');
  if (trigger && ['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); uiSelectOpen(trigger.closest('[data-select]')); return; }
  const menu = e.target.closest?.('[data-select] .cf-menu'); if (!menu) return;
  const root = menu.closest('[data-select]');
  if (root.hasAttribute('data-select-popover')) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); uiSelectClose(root, true); } return; }
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); uiSelectClose(root, true); }
  else if (e.key === 'Tab') uiSelectClose(root);
  else if (['Enter', ' '].includes(e.key)) { e.preventDefault(); const active = menu.querySelector('.is-active'); if (active) uiSelectChoose(root, active); }
  else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) { e.preventDefault(); uiSelectMove(root, e.key); }
  else if (e.key.length === 1) { const match = uiSelectOptions(root).find(o => o.textContent.trim().toLowerCase().startsWith(e.key.toLowerCase())); if (match) uiSelectActivate(root, match); }
});
document.addEventListener('focusout', e => { const root = e.target.closest?.('[data-select].is-open'); if (root && !root.contains(e.relatedTarget)) uiSelectClose(root); });
