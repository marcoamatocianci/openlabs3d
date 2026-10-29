// Run using Playwright's browser_run_code_unsafe filename argument against
// scripts/availability_preview.py. Fixtures are isolated in a fresh temporary DB.
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
    const editor=await hostContext.newPage();editor.on('pageerror',e=>errors.push(e.message));
    await editor.goto(base+'/#my-printers/edit');
    await editor.locator('#next-step').click();await editor.locator('#next-step').click();
    const material=editor.locator('.host-color-editor').filter({has:editor.getByRole('heading',{name:'PETG',exact:true})});
    await material.getByRole('button',{name:'Remove white from PETG'}).click();
    await material.getByPlaceholder('e.g. aqua-blue').fill('green');
    await material.locator('input[type=color]').fill('#00ff00');
    await material.getByRole('button',{name:'Add color',exact:true}).click();
    const save=editor.waitForResponse(r=>r.url().endsWith('/host/equipment-application')&&r.request().method()==='PUT');
    await editor.getByRole('button',{name:'Save Draft',exact:true}).click();assert((await save).status()===200,'Host equipment saved');
    const equipment=await(await hostContext.request.get(base+'/api/host/equipment')).json();
    assert(equipment[0].material_colors.PETG.green==='#00ff00'&&!equipment[0].material_colors.PETG.white,'Per-material color changes persist');
    await page.waitForFunction(()=>!document.querySelector('.swatches input[value=white]'),{},{timeout:22000});
    assert(await page.locator('input[name=color]:checked').inputValue()==='black','Stale selection replaced');
    cart=await(await page.request.get(base+'/api/cart')).json();assert(!cart[0].available,'Stale cart configuration unavailable');
    const first=await(await hostContext.request.post(base+'/api/auth/login',{data:{email:'host@example.org',password:'TestPassword2026'}})).json();
    const printers=await(await hostContext.request.get(base+'/api/host/equipment')).json();
    assert((await hostContext.request.put(base+'/api/host/equipment-application',{headers:{'X-CSRF-Token':first.csrf_token},data:{submit:false,printers:printers.map(({id,verified,...p})=>p)}})).status()===200,'Last eligible host updates capabilities');
    await page.waitForFunction(()=>document.querySelector('.material-grid')?.children.length===0,{},{timeout:22000});
    assert(await page.locator('#config-add').isDisabled()&&await page.locator('#buy-now').isDisabled(),'Unavailable products cannot be purchased');
    assert(await page.locator('.swatches input').count()===0,'Unavailable selections cleared');
  }finally{await hostContext.close()}
  assert(errors.length===0,errors.join('\n'));
  return {passed:true,checks:['material/color filtering','dynamic price','persistent cart','direct checkout','compatible assignment','host color editing','live invalidation','empty state','mobile layout','no page errors']};
}
