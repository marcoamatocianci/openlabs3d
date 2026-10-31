// Isolated fixtures: run scripts/catalogue_preview.py, then this file with Playwright MCP
// browser_run_code_unsafe or tests/run_playwright_script.js. Uses guest storage only.
async page => {
 const BASE=globalThis.OPENLABS3D_BASE||'http://127.0.0.1:18101';
 const context=await page.context().browser().newContext({viewport:{width:1280,height:900}});
 const p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 try{
  await p.goto(BASE+'/#catalogue');
  // Products are found by their collection key, not by database id.
  const ids=await p.evaluate(async()=>Object.fromEntries((await (await fetch('/api/listings?per_page=12')).json()).items.map(i=>[i.collection_key,i.id])));
  const micro='api-'+ids['microtube-rack'],fifteen='api-'+ids['15ml-rack'];
  await p.goto(BASE+'/#product/'+micro);
  await p.locator('#config-add:enabled').waitFor();
  await p.waitForFunction(()=>document.querySelector('#model-viewer')?.dataset.loaded==='true');
  const before=await p.locator('#model-viewer canvas').screenshot();
  await p.locator('.material-choice').filter({has:p.locator('input[value=PLA]')}).click();
  await p.locator('.swatches label').filter({has:p.locator('input[value=orange]')}).click();
  await p.waitForFunction(()=>document.querySelector('#live-price')?.dataset.ready==='1');
  const after=await p.locator('#model-viewer canvas').screenshot();
  assert(!before.equals(after),'3D preview should visibly change color');
  await p.getByRole('link',{name:'← Catalogue / Tube racks'}).click();
  const card=p.locator('.product-card').filter({has:p.locator(`a[href="#product/${micro}"]`)});
  await card.waitFor();
  assert((await card.locator('.product-card-selection').innerText()).includes('PLA · Orange'),'Card label must remember selection');
  await p.waitForFunction(()=>id=>document.querySelector(`img[data-product="${id}"]`)?.dataset.tinted==='#e66100');
  assert(await card.locator('input,select').count()===0,'Cards must remain minimal');
  await card.locator('a').click();await p.locator('#config-add:enabled').waitFor();await p.reload();await p.locator('#config-add:enabled').waitFor();
  assert(await p.locator('input[name=color]:checked').inputValue()==='orange','Refresh must restore selection');
  await p.goto(BASE+'/#product/'+fifteen);await p.locator('#config-add:enabled').waitFor();
  // Colours come from host stock: check the selection against the eligible combinations instead of a fixed colour.
  const offer=await p.evaluate(async id=>(await (await fetch(`/api/listings/${id}/availability`)).json()),ids['15ml-rack']);
  const chosen={material:await p.locator('input[name=material]:checked').inputValue(),color:await p.locator('input[name=color]:checked').inputValue()};
  assert(offer.colors_by_material[chosen.material]?.[chosen.color],'Default selection must be an eligible material and colour');
  assert(chosen.material===Object.keys(offer.materials)[0]&&chosen.color===Object.keys(offer.colors_by_material[chosen.material])[0],'Without a saved choice the first eligible configuration is selected');
  assert(!(chosen.material==='PLA'&&chosen.color==='orange'),'Selections must be independent: the microtube rack choice must not carry over');
  await p.setViewportSize({width:390,height:844});await p.evaluate(()=>applyTheme('dark'));
  assert(!await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Mobile detail overflow');
  await p.goto(BASE+'/#catalogue');await p.locator('.product-card').first().waitFor();
  assert(!await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Mobile catalogue overflow');
  await p.evaluate(id=>localStorage.setItem('ol3d-config-guest-'+id,JSON.stringify({product_id:id,material:'PLA',color:'retired',quantity:1})),micro);
  await p.goto(BASE+'/#product/'+micro);
  await p.getByText('Your saved configuration is no longer available. Choose an available material and color before purchasing.').waitFor();
  await p.evaluate(()=>document.querySelector('#configurator').refreshAvailability());
  assert(await p.locator('#config-add').isDisabled()&&await p.locator('#buy-now').isDisabled(),'Invalid saved selection must block purchasing');
  await p.locator('.swatches label').filter({has:p.locator('input[value=orange]')}).click();await p.locator('#config-add:enabled').waitFor();
  assert(errors.length===0,errors.join('\n'));
  return {passed:true,checks:['visible WebGL color change','minimal remembered-color card','reload persistence','per-product isolation','mobile dark theme','invalid-selection blocking and recovery','no page errors']};
 }finally{await context.close()}
}
