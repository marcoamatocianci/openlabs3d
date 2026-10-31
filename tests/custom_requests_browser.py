"""End-to-end check of custom requests against the local development stack (http://127.0.0.1:8080).
Uses the development accounts from app.seed_dev_accounts and leaves its test requests in the database:
run it only against disposable development data.
    uv run --no-project --python 3.12 --with playwright --with Pillow python tests/custom_requests_browser.py OUTPUT_DIR
Set CHROME to a Chromium binary if Playwright's bundled browser is not installed."""
import io,os,struct,sys,json
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright,expect
BASE='http://127.0.0.1:8080';OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=True)
CHROME=os.environ.get('CHROME') or None
FILES=OUT/'files';FILES.mkdir(exist_ok=True)
(FILES/'holder.stl').write_bytes(b'test'.ljust(80,b'\0')+struct.pack('<I',1)+struct.pack('<12fH',0,0,1,0,0,0,10,0,0,0,10,10,0))
img=Image.new('RGB',(640,480),(69,123,157));[img.putpixel((x,y),(230,190,90)) for x in range(200,440) for y in range(150,330)];img.save(FILES/'bench-photo.jpg',quality=88)
(FILES/'drawing.pdf').write_bytes(b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n')
(FILES/'virus.exe').write_bytes(b'MZ')
ACCOUNTS={'buyer':('buyer@example.org','BuyerTest2026!'),'host':('host@example.org','HostTest2026!'),'admin':('admin@example.org','AdminTest2026!')}
errors=[];checks=[]
def ok(cond,msg):
    checks.append(('PASS' if cond else 'FAIL',msg));print(('PASS ' if cond else 'FAIL ')+msg)
def context(browser,who=None,w=1366,h=900,dark=False):
    ctx=browser.new_context(viewport={'width':w,'height':h},device_scale_factor=1,color_scheme='dark' if dark else 'light')
    if who:
        r=ctx.request.post(BASE+'/api/auth/login',data={'email':ACCOUNTS[who][0],'password':ACCOUNTS[who][1]})
        assert r.ok,r.text()
    p=ctx.new_page();p.mode='dark' if dark else 'light';p.on('pageerror',lambda e:errors.append(f'{who}: {e}'));p.on('console',lambda m:m.type=='error' and errors.append(f'{who} console: {m.text}'))
    return ctx,p
def go(p,hash_):p.goto(f'{BASE}/#{hash_}');p.wait_for_load_state('networkidle');p.evaluate(f"applyTheme('{p.mode}')")
def theme(p,mode):p.evaluate(f"applyTheme('{mode}')");p.wait_for_timeout(150)
def shot(p,name,full=True):p.screenshot(path=str(OUT/f'{name}.png'),full_page=full)

with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path=CHROME)
    # Guest: introduction only, with sign-in calls to action.
    ctx,p=context(b);go(p,'custom')
    ok(p.locator('.primary-nav a',has_text='Custom requests').count()==1,'guest topbar links Custom requests')
    ok(p.get_by_role('heading',name='Have a laboratory tool in mind?').is_visible(),'guest sees introduction')
    ok(p.locator('#cr-form').count()==0 and p.get_by_role('link',name='Sign in to submit a request').is_visible(),'guest must sign in before submitting')
    shot(p,'guest-1366-light');go(p,'my-requests');ok('Sign in' in p.inner_text('#app'),'guest My requests asks to sign in');ctx.close()

    # Buyer: validation, files, double submit, persistence.
    ctx,p=context(b,'buyer');api=ctx.request
    before=len(api.get(BASE+'/api/orders').json());own_before=len(api.get(BASE+'/api/custom-requests').json())
    go(p,'custom');p.wait_for_selector('#cr-form')
    ok(p.locator('.primary-nav a',has_text='Custom requests').count()==1,'buyer topbar links Custom requests')
    shot(p,'buyer-form-1366-light')
    p.get_by_role('button',name='Submit Request for Review').click()
    ok(p.locator('[aria-invalid=true]').count()==3,'empty submit flags title, application and dimensions')
    ok(p.evaluate('document.activeElement.name')=='title','focus moves to first invalid field')
    shot(p,'buyer-form-validation',full=False)
    p.fill('[name=title]','Cryovial rack for a −80 °C freezer box')
    p.fill('[name=application]','Hold twelve 2 mL cryovials upright inside a standard freezer box so we can label and retrieve them quickly with gloves on.')
    p.fill('[name=dimensions]','Footprint max 130 × 130 mm, height under 50 mm; hole pitch about 13 mm')
    p.fill('[name=compatibility]','Corning 2 mL external-thread cryovials; 133 mm cardboard freezer boxes')
    p.fill('[name=quantity]','0');p.get_by_role('button',name='Submit Request for Review').click()
    ok(p.locator('[name=quantity][aria-invalid=true]').count()==1,'quantity 0 rejected')
    p.fill('[name=quantity]','6');p.select_option('[name=material]','PETG')
    for label in ('Cold storage','Frequent cleaning'):p.get_by_role('button',name=label).click()
    p.fill('[name=requirements]','Wiped daily with 70% ethanol.')
    p.set_input_files('#cr-files',[str(FILES/'virus.exe')])
    ok('unsupported type' in p.inner_text('#cr-file-error'),'unsupported file rejected in the browser')
    p.set_input_files('#cr-files',[str(FILES/n) for n in ('holder.stl','bench-photo.jpg','drawing.pdf')])
    ok(p.locator('#cr-file-list li').count()==3 and p.locator('#cr-file-list img').count()==1,'three files listed with image preview')
    p.get_by_role('button',name='Remove drawing.pdf').click();ok(p.locator('#cr-file-list li').count()==2,'file removal works')
    p.set_input_files('#cr-files',[str(FILES/'drawing.pdf')])
    ok('3 files' in p.inner_text('#cr-summary'),'review summary counts files')
    shot(p,'buyer-form-filled-1366-light')
    # Draft survives a refresh (files are not kept).
    p.reload();p.wait_for_selector('#cr-form');ok(p.input_value('[name=quantity]')=='6' and p.locator('[data-condition=cold][aria-pressed=true]').count()==1,'draft restored after refresh')
    p.set_input_files('#cr-files',[str(FILES/n) for n in ('holder.stl','bench-photo.jpg','drawing.pdf')])
    button=p.locator('.cr-submit-btn');button.dblclick();p.evaluate("document.querySelector('.cr-submit-btn').click()")
    p.wait_for_url('**/#my-requests?created=*');p.wait_for_selector('.cr-card')
    mine=api.get(BASE+'/api/custom-requests').json()
    ok(len(mine)==own_before+1,'multiple clicks create exactly one request')
    created=mine[0];ok(len(created['files'])==3 and created['quantity']==6 and created['conditions']==['cold','cleaning'],'request persisted with files and conditions')
    ok(len(api.get(BASE+'/api/orders').json())==before,'submission creates no order')
    ok(p.locator('.cr-card.is-new details[open]').count()==1,'new request highlighted and expanded')
    shot(p,'buyer-list-1366-light')
    p.reload();p.wait_for_selector('.cr-card');ok(p.locator('.cr-card').count()==own_before+1,'requests persist after refresh')
    p.locator('.cr-gallery img').first.scroll_into_view_if_needed();p.wait_for_function("document.querySelector('.cr-gallery img').naturalWidth>0",timeout=15000)
    ok(True,'attached image renders for owner')
    dl=api.get(BASE+created['files'][0]['url']+'?download=true');ok(dl.ok and dl.headers['content-disposition'].startswith('attachment'),'owner downloads model')
    theme(p,'dark');shot(p,'buyer-list-1366-dark');go(p,'custom');p.wait_for_selector('#cr-form');shot(p,'buyer-form-1366-dark');theme(p,'light')
    buyer_request=created;ctx.close()

    # Mobile buyer, both themes.
    for mode in ('light','dark'):
        ctx,p=context(b,'buyer',390,844,mode=='dark');go(p,'custom');p.wait_for_selector('#cr-form');theme(p,mode)
        ok(not p.evaluate('document.documentElement.scrollWidth>innerWidth'),f'mobile form has no horizontal overflow ({mode})')
        shot(p,f'buyer-form-390-{mode}');go(p,'my-requests');p.wait_for_selector('.cr-card');theme(p,mode)
        p.locator('.cr-card summary').first.click()
        ok(not p.evaluate('document.documentElement.scrollWidth>innerWidth'),f'mobile list has no horizontal overflow ({mode})')
        shot(p,f'buyer-list-390-{mode}');ctx.close()

    # Printing host acting as a customer.
    ctx,p=context(b,'host');go(p,'custom');p.wait_for_selector('#cr-form')
    p.locator('#user-menu-button').click();ok(p.locator('#user-menu a',has_text='Custom requests').count()==1,'host account menu links Custom requests');p.keyboard.press('Escape')
    p.fill('[name=title]','Filament spool holder clip');p.fill('[name=application]','Clip that keeps the filament end from unwinding when spools are stored on a shelf.')
    p.fill('[name=dimensions]','Spool flange 200 mm diameter, 4 mm thick rim');p.fill('[name=quantity]','20')
    p.get_by_role('button',name='Submit Request for Review').click();p.wait_for_url('**/#my-requests?created=*');p.wait_for_selector('.cr-card.is-new')
    host_request=ctx.request.get(BASE+'/api/custom-requests').json()[0];ok(host_request['title']=='Filament spool holder clip','host submitted a request as a customer')
    go(p,'host');p.wait_for_selector('.ws-main h1');ok(p.inner_text('.ws-main h1')=='Overview','host workspace unaffected')
    ok(ctx.request.get(BASE+f"/api/custom-requests/{buyer_request['id']}").status==404,'host cannot read buyer request')
    ok(ctx.request.get(BASE+buyer_request['files'][1]['url']).status==404,'host cannot read buyer attachment')
    ctx.close()

    # Administrator review.
    ctx,p=context(b,'admin');go(p,'custom');p.wait_for_url('**/#admin/requests');p.wait_for_selector('#request-list')
    ok(p.locator('.ws-link',has_text='Custom requests').count()==1,'admin sidebar has Custom requests')
    ok(p.locator('#request-list .list-row').count()>=2,'admin lists requests from buyers and hosts')
    shot(p,'admin-list-1366-light')
    p.locator('.list-row',has_text=buyer_request['reference']).get_by_role('button',name='Review').click()
    dialog=p.locator('dialog[open]');ok('buyer@example.org' in dialog.inner_text() and 'Corning 2 mL' in dialog.inner_text(),'review shows requester and specifications')
    p.wait_for_timeout(400);ok(p.evaluate("[...document.querySelectorAll('dialog .cr-gallery img')].every(i=>i.complete&&i.naturalWidth>0)"),'admin sees attached image')
    dialog.get_by_role('button',name='Preview 3D').click();p.wait_for_selector('dialog [data-cad-viewer][data-loaded=true]',timeout=15000);ok(True,'admin previews STL in 3D')
    shot(p,'admin-review-1366-light',full=False)
    dialog.locator('[name=status]').select_option('under_review');dialog.locator('[name=admin_notes]').fill('Check pitch against freezer box insert.')
    dialog.get_by_role('button',name='Save review').click();p.wait_for_timeout(800)
    ok(ctx.request.get(BASE+f"/api/custom-requests/{buyer_request['id']}").json()['admin_notes']=='Check pitch against freezer box insert.','admin notes saved')
    theme(p,'dark');go(p,'admin/requests');p.wait_for_selector('#request-list');shot(p,'admin-list-1366-dark')
    p.locator('.list-row',has_text=buyer_request['reference']).get_by_role('button',name='Review').click();p.wait_for_timeout(300);shot(p,'admin-review-1366-dark',full=False);p.keyboard.press('Escape')
    ctx2,p2=context(b,'admin',390,844);go(p2,'admin/requests');p2.wait_for_selector('#request-list');shot(p2,'admin-list-390-light');ctx2.close()
    theme(p,'light');ctx.close()

    # The owner sees the status change, never the internal notes.
    ctx,p=context(b,'buyer');go(p,'my-requests');p.wait_for_selector('.cr-card')
    card=p.locator(f"#request-{buyer_request['id']}");ok('Under review' in card.inner_text() and 'Check pitch' not in p.inner_text('#app'),'buyer sees new status without internal notes')
    ctx.close();b.close()
print('\nERRORS:',errors or 'none');print(sum(c[0]=='PASS' for c in checks),'passed,',sum(c[0]=='FAIL' for c in checks),'failed')
