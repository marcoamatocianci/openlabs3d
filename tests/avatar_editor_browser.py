"""Profile-picture end-to-end checks against scripts/catalogue_preview.py (a fresh fixture).
uv run --offline --no-project --python 3.12 --with playwright --with Pillow python tests/avatar_editor_browser.py OUTPUT_DIR [BASE_URL]
"""
import os
import sys
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect

OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
BASE=sys.argv[2] if len(sys.argv)>2 else 'http://127.0.0.1:18101'
CHROME=os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
PHOTO=OUT/'portrait.png';Image.new('RGB',(320,240),(214,120,70)).save(PHOTO)
errors=[];checks=[]
def ok(condition,message):
    checks.append(bool(condition));print(('PASS ' if condition else 'FAIL ')+message,flush=True)
    assert condition,message

def session(browser,who,width=1366,height=900):
    ctx=browser.new_context(viewport={'width':width,'height':height})
    assert ctx.request.post(BASE+'/api/auth/login',data={'email':who+'@example.org','password':'TestPassword2026'}).ok
    p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)))
    return ctx,p

def account_page(p,theme='light'):
    p.goto(BASE+'/#account');p.wait_for_selector('#avatar-pick');p.evaluate(f"applyTheme('{theme}')")

def open_editor(p):
    p.click('#avatar-pick');expect(p.locator('#avatar-editor')).to_be_visible()

def choose(p,name):
    radio=p.get_by_role('radio',name=name,exact=True);radio.locator('..').click();expect(radio).to_be_checked()
def save(p):
    p.click('[data-ae-save]');expect(p.locator('#avatar-editor')).not_to_be_visible()

def picture(ctx): return ctx.request.get(BASE+'/api/auth/me').json()['user']['profile_picture']
def topbar(p): return p.locator('#topbar .user-trigger .avatar').inner_html()
def preview(p): return p.locator('#ae-preview').inner_html()
def stage(p):
    p.set_input_files('#ae-file',str(PHOTO));expect(p.locator('#ae-preview img')).to_have_attribute('src',__import__('re').compile('blob:'))
def swatch(p,key,value):
    radio=p.locator(f'input[name=ae-{key}][value="{value}"]');radio.locator('..').click();expect(radio).to_be_checked()

with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=CHROME)
    ctx,p=session(browser,'buyer');account_page(p)
    ok(p.locator('#account-profile input[name=display_name]').count()==0,'the profile has a single public name: the username')
    p.locator('#account-profile input[name=username]').fill('Ada_Lovelace')
    p.locator('#account-profile').get_by_role('button',name='Save profile').click()
    expect(p.locator('#avatar-pick .avatar')).to_have_text('AL')
    ok(topbar(p)=='AL','updated username initials refresh in settings and topbar')
    p.locator('#account-profile input[name=username]').fill('buyer')
    p.locator('#account-profile').get_by_role('button',name='Save profile').click()
    expect(p.locator('#avatar-pick .avatar')).to_have_text('BU')
    before=topbar(p)
    ok(picture(ctx)=={'kind':'initials'} and '<svg' not in before and '<img' not in before and before=='BU','new users show username initials')
    ok(p.evaluate("initials({username:'Ada_Lovelace',display_name:'Zed Old',first_name:'Other',last_name:'Name'})")=='AL','initials use the username, not the legacy display name or other fields')
    ok(p.evaluate("initials({username:'marie_curie'})")=='MC','username fallback uses first letters')
    open_editor(p)
    ok(p.get_by_role('heading',name='Change profile picture').is_visible(),'clear dialog title')
    ok(p.evaluate("document.querySelector('#avatar-editor').matches(':modal') && document.querySelector('#avatar-editor').contains(document.activeElement)"),'native modal contains focus')
    ok(p.evaluate("getComputedStyle(document.documentElement).overflow")=='hidden','background scrolling locked')
    ok(p.locator('#ae-preview').inner_text()=='BU' and p.locator('#ae-custom').is_hidden(),'initials preview until a method is chosen')
    ok(p.locator('[data-ae-save]').is_disabled(),'no implicit avatar assignment')
    choose(p,'Create Avatar')
    ok(p.locator('input[name=ae-type]').count()==6,'six motifs only')
    ok(p.locator('input[name=ae-fg]').count()==6 and p.locator('input[name=ae-bg]').count()==6 and p.locator('#avatar-editor input[type=color]').count()==0,'six colors per palette with no unrestricted picker')
    artwork=set()
    for name in ('Flask','Test tube','Micropipette','DNA','Molecule','Petri dish'):
        choose(p,name);artwork.add(preview(p))
        ok(p.locator('#ae-variation-group').is_visible()==(name=='Molecule'),name+': variation selector only for molecule')
        if name=='Molecule':
            ok(p.locator('input[name=ae-variant]').count()==3,'three molecule variations')
            variants=set()
            for v in ('Triad','Ring','Chain'):choose(p,v);variants.add(preview(p))
            ok(len(variants)==3,'three distinct molecule drawings')
    ok(len(artwork)==6,'all six motifs render distinct SVGs')
    choose(p,'DNA');ok(p.evaluate('ae.style.variant')=='helix','DNA uses only basic helix')
    for key in ('fg','bg'):
        values=p.locator(f'input[name=ae-{key}]').evaluate_all('(els)=>els.map(e=>e.value)')
        for value in values:
            swatch(p,key,value)
            ok(p.evaluate('ae.style.foreground' if key=='fg' else 'ae.style.background')==value,f'{key} {value}: selected colour retained')
    ok(topbar(p)==before and picture(ctx)=={'kind':'initials'},'live previews do not change the account')
    p.screenshot(path=str(OUT/'editor-desktop-light.png'))
    p.click('[data-ae-cancel]');ok(topbar(p)==before and picture(ctx)=={'kind':'initials'},'Cancel discards avatar changes')
    ok(p.evaluate('document.activeElement.id')=='avatar-pick','focus restored after Cancel')
    open_editor(p);choose(p,'Upload Photo');stage(p)
    ok(picture(ctx)=={'kind':'initials'},'photo previews locally without upload')
    p.click('[data-ae-cancel]');ok(picture(ctx)=={'kind':'initials'},'Cancel discards selected photo')
    open_editor(p);choose(p,'Upload Photo');stage(p);save(p)
    first_photo=picture(ctx)
    ok(first_photo['kind']=='photo' and '<img' in topbar(p) and '<svg' not in topbar(p),'photo replaces initials immediately, with no second avatar')
    ok(p.locator('#avatar-pick img').count()==1,'settings photo updates immediately')
    p.reload();p.wait_for_selector('#avatar-pick');ok(picture(ctx)==first_photo and '<img' in topbar(p),'photo persists after refresh')
    admin,ap=session(browser,'admin');ap.goto(BASE+'/#admin/users');ap.wait_for_selector('.list-row')
    row=ap.locator('.list-row',has_text='buyer@example.org')
    expect(row.locator('.avatar img')).to_be_visible()
    ok(row.locator('.avatar img').evaluate('(i)=>i.complete && i.naturalWidth>0'),'admin sees the same uploaded photo')
    open_editor(p);choose(p,'Create Avatar');choose(p,'Molecule');choose(p,'Ring');swatch(p,'fg','#d99a45');swatch(p,'bg','#1d3557');save(p)
    avatar=picture(ctx)
    ok(avatar=={'kind':'avatar','style':{'type':'molecule','variant':'ring','foreground':'#d99a45','background':'#1d3557'}},'avatar replaces photo in one active selection')
    ok('<svg' in topbar(p) and '<img' not in topbar(p) and p.locator('#avatar-pick .avatar svg').count()==1,'shared components update immediately')
    ok(ctx.request.get(BASE+'/api/profile/avatar').status==404,'inactive photo is not served')
    ap.reload();ap.wait_for_selector('.list-row');ok(row.locator('.avatar').inner_html()==p.locator('#avatar-pick .avatar').inner_html(),'admin sees the identical saved avatar')
    # Staging an unused photo must not upload it when an avatar is saved.
    uploads=[]
    p.on('request',lambda req: uploads.append(req.url) if req.method=='POST' and '/api/profile/avatar' in req.url else None)
    open_editor(p);choose(p,'Upload Photo');stage(p);choose(p,'Create Avatar');choose(p,'DNA');save(p)
    ok(not uploads and picture(ctx)['style']['type']=='dna','switching away from a staged photo saves only the chosen avatar')
    saved=picture(ctx);html=topbar(p)
    open_editor(p);choose(p,'Flask');p.keyboard.press('Escape')
    ok(p.locator('#avatar-editor').is_hidden() and picture(ctx)==saved and topbar(p)==html,'Escape discards changes')
    open_editor(p);choose(p,'Upload Photo');stage(p)
    p.route('**/api/profile/avatar',lambda route:route.fulfill(status=500,content_type='application/json',body='{"detail":"Please try again"}'))
    p.click('[data-ae-save]');expect(p.locator('#ae-status')).to_have_text('Please try again')
    ok(picture(ctx)==saved and topbar(p)==html,'failed upload preserves active picture and keeps draft open')
    p.unroute('**/api/profile/avatar');save(p)
    ok(picture(ctx)['kind']=='photo','upload replaces avatar after retry')
    open_editor(p);choose(p,'Create Avatar');choose(p,'Molecule');choose(p,'Chain');save(p)
    saved=picture(ctx);p.reload();p.wait_for_selector('#avatar-pick');ok(picture(ctx)==saved,'avatar persists after refreshing')
    relog,rp=session(browser,'buyer');account_page(rp)
    ok(picture(relog)==saved and topbar(rp)==topbar(p),'picture persists after a fresh login')
    p.goto(BASE+'/#orders');p.wait_for_selector('#topbar .user-trigger .avatar svg')
    ok(topbar(p)==topbar(rp),'buyer workspace uses the same picture')
    host,hp=session(browser,'host');account_page(hp);open_editor(hp);choose(hp,'Create Avatar');choose(hp,'Micropipette');save(hp)
    host_picture=topbar(hp);hp.goto(BASE+'/#host');hp.wait_for_selector('#topbar .user-trigger .avatar svg')
    ok(topbar(hp)==host_picture,'printing host workspace uses the same picture')
    # Keyboard, desktop/mobile, both explicit application themes.
    for width,height,theme in ((1366,900,'light'),(1366,900,'dark'),(390,844,'light'),(390,844,'dark'),(320,640,'light'),(844,390,'dark')):
        c,q=session(browser,'buyer',width,height);account_page(q,theme);open_editor(q)
        choose(q,'Molecule')
        for _ in range(28):
            q.keyboard.press('Tab');assert q.evaluate("document.querySelector('#avatar-editor').contains(document.activeElement)")
        box=q.locator('#avatar-editor').bounding_box()
        ok(q.evaluate('document.documentElement.scrollWidth<=innerWidth') and box['x']>=0 and box['x']+box['width']<=width+.5,f'{width} {theme}: no horizontal overflow')
        ok(box['y']>=0 and box['y']+box['height']<=height+.5 and q.locator('[data-ae-save]').is_visible(),f'{width} {theme}: dialog and save fit viewport')
        q.locator('input[name=ae-bg]').last.locator('..').scroll_into_view_if_needed()
        ok(q.locator('input[name=ae-bg]').last.locator('..').is_visible(),f'{width} {theme}: controls reachable by scrolling')
        q.locator('.ae-body').evaluate('e=>e.scrollTop=0')
        q.screenshot(path=str(OUT/f'editor-{width}-{theme}.png'))
        # Save on each layout; no page reload required.
        save(q);ok(q.locator('#avatar-pick .avatar svg').count()==1,f'{width} {theme}: save updates settings')
        c.close()
    browser.close()
print('PAGE ERRORS',errors)
ok(not errors,'no browser JavaScript errors')
print(f'{len(checks)} checks passed')
