// Admin Approvals: under Operations above Orders, tabs by type with counts, cards with submitter and waiting time,
// inline decisions and empty states. Requires scripts/equipment_preview.py (18099).
async page => {
  const base = 'http://127.0.0.1:18099', check = (ok, m) => { if (!ok) throw Error(m); };
  await page.context().clearCookies();
  await page.context().request.post(base + '/api/auth/login', {data:{email:'admin@example.org', password:'TestPassword2026'}});
  await page.goto(base + '/?qa=' + Date.now() + '#admin/pending'); await page.locator('.approvals-tabs').waitFor();
  const nav = (await page.locator('aside.ws-sidebar').innerText()).toLowerCase();
  check(/operations\s+approvals[\s\S]*orders/.test(nav) && nav.indexOf('approvals') > nav.indexOf('people'), 'Approvals sits under Operations, above Orders');
  const labels = await page.locator('.approvals-tabs .segment').evaluateAll(t => t.map(x => x.firstChild.textContent));
  check(JSON.stringify(labels) === '["Host applications","Equipment updates","Listings","Printer suggestions"]', 'Tabs by type: ' + labels);
  // The fixture's hosts typed their printers by hand: printer suggestions are waiting, so that tab opens first.
  check((await page.locator('.segment[aria-pressed=true]').innerText()).startsWith('Printer suggestions'), 'First non-empty tab selected');
  const counts = await page.locator('.approvals-tabs .segment-count').allInnerTexts();
  check(+counts[3] === await page.locator('.approval-card').count() && +counts[3] > 0, 'Count matches the cards');
  const card = page.locator('.approval-card').first();
  check((await card.innerText()).includes('Submitted by') && await card.getByRole('button', {name:'Verify specs'}).count() === 1, 'Card shows submitter and inline actions');
  await card.getByRole('button', {name:'Add as unverified'}).click();
  const done = page.waitForResponse(r => r.url().includes('/approve') && r.ok());
  await page.locator('#action-dialog[open]').getByRole('button', {name:'Add to catalogue'}).click(); await done;
  await page.waitForFunction(n => document.querySelectorAll('.approval-card').length === n - 1, +counts[3]);
  // Empty state.
  await page.locator('.approvals-tabs .segment', {hasText:'Host applications'}).click(); await page.waitForURL(/type=hosts/);
  await page.locator('.segment[aria-pressed=true]', {hasText:'Host applications'}).waitFor();
  check((await page.locator('.approvals').innerText()).includes('No applications waiting'), 'Empty state');
  await page.setViewportSize({width:390, height:844});
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow on mobile');
  return {passed:true};
}
