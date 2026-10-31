// Host account settings: read-only equipment summary. Requires scripts/availability_preview.py (18097).
async page => {
  const base = 'http://127.0.0.1:18097', check = (ok, m) => { if (!ok) throw Error(m); };
  await page.context().clearCookies();
  await page.context().request.post(base + '/api/auth/login', {data:{email:'host@example.org', password:'TestPassword2026'}});
  await page.goto(base + '/?qa=' + Date.now() + '#account');
  const card = page.locator('#settings-equipment'); await card.locator('.es-grid').waitFor();
  const text = await card.innerText();
  check(text.includes('QA host') && text.includes('200 × 200 × 200 mm') && text.includes('FDM'), 'Printer listed with technology and volume');
  check(await card.locator('.es-printer .eq-art').count() === 1, 'Technology icon shown');
  check(await card.locator('.es-material').count() === 2 && await card.locator('.es-material .eq-dot').count() === 3, 'Materials with colour swatches');
  check(await card.locator('input,select,textarea').count() === 0, 'Read-only');
  check(await card.locator('a[href="#my-printers"]').count() === 1, 'Links to My equipment');
  await page.context().clearCookies();
  await page.context().request.post(base + '/api/auth/login', {data:{email:'buyer@example.org', password:'TestPassword2026'}});
  await page.goto(base + '/?qa=' + Date.now() + '#account'); await page.locator('#account-contact').waitFor();
  check(await page.locator('#settings-equipment').count() === 0, 'Buyers have no equipment card');
  return {passed:true};
}
