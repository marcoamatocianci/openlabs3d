// Run with Playwright MCP browser_run_code_unsafe. Uses guest storage only.
async page => {
 const context=await page.context().browser().newContext({viewport:{width:1280,height:900}});
 const p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 try{
  await p.goto('http://127.0.0.1:8080/#product/api-2');
  await p.locator('#config-add:enabled').waitFor();
  await p.waitForFunction(()=>document.querySelector('#model-viewer')?.dataset.loaded==='true');
  const before=await p.locator('#model-viewer canvas').screenshot();
  await p.locator('.material-choice').filter({has:p.locator('input[value=PLA]')}).click();
  await p.locator('.swatches label').filter({has:p.locator('input[value=orange]')}).click();
  await p.waitForFunction(()=>document.querySelector('#live-price')?.dataset.ready==='1');
  const after=await p.locator('#model-viewer canvas').screenshot();
  assert(!before.equals(after),'3D preview should visibly change color');
  await p.getByRole('link',{name:'← Catalogue / Tube racks'}).click();
  const card=p.locator('.product-card').filter({has:p.locator('a[href="#product/api-2"]')});
  await card.waitFor();
  assert((await card.locator('.product-card-selection').innerText()).includes('PLA · orange'),'Card label must remember selection');
  await p.waitForFunction(()=>document.querySelector('img[data-product="api-2"]')?.dataset.tinted==='#e66100');
  assert(await card.locator('input,select').count()===0,'Cards must remain minimal');
  await card.locator('a').click();await p.locator('#config-add:enabled').waitFor();await p.reload();await p.locator('#config-add:enabled').waitFor();
  assert(await p.locator('input[name=color]:checked').inputValue()==='orange','Refresh must restore selection');
  await p.goto('http://127.0.0.1:8080/#product/api-3');await p.locator('#config-add:enabled').waitFor();
  assert(await p.locator('input[name=color]:checked').inputValue()==='white','Selections must be independent');
  await p.setViewportSize({width:390,height:844});await p.evaluate(()=>applyTheme('dark'));
  assert(!await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Mobile detail overflow');
  await p.goto('http://127.0.0.1:8080/#catalogue');await p.locator('.product-card').first().waitFor();
  assert(!await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Mobile catalogue overflow');
  await p.evaluate(()=>localStorage.setItem('ol3d-config-guest-api-2',JSON.stringify({product_id:'api-2',material:'PLA',color:'retired',quantity:1})));
  await p.goto('http://127.0.0.1:8080/#product/api-2');
  await p.getByText('Your saved configuration is no longer available. Choose an available material and color before purchasing.').waitFor();
  await p.evaluate(()=>document.querySelector('#configurator').refreshAvailability());
  assert(await p.locator('#config-add').isDisabled()&&await p.locator('#buy-now').isDisabled(),'Invalid saved selection must block purchasing');
  await p.locator('.swatches label').filter({has:p.locator('input[value=orange]')}).click();await p.locator('#config-add:enabled').waitFor();
  assert(errors.length===0,errors.join('\n'));
  return {passed:true,checks:['visible WebGL color change','minimal remembered-color card','reload persistence','per-product isolation','mobile dark theme','invalid-selection blocking and recovery','no page errors']};
 }finally{await context.close()}
}
