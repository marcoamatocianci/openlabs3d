// Admin Products: official/community badge and the All / Official / Community view switch. Requires scripts/catalogue_preview.py (18101).
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
  // Viewing only: the listing type is not changed from this page.
  await rows().first().locator('[data-dropdown]').click();
  check(await page.getByRole('button', {name:/Mark as (official|community)/}).count() === 0, 'No type toggle in the row menu');
  await open('admin/products');
  await page.locator('.segmented .segment', {hasText:'Community'}).click(); await page.waitForURL('**type=community');
  await page.locator('.segment[aria-pressed=true]', {hasText:'Community'}).waitFor();
  check(await page.locator('.listing-type-official').count() === 0, 'Community filter');
  await page.locator('.segmented .segment', {hasText:'All'}).click(); await page.locator('.segment[aria-pressed=true]', {hasText:'All'}).waitFor();
  check(await rows().count() === total, 'All shows every product');
  return {passed:true, total};
}
