// Admin Approvals: under Operations above Orders, a board with one stage per review queue and its count, cards
// with submitter and waiting time, the decision on each card, and empty stages. Requires scripts/equipment_preview.py (18099).
async page => {
  const base = 'http://127.0.0.1:18099', check = (ok, m) => { if (!ok) throw Error(m); };
  await page.context().clearCookies();
  await page.context().request.post(base + '/api/auth/login', {data:{email:'admin@example.org', password:'TestPassword2026'}});
  await page.setViewportSize({width:1366, height:900});
  await page.goto(base + '/?qa=' + Date.now() + '#admin/pending'); await page.locator('#approvals-board').waitFor();
  const nav = (await page.locator('aside.ws-sidebar').innerText()).toLowerCase();
  check(/operations\s+approvals[\s\S]*orders/.test(nav) && nav.indexOf('approvals') > nav.indexOf('people'), 'Approvals sits under Operations, above Orders');
  const labels = await page.locator('#approvals-board .sb-col').evaluateAll(cs => cs.sort((a, b) => a.dataset.index - b.dataset.index).map(c => c.querySelector('.sb-title').textContent));
  check(JSON.stringify(labels) === '["Host applications","Equipment updates","Listings","Printer suggestions"]', 'Stages by queue: ' + labels);
  // The fixture's hosts typed their printers by hand: printer suggestions are waiting, so that stage opens first.
  check(await page.locator('#approvals-board .sb-col.is-open').getAttribute('data-stage') === 'printers' && (await page.locator('.scope-nav .segment[aria-current]').innerText()).startsWith('Pending'), 'Pending queue, first non-empty stage open');
  const stage = key => page.locator(`#approvals-board [data-stage="${key}"]`), cards = key => stage(key).locator('.wf-card');
  const count = +(await stage('printers').locator('.sb-head [data-sb-count]').innerText());
  check(count === await cards('printers').count() && count > 0, 'Count matches the cards');
  check(+(await page.locator('.scope-nav .segment', {hasText:'Pending'}).locator('.segment-count').innerText()) === (await page.locator('#approvals-board .sb-head [data-sb-count]').allTextContents()).reduce((a, b) => a + +b, 0), 'Pending total is the sum of the stages');
  const card = cards('printers').first();
  check((await card.innerText()).includes('Submitted by') && await card.getByRole('button', {name:'Verify specs'}).count() === 1, 'Card shows submitter and its decision');
  // Search filters every stage and counts the matches.
  await page.locator('[data-filter-list="approvals-search"]').fill('no such printer');
  check(await stage('printers').locator('.sb-head [data-sb-count]').innerText() === '0' && await page.locator('#approvals-search [data-filter-empty]').isVisible(), 'Search with no match says so');
  await page.locator('[data-filter-list="approvals-search"]').fill('');
  await card.getByRole('button', {name:'Add as unverified'}).click();
  const done = page.waitForResponse(r => r.url().includes('/approve') && r.ok());
  await page.locator('#action-dialog[open]').getByRole('button', {name:'Add to catalogue'}).click(); await done;
  await page.waitForFunction(n => document.querySelectorAll('#approvals-board [data-stage="printers"] .wf-card').length === n - 1, count);
  check(await page.locator('#approvals-board .sb-col.is-open').getAttribute('data-stage') === 'printers', 'The decided queue stays open');
  // Empty stage: switching is local and kept in the address.
  await stage('hosts').locator('.sb-head').click(); await page.waitForFunction(() => location.hash.includes('type=hosts'));
  check((await stage('hosts').innerText()).includes('No applications waiting'), 'Empty stage');
  await page.reload(); await page.locator('#approvals-board').waitFor();
  check(await page.locator('#approvals-board .sb-col.is-open').getAttribute('data-stage') === 'hosts', 'Reload keeps the open stage');
  await page.setViewportSize({width:390, height:844});
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow on mobile');
  check(await page.locator('#approvals-board .sb-pills').isVisible(), 'Stage pills on a phone');
  return {passed:true};
}
