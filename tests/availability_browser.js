// Run scripts/availability_preview.py (fresh temporary DB on each start), then this file with
// Playwright's browser_run_code_unsafe or tests/run_playwright_script.js.
async (page) => {
  const base='http://127.0.0.1:18097';
  const assert=(condition,message)=>{if(!condition)throw Error(message)};
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#account');
  await page.locator('#real-login input[name=email]').fill('buyer@example.org');
  await page.locator('#real-login input[name=password]').fill('TestPassword2026');
  await page.locator('#real-login button.primary').click();
  await page.waitForFunction(()=>!!account);
  await page.goto(base+'/#product/api-1');
  await page.locator('#config-add:enabled').waitFor();
  assert(await page.locator('.swatches input').count()===3,'PLA should have three colors');
  await page.locator('.material-choice').filter({has:page.locator('input[value=PETG]')}).click();
  await page.locator('.swatches label').filter({has:page.locator('input[value=white]')}).click();
  await page.locator('#config-add:enabled').waitFor();
  assert(await page.locator('.swatches input').count()===2,'PETG should have two colors');
  await page.locator('#config-add').click();
  await page.getByText('Added!',{exact:true}).waitFor();
  let cart=await(await page.request.get(base+'/api/cart')).json();
  assert(cart[0].material==='PETG'&&cart[0].color==='white'&&cart[0].total_cents===1200,'Exact configuration and price');
  await page.setViewportSize({width:390,height:844});
  assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Mobile must not overflow');
  await page.locator('#buy-now:enabled').waitFor();await page.locator('#buy-now').click();
  await page.locator('#checkout-form').waitFor();
  await page.locator('input[name=street]').fill('Via Roma 1');
  await page.locator('#new-address [data-location=region] .cf-input').fill('Piedmont');await page.keyboard.press('Tab');
  await page.locator('#new-address [name=postal_code]').fill('10100');
  await page.getByRole('button',{name:'Submit order request'}).click();
  await page.waitForURL('**/#orders');
  assert((await(await page.request.get(base+'/api/orders')).json()).length===1,'Checkout creates one order');
  assert((await(await page.request.get(base+'/api/cart')).json()).length===1,'Direct checkout preserves cart');
  await page.goto(base+'/#product/api-1');await page.locator('#config-add:enabled').waitFor();
  const hostContext=await page.context().browser().newContext();
  try{
    const login=await(await hostContext.request.post(base+'/api/auth/login',{data:{email:'other@example.org',password:'TestPassword2026'}})).json();
    const headers={'X-CSRF-Token':login.csrf_token};
    const jobs=await(await hostContext.request.get(base+'/api/host/jobs')).json();
    assert((await hostContext.request.post(base+'/api/host/jobs/'+jobs[0].id+'/accept',{headers})).status()===200,'Compatible host accepts job');
    // My Equipment → Materials & Colors: stock is host-managed and live without a review.
    const editor=await hostContext.newPage();editor.on('pageerror',e=>errors.push(e.message));
    await editor.goto(base+'/#my-printers/materials');await editor.locator('#eq-stock .inv').first().waitFor();
    const settle=()=>editor.waitForFunction(()=>!document.querySelector('#eq-stock [aria-busy=true]'));
    await editor.locator('[data-open-material="PETG"]').click();
    await editor.getByRole('button',{name:'Remove White from PETG'}).click();await settle();
    await editor.locator('[data-custom-color="PETG"] [name=name]').fill('Lab green');await editor.locator('[data-custom-color="PETG"] [name=hex]').fill('#00ff00');
    await editor.locator('[data-custom-color="PETG"] button').click();await settle();
    // Standard colours toggle with a single click.
    const black=()=>editor.locator('[data-toggle-color="black"][data-material="PETG"]');
    await black().click();await settle();assert(await black().getAttribute('aria-pressed')==='true','One click adds a standard color');
    await black().click();await settle();assert(await black().getAttribute('aria-pressed')==='false','A second click removes it');
    // Rename a colour in place (e.g. a "yellow-2" left by the stock merge).
    await editor.locator('[data-rename-start="lab-green"][data-material="PETG"]').click();
    await editor.locator('[data-rename="PETG"] input').fill('Bench green');await editor.locator('[data-rename="PETG"] input').press('Enter');await settle();
    const renamed=(await(await hostContext.request.get(base+'/api/host/materials')).json()).material_colors.PETG;
    assert(renamed['bench-green']==='#00ff00'&&!renamed['lab-green'],'Colour renamed, shade kept');
    const stock=(await(await hostContext.request.get(base+'/api/host/equipment')).json())[0].material_colors.PETG;
    assert(stock['bench-green']==='#00ff00'&&!stock.white,'Stock changes are saved directly');
    const offer=(await(await page.request.get(base+'/api/listings/1/availability')).json()).colors_by_material.PETG;
    assert(offer['bench-green']==='#00ff00'&&!offer.white,'Buyers see the new stock at once');
    assert(!(await(await page.request.get(base+'/api/cart')).json())[0].available,'A basket line no host can make becomes unavailable');
    // The accepted order keeps the configuration that was bought, and stays with its host.
    const job=(await(await hostContext.request.get(base+'/api/host/jobs')).json()).find(j=>j.id===jobs[0].id);
    assert(job&&job.status==='accepted'&&job.item.material==='PETG'&&job.item.color==='white'&&job.item.color_hex==='#ffffff','Accepted job keeps its snapshot');
    const bought=(await(await page.request.get(base+'/api/orders')).json())[0].items[0];
    assert(bought.color==='white'&&bought.color_hex==='#ffffff','Buyer order keeps the purchased colour');
    assert((await(await hostContext.request.get(base+'/api/auth/me')).json()).user.role==='host','Stock edits keep the host role');
  }finally{await hostContext.close()}
  assert(errors.length===0,errors.join('\n'));
  return {passed:true,checks:['material/color filtering','dynamic price','persistent cart','direct checkout','compatible assignment','materials & colors stock editing','live marketplace availability','unavailable basket line','order snapshot kept','mobile layout','no page errors']};
}
