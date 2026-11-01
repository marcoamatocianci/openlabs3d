// Admin Printers: suggestions with origin, add as unverified and verify specs. Requires scripts/equipment_preview.py (18099).
async page => {
  const base = 'http://127.0.0.1:18099', check = (ok, m) => { if (!ok) throw Error(m); };
  await page.context().clearCookies();
  await page.context().request.post(base + '/api/auth/login', {data:{email:'admin@example.org', password:'TestPassword2026'}});
  const open = async () => { await page.goto(base + '/?qa=' + Date.now() + '#admin/printers'); await page.locator('[data-suggestions]').waitFor({state:'attached'}); };
  await open();
  // Layout: tiles first, then two sections collapsed by default; the arrow turns when one opens.
  const tiles = page.locator('.ap-tiles .ap-tile');
  check(await tiles.count() === 2 && (await tiles.first().innerText()).includes('QA'), 'One tile per registered printer type');
  check((await tiles.first().locator('.ap-tile-count').innerText()).trim().split(/\s+/)[0] === '1', 'Tile counts units');
  await tiles.first().hover();
  check(await tiles.first().locator('.ap-tip').isVisible() && (await tiles.first().locator('.ap-tip').innerText()).includes('Registered hosts'), 'Hover shows utilisation and hosts');
  const order = await page.locator('.ws-main .ap-available, .ws-main .ap-collapse').evaluateAll(e => e.map(x => x.dataset.collapse || 'available'));
  check(JSON.stringify(order) === '["available","suggestions","catalogue"]', 'Section order ' + order);
  check(await page.locator('.ap-collapse[open]').count() === 0, 'Both collapsed by default');
  const summary = page.locator('[data-collapse=catalogue] > summary');
  check(/^Catalogue\s*· \(\d+\)\s*▸$/.test((await summary.innerText()).trim()), 'Catalogue header reads "Catalogue · (n) ▸"');
  await summary.hover(); await page.waitForTimeout(300);
  const colours = await summary.evaluate(s => [...s.children].map(c => getComputedStyle(c).color));
  check(new Set(colours).size === 1, 'Title, count and arrow highlight together');
  await summary.click();
  check(await page.locator('[data-collapse=catalogue] .ap-collapse-arrow').evaluate(a => getComputedStyle(a).transform !== 'none'), 'Arrow rotates when open');
  const rows = page.locator('[data-suggestions] .list-row');
  await page.locator('[data-collapse=suggestions] > summary').click();
  check(await rows.count() >= 2, 'Suggestions listed');
  check((await rows.first().innerText()).includes('Host application'), 'Origin shown');
  // Verify the first suggestion.
  const name = (await rows.first().locator('.row-title').innerText()).trim();
  await page.locator('[data-suggestions]').evaluate(e => { const d = e.closest('details'); if (d) d.open = true; });
  await rows.first().getByRole('button', {name:'Verify specs'}).click();
  const d = page.locator('#action-dialog[open]'); await d.locator('#verify-printer').waitFor();
  await d.getByRole('button', {name:'Save as verified'}).click();
  check((await d.locator('.ad-error').innerText()).includes('source'), 'Source required');
  await d.locator('[name=source]').fill('https://example.org/specs'); await d.locator('[name=z]').fill('210');
  await d.locator('[name=materials][value=PLA]').check(); await d.locator('[name=materials][value=PETG]').check();
  const saved = page.waitForResponse(r => r.url().includes('/approve') && r.ok());
  await d.getByRole('button', {name:'Save as verified'}).click(); await saved;
  const entry = (await (await page.context().request.get(base + '/api/printer-catalogue')).json()).find(m => `${m.manufacturer} ${m.model}` === name);
  check(entry && entry.verified && entry.z === 210 && JSON.stringify(entry.materials) === '["PETG","PLA"]', 'Saved as verified: ' + JSON.stringify(entry));
  // Add the next one as unverified.
  await open(); await page.locator('[data-suggestions]').evaluate(e => { const d = e.closest('details'); if (d) d.open = true; });
  const next = (await rows.first().locator('.row-title').innerText()).trim();
  await rows.first().getByRole('button', {name:'Add as unverified'}).click();
  const added = page.waitForResponse(r => r.url().includes('/approve') && r.ok());
  await page.locator('#action-dialog[open]').getByRole('button', {name:'Add to catalogue'}).click(); await added;
  const other = (await (await page.context().request.get(base + '/api/printer-catalogue')).json()).find(m => `${m.manufacturer} ${m.model}` === next);
  check(other && !other.verified, 'Added as unverified');
  return {passed:true};
}
