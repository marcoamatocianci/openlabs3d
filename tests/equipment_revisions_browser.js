// Run scripts/equipment_preview.py, then browser_run_code_unsafe with this file.
async (page) => {
 const base='http://127.0.0.1:18099';
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const browser=page.context().browser();
 const hc=await browser.newContext(),ac=await browser.newContext();
 try{
  const login=async(context,email)=>{const r=await context.request.post(base+'/api/auth/login',{data:{email,password:'TestPassword2026'}});assert(r.ok(),await r.text());return (await r.json()).csrf_token};
  const csrf=await login(hc,'host@example.org');await login(ac,'admin@example.org');
  const h=await hc.newPage(),a=await ac.newPage();
  h.on('pageerror',e=>errors.push(e.message));a.on('pageerror',e=>errors.push(e.message));
  const approved=await (await hc.request.get(base+'/api/host/equipment')).json();
  await h.goto(base+'/#my-printers/edit');await h.getByRole('heading',{name:'Approved Equipment',exact:true}).waitFor();
  assert((await (await hc.request.get(base+'/api/auth/me')).json()).user.role==='host','Opening editor preserves host');
  await h.locator('#next-step').click();
  await h.locator('[data-field=model]').fill('Revised printer');
  const save=h.waitForResponse(r=>r.url().endsWith('/host/equipment-application')&&r.request().method()==='PUT');
  await h.getByRole('button',{name:'Save Draft',exact:true}).click();assert((await save).ok(),'Draft saved');
  assert((await (await ac.request.get(base+'/api/admin/equipment-revisions')).json()).length===0,'Draft creates no admin request');
  assert(JSON.stringify(await(await hc.request.get(base+'/api/host/equipment')).json())===JSON.stringify(approved),'Approved equipment unchanged');
  await h.reload();await h.locator('#next-step').click();assert(await h.locator('[data-field=model]').inputValue()==='Revised printer','Draft survives reload');
  await h.locator('[data-field=model]').fill('Latest unsaved printer');
  for(let i=0;i<3;i++)await h.locator('#next-step').click();
  const submitted=h.waitForResponse(r=>r.url().endsWith('/host/equipment-application')&&r.request().method()==='PUT');
  await h.getByRole('button',{name:'Submit for Approval',exact:true}).click();assert((await submitted).ok(),'Submitted');
  await h.waitForFunction(()=>document.querySelector('[value=submit]')?.disabled);
  assert((await(await hc.request.get(base+'/api/auth/me')).json()).user.role==='host','Submission preserves host');
  await a.goto(base+'/#admin/pending');await a.getByRole('heading',{name:'Before / Currently approved'}).waitFor();
  assert(await a.getByRole('heading',{name:'After / Proposed equipment'}).count()===1,'Before/After visible');
  a.on('dialog',d=>d.accept(d.type()==='prompt'?'Verify printer calibration':undefined));
  const rejected=a.waitForResponse(r=>r.url().includes('/equipment-revisions/')&&r.url().endsWith('/reject'));
  await a.getByRole('button',{name:'Reject equipment update'}).click();assert((await rejected).ok(),'Rejected');
  await h.reload();await h.getByText(/Verify printer calibration/).waitFor();
  assert(JSON.stringify(await(await hc.request.get(base+'/api/host/equipment')).json())===JSON.stringify(approved),'Rejection preserves approved equipment');
  for(let i=0;i<4;i++)await h.locator('#next-step').click();
  const resubmitted=h.waitForResponse(r=>r.url().endsWith('/host/equipment-application')&&r.request().method()==='PUT');
  await h.getByRole('button',{name:'Submit for Approval',exact:true}).click();assert((await resubmitted).ok(),'Resubmitted');
  await a.reload();await a.getByRole('button',{name:'Approve equipment update'}).waitFor();
  const accepted=a.waitForResponse(r=>r.url().includes('/equipment-revisions/')&&r.url().endsWith('/approve'));
  await a.getByRole('button',{name:'Approve equipment update'}).click();assert((await accepted).ok(),'Approved');
  assert((await(await hc.request.get(base+'/api/host/equipment')).json())[0].model==='Latest unsaved printer','Approved revision activated');
  await hc.request.post(base+'/api/auth/logout',{headers:{'X-CSRF-Token':csrf}});
  await login(hc,'host@example.org');
  await h.goto(base+'/#my-printers/edit');await h.getByRole('heading',{name:'Approved Equipment',exact:true}).waitFor();
  assert((await(await hc.request.get(base+'/api/auth/me')).json()).user.role==='host','Host permission survives login');
  await h.setViewportSize({width:390,height:844});assert(!await h.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'No mobile overflow');
  assert(!errors.length,errors.join('\n'));
  return {passed:true,checks:['approved view','private draft','reload persistence','pending lock','before/after','rejection','resubmission','approval','logout/login','mobile','no browser errors']};
 }finally{await hc.close();await ac.close()}
}
