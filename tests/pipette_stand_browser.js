// Isolated fixtures: run scripts/catalogue_preview.py, then this file with Playwright MCP
// browser_run_code_unsafe or tests/run_playwright_script.js. Uses guest storage only.
// The fixture publishes the DNA pipette stand and stocks PLA/PETG/ABS in cream and signal-red.
async page => {
 const BASE=globalThis.OPENLABS3D_BASE||'http://127.0.0.1:18101';
 const context=await page.context().browser().newContext({viewport:{width:1280,height:900}});
 const p=await context.newPage(),errors=[],glb=[];p.on('pageerror',e=>errors.push(e.message));
 p.on('request',r=>{if(r.url().endsWith('.glb'))glb.push(r.url())});
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 try{
  await p.goto(BASE+'/#home');
  const stand=await p.evaluate(async()=>(await (await fetch('/api/listings?category=Pipette%20holders')).json()).items.find(i=>i.collection_key==='dna-pipette-stand'));
  assert(stand,'Stand must be published in Pipette holders');
  const route='#product/api-'+stand.id;
  await p.goto(BASE+'/'+route);await p.locator('#config-add:enabled').waitFor();
  await p.waitForFunction(()=>document.querySelector('#model-viewer')?.dataset.loaded==='true');
  assert(glb.some(u=>u.endsWith(stand.configurator.model_url)),'Viewer must load the listing model '+stand.configurator.model_url);
  const canvas=p.locator('#model-viewer canvas'),initial=await canvas.screenshot();
  // Prices shown come from the server quote for every material.
  for(const material of ['PLA','PETG','ABS']){
   await p.locator('.material-choice').filter({has:p.locator(`input[value=${material}]`)}).click();
   await p.locator('.swatches label').filter({has:p.locator('input[value=cream]')}).click();
   await p.waitForFunction(()=>document.querySelector('#live-price')?.dataset.ready==='1');
   const quote=await p.evaluate(async([id,material])=>(await (await fetch(`/api/listings/${id}/quote`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({material,color:'cream',quantity:1})})).json()),[stand.id,material]);
   const shown=await p.locator('#live-price').innerText();
   assert(shown.includes((quote.total_cents/100).toFixed(2)),`Displayed ${material} price must equal the server quote ${quote.total_cents}`);
  }
  const cream=await canvas.screenshot();assert(!initial.equals(cream),'Changing colour must repaint the model');
  await p.locator('.swatches label').filter({has:p.locator('input[value=signal-red]')}).click();await p.waitForTimeout(200);
  assert(!cream.equals(await canvas.screenshot()),'Each colour must repaint the model');
  // Rotate, zoom and reset.
  const box=await canvas.boundingBox(),before=await canvas.screenshot();
  await p.mouse.move(box.x+box.width/2,box.y+box.height/2);await p.mouse.down();await p.mouse.move(box.x+box.width/2+160,box.y+box.height/2,{steps:8});await p.mouse.up();
  const rotated=await canvas.screenshot();assert(!before.equals(rotated),'Drag must rotate the model');
  await p.locator('#zoom-in').click();assert(!rotated.equals(await canvas.screenshot()),'Zoom must change the view');
  await p.locator('#reset-view').click();assert(before.equals(await canvas.screenshot()),'Reset View must restore the default framing');
  // Catalogue card.
  await p.goto(BASE+'/#catalogue');const card=p.locator('.product-card').filter({has:p.locator(`a[href="${route}"]`)});await card.waitFor();
  assert(await card.locator('img').count()>0,'Catalogue card must show the product image');
  // Image fallback when the GLB cannot load.
  await p.route('**/*.glb',r=>r.abort());await p.goto(BASE+'/'+route);await p.locator('#config-add:enabled').waitFor();
  await p.getByText('3D preview unavailable').waitFor();
  assert(await p.locator('#model-viewer img').count()===1&&!await p.locator('#model-viewer canvas').count(),'Still image must replace the failed 3D model');
  await p.unroute('**/*.glb');
  await p.setViewportSize({width:390,height:844});await p.goto(BASE+'/'+route);await p.locator('#config-add:enabled').waitFor();
  assert(!await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'Mobile product page overflow');
  assert(errors.length===0,errors.join('\n'));
  return {passed:true,model:stand.configurator.model_url,checks:['model loads','server quote per material','colour repaint','rotate/zoom/reset','catalogue card','image fallback on GLB failure','mobile layout','no page errors']};
 }finally{await context.close()}
}
