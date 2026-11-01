"""Job eligibility in the browser: hosts never see or take their own orders, are not offered capacity
only they have, and acceptance is revalidated. Administrators see who can take each job and why not.
Start a fresh isolated fixture first (it places orders and changes stock):
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/catalogue_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/job_eligibility_browser.py OUTPUT_DIR [BASE_URL]
Fixture stock: host has PLA orange #e66100, black #1b1b1b and more; other has only PLA black #2b2b2b."""
import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18101'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg)
DIALOG = '#action-dialog'

def session(browser, who, width=1366, height=900, theme='light'):
    ctx = browser.new_context(viewport={'width': width, 'height': height}, color_scheme=theme)
    login = ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}); assert login.ok
    ctx.csrf = login.json()['csrf_token']
    page = ctx.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
    # Refused requests (403/409/422) are expected here; anything else is an error.
    page.on('console', lambda m: m.type == 'error' and not any(c in m.text for c in ('403', '409', '422')) and errors.append(m.text))
    return ctx, page

def order(ctx, listing_id, color):
    line = {'listing_id': listing_id, 'material': 'PLA', 'color': color, 'quantity': 1}
    price = ctx.request.post(f'{BASE}/api/listings/{listing_id}/quote', data={k: line[k] for k in ('material', 'color', 'quantity')}).json()['unit_price_cents']
    r = ctx.request.post(BASE + '/api/checkout', headers={'X-CSRF-Token': ctx.csrf}, data={'idempotency_key': os.urandom(12).hex(), 'contact': {'first_name': 'Ada', 'last_name': 'Bench', 'phone': '+39 011 1234567', 'country': 'IT', 'city': 'Torino', 'street': 'Via Po 1'}, 'direct': line, 'confirmed': [{**line, 'unit_price_cents': price}]})
    assert r.ok, r.text(); return r.json()

def configurator(page, listing_id):
    page.goto(f'{BASE}/?qa={os.urandom(4).hex()}#product/api-{listing_id}')   # a fresh load, even on the same product
    page.wait_for_function("document.querySelector('#live-price')?.dataset.ready !== '' || document.querySelector('.availability-message')?.textContent")
    page.wait_for_timeout(300)
    return (page.eval_on_selector_all('input[name=material]', 'els => els.map(e => e.value)'),
            page.eval_on_selector_all('input[name=color]', 'els => els.map(e => e.value)'))

def jobs_page(page, route='host/jobs/available'):
    page.goto(f'{BASE}/?qa={os.urandom(4).hex()}#{route}'); page.wait_for_selector('.ws-main h1'); page.wait_for_selector('.ws-main[aria-busy]', state='detached')

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    buyer, bp = session(browser, 'buyer'); host, hp = session(browser, 'host'); other, op = session(browser, 'other')
    micro = next(i['id'] for i in buyer.request.get(BASE + '/api/listings?per_page=12').json()['items'] if i['collection_key'] == 'microtube-rack')

    # Configurator: a host is offered only what another host can make, under the same shade keys.
    materials, colors = configurator(bp, micro)
    ok('PETG' in materials and len(colors) > 2, f'buyer is offered every host\'s stock ({materials}, {len(colors)} PLA shades)')
    materials, colors = configurator(hp, micro)
    ok(materials == ['PLA'] and colors == ['black~2b2b2b'], f'host is offered only the other host\'s black ({materials}, {colors})')
    hp.screenshot(path=str(OUT / 'configurator-host-1366-light.png'))
    # Only the host's own printers can make it: the configurator says why instead of offering nothing.
    kept = other.request.get(BASE + '/api/host/materials').json()['material_colors']
    ok(other.request.put(BASE + '/api/host/materials', headers={'X-CSRF-Token': other.csrf}, data={'material_colors': {}}).ok, 'the other host clears its stock')
    configurator(hp, micro)
    ok('Only your own printers' in hp.locator('.availability-message').inner_text() and hp.locator('#configurator .material-options').is_hidden()
       and hp.locator('#live-price').inner_text() == 'Not available to order' and hp.locator('#config-add').is_disabled(),
       'host is told only their own printers make it: ' + hp.locator('.availability-message').inner_text()[:80])
    hp.screenshot(path=str(OUT / 'configurator-own-printers-only-1366-light.png'))
    materials, _ = configurator(bp, micro)
    ok('PLA' in materials and 'Only your own' not in bp.locator('.availability-message').inner_text(), 'buyers are still offered that host\'s stock')
    ok(other.request.put(BASE + '/api/host/materials', headers={'X-CSRF-Token': other.csrf}, data={'material_colors': kept}).ok, 'the other host restores its stock')

    # A host's own order: never in their Available Jobs, still in their My Orders, offered to the other host.
    own = order(host, micro, 'black~2b2b2b'); own_job = own['jobs'][0]['id']
    jobs_page(hp)
    ok(hp.locator(f'[data-job="{own_job}"]').count() == 0, 'host does not see the job from their own order')
    ok('Jobs from your own orders are never listed' in hp.locator('.ws-intro').inner_text(), 'the page says why')
    refused = host.request.post(f'{BASE}/api/host/jobs/{own_job}/accept', headers={'X-CSRF-Token': host.csrf})
    ok(refused.status == 403 and 'your own order' in refused.json()['detail'], 'accepting it through the API is refused')
    hp.goto(BASE + '/#orders'); hp.wait_for_selector(f'text={own["reference"]}')
    ok(hp.locator(f'text={own["reference"]}').count() >= 1, 'host still sees it in My Orders')
    hp.screenshot(path=str(OUT / 'host-my-orders-1366-light.png'))
    jobs_page(op)
    ok(op.locator(f'[data-job="{own_job}"]').count() == 1, 'the other host is offered it')

    # Revalidation: the host removes the ordered colour while the accept dialog is open.
    stranded = order(buyer, micro, 'orange'); job = stranded['jobs'][0]['id']
    jobs_page(hp); hp.locator(f'[data-job="{job}"]', has_text='Accept job').click(); hp.wait_for_selector(DIALOG + '[open]')
    stock = host.request.get(BASE + '/api/host/materials').json()['material_colors']
    stock['PLA'].pop('orange')
    ok(host.request.put(BASE + '/api/host/materials', headers={'X-CSRF-Token': host.csrf}, data={'material_colors': stock}).ok, 'host removes PLA orange from stock')
    hp.locator(DIALOG).get_by_role('button', name='Accept job').click(); hp.locator('.ad-error').wait_for()
    ok('do not stock PLA' in hp.locator('.ad-error').inner_text() and hp.locator(DIALOG + '[open]').count() == 1, 'acceptance is refused with its reason in the dialog')
    hp.screenshot(path=str(OUT / 'accept-refused-1366-light.png'))
    hp.locator(DIALOG).get_by_role('button', name='Cancel').click()
    hp.wait_for_selector(f'[data-job="{job}"]', state='detached')
    ok(hp.locator(f'[data-job="{job}"]').count() == 0, 'closing the dialog refreshes the list without that job')
    hp.wait_for_function("document.activeElement !== document.body")
    ok(hp.evaluate("document.activeElement.matches('#host-jobs-board .wf-column[data-stage=available], .scope-nav [aria-current]')"), 'focus returns to the Available column the job was in (or Active jobs when none is left)')
    ok(next(j for j in buyer.request.get(BASE + '/api/orders').json() if j['id'] == stranded['id'])['jobs'][0]['status'] == 'available', 'the job is still available')

    # Administrators: who can take each available job, and why the others cannot.
    for width, height, theme in ((1366, 900, 'light'), (1366, 900, 'dark'), (390, 844, 'light'), (390, 844, 'dark')):
        ctx, ap = session(browser, 'admin', width, height, theme); ap.emulate_media(color_scheme=theme)
        jobs_page(ap, 'admin/orders'); ap.evaluate(f"applyTheme('{theme}')")
        rows = {ref: ap.locator('.list-row', has_text=ref) for ref in (own['reference'], stranded['reference'])}
        for row in rows.values(): row.locator('summary').click()
        own_text, stranded_text = rows[own['reference']].inner_text(), rows[stranded['reference']].inner_text()
        if width == 1366 and theme == 'light':
            ok('can be made by other' in own_text.lower() and 'buyer of this order' in own_text, 'admin: the host\'s own order can be made by the other host, not its buyer')
            ok('No eligible host' in stranded_text and 'does not stock PLA orange' in stranded_text, 'admin: the stranded job shows why no host can take it')
        ok(ap.evaluate('document.documentElement.scrollWidth - innerWidth') <= 0, f'{width} {theme}: admin orders fit the screen')
        rows[stranded['reference']].scroll_into_view_if_needed()
        ap.screenshot(path=str(OUT / f'admin-orders-{width}-{theme}.png'))
        if width == 1366 and theme == 'light':
            jobs_page(ap, 'admin'); ap.wait_for_selector('.attention-list, .ws-main .empty-state')
            ok(ap.locator('.attention-list', has_text='available job no approved host can make').count() == 1, 'admin overview flags the job no host can make')
            ap.screenshot(path=str(OUT / 'admin-overview-1366-light.png'))
            # The warning opens the orders behind it, marked and expanded; one click shows every order again.
            ap.locator('.attention-list a', has_text='available job no approved host can make').click()
            ap.wait_for_url('**attention=unmatched**'); ap.wait_for_selector('.attention-filter'); ap.wait_for_selector('.ws-main[aria-busy]', state='detached')
            ok(ap.locator('#order-list .row-title').all_inner_texts() == [stranded['reference']], 'the warning lists only the order no host can make')
            ok(ap.locator('#order-list .row-status', has_text='No eligible host').count() == 1 and ap.locator('#order-list details[open]').count() == 1, 'it is marked on the row and opened')
            ap.screenshot(path=str(OUT / 'admin-attention-1366-light.png'))
            ap.locator('.attention-filter a', has_text='Show all orders').click(); ap.wait_for_selector('.attention-filter', state='detached')
            ok(ap.locator('#order-list .list-row').count() > 1 and 'attention' not in ap.url, 'Show all orders clears the filter')
        ctx.close()
    browser.close()
print('ERRORS', errors)
print(f'{sum(checks)} passed, {len(checks) - sum(checks)} failed')
sys.exit(0 if all(checks) and not errors else 1)
