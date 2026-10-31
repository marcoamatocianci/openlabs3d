"""Host job steps are confirmed in the site's own dialog, never the browser's confirm box.
Start a fresh isolated fixture first (it places orders and changes job states):
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/catalogue_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/host_job_dialog_browser.py OUTPUT_DIR [BASE_URL]
Set CHROME to a Chromium binary if Playwright's bundled browser is not installed."""
import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18101'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors, native = [], [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg)
DIALOG = '#action-dialog'

def session(browser, who, width=1366, height=900, theme='light'):
    ctx = browser.new_context(viewport={'width': width, 'height': height}, color_scheme=theme)
    login = ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}); assert login.ok
    ctx.csrf = login.json()['csrf_token']
    page = ctx.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: m.type == 'error' and '409' not in m.text and errors.append(m.text))
    page.on('dialog', lambda d: (native.append(d.message), d.dismiss()))   # any browser confirm/alert is a failure
    return ctx, page

def order(buyer, listing_id):
    line = {'listing_id': listing_id, 'material': 'PLA', 'color': 'orange', 'quantity': 2}
    price = buyer.request.post(f'{BASE}/api/listings/{listing_id}/quote', data={k: line[k] for k in ('material', 'color', 'quantity')}).json()['unit_price_cents']
    r = buyer.request.post(BASE + '/api/checkout', headers={'X-CSRF-Token': buyer.csrf}, data={'idempotency_key': os.urandom(12).hex(), 'contact': {'first_name': 'Ada', 'last_name': 'Bench', 'phone': '+39 011 1234567', 'country': 'IT', 'city': 'Torino', 'street': 'Via Po 1'}, 'direct': line, 'confirmed': [{**line, 'unit_price_cents': price}]})
    assert r.ok, r.text(); return r.json()['jobs'][0]['id']

def open_step(page, job, label):
    page.locator(f'[data-job="{job}"]', has_text=label).click(); page.wait_for_selector(DIALOG + '[open]')

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    buyer, _ = session(browser, 'buyer')
    micro = next(i['id'] for i in buyer.request.get(BASE + '/api/listings?per_page=12').json()['items'] if i['collection_key'] == 'microtube-rack')
    first, second = order(buyer, micro), order(buyer, micro)
    host, p = session(browser, 'host')
    status = lambda job: next(j['status'] for j in host.request.get(BASE + '/api/host/jobs').json() if j['id'] == job)
    p.goto(BASE + '/#host/jobs/available'); p.wait_for_selector(f'[data-job="{first}"]')

    # The dialog: modal, labelled, describes the job and the step.
    open_step(p, first, 'Accept job')
    d = p.locator(DIALOG)
    ok(p.evaluate("document.querySelector('#action-dialog').matches(':modal')") and d.get_by_role('heading', name='Accept this printing job?').is_visible(), 'Accept opens the site dialog')
    ok(not native, 'no browser confirm box')
    text = d.inner_text()
    ok('Microtube Rack' in text and '× 2' in text and 'PLA · Orange' in text and f'Order #' in text, 'shows the product, quantity, material and colour')
    ok(d.locator('.ad-swatch').evaluate('e => getComputedStyle(e).backgroundColor') == 'rgb(230, 97, 0)', 'colour swatch uses the ordered shade')
    ok(d.locator('.ad-flow [aria-current=step]').inner_text().strip() == 'Accepted', 'progress shows the next step')
    ok('contact and delivery details become visible' in text, 'explains what accepting means')
    ok(p.evaluate("document.activeElement.dataset.adConfirm !== undefined"), 'focus starts on the action')
    ok(p.evaluate("getComputedStyle(document.documentElement).overflow") == 'hidden', 'page behind does not scroll')
    p.screenshot(path=str(OUT / 'accept-1366-light.png'))
    for _ in range(8): p.keyboard.press('Tab')
    ok(p.evaluate("document.querySelector('#action-dialog').contains(document.activeElement)"), 'Tab stays inside the dialog')

    # Leaving without acting: Escape, Cancel, outside click. Nothing changes.
    p.keyboard.press('Escape')
    ok(p.locator(DIALOG + '[open]').count() == 0 and status(first) == 'available', 'Escape closes without accepting')
    ok(p.evaluate('document.activeElement.dataset.job') == str(first), 'focus returns to the button')
    open_step(p, first, 'Accept job'); d.get_by_role('button', name='Cancel').click()
    ok(p.locator(DIALOG + '[open]').count() == 0 and status(first) == 'available', 'Cancel closes without accepting')
    open_step(p, first, 'Accept job'); p.mouse.click(8, 450)
    ok(p.locator(DIALOG + '[open]').count() == 0, 'clicking outside closes it')

    # Each step through to completion.
    for label, title, after, toast in (('Accept job', 'Accept this printing job?', 'accepted', 'Job accepted'), ('Start printing', 'Start printing?', 'printing', 'Printing started'),
                                       ('Mark ready', 'Mark as ready for delivery?', 'ready', 'Marked ready for delivery'), ('Mark completed', 'Mark this job completed?', 'completed', 'Job completed')):
        if label != 'Accept job': p.goto(BASE + '/#host/jobs'); p.wait_for_selector(f'[data-job="{first}"]')
        open_step(p, first, label)
        ok(d.get_by_role('heading', name=title).is_visible(), f'{label}: dialog titled "{title}"')
        if label == 'Mark ready': p.screenshot(path=str(OUT / 'ready-1366-light.png'))
        d.get_by_role('button', name=label).click()
        p.wait_for_selector(DIALOG + ':not([open])', state='attached'); p.get_by_text(toast, exact=True).wait_for()
        ok(status(first) == after, f'{label}: job is now {after}, confirmed with "{toast}"')
    p.wait_for_timeout(400)
    ok(p.evaluate("document.activeElement.classList.contains('chip') || !!document.activeElement.dataset.job"), 'focus lands back in the job list after the refresh')

    # Errors stay in the dialog, in the site's style.
    p.goto(BASE + '/#host/jobs/available'); p.wait_for_selector(f'[data-job="{second}"]')
    open_step(p, second, 'Accept job')
    host.request.post(f'{BASE}/api/host/jobs/{second}/accept', headers={'X-CSRF-Token': host.csrf})   # taken meanwhile
    d.get_by_role('button', name='Accept job').click(); p.locator('.ad-error').wait_for()
    ok('no longer available' in p.locator('.ad-error').inner_text() and p.locator(DIALOG + '[open]').count() == 1, 'a failed step shows its reason inside the dialog')
    p.screenshot(path=str(OUT / 'error-1366-light.png'))
    d.get_by_role('button', name='Cancel').click()
    ok(not native, 'still no browser dialogs')

    # Dark mode and the mobile sheet.
    third = order(buyer, micro)
    for width, height, theme in ((1366, 900, 'dark'), (390, 844, 'dark'), (390, 844, 'light')):
        ctx, q = session(browser, 'host', width, height, theme); q.goto(BASE + '/#host/jobs/available'); q.evaluate(f"applyTheme('{theme}')")
        q.wait_for_selector(f'[data-job="{third}"]'); open_step(q, third, 'Accept job'); q.wait_for_timeout(350)
        box = q.locator(DIALOG).bounding_box()
        ok(q.evaluate('document.documentElement.scrollWidth - innerWidth') <= 0 and box['x'] >= 0 and box['x'] + box['width'] <= width + .5, f'{width} {theme}: fits the screen')
        if width < 640: ok(abs(box['y'] + box['height'] - height) <= 1 and q.locator(f'{DIALOG} [data-ad-confirm]').bounding_box()['height'] >= 44, f'{width} {theme}: bottom sheet with 44 px buttons')
        q.screenshot(path=str(OUT / f'accept-{width}-{theme}.png')); ctx.close()
    browser.close()
print('NATIVE DIALOGS', native); print('ERRORS', errors)
print(f'{sum(checks)} passed, {len(checks) - sum(checks)} failed')
sys.exit(0 if all(checks) and not errors and not native else 1)
