// Active work vs history for hosts and administrators: items move by status alone, history is one click
// away, read-only, and the two-level navigation is consistent. Requires scripts/equipment_preview.py (18099).
async page => {
  const base = 'http://127.0.0.1:18099', check = (ok, m) => { if (!ok) throw Error(m); };
  const ctx = page.context(), errors = []; page.on('pageerror', e => errors.push(e.message));
  const login = async who => { await ctx.clearCookies(); return (await (await ctx.request.post(base + '/api/auth/login', {data:{email:who + '@example.org', password:'TestPassword2026'}})).json()).csrf_token; };
  const post = (path, csrf, data) => ctx.request.post(base + '/api/' + path, {data, headers:{'x-csrf-token':csrf}});
  const open = async hash => { await page.goto(base + '/?qa=' + Date.now() + '#' + hash); await page.waitForLoadState('networkidle'); await page.waitForFunction(() => !document.querySelector('.ws-main[aria-busy], .ws-loading')); };
  const navState = () => page.evaluate(() => [...document.querySelectorAll('.scope-nav .segment, .chips .chip')].filter(e => e.getClientRects().length).map(e => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return {h:Math.round(r.height), radius:s.borderRadius, on:e.matches('[aria-current]') , bg:s.backgroundColor}; }));
  // A buyer order the host makes and ships; the buyer then confirms receipt.
  let csrf = await login('buyer');
  const listing = (await (await ctx.request.get(base + '/api/listings')).json()).items.find(p => p.title === 'Availability QA Rack'), line = {listing_id:listing.id, material:'PLA', color:'black', quantity:1};
  const quote = await (await post(`listings/${listing.id}/quote`, csrf, {material:'PLA', color:'black', quantity:1})).json();
  const order = await (await post('checkout', csrf, {contact:{first_name:'Q', last_name:'A', phone:'+39 011 1234567', street:'Via QA 1', city:'Torino', country:'IT', postal_code:'10100', region:'Piedmont'}, direct:line, confirmed:[{...line, unit_price_cents:quote.unit_price_cents}], idempotency_key:'history-' + Date.now()})).json();
  const job = order.jobs[0].id;
  csrf = await login('host');
  check((await post(`host/jobs/${job}/accept`, csrf)).ok(), 'Host accepts');
  for (const status of ['printing', 'ready']) check((await post(`host/jobs/${job}/status`, csrf, {status})).ok(), status);
  check((await post(`host/jobs/${job}/status`, csrf, {status:'shipped', carrier:'DHL', tracking_number:'QA-HIST-1'})).ok(), 'Shipped');
  // Host overview: the shipped job sits in the Shipped column of the active board.
  await open('host');
  check(await page.locator('.hb-column', {hasText:'Shipped'}).locator('.hb-card').count() === 1, 'Shipped job on the board');
  check(await page.locator('.hb-section a[href="#host/jobs?scope=history"]').count() === 1, 'Job history one click away');
  // Printing jobs: Active jobs by default, with the shipped job; history empty for now.
  await open('host/jobs');
  check((await page.locator('.scope-nav .segment[aria-current]').innerText()).startsWith('Active jobs'), 'Active jobs is the default');
  check(await page.locator(`.list-row:has-text("Awaiting buyer confirmation")`).count() === 1, 'Shipped job is active');
  await open('host/jobs/accepted');   // an earlier link form keeps working
  check((await page.locator('.chips .chip[aria-current]').innerText()).startsWith('Accepted'), 'Legacy path opens the Accepted filter');
  csrf = await login('buyer');
  check((await post(`orders/${order.id}/jobs/${job}/received`, csrf)).ok(), 'Buyer confirms receipt');
  csrf = await login('host');
  await open('host/jobs');
  check(await page.locator('.list-row:has-text("Awaiting buyer confirmation")').count() === 0, 'Completed job left Active jobs');
  await page.locator('.scope-nav .segment', {hasText:'Job history'}).click();
  await page.waitForURL(/scope=history/); await page.locator('.job-history .list-row').first().waitFor();
  const done = page.locator('.job-history .list-row').first();
  check((await done.innerText()).includes('Completed') && await done.locator('button, a[download]').count() === 0, 'History row: completed, no actions or downloads');
  await done.locator('summary').click();
  check((await done.innerText()).includes('QA-HIST-1'), 'History keeps the shipment');
  // Administrator: orders, approvals and requests.
  csrf = await login('admin');
  await open('admin/orders');
  check(!(await page.locator('#order-list').innerText().catch(() => '')).includes(order.reference), 'Completed order not in Active orders');
  await page.locator('.scope-nav .segment', {hasText:'Order history'}).click(); await page.waitForURL(/scope=history/);
  await page.locator('#order-list').waitFor();
  check((await page.locator('#order-list').innerText()).includes(order.reference), 'Completed order in Order history');
  await page.locator('#admin-order-q').fill(order.reference.slice(-6)); await page.locator('#admin-order-q').press('Enter');
  await page.waitForURL(/q=/); await page.waitForFunction(n => document.querySelectorAll('#order-list .list-row').length === n, 1);
  // Approvals: deciding a printer suggestion moves it from Pending to Approval history.
  await open('admin/pending?type=printers');
  const pendingBefore = +(await page.locator('.scope-nav .segment', {hasText:'Pending'}).locator('.segment-count').innerText());
  await page.locator('.approval-card').first().getByRole('button', {name:'Add as unverified'}).click();
  const added = page.waitForResponse(r => r.url().includes('/approve') && r.ok());
  await page.locator('#action-dialog[open]').getByRole('button', {name:'Add to catalogue'}).click(); await added;
  await open('admin/pending?type=printers');
  check(+(await page.locator('.scope-nav .segment', {hasText:'Pending'}).locator('.segment-count').innerText()) === pendingBefore - 1, 'Decided item left the pending queue');
  await page.locator('.scope-nav .segment', {hasText:'Approval history'}).click(); await page.waitForURL(/scope=history/);
  await page.locator('.decision-row').first().waitFor();
  check((await page.locator('.decision-row').first().innerText()).includes('Added unverified'), 'Decision recorded in Approval history');
  check(await page.locator('.chips .chip', {hasText:'Printers'}).locator('span').innerText() === '1', 'History counted by type');
  // Requests: closed goes to Request history; reopening brings it back.
  csrf = await login('buyer');
  const rid = (await (await ctx.request.post(base + '/api/custom-requests', {multipart:{payload:JSON.stringify({idempotency_key:'history-request-' + Date.now(), title:'History holder', application:'A holder for checking request history in the browser.', dimensions:'10 x 10 x 10 mm', quantity:1})}, headers:{'x-csrf-token':csrf}})).json()).id;
  csrf = await login('admin');
  check((await ctx.request.patch(`${base}/api/admin/custom-requests/${rid}`, {data:{status:'closed'}, headers:{'x-csrf-token':csrf}})).ok(), 'Closed');
  await open('admin/requests');
  check(!(await page.locator('.ws-main').innerText()).includes('History holder'), 'Closed request not active');
  await open('admin/requests?scope=history');
  check((await page.locator('.ws-main').innerText()).includes('History holder'), 'Closed request in Request history');
  check((await ctx.request.patch(`${base}/api/admin/custom-requests/${rid}`, {data:{status:'under_review'}, headers:{'x-csrf-token':csrf}})).ok(), 'Reopened');
  await open('admin/requests');
  check((await page.locator('.ws-main').innerText()).includes('History holder'), 'Reopened request back in the active queue');
  // Navigation: shared pills, 44 px, rounded, navy when selected, in both themes and on a phone.
  for (const [width, theme] of [[1366, 'light'], [390, 'dark']]) {
    await page.setViewportSize({width, height:900});
    for (const hash of ['admin/orders', 'admin/pending?scope=history', 'admin/requests']) {
      await open(hash); await page.evaluate(t => applyTheme(t), theme); await page.waitForTimeout(150);
      const pills = await navState();
      check(pills.length >= 4 && pills.every(p => p.h >= 43 && p.h <= 45 && p.radius === '999px'), `${hash} ${width} ${theme}: pill sizes ${JSON.stringify(pills)}`);
      check(pills.filter(p => p.on).every(p => p.bg === 'rgb(29, 53, 87)') && pills.filter(p => p.on).length === 2, `${hash} ${width} ${theme}: one selected pill per level`);
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${hash} ${width}: no horizontal overflow`);
    }
  }
  check(!errors.length, 'Page errors: ' + errors.join('; '));
  return {passed:['host board', 'active jobs', 'legacy links', 'job history', 'admin order history', 'approval history', 'request history', 'navigation']};
}
