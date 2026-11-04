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
/* Country, region and city: searchable dropdowns (assets/select.js). Regions and cities follow the chosen
   country, cities the chosen region (GeoNames data from /api/countries/{code}/locations). Region and city
   also accept text that is not in the list. */
function countryField(value='', required=false) {
  return uiSelect({name:'country', label:'Country', value, required, searchable:true, placeholder:'Search countries…', className:'cf-select-field', attrs:'data-location="country"', options:accountCountries.map(c => [c.code, c.name])});
}
function regionField(value='', {required=false}={}) {
  return uiSelect({name:'region', label:contactNames.region + (required ? '' : ' (optional)'), value, required, searchable:true, freeText:true, placeholder:'Search regions…', className:'cf-select-field', attrs:'data-location="region"', options:value ? [[value, value]] : []});
}
function cityField(value='', {required=false}={}) {
  return uiSelect({name:'city', label:contactNames.city + (required ? '' : ' (optional)'), value, required, searchable:true, freeText:true, placeholder:'Search cities…', className:'cf-select-field', attrs:'data-location="city"', options:value ? [[value, value]] : []});
}
const locationCache = {};
function ensureLocations(code) {
  if (!code) return Promise.resolve({regions:[], cities:[]});
  return locationCache[code] ||= api(`/countries/${encodeURIComponent(code)}/locations`).catch(e => { delete locationCache[code]; throw e; });
}

function passwordField(name='password', label='Password') { return `<label>${label}<input name="${name}" type="password" minlength="8" maxlength="128" required autocomplete="new-password" data-policy></label><button type="button" class="btn-ghost btn-sm password-toggle">Show password</button><p class="password-rules" aria-live="polite">At least 8 characters · One uppercase letter · One number</p>`; }
function bindAccountFields(root=document) {
  root.querySelectorAll('[data-location=country]:not([data-bound])').forEach(bindLocationFields);
  root.querySelectorAll('[data-policy]:not([data-bound])').forEach(input => {
    input.dataset.bound = 1; const form = input.closest('form');
    input.oninput = () => { const checks = [input.value.length >= 8, /[A-Z]/.test(input.value), /[0-9]/.test(input.value)]; input.setCustomValidity(checks.every(Boolean) ? '' : 'Use at least 8 characters, an uppercase letter and a number.'); form.querySelector('.password-rules').textContent = checks.map((ok, i) => `${ok ? '✓' : '○'} ${['8 characters', 'Uppercase letter', 'Number'][i]}`).join(' · '); };
    form.querySelector('.password-toggle').onclick = e => { input.type = input.type === 'password' ? 'text' : 'password'; e.target.textContent = input.type === 'password' ? 'Show password' : 'Hide password'; };
  });
  root.querySelectorAll('[data-username]:not([data-bound])').forEach(input => {
    input.dataset.bound = 1; let timer, seq = 0;
    input.addEventListener('input', () => { clearTimeout(timer); const n = ++seq; input.setCustomValidity(''); timer = setTimeout(async () => { try { const r = await api('/auth/username?username=' + encodeURIComponent(input.value)); if (n !== seq) return; input.setCustomValidity(r.available ? '' : 'Username is unavailable or invalid'); input.closest('form').querySelector('.username-status').textContent = r.available ? 'Username available' : 'Username unavailable or invalid' + (input.form?.id === 'real-register' ? '. If it is yours and your email is not confirmed yet, sign in to ask for a new link.' : ''); } catch (e) { showError(e); } }, 300); });
  });

}
function bindLocationFields(countryRoot) {
  countryRoot.dataset.bound = 1;
  const scope = countryRoot.closest('form, fieldset, .fields') || countryRoot.parentElement;
  const region = scope.querySelector('[data-location=region]'), city = scope.querySelector('[data-location=city]');
  let data = {regions:[], cities:[]}, seq = 0;
  const regionCode = () => data.regions.find(r => r.name === uiSelectValue(region))?.code;
  // Cities are rows [name, region code, aliases?]; the region narrows them, aliases ("Torino") only help searching.
  const fillCities = () => {
    if (!city) return;
    const code = regionCode(), seen = new Set();
    uiSelectSetOptions(city, data.cities.filter(c => (!code || c[1] === code) && !seen.has(c[0]) && seen.add(c[0])).map(([n, , aliases]) => [n, n, aliases]));
  };
  const load = async (reset) => {
    const n = ++seq, code = uiSelectValue(countryRoot);
    if (reset) { if (region) uiSelectSet(region, ''); if (city) uiSelectSet(city, ''); }
    try { data = await ensureLocations(code); } catch (e) { data = {regions:[], cities:[]}; }
    if (n !== seq) return;
    if (region) uiSelectSetOptions(region, data.regions.map(r => [r.name, r.name]));
    fillCities();
  };
  countryRoot.querySelector('input[type=hidden]').addEventListener('change', () => load(true));
  region?.querySelector('input[type=hidden]').addEventListener('change', () => {
    // A city that belongs to another region is cleared; one typed by hand is kept.
    const code = regionCode(), known = data.cities.find(c => c[0] === uiSelectValue(city));
    if (city && code && known && !data.cities.some(c => c[0] === known[0] && c[1] === code)) uiSelectSet(city, '');
    fillCities();
  });
  load(false);
}
async function accountAction(path, body, method='POST') { const r = await api(path, {method, body:JSON.stringify(body)}); if (r.message) toast(r.message); return r; }

/* Signed-out: sign in and registration side by side. */
/* Sign-in through an external provider. Shown only when the server has it configured. */
const GOOGLE_MARK = '<svg viewBox="0 0 48 48" width="18" height="18" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';
const googleBlock = () => `<div class="google-signin" hidden><a class="google-btn" href="/api/auth/google/start">${GOOGLE_MARK}<span>Continue with Google</span></a><p class="auth-separator"><span>or continue with email</span></p></div>`;
let authProviders = null;
function revealProviders() {
  authProviders ||= api('/auth/providers').catch(() => ({}));
  authProviders.then(p => { if (p.google) document.querySelectorAll('.google-signin').forEach(block => { block.hidden = false; }); });
}
const AUTH_MESSAGES = {
  email_exists:'An OpenLabs3D account already uses this email address. Sign in with your password, or reset it, then connect Google from Account settings. Accounts are never joined automatically.',
  email_not_verified:'Google has not verified this email address, so we cannot create an account with it.',
  sign_in_failed:'We could not complete the sign-in with Google. Please try again.', sign_in_cancelled:'The sign-in with Google was cancelled.',
  account_unavailable:'This account cannot be used right now. Contact the site administrator.', try_again:'Please try again.',
  link_session:'Connecting Google needs the session that started it. Please try again.', identity_in_use:'This Google account is already connected to another OpenLabs3D account.',
  already_connected:'A Google account is already connected.', google_connected:'Google is connected. You can now sign in with it too.',
};
function showAuthMessage() {
  const params = new URLSearchParams(location.hash.split('?')[1] || ''), code = params.get('auth_error'), notice = params.get('auth_notice');
  if (!code && !notice) return;
  // The code only selects one of the messages above: nothing from the address reaches the page.
  const text = AUTH_MESSAGES[code || notice] || AUTH_MESSAGES.sign_in_failed;
  history.replaceState(history.state, '', '#account');
  document.querySelector('.auth-grid, .settings-head')?.insertAdjacentHTML(account ? 'afterend' : 'beforebegin', `<div class="banner ${code ? 'warning' : 'info'}" id="auth-message" role="alert"><span>${esc(text)}</span></div>`);
}

function authPage() {
  const register = new URLSearchParams(location.hash.split('?')[1] || '').get('mode') === 'register';
  return layout(`<div class="auth-layout"><header class="auth-head"><h1>${register ? 'Create your account' : 'Welcome to OpenLabs3D'}</h1><p class="muted">Order laboratory tools made by independent printing hosts, or apply to print them yourself.</p></header><div class="auth-grid ${register ? 'register-first' : ''}"><form id="real-login" class="section-card auth-card"><h2>Sign in</h2>${googleBlock()}<label>Email<input name="email" type="email" required autocomplete="email"></label><label>Password<input name="password" type="password" required autocomplete="current-password"></label><button class="primary">Sign in</button><p><a class="textlink" href="#forgot-password">Forgot password?</a></p></form><form id="real-register" class="section-card auth-card"><h2>Create an account</h2>${googleBlock()}<label>Username<input name="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+" autocomplete="username" data-username></label><p class="username-status hint" aria-live="polite">3–32 letters, numbers or underscores; case-insensitive.</p><label>Email<input name="email" type="email" required autocomplete="email"></label>${passwordField()}<button class="primary">Create account</button></form></div></div>`);
}

/* Email verification: the pages after registering, the link from the email, and the resend form. */
const VERIFY_EMAIL_KEY = 'ol3d-verify-email', MAIL_CAPTURE_KEY = 'ol3d-mail-capture';
// Development only: the server names this only when mail is captured locally instead of being delivered.
const mailCaptureNote = url => url ? `<div class="banner info" id="mail-capture"><span><strong>Development:</strong> email is captured locally and does not reach real inboxes.</span><a class="btn-ghost btn-sm" href="${esc(url)}" target="_blank" rel="noopener">Open Mailpit</a></div>` : '';
const rememberedMailCapture = () => { try { return sessionStorage.getItem(MAIL_CAPTURE_KEY) || ''; } catch (e) { return ''; } };
function showMailCapture(url, after) {
  if (!url || $('#mail-capture')) return;
  try { sessionStorage.setItem(MAIL_CAPTURE_KEY, url); } catch (e) {}
  after.insertAdjacentHTML('afterend', mailCaptureNote(url));
}
let verifyLink = null, verifyRedirect = 0;
const rememberedVerifyEmail = () => { try { return sessionStorage.getItem(VERIFY_EMAIL_KEY) || ''; } catch (e) { return ''; } };
function waitToResend(button, seconds, label) {
  let left = seconds || 0;
  const tick = () => {
    if (!button.isConnected) return;
    button.disabled = left > 0; button.textContent = left > 0 ? `${label} (${left} s)` : label;
    if (left-- > 0) setTimeout(tick, 1000);
  };
  tick();
}
const resendForm = (email, buttonClass='primary') => `<form id="resend-form" novalidate>${email ? `<input type="hidden" name="email" value="${esc(email)}">` : '<label>Email<input name="email" type="email" required autocomplete="email"></label>'}<button class="${buttonClass}" id="resend-button">Resend Verification Email</button><p class="form-status" id="resend-status" role="status"></p></form>`;
function bindResendForm(cooldown=0) {
  const form = $('#resend-form'); if (!form) return;
  const button = $('#resend-button'), status = $('#resend-status'), label = 'Resend Verification Email';
  if (cooldown) waitToResend(button, cooldown, label);
  form.onsubmit = async e => {
    e.preventDefault();
    if (!form.reportValidity()) return;
    button.disabled = true;
    try { const r = await api('/auth/resend-verification', {method:'POST', body:JSON.stringify({email:form.email.value.trim()})}); status.classList.remove('error'); status.textContent = r.message; waitToResend(button, r.resend_after, label); showMailCapture(r.mail_capture_url, form); }
    catch (err) { status.classList.add('error'); status.textContent = err.message; button.disabled = false; }
  };
}
const authMessage = (title, body) => layout(`<div class="auth-layout"><section class="section-card auth-card auth-message" aria-labelledby="auth-message-title"><h1 id="auth-message-title" tabindex="-1">${title}</h1>${body}</section></div>`);
const toSignIn = (label='Back to sign in') => `<p class="auth-links"><a class="textlink" href="#account">${label}</a></p>`;
function checkInboxPage() {
  const email = rememberedVerifyEmail();
  return authMessage('Check your inbox', `<p>We've sent a verification link to ${email ? `<strong>${esc(email)}</strong>` : 'your email address'}. Please verify your email to activate your OpenLabs3D account.</p><p class="muted">If it doesn't arrive in a few minutes, check your spam folder or ask for a new one.</p>${mailCaptureNote(rememberedMailCapture())}${resendForm(email)}${toSignIn()}`);
}
function showVerificationPage(html, cooldown=0) {
  $('#app').innerHTML = html; bindResendForm(cooldown); document.title = $('#auth-message-title').textContent + ' · OpenLabs3D';
  $('#auth-message-title').focus({preventScroll:true}); window.scrollTo(0, 0);
}
function showCheckInbox(data) {
  try { sessionStorage.setItem(VERIFY_EMAIL_KEY, data.email); if (data.mail_capture_url) sessionStorage.setItem(MAIL_CAPTURE_KEY, data.mail_capture_url); } catch (e) {}
  history.pushState(history.state, '', '#check-inbox');
  showVerificationPage(checkInboxPage(), data.resend_after);
}
// Sign-in with the right password on an account that has not confirmed its address.
function showLoginVerification(form, detail) {
  form.querySelector('#login-verify')?.remove(); form.querySelector('#mail-capture')?.remove();
  const email = form.email.value.trim(), notice = document.createElement('div');
  notice.className = 'banner warning'; notice.id = 'login-verify'; notice.setAttribute('role', 'alert');
  notice.innerHTML = `<span><strong>Please verify your email address before signing in.</strong> Open the link we sent you, or ask for a new one.</span><button type="button" class="btn-ghost btn-sm" id="login-resend">Resend Verification Email</button><p class="form-status" id="login-resend-status" role="status"></p>`;
  form.querySelector('button.primary').before(notice);
  showMailCapture(detail?.mail_capture_url, notice);
  const button = notice.querySelector('#login-resend'), status = notice.querySelector('#login-resend-status');
  button.onclick = async () => {
    button.disabled = true;
    try { const r = await api('/auth/resend-verification', {method:'POST', body:JSON.stringify({email})}); status.textContent = r.message; waitToResend(button, r.resend_after, 'Resend Verification Email'); }
    catch (err) { status.textContent = err.message; button.disabled = false; }
  };
}
const VERIFY_RESULTS = {
  verified: r => authMessage('Email verified', `<p>${esc(r.message)}</p><p class="muted">${r.signed_in ? 'Taking you to your account…' : 'Taking you to sign in…'}</p><a class="btn" href="#account">${r.signed_in ? 'Go to your account' : 'Sign in'}</a>`),
  email_changed: r => authMessage('Email address changed', `<p>Your email address is now <strong>${esc(r.email)}</strong>. Use it to sign in from now on.</p><p class="muted">${r.signed_in ? 'Taking you to your account…' : 'Taking you to sign in…'}</p><a class="btn" href="#account">${r.signed_in ? 'Go to your account' : 'Sign in'}</a>`),
  expired: () => authMessage('This link has expired', `<p>Verification links only work for a limited time. Enter your email address and we will send a new one.</p>${resendForm(rememberedVerifyEmail())}${toSignIn()}`),
  invalid: () => authMessage('This link isn\'t valid', `<p>It may be incomplete, or a newer email may have replaced it. Use the link in your newest email, or ask for a new one.</p>${resendForm(rememberedVerifyEmail())}${toSignIn()}`),
  used: () => authMessage('This link has already been used', `<p>Your email address has been confirmed with it. You can sign in.</p><a class="btn" href="#account">Sign in</a>`),
  conflict: e => authMessage('This address can\'t be used', `<p>${esc(e.message)}</p><a class="btn" href="#account">Account settings</a>`),
  unavailable: e => authMessage('We couldn\'t check this link', `<p>${esc(e.message)}</p><button class="primary" id="verify-again">Try again</button>`),
};
// The token leaves the address as soon as it is read, so it does not stay in the browser history.
function verifyEmailPage() {
  const token = new URLSearchParams(location.hash.split('?')[1] || '').get('token');
  if (token) { verifyLink = {token}; history.replaceState(history.state, '', '#verify-email'); }
  if (!verifyLink) return showVerificationPage(VERIFY_RESULTS.invalid());
  if (verifyLink.result) return showVerificationPage(verifyLink.result);
  if (!verifyLink.started) redeemVerifyLink();
  showVerificationPage(authMessage('Verifying your email…', '<p class="muted">This only takes a moment.</p>'));
}
async function redeemVerifyLink() {
  const current = verifyLink; current.started = true;
  let html;
  try {
    const r = await api('/auth/verify', {method:'POST', body:JSON.stringify({token:current.token})});
    try { sessionStorage.removeItem(VERIFY_EMAIL_KEY); } catch (e) {}
    if (account) { account = (await api('/auth/me')).user; renderNavbar(); }
    html = VERIFY_RESULTS[r.status](r);
    clearTimeout(verifyRedirect);
    verifyRedirect = setTimeout(() => { if (currentRoute() === 'verify-email') location.hash = 'account'; }, 4000);
  } catch (e) {
    const known = ['expired', 'invalid', 'used', 'conflict'].includes(e.detail?.code);
    html = VERIFY_RESULTS[known ? e.detail.code : 'unavailable'](e);
    if (!known) current.started = false;
  }
  if (verifyLink !== current) return;
  current.result = current.started ? html : null;
  if (currentRoute() !== 'verify-email') return;
  showVerificationPage(html);
  const again = $('#verify-again'); if (again) again.onclick = () => { showVerificationPage(authMessage('Verifying your email…', '<p class="muted">This only takes a moment.</p>')); redeemVerifyLink(); };
}

/* Signed-in: one Account Settings page. */
function avatarFieldHtml() {
  const picture = profilePictureFor(account);
  // The design itself happens in the avatar editor (assets/avatar-editor.js); the page stays compact.
  return `<div class="avatar-field" id="avatar-field"><button type="button" class="avatar-button" id="avatar-pick" aria-haspopup="dialog" aria-describedby="avatar-help">${avatarHtml(account, 80, 'avatar-lg')}<span class="avatar-overlay" aria-hidden="true">${icon('pencil')}</span><span class="sr-only">Change profile picture</span></button><div class="avatar-copy"><strong>Profile picture</strong><p id="avatar-help">${picture.kind === 'photo' ? 'Your uploaded photo.' : picture.kind === 'avatar' ? 'Your scientific avatar.' : 'Your initials, until you choose a picture.'} Upload a photo or create an avatar.</p><div class="avatar-actions"><button type="button" class="btn-ghost btn-sm" id="avatar-edit" aria-haspopup="dialog">${icon('pencil')}Change picture</button></div><p class="avatar-status" id="avatar-status" role="status" aria-live="polite"></p></div></div>`;
}
const settingsCard = (id, title, text, body, extra='') => `<section class="settings-card" id="settings-${id}" aria-labelledby="settings-${id}-title"><div class="settings-card-head"><div><h2 id="settings-${id}-title">${title}</h2><p>${text}</p></div>${extra}</div>${body}</section>`;
const formFooter = label => `<div class="form-footer"><p class="form-status" role="status"></p><button class="primary" disabled>${label}</button></div>`;
const revealButton = (target, label) => `<button type="button" class="btn-ghost btn-sm" data-reveal="${target}" aria-expanded="false" aria-controls="${target}">${label}</button>`;
function profileSection() {
  return settingsCard('profile', 'Profile', 'How you appear on OpenLabs3D and how you sign in.', `<div class="settings-card-body">${avatarFieldHtml()}<form id="account-profile" class="settings-form"><div class="fields"><label>Username<input name="username" value="${esc(account.username)}" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+" autocomplete="username" data-username><small class="hint username-status" aria-live="polite">Letters, numbers and underscores. Shown as the seller on your listings.</small></label></div>${formFooter('Save profile')}</form><div class="settings-rows"><div class="settings-row"><div><span class="settings-label">Email</span><span class="settings-value">${esc(account.email)} ${account.email_verified ? statusBadge('approved', 'Verified') : statusBadge('pending', 'Not verified')}</span></div>${revealButton('email-form', 'Change')}</div>${account.pending_email ? `<div class="banner info" id="email-pending" role="status"><span>Waiting for confirmation of <strong>${esc(account.pending_email)}</strong>. Your current address stays active until you open the link sent there.</span><button type="button" class="btn-ghost btn-sm" id="email-change-cancel">Cancel change</button></div>` : ''}<form id="email-form" class="inline-form" hidden><div class="fields"><label>New email<input name="email" type="email" required autocomplete="email"></label><label>Current password<input name="current_password" type="password" required autocomplete="current-password"></label></div><p class="hint">We will send a confirmation link to the new address. Your current address stays active until you confirm it.</p><div class="form-footer"><button type="button" class="secondary" data-reveal="email-form">Cancel</button><button class="primary">Change email</button></div></form><div class="settings-row"><div><span class="settings-label">Account type</span><span class="settings-value">${esc(roleLabel(account.role))}</span></div></div><div class="settings-row"><div><span class="settings-label">Appearance</span><span class="settings-value muted">Applies immediately and is saved to your account.</span></div>${themeToggle()}</div></div></div>`);
}
function contactSection() {
  return settingsCard('contact', 'Contact information', 'Used for order requests and printing host applications. A host sees it only after accepting your job.', `<form id="account-contact" class="settings-card-body settings-form"><div class="fields">${textField('first_name', account.first_name)}${textField('last_name', account.last_name)}${textField('phone', account.phone)}${countryField(account.country)}${regionField(account.region)}${cityField(account.city)}</div>${formFooter('Save contact information')}</form>`);
}
const addressLines = a => [[a.first_name, a.last_name].filter(Boolean).join(' '), a.street, a.additional, [a.postal_code, a.city].filter(Boolean).join(' ') + (a.region ? ', ' + a.region : ''), countryLabel(a.country)].filter(Boolean);
function addressCard(a) {
  const name = esc(a.label || 'Address');
  return `<article class="address-card ${a.is_default ? 'is-default' : ''}"><div class="address-card-head"><span class="address-label">${name}</span>${a.is_default ? statusBadge('approved', 'Default') : ''}</div><address>${addressLines(a).map(esc).join('<br>')}</address><p class="address-phone">${esc(a.phone)}</p><div class="address-card-actions"><button type="button" class="btn-ghost btn-sm" data-address-edit="${a.id}" aria-label="Edit ${name}">Edit</button>${a.is_default ? '' : `<button type="button" class="btn-ghost btn-sm" data-address-default="${a.id}" aria-label="Set ${name} as default">Set as default</button>`}<button type="button" class="btn-ghost btn-sm danger-text" data-address-delete="${a.id}" aria-label="Delete ${name}">Delete</button></div></article>`;
}
function addressForm(a={}) {
  const v = {first_name:account.first_name, last_name:account.last_name, phone:account.phone, country:account.country, city:account.city, ...a}, locked = a.is_default || !savedAddresses.length;
  return `<form class="address-card address-form" id="address-form" data-id="${a.id || 0}" aria-labelledby="address-form-title"><h3 id="address-form-title">${a.id ? 'Edit address' : 'New address'}</h3><div class="fields">${textField('first_name', v.first_name, {required:true})}${textField('last_name', v.last_name, {required:true})}${textField('street', v.street, {required:true, wide:true})}${textField('additional', v.additional, {optional:true, wide:true})}${countryField(v.country, true)}${regionField(v.region, {required:true})}${cityField(v.city, {required:true})}${textField('postal_code', v.postal_code, {required:true})}${textField('phone', v.phone, {required:true})}<label>Label <span class="optional">optional</span><input name="label" maxlength="40" list="address-label-options" placeholder="Laboratory, Home, Work…" value="${esc(a.label || '')}"></label></div><datalist id="address-label-options"><option value="Laboratory"><option value="Home"><option value="Work"></datalist><label class="check"><input type="checkbox" name="is_default" ${locked ? 'checked disabled' : ''}> Use as my default address${!savedAddresses.length ? ' <span class="hint">(your first address is the default)</span>' : ''}</label><p class="form-error" role="alert"></p><div class="form-footer"><button type="button" class="secondary" data-address-cancel>Cancel</button><button class="primary">Save address</button></div></form>`;
}
function addressGridHtml() {
  if (savedAddresses === null) return '<p class="muted" role="status">Loading addresses…</p>';
  const cards = savedAddresses.map(a => addressEditing === a.id ? addressForm(a) : addressCard(a));
  if (addressEditing === 0) cards.unshift(addressForm());
  return cards.join('') || `<div class="address-empty">${emptyState('No saved addresses', 'Save a delivery address to check out faster.', `<button type="button" class="btn btn-sm" data-address-new>${icon('plus')}Add address</button>`)}</div>`;
}
function addressSection() { return settingsCard('addresses', 'Saved addresses', 'Choose one at checkout. Your default address is preselected.', `<div class="settings-card-body"><div class="address-grid" id="address-grid">${addressGridHtml()}</div></div>`, `<button type="button" class="btn-ghost btn-sm" id="address-add" data-address-new hidden>${icon('plus')}Add address</button>`); }
function securitySection() {
  return settingsCard('security', 'Security & Sign-In Methods', 'How you sign in, and how your account stays protected.', `<div class="settings-card-body"><div class="settings-rows"><div class="settings-row" id="password-row"><div><span class="settings-label">Email &amp; password</span><span class="settings-value muted" id="password-state">Changing your password signs out your other sessions.</span></div><span id="password-action">${revealButton('password-form', 'Change password')}</span></div><form id="password-form" class="inline-form" hidden><div class="fields"><label>Current password<input name="current_password" type="password" required autocomplete="current-password"></label><div>${passwordField('password', 'New password')}</div></div><div class="form-footer"><button type="button" class="secondary" data-reveal="password-form">Cancel</button><button class="primary">Update password</button></div></form><div id="sign-in-methods"></div></div></div>`);
}
function dangerSection() {
  return `<details class="settings-card danger-zone" id="settings-delete"><summary><span><strong>Delete account</strong><span class="muted">Permanently remove your account and sign out everywhere.</span></span>${icon('chevron')}</summary><div class="settings-card-body"><p>Accounts with listings, orders, printing jobs or custom requests cannot be deleted while those records exist. Your host application and active sessions are removed.</p><form class="delete-account-form" data-id="${account.id}" data-self="true"><label>Confirm with your password<input name="password" type="password" maxlength="128" autocomplete="current-password" required></label><p class="delete-account-error form-error" role="alert"></p><button class="danger">Delete my account</button></form></div></details>`;
}
/* Host only: read-only summary filled from approved equipment and the material inventory (edited in My equipment). */
function equipmentSummarySection() {
  return settingsCard('equipment', 'Printing equipment', 'Filled in automatically from your approved equipment and materials.', '<div class="settings-card-body" id="equipment-summary"><p class="muted" role="status">Loading equipment…</p></div>', '<a class="btn-ghost btn-sm" href="#my-printers">Edit in My equipment</a>');
}
async function fillEquipmentSummary() {
  const box = $('#equipment-summary'); if (!box) return;
  try {
    const [printers, inventory] = await Promise.all([api('/host/equipment'), api('/host/materials')]);
    if (!box.isConnected) return;
    const units = printers.reduce((n, p) => n + p.quantity, 0), materials = Object.entries(inventory.material_colors);
    const rows = printers.map(p => `<li class="es-printer">${printerArt(p, 'sm')}<span><strong>${esc(printerName(p))}${p.quantity > 1 ? ` <span class="eq-qty">× ${p.quantity}</span>` : ''}</strong><small><span class="eq-tech">${techLabel(p.technology)}</span> ${volumeText(p)}</small></span></li>`).join('');
    const stock = materials.map(([m, colors]) => `<li class="es-material"><strong>${esc(m)}</strong><span class="eq-dots">${Object.entries(colors).map(([n, h]) => colorDot(h, n)).join('') || '<span class="eq-muted">No colors</span>'}</span></li>`).join('');
    box.innerHTML = `<div class="es-grid"><section><p class="eq-label">Printers · ${printers.length} model${printers.length === 1 ? '' : 's'}, ${units} unit${units === 1 ? '' : 's'}</p>${rows ? `<ul class="es-list">${rows}</ul>` : '<p class="eq-muted">No approved printers yet.</p>'}</section><section><p class="eq-label">Materials &amp; colors</p>${stock ? `<ul class="es-list">${stock}</ul>` : '<p class="eq-muted">No materials listed yet.</p>'}</section></div>`;
  } catch (e) { box.innerHTML = `<p class="form-error">${esc(e.message)}</p>`; }
}
function accountPage() {
  if (!account) return authPage();
  document.title = 'Account settings · ' + (publicSettings.marketplace_name || 'OpenLabs3D');
  const checkout = sessionStorage.getItem('checkout-return-' + account.id);
  const banners = (!account.email_verified ? `<div class="banner warning" role="status"><span><strong>Verify your email address.</strong> A verified email is required to order, apply as a printing host or create listings.</span><button type="button" class="btn-ghost btn-sm" id="resend-verification">Send verification email</button></div>` : '')
    + (checkout ? `<div class="banner info" id="checkout-banner"><span>Your checkout is saved. Return to it when your details are complete.</span><a class="btn btn-sm" href="#${checkout === 'checkout' ? 'checkout' : 'checkout-cart'}">Return to checkout</a><button type="button" class="icon-btn" id="dismiss-checkout" aria-label="Dismiss">${icon('close')}</button></div>` : '');
  return layout(`<div class="settings"><header class="settings-head"><h1>Account settings</h1><p class="muted">Your profile, contact details and delivery addresses in one place.</p></header>${banners}${profileSection()}${account.role === 'host' ? equipmentSummarySection() : ''}${contactSection()}${addressSection()}${securitySection()}${dangerSection()}</div>`);
}

/* Behaviour */
function refreshAvatarField() { const field = $('#avatar-field'); if (!field) return; field.outerHTML = avatarFieldHtml(); bindAvatar(); renderNavbar(); }
function bindAvatar() {
  const field = $('#avatar-field'); if (!field) return;
  $('#avatar-pick').onclick = $('#avatar-edit').onclick = () => openAvatarEditor();
  // Dropping an image opens the editor with that photo ready to save.
  field.ondragenter = field.ondragover = e => { e.preventDefault(); field.classList.add('dragging'); };
  field.ondragleave = e => { if (!field.contains(e.relatedTarget)) field.classList.remove('dragging'); };
  field.ondrop = e => { e.preventDefault(); field.classList.remove('dragging'); const file = e.dataTransfer.files[0]; if (file) openAvatarEditor({file}); };
}
function bindProfileForm(form, extra={}) {
  const button = form.querySelector('.form-footer .primary'), status = form.querySelector('.form-status');
  form.addEventListener('input', () => { button.disabled = false; status.textContent = ''; status.classList.remove('error'); });
  form.onsubmit = async e => {
    e.preventDefault(); button.disabled = true; status.textContent = 'Saving…';
    try {
      account = await api('/profile', {method:'PATCH', body:JSON.stringify({username:account.username, ...Object.fromEntries(new FormData(form)), ...extra})});
      status.textContent = 'Saved'; renderNavbar(); refreshProfilePictures(account);
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
async function fillSignInMethods() {
  const root = $('#sign-in-methods'); if (!root) return;
  let m; try { m = await api('/auth/sign-in-methods'); } catch (e) { return; }
  if (!root.isConnected) return;
  if (!m.password) {
    $('#password-state').textContent = 'Not set. Google manages the password you sign in with.';
    $('#password-action').innerHTML = '<button type="button" class="btn-ghost btn-sm" id="password-link">Set a password</button>';
    $('#password-link').onclick = async e => { e.target.disabled = true; try { await accountAction('/auth/password-link', {}); } catch (err) { showError(err); } e.target.disabled = false; };
  }
  const google = m.providers.find(p => p.name === 'google');
  const confirm = (id, label) => `<form id="${id}" class="inline-form" hidden><div class="fields"><label>Confirm with your password<input name="password" type="password" required autocomplete="current-password"></label></div><p class="form-error" role="alert"></p><div class="form-footer"><button type="button" class="secondary" data-reveal="${id}">Cancel</button><button class="primary">${label}</button></div></form>`;
  let row = '';
  if (google.connected) row = `<div class="settings-row"><div><span class="settings-label">Google</span><span class="settings-value">${esc(google.email)} ${statusBadge('approved', 'Connected')}</span></div>${m.password ? revealButton('google-disconnect', 'Disconnect Google') : ''}</div>${m.password ? confirm('google-disconnect', 'Disconnect Google') : '<p class="hint">Set a password before disconnecting Google: it is your only way to sign in.</p>'}`;
  else if (google.available) row = `<div class="settings-row"><div><span class="settings-label">Google</span><span class="settings-value muted">Not connected</span></div>${revealButton('google-connect', 'Connect Google')}</div>${confirm('google-connect', 'Continue to Google')}`;
  root.innerHTML = row + `<div class="settings-row"><div><span class="settings-label">Sessions</span><span class="settings-value muted">Signed in on ${m.sessions} ${m.sessions === 1 ? 'device or browser' : 'devices or browsers'}.</span></div>${m.sessions > 1 ? '<button type="button" class="btn-ghost btn-sm" id="sign-out-others">Sign out others</button>' : ''}</div>`;
  const send = (id, path, done) => { const form = $('#' + id); if (form) form.onsubmit = async e => { e.preventDefault(); const error = form.querySelector('.form-error'), button = form.querySelector('.primary'); button.disabled = true; error.textContent = ''; try { done(await api(path, {method:'POST', body:JSON.stringify({password:form.password.value})})); } catch (err) { error.textContent = err.message; button.disabled = false; } }; };
  send('google-connect', '/auth/google/connect', r => { location.href = r.url; });
  send('google-disconnect', '/auth/google/disconnect', r => { toast(r.message); fillSignInMethods(); });
  const others = $('#sign-out-others'); if (others) others.onclick = async () => { try { await accountAction('/auth/sessions/sign-out-others', {}); fillSignInMethods(); } catch (e) { showError(e); } };
}
function bindAccountPage() {
  bindMarketplace(); bindAccountFields(); bindOperations(); showAuthMessage();
  if (!account) { revealProviders(); if (new URLSearchParams(location.hash.split('?')[1] || '').get('mode') === 'register') $('#real-register input')?.focus(); return; }
  fillSignInMethods(); bindAvatar(); bindProfileForm($('#account-profile')); bindProfileForm($('#account-contact')); bindAddresses(); fillEquipmentSummary();
  $('#address-add').hidden = !savedAddresses?.length;
  $('#app .settings').addEventListener('click', e => {
    const trigger = e.target.closest('[data-reveal]'); if (!trigger) return;
    const form = document.getElementById(trigger.dataset.reveal), open = form.hidden;
    form.hidden = !open; if (!open) form.reset();
    document.querySelectorAll(`[aria-controls="${form.id}"]`).forEach(b => b.setAttribute('aria-expanded', open));
    if (open) form.querySelector('input')?.focus(); else document.querySelector(`[aria-controls="${form.id}"]`)?.focus();
  });
  const resend = $('#resend-verification'); if (resend) resend.onclick = async () => { resend.disabled = true; try { const r = await accountAction('/auth/resend-verification', {email:account.email}); waitToResend(resend, r.resend_after, 'Send verification email'); showMailCapture(r.mail_capture_url, resend.closest('.banner')); } catch (e) { showError(e); resend.disabled = false; } };
  const cancelChange = $('#email-change-cancel'); if (cancelChange) cancelChange.onclick = async () => { try { await api('/auth/change-email', {method:'DELETE'}); account = (await api('/auth/me')).user; toast('Email change cancelled'); render(); } catch (e) { showError(e); } };
  const dismiss = $('#dismiss-checkout'); if (dismiss) dismiss.onclick = () => { sessionStorage.removeItem('checkout-return-' + account.id); $('#checkout-banner').remove(); };
  const email = $('#email-form'); email.onsubmit = async e => { e.preventDefault(); try { const r = await accountAction('/auth/change-email', Object.fromEntries(new FormData(email))); account = (await api('/auth/me')).user; renderNavbar(); render(); if (r.mail_capture_url) setTimeout(() => { const place = $('#email-pending') || $('#settings-profile .settings-rows .settings-row'); if (place) showMailCapture(r.mail_capture_url, place); }, 400); } catch (err) { showError(err); } };
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
  if (route === 'check-inbox') return showVerificationPage(checkInboxPage());
  if (route === 'verify-email' || route === 'verify') return verifyEmailPage();
  if (['reset', 'forgot-password'].includes(route)) {
    const token = new URLSearchParams(location.hash.split('?')[1] || '').get('token') || '';
    $('#app').innerHTML = layout(`<div class="auth-layout"><form id="token-form" class="section-card auth-card"><h1>${route === 'reset' ? 'Choose a new password' : 'Reset your password'}</h1>${route === 'forgot-password' ? '<p class="muted">Enter your account email and we will send a reset link.</p><label>Email<input name="email" type="email" required autocomplete="email"></label>' : passwordField()}<button class="primary">Continue</button><p id="token-result" role="status"></p></form></div>`);
    bindAccountFields();
    $('#token-form').onsubmit = async e => { e.preventDefault(); try { const data = Object.fromEntries(new FormData(e.target)); if (route !== 'forgot-password') data.token = token; const r = await accountAction('/auth/' + ({reset:'reset-password', 'forgot-password':'forgot-password'}[route]), data); $('#token-result').textContent = r.message; if (route === 'reset') { account = null; csrf = ''; updateAccount(); } } catch (e) { $('#token-result').textContent = e.message; } };
    return;
  }
  accountRender();
};
const accountUpdate = updateAccount;
updateAccount = function() { accountUpdate(); if (account) applyTheme(account.theme || 'system'); };
