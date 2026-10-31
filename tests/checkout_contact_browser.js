// Run with Playwright MCP against scripts/equipment_preview.py (isolated data only).
async (page) => {
  const base = 'http://127.0.0.1:18099';
  const check = (ok, message) => { if (!ok) throw Error(message); };
  await page.context().clearCookies();
  await page.goto(base);
  await page.evaluate(()=>sessionStorage.clear());
  await page.goto(base + '/#account');
  await page.waitForLoadState('networkidle');
  await page.locator('#real-login [name=email]').fill('buyer@example.org');
  await page.locator('#real-login [name=password]').fill('TestPassword2026');
  await page.locator('#real-login button').click();
  await page.waitForFunction(() => typeof account !== 'undefined' && account?.email === 'buyer@example.org');
  const setup = await page.evaluate(async () => {
    await accountAction('/profile',{username:'buyer',first_name:'Test',last_name:'User',phone:'+39 011 1234567',country:'IT',city:'Torino'},'PATCH');
    for(const address of await api('/addresses'))await api('/addresses/'+address.id,{method:'DELETE'});
    const user = (await api('/auth/me')).user;
    const address = await accountAction('/addresses/0', {first_name:'Delivery',last_name:'Recipient',phone:'+39 011 9999999',country:'IT',city:'Torino',street:'Via QA 1',label:'QA laboratory'}, 'PUT');
    const listings = await api('/listings');
    const product = listings.items.find(p => p.title === 'Availability QA Rack');
    return {user, address, line:{listing_id:product.id,material:'PLA',color:'black',quantity:1}};
  });
  const keys = ['first_name','last_name','email','phone'];
  const values = () => page.locator('#checkout-form').evaluate(f => Object.fromEntries(['first_name','last_name','email','phone'].map(k => [k,f.elements[k].value])));
  const open = async (direct=false) => {
    await page.evaluate(async ({line,direct}) => {
      sessionStorage.removeItem('checkout-contact-'+account.id);
      // As the Buy Now button does: remember the line and the unit price the product page showed.
      if(direct) sessionStorage.setItem('ol3d-direct',JSON.stringify({line,unit_price_cents:(await obtainQuote(line.listing_id,{material:line.material,color:line.color,quantity:line.quantity})).unit_price_cents,owner:account.id,key:uid()}));
      else await accountAction('/cart',line,'PUT');
      location.hash = direct ? 'checkout' : 'checkout-cart';
    }, {line:setup.line,direct});
    await page.locator('#checkout-form').waitFor();
  };
  const submit = async expected => {
    const response = page.waitForResponse(r => r.url().endsWith('/api/checkout') && r.request().method()==='POST');
    await page.getByRole('button',{name:'Submit order request',exact:true}).click();
    const r = await response;
    check(r.status()===201, 'Checkout failed: '+await r.text());
    const order = await r.json();
    const snapshot = JSON.parse(order.contact);
    for(const k of keys)check(snapshot[k]===expected[k], 'Incorrect saved '+k);
    await page.waitForURL('**/#orders');
    const persisted = await page.evaluate(async id => (await api('/orders')).find(o=>o.id===id),order.id);
    check(persisted.contact===order.contact,'Order snapshot not persisted');
    return order;
  };
  await open();
  check(await page.locator('#checkout-contact-source').inputValue()==='account','Account contact not preselected');
  const initial=await values();
  for(const k of keys)check(initial[k]===setup.user[k],'Autofill failed: '+k);
  await submit(initial);
  await open();
  const alternative={first_name:'Alternative',last_name:'Buyer',email:'alternative@example.org',phone:'+39 011 7654321'};
  for(const k of keys)await page.locator('#checkout-form [name='+k+']').fill(alternative[k]);
  check(await page.locator('#checkout-contact-source').inputValue()==='custom','Manual changes not indicated');
  await page.reload();
  await page.locator('#checkout-form').waitFor();
  check(JSON.stringify(await values())===JSON.stringify(alternative),'Manual draft lost on reload');
  await page.locator('#checkout-contact-source').selectOption('account');
  check((await values()).email===setup.user.email,'Selecting saved contact did not autofill');
  await page.locator('#checkout-contact-source').selectOption('custom');
  for(const k of keys)check((await values())[k]==='','Alternative fields not empty');
  for(const k of keys)await page.locator('#checkout-form [name='+k+']').fill(alternative[k]);
  await submit(alternative);
  const unchanged=await page.evaluate(async()=>({user:(await api('/auth/me')).user,addresses:await api('/addresses')}));
  for(const k of keys)check(unchanged.user[k]===setup.user[k],'Account modified: '+k);
  check(unchanged.addresses.length===1&&unchanged.addresses[0].first_name==='Delivery','Saved address changed');
  // Missing profile fields, Buy Now, new delivery address, and mobile layout.
  await page.evaluate(async()=>accountAction('/profile',{username:account.username,first_name:'',last_name:'',phone:''},'PATCH'));
  await open(true);
  check((await values()).email===setup.user.email && (await values()).first_name==='','Incomplete account not handled');
  await page.getByRole('button',{name:'Submit order request',exact:true}).click();
  check(await page.locator('#checkout-form').evaluate(f=>!f.checkValidity()),'Missing required fields accepted');
  await page.setViewportSize({width:390,height:844});
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile horizontal overflow');
  for(const k of keys)await page.locator('#checkout-form [name='+k+']').fill(alternative[k]);
  await page.getByText('Use a new address',{exact:true}).click();
  await page.locator('#new-address [name=street]').fill('Via QA 2');
  await page.locator('#new-address [name=city]').fill('Torino');
  await page.locator('#new-address [name=country]').selectOption('IT');
  await page.locator('[name=save_address]').check();
  await submit(alternative);
  await page.waitForFunction(async()=> (await api('/addresses')).length===2);
  await page.setViewportSize({width:1280,height:900});
  return {passed:['account autofill','saved contact selection','manual overrides','draft reload','order persistence','unchanged account and saved address','incomplete contact validation','mobile layout','Buy Now','new address saving']};
}
