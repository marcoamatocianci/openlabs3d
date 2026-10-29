/* Account Settings: profile, contact details, saved addresses and security on one page.
   Reuses the existing router, session and API helpers. */
let accountCountries = [], savedAddresses = null, savedAddressesOwner = null, addressEditing = null, cityHintSeq = 0;
const accountRender = render;
const contactNames = {first_name:'First name', last_name:'Last name', phone:'Phone number', street:'Street address', additional:'Apartment, building or floor', postal_code:'Postal code', city:'City', region:'Region / province'};
const fieldLimits = {first_name:100, last_name:100, phone:40, city:150, region:150, postal_code:30, street:200, additional:200};
const fieldAutocomplete = {first_name:'given-name', last_name:'family-name', phone:'tel', street:'address-line1', additional:'address-line2', postal_code:'postal-code', city:'address-level2', region:'address-level1'};
async function ensureCountries() { if (!accountCountries.length) accountCountries = await api('/countries'); return accountCountries; }
const countryLabel = code => accountCountries.find(c => c.code === code)?.name || code || '';
function textField(key, value='', {required=false, optional=false, wide=false}={}) {
  return `<label class="${wide ? 'wide' : ''}">${contactNames[key]}${optional ? ' <span class="optional">optional</span>' : ''}<input name="${key}" type="${key === 'phone' ? 'tel' : 'text'}" maxlength="${fieldLimits[key]}" autocomplete="${fieldAutocomplete[key]}" value="${esc(value || '')}" ${required ? 'required' : ''} ${key === 'phone' ? 'placeholder="+39 011 1234567"' : ''}></label>`;
}
function countryField(value='', required=false) {
  return `<label>Country<input type="search" placeholder="Search countries" class="country-search" aria-label="Search countries"><select name="country" aria-label="Country" autocomplete="country" ${required ? 'required' : ''}><option value="">Select country</option>${accountCountries.map(c => `<option value="${c.code}" ${c.code === value ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>`;
}
function passwordField(name='password', label='Password') { return `<label>${label}<input name="${name}" type="password" minlength="8" maxlength="128" required autocomplete="new-password" data-policy></label><button type="button" class="btn-ghost btn-sm password-toggle">Show password</button><p class="password-rules" aria-live="polite">At least 8 characters · One uppercase letter · One number</p>`; }
// Small self-hosted city hint list; manual entry is always supported.
const cityHints = {IT:['Torino','Milano','Roma','Napoli','Bologna','Firenze','Genova','Padova'], FR:['Paris','Lyon','Marseille'], DE:['Berlin','Hamburg','Munich'], GB:['London','Cambridge','Oxford','Edinburgh'], US:['New York','Boston','Chicago','San Francisco'], ES:['Madrid','Barcelona','Valencia'], CH:['Zürich','Geneva','Basel']};
function bindAccountFields(root=document) {
  root.querySelectorAll('.country-search:not([data-bound])').forEach(input => { input.dataset.bound = 1; input.oninput = () => { for (const option of input.nextElementSibling.options) option.hidden = !!option.value && !option.textContent.toLowerCase().includes(input.value.toLowerCase()); }; });
  root.querySelectorAll('[data-policy]:not([data-bound])').forEach(input => {
    input.dataset.bound = 1; const form = input.closest('form');
    input.oninput = () => { const checks = [input.value.length >= 8, /[A-Z]/.test(input.value), /[0-9]/.test(input.value)]; input.setCustomValidity(checks.every(Boolean) ? '' : 'Use at least 8 characters, an uppercase letter and a number.'); form.querySelector('.password-rules').textContent = checks.map((ok, i) => `${ok ? '✓' : '○'} ${['8 characters', 'Uppercase letter', 'Number'][i]}`).join(' · '); };
    form.querySelector('.password-toggle').onclick = e => { input.type = input.type === 'password' ? 'text' : 'password'; e.target.textContent = input.type === 'password' ? 'Show password' : 'Hide password'; };
  });
  root.querySelectorAll('[data-username]:not([data-bound])').forEach(input => {
    input.dataset.bound = 1; let timer, seq = 0;
    input.addEventListener('input', () => { clearTimeout(timer); const n = ++seq; input.setCustomValidity(''); timer = setTimeout(async () => { try { const r = await api('/auth/username?username=' + encodeURIComponent(input.value)); if (n !== seq) return; input.setCustomValidity(r.available ? '' : 'Username is unavailable or invalid'); input.closest('form').querySelector('.username-status').textContent = r.available ? 'Username available' : 'Username unavailable or invalid'; } catch (e) { showError(e); } }, 300); });
  });
  root.querySelectorAll('form').forEach(form => {
    const country = form.elements.country, city = form.elements.city;
    if (!country || !city || city.dataset.hints) return;
    const id = 'city-hints-' + (++cityHintSeq); city.dataset.hints = id; city.setAttribute('list', id); city.insertAdjacentHTML('afterend', `<datalist id="${id}"></datalist>`);
    const update = () => { document.getElementById(id).innerHTML = (cityHints[country.value] || []).map(c => `<option value="${esc(c)}">`).join(''); };
    country.addEventListener('change', update); update();
  });
}
async function accountAction(path, body, method='POST') { const r = await api(path, {method, body:JSON.stringify(body)}); if (r.message) toast(r.message); return r; }

/* Signed-out: sign in and registration side by side. */
function authPage() {
  const register = new URLSearchParams(location.hash.split('?')[1] || '').get('mode') === 'register';
  return layout(`<div class="auth-layout"><header class="auth-head"><h1>${register ? 'Create your account' : 'Welcome to OpenLabs3D'}</h1><p class="muted">Order laboratory tools made by independent printing hosts, or apply to print them yourself.</p></header><div class="auth-grid ${register ? 'register-first' : ''}"><form id="real-login" class="section-card auth-card"><h2>Sign in</h2><label>Email<input name="email" type="email" required autocomplete="email"></label><label>Password<input name="password" type="password" required autocomplete="current-password"></label><button class="primary">Sign in</button><p><a class="textlink" href="#forgot-password">Forgot password?</a></p></form><form id="real-register" class="section-card auth-card"><h2>Create an account</h2><label>Username<input name="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+" autocomplete="username" data-username></label><p class="username-status hint" aria-live="polite">3–32 letters, numbers or underscores; case-insensitive.</p><label>Email<input name="email" type="email" required autocomplete="email"></label>${passwordField()}<button class="primary">Create account</button></form></div></div>`);
}

/* Signed-in: one Account Settings page. */
function avatarFieldHtml() {
  return `<div class="avatar-field" id="avatar-field"><button type="button" class="avatar-button" id="avatar-pick" aria-describedby="avatar-help">${avatarHtml(account, 80, 'avatar-lg')}<span class="avatar-overlay" aria-hidden="true">${icon('camera')}</span><svg class="avatar-progress" viewBox="0 0 36 36" aria-hidden="true"><circle cx="18" cy="18" r="17" pathLength="100"/></svg><span class="sr-only">${account.avatar ? 'Change' : 'Upload'} profile picture</span></button><div class="avatar-copy"><strong>Profile picture</strong><p id="avatar-help">Drop an image here or choose a file. PNG, JPEG or WebP, up to 2 MB.</p><div class="avatar-actions"><button type="button" class="btn-ghost btn-sm" id="avatar-choose">${account.avatar ? 'Change picture' : 'Upload picture'}</button>${account.avatar ? '<button type="button" class="btn-ghost btn-sm danger-text" id="avatar-remove">Remove</button>' : ''}</div><p class="avatar-status" id="avatar-status" role="status" aria-live="polite"></p></div><input type="file" id="avatar-input" accept="image/png,image/jpeg,image/webp" hidden></div>`;
}
const settingsCard = (id, title, text, body, extra='') => `<section class="settings-card" id="settings-${id}" aria-labelledby="settings-${id}-title"><div class="settings-card-head"><div><h2 id="settings-${id}-title">${title}</h2><p>${text}</p></div>${extra}</div>${body}</section>`;
const formFooter = label => `<div class="form-footer"><p class="form-status" role="status"></p><button class="primary" disabled>${label}</button></div>`;
const revealButton = (target, label) => `<button type="button" class="btn-ghost btn-sm" data-reveal="${target}" aria-expanded="false" aria-controls="${target}">${label}</button>`;
function profileSection() {
  return settingsCard('profile', 'Profile', 'How you appear on OpenLabs3D and how you sign in.', `<div class="settings-card-body">${avatarFieldHtml()}<form id="account-profile" class="settings-form"><div class="fields"><label>Display name<input name="display_name" required maxlength="100" autocomplete="name" value="${esc(account.display_name)}"><small class="hint">Shown as the seller on your listings.</small></label><label>Username<input name="username" value="${esc(account.username)}" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+" autocomplete="username" data-username><small class="hint username-status" aria-live="polite">Letters, numbers and underscores.</small></label></div>${formFooter('Save profile')}</form><div class="settings-rows"><div class="settings-row"><div><span class="settings-label">Email</span><span class="settings-value">${esc(account.email)} ${account.email_verified ? statusBadge('approved', 'Verified') : statusBadge('pending', 'Not verified')}</span></div>${revealButton('email-form', 'Change')}</div><form id="email-form" class="inline-form" hidden><div class="fields"><label>New email<input name="email" type="email" required autocomplete="email"></label><label>Current password<input name="current_password" type="password" required autocomplete="current-password"></label></div><p class="hint">You will need to verify the new address. Your other sessions are signed out.</p><div class="form-footer"><button type="button" class="secondary" data-reveal="email-form">Cancel</button><button class="primary">Change email</button></div></form><div class="settings-row"><div><span class="settings-label">Account type</span><span class="settings-value">${esc(roleLabel(account.role))}</span></div></div><div class="settings-row"><div><span class="settings-label">Appearance</span><span class="settings-value muted">Applies immediately and is saved to your account.</span></div>${themeToggle()}</div></div></div>`);
}
function contactSection() {
  return settingsCard('contact', 'Contact information', 'Used for order requests and printing host applications. A host sees it only after accepting your job.', `<form id="account-contact" class="settings-card-body settings-form"><div class="fields">${textField('first_name', account.first_name)}${textField('last_name', account.last_name)}${textField('phone', account.phone)}${countryField(account.country)}${textField('city', account.city)}</div>${formFooter('Save contact information')}</form>`);
}
const addressLines = a => [[a.first_name, a.last_name].filter(Boolean).join(' '), a.street, a.additional, [a.postal_code, a.city].filter(Boolean).join(' ') + (a.region ? ', ' + a.region : ''), countryLabel(a.country)].filter(Boolean);
function addressCard(a) {
  const name = esc(a.label || 'Address');
  return `<article class="address-card ${a.is_default ? 'is-default' : ''}"><div class="address-card-head"><span class="address-label">${name}</span>${a.is_default ? statusBadge('approved', 'Default') : ''}</div><address>${addressLines(a).map(esc).join('<br>')}</address><p class="address-phone">${esc(a.phone)}</p><div class="address-card-actions"><button type="button" class="btn-ghost btn-sm" data-address-edit="${a.id}" aria-label="Edit ${name}">Edit</button>${a.is_default ? '' : `<button type="button" class="btn-ghost btn-sm" data-address-default="${a.id}" aria-label="Set ${name} as default">Set as default</button>`}<button type="button" class="btn-ghost btn-sm danger-text" data-address-delete="${a.id}" aria-label="Delete ${name}">Delete</button></div></article>`;
}
function addressForm(a={}) {
  const v = {first_name:account.first_name, last_name:account.last_name, phone:account.phone, country:account.country, city:account.city, ...a}, locked = a.is_default || !savedAddresses.length;
  return `<form class="address-card address-form" id="address-form" data-id="${a.id || 0}" aria-labelledby="address-form-title"><h3 id="address-form-title">${a.id ? 'Edit address' : 'New address'}</h3><div class="fields">${textField('first_name', v.first_name, {required:true})}${textField('last_name', v.last_name, {required:true})}${textField('street', v.street, {required:true, wide:true})}${textField('additional', v.additional, {optional:true, wide:true})}${textField('postal_code', v.postal_code, {optional:true})}${textField('city', v.city, {required:true})}${textField('region', v.region, {optional:true})}${countryField(v.country, true)}${textField('phone', v.phone, {required:true})}<label>Label <span class="optional">optional</span><input name="label" maxlength="40" list="address-label-options" placeholder="Laboratory, Home, Work…" value="${esc(a.label || '')}"></label></div><datalist id="address-label-options"><option value="Laboratory"><option value="Home"><option value="Work"></datalist><label class="check"><input type="checkbox" name="is_default" ${locked ? 'checked disabled' : ''}> Use as my default address${!savedAddresses.length ? ' <span class="hint">(your first address is the default)</span>' : ''}</label><p class="form-error" role="alert"></p><div class="form-footer"><button type="button" class="secondary" data-address-cancel>Cancel</button><button class="primary">Save address</button></div></form>`;
}
function addressGridHtml() {
  if (savedAddresses === null) return '<p class="muted" role="status">Loading addresses…</p>';
  const cards = savedAddresses.map(a => addressEditing === a.id ? addressForm(a) : addressCard(a));
  if (addressEditing === 0) cards.unshift(addressForm());
  return cards.join('') || `<div class="address-empty">${emptyState('No saved addresses', 'Save a delivery address to check out faster.', `<button type="button" class="btn btn-sm" data-address-new>${icon('plus')}Add address</button>`)}</div>`;
}
function addressSection() { return settingsCard('addresses', 'Saved addresses', 'Choose one at checkout. Your default address is preselected.', `<div class="settings-card-body"><div class="address-grid" id="address-grid">${addressGridHtml()}</div></div>`, `<button type="button" class="btn-ghost btn-sm" id="address-add" data-address-new hidden>${icon('plus')}Add address</button>`); }
function securitySection() {
  return settingsCard('security', 'Security', 'Keep your account protected.', `<div class="settings-card-body"><div class="settings-rows"><div class="settings-row"><div><span class="settings-label">Password</span><span class="settings-value muted">Changing your password signs out your other sessions.</span></div>${revealButton('password-form', 'Change password')}</div><form id="password-form" class="inline-form" hidden><div class="fields"><label>Current password<input name="current_password" type="password" required autocomplete="current-password"></label><div>${passwordField('password', 'New password')}</div></div><div class="form-footer"><button type="button" class="secondary" data-reveal="password-form">Cancel</button><button class="primary">Update password</button></div></form></div></div>`);
}
function dangerSection() {
  return `<details class="settings-card danger-zone" id="settings-delete"><summary><span><strong>Delete account</strong><span class="muted">Permanently remove your account and sign out everywhere.</span></span>${icon('chevron')}</summary><div class="settings-card-body"><p>Accounts with listings, orders or printing jobs cannot be deleted while those records exist. Your host application and active sessions are removed.</p><form class="delete-account-form" data-id="${account.id}" data-self="true"><label>Confirm with your password<input name="password" type="password" maxlength="128" autocomplete="current-password" required></label><p class="delete-account-error form-error" role="alert"></p><button class="danger">Delete my account</button></form></div></details>`;
}
function accountPage() {
  if (!account) return authPage();
  document.title = 'Account settings · ' + (publicSettings.marketplace_name || 'OpenLabs3D');
  const checkout = sessionStorage.getItem('checkout-return-' + account.id);
  const banners = (!account.email_verified ? `<div class="banner warning" role="status"><span><strong>Verify your email address.</strong> A verified email is required to order, apply as a printing host or create listings.</span><button type="button" class="btn-ghost btn-sm" id="resend-verification">Resend email</button></div>` : '')
    + (checkout ? `<div class="banner info" id="checkout-banner"><span>Your checkout is saved. Return to it when your details are complete.</span><a class="btn btn-sm" href="#${checkout === 'checkout' ? 'checkout' : 'checkout-cart'}">Return to checkout</a><button type="button" class="icon-btn" id="dismiss-checkout" aria-label="Dismiss">${icon('close')}</button></div>` : '');
  return layout(`<div class="settings"><header class="settings-head"><h1>Account settings</h1><p class="muted">Your profile, contact details and delivery addresses in one place.</p></header>${banners}${profileSection()}${contactSection()}${addressSection()}${securitySection()}${dangerSection()}</div>`);
}

/* Behaviour */
function avatarStatus(text, kind='') { const s = $('#avatar-status'); if (s) { s.textContent = text; s.className = 'avatar-status ' + kind; } }
function setAvatarProgress(fraction) { const circle = $('#avatar-field .avatar-progress circle'); if (circle) circle.style.strokeDashoffset = String(100 - 100 * fraction); }
function refreshAvatarField() { const field = $('#avatar-field'); if (!field) return; field.outerHTML = avatarFieldHtml(); bindAvatar(); renderNavbar(); }
function uploadAvatar(file) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) return avatarStatus('Choose a PNG, JPEG or WebP image.', 'error');
  if (file.size > 2 * 1024 * 1024) return avatarStatus(`This image is ${(file.size / 1048576).toFixed(1)} MB. Choose one up to 2 MB.`, 'error');
  const field = $('#avatar-field'), preview = URL.createObjectURL(file), avatar = field.querySelector('.avatar-lg');
  avatar.querySelector('img')?.remove(); avatar.insertAdjacentHTML('beforeend', `<img src="${preview}" alt="">`);
  field.classList.add('uploading'); setAvatarProgress(0); avatarStatus('Uploading…');
  const data = new FormData(); data.append('file', file);
  // XMLHttpRequest reports upload progress; fetch does not.
  const xhr = new XMLHttpRequest(); xhr.open('POST', '/api/profile/avatar'); xhr.setRequestHeader('X-CSRF-Token', csrf);
  xhr.upload.onprogress = e => { if (e.lengthComputable) { setAvatarProgress(e.loaded / e.total); avatarStatus(`Uploading… ${Math.round(e.loaded / e.total * 100)}%`); } };
  xhr.onload = () => {
    let body = {}; try { body = JSON.parse(xhr.responseText); } catch (e) {}
    URL.revokeObjectURL(preview);
    if (xhr.status >= 200 && xhr.status < 300) { account = body; refreshAvatarField(); avatarStatus('Profile picture updated.', 'success'); }
    else { refreshAvatarField(); avatarStatus(typeof body.detail === 'string' ? body.detail : 'The image could not be uploaded.', 'error'); }
  };
  xhr.onerror = () => { URL.revokeObjectURL(preview); refreshAvatarField(); avatarStatus('Upload failed. Check your connection and try again.', 'error'); };
  xhr.send(data);
}
async function removeAvatar() { if (!confirm('Remove your profile picture? Your initials are shown instead.')) return; try { account = await api('/profile/avatar', {method:'DELETE'}); refreshAvatarField(); avatarStatus('Profile picture removed.', 'success'); } catch (e) { avatarStatus(e.message, 'error'); } }
function bindAvatar() {
  const field = $('#avatar-field'), input = $('#avatar-input'); if (!field) return;
  $('#avatar-pick').onclick = $('#avatar-choose').onclick = () => input.click();
  input.onchange = () => { if (input.files[0]) uploadAvatar(input.files[0]); input.value = ''; };
  field.ondragenter = field.ondragover = e => { e.preventDefault(); field.classList.add('dragging'); };
  field.ondragleave = e => { if (!field.contains(e.relatedTarget)) field.classList.remove('dragging'); };
  field.ondrop = e => { e.preventDefault(); field.classList.remove('dragging'); const file = e.dataTransfer.files[0]; if (file) uploadAvatar(file); };
  const remove = $('#avatar-remove'); if (remove) remove.onclick = removeAvatar;
}
function bindProfileForm(form, extra={}) {
  const button = form.querySelector('.form-footer .primary'), status = form.querySelector('.form-status');
  form.addEventListener('input', () => { button.disabled = false; status.textContent = ''; status.classList.remove('error'); });
  form.onsubmit = async e => {
    e.preventDefault(); button.disabled = true; status.textContent = 'Saving…';
    try {
      account = await api('/profile', {method:'PATCH', body:JSON.stringify({username:account.username, ...Object.fromEntries(new FormData(form)), ...extra})});
      status.textContent = 'Saved'; renderNavbar();
      // Keep an in-progress checkout in step with the saved contact details.
      try { const key = 'checkout-contact-' + account.id, draft = JSON.parse(sessionStorage.getItem(key) || '{}'); for (const k of ['first_name', 'last_name', 'phone']) draft[k] = account[k]; sessionStorage.setItem(key, JSON.stringify(draft)); } catch (e) {}
    } catch (err) { status.textContent = err.message; status.classList.add('error'); button.disabled = false; }
  };
}
function renderAddressGrid() {
  const grid = $('#address-grid'); if (!grid) return;
  grid.innerHTML = addressGridHtml(); bindAccountFields(grid);
  $('#address-add').hidden = !savedAddresses?.length || addressEditing === 0;
  grid.querySelector('#address-form input')?.focus();
}
async function reloadAddresses() { savedAddresses = await api('/addresses'); savedAddressesOwner = account.id; renderAddressGrid(); }
function bindAddresses() {
  const section = $('#settings-addresses');
  section.addEventListener('click', async e => {
    const target = e.target.closest('button'); if (!target) return;
    if (target.matches('[data-address-new]')) { addressEditing = 0; renderAddressGrid(); }
    else if (target.dataset.addressEdit) { addressEditing = Number(target.dataset.addressEdit); renderAddressGrid(); }
    else if (target.matches('[data-address-cancel]')) { addressEditing = null; renderAddressGrid(); }
    else if (target.dataset.addressDefault) {
      const address = savedAddresses.find(a => a.id === Number(target.dataset.addressDefault)); target.disabled = true;
      try { const {id, ...body} = address; await api('/addresses/' + id, {method:'PUT', body:JSON.stringify({...body, is_default:true})}); await reloadAddresses(); toast('Default address updated'); } catch (err) { showError(err); target.disabled = false; }
    } else if (target.dataset.addressDelete) {
      if (!confirm('Delete this saved address? Orders that used it keep their copy.')) return;
      try { await api('/addresses/' + target.dataset.addressDelete, {method:'DELETE'}); addressEditing = null; await reloadAddresses(); toast('Address deleted'); } catch (err) { showError(err); }
    }
  });
  section.addEventListener('submit', async e => {
    const form = e.target.closest('#address-form'); if (!form) return;
    e.preventDefault(); const button = form.querySelector('.form-footer .primary'); button.disabled = true;
    const data = Object.fromEntries(new FormData(form)); data.is_default = form.elements.is_default.checked;
    try { await api('/addresses/' + form.dataset.id, {method:'PUT', body:JSON.stringify(data)}); addressEditing = null; await reloadAddresses(); toast('Address saved'); }
    catch (err) { form.querySelector('.form-error').textContent = err.message; button.disabled = false; }
  });
}
function bindAccountPage() {
  bindMarketplace(); bindAccountFields(); bindOperations();
  if (!account) { if (new URLSearchParams(location.hash.split('?')[1] || '').get('mode') === 'register') $('#real-register input')?.focus(); return; }
  bindAvatar(); bindProfileForm($('#account-profile')); bindProfileForm($('#account-contact')); bindAddresses();
  $('#address-add').hidden = !savedAddresses?.length;
  $('#app .settings').addEventListener('click', e => {
    const trigger = e.target.closest('[data-reveal]'); if (!trigger) return;
    const form = document.getElementById(trigger.dataset.reveal), open = form.hidden;
    form.hidden = !open; if (!open) form.reset();
    document.querySelectorAll(`[aria-controls="${form.id}"]`).forEach(b => b.setAttribute('aria-expanded', open));
    if (open) form.querySelector('input')?.focus(); else document.querySelector(`[aria-controls="${form.id}"]`)?.focus();
  });
  const resend = $('#resend-verification'); if (resend) resend.onclick = async () => { resend.disabled = true; try { await accountAction('/auth/resend-verification', {}); } catch (e) { showError(e); } resend.disabled = false; };
  const dismiss = $('#dismiss-checkout'); if (dismiss) dismiss.onclick = () => { sessionStorage.removeItem('checkout-return-' + account.id); $('#checkout-banner').remove(); };
  const email = $('#email-form'); email.onsubmit = async e => { e.preventDefault(); try { await accountAction('/auth/change-email', Object.fromEntries(new FormData(email))); account = (await api('/auth/me')).user; renderNavbar(); render(); } catch (err) { showError(err); } };
  const password = $('#password-form'); password.onsubmit = async e => { e.preventDefault(); try { await accountAction('/auth/change-password', Object.fromEntries(new FormData(password))); password.reset(); password.hidden = true; document.querySelector('[aria-controls="password-form"]').setAttribute('aria-expanded', 'false'); } catch (err) { showError(err); } };
}
const legacySections = {'account-contact':'settings-contact', 'account-addresses':'settings-addresses', 'account-security':'settings-security'};
render = function() {
  const route = currentRoute();
  if (route.startsWith('account')) {
    const owner = account?.id; addressEditing = null;
    if (savedAddressesOwner !== owner) savedAddresses = null;
    (async () => {
      try {
        await ensureCountries(); if (!currentRoute().startsWith('account')) return;
        $('#app').innerHTML = accountPage(); bindAccountPage();
        if (legacySections[route]) document.getElementById(legacySections[route])?.scrollIntoView();
        if (account) { savedAddresses = await api('/addresses'); savedAddressesOwner = account.id; if (currentRoute().startsWith('account')) renderAddressGrid(); }
      } catch (e) { showError(e); }
    })();
    return;
  }
  if (['verify', 'reset', 'forgot-password'].includes(route)) {
    const token = new URLSearchParams(location.hash.split('?')[1] || '').get('token') || '';
    $('#app').innerHTML = layout(`<div class="auth-layout"><form id="token-form" class="section-card auth-card"><h1>${route === 'verify' ? 'Verify your email' : route === 'reset' ? 'Choose a new password' : 'Reset your password'}</h1>${route === 'forgot-password' ? '<p class="muted">Enter your account email and we will send a reset link.</p><label>Email<input name="email" type="email" required autocomplete="email"></label>' : route === 'reset' ? passwordField() : '<p class="muted">Confirm access to your email inbox.</p>'}<button class="primary">${route === 'verify' ? 'Verify email' : 'Continue'}</button><p id="token-result" role="status"></p></form></div>`);
    bindAccountFields();
    $('#token-form').onsubmit = async e => { e.preventDefault(); try { const data = Object.fromEntries(new FormData(e.target)); if (route !== 'forgot-password') data.token = token; const r = await accountAction('/auth/' + ({verify:'verify', reset:'reset-password', 'forgot-password':'forgot-password'}[route]), data); $('#token-result').textContent = r.message; if (route === 'verify' && account) { const me = await api('/auth/me'); account = me.user; } if (route === 'reset') { account = null; csrf = ''; updateAccount(); } } catch (e) { $('#token-result').textContent = e.message; } };
    return;
  }
  accountRender();
};
const accountUpdate = updateAccount;
updateAccount = function() { accountUpdate(); if (account) applyTheme(account.theme || 'system'); };
