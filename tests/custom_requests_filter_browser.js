// My requests: the segmented status switch (All / Submitted / Under review / Accepted = quoted).
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
  const mine = await (await ctx.request.get(base + '/api/custom-requests')).json(), count = s => s ? mine.filter(r => r.status === s).length : mine.length;
  await page.goto(base + '/?qa=' + Date.now() + '#my-requests');
  await page.evaluate(() => sessionStorage.removeItem('ol3d-cr-filter'));
  await page.reload(); await page.locator('.cr-filter').waitFor();
  const segments = page.locator('.cr-filter .segment');
  check(JSON.stringify(await segments.evaluateAll(b => b.map(x => x.firstChild.textContent))) === '["All","Submitted","Under review","Accepted"]', 'Segments in lifecycle order');
  check(await page.locator('.cr-filter').getAttribute('role') === 'group' && await segments.first().getAttribute('aria-pressed') === 'true', 'All selected by default');
  const visible = () => page.locator('.cr-card:visible').count();
  check(await visible() === mine.length, 'All shows every request');
  for (const [label, status] of [['Submitted', 'submitted'], ['Under review', 'under_review'], ['Accepted', 'quoted']]) {
    const button = page.locator('.cr-filter .segment', {hasText:label});
    check(+(await button.locator('.segment-count').textContent()) === count(status), label + ' count');
    await button.click();
    check(await button.getAttribute('aria-pressed') === 'true', label + ' pressed');
    check(await visible() === count(status), label + ' shows only its requests');
    check((await page.locator('.cr-card:visible').evaluateAll(cs => cs.map(c => c.dataset.status))).every(s => s === status), label + ' filters by ' + status);
    check(+(await page.locator('#cr-filter-status').textContent()).split(' ')[0] === count(status), label + ' announced');
  }
  check(await page.locator('.cr-card:visible .status').first().textContent() === 'Accepted · quote sent', 'Quoted reads as accepted to the customer');
  // The choice survives a reload; closed requests appear only under All.
  await page.reload(); await page.locator('.cr-filter').waitFor();
  check(await page.locator('.cr-filter .segment[aria-pressed=true]').textContent().then(t => t.startsWith('Accepted')) && await visible() === count('quoted'), 'Filter kept after reload');
  await page.locator('.cr-filter .segment', {hasText:'All'}).click();
  check(await page.locator('.cr-card:visible[data-status=closed]').count() === count('closed'), 'Closed requests listed under All');
  // Hierarchy: reference and date above the title, the status note set apart.
  const card = page.locator('.cr-card').first(), meta = await card.locator('.cr-meta').boundingBox(), title = await card.locator('h2').boundingBox();
  check(meta.y < title.y, 'Reference line above the title');
  check(await card.locator('.cr-status-note').evaluate(n => parseFloat(getComputedStyle(n).borderLeftWidth)) >= 3, 'Status note set apart');
  await page.setViewportSize({width:390, height:844});
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow on mobile');
  return {passed:['segments', 'counts', 'filtering', 'persistence', 'customer label', 'hierarchy', 'mobile']};
}
