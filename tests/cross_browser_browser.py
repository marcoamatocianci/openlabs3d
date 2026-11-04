"""The same behaviour in Chromium, Firefox and WebKit: mosaics, overview, popup, rounded navigation, sticky panels,
forms and browser history, at 320 to 1440 px in Bright and Dark. Job counts are rewritten in the browser. Read-only.
    uv run --no-project --python 3.12 --with playwright python tests/cross_browser_browser.py ENGINE OUTPUT_DIR [BASE_URL]
ENGINE: chromium | firefox | webkit. CHROME and WEBKIT_EXEC may point at specific binaries. (Playwright's WebKit is
the Safari engine on Linux, not Safari itself.)"""
import copy, os, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ENGINE = sys.argv[1]; OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[3] if len(sys.argv) > 3 else 'http://127.0.0.1:18102'
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + f'[{ENGINE}] ' + msg, flush=True)
COUNTS = [3, 8, 1, 0]
def session(browser, who='host', w=1440, h=900, theme='light', rewrite=True):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme)
    assert ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}).ok
    if rewrite:
        def handler(route):
            response = route.fetch(); data = response.json(); groups = data['scopes']['active']['groups']; items, n = [], 900000
            templates = {g['key']: next((j for j in data['items'] if j['status'] in g['statuses']), data['items'][0]) for g in groups}
            for g, c in zip(groups, COUNTS):
                g['count'] = c
                for k in range(c):
                    item = copy.deepcopy(templates[g['key']]); item['id'] = n; n += 1; item['status'] = g['statuses'][0]; items.append(item)
            data['items'] = items; data['total'] = data['per_page'] = len(items); data['scopes']['active']['total'] = len(items)
            route.fulfill(response=response, json=data)
        ctx.route(re.compile(r'/api/host/jobs\?scope=active$'), handler)
    p = ctx.new_page()
    p.on('pageerror', lambda e: errors.append(f'{w} {theme}: {e}'))
    p.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(f'{w} {theme}: {m.text}'))
    return ctx, p
def settled(p, ms=350): p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)
def theme_on(p, theme): p.evaluate(f"applyTheme('{theme}')"); p.wait_for_timeout(80)
GEOM = """() => { const b = document.querySelector('#host-jobs-board'), r = e => e.getBoundingClientRect(), tiles = [...b.querySelectorAll('.sb-mosaic > .sb-col')].filter(c => c.checkVisibility());
  const box = tiles.map(t => { const x = r(t), title = t.querySelector('.sb-title'), tr = r(title); return {stage:t.dataset.stage, count:+t.dataset.count, x:x.left, y:x.top, right:x.right, bottom:x.bottom, w:x.width, h:x.height, fits:title.scrollWidth <= title.clientWidth + 1 && tr.right <= x.right + 1 && tr.bottom <= x.bottom + 1}; });
  const open = b.querySelector('.sb-col.is-open'), m = b.querySelector('.sb-mosaic');
  return {box, overflow:document.documentElement.scrollWidth - innerWidth, board:b.clientWidth, openCount:b.querySelectorAll('.sb-col.is-open').length, openShare:open && open.checkVisibility() ? r(open).width / r(b).width : 0, openCards:open ? [...open.querySelectorAll('[data-job-card]')].filter(c => c.checkVisibility()).length : 0, mosaic:m.checkVisibility(), columns:getComputedStyle(m).gridTemplateColumns.split(' ').length, pills:[...b.querySelectorAll('.sb-pills .chip')].filter(c => c.checkVisibility()).length, overflowCards:open ? [...open.querySelectorAll('[data-job-card]')].filter(c => c.checkVisibility() && r(c).right > r(open).right + 1).length : 0}; }"""
def no_overlap(box):
    return not [1 for i, a in enumerate(box) for b in box[i + 1:] if min(a['right'], b['right']) - max(a['x'], b['x']) > 1 and min(a['bottom'], b['bottom']) - max(a['y'], b['y']) > 1]

with sync_playwright() as pw:
    launch = {}
    if ENGINE == 'chromium': launch['executable_path'] = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
    if ENGINE == 'webkit' and os.environ.get('WEBKIT_EXEC'): launch['executable_path'] = os.environ['WEBKIT_EXEC']
    browser = getattr(pw, ENGINE).launch(**launch)
    print('version', browser.version, flush=True)
    for w in (320, 390, 768, 1024, 1440):
        for theme in ('light', 'dark'):
            label = f'{w} {theme}'
            ctx, p = session(browser, w=w, theme=theme); p.goto(BASE + '/#host/jobs?group=in-production'); p.wait_for_selector('#host-jobs-board'); settled(p); theme_on(p, theme)
            # Focus.
            s = p.evaluate(GEOM)
            ok(s['overflow'] <= 0 and s['overflowCards'] == 0, f'{label}: no horizontal overflow, cards inside their stage')
            ok(s['openCount'] == 1 and s['openCards'] == COUNTS[1], f'{label}: one open stage, with its {COUNTS[1]} cards')
            if s['board'] >= 680:
                ok(s['mosaic'] and s['pills'] == 0 and no_overlap(s['box']) and all(t['fits'] for t in s['box']) and .62 <= s['openShare'] <= .75, f'{label}: open stage ({s["openShare"]:.0%}) beside the mosaic; no overlap; names fit')
            else:
                ok(not s['mosaic'] and s['pills'] == 4, f'{label}: stage pills instead of the mosaic')
            # Sticky.
            if s['board'] >= 680:
                p.mouse.move(2, 2); p.evaluate('window.scrollTo(0, 500)'); p.wait_for_timeout(120)
                top = p.evaluate("(() => { const m = document.querySelector('.sb-mosaic').getBoundingClientRect(); return [m.top, m.bottom, scrollY]; })()")
                ok(top[2] > 100 and 0 <= top[0] <= 120, f'{label}: the mosaic stays in view while the page scrolls (top {top[0]:.0f} at scroll {top[2]:.0f})')
                p.evaluate('window.scrollTo(0, 0)')
            p.screenshot(path=str(OUT / f'{ENGINE}-focus-{w}-{theme}.png'))
            # Overview.
            control = '.sb-col.is-open .sb-head' if s['board'] >= 680 else '.sb-pills [data-sb-open="in-production"]'
            p.locator(control).click(); p.mouse.move(2, 2); p.wait_for_timeout(450)
            s = p.evaluate(GEOM); areas = {t['stage']: t['w'] * t['h'] for t in s['box']}
            ok(s['openCount'] == 0 and len(s['box']) == 4 and no_overlap(s['box']) and all(t['fits'] and t['h'] >= 44 for t in s['box']) and s['overflow'] <= 0 and s['pills'] == 0, f'{label}: overview: four tiles, no overlap, names fit, no overflow')
            ok(areas['in-production'] > areas['available'] > areas['shipped'], f'{label}: overview: sizes follow the counts')
            ok(p.evaluate("getComputedStyle(document.querySelector('.sb-mosaic > .sb-col')).backgroundColor") not in ('', 'rgba(0, 0, 0, 0)', 'transparent'), f'{label}: overview: the tint renders')
            p.screenshot(path=str(OUT / f'{ENGINE}-overview-{w}-{theme}.png'))
            p.locator('.sb-mosaic [data-sb-open="in-production"]').click(); p.wait_for_timeout(450)
            ok(p.locator('#host-jobs-board').get_attribute('data-open') == 'in-production', f'{label}: a tile opens its stage')
            # Popup.
            p.locator('.sb-col.is-open [data-sb-expand]').click(); p.wait_for_selector('#section-dialog[open]'); p.wait_for_timeout(280)
            d = p.evaluate("""(() => { const e = document.querySelector('#section-dialog'), r = e.getBoundingClientRect(), b = e.querySelector('.ss-body'), l = e.querySelector('.ss-list');
              return {fits:r.left >= -1 && r.top >= -1 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1, cards:l.children.length, over:l.scrollWidth - l.clientWidth, scrolls:b.scrollHeight > b.clientHeight, inside:e.contains(document.activeElement), lock:getComputedStyle(document.documentElement).overflowY, w:r.width / innerWidth}; })()""")
            ok(d['fits'] and d['cards'] == COUNTS[1] and d['over'] <= 0 and d['inside'] and d['lock'] == 'hidden', f'{label}: popup fits, shows every card, holds focus, locks the page {d}')
            ok(d['scrolls'] or w >= 1024, f'{label}: popup scrolls inside')
            p.screenshot(path=str(OUT / f'{ENGINE}-popup-{w}-{theme}.png'))
            p.locator('#section-dialog [data-ss-close]').focus(); p.keyboard.press('Escape'); p.wait_for_selector('#section-dialog', state='hidden')
            ok(p.evaluate("document.activeElement.matches('[data-sb-expand]')"), f'{label}: Escape closes the popup; focus returns')
            ctx.close()
    # Rounded navigation, forms, history (once per engine).
    ctx, p = session(browser, 'buyer', rewrite=False); p.goto(BASE + '/#orders'); p.wait_for_selector('#bo-board'); settled(p)
    pill = p.evaluate("(() => { const s = getComputedStyle(document.querySelector('#bo-toolbar .segment[aria-current]')); return [parseFloat(s.borderTopLeftRadius), s.backgroundColor]; })()")
    ok(pill[0] >= 20, f'rounded navigation stays rounded ({pill[0]} px)')
    p.locator('#bo-toolbar [data-select=bo-sort] .cf-trigger').click(); p.locator('[data-select=bo-sort] [role=option][data-value=oldest]').click(); settled(p)
    ok('sort=oldest' in p.url, 'a custom dropdown chooses and updates the address')
    p.evaluate("location.hash = '#catalogue'"); p.wait_for_selector('#results'); settled(p); p.fill('#filters input[name=q]', 'rack'); p.wait_for_timeout(500)
    ok(p.input_value('#filters input[name=q]') == 'rack', 'a text field takes input')
    p.go_back(); p.wait_for_selector('#bo-board'); settled(p)
    ok('#orders' in p.url and p.locator('#bo-board').count() == 1, 'Back returns to the previous page')
    p.go_forward(); p.wait_for_selector('#results'); settled(p)
    ok('#catalogue' in p.url, 'Forward goes on again')
    ctx.close()
    ctx, p = session(browser, 'host', rewrite=True); p.goto(BASE + '/#host/jobs?group=available'); p.wait_for_selector('#host-jobs-board'); settled(p)
    p.locator('.sb-mosaic [data-sb-open="in-production"]').click(); p.wait_for_timeout(400)
    ok(p.url.endswith('group=in-production'), 'switching stage updates the address')
    p.reload(); p.wait_for_selector('#host-jobs-board'); settled(p)
    ok(p.locator('#host-jobs-board').get_attribute('data-open') == 'in-production', 'a reload keeps the open stage')
    ctx.close()
    browser.close()
real = [e for e in errors]
ok(not real, 'no page errors: ' + '; '.join(real[:4]))
print(f'[{ENGINE}] {sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
