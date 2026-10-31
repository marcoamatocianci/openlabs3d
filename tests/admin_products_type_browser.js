// Admin Products: official/community badge, type switch and toggle. Requires scripts/catalogue_preview.py (18101).
async page => {
  const base = 'http://127.0.0.1:18101', check = (ok, m) => { if (!ok) throw Error(m); };
  await page.context().clearCookies();
  await page.context().request.post(base + '/api/auth/login', {data:{email:'admin@example.org', password:'TestPassword2026'}});
  const rows = () => page.locator('#product-list .list-row');
  const open = async hash => { await page.goto(base + '/?qa=' + Date.now() + '#' + hash); await page.locator('.segmented').waitFor(); };
  await open('admin/products');
  const total = await rows().count();
  check(total > 0 && await page.locator('.listing-type').count() === total, 'Every product shows its type badge');
  await page.locator('.segmented .segment', {hasText:'Official'}).click(); await page.waitForURL('**type=official');
  await page.locator('.segment[aria-pressed=true]', {hasText:'Official'}).waitFor();
  check(await page.locator('.listing-type-community').count() === 0 && await rows().count() > 0, 'Official filter');
  await page.locator('#product-list .chip, nav.chips .chip', {hasText:'Published'}).first().click();
  await page.waitForURL('**admin/products/approved?type=official'); await page.locator('.segmented').waitFor();
  check(await page.locator('.listing-type-community').count() === 0, 'Status chips keep the type filter');
  // Toggle the first official product to community.
  const title = (await rows().first().locator('.row-title').evaluate(t => t.firstChild.textContent)).trim();
  await rows().first().locator('[data-dropdown]').click();
  const saved = page.waitForResponse(r => r.url().endsWith('/community') && r.ok());
  await page.getByRole('button', {name:'Mark as community'}).first().click(); await saved;
  await open('admin/products?type=community');
  check((await rows().allInnerTexts()).some(t => t.includes(title)), 'Toggled product is community now: ' + title);
  return {passed:true, total};
}
