// Playwright MCP browser_run_code_unsafe; requires a fresh scripts/orders_preview.py (it changes an address
// and confirms a delivery). Fixture: buyer orders OL3D-QA-1001…1015; pending 1007/1014, in progress
// 1001–1003/1008–1010/1015 (three products: printing, received, awaiting a host), shipping 1004/1011,
// completed 1005/1012, cancelled 1006/1013. OL3D-QA-1000 belongs to "other".
async page => {
  const base='http://127.0.0.1:18100',check=(ok,message)=>{if(!ok)throw Error(message)};
  const failures=[];page.on('pageerror',e=>failures.push(e.message));
  await page.context().clearCookies();
  await page.setViewportSize({width:1280,height:900});
  await page.goto(base+'/?qa='+Date.now()+'#account');await page.waitForLoadState('networkidle');
  await page.evaluate(()=>sessionStorage.clear());
  const login=async name=>{
    await page.locator('#real-login [name=email]').fill(name+'@example.org');
    await page.locator('#real-login [name=password]').fill('TestPassword2026');
    await page.locator('#real-login button').click();
    await page.waitForFunction(n=>account?.email===n+'@example.org',name);
  };
  await login('buyer');
  const settled=()=>page.waitForFunction(()=>!!buyerOrdersShown&&!document.querySelector('#bo-results[aria-busy]'));
  const goto=async hash=>{await page.goto(base+'/#'+hash);await settled();};
  const refs=(scope='')=>page.locator(scope+' .bo-card .bo-ref').allTextContents();
  const column=key=>page.locator(`#bo-board [data-stage="${key}"]`);
  const navigate=async action=>{
    const done=page.waitForResponse(r=>r.url().includes('/api/orders?')&&r.status()===200);
    await action();await done;await settled();
  };
  // Current orders is the default view: a board with one column per stage, no completed or cancelled order.
  await goto('orders');
  check((await page.locator('.scope-nav .segment[aria-current]').innerText()).startsWith('Current orders'),'Current orders is the default view');
  const nav=(await page.locator('.scope-nav').innerText()).replace(/\s+/g,' ');
  check(nav.includes('Current orders 11')&&nav.includes('Previous orders 4'),'Active and history counts are separate');
  check(JSON.stringify(await page.locator('#bo-board .wf-column').evaluateAll(cs=>cs.map(c=>[c.dataset.stage,c.querySelectorAll('.bo-card').length])))==='[["pending",2],["in-progress",7],["shipping",2]]','Orders grouped by stage');
  check(JSON.stringify(await page.locator('#bo-board .wf-column-head .segment-count').evaluateAll(es=>es.map(e=>parseInt(e.textContent))))==='[2,7,2]','Column counts');
  check((await refs()).length===11&&!(await page.locator('#bo-board .bo-card-stage .status').allTextContents()).some(s=>['Completed','Cancelled'].includes(s)),'Every current order, nothing finished');
  check((await refs('#bo-board [data-stage="in-progress"]'))[0]==='OL3D-QA-1015','Newest first within a stage');
  await page.waitForFunction(()=>document.querySelector('.bo-thumb img')?.naturalWidth>0);
  // A three-product order with products at different stages: in progress, every stage counted.
  const mixed=page.locator('.bo-card',{hasText:'OL3D-QA-1015'});
  check(await mixed.locator('.bo-line').count()===2&&(await mixed.innerText()).includes('+ 1 more product'),'Compact product preview');
  check((await mixed.locator('.bo-mix').innerText())==='1 received · 1 in production · 1 awaiting a host','Every product stage on the card: '+await mixed.locator('.bo-mix').innerText());
  check((await mixed.innerText()).includes('€72.00'),'Snapshot total');
  await mixed.getByRole('button',{name:/View details/}).focus();await page.keyboard.press('Enter');
  await page.locator('#modal[open]').waitFor();
  const details=await page.locator('#modal').innerText();
  for(const value of ['Archived sample rack','PLA · Custom violet','Quantity 2','order-contact@example.org','Via Laboratory 12','Made by a printing host','Awaiting a host','Received','In production'])
    check(details.includes(value),'Missing snapshot/fulfillment detail: '+value);
  check(!details.includes('Updated catalogue product')&&!details.includes('€99.00'),'Live listing leaked into snapshots');
  check(await page.locator('#modal .bo-detail-line').count()===3&&await page.locator('#modal .bo-delivery .bo-fact').count()===2,'Details: every product once, contact and address');
  check(await page.locator('#modal [data-change-address]').isDisabled()&&(await page.locator('#modal .bo-delivery').innerText()).includes('fixed once a product has shipped'),'Address locked once a product is completed');
  await page.screenshot({animations:'disabled',path:'.playwright-mcp/orders-details-bright.png'});
  await page.keyboard.press('Escape');
  check(await page.evaluate(()=>document.activeElement?.closest('.bo-card')?.textContent.includes('OL3D-QA-1015')),'Closing the details returns focus to the card');
  await page.screenshot({animations:'disabled',fullPage:true,path:'.playwright-mcp/orders-desktop-bright.png'});
  // Shipping: tracking and the receipt confirmation on the card; nothing to confirm elsewhere.
  for(const card of await column('shipping').locator('.bo-card').all()){
    check(await card.locator('a[href^="https://www.dhl.com/track"]').count()===1&&(await card.innerText()).includes('DHL Express'),'Shipped orders show tracking');
    check(await card.getByRole('button',{name:/Mark as received/}).count()===1,'Shipped orders offer Mark as received');
  }
  check(await column('pending').locator('.bo-shipments').count()===0,'Pending orders show no receipt action');
  // Previous orders: completed and cancelled, by status, searchable.
  await navigate(()=>page.getByRole('navigation',{name:'My orders'}).getByRole('link',{name:/Previous orders/}).click());
  let statuses=await page.locator('.bo-row .row-status .status').allTextContents();
  check(statuses.length===4&&statuses.every(s=>['Completed','Cancelled'].includes(s)),'Previous orders holds completed and cancelled orders');
  for(const [label,count] of [['Completed',2],['Cancelled',2]]){
    await navigate(()=>page.getByRole('navigation',{name:'Previous orders by status'}).getByRole('link',{name:new RegExp('^'+label)}).click());
    statuses=await page.locator('.bo-row .row-status .status').allTextContents();
    check(statuses.length===count&&statuses.every(s=>s===label),'Incorrect '+label+' grouping');
  }
  await navigate(()=>page.getByRole('navigation',{name:'Previous orders by status'}).getByRole('link',{name:/^All/}).click());
  await page.locator('#bo-q').fill('1012');
  await navigate(()=>page.locator('#bo-q').press('Enter'));
  check(JSON.stringify(await refs())==='["OL3D-QA-1012"]'&&page.url().includes('q=1012'),'Search by order number');
  await page.locator('#bo-q').fill('no such product');
  await navigate(()=>page.locator('#bo-q').press('Enter'));
  check((await page.locator('.bo-page').innerText()).includes('No orders match your search'),'Search empty state');
  // Sorting applies within each stage and is remembered for the session.
  await navigate(()=>page.getByRole('navigation',{name:'My orders'}).getByRole('link',{name:/Current orders/}).click());
  await navigate(async()=>{await page.click('[data-select=bo-sort] .cf-trigger');await page.click('[data-select=bo-sort] [role=option][data-value=oldest]')});
  check((await refs('#bo-board [data-stage="pending"]'))[0]==='OL3D-QA-1007','Combined sorting and grouping');
  await page.goto(base+'/#catalogue');await page.waitForLoadState('networkidle');
  await goto('orders');
  check(await page.locator('[data-select=bo-sort] input[type=hidden]').inputValue()==='oldest'&&await page.locator('[data-select=bo-sort] .cf-value').textContent()==='Oldest first','Sort not preserved');
  check((await refs('#bo-board [data-stage="in-progress"]'))[0]==='OL3D-QA-1001','My orders reopens on Current orders, in the remembered order');
  await goto('orders?group=pending&sort=oldest');
  await page.reload();await settled();
  check((await refs('#bo-board [data-stage="pending"]'))[0]==='OL3D-QA-1007'&&await page.locator('#bo-board [data-stage="pending"].is-focus').count()===1,'Reload keeps the view in the address');
  await goto('orders?sort=newest');
  await page.evaluate(()=>document.documentElement.dataset.theme='dark');
  await page.waitForFunction(()=>document.querySelector('.bo-thumb img')?.naturalWidth>0);
  await page.screenshot({animations:'disabled',fullPage:true,path:'.playwright-mcp/orders-desktop-dark.png'});
  // Status text must retain AA contrast in each existing theme.
  for(const theme of ['dark','light']){
    const contrast=await page.evaluate(theme=>{
      document.documentElement.dataset.theme=theme;
      const lum=values=>{const rgb=values.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]};
      return [...document.querySelectorAll('.bo-card .status')].map(el=>{const s=getComputedStyle(el),parse=v=>v.match(/[\d.]+/g).map(Number),fg=parse(s.color),bg=parse(s.backgroundColor),surface=parse(getComputedStyle(el.closest('.bo-card')).backgroundColor),alpha=bg[3]??1,a=lum(fg.slice(0,3)),b=lum(bg.slice(0,3).map((v,i)=>v*alpha+surface[i]*(1-alpha)));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)});
    },theme);
    check(contrast.every(r=>r>=4.5),theme+' status contrast: '+contrast);
  }
  await page.setViewportSize({width:390,height:844});
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile overflow');
  check(await page.locator('.wf-stages').isVisible(),'Mobile: stage strip');
  await page.locator('.bo-card [data-order-details]').first().click();await page.locator('#modal[open]').waitFor();
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Detail overflow');
  await page.screenshot({animations:'disabled',path:'.playwright-mcp/orders-mobile-dark.png'});
  await page.keyboard.press('Escape');
  await page.evaluate(()=>document.documentElement.dataset.theme='light');
  await page.screenshot({animations:'disabled',path:'.playwright-mcp/orders-mobile-bright.png'});
  await page.setViewportSize({width:768,height:1024});
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Tablet overflow');
  await page.setViewportSize({width:1280,height:900});
  // Simulate service states without modifying any order records.
  const pattern='**/api/orders?*';let release;
  const gate=new Promise(resolve=>release=resolve);
  await page.route(pattern,async route=>{await gate;await route.continue()});
  await page.goto(base+'/#catalogue');await page.waitForLoadState('networkidle');
  await page.goto(base+'/#orders');
  await page.getByRole('status',{name:'Loading orders'}).waitFor();
  release();await page.locator('.bo-card').first().waitFor();await page.unroute(pattern);
  await page.route(pattern,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Temporarily unavailable'})}));
  await page.evaluate(()=>render());
  await page.getByRole('heading',{name:'Unable to load orders'}).waitFor();
  await page.unroute(pattern);
  await page.getByRole('button',{name:'Retry',exact:true}).click();await page.locator('.bo-card').first().waitFor();
  await page.route(pattern,async route=>{const response=await route.fetch(),data=await response.json();await route.fulfill({json:{...data,items:[],total:0,page:1,pages:1}})});
  await navigate(()=>page.evaluate(()=>{location.hash='#orders?sort=oldest'}));
  check((await page.locator('.bo-page').innerText()).includes('No current orders at the moment'),'Empty board state');
  await page.unroute(pattern);
  // A shipped order's address is locked; a pending order's address changes from its details.
  await goto('orders');
  await column('shipping').locator('[data-order-details]').first().click();await page.locator('#modal[open]').waitFor();
  check(await page.locator('#modal [data-change-address]').isDisabled(),'Shipped orders cannot change address');
  await page.keyboard.press('Escape');
  await column('pending').locator('[data-order-details]').first().click();await page.locator('#modal[open]').waitFor();
  await page.locator('#modal [data-change-address]').click();
  await page.locator('#action-dialog[open] #order-address-form').waitFor();
  check(await page.locator('#action-dialog [name=street]').inputValue()==='Via Laboratory 12','Current address prefilled');
  await page.locator('#action-dialog [name=street]').fill('');
  await page.locator('#action-dialog').getByRole('button',{name:'Save address'}).click();
  check((await page.locator('#action-dialog .ad-error').innerText()).includes('street'),'Street required');
  await page.locator('#action-dialog [name=street]').fill('Via Nuova 5');
  const saved=page.waitForResponse(r=>r.url().includes('/address')&&r.request().method()==='PUT'&&r.status()===200);
  await page.locator('#action-dialog').getByRole('button',{name:'Save address'}).click();await saved;
  await page.waitForFunction(()=>document.querySelector('#modal[open] address')?.textContent.includes('Via Nuova 5'));
  check(true,'Address updated in the open details');
  await page.keyboard.press('Escape');
  // Mark as received: confirmed in the site dialog; the order completes and moves to Previous orders.
  const shippedRef=(await refs('#bo-board [data-stage="shipping"]'))[0];
  await column('shipping').locator('.bo-card').first().getByRole('button',{name:/Mark as received/}).click();
  await page.locator('#action-dialog[open]').waitFor();
  check(await page.locator('#action-dialog').getByRole('heading',{name:'Mark as received?'}).isVisible(),'Receipt confirmation dialog');
  await page.locator('#action-dialog').getByRole('button',{name:'Cancel'}).click();
  check((await refs('#bo-board [data-stage="shipping"]'))[0]===shippedRef,'Cancel keeps the order shipped');
  await column('shipping').locator('.bo-card').first().getByRole('button',{name:/Mark as received/}).click();
  const received=page.waitForResponse(r=>r.url().includes('/received')&&r.status()===200);
  await page.locator('#action-dialog').getByRole('button',{name:'Mark as received'}).click();await received;
  await page.waitForFunction(ref=>![...document.querySelectorAll('#bo-board .bo-ref')].some(h=>h.textContent===ref),shippedRef);
  check(await column('shipping').locator('.bo-card').count()===1,'Received order leaves Current orders');
  check((await page.locator('#toast').innerText()).includes('Previous orders'),'Completion says where the order went');
  await goto('orders?scope=history&group=completed');
  check((await refs()).includes(shippedRef),'Received order is completed');
  check((await page.locator('#bo-toolbar .chip',{hasText:'Completed'}).innerText()).replace(/\s+/g,' ').trim()==='Completed 3','Completed count updated');
  // Owner scoping is verified on real API responses with separate authenticated sessions.
  await page.evaluate(()=>logout());await page.goto(base+'/#account');await login('other');await goto('orders');
  check((await refs()).join(',')==='OL3D-QA-1000','Buyer isolation');
  const scoped=await page.evaluate(async()=>api('/orders?paginated=true&buyer_id=1'));
  check(scoped.total===1&&scoped.items[0].reference==='OL3D-QA-1000','Owner filter bypass');
  await page.evaluate(()=>logout());await page.goto(base+'/#account');await login('empty');await goto('orders');
  const emptyText=await page.locator('.bo-page').innerText();
  check(emptyText.includes("You're all caught up")&&emptyText.includes('No current orders at the moment')&&await page.getByRole('link',{name:'Explore catalogue'}).count()===1,'No current orders empty state');
  await page.evaluate(()=>logout());await page.goto(base+'/#orders');
  await page.getByRole('heading',{name:'Sign in to continue'}).waitFor();
  check(await page.locator('.bo-card').count()===0,'Signed-out data exposure');
  check(failures.length===0,'JavaScript errors: '+failures.join('; '));
  return {passed:['stage board','counts and grouping','mixed-stage order','sorting','filter persistence','snapshot fields','details dialog','address change','receipt confirmation','previous orders search','loading','retry','empty board','no orders','buyer isolation','desktop/tablet/mobile','bright/dark contrast'],screenshots:'.playwright-mcp/orders-*.png'};
}
