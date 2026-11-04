// My requests: an Active requests board (Submitted / Under review / Accepted = quoted) and Request history (Closed).
// Requires scripts/catalogue_preview.py (http://127.0.0.1:18101, isolated data); adds requests for buyer@example.org.
async page => {
  const base = 'http://127.0.0.1:18101', check = (ok, message) => { if (!ok) throw Error(message); };
  const ctx = page.context(); await ctx.clearCookies();
  const login = async who => (await (await ctx.request.post(base + '/api/auth/login', {data:{email:who + '@example.org', password:'TestPassword2026'}})).json()).csrf_token;
  let csrf = await login('buyer');
  const created = [];
  for (const title of ['Filter QA submitted', 'Filter QA review', 'Filter QA quoted', 'Filter QA closed']) {
    const payload = {idempotency_key:'filter-qa-' + Date.now() + '-' + created.length, title, application:'A holder for testing the request status filter in the browser.', dimensions:'100 x 50 x 20 mm', quantity:1};
    const r = await ctx.request.post(base + '/api/custom-requests', {multipart:{payload:JSON.stringify(payload)}, headers:{'x-csrf-token':csrf}});
    check(r.ok(), 'Request not created: ' + await r.text()); created.push((await r.json()).id);
  }
  csrf = await login('admin');
  for (const [id, status] of [[created[1], 'under_review'], [created[2], 'quoted'], [created[3], 'closed']])
    check((await ctx.request.patch(`${base}/api/admin/custom-requests/${id}`, {data:{status}, headers:{'x-csrf-token':csrf}})).ok(), 'Status not set');
  await login('buyer');
  const mine = await (await ctx.request.get(base + '/api/custom-requests')).json(), count = (...s) => mine.filter(r => s.includes(r.status)).length;
  const open = async hash => { await page.goto(base + '/?qa=' + Date.now() + '#' + hash); await page.locator('.cr-scope').waitFor(); };
  const stage = key => page.locator(`#cr-board [data-stage="${key}"]`);
  const shown = key => stage(key).locator('[data-cr-card]').evaluateAll(cs => cs.map(c => c.dataset.status));
  await page.setViewportSize({width:1366, height:900});
  await open('my-requests');
  // Level 1: Active requests by default; closed ones only in Request history.
  check((await page.locator('.scope-nav .segment[aria-current]').innerText()).startsWith('Active requests'), 'Active requests is the default');
  check(+(await page.locator('.cr-head .chip', {hasText:'My requests'}).locator('span').innerText()) === count('submitted', 'under_review', 'quoted'), 'Tab counts active requests');
  // The board: one stage per active status, in lifecycle order, each holding only its own requests.
  check(JSON.stringify(await page.locator('#cr-board .sb-col').evaluateAll(cs => cs.map(c => c.dataset.stage))) === '["submitted","under_review","quoted"]', 'Active stages in lifecycle order');
  check(JSON.stringify(await page.locator('#cr-board .sb-title').allTextContents()) === '["Submitted","Under review","Accepted"]', 'Stage names in the customer\'s words');
  check(await page.locator('#cr-board [data-status="closed"]').count() === 0, 'Closed requests are not in the active board');
  for (const status of ['submitted', 'under_review', 'quoted']) {
    check(+(await stage(status).locator('.sb-head [data-sb-count]').innerText()) === count(status), status + ' count');
    check((await shown(status)).length === count(status) && (await shown(status)).every(s => s === status), status + ' stage holds its requests');
  }
  // Switching stage is local and kept in the address, so a reload reopens it.
  await stage('quoted').locator('.sb-head').click();
  await page.waitForFunction(() => location.hash.includes('group=quoted'));
  check(await stage('quoted').evaluate(c => c.classList.contains('is-open')), 'Accepted stage opens');
  check((await stage('quoted').locator('.jc-side .status').first().textContent()) === 'Accepted · quote sent', 'Quoted reads as accepted to the customer');
  await page.reload(); await page.locator('.cr-scope').waitFor();
  check(await stage('quoted').evaluate(c => c.classList.contains('is-open')) && page.url().includes('group=quoted'), 'Open stage kept after reload');
  // Details: the full request in the site dialog.
  await stage('quoted').locator('[data-cr-details]').first().click(); await page.locator('#modal[open]').waitFor();
  check((await page.locator('#modal').innerText()).includes('A holder for testing the request status filter'), 'Details show the submitted request');
  await page.keyboard.press('Escape');
  // Search filters the cards of every stage and counts the matches.
  await page.locator('[data-filter-list="cr-board-search"]').fill('Filter QA review');
  check(await stage('under_review').locator('.sb-head [data-sb-count]').innerText() === '1' && await stage('submitted').locator('.sb-head [data-sb-count]').innerText() === '0', 'Search counts matches per stage');
  await page.locator('[data-filter-list="cr-board-search"]').fill('');
  await page.locator('.scope-nav .segment', {hasText:'Request history'}).click();
  await page.waitForURL(/scope=history/); await page.waitForFunction(() => document.querySelector('.scope-nav .segment[aria-current]')?.textContent.includes('Request history'));
  // Request history has one stage, Closed: a single full-width column.
  await page.locator('#cr-board.sb-single').waitFor();
  check(await page.locator('#cr-board .sb-col').count() === 1 && await page.locator('#cr-board .sb-pills').count() === 0, 'Request history is one column');
  check(JSON.stringify(await shown('closed')) === JSON.stringify(Array(count('closed')).fill('closed')), 'Request history holds the closed requests');
  // Hierarchy: reference and date above the title, the status note set apart.
  await open('my-requests?group=submitted');
  const card = stage('submitted').locator('[data-cr-card]').first(), meta = await card.locator('.jc-kicker').boundingBox(), title = await card.locator('.jc-title').boundingBox();
  check(meta.y < title.y, 'Reference line above the title');
  check(await card.locator('.jc-note').evaluate(n => getComputedStyle(n).backgroundColor !== getComputedStyle(n.closest('.wf-card')).backgroundColor), 'Status note set apart');
  await page.setViewportSize({width:390, height:844});
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow on mobile');
  check(await page.locator('#cr-board .sb-pills').isVisible(), 'Stage pills on a phone');
  return {passed:['active by default', 'stages', 'customer label', 'persistence', 'details', 'search', 'request history', 'hierarchy', 'mobile']};
}
