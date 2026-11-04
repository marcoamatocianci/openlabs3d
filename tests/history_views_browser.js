// Active work vs history for hosts and administrators: items move by status alone, history is one click
// away, read-only, and the two-level navigation is consistent. Requires scripts/equipment_preview.py (18099).
async page => {
  const base = 'http://127.0.0.1:18099', check = (ok, m) => { if (!ok) throw Error(m); };
  const ctx = page.context(), errors = []; page.on('pageerror', e => errors.push(e.message));
  const login = async who => { await ctx.clearCookies(); return (await (await ctx.request.post(base + '/api/auth/login', {data:{email:who + '@example.org', password:'TestPassword2026'}})).json()).csrf_token; };
  const post = (path, csrf, data) => ctx.request.post(base + '/api/' + path, {data, headers:{'x-csrf-token':csrf}});
  const open = async hash => { await page.goto(base + '/?qa=' + Date.now() + '#' + hash); await page.waitForLoadState('networkidle'); await page.waitForFunction(() => !document.querySelector('.ws-main[aria-busy], .ws-loading')); };
  const navState = () => page.evaluate(() => [...document.querySelectorAll('.scope-nav .segment')].filter(e => e.getClientRects().length).map(e => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return {h:Math.round(r.height), radius:s.borderRadius, on:e.matches('[aria-current]') , bg:s.backgroundColor}; }));
  // A buyer order the host makes and ships; the buyer then confirms receipt.
  let csrf = await login('buyer');
  const listing = (await (await ctx.request.get(base + '/api/listings')).json()).items.find(p => p.title === 'Availability QA Rack'), line = {listing_id:listing.id, material:'PLA', color:'black', quantity:1};
  const quote = await (await post(`listings/${listing.id}/quote`, csrf, {material:'PLA', color:'black', quantity:1})).json();
  const order = await (await post('checkout', csrf, {contact:{first_name:'Q', last_name:'A', phone:'+39 011 1234567', street:'Via QA 1', city:'Torino', country:'IT', postal_code:'10100', region:'Piedmont'}, direct:line, confirmed:[{...line, unit_price_cents:quote.unit_price_cents}], idempotency_key:'history-' + Date.now()})).json();
  const job = order.jobs[0].id;
  csrf = await login('host');
  check((await post(`host/jobs/${job}/accept`, csrf)).ok(), 'Host accepts');
  check((await post(`host/jobs/${job}/status`, csrf, {status:'ready'})).ok(), 'ready (straight from accepted)');
  check((await post(`host/jobs/${job}/status`, csrf, {status:'shipped', carrier:'DHL', tracking_number:'QA-HIST-1'})).ok(), 'Shipped');
  // Host overview: the shipped job counts under Awaiting buyer; job history is one click away.
  await open('host');
  const awaiting = +(await page.locator('.ho-stat[data-stage="shipped"] .ho-stat-count').innerText());
  check(awaiting >= 1 && await page.locator('#app [data-job-card]').count() === 0, 'Shipped job counted under Awaiting buyer (no job cards on the overview)');
  check(await page.locator('.ho-head a[href="#host/jobs?scope=history"]').count() === 1, 'Job history one click away');
  // Printing jobs: active jobs by default, with the shipped job; history one button away.
  await open('host/jobs?group=shipped');
  check(await page.locator('#ws-title').innerText() === 'Printing jobs' && await page.locator('.ws-actions a', {hasText:'Job history'}).count() === 1, 'Active jobs is the default, Job history a secondary button');
  check(await page.locator(`#host-jobs-board .sb-col.is-open[data-stage="shipped"] [data-job-card="${job}"]`).count() === 1, 'Shipped job is active, awaiting the buyer');
  await open('host/jobs/accepted');   // an earlier link form keeps working: it opens the stage that holds accepted jobs
  check(await page.locator('#host-jobs-board .sb-col.is-open[data-stage="in-production"]').count() === 1, 'Legacy path opens the board on In production');
  csrf = await login('buyer');
  check((await post(`orders/${order.id}/jobs/${job}/received`, csrf)).ok(), 'Buyer confirms receipt');
  csrf = await login('host');
  await open('host/jobs');
  check(await page.locator(`[data-job-card="${job}"]`).count() === 0, 'Completed job left Active jobs');
  await page.locator('.ws-actions a', {hasText:'Job history'}).click();
  await page.waitForURL(/scope=history/); await page.locator('#job-history-board').waitFor();
  const done = page.locator(`#job-history-board [data-stage="completed"] [data-job-card="${job}"]`);
  check(await done.count() === 1 && (await done.innerText()).includes('Completed') && await done.locator('[data-job], a[download]').count() === 0, 'History card: under Completed, no steps or downloads');
  check((await done.innerText()).includes('QA-HIST-1'), 'History card keeps the shipment');
  await done.locator('[data-job-details]').click(); await page.locator('#modal[open]').waitFor();
  check((await page.locator('#modal').innerText()).includes('QA-HIST-1') && await page.locator('#modal [data-details-step], #modal a[download]').count() === 0, 'History details keep the shipment, read-only');
  await page.keyboard.press('Escape');
  // Administrator: orders, approvals and requests.
  csrf = await login('admin');
  await open('admin/orders');
  check(!(await page.locator('.ws-main').innerText()).includes(order.reference), 'Completed order not in Active orders');
  await page.locator('.scope-nav .segment', {hasText:'Order history'}).click(); await page.waitForURL(/scope=history/);
  await page.locator('#admin-orders-board').waitFor();
  const card = page.locator('#admin-orders-board [data-stage="completed"] [data-order-card]', {hasText:order.reference});
  check(await card.count() === 1, 'Completed order in Order history, under Completed');
  await card.locator('[data-admin-order]').click(); await page.locator('#modal[open]').waitFor();
  const details = await page.locator('#modal').textContent();
  check(details.includes('Printing jobs (1)') && details.includes('Delivery address') && details.includes('order.created') && await page.locator('#modal').getByRole('button', {name:'Cancel order'}).count() === 0, 'Order details: jobs, delivery and history, no cancel once completed');
  await page.keyboard.press('Escape');
  await page.locator('#admin-order-q').fill(order.reference.slice(-6)); await page.locator('#admin-order-q').press('Enter');
  await page.waitForURL(/q=/); await page.waitForFunction(n => document.querySelectorAll('#admin-orders-board [data-order-card]').length === n, 1);
  check(await page.locator('#admin-orders-board [data-stage="completed"] .sb-head [data-sb-count]').innerText() === '1', 'Search counts its matches per stage');
  // Approvals: deciding a printer suggestion moves it from Pending to Approval history.
  await open('admin/pending?type=printers');
  const pendingBefore = +(await page.locator('.scope-nav .segment', {hasText:'Pending'}).locator('.segment-count').innerText());
  await page.locator('#approvals-board [data-stage="printers"] .wf-card').first().getByRole('button', {name:'Add as unverified'}).click();
  const added = page.waitForResponse(r => r.url().includes('/approve') && r.ok());
  await page.locator('#action-dialog[open]').getByRole('button', {name:'Add to catalogue'}).click(); await added;
  await open('admin/pending?type=printers');
  check(+(await page.locator('.scope-nav .segment', {hasText:'Pending'}).locator('.segment-count').innerText()) === pendingBefore - 1, 'Decided item left the pending queue');
  await page.locator('.scope-nav .segment', {hasText:'Approval history'}).click(); await page.waitForURL(/scope=history/);
  await page.locator('#approval-history-board').waitFor();
  check((await page.locator('#approval-history-board [data-stage="printers"] [data-decision-card]').first().innerText()).includes('Added unverified'), 'Decision recorded in Approval history, under Printers');
  check(await page.locator('#approval-history-board [data-stage="printers"] .sb-head [data-sb-count]').innerText() === '1', 'History counted by type');
  // Expand section on an approvals board: the decision cards, search but no sort, and Escape returns focus.
  if (await page.locator('#approval-history-board').getAttribute('data-open') !== 'printers') { await page.locator('#approval-history-board .sb-head[data-sb-open="printers"]').click(); await page.waitForTimeout(360); }
  await page.locator('#approval-history-board .sb-col.is-open[data-stage="printers"] [data-sb-expand]').click(); await page.locator('#section-dialog[open]').waitFor();
  check(await page.locator('#section-dialog [data-decision-card]').count() === 1 && await page.locator('#section-dialog [data-select=ss-sort]').count() === 0 && await page.locator('#section-dialog #ss-count').innerText() === '1 decision', 'Approval history section: its decision, search only');
  await page.locator('#section-dialog #ss-q').fill('no such decision'); await page.waitForFunction(() => !document.querySelector('#section-dialog [data-decision-card]'));
  check(await page.locator('#section-dialog .ss-empty').isVisible(), 'A search with no match says so');
  await page.keyboard.press('Escape'); await page.waitForFunction(() => document.querySelector('#section-dialog [data-decision-card]'));
  check(await page.locator('#section-dialog #ss-q').inputValue() === '' && await page.locator('#section-dialog').evaluate(d => d.open), 'The first Escape clears the search and keeps the section open');
  await page.keyboard.press('Escape'); await page.locator('#section-dialog').waitFor({state:'hidden'});
  check(await page.evaluate(() => document.activeElement.matches('.sb-col.is-open [data-sb-expand]')), 'Focus returns to Expand section');
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
  // Navigation: level 1 is the shared pills (44 px, rounded, navy when selected); level 2 is the board, one stage
  // open, with stage pills only where the columns do not fit (phones). Both themes, no overflow.
  for (const [width, theme] of [[1366, 'light'], [390, 'dark']]) {
    await page.setViewportSize({width, height:900});
    for (const hash of ['admin/orders?scope=history', 'admin/pending?scope=history', 'admin/requests']) {
      await open(hash); await page.evaluate(t => applyTheme(t), theme); await page.waitForTimeout(150);
      const pills = await navState();
      check(pills.length === 2 && pills.every(p => p.h >= 43 && p.h <= 45 && p.radius === '999px'), `${hash} ${width} ${theme}: pill sizes ${JSON.stringify(pills)}`);
      check(pills.filter(p => p.on).every(p => p.bg === 'rgb(29, 53, 87)') && pills.filter(p => p.on).length === 1, `${hash} ${width} ${theme}: one selected level-1 pill`);
      const board = await page.evaluate(() => { const b = document.querySelector('[data-stage-board]'), shown = [...b.querySelectorAll('.sb-pills .chip')].filter(e => e.getClientRects().length); return {open:b.querySelectorAll('.sb-col.is-open').length, pills:shown.length, pressed:shown.filter(e => e.getAttribute('aria-pressed') === 'true').length, low:shown.filter(e => e.getBoundingClientRect().height < 43).length}; });
      check(board.open === 1 && (width < 700 ? board.pills >= 2 && board.pressed === 1 && !board.low : board.pills === 0), `${hash} ${width}: one open stage; stage pills only on a phone ${JSON.stringify(board)}`);
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${hash} ${width}: no horizontal overflow`);
    }
  }
  check(!errors.length, 'Page errors: ' + errors.join('; '));
  return {passed:['host board', 'active jobs', 'legacy links', 'job history', 'admin order history', 'approval history', 'request history', 'navigation']};
}
