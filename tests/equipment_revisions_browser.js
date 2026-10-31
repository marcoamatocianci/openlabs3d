// Run scripts/equipment_preview.py, then browser_run_code_unsafe with this file.
async (page) => {
 const base='http://127.0.0.1:18099';
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const browser=page.context().browser();
 const hc=await browser.newContext({viewport:{width:1280,height:900}}),ac=await browser.newContext();
 try{
  const login=async(context,email)=>{const r=await context.request.post(base+'/api/auth/login',{data:{email,password:'TestPassword2026'}});assert(r.ok(),await r.text());return (await r.json()).csrf_token};
  const csrf=await login(hc,'host@example.org');await login(ac,'admin@example.org');
  const h=await hc.newPage(),a=await ac.newPage();
  h.on('pageerror',e=>errors.push(e.message));a.on('pageerror',e=>errors.push(e.message));
  const json=async(context,path)=>(await context.request.get(base+path)).json();
  const approved=await json(hc,'/api/host/equipment');
  const listing=(await json(hc,'/api/listings')).items?.[0]?.id;
  const colors=async()=>listing?Object.keys((await json(hc,`/api/listings/${listing}/availability`)).colors||{}):[];
  const marketplace=await colors();
  const isHost=async()=>(await json(hc,'/api/auth/me')).user.role==='host';

  // Overview: read-only approved cards, wizard hidden, specifications on hover/focus.
  await h.goto(base+'/#my-printers');await h.getByRole('heading',{name:'Approved equipment',exact:true}).waitFor();
  assert(await h.locator('#equipment-form').count()===0,'Wizard hidden by default');
  assert(await h.locator('.eq-card').count()===approved.length,'Approved printer cards');
  assert(await h.locator('.eq-card').getByRole('button',{name:'Edit'}).count()===0,'Approved cards are read-only');
  assert(await h.getByText('Equipment draft').count()===0,'No empty draft section');
  await h.locator('.eq-art-btn').first().hover();await h.locator('.eq-pop').first().waitFor({state:'visible'});
  await h.mouse.move(0,0);await h.locator('.eq-art-btn').first().focus();await h.keyboard.press('Tab');await h.keyboard.press('Shift+Tab');
  await h.locator('.eq-pop').first().waitFor({state:'visible'});await h.keyboard.press('Escape');

  // Modify Equipment: edit a printer in the drawer, then configure materials and colors.
  await h.getByRole('button',{name:'Modify equipment'}).click();await h.locator('.eq-stepper').waitFor();
  assert(await isHost(),'Opening the editor preserves the host role');
  await h.locator('#next-step').click();
  await h.locator('[data-edit-printer="0"]').click();await h.locator('[data-d=quantity]').fill('2');await h.locator('[data-d-save]').click();
  assert((await h.locator('[data-card="draft-0"]').innerText()).includes('× 2'),'Printer edited');
  await h.locator('#next-step').click();
  assert(await h.locator('.eq-caps-review input,.eq-caps-review [data-add-color]').count()===0,'Step 3 is read-only');
  assert((await h.locator('.eq-caps-review').innerText()).includes('✓ PLA'),'Step 3 shows approved capabilities');
  await h.locator('[data-step="1"]').click();
  assert((await h.locator('[data-card="draft-0"]').innerText()).includes('× 2'),'Edits persist between steps');

  // Save Draft: private, no approval request, approved equipment unchanged.
  await h.getByRole('button',{name:'Save draft',exact:true}).click();await h.locator('.eq-draft').waitFor();
  assert((await json(ac,'/api/admin/equipment-revisions')).length===0,'Draft creates no admin request');
  assert(JSON.stringify(await json(hc,'/api/host/equipment'))===JSON.stringify(approved),'Approved equipment unchanged');
  assert(await h.getByRole('button',{name:'Modify equipment'}).isDisabled(),'Modify disabled while a draft exists');
  await h.getByText('An equipment draft already exists').waitFor();
  assert(JSON.stringify(await colors())===JSON.stringify(marketplace),'Marketplace availability ignores drafts');

  // Continue Editing restores the draft; Delete Draft removes only the draft.
  await h.getByRole('link',{name:'Continue editing'}).click();await h.locator('#next-step').click();
  assert((await h.locator('[data-card="draft-0"]').innerText()).includes('× 2'),'Draft restored');
  await h.locator('[data-leave]').click();await h.locator('.eq-draft').waitFor();
  await h.getByRole('button',{name:'Delete draft'}).click();await h.locator('dialog [data-confirm]').click();
  await h.waitForFunction(()=>!document.querySelector('.eq-draft')&&document.querySelector('[data-modify]')?.disabled===false);
  assert(await h.locator('.eq-draft').count()===0,'Draft card removed');
  assert(JSON.stringify(await json(hc,'/api/host/equipment'))===JSON.stringify(approved),'Delete preserves approved equipment');

  // Save, reopen, change again and submit: the latest unsaved edit is submitted.
  await h.getByRole('button',{name:'Modify equipment'}).click();await h.locator('#next-step').click();
  await h.locator('[data-edit-printer="0"]').click();await h.locator('[data-d=quantity]').fill('2');await h.locator('[data-d-save]').click();
  await h.getByRole('button',{name:'Save draft',exact:true}).click();await h.getByRole('link',{name:'Continue editing'}).click();
  await h.locator('#next-step').click();await h.locator('[data-edit-printer="0"]').click();await h.locator('[data-d=quantity]').fill('3');await h.locator('[data-d-save]').click();
  for(let i=0;i<3;i++)await h.locator('#next-step').click();
  const submitted=h.waitForResponse(r=>r.url().endsWith('/host/equipment-application')&&r.request().method()==='PUT');
  await h.getByRole('button',{name:'Submit for approval',exact:true}).click();assert((await submitted).ok(),'Submitted');
  await h.locator('.eq-draft.is-pending').waitFor();
  assert(await h.getByRole('button',{name:'Modify equipment'}).isDisabled(),'Modify disabled while pending');
  assert(await isHost(),'Submission preserves host');
  assert(JSON.stringify(await json(hc,'/api/host/equipment'))===JSON.stringify(approved),'Approved equipment unchanged while pending');

  // Administrator rejects, host resubmits, administrator approves.
  await a.goto(base+'/#admin/pending?type=equipment');await a.locator('.approval-card').first().waitFor();
  assert((await a.locator('.approval-card').first().innerText()).includes('Waiting'),'Approval card shows how long it has waited');
  await a.locator('.approval-details > summary').first().click();await a.getByRole('heading',{name:'Before / Currently approved'}).waitFor();
  assert(await a.getByRole('heading',{name:'After / Proposed equipment'}).count()===1,'Before/After visible');
  a.on('dialog',d=>d.accept(d.type()==='prompt'?'Verify printer calibration':undefined));
  const rejected=a.waitForResponse(r=>r.url().includes('/equipment-revisions/')&&r.url().endsWith('/reject'));
  await a.getByRole('button',{name:'Reject equipment update'}).click();assert((await rejected).ok(),'Rejected');
  await h.reload();await h.getByText(/Verify printer calibration/).waitFor();
  assert(JSON.stringify(await json(hc,'/api/host/equipment'))===JSON.stringify(approved),'Rejection preserves approved equipment');
  await h.getByRole('link',{name:'Revise and resubmit'}).click();
  for(let i=0;i<4;i++)await h.locator('#next-step').click();
  const resubmitted=h.waitForResponse(r=>r.url().endsWith('/host/equipment-application')&&r.request().method()==='PUT');
  await h.getByRole('button',{name:'Submit for approval',exact:true}).click();assert((await resubmitted).ok(),'Resubmitted');
  await a.reload();await a.getByRole('button',{name:'Approve equipment update'}).waitFor();
  assert(await a.locator('.approvals-tabs .segment[aria-pressed=true]').innerText().then(t=>t.startsWith('Equipment updates')),'Equipment tab selected');
  const accepted=a.waitForResponse(r=>r.url().includes('/equipment-revisions/')&&r.url().endsWith('/approve'));
  await a.getByRole('button',{name:'Approve equipment update'}).click();assert((await accepted).ok(),'Approved');
  assert((await json(hc,'/api/host/equipment'))[0].quantity===3,'Approved revision activated');

  // Materials & Colors: one inventory for all printers, live without approval, offered where a printer is approved.
  await h.goto(base+'/#my-printers/materials');await h.locator('#eq-stock .eq-acc').waitFor();
  assert(await h.locator('#eq-stock [data-toggle-material="PLA+"]').isDisabled(),'A material no printer supports cannot be selected');
  await h.locator('[data-open-material="PLA"]').click();
  await h.locator('[data-toggle-color="orange"][data-material="PLA"]').click();   // a single click adds it
  await h.waitForFunction(()=>!document.querySelector('#eq-stock [aria-busy=true]'));
  assert(await h.locator('[data-toggle-color="orange"][data-material="PLA"]').getAttribute('aria-pressed')==='true','One click selects a color');
  assert((await colors()).includes('orange'),'Added color is live for buyers');
  assert((await json(ac,'/api/admin/equipment-revisions')).length===0,'Stock needs no approval');
  await h.locator('[data-custom-color="PLA"] [name=name]').fill('Lab Teal');await h.locator('[data-custom-color="PLA"] [name=hex]').fill('#127a8a');
  await h.locator('[data-custom-color="PLA"] button').click();
  await h.waitForFunction(()=>!document.querySelector('#eq-stock [aria-busy=true]'));
  await h.reload();await h.locator('[data-open-material="PLA"]').click();
  assert(await h.locator('[data-toggle-color="orange"][data-material="PLA"]').getAttribute('aria-pressed')==='true'&&(await h.locator('#eq-stock').innerText()).includes('Lab teal'),'Stock persists after refresh');
  await h.locator('[data-toggle-color="orange"][data-material="PLA"]').click();await h.waitForFunction(()=>!document.querySelector('#eq-stock [aria-busy=true]'));
  assert(!(await colors()).includes('orange'),'Removed color leaves the marketplace');
  await h.locator('.eq-tab',{hasText:'Printers'}).click();await h.locator('[data-card="approved-0"]').waitFor();
  assert((await h.locator('[data-card="approved-0"] .eq-card-materials').innerText()).includes('PLA'),'Printer card reflects stock');

  await hc.request.post(base+'/api/auth/logout',{headers:{'X-CSRF-Token':csrf}});
  await login(hc,'host@example.org');
  await h.goto(base+'/#my-printers');await h.getByRole('heading',{name:'Approved equipment',exact:true}).waitFor();
  assert(await isHost(),'Host permission survives login');
  await h.setViewportSize({width:390,height:844});assert(!await h.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'No mobile overflow');
  assert(!errors.length,errors.join('\n'));
  return {passed:true,checks:['read-only approved cards','spec popover hover/focus','hidden wizard','printer drawer','read-only step 3','step persistence','private draft','draft card','modify lock','continue editing','delete draft','submit latest edits','pending lock','before/after','rejection','resubmission','approval','marketplace availability','stock tab','capability bounds','stock persistence','logout/login','mobile','no browser errors']};
 }finally{await hc.close();await ac.close()}
}
