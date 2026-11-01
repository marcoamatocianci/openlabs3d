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
    ok('Microtube Rack' in text and '× 2' in text and 'PLA · Orange' in text and 'Order OL3D-' in text, 'shows the product, quantity, material and colour, and the order as the buyer names it')
    ok(d.locator('.ad-swatch').evaluate('e => getComputedStyle(e).backgroundColor') == 'rgb(230, 97, 0)', 'colour swatch uses the ordered shade')
    ok(d.locator('.ad-flow [aria-current=step]').inner_text().strip() == 'In production', 'progress shows the next step: In production')
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

    # Each step up to shipped: accepting puts the job in production; Mark ready to ship follows directly.
    for label, title, after, toast, stage in (('Accept job', 'Accept this printing job?', 'accepted', 'Job accepted', 'available'),
                                              ('Mark ready to ship', 'Mark as ready to ship?', 'ready', 'Marked ready to ship', 'in-production')):
        if label != 'Accept job': p.goto(BASE + f'/#host/jobs?group={stage}'); p.wait_for_selector(f'[data-job="{first}"]')
        open_step(p, first, label)
        ok(d.get_by_role('heading', name=title).is_visible(), f'{label}: dialog titled "{title}"')
        if label != 'Accept job': p.screenshot(path=str(OUT / 'ready-1366-light.png'))
        d.get_by_role('button', name=label).click()
        p.wait_for_selector(DIALOG + ':not([open])', state='attached'); p.get_by_text(toast, exact=True).wait_for()
        ok(status(first) == after, f'{label}: job is now {after}, confirmed with "{toast}"')
        p.wait_for_function("document.activeElement?.closest('.sb-col.is-open')")
        ok(p.locator('.sb-col.is-open').get_attribute('data-stage') == stage, f'{label}: the stage it was done from stays open, and keeps focus')
    ok(p.get_by_text('Start printing').count() == 0, 'no Start printing step')
    ok(p.locator(f'[data-job="{first}"]', has_text='Mark completed').count() == 0, 'hosts cannot complete a job')

    # Shipping: same dialog and bullets, plus the shipment form.
    p.goto(BASE + '/#host/jobs?group=ready'); p.wait_for_selector(f'[data-job="{first}"]')
    open_step(p, first, 'Mark shipped')
    ok(d.get_by_role('heading', name='Mark as shipped?').is_visible() and d.locator('.ad-notes li').count() == 3, 'Mark shipped opens the job dialog with its notes')
    ok(d.locator('.ad-flow [aria-current=step]').inner_text().strip() == 'Shipped', 'progress shows Shipped between Ready to ship and Completed')
    ok([t.strip().split('\n')[0] for t in d.locator('.ad-flow li').all_inner_texts()] == ['In production', 'Ready to ship', 'Shipped', 'Completed'] and 'Awaiting buyer confirmation' in d.locator('.ad-flow li').last.inner_text(), 'Completed waits for the buyer')
    ok(p.evaluate("document.activeElement.name") == 'carrier', 'focus starts in the shipment form')
    p.screenshot(path=str(OUT / 'shipped-1366-light.png'))
    d.get_by_role('button', name='Mark shipped').click()
    ok(p.locator(DIALOG + '[open]').count() == 1 and 'carrier and tracking number' in p.locator('.ad-error').inner_text() and status(first) == 'ready', 'shipment details are required')
    d.locator('[name=carrier]').fill('DHL Express'); d.locator('[name=tracking_number]').fill('JD0146000032')
    d.locator('[name=tracking_url]').fill('ftp://example.org')
    d.get_by_role('button', name='Mark shipped').click()
    ok('http:// or https://' in p.locator('.ad-error').inner_text() and status(first) == 'ready', 'tracking links must be web addresses')
    d.locator('[name=tracking_url]').fill('https://www.dhl.com/track?id=JD0146000032'); d.locator('[name=note]').fill('Left with reception')
    d.locator('[name=tracking_number]').press('Enter')
    p.wait_for_selector(DIALOG + ':not([open])', state='attached'); p.get_by_text('Marked as shipped', exact=True).wait_for()
    ok(status(first) == 'shipped', 'Enter in the form marks the job shipped')
    # A shipped job stays in Active jobs (Awaiting buyer) until the buyer confirms receipt.
    p.goto(BASE + '/#host/jobs?group=shipped'); p.wait_for_selector(f'[data-job-card="{first}"]')
    shipped_card = p.locator(f'#host-jobs-board [data-stage="shipped"] [data-job-card="{first}"]')
    ok(shipped_card.count() == 1 and p.locator('#ws-title').inner_text() == 'Printing jobs', 'a shipped job stays an active job')
    ok(p.locator('#host-jobs-board .sb-col.is-open[data-stage="shipped"] .sb-title').inner_text() == 'Awaiting buyer', 'listed under Awaiting buyer, the stage the link opened')
    ok('DHL Express' in shipped_card.inner_text() and shipped_card.locator('a[href^="https://www.dhl.com"]').count() == 1, 'the shipment appears with the job')
    shipped_card.locator('[data-job-details]').click(); p.wait_for_selector('#modal[open]')
    ok('Left with reception' in p.locator('#modal').inner_text() and p.locator('#modal [data-details-step]').count() == 0, 'its details show the shipment note and no further step')
    p.keyboard.press('Escape')

    # Colours: one per category; accepted, printing, ready and shipped share one.
    third_job = order(buyer, micro); host.request.post(f'{BASE}/api/host/jobs/{third_job}/accept', headers={'X-CSRF-Token': host.csrf})
    p.goto(BASE + '/#host/jobs'); p.wait_for_selector(f'[data-job="{third_job}"]', state='attached')   # in a collapsed stage
    stages = p.evaluate("[...document.querySelectorAll('#host-jobs-board .sb-col')].map(c => c.dataset.stage)")
    ok(stages == ['available', 'in-production', 'ready', 'shipped'] and p.locator(f'#host-jobs-board [data-stage="in-production"] [data-job-card="{third_job}"]').count() == 1, 'Active jobs: one stage each, available first, no finished stage: ' + ','.join(stages))
    # Colours: one per category in the status badges (job details); accepted to shipped share one.
    badges = {}
    for jid, stage in ((second, 'available'), (third_job, 'in-production'), (first, 'shipped')):
        p.locator(f'#host-jobs-board .sb-head[data-sb-open="{stage}"]').click()
        p.locator(f'[data-job-details="{jid}"]').first.click(); p.wait_for_selector('#modal[open]')
        b = p.locator('#modal .job-status'); badges[jid] = (b.get_attribute('class').split('job-')[-1], b.evaluate('e => getComputedStyle(e).backgroundColor')); p.keyboard.press('Escape')
    ok(badges[second][0] == 'available' and badges[third_job][0] == badges[first][0] == 'active' and badges[third_job][1] == badges[first][1] != badges[second][1], f'one colour per category, shared within it {badges}')

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
