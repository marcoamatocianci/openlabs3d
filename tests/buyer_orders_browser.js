// Playwright MCP browser_run_code_unsafe; requires scripts/orders_preview.py.
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
  const goto=async hash=>{await page.goto(base+'/#'+hash);await page.locator('.bo-results').waitFor();await page.waitForFunction(()=>!document.querySelector('.bo-page[aria-busy]'));};
  const refs=()=>page.locator('.bo-card h2').allTextContents();
  const navigate=async action=>{
    const done=page.waitForResponse(r=>r.url().includes('/api/orders?')&&r.status()===200);
    await action();await done;await page.waitForFunction(()=>!document.querySelector('.bo-page[aria-busy]'));
  };
  await goto('orders?category=all&sort=newest');
  check((await refs()).length===10,'Expected bounded first page');
  check((await refs())[0]==='OL3D-QA-1015','Newest ordering');
  check((await page.locator('.bo-results').innerText()).includes('15 orders'),'Incorrect total');
  await page.waitForFunction(()=>document.querySelector('.bo-thumb img')?.naturalWidth>0);
  const first=page.locator('.bo-card').first();
  check((await first.locator(':scope > .bo-products > li').count())===2,'Compact product preview');
  check((await first.innerText()).includes('6 items · 3 products'),'Multi-product grouping');
  check((await first.innerText()).includes('€72.00'),'Snapshot total');
  await first.locator('summary').focus();await page.keyboard.press('Enter');
  check(await first.locator('details').getAttribute('open')!==null,'Keyboard details');
  const details=await first.locator('.bo-detail-body').innerText();
  for(const value of ['Archived sample rack','PLA · Custom violet','€12.00 each','Quantity: 2','order-contact@example.org','Via Laboratory 12','Assigned printing host #4','Awaiting host acceptance','Completed']) {
    check(details.includes(value),'Missing snapshot/fulfillment detail: '+value);
  }
  check(!details.includes('Updated catalogue product')&&!details.includes('€99.00'),'Live listing leaked into snapshots');
  check(await first.locator('[aria-label="Product preview unavailable"]').count()===1,'Archived preview fallback');
  await first.locator('summary').click();
  await page.screenshot({animations:'disabled',path:'.playwright-mcp/orders-desktop-bright.png'});
  await navigate(()=>page.getByRole('link',{name:'Next',exact:true}).click());
  check((await refs()).length===5&&(await refs()).at(-1)==='OL3D-QA-1001','Pagination lost orders');
  const expected={Pending:5,'In progress':6,Completed:2,Cancelled:2};
  for(const [label,count] of Object.entries(expected)){
    await navigate(()=>page.getByRole('navigation',{name:'Order status'}).getByRole('link',{name:new RegExp('^'+label)}).click());
    check((await refs()).length===count,'Incorrect '+label+' grouping');
    const statuses=await page.locator('.bo-card-head .status').allTextContents();
    if(label==='Pending')check(statuses.every(s=>['Awaiting host acceptance','Accepted · awaiting printing'].includes(s)),'Pending mislabeled as printing');
    if(label==='In progress')check(statuses.every(s=>['Production in progress','Ready for delivery'].includes(s)),'Active grouping');
  }
  await navigate(()=>page.getByRole('navigation',{name:'Order status'}).getByRole('link',{name:/^Pending/}).click());
  await navigate(async()=>{await page.click('[data-select=bo-sort] .cf-trigger');await page.click('[data-select=bo-sort] [role=option][data-value=oldest]')});
  check((await refs())[0]==='OL3D-QA-1001','Combined sorting/filtering');
  await page.goto(base+'/#catalogue');await page.waitForLoadState('networkidle');
  await goto('orders');
  check(await page.locator('[data-select=bo-sort] input[type=hidden]').inputValue()==='oldest'&&await page.locator('[data-select=bo-sort] .cf-value').textContent()==='Oldest first','Sort not preserved');
  check((await refs()).length===5,'Category not preserved');
  await page.reload();await page.locator('.bo-results').waitFor();
  check((await refs())[0]==='OL3D-QA-1001','Reload lost preferences');
  await goto('orders?category=all&sort=newest');
  await page.evaluate(()=>document.documentElement.dataset.theme='dark');
  await page.waitForFunction(()=>document.querySelector('.bo-thumb img')?.naturalWidth>0);
  await page.screenshot({animations:'disabled',path:'.playwright-mcp/orders-desktop-dark.png'});
  // Status text must retain AA contrast in each existing theme.
  for(const theme of ['dark','light']){
    const contrast=await page.evaluate(theme=>{
      document.documentElement.dataset.theme=theme;
      const lum=values=>{const rgb=values.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]};
      return [...document.querySelectorAll('.bo-card-head .status')].map(el=>{const s=getComputedStyle(el),parse=v=>v.match(/[\d.]+/g).map(Number),fg=parse(s.color),bg=parse(s.backgroundColor),surface=parse(getComputedStyle(el.closest('.bo-card')).backgroundColor),alpha=bg[3]??1,a=lum(fg.slice(0,3)),b=lum(bg.slice(0,3).map((v,i)=>v*alpha+surface[i]*(1-alpha)));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)});
    },theme);
    check(contrast.every(r=>r>=4.5),theme+' status contrast: '+contrast);
  }
  await page.setViewportSize({width:390,height:844});
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile overflow');
  await page.locator('.bo-card summary').first().click();
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Detail overflow');
  await page.screenshot({animations:'disabled',path:'.playwright-mcp/orders-mobile-bright.png'});
  await page.evaluate(()=>document.documentElement.dataset.theme='dark');
  await page.screenshot({animations:'disabled',path:'.playwright-mcp/orders-mobile-dark.png'});
  await page.setViewportSize({width:768,height:1024});
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Tablet overflow');
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
  await navigate(()=>page.getByRole('navigation',{name:'Order status'}).getByRole('link',{name:/^In progress/}).click());
  check((await page.locator('.bo-page').innerText()).includes('No orders in progress'),'Contextual empty state');
  await page.unroute(pattern);
  // Owner scoping is verified on real API responses with separate authenticated sessions.
  await page.evaluate(()=>logout());await page.goto(base+'/#account');await login('other');await goto('orders');
  check((await refs()).join(',')==='OL3D-QA-1000','Buyer isolation');
  const scoped=await page.evaluate(async()=>api('/orders?paginated=true&buyer_id=1'));
  check(scoped.total===1&&scoped.items[0].reference==='OL3D-QA-1000','Owner filter bypass');
  await page.evaluate(()=>logout());await page.goto(base+'/#account');await login('empty');await goto('orders');
  check((await page.locator('.bo-page').innerText()).includes('No orders yet'),'First-order empty state');
  await page.evaluate(()=>logout());await page.goto(base+'/#orders');
  await page.getByRole('heading',{name:'Sign in to continue'}).waitFor();
  check(await page.locator('.bo-card').count()===0,'Signed-out data exposure');
  check(failures.length===0,'JavaScript errors: '+failures.join('; '));
  return {passed:['pagination','category counts and grouping','sorting','filter persistence','snapshot fields','multi-product grouping','keyboard details','CAD previews and fallback','loading','retry','empty categories','no orders','buyer isolation','desktop/tablet/mobile','bright/dark contrast'],screenshots:'.playwright-mcp/orders-*.png'};
}
