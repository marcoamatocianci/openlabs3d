// Admin People: user profile with account info, printing specs and filterable activity.
// Requires scripts/availability_preview.py with EQUIPMENT_QA_ADMIN=1 (scripts/equipment_preview.py, 18099).
async page => {
  const base = 'http://127.0.0.1:18099', check = (ok, m) => { if (!ok) throw Error(m); };
  const ctx = page.context(), login = async who => { await ctx.clearCookies(); return (await (await ctx.request.post(base + '/api/auth/login', {data:{email:who + '@example.org', password:'TestPassword2026'}})).json()).csrf_token; };
  // A purchase and an accepted job create activity for the buyer and the host.
  let csrf = await login('buyer');
  const listing = (await (await ctx.request.get(base + '/api/listings')).json()).items[0], line = {listing_id:listing.id, material:'PLA', color:'black', quantity:1};
  const quote = await (await ctx.request.post(`${base}/api/listings/${listing.id}/quote`, {data:{material:'PLA', color:'black', quantity:1}, headers:{'x-csrf-token':csrf}})).json();
  check((await ctx.request.post(base + '/api/checkout', {data:{contact:{first_name:'Q', last_name:'A', phone:'+39 011 1234567', street:'Via QA 1', city:'Torino', country:'IT', postal_code:'10100', region:'Piedmont'}, direct:line, confirmed:[{...line, unit_price_cents:quote.unit_price_cents}], idempotency_key:'profile-' + Date.now()}, headers:{'x-csrf-token':csrf}})).ok(), 'Order placed');
  csrf = await login('host');
  const job = (await (await ctx.request.get(base + '/api/host/jobs')).json()).find(j => j.status === 'available');
  check((await ctx.request.post(`${base}/api/host/jobs/${job.id}/accept`, {headers:{'x-csrf-token':csrf}})).ok(), 'Job accepted');
  await login('admin');
  await page.goto(base + '/?qa=' + Date.now() + '#admin/users');
  await page.locator('.row-link', {hasText:'host'}).first().click();
  await page.waitForURL(/#admin\/users\/\d+$/); await page.locator('.up-activity').waitFor();
  const body = await page.locator('.ws-main').innerText();
  check(body.includes('host@example.org') && body.includes('Printing specs') && body.includes('QA host') && body.includes('PLA'), 'Account info and printing specs');
  check(await page.locator('.up-card input, .up-card select').count() === 0, 'Read-only');
  await page.locator('.up-filter .segment', {hasText:'Printing log'}).click(); await page.waitForURL(/type=printing/);
  await page.locator('.segment[aria-pressed=true]', {hasText:'Printing log'}).waitFor();
  check((await page.locator('.activity-list').innerText()).toLowerCase().includes('accepted'), 'Printing log lists the accepted job');
  // The buyer has purchases and no printing log.
  await page.goto(base + '/?qa=' + Date.now() + '#admin/users'); await page.locator('.row-link', {hasText:'buyer'}).first().click();
  await page.locator('.up-activity').waitFor();
  check(await page.locator('.up-filter .segment', {hasText:'Printing log'}).count() === 0 && await page.locator('.ws-main').getByText('Printing specs').count() === 0, 'No host sections for a buyer');
  await page.locator('.up-filter .segment', {hasText:'Marketplace purchases'}).click(); await page.waitForURL(/type=purchases/);
  await page.locator('.segment[aria-pressed=true]', {hasText:'Marketplace purchases'}).waitFor();
  check((await page.locator('.activity-list li').count()) >= 1 && (await page.locator('.activity-list').innerText()).toLowerCase().includes('order created'), 'Purchases filter');
  return {passed:true};
}
