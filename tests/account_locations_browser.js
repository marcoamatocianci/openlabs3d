// Account settings: one public name, and searchable country / region / city fields (region narrows cities).
// Requires scripts/catalogue_preview.py (http://127.0.0.1:18101, isolated data); edits buyer@example.org.
async page => {
  const base = 'http://127.0.0.1:18101', check = (ok, message) => { if (!ok) throw Error(message); };
  await page.context().clearCookies();
  check((await page.context().request.post(base + '/api/auth/login', {data:{email:'buyer@example.org', password:'TestPassword2026'}})).ok(), 'Login');
  await page.goto(base + '/?qa=' + Date.now() + '#account');
  await page.locator('#account-contact').waitFor();
  // Profile: username only.
  check(await page.locator('#account-profile [name=display_name]').count() === 0 && await page.locator('#account-profile [name=username]').count() === 1, 'Profile edits a single username');
  check((await page.locator('.user-trigger').innerText()).includes('buyer'), 'Navigation shows the username');
  // Contact information: one searchable country input, no second search box or native select.
  const contact = page.locator('#account-contact'), combo = (scope, name) => scope.locator(`[data-location=${name}] .cf-input`), value = (scope, name) => scope.locator(`[data-location=${name}] input[type=hidden]`).inputValue();
  check(await contact.locator('select, .country-search').count() === 0, 'No native country select or extra search box');
  check(await combo(contact, 'country').inputValue() === 'Italy' && await value(contact, 'country') === 'IT', 'Country shows the saved value');
  check(await combo(contact, 'country').getAttribute('role') === 'combobox', 'Country is a combobox');
  await contact.locator('[data-location=region] [role=option]', {hasText:'Piedmont'}).waitFor({state:'attached'}); // lists load with the page
  await combo(contact, 'region').click();
  await contact.locator('[data-location=region] [role=option]', {hasText:'Piedmont'}).waitFor();
  check(await contact.locator('[data-location=region] [role=option]').count() === 20, 'Italian regions offered');
  await combo(contact, 'region').fill('Piedm'); await page.keyboard.press('Enter');
  check(await value(contact, 'region') === 'Piedmont', 'Region chosen');
  await combo(contact, 'city').click();
  const cities = await contact.locator('[data-location=city] [role=option]').allTextContents();
  check(cities.includes('Turin') && !cities.includes('Milan') && !cities.includes('Rome'), 'Cities follow the region');
  await combo(contact, 'city').fill('Turin'); await page.keyboard.press('Enter');
  check(await value(contact, 'city') === 'Turin', 'City chosen from the list');
  // Changing country resets region and city and reloads the lists.
  await combo(contact, 'country').fill('France'); await page.keyboard.press('Enter');
  check(await value(contact, 'country') === 'FR' && await value(contact, 'region') === '' && await value(contact, 'city') === '', 'New country clears region and city');
  await combo(contact, 'region').click();
  await contact.locator('[data-location=region] [role=option]', {hasText:'Île-de-France'}).waitFor();
  await combo(contact, 'region').fill('ile de'); await page.keyboard.press('Enter');
  check(await value(contact, 'region') === 'Île-de-France', 'Accent-insensitive region search');
  await combo(contact, 'city').fill('Paris'); await page.keyboard.press('Enter');
  await contact.getByRole('button', {name:'Save contact information'}).click();
  await contact.locator('.form-status', {hasText:'Saved'}).waitFor();
  const me = (await (await page.context().request.get(base + '/api/auth/me')).json()).user;
  check(me.country === 'FR' && me.region === 'Île-de-France' && me.city === 'Paris', 'Contact saved: ' + [me.country, me.region, me.city]);
  // Saved address: postal code and region required; free-text city kept.
  await page.locator('[data-address-new]:visible').first().click();
  const form = page.locator('#address-form');
  await form.waitFor();
  check(await form.locator('[name=postal_code]').getAttribute('required') !== null && await combo(form, 'region').getAttribute('required') !== null, 'Postal code and region required');
  await combo(form, 'country').fill('Italy'); await page.keyboard.press('Enter');
  await form.locator('[name=street]').fill('Via QA 9');
  await combo(form, 'city').fill('Torino'); await page.keyboard.press('Tab');
  check(await value(form, 'city') === 'Torino', 'City not in the list is kept as typed');
  await form.getByRole('button', {name:'Save address'}).click();
  check(await form.evaluate(f => !f.checkValidity()), 'Missing region and postal code block saving');
  await combo(form, 'region').click(); await form.locator('[data-location=region] [role=option]', {hasText:'Piedmont'}).click();
  await form.locator('[name=postal_code]').fill('10121');
  await form.getByRole('button', {name:'Save address'}).click();
  await page.locator('.address-card address', {hasText:'Via QA 9'}).waitFor();
  const saved = (await (await page.context().request.get(base + '/api/addresses')).json()).find(a => a.street === 'Via QA 9');
  check(saved && saved.city === 'Torino' && saved.region === 'Piedmont' && saved.postal_code === '10121', 'Address saved');
  await page.setViewportSize({width:390, height:844});
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow on mobile');
  return {passed:['single username', 'searchable country', 'regions by country', 'cities by region', 'reset on country change', 'saved contact', 'required postal code and region', 'free-text city']};
}
