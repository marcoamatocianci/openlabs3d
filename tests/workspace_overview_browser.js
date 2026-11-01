// Host and admin overviews: summary cards carry no attention highlight; the host overview is counts only.
// Requires scripts/equipment_preview.py (http://127.0.0.1:18099, isolated data only).
async page => {
  const base = 'http://127.0.0.1:18099', check = (ok, message) => { if (!ok) throw Error(message); };
  const login = async name => {
    await page.context().clearCookies();
    const r = await page.request.post(base + '/api/auth/login', {data:{email:name + '@example.org', password:'TestPassword2026'}});
    check(r.ok(), 'Login failed for ' + name);
    return (await r.json()).csrf_token;
  };
  // A buyer order gives the host at least one available job.
  const csrf = await login('buyer');
  const listing = (await (await page.request.get(base + '/api/listings')).json()).items.find(p => p.title === 'Availability QA Rack');
  const line = {listing_id:listing.id, material:'PLA', color:'black', quantity:1};
  const quote = await (await page.request.post(base + `/api/listings/${listing.id}/quote`, {data:{material:'PLA', color:'black', quantity:1}, headers:{'x-csrf-token':csrf}})).json();
  const order = await page.request.post(base + '/api/checkout', {data:{contact:{first_name:'Q', last_name:'A', email:'qa@example.org', phone:'+39 011 1234567', street:'Via QA 1', city:'Torino', country:'IT', postal_code:'10100', region:'TO'}, address_id:null, direct:line, confirmed:[{...line, unit_price_cents:quote.unit_price_cents}], idempotency_key:'overview-' + Date.now()}, headers:{'x-csrf-token':csrf}});
  check(order.ok(), 'Order not created: ' + await order.text());
  const card = async label => page.locator('.stat-card', {hasText:label}).first();
  await login('host');
  await page.goto(base + '/?qa=' + Date.now() + '#host');
  const jobs = page.locator('.ho-stat[data-stage="available"]'); await jobs.waitFor();
  check(+(await jobs.locator('.ho-stat-count').textContent()) > 0, 'Host has available jobs');
  check(await page.locator('.ho-stat').count() === 4 && await page.locator('#app [data-job-card]').count() === 0, 'Host overview: four stage counts, no job cards');
  check(await page.locator('.stat-card.attention, .ho-stat.attention').count() === 0, 'Host overview has no attention card');
  await jobs.click(); await page.waitForURL(/#host\/jobs\?group=available$/); await page.locator('.sb-col.is-open[data-stage="available"]').waitFor();
  await login('admin');
  await page.goto(base + '/?qa=' + Date.now() + '#admin');
  await (await card('Pending approvals')).waitFor();
  check(page.url().endsWith('#admin'), 'Direct load of #admin stays on the overview');
  check(await page.locator('.stat-card.attention').count() === 0, 'Admin overview has no attention card');
  return {passed:['host overview', 'admin overview']};
}
