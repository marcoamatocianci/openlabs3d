// My requests: Active requests (Submitted / Under review / Accepted = quoted) and Request history (Closed).
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
  const shown = () => page.locator('.cr-card').evaluateAll(cs => cs.map(c => c.dataset.status));
  await open('my-requests');
  // Level 1: Active requests by default; closed ones only in Request history.
  check((await page.locator('.scope-nav .segment[aria-current]').innerText()).startsWith('Active requests'), 'Active requests is the default');
  check((await shown()).length === count('submitted', 'under_review', 'quoted') && !(await shown()).includes('closed'), 'Closed requests are not in the active list');
  check(+(await page.locator('.cr-head .chip', {hasText:'My requests'}).locator('span').innerText()) === count('submitted', 'under_review', 'quoted'), 'Tab counts active requests');
  // Level 2: status filters of the active scope, in lifecycle order, kept in the address.
  const chips = page.locator('.cr-scope .chips .chip');
  check(JSON.stringify(await chips.evaluateAll(b => b.map(x => x.firstChild.textContent))) === '["All active","Submitted","Under review","Accepted"]', 'Active filters in lifecycle order');
  for (const [label, status] of [['Submitted', 'submitted'], ['Under review', 'under_review'], ['Accepted', 'quoted']]) {
    const chip = page.locator('.cr-scope .chip', {hasText:label});
    check(+(await chip.locator('span').textContent()) === count(status), label + ' count');
    await chip.click(); await page.waitForFunction(l => document.querySelector('.cr-scope .chip[aria-current]')?.textContent.startsWith(l), label);
    await page.waitForFunction(n => document.querySelectorAll('.cr-card').length === n, count(status));
    check((await shown()).every(s => s === status), label + ' filters by ' + status);
  }
  check(await page.locator('.cr-card .status').first().textContent() === 'Accepted · quote sent', 'Quoted reads as accepted to the customer');
  await page.reload(); await page.locator('.cr-scope').waitFor();
  check((await page.locator('.cr-scope .chip[aria-current]').innerText()).startsWith('Accepted') && page.url().includes('group=quoted'), 'Filter kept after reload');
  await page.locator('.scope-nav .segment', {hasText:'Request history'}).click();
  await page.waitForURL(/scope=history/); await page.waitForFunction(() => document.querySelector('.scope-nav .segment[aria-current]')?.textContent.includes('Request history'));
  check(JSON.stringify(await shown()) === JSON.stringify(Array(count('closed')).fill('closed')), 'Request history holds the closed requests');
  // Hierarchy: reference and date above the title, the status note set apart.
  await open('my-requests');
  const card = page.locator('.cr-card').first(), meta = await card.locator('.cr-meta').boundingBox(), title = await card.locator('h2').boundingBox();
  check(meta.y < title.y, 'Reference line above the title');
  check(await card.locator('.cr-status-note').evaluate(n => parseFloat(getComputedStyle(n).borderLeftWidth)) >= 3, 'Status note set apart');
  await page.setViewportSize({width:390, height:844});
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow on mobile');
  return {passed:['active by default', 'status filters', 'customer label', 'persistence', 'request history', 'hierarchy', 'mobile']};
}
