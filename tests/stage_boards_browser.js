// Stage boards on the Active/History pages: Load more within a stage (focus on the first new card), a failed
// page kept inside its stage with Try again, single-stage scopes, earlier links and overview links landing on
// the right stage, and the switch animation off with reduced motion. Requires a fresh scripts/workflow_preview.py
// (http://127.0.0.1:18102); it places and cancels orders and adds custom requests.
async page => {
  const base = 'http://127.0.0.1:18102', check = (ok, m) => { if (!ok) throw Error(m); };
  const ctx = page.context(), errors = []; page.on('pageerror', e => errors.push(e.message));
  const login = async who => { await ctx.clearCookies(); return (await (await ctx.request.post(base + '/api/auth/login', {data:{email:who + '@example.org', password:'TestPassword2026'}})).json()).csrf_token; };
  const post = (path, csrf, data) => ctx.request.post(base + '/api/' + path, {data, headers:{'x-csrf-token':csrf}});
  const open = async hash => { await page.goto(base + '/?qa=' + Date.now() + '#' + hash); await page.waitForLoadState('networkidle'); await page.waitForFunction(() => !document.querySelector('.ws-main[aria-busy], #bo-results[aria-busy], .ws-loading')); };
  const openStage = board => page.locator(`${board} .sb-col.is-open`).getAttribute('data-stage');
  await page.setViewportSize({width:1366, height:900});

  // Thirteen more cancelled orders: the Cancelled stage needs more than one page (12 cards).
  let csrf = await login('buyer');
  const listing = (await (await ctx.request.get(base + '/api/listings?per_page=12')).json()).items[0];
  const offer = await (await ctx.request.get(`${base}/api/listings/${listing.id}/availability`)).json();
  const material = Object.keys(offer.materials)[0], color = Object.keys(offer.colors_by_material[material])[0], line = {listing_id:listing.id, material, color, quantity:1};
  const price = (await (await post(`listings/${listing.id}/quote`, csrf, {material, color, quantity:1})).json()).unit_price_cents;
  const placed = [];
  for (let n = 0; n < 13; n++) {
    const r = await post('checkout', csrf, {contact:{first_name:'Q', last_name:'A', phone:'+39 011 1234567', street:'Via QA 1', city:'Torino', country:'IT', postal_code:'10100', region:'Piedmont'}, direct:line, confirmed:[{...line, unit_price_cents:price}], idempotency_key:`boards-${Date.now()}-${n}`});
    check(r.ok(), 'Order not placed: ' + await r.text()); placed.push((await r.json()).id);
  }
  const request = (await (await ctx.request.post(base + '/api/custom-requests', {multipart:{payload:JSON.stringify({idempotency_key:'boards-request-' + Date.now(), title:'Board holder', application:'A holder for checking the request boards in the browser.', dimensions:'10 x 10 x 10 mm', quantity:1})}, headers:{'x-csrf-token':csrf}})).json()).id;
  const closed = (await (await ctx.request.post(base + '/api/custom-requests', {multipart:{payload:JSON.stringify({idempotency_key:'boards-closed-' + Date.now(), title:'Closed board holder', application:'A holder for checking request history in the browser.', dimensions:'10 x 10 x 10 mm', quantity:1})}, headers:{'x-csrf-token':csrf}})).json()).id;
  csrf = await login('admin');
  for (const id of placed) check((await post(`admin/orders/${id}/cancel`, csrf, {reason:'Board history check'})).ok(), 'Order not cancelled');
  check((await ctx.request.patch(`${base}/api/admin/custom-requests/${closed}`, {data:{status:'closed'}, headers:{'x-csrf-token':csrf}})).ok(), 'Request not closed');

  // Buyer, Previous orders: the first page of the stage, how many are shown, then Load more.
  await login('buyer');
  await open('orders?scope=history&group=cancelled'); await page.locator('#bo-history-board').waitFor();
  const cancelled = page.locator('#bo-history-board [data-stage="cancelled"]');
  const total = +(await cancelled.locator('.sb-head [data-sb-count]').innerText());
  check(total >= 14 && await cancelled.locator('.bo-card').count() === 12, `first page of the stage (${total})`);
  check(await cancelled.locator('.sb-more-note').innerText() === `12 of ${total} shown`, 'the stage says how many are shown');
  // A failed page stays inside its stage, with the reason, and Try again loads it.
  const secondPage = url => url.pathname === '/api/orders' && url.searchParams.get('page') === '2';
  await page.route(secondPage, r => r.fulfill({status:500, contentType:'application/json', body:JSON.stringify({detail:'Temporarily unavailable'})}));
  await cancelled.getByRole('button', {name:'Load more'}).click(); await cancelled.locator('.sb-more-error').waitFor();
  check((await cancelled.locator('.sb-more-error').innerText()).includes('Temporarily unavailable') && await cancelled.getByRole('button', {name:'Try again'}).count() === 1 && await cancelled.locator('.bo-card').count() === 12, 'a failed page stays inside the stage');
  await page.unroute(secondPage);
  await cancelled.getByRole('button', {name:'Try again'}).click();
  await page.waitForFunction(n => document.querySelectorAll('#bo-history-board [data-stage="cancelled"] .bo-card').length === n, total);
  check(await cancelled.locator('.sb-more').count() === 0, 'Load more disappears once every card is shown');
  check(await page.evaluate(() => document.activeElement === document.querySelectorAll('#bo-history-board [data-stage="cancelled"] .bo-card')[12]), 'focus moves to the first new card');
  await cancelled.locator('.bo-card').last().locator('[data-order-details]').click(); await page.locator('#modal[open]').waitFor();
  check((await page.locator('#modal').innerText()).includes('Cancelled'), 'details open for a card added by Load more'); await page.keyboard.press('Escape');

  // Administrator: the same in Order history; earlier links and overview links open the right stage.
  await login('admin');
  await open('admin/orders?scope=history&group=cancelled'); await page.locator('#admin-orders-board').waitFor();
  const adminCancelled = page.locator('#admin-orders-board [data-stage="cancelled"]');
  check(await adminCancelled.locator('[data-order-card]').count() === 12, 'admin: first page of Cancelled');
  await adminCancelled.getByRole('button', {name:'Load more'}).click();
  await page.waitForFunction(() => document.querySelectorAll('#admin-orders-board [data-stage="cancelled"] [data-order-card]').length > 12);
  for (const [hash, board, stage] of [['admin/orders/pending', '#admin-orders-board', 'pending'], ['admin/orders/cancelled', '#admin-orders-board', 'cancelled'],
    ['admin/requests/submitted', '#cr-admin-board', 'submitted'], ['admin/pending?type=hosts', '#approvals-board', 'hosts'], ['admin/orders?attention=unassigned', '#admin-orders-board', null]]) {
    await open(hash); await page.locator(board).waitFor();
    const opened = await openStage(board);
    check(stage ? opened === stage : opened === (await page.locator(`${board} .sb-col`).evaluateAll(cs => cs.find(c => +c.querySelector('.sb-head [data-sb-count]').textContent > 0)?.dataset.stage)), `${hash} opens ${stage || 'the first stage with matches'} (${opened})`);
  }
  // A scope with a single stage: Request history is one full-width column, without stage pills.
  await open('admin/requests?scope=history'); await page.locator('#cr-admin-board').waitFor();
  check(await page.locator('#cr-admin-board.sb-single .sb-col').count() === 1 && await page.locator('#cr-admin-board .sb-pills').count() === 0 && await page.locator(`#cr-admin-board [data-cr-card="${closed}"]`).count() === 1, 'Request history: one column');
  check(await page.locator('#cr-admin-board [data-sb-expand]').isVisible(), 'A single-stage board offers Expand section');
  await page.locator('#cr-admin-board [data-sb-expand]').click(); await page.locator('#section-dialog[open]').waitFor();
  check(await page.locator('#section-dialog #ss-title').innerText() === await page.locator('#cr-admin-board .sb-title').innerText() && await page.locator('#section-dialog [data-cr-card]').count() >= 1, 'It opens on that stage');
  await page.locator('#section-dialog [data-ss-close]').click(); await page.locator('#section-dialog').waitFor({state:'hidden'});
  const width = await page.locator('#cr-admin-board .sb-col').evaluate(c => c.getBoundingClientRect().width / c.closest('.sb').getBoundingClientRect().width);
  check(width > .98, 'the single stage takes the full width');
  // The administrator moves a request one stage on: it lands in Under review, which lights up.
  await open('admin/requests?group=submitted'); await page.locator(`#cr-admin-board [data-cr-card="${request}"]`).waitFor();
  await page.locator(`#cr-admin-board [data-cr-next="${request}"]`).click(); await page.locator('#action-dialog[open]').waitFor();
  await page.locator('#action-dialog').getByRole('button', {name:'Start review'}).click();
  await page.locator(`#cr-admin-board [data-stage="under_review"] [data-cr-card="${request}"]`).waitFor({state:'attached'});
  check(await openStage('#cr-admin-board') === 'submitted' && await page.locator('#cr-admin-board [data-stage="under_review"].sb-bump').count() === 1, 'request moved to Under review; the open stage stays and the destination lights up');

  // Host: an earlier link and the overview link open Job history on Completed.
  await login('host');
  for (const hash of ['host/jobs/completed', 'host/jobs?scope=history&group=completed']) {
    await open(hash); await page.locator('#job-history-board').waitFor();
    check(await openStage('#job-history-board') === 'completed', hash + ' opens Completed');
  }
  // Switching slides the panels, and never with reduced motion.
  const switching = () => page.evaluate(() => { const b = document.querySelector('[data-stage-board]'), next = [...b.querySelectorAll('.sb-col:not(.is-open) .sb-head')][0]; next.click(); return [[...b.querySelectorAll('.sb-col')].flatMap(c => c.getAnimations()).filter(a => !(a instanceof CSSAnimation)).length, getComputedStyle(b.querySelector('.sb-col.is-open .sb-body')).animationName]; });
  const [moving] = await switching();
  check(moving > 0, 'switching slides the panels: ' + moving);
  await page.emulateMedia({reducedMotion:'reduce'}); await page.waitForTimeout(500);
  const [still, fade] = await switching();
  check(still === 0 && fade === 'none', `no animation with reduced motion (${still}, ${fade})`);
  await page.emulateMedia({reducedMotion:null});
  check(!errors.length, 'Page errors: ' + errors.join('; '));
  return {passed:['load more', 'failed page in its stage', 'focus on new cards', 'admin load more', 'earlier and overview links', 'single stage', 'stage move', 'reduced motion']};
}
