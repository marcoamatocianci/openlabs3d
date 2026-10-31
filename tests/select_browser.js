// Shared dropdown (assets/select.js): the marketplace filters still work, and the searchable mode behaves.
// Requires scripts/catalogue_preview.py (http://127.0.0.1:18101), then:
//   PLAYWRIGHT_MODULE=.../node_modules/playwright node tests/run_playwright_script.js tests/select_browser.js
async page => {
  const base = 'http://127.0.0.1:18101', check = (ok, message) => { if (!ok) throw Error(message); };
  await page.goto(base + '/?qa=' + Date.now() + '#catalogue');
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(base + '/?qa=' + Date.now() + '#catalogue');
  await page.locator('[data-cf-select=category] .cf-trigger').waitFor();
  const hidden = name => page.locator(`#filters input[type=hidden][name=${name}]`).inputValue();

  // Marketplace: mouse selection.
  await page.click('[data-cf-select=material] .cf-trigger');
  check(await page.locator('[data-cf-select=material] .cf-menu').isVisible(), 'Material menu opens on click');
  check(await page.getAttribute('[data-cf-select=material] .cf-trigger', 'aria-expanded') === 'true', 'aria-expanded follows the menu');
  await page.click('[data-cf-select=material] [role=option][data-value=PETG]');
  check(await hidden('material') === 'PETG', 'Material written to the form');
  check(await page.locator('[data-cf-select=material] .cf-value').textContent() === 'PETG', 'Trigger shows the choice');
  check(await page.locator('[data-cf-select=material] .cf-menu').isHidden(), 'Menu closes after choosing');
  check(await page.locator('#cf-apply.is-dirty').count() === 1, 'Apply button marked dirty');

  // Marketplace: keyboard selection and Escape.
  await page.focus('[data-cf-select=sort] .cf-trigger');
  await page.keyboard.press('ArrowDown');
  check(await page.locator('[data-cf-select=sort] .cf-menu').isVisible(), 'ArrowDown opens the sort menu');
  await page.keyboard.press('End'); await page.keyboard.press('Enter');
  check(await hidden('sort') === 'price_desc', 'End + Enter picks the last sort option');
  check(await page.evaluate(() => document.activeElement.matches('[data-cf-select=sort] .cf-trigger')), 'Focus returns to the trigger');
  await page.keyboard.press('Enter'); await page.keyboard.press('Escape');
  check(await page.locator('[data-cf-select=sort] .cf-menu').isHidden(), 'Escape closes');
  check(await hidden('sort') === 'price_desc', 'Escape keeps the value');

  // Marketplace: one open at a time, outside clicks close, price popover focuses its slider.
  await page.click('[data-cf-select=category] .cf-trigger');
  await page.click('[data-cf-select=price] .cf-trigger');
  check(await page.locator('[data-cf-select=category] .cf-menu').isHidden(), 'Opening another dropdown closes the first');
  check(await page.locator('#cf-price-pop').isVisible(), 'Price popover opens');
  await page.waitForFunction(() => !document.querySelector('#cf-range').disabled);
  await page.click('[data-cf-select=price] .cf-trigger'); await page.click('[data-cf-select=price] .cf-trigger');
  check(await page.evaluate(() => document.activeElement.id) === 'cf-range', 'Slider focused when the popover opens');
  await page.click('h1');
  check(await page.locator('#cf-price-pop').isHidden(), 'Outside click closes the popover');

  // Marketplace: applying still filters and stores the choice.
  const done = page.waitForResponse(r => r.url().includes('/api/listings?') && r.url().includes('material=PETG'));
  await page.click('#cf-apply'); await done;
  check(await page.locator('#cf-chips .cf-chip').filter({hasText:'PETG'}).count() === 1, 'Applied filter chip shown');
  await page.click('[data-cf-clear]');
  check(await hidden('material') === '' && await hidden('sort') === 'newest', 'Clear filters resets the dropdowns');

  // Searchable mode, rendered on its own form.
  const changes = await page.evaluate(() => {
    document.querySelector('#app').insertAdjacentHTML('beforeend', `<form id="qa-select" style="width:280px;margin:20px">${uiSelect({name:'country', label:'Country', searchable:true, required:true, value:'IT', options:[['DE', 'Germany'], ['IT', 'Italy'], ['FR', 'France'], ['CI', 'Côte d’Ivoire']]})}<button id="qa-after">After</button></form>`);
    window.qaChanges = []; document.querySelector('#qa-select').addEventListener('change', e => qaChanges.push(e.target.value));
    return qaChanges;
  });
  const root = '#qa-select [data-select=country]', input = root + ' .cf-input', menu = root + ' .cf-menu';
  const visible = () => page.locator(menu + ' [role=option]:visible').allTextContents();
  check(await page.inputValue(input) === 'Italy', 'Inactive searchable select shows the selected label');
  check(await page.getAttribute(input, 'placeholder') === 'Search…', 'Placeholder reads Search…');
  check(await page.getAttribute(input, 'role') === 'combobox' && await page.getAttribute(menu, 'role') === 'listbox', 'Combobox and listbox roles');
  check(await page.locator(root + ' input:not([type=hidden])').count() === 1, 'Only one text input');
  await page.click(input);
  check(await page.locator(menu).isVisible(), 'Click opens the menu directly');
  const box = await page.locator(root + ' .cf-combo').boundingBox(), list = await page.locator(menu).boundingBox();
  check(list.y >= box.y + box.height && list.y - (box.y + box.height) < 12, 'Menu sits directly below the input');
  check((await visible()).length === 4, 'All options listed before typing');
  check(await page.evaluate(i => { const el = document.querySelector(i); return el.selectionStart === 0 && el.selectionEnd === el.value.length; }, input), 'Current value selected for editing');
  await page.keyboard.type('ger');
  check(JSON.stringify(await visible()) === '["Germany"]', 'Typing filters live');
  await page.keyboard.press('Enter');
  check(await page.inputValue(root + ' input[type=hidden]') === 'DE' && await page.inputValue(input) === 'Germany', 'Enter chooses the match');
  check(await page.locator(menu).isHidden(), 'Menu closes after Enter');
  await page.keyboard.press('ArrowDown');
  check(await page.locator(menu).isVisible(), 'ArrowDown reopens');
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
  check(await page.inputValue(root + ' input[type=hidden]') === 'IT', 'Arrow moves from the selected option');
  await page.keyboard.type('cote');
  check(JSON.stringify(await visible()) === '["Côte d’Ivoire"]', 'Matching ignores accents');
  await page.keyboard.press('Escape');
  check(await page.locator(menu).isHidden() && await page.inputValue(input) === 'Italy', 'Escape closes and restores the label');
  await page.keyboard.type('zzz');
  check(await page.locator(root + ' .cf-no-match').isVisible(), 'No-match state shown');
  await page.keyboard.press('Tab');
  check(await page.inputValue(input) === 'Italy' && await page.locator(menu).isHidden(), 'Leaving discards half-typed text');
  await page.click(root + ' .cf-combo-toggle');
  check(await page.locator(menu).isVisible(), 'Chevron opens the menu');
  await page.click(menu + ' [role=option]:has-text("France")');
  check(await page.inputValue(root + ' input[type=hidden]') === 'FR' && await page.evaluate(i => document.activeElement === document.querySelector(i), input), 'Mouse choice keeps focus in the input');
  check(JSON.stringify(await page.evaluate(() => qaChanges)) === '["DE","IT","FR"]', 'change fires once per new value');
  await page.evaluate(() => uiSelectSetOptions('country', [['FR', 'France'], ['ES', 'Spain']]));
  check(await page.inputValue(input) === 'France' && (await page.locator(menu + ' [role=option]').count()) === 2, 'Options can be replaced, keeping the value');
  await page.evaluate(() => uiSelectSetOptions('country', [['ES', 'Spain']]));
  check(await page.inputValue(input) === '' && await page.evaluate(i => !document.querySelector(i).checkValidity(), input), 'A required select with no value is invalid');
  return {ok:true, changes};
}
