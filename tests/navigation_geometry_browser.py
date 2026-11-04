"""Responsive shared navigation geometry against the running site; no account data is changed."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
phase=sys.argv[1] if len(sys.argv)>1 else 'after'
out=Path('/tmp/openlabs-navigation-'+phase);out.mkdir(exist_ok=True)
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/home/mcianci/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
 for width in (320,375,390,430,768,1366):
  for theme in ('light','dark'):
   p=b.new_page(viewport={'width':width,'height':1000});p.goto('http://localhost:8080');p.wait_for_load_state('networkidle')
   p.evaluate('''theme=>{applyTheme(theme);const labels=['All requests','Submitted','Under review','Completed','Declined'];const segments=labels.map((s,i)=>`<button class="segment" aria-pressed="${i===0}">${s}<span class="segment-count">${i?128:1024}</span></button>`).join('');const opts=labels.map((label,i)=>({label,value:String(i),href:'orders',count:128}));document.querySelector('#app').innerHTML=`<div style="padding:20px;min-width:0;max-width:100%" id="geometry"><h2>Navigation controls</h2><h3>Request / admin segments</h3><nav class="segmented">${segments}</nav><h3>Buyer orders</h3><div class="bo-toolbar">${filterChips('Orders',opts,'0')}</div><h3>Host / admin filters</h3><div class="toolbar">${filterChips('Status',opts,'0')}</div><h3>Equipment</h3><nav class="eq-tabs"><a class="eq-tab" aria-current="page">Printers</a><a class="eq-tab">Materials &amp; Colors</a></nav><h3>Account appearance</h3>${themeToggle()}<h3>Catalogue selections</h3><div class="cf-chips"><button class="cf-chip">A longer material filter <span>×</span></button><button class="cf-chip">PETG <span>×</span></button></div></div>`;document.querySelector('#geometry').onclick=e=>{const t=e.target.closest('.segment,.chip,.eq-tab');if(!t)return;e.preventDefault();for(const n of t.parentElement.children){n.classList.toggle('active',n===t);if(n.classList.contains('segment'))n.setAttribute('aria-pressed',String(n===t));else if(n===t)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');}};}''',theme)
   for state in ('first','last'):
    for selector in ('.segmented','.chips','.eq-tabs'):
     for group in p.locator(selector).all():
      item=group.locator(':scope > *').first if state=='first' else group.locator(':scope > *').last
      item.click()
    if phase=='after':
     issues=p.evaluate('''()=>{const errors=[];if(document.documentElement.scrollWidth>innerWidth)errors.push('page overflow');for(const g of document.querySelectorAll('#geometry .segmented,#geometry .chips,#geometry .eq-tabs')){const r=g.getBoundingClientRect();if(r.left<0||r.right>innerWidth)errors.push('group overflow');const heights=[...g.children].map(t=>t.getBoundingClientRect().height);if(Math.max(...heights)-Math.min(...heights)>1)errors.push('unequal tab heights');for(const t of g.children){const b=t.getBoundingClientRect();if(b.top<r.top||b.bottom>r.bottom+1)errors.push('vertical spill');if(t.matches('[aria-pressed=true],.active,[aria-current]')&&(b.left<r.left-1||b.right>r.right+1))errors.push('selected tab not scrolled into view');}}return errors;}''')
     assert not issues,(width,theme,state,issues)
    p.screenshot(path=str(out/f'{width}-{theme}-{state}.png'),full_page=True)
   p.close();print('PASS',phase,width,theme,flush=True)
 b.close()
