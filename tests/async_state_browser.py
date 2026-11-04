"""Late and repeated responses, against the workflow fixture: a slow answer never overwrites a newer page, a refresh
after a write never reuses an older read, repeated navigation fetches once per visit, and handlers do not pile up.
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/async_state_browser.py [BASE_URL]"""
import os, re, sys, time
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
def session(browser, who=None):
    ctx = browser.new_context(viewport={'width': 1366, 'height': 900})
    if who: assert ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}).ok
    p = ctx.new_page(); p.calls = []
    p.on('pageerror', lambda e: errors.append(str(e)))
    p.on('request', lambda r: '/api/' in r.url and r.resource_type in ('fetch', 'xhr') and '/visuals/' not in r.url and p.calls.append(f"{r.method} {r.url.split('/api/')[1]}"))
    return ctx, p
def delay(ctx, pattern, seconds, first_only=True):
    state = {'n': 0}
    def handler(route):
        state['n'] += 1
        if state['n'] == 1 or not first_only: time.sleep(seconds)
        route.continue_()
    ctx.route(re.compile(pattern), handler)
def settled(p, ms=600): p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)

    # A slow page cannot replace the page the reader moved on to.
    ctx, p = session(browser, 'host'); p.goto(BASE + '/#my-listings'); p.wait_for_selector('.ws-main h1, .ws-main .ws-title, .ws-main'); settled(p, 200)
    title = lambda: p.evaluate("document.title + ' | ' + (document.querySelector('.ws-main h1, .ws-head h1')?.textContent || '')")
    listings = title()
    delay(ctx, r'/api/host/jobs\?scope=active$', 1.0)
    p.evaluate("location.hash = '#host/jobs'"); p.wait_for_timeout(120); p.evaluate("location.hash = '#my-listings'"); settled(p, 1300)
    ok(title() == listings and p.locator('#host-jobs-board').count() == 0, f'workspace: the late Printing jobs response does not replace My listings ({title()})')
    ctx.close()

    # My orders: the same, between its two views.
    ctx, p = session(browser, 'buyer'); delay(ctx, r'/api/orders\?scope=active', 1.0)
    p.goto(BASE + '/#orders?scope=history'); p.wait_for_selector('#bo-history-board'); settled(p, 200)
    p.evaluate("location.hash = '#orders'"); p.wait_for_timeout(100); p.evaluate("location.hash = '#orders?scope=history'"); settled(p, 1300)
    ok(p.locator('#bo-history-board').count() == 1 and p.locator('#bo-board').count() == 0, 'My orders: the late Current orders response does not replace Previous orders')
    ctx.close()

    # Catalogue filters: an older search cannot overwrite a newer one.
    ctx, p = session(browser); delay(ctx, r'/api/listings\?q=&category=&sort=price_asc', 1.0)
    p.goto(BASE + '/#catalogue'); p.wait_for_selector('#results .card, #results article, #results a', state='attached'); settled(p, 300)
    newer = p.evaluate("""async () => { const form = document.querySelector('#filters'), sort = form.elements.sort; if (!sort) return null;
      const set = v => { sort.value = v; if (typeof filter === 'function') filter(); }; set('price_asc'); await new Promise(r => setTimeout(r, 80)); set('newest'); return true; }""")
    settled(p, 1400)
    if newer:
        last = p.evaluate("document.querySelector('#filters').elements.sort.value")
        expected = p.evaluate("(async () => (await (await fetch('/api/listings?q=&category=&sort=newest&page=1&per_page=12')).json()).items.map(i => i.title))()")
        shown = p.evaluate("document.querySelector('#results').innerText")
        ok(last == 'newest' and shown.find(expected[0]) <= shown.find(expected[-1]), 'catalogue: the slower, older sort does not overwrite the newer one')
    ctx.close()

    # A signed-in session: the account does not arrive after the page has drawn for nobody.
    ctx, p = session(browser, 'host'); delay(ctx, r'/api/auth/me$', .7); p.goto(BASE + '/#host/jobs')
    p.wait_for_selector('#host-jobs-board', timeout=8000)
    ok(p.locator('.ws-main').count() == 1 and p.evaluate("document.body.innerText").find('Sign in to continue') < 0, 'a slow session check shows no sign-in prompt to a signed-in host')
    ctx.close()

    # Sharing reads never survives a write.
    ctx, p = session(browser, 'host'); p.goto(BASE + '/#host/jobs'); p.wait_for_selector('#host-jobs-board'); settled(p, 200); p.calls.clear()
    shared = p.evaluate("""async () => { const a = api('/settings'), b = api('/settings'); const [x, y] = await Promise.all([a, b]); return x !== y && JSON.stringify(x) === JSON.stringify(y); }""")
    ok(shared and p.calls.count('GET settings') == 1, 'identical reads at the same moment share one request, each with its own copy')
    p.calls.clear()
    fresh = p.evaluate("""async () => {
      const before = api('/settings');                       // a read on its way…
      const write = api('/profile', {method:'PUT', body:'{}'}).catch(() => null);    // …then a write (its answer does not matter here)
      const during = api('/settings'); await write;
      const after = api('/settings'); await Promise.all([before, during, after]); return true; }""")
    ok(fresh and p.calls.count('GET settings') == 3, f'reads around a write are not shared: {p.calls.count("GET settings")} of 3 went to the server')
    ctx.close()

    # Repeated navigation: one fetch per visit (legitimate refreshes still happen), no extra handlers.
    ctx, p = session(browser, 'host'); p.goto(BASE + '/#host/jobs'); p.wait_for_selector('#host-jobs-board'); settled(p, 200)
    for n in range(3):
        p.calls.clear()
        p.evaluate("location.hash = '#host'"); p.wait_for_selector('.ho-stats'); settled(p, 150)
        away = p.calls.count('GET host/jobs?scope=active')
        p.calls.clear()
        p.evaluate("location.hash = '#host/jobs'"); p.wait_for_selector('#host-jobs-board'); settled(p, 150)
        ok(away == 1 and p.calls.count('GET host/jobs?scope=active') == 1, f'visit {n + 1}: each page fetches once when opened ({away}, {p.calls.count("GET host/jobs?scope=active")})')
    theme = lambda: p.evaluate('document.documentElement.dataset.theme')
    p.evaluate("(() => { const t = document.querySelector('[data-dropdown][aria-controls]'); })()")
    before = theme(); p.evaluate('toggleTheme()'); first = theme(); p.evaluate('toggleTheme()')
    ok(first != before and theme() == before, 'theme toggles once per call after repeated navigation')
    head = p.locator('#host-jobs-board .sb-col.is-open .sb-head'); start = p.locator('#host-jobs-board').get_attribute('data-open'); head.click(); p.wait_for_timeout(420)
    ok(p.locator('#host-jobs-board').get_attribute('data-open') == 'none', 'one click collapses once after repeated navigation: handlers have not piled up')
    p.locator(f'#host-jobs-board .sb-mosaic [data-sb-open="{start}"]').click(); p.wait_for_timeout(420)
    p.locator('#host-jobs-board .sb-col.is-open [data-sb-expand]').click(); p.wait_for_selector('#section-dialog[open]')
    ok(p.evaluate("document.querySelectorAll('dialog[open]').length") == 1, 'one click opens one dialog')
    ctx.close()

    # Moving between roles' pages after startup draws what the page needs, the catalogue included.
    ctx, p = session(browser, 'buyer'); p.goto(BASE + '/#orders'); p.wait_for_selector('#bo-board'); settled(p, 200)
    ok('GET listings?per_page=50' not in p.calls, 'My orders does not download the catalogue it does not show')
    p.calls.clear(); pid = p.evaluate("(async () => (await (await fetch('/api/listings?per_page=1')).json()).items[0].id)()")
    p.evaluate(f"location.hash = '#product/api-{pid}'"); p.wait_for_selector('.config-layout, .product-big, #model-viewer', timeout=8000)
    ok(p.calls.count('GET listings?per_page=50') == 1 and p.evaluate("document.body.innerText").find('Product unavailable') < 0, 'opening a product from there loads the catalogue first, once, and the page is right')
    p.evaluate("location.hash = '#catalogue'"); p.wait_for_selector('#results'); settled(p, 200)
    ok(p.calls.count('GET listings?per_page=50') == 1, 'and it is not fetched again')
    ctx.close()
    # A basket write right after the page loads: the startup read of the basket must not stand in for it.
    ctx, p = session(browser, 'buyer'); p.goto(BASE + '/#home'); p.wait_for_function("typeof account !== 'undefined' && account && typeof accountAction === 'function'")
    title, at = p.evaluate("""async () => { const product = (await api('/listings?per_page=12')).items.find(i => i.collection_key === '15ml-rack');
      await accountAction('/cart', {listing_id:product.id, material:'PETG', color:'signal-red', quantity:1}, 'PUT'); location.hash = 'basket'; return [product.title, performance.now()]; }""")
    settled(p)
    ok(at < 3000 and title in p.locator('#app').inner_text() and p.evaluate('opsCart.length') == 1, f'a basket line added {at:.0f} ms after load shows on the basket page')
    ctx.close()
    ok(not errors, 'no page errors: ' + '; '.join(errors[:4]))
    browser.close()
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
