/* One local draft, one save request. Closing the popup never writes account data. */
Object.assign(iconPaths, {
  pencil: '<path d="M4.5 19.5h4l10-10-4-4-10 10z"/><path d="m13 7 4 4"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>'
});
const AE_COLOR_NAMES = {'#386641':'Hunter green', '#6a994e':'Sage green', '#a7c957':'Yellow green', '#f2e8cf':'Vanilla cream', '#bc4749':'Blushed brick', '#d7e0d9':'Soft hunter green', '#e1eadc':'Soft sage green', '#edf4dd':'Soft yellow green', '#fcfaf5':'Soft vanilla cream', '#f2dadb':'Soft blushed brick'};
const ae = {stageId:0};

function openAvatarEditor({file} = {}) {
  if (!account || $('#avatar-editor')?.open) return;
  const picture = profilePictureFor(account), style = labAvatarStyle(picture.style);
  Object.assign(ae, {style:{...(style || AVATAR_START)}, mode:picture.kind === 'photo' ? 'photo' : style ? 'avatar' : 'photo', file:null, fileUrl:'', loading:false, saving:false, trigger:document.activeElement});
  let dialog = $('#avatar-editor');
  if (!dialog) {
    dialog = document.createElement('dialog'); dialog.id = 'avatar-editor'; dialog.className = 'ae-dialog'; dialog.setAttribute('aria-labelledby', 'ae-title');
    document.body.append(dialog); aeListen(dialog);
  }
  dialog.innerHTML = aeMarkup(); aePaint();
  document.documentElement.classList.add('ae-locked'); dialog.showModal();
  dialog.querySelector('input[name=ae-mode]:checked, input[name=ae-mode]')?.focus();
  if (file) aeStage(file);
}
function aeSwatches(key) {
  const list = key === 'fg' ? AVATAR_FOREGROUNDS : AVATAR_BACKGROUNDS, kind = key === 'fg' ? 'Pattern' : 'Background';
  return `<div class="ae-swatches">${list.map(c => `<label class="ae-swatch${avatarLuminance(c) > .5 ? ' is-light' : ''}" style="--swatch:${c}" title="${AE_COLOR_NAMES[c]}"><input type="radio" name="ae-${key}" value="${c}" aria-label="${kind} colour: ${AE_COLOR_NAMES[c]}"><span>${icon('check')}</span></label>`).join('')}</div>`;
}
function aeMarkup() {
  return `<form class="ae" novalidate>
    <header class="ae-head"><h2 id="ae-title">Change profile picture</h2><button type="button" class="icon-btn ae-close" data-ae-close aria-label="Close">${icon('close')}</button></header>
    <div class="ae-body">
      <div class="ae-stage">
        <div class="ae-preview" id="ae-preview" role="img" aria-label="Profile picture preview"></div>
        <p class="ae-caption">Live preview</p>
        <fieldset class="ae-mode"><legend class="sr-only">Picture method</legend><label><input type="radio" name="ae-mode" value="photo"><span>${icon('camera')}Upload Photo</span></label><label><input type="radio" name="ae-mode" value="avatar"><span>${icon('pencil')}Create Avatar</span></label></fieldset>
      </div>
      <div class="ae-panels">
        <p class="ae-hint" id="ae-intro">Choose a photo or create a scientific avatar. Your current picture stays until you save.</p>
        <div class="ae-panel" id="ae-custom" hidden>
          <fieldset class="ae-group"><legend>Choose design</legend><div class="ae-patterns">${Object.keys(AVATAR_VARIANTS).map(t => `<label class="ae-pattern"><input type="radio" name="ae-type" value="${t}" aria-label="${AVATAR_LABELS[t]}"><span class="ae-thumb" data-thumb="${t}"></span><span class="ae-name">${AVATAR_LABELS[t]}</span></label>`).join('')}</div></fieldset>
          <fieldset class="ae-group" id="ae-variation-group" hidden><legend>Molecule variation</legend><div class="ae-variants">${AVATAR_VARIANTS.molecule.map(v => `<label class="ae-variant"><input type="radio" name="ae-variant" value="${v}" aria-label="${AVATAR_VARIANT_LABELS[v]}"><span class="ae-thumb" data-variant="${v}"></span><span>${AVATAR_VARIANT_LABELS[v]}</span></label>`).join('')}</div></fieldset>
          <fieldset class="ae-group"><legend>Pattern colour</legend>${aeSwatches('fg')}</fieldset>
          <fieldset class="ae-group"><legend>Background colour</legend>${aeSwatches('bg')}</fieldset>
          <p class="ae-hint" id="ae-contrast" role="status">Choose any combination you like.</p>
        </div>
        <div class="ae-panel" id="ae-photo" hidden>
          <div class="ae-drop" data-ae-drop><p><strong id="ae-photo-label">Choose your photo</strong>Drop an image here or choose a file.<br>PNG, JPEG or WebP · Up to 2 MB</p><button type="button" class="btn-ghost btn-sm" data-ae-choose>${icon('camera')}Choose photo</button></div>
          <p class="ae-hint">Your photo fills the circular frame. It is uploaded only when you save.</p>
        </div>
      </div>
    </div>
    <div class="ae-foot"><p class="ae-status" id="ae-status" role="status"></p><div class="ae-actions"><button type="button" class="btn-ghost" data-ae-cancel>Cancel</button><button type="submit" class="primary" data-ae-save>Save</button></div></div>
    <input type="file" id="ae-file" accept="image/png,image/jpeg,image/webp" hidden>
  </form>`;
}
const aePhotoUrl = () => ae.fileUrl || profilePhotoUrl(account);
function aePaint() {
  const d = $('#avatar-editor'), s = ae.style;
  const preview = ae.mode === 'avatar' ? avatarHtml({...account, profile_picture:{kind:'avatar', style:s}}, 128) :
    ae.mode === 'photo' ? (aePhotoUrl() ? `<img src="${esc(aePhotoUrl())}" alt="">` : avatarHtml({...account, profile_picture:{kind:'initials'}}, 128)) : avatarHtml(account, 128);
  d.querySelector('#ae-preview').innerHTML = preview;
  for (const thumb of d.querySelectorAll('[data-thumb]')) { const type = thumb.dataset.thumb; thumb.innerHTML = labAvatarSvg({...s, type, variant:type === s.type ? s.variant : AVATAR_VARIANTS[type][0]}); }
  for (const thumb of d.querySelectorAll('[data-variant]')) thumb.innerHTML = labAvatarSvg({...s, type:'molecule', variant:thumb.dataset.variant});
  const check = (name, value) => d.querySelectorAll(`input[name=${name}]`).forEach(i => { i.checked = i.value === value; });
  check('ae-mode', ae.mode); check('ae-type', s.type); check('ae-variant', s.variant); check('ae-fg', s.foreground); check('ae-bg', s.background);
  d.querySelector('#ae-variation-group').hidden = s.type !== 'molecule';
  d.querySelector('#ae-custom').hidden = ae.mode !== 'avatar';
  d.querySelector('#ae-photo').hidden = ae.mode !== 'photo';
  d.querySelector('#ae-intro').hidden = !!ae.mode;
  d.querySelector('#ae-photo-label').textContent = ae.file ? ae.file.name : aePhotoUrl() ? 'Replace your photo' : 'Choose your photo';
  d.querySelector('[data-ae-save]').disabled = ae.loading || ae.saving || !ae.mode || (ae.mode === 'photo' && !aePhotoUrl());
}
function aeStatus(text, kind = '') { const s = $('#ae-status'); if (s) { s.textContent = text; s.className = 'ae-status ' + kind; } }
async function aeStage(file) {
  if (ae.saving) return;
  const stageId = ++ae.stageId;
  ae.loading = false;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || !file.size) { aePaint(); return aeStatus('Choose a valid PNG, JPEG or WebP image.', 'error'); }
  if (file.size > 2 * 1024 * 1024) { aePaint(); return aeStatus('Choose an image up to 2 MB.', 'error'); }
  ae.loading = true; aePaint(); aeStatus('Checking photo…');
  const url = URL.createObjectURL(file), img = new Image();
  try {
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = url; });
    if (stageId !== ae.stageId) return;
    if (img.naturalWidth * img.naturalHeight > 16000000) throw Error('Choose an image under 16 megapixels.');
    if (ae.fileUrl) URL.revokeObjectURL(ae.fileUrl);
    Object.assign(ae, {file, fileUrl:url, mode:'photo'}); aeStatus('');
  } catch (e) { if (stageId === ae.stageId) aeStatus(e.message || 'This image could not be opened. Choose another photo.', 'error'); }
  finally {
    if (ae.fileUrl !== url) URL.revokeObjectURL(url);
    if (stageId === ae.stageId) { ae.loading = false; aePaint(); }
  }
}
function aeClose() {
  const d = $('#avatar-editor'); if (!d?.open || ae.saving) return;
  ++ae.stageId;
  if (ae.fileUrl) URL.revokeObjectURL(ae.fileUrl);
  Object.assign(ae, {file:null, fileUrl:'', loading:false});
  document.documentElement.classList.remove('ae-locked'); d.close();
  (ae.trigger?.isConnected ? ae.trigger : $('#avatar-pick'))?.focus();
}
function aeUpload(file) {
  return new Promise((resolve, reject) => {
    const data = new FormData(); data.append('file', file);
    const xhr = new XMLHttpRequest(); xhr.open('POST', '/api/profile/avatar'); xhr.setRequestHeader('X-CSRF-Token', csrf);
    xhr.upload.onprogress = e => { if (e.lengthComputable) aeStatus(`Uploading photo… ${Math.round(e.loaded / e.total * 100)}%`); };
    xhr.onload = () => { let body = {}; try { body = JSON.parse(xhr.responseText); } catch (e) {} xhr.status >= 200 && xhr.status < 300 ? resolve(body) : reject(Error(typeof body.detail === 'string' ? body.detail : 'The photo could not be uploaded.')); };
    xhr.onerror = () => reject(Error('Upload failed. Check your connection and try again.'));
    xhr.send(data);
  });
}
async function aeSave() {
  if (ae.saving || ae.loading || !ae.mode) return;
  if (ae.mode === 'photo' && !aePhotoUrl()) return aeStatus('Choose a photo first.', 'error');
  const d = $('#avatar-editor'), button = d.querySelector('[data-ae-save]');
  ae.saving = true; d.querySelectorAll('button,input').forEach(c => { c.disabled = true; }); button.textContent = 'Saving…'; aeStatus('');
  try {
    if (ae.mode === 'photo') {
      if (ae.file) account = await aeUpload(ae.file);
    } else {
      account = await api('/profile/avatar-style', {method:'PUT', body:JSON.stringify({kind:'avatar', style:ae.style})});
    }
    ae.saving = false;
    renderNavbar(); refreshAvatarField(); refreshProfilePictures(account); aeClose(); toast('Profile picture saved');
  } catch (e) { aeStatus(e.message, 'error'); }
  finally {
    ae.saving = false;
    d.querySelectorAll('button,input').forEach(c => { c.disabled = false; }); button.textContent = 'Save';
    if (d.open) aePaint();
  }
}
function aeListen(d) {
  keepFocusInside(d);
  d.addEventListener('submit', e => { e.preventDefault(); aeSave(); });
  d.addEventListener('cancel', e => { e.preventDefault(); aeClose(); });
  let pressedOutside = false;
  d.addEventListener('pointerdown', e => { pressedOutside = e.target === d; });
  d.addEventListener('click', e => {
    if (ae.saving) return;
    if ((e.target === d && pressedOutside) || e.target.closest('[data-ae-close], [data-ae-cancel]')) return aeClose();
    if (e.target.closest('[data-ae-choose]')) d.querySelector('#ae-file').click();
  });
  d.addEventListener('input', e => {
    if (ae.saving) return;
    const t = e.target, s = ae.style;
    if (t.name === 'ae-mode') { ae.mode = t.value; ++ae.stageId; ae.loading = false; }
    else if (t.name === 'ae-type') { s.type = t.value; s.variant = AVATAR_VARIANTS[t.value][0]; }
    else if (t.name === 'ae-variant') s.variant = t.value;
    else if (t.name === 'ae-fg' || t.name === 'ae-bg') {
      const foreground = t.name === 'ae-fg';
      s[foreground ? 'foreground' : 'background'] = t.value;
      let message = 'Choose any combination you like.';
      d.querySelector('#ae-contrast').textContent = message;
    } else return;
    aeStatus(''); aePaint();
  });
  d.addEventListener('change', e => { if (e.target.id === 'ae-file' && e.target.files[0]) { aeStage(e.target.files[0]); e.target.value = ''; } });
  d.addEventListener('dragover', e => { if (e.target.closest('[data-ae-drop]')) { e.preventDefault(); e.target.closest('[data-ae-drop]').classList.add('is-over'); } });
  d.addEventListener('dragleave', e => e.target.closest?.('[data-ae-drop]')?.classList.remove('is-over'));
  d.addEventListener('drop', e => { const zone = e.target.closest('[data-ae-drop]'); if (!zone) return; e.preventDefault(); zone.classList.remove('is-over'); if (e.dataTransfer.files[0]) aeStage(e.dataTransfer.files[0]); });
}
