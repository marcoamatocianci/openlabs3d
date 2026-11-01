"""Real workspace navigation across desktop/mobile themes using catalogue_preview.py fixtures."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=os.environ.get('NAV_QA_URL','http://127.0.0.1:18109')
OUT=Path('/tmp/openlabs-unified-navigation');OUT.mkdir(exist_ok=True)
ROUTES={'admin':['admin/pending','admin/products','admin/hosts','admin/users','admin/orders'],'buyer':['orders','my-requests','account','catalogue'],'host':['host/jobs','my-printers','my-printers/materials']}
errors=[]
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path=os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'))
 for role,routes in ROUTES.items():
  ctx=b.new_context();assert ctx.request.post(BASE+'/api/auth/login',data={'email':role+'@example.org','password':'TestPassword2026'}).ok
  p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)))
  for width in (1440,1280,1024,768,430,390,375,320):
   p.set_viewport_size({'width':width,'height':1000})
   for theme in ('light','dark'):
    for route in routes:
     p.goto(BASE+'/#'+route);p.wait_for_load_state('networkidle');p.evaluate('t=>applyTheme(t)',theme);p.wait_for_timeout(300)
     assert p.locator('#app').inner_text().strip(),route
     if route=='admin/pending' and width<=900:
      p.locator('.ws-switch').click()
     issues=p.evaluate('''()=>{let errors=[];if(document.documentElement.scrollWidth>innerWidth+1)errors.push('page overflow');for(const e of document.querySelectorAll('.chip,.segment,.eq-tab')){if(!e.getClientRects().length)continue;let s=getComputedStyle(e),r=e.getBoundingClientRect();if(r.height<43||r.height>45)errors.push(e.className+' height '+r.height);if(s.borderRadius!=='999px')errors.push(e.className+' radius '+s.borderRadius);if(e.matches('.active,[aria-current],[aria-pressed=true]')&&s.backgroundColor!=='rgb(29, 53, 87)')errors.push(e.className+' active '+s.backgroundColor);}return errors;}''')
     assert not issues,(role,route,width,theme,issues)
     if route in ('admin/pending','orders','my-requests','host/jobs','my-printers','account'):
      p.screenshot(path=str(OUT/f'{role}-{route.replace("/","-")}-{width}-{theme}.png'))
     if route=='admin/pending' and width<=900:
      p.locator('.ws-switch').click()
      p.screenshot(path=str(OUT/f'admin-approvals-tabs-{width}-{theme}.png'))
     # Exercise last/first links with their real route handlers and persisted selected states.
     groups=p.locator('.chips,.segmented,.eq-tabs')
     if groups.count():
      group=groups.first
      for edge in ('last','first'):
       children=group.locator(':scope > a,:scope > button')
       if not children.count():break
       target=children.last if edge=='last' else children.first
       target.click();p.wait_for_load_state('networkidle')
       assert p.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(route,width,edge)
    print('PASS',role,width,theme,flush=True)
  ctx.close()
 b.close()
assert not errors,errors
print('All workspace navigation checks passed')
