/* Six curated motifs. Historical artwork below is read-only compatibility for saved pictures;
   it is never offered in the editor. Catalogue and palettes are mirrored by backend/app/avatars.py. */
const AVATAR_VARIANTS = {"erlenmeyer":["angular"],"test-tube":["single"],"pipette":["classic"],"dna":["helix"],"molecule":["triad","ring","chain"],"petri-dish":["agar"]};
const AVATAR_LABELS = {erlenmeyer:'Flask', 'test-tube':'Test tube', pipette:'Micropipette', dna:'DNA', molecule:'Molecule', 'petri-dish':'Petri dish'};
const AVATAR_VARIANT_LABELS = {triad:'Triad', ring:'Ring', chain:'Chain'};
const AVATAR_FOREGROUNDS = ['#386641', '#6a994e', '#a7c957', '#f2e8cf', '#bc4749'];
const AVATAR_BACKGROUNDS = ['#d7e0d9', '#e1eadc', '#edf4dd', '#fcfaf5', '#f2dadb'];
const AVATAR_MIN_CONTRAST = 3;
const AVATAR_START = {type:'erlenmeyer', variant:'angular', foreground:'#386641', background:'#fcfaf5'};
/* Artwork. f = pattern colour, b = background colour (used for cut-outs). 64 × 64, motif kept within
   the central circle so the round crop never clips it. Strokes are 4 units (2 px at 32 px). */
const S = (d, f, w = 4) => `<path d="${d}" fill="none" stroke="${f}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
const C = (x, y, r, fill) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}"/>`;
const R = (x, y, w, h, r, fill, extra = '') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}"${extra}/>`;
const P = (d, fill) => `<path d="${d}" fill="${fill}"/>`;
const FLASK = 'M28 18h8v10l10.4 17.3A2.5 2.5 0 0 1 44.3 49H19.7a2.5 2.5 0 0 1-2.1-3.7L28 28z';
const TUBE = 'M26 13h12v29a6 6 0 0 1-12 0z';
const FALCON = 'M25 19h14v20l-5.2 9.4a2 2 0 0 1-3.6 0L25 39z';
const ART = {
  erlenmeyer: {
    angular: (f, b) => R(25, 14, 14, 4.5, 2.2, f) + P(FLASK, f) + C(28.5, 42, 2.6, b) + C(34.5, 38, 1.7, b),
    rounded: (f, b) => R(25, 14, 14, 4.5, 2.2, f) + P('M28 18h8v9c6.5 5 13 11.5 13 17a5 5 0 0 1-5 5H20a5 5 0 0 1-5-5c0-5.5 6.5-12 13-17z', f) + R(21.5, 40, 21, 3, 1.5, b),
    liquid: (f, b) => R(25, 14, 14, 4.5, 2.2, f) + S(FLASK, f, 3.5) + P('M22.6 37h18.8l5 8.3A2.5 2.5 0 0 1 44.3 49H19.7a2.5 2.5 0 0 1-2.1-3.7z', f) + C(31, 26, 1.8, f),
    abstract: (f, b) => P('M32 20 49 48H15z', f) + C(32, 39, 5.5, b) + C(32, 13.5, 3.5, f),
  },
  beaker: {
    classic: (f, b) => P('M15.5 14h30v31a6 6 0 0 1-6 6H26a6 6 0 0 1-6-6V18.5z', f) + R(24.5, 23, 9, 2.6, 1.3, b) + R(24.5, 29.5, 5.5, 2.6, 1.3, b) + R(24.5, 36, 9, 2.6, 1.3, b) + R(24.5, 42.5, 5.5, 2.6, 1.3, b),
    filled: (f, b) => S('M16 14h28v30a6 6 0 0 1-6 6H26a6 6 0 0 1-6-6V18z', f, 3.5) + P('M21.75 32h20.5v12a4.3 4.3 0 0 1-4.3 4.3H26.05a4.3 4.3 0 0 1-4.3-4.3z', f) + C(28, 27, 1.8, f) + C(34, 22, 1.4, f),
    wide: (f, b) => S('M12 20h38v19a8 8 0 0 1-8 8H24a8 8 0 0 1-8-8V24z', f, 3.5) + P('M17.75 33h30.5v6a6.25 6.25 0 0 1-6.25 6.25H24a6.25 6.25 0 0 1-6.25-6.25z', f) + S('M41 25h5M43 29h3', f, 2.6) + C(28, 28, 1.6, f),
  },
  'test-tube': {
    single: (f, b) => `<g transform="rotate(22 32 32)">${R(23, 10, 18, 5, 2.5, f)}${S('M26 17v26a6 6 0 0 0 12 0V17', f, 3.5)}${P('M28 31h8v12a4 4 0 0 1-8 0z', f)}${S('M34 22h2M34 27h2', f, 2)}</g>`,
    trio: (f, b) => [16.5, 32, 47.5].map((x, n) => R(x - 6, 13, 12, 4, 2, f) + S(`M${x - 3.5} 17v24a3.5 3.5 0 0 0 7 0V17`, f, 3) + P(`M${x - 2} ${[34, 27, 38][n]}h4v7a2 2 0 0 1-4 0z`, f)).join(''),
    tilted: (f, b) => `<g transform="rotate(-32 32 32)">${R(23, 9.5, 18, 5, 2.5, f)}${S('M27 14.5v27.5a5 5 0 0 0 10 0V14.5', f, 3.5)}${P('M29.5 31h5v11a2.5 2.5 0 0 1-5 0z', f)}</g>`,
  },
  pipette: {
    classic: (f, b) => `<g transform="rotate(-28 32 32)">${R(28.5, 7, 7, 6, 2.5, f)}${R(31, 12, 2, 4, 0, f)}${R(24.5, 15.5, 15, 21, 5.5, f)}${R(28, 20, 8, 5.5, 1.6, b)}${P('M27.5 36h9l-2 8h-5z', f)}${P('M30.2 44h3.6L32 57.5z', f)}</g>`,
    drop: (f, b) => `<g transform="rotate(-28 32 32)">${R(28.5, 6, 7, 6, 2.5, f)}${R(31, 11, 2, 4, 0, f)}${R(24.5, 14.5, 15, 20, 5.5, f)}${R(28, 19, 8, 5.5, 1.6, b)}${P('M27.5 34.5h9l-2 7.5h-5z', f)}${P('M30.2 42h3.6L32 51z', f)}</g>${P('M41.6 47.5c0 3-2.2 5-4.6 5s-4.6-2-4.6-5c0-2.6 2.8-6 4.6-8 1.8 2 4.6 5.4 4.6 8z', f)}`,
    minimal: (f, b) => `<g transform="rotate(-28 32 32)">${C(32, 12, 4.5, f)}${R(27, 18.5, 10, 22, 5, f)}${S('M32 40.5V54', f, 3.5)}</g>`,
  },
  dna: {
    helix: f => S('M22 11c0 11 20 10 20 21s-20 10-20 21', f) + S('M42 11c0 11-20 10-20 21s20 10 20 21', f) + [15.5, 28.5, 35.5, 48.5].map(y => S(`M${y < 32 ? 26 : 26} ${y}h12`, f, 3)).join(''),
    ladder: f => `<g transform="rotate(24 32 32)">${S('M24 10v44M40 10v44', f)}${[17, 25, 33, 41, 49].map(y => S(`M24 ${y}h16`, f, 3)).join('')}</g>`,
    // A helix in perspective: rungs shorten as they turn, the near bead is larger than the far one.
    beads: f => { const rows = [12, 18.7, 25.3, 32, 38.7, 45.3, 52].map((y, n) => [11 * Math.cos(n * .95), y]), strand = sign => 'M' + rows.map(([x, y]) => `${(32 + sign * x).toFixed(1)} ${y}`).join('L');
      return S(strand(1), f, 2) + S(strand(-1), f, 2) + rows.map(([x, y]) => (Math.abs(x) > 3 ? S(`M${32 - x} ${y}H${32 + x}`, f, 2) : '') + C(32 - x, y, 2.4, f) + C(32 + x, y, 3.8, f)).join(''); },
  },
  molecule: {
    triad: (f, b) => S('M32 34 18 20M32 34l15-11M32 34v14', f) + C(32, 34, 7.5, f) + C(32, 34, 2.8, b) + C(18, 20, 5, f) + C(47, 23, 5, f) + C(32, 49, 4.5, f),
    ring: (f, b) => S('M32 14 47.6 23v18L32 50 16.4 41V23z', f) + [[32, 14], [47.6, 23], [47.6, 41], [32, 50], [16.4, 41], [16.4, 23]].map(([x, y], n) => C(x, y, n % 2 ? 3.4 : 5, f)).join('') + C(32, 32, 4, f),
    chain: f => S('M12 38 22 26l10 12 10-12 10 12', f) + [[12, 38], [22, 26], [32, 38], [42, 26], [52, 38]].map(([x, y], n) => C(x, y, n === 2 ? 6 : 4.4, f)).join(''),
  },
  microscope: {
    classic: (f, b) => R(16, 46, 32, 5.5, 2.75, f) + S('M41.5 46V31a11 11 0 0 0-8-10.6', f, 5) + R(19, 36, 18, 4, 2, f) + `<g transform="rotate(-32 27 22)">${R(23, 9, 9, 20, 3, f)}${R(21.5, 7, 12, 4, 2, f)}${R(25.5, 28, 4, 5, 1.5, f)}</g>` + C(41.5, 46, 2, b),
    compact: (f, b) => R(17, 46, 30, 5.5, 2.75, f) + R(27.5, 12, 9, 26, 4.5, f) + R(25, 9, 14, 5, 2.5, f) + R(22, 36, 20, 4, 2, f) + R(29.5, 40, 5, 6, 0, f) + C(32, 21, 2.2, b),
  },
  'petri-dish': {
    colonies: f => `<circle cx="32" cy="32" r="18.5" fill="none" stroke="${f}" stroke-width="4"/>` + C(26, 26, 3.6, f) + C(37.5, 28, 2.4, f) + C(29, 38.5, 2.2, f) + C(38, 38, 4, f) + C(32, 31.5, 1.5, f) + C(23, 35, 1.4, f),
    agar: (f, b) => C(32, 32, 20, f) + `<circle cx="32" cy="32" r="15" fill="none" stroke="${b}" stroke-width="2.4"/>` + C(27, 28, 3.2, b) + C(36.5, 30, 2.2, b) + C(31, 37.5, 2.6, b),
    stacked: (f, b) => `<ellipse cx="32" cy="38" rx="20" ry="7.5" fill="${f}"/>` + R(12, 30, 40, 8, 0, f) + `<ellipse cx="32" cy="30" rx="20" ry="7.5" fill="${f}"/><ellipse cx="32" cy="29.5" rx="15.5" ry="4.8" fill="${b}"/>` + C(28, 29.5, 1.5, f) + C(35, 28.5, 1.2, f) + `<path d="M12 22.5c0-4 9-7.5 20-7.5s20 3.5 20 7.5" fill="none" stroke="${f}" stroke-width="3.5" stroke-linecap="round"/>`,
  },
  cell: {
    nucleus: (f, b) => C(32, 32, 19.5, f) + C(35, 29, 7, b) + C(36.5, 27.5, 2.2, f) + C(23.5, 38, 2.4, b) + C(28.5, 44, 1.6, b) + C(42, 41.5, 1.8, b),
    dividing: (f, b) => C(23.5, 32, 12.5, f) + C(40.5, 32, 12.5, f) + C(22, 31, 4.2, b) + C(42, 33, 4.2, b),
    membrane: (f, b) => `<circle cx="32" cy="32" r="18.5" fill="none" stroke="${f}" stroke-width="4"/>` + C(34, 30, 7, f) + C(22.5, 37, 2.2, f) + C(41, 42, 1.8, f) + C(25, 24, 1.5, f),
  },
  bacterium: {
    rod: (f, b) => `<g transform="rotate(-30 32 32)">${R(14, 23.5, 30, 17, 8.5, f)}${C(22, 30, 2, b)}${C(30, 34.5, 2.2, b)}${C(36.5, 29.5, 1.6, b)}${S('M44 32c3-3 5 3 8 0s5 3 6 1.5', f, 2.6)}${S('M43 27c2.4-2.6 4 1 6.5-1.5', f, 2.4)}${S('M43 37c2.4 2.6 4-1 6.5 1.5', f, 2.4)}</g>`,
    cocci: (f, b) => C(25, 25, 8, f) + C(40, 27, 7, f) + C(31, 40, 8.5, f) + C(44, 41.5, 5, f) + C(19.5, 39, 4, f) + C(31, 40, 2.4, b) + C(25, 25, 2, b),
    spiral: f => S('M12 36c4-12 9-12 12 0s8 12 12 0 8-12 12 0 5 6 6 4', f, 5),
  },
  'centrifuge-tube': {
    conical: (f, b) => R(22.5, 11, 19, 7.5, 2.5, f) + R(24, 17, 16, 3, 0, f) + P(FALCON, f) + R(29, 25, 8, 2.4, 1.2, b) + R(32, 30, 5, 2.4, 1.2, b) + R(29, 35, 8, 2.4, 1.2, b),
    filled: (f, b) => R(22.5, 11, 19, 7.5, 2.5, f) + S('M26 20.5h12v18.2l-4.7 8.5a1.5 1.5 0 0 1-2.6 0L26 38.7z', f, 3.2) + P('M28 31h8v7.3l-3.3 6.1a.8.8 0 0 1-1.4 0L28 38.3z', f),
    pair: (f, b) => `<g transform="rotate(-14 22 34)">${R(13.5, 13, 15, 6, 2, f)}${P('M15 19h12v17l-4.3 8a1.9 1.9 0 0 1-3.4 0L15 36z', f)}${R(18.5, 27, 5, 2.2, 1.1, b)}</g><g transform="rotate(14 42 34)">${R(35.5, 13, 15, 6, 2, f)}${P('M37 19h12v17l-4.3 8a1.9 1.9 0 0 1-3.4 0L37 36z', f)}${R(40.5, 27, 5, 2.2, 1.1, b)}</g>`,
  },
  microplate: {
    grid: (f, b) => R(12, 18, 40, 28, 5.5, f) + [0, 1, 2].map(r => [0, 1, 2, 3].map(c => C(19.5 + c * 8.3, 25 + r * 7, 2.7, b)).join('')).join(''),
    filled: (f, b) => R(12, 18, 40, 28, 5.5, f) + [0, 1, 2].map(r => [0, 1, 2, 3].map(c => C(19.5 + c * 8.3, 25 + r * 7, 2.7, b) + ((r * 4 + c) % 3 === 0 ? C(19.5 + c * 8.3, 25 + r * 7, 1.3, f) : '')).join('')).join(''),
    strip: (f, b) => `<g transform="rotate(-20 32 32)">${R(9, 25, 46, 14, 7, f)}${[0, 1, 2, 3, 4].map(c => C(16 + c * 8, 32, 3, b)).join('')}</g>`,
  },
};

function avatarLuminance(hex) { const [r, g, b] = hex.slice(1).match(/../g).map(v => { const c = parseInt(v, 16) / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; }); return .2126 * r + .7152 * g + .0722 * b; }
function avatarContrast(a, b) { const [x, y] = [avatarLuminance(a), avatarLuminance(b)].sort((m, n) => n - m); return (x + .05) / (y + .05); }
const HEX = /^#[0-9a-f]{6}$/i;
function labAvatarStyle(style, legacy = false) {
  if (!style || typeof style !== 'object') return null;
  const {type, variant, foreground, background} = style;
  if (![type, variant, foreground, background].every(v => typeof v === 'string') || !HEX.test(foreground) || !HEX.test(background)) return null;
  const f = foreground.toLowerCase(), b = background.toLowerCase();
  if (legacy) {
    if (!Object.hasOwn(ART, type) || !Object.hasOwn(ART[type], variant)) return null;
  } else if (!Object.hasOwn(AVATAR_VARIANTS, type) || !AVATAR_VARIANTS[type].includes(variant) || !AVATAR_FOREGROUNDS.includes(f) || !AVATAR_BACKGROUNDS.includes(b)) return null;
  return {type, variant, foreground:f, background:b};
}
function labAvatarSvg(style, label = '') {
  const s = labAvatarStyle(style, true);
  if (!s) return '';
  return `<svg class="lab-avatar" viewBox="0 0 64 64" ${label ? `role="img" aria-label="${esc(label)}"` : 'aria-hidden="true"'} focusable="false"><rect width="64" height="64" fill="${s.background}"/>${ART[s.type][s.variant](s.foreground, s.background)}</svg>`;
}
function profilePictureFor(user) {
  const p = user?.profile_picture;
  if (p?.kind === 'avatar' && labAvatarStyle(p.style, true)) return p;
  if (p?.kind === 'photo' && /^[a-f0-9]{48}\.webp$/.test(p.file)) return p;
  return {kind:'initials'};
}
function profilePhotoUrl(user) {
  const p = profilePictureFor(user);
  return p.kind === 'photo' ? `/api/profile/avatar?user_id=${encodeURIComponent(user.id)}&v=${encodeURIComponent(p.file)}` : '';
}
