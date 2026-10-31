"""Price confirmation, colour shades and order-specific model downloads, in the browser.
Start a fresh isolated fixture first (it changes prices and creates orders):
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/catalogue_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/integrity_browser.py OUTPUT_DIR [BASE_URL]
Set CHROME to a Chromium binary if Playwright's bundled browser is not installed."""
import hashlib, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18101'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg)
NOTICE = 'The price of this product has changed from {} to {}. Please review the updated price before continuing.'

def session(browser, who, width=1366, theme='light'):
    ctx = browser.new_context(viewport={'width': width, 'height': 900}, color_scheme=theme)
    login = ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}); assert login.ok, login.text()
    ctx.csrf = login.json()['csrf_token']
    page = ctx.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
    # Intentional 409 responses (price changed) are logged by the browser; anything else is an error.
    page.on('console', lambda m: m.type == 'error' and '409' not in m.text and errors.append(m.text))
    return ctx, page

def go(page, route, theme='light'):
    page.goto(f'{BASE}/#{route}'); page.wait_for_load_state('networkidle'); page.evaluate(f"applyTheme('{theme}')")

def set_factor(admin, listing_id, factor):
    """Administrator pricing change: PLA factor in basis points (1800 × factor)."""
    r = admin.request.put(f'{BASE}/api/listings/{listing_id}/pricing', headers={'X-CSRF-Token': admin.csrf}, data={'materials': {'PLA': factor, 'PETG': 10000}, 'discounts': {}, 'max_quantity': 50})
    assert r.ok, r.text()

def configure(page, listing_id, material, color):
    go(page, f'product/api-{listing_id}'); page.locator('#config-add:enabled').wait_for()
    page.locator('.material-choice', has=page.locator(f'input[value="{material}"]')).click()
    page.locator('.swatches label', has=page.locator(f'input[value="{color}"]')).click()
    page.wait_for_function("document.querySelector('#live-price')?.dataset.ready==='1'")

def submit(page):
    street = page.locator('#new-address:not([disabled]) input[name=street]')
    if street.count() and not street.input_value(): street.fill('Via Laboratorio 12')   # no saved address yet
    page.get_by_role('button', name='Submit order request').click()

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    admin, _ = session(browser, 'admin')
    ids = {i['collection_key']: i['id'] for i in admin.request.get(BASE + '/api/listings?per_page=12').json()['items']}
    micro, fifteen = ids['microtube-rack'], ids['15ml-rack']
    buyer, p = session(browser, 'buyer')
    orders = lambda: buyer.request.get(BASE + '/api/orders').json()

    # 1. Basket: price changes after adding, the buyer must accept it, then it changes again at checkout.
    configure(p, micro, 'PLA', 'orange')
    ok('€18.00 each' in p.inner_text('#live-price'), 'product page shows €18.00')
    p.locator('#config-add').click(); p.get_by_text('Added!', exact=True).wait_for()
    line = buyer.request.get(BASE + '/api/cart').json()[0]
    ok(line['confirmed_unit_price_cents'] == 1800 and not line['price_changed'], 'basket remembers the price shown (€18.00)')
    set_factor(admin, micro, 11667)
    go(p, 'basket')
    notice = p.locator('.cart-line .price-notice')
    ok(notice.locator('p').inner_text() == NOTICE.format('€18.00', '€21.00'), 'basket shows the exact price-change notice')
    ok(p.locator('a', has_text='Checkout').get_attribute('aria-disabled') == 'true', 'checkout is blocked until the change is accepted')
    p.screenshot(path=str(OUT / 'basket-price-notice-1366-light.png'))
    notice.get_by_role('button', name='Accept updated price').click()
    p.wait_for_function("!document.querySelector('.cart-line .price-notice')")
    ok(p.locator('a', has_text='Checkout').get_attribute('aria-disabled') is None, 'accepting unblocks checkout')
    p.locator('a', has_text='Checkout').click(); p.locator('#checkout-form').wait_for()
    ok('€21.00 each' in p.inner_text('.summary-lines'), 'checkout summary shows the accepted €21.00')
    set_factor(admin, micro, 12778)          # changes again before submission
    submit(p); p.locator('.summary-card .banner').wait_for()
    ok(p.locator('.summary-lines .price-notice p').inner_text() == NOTICE.format('€21.00', '€23.00'), 'second change: new notice at checkout')
    ok(p.get_by_role('button', name='Submit order request').is_disabled() and orders() == [], 'no order placed; submission blocked')
    p.screenshot(path=str(OUT / 'checkout-price-notice-1366-light.png'))
    p.locator('.summary-lines').get_by_role('button', name='Accept updated price').click()
    p.get_by_role('button', name='Submit order request').wait_for(state='visible'); p.wait_for_function("!document.querySelector('.summary-card button.primary').disabled")
    submit(p); p.wait_for_url('**/#orders')
    placed = orders()
    ok(len(placed) == 1 and placed[0]['items'][0]['price_cents'] == 2300 and placed[0]['total_cents'] == 2300, 'order stores the confirmed €23.00')

    # 2. Buy Now: the price moves while the buyer is on the checkout page.
    configure(p, fifteen, 'PLA', 'cream')
    p.locator('#buy-now').click(); p.locator('#checkout-form').wait_for()
    shown = p.inner_text('.summary-lines')
    admin.request.put(f'{BASE}/api/listings/{fifteen}/pricing', headers={'X-CSRF-Token': admin.csrf}, data={'materials': {'PLA': 11000, 'PETG': 10000}, 'discounts': {}, 'max_quantity': 50})
    submit(p); p.locator('.summary-lines .price-notice').wait_for()
    ok('€22.00 each' in shown and p.locator('.summary-lines .price-notice p').inner_text() == NOTICE.format('€22.00', '€24.20'), 'Buy Now: notice from €22.00 to €24.20')
    p.locator('.summary-lines').get_by_role('button', name='Accept updated price').click()
    p.wait_for_function("!document.querySelector('.summary-card button.primary').disabled")
    submit(p); p.wait_for_url('**/#orders')
    ok(orders()[0]['total_cents'] == 2420 and len(buyer.request.get(BASE + '/api/cart').json()) == 0, 'Buy Now order at the accepted €24.20; basket untouched')

    # 3. Two hosts stock "black" in different shades: two distinct, labelled options.
    configure(p, micro, 'PLA', 'black~2b2b2b')
    labels = p.locator('.swatches small').all_inner_texts()
    ok('Black · #1B1B1B' in labels and 'Black · #2B2B2B' in labels and 'Black' not in labels, f'shades are separate options {labels}')
    ok(p.inner_text('#selected-color') == 'Black · #2B2B2B', 'selected shade is named with its colour')
    p.locator('#config-add').click(); p.get_by_text('Added!', exact=True).wait_for()
    go(p, 'basket')
    ok('PLA · Black · #2B2B2B' in p.inner_text('.cart-line .row-meta'), 'basket names the exact shade')
    p.locator('a', has_text='Checkout').click(); p.locator('#checkout-form').wait_for(); submit(p); p.wait_for_url('**/#orders')
    bought = orders()[0]
    ok((bought['items'][0]['color'], bought['items'][0]['color_hex']) == ('black~2b2b2b', '#2b2b2b'), 'order keeps the purchased shade')
    job = bought['jobs'][0]['id']
    host, hp = session(browser, 'host'); other, op = session(browser, 'other')
    ok(job not in [j['id'] for j in host.request.get(BASE + '/api/host/jobs').json()], 'host with the other black does not see the job')

    # 4. Order-specific model download, revoked on reassignment.
    ok(other.request.post(f'{BASE}/api/host/jobs/{job}/accept', headers={'X-CSRF-Token': other.csrf}).ok, 'matching host accepts the job')
    go(op, 'host/jobs/accepted')
    link = op.get_by_role('link', name='Download STL')
    ok(link.count() == 1 and link.get_attribute('href') == f'/api/jobs/{job}/cad', 'accepted job offers its model download')
    op.screenshot(path=str(OUT / 'host-job-download-1366-light.png'))
    model = other.request.get(f'{BASE}/api/jobs/{job}/cad')
    ok(model.ok and model.headers['x-content-sha256'] == hashlib.sha256(model.body()).hexdigest() and model.headers['x-openlabs3d-model-version'] == 'pinned', 'download is the pinned file, checksum verified')
    ok(host.request.get(f'{BASE}/api/jobs/{job}/cad').status == 404, 'another host cannot download it')
    ok(admin.request.post(f'{BASE}/api/admin/jobs/{job}/reopen', headers={'X-CSRF-Token': admin.csrf}).ok, 'administrator reopens the job')
    ok(other.request.get(f'{BASE}/api/jobs/{job}/cad').status == 404, 'previous host loses access after reassignment')
    go(op, 'host/jobs'); ok(op.get_by_role('link', name='Download STL').count() == 0, 'download link disappears')

    # Mobile and Dark: the notice fits.
    set_factor(admin, micro, 10000)
    mob, mp = session(browser, 'buyer', 390, 'dark')
    configure(mp, micro, 'PLA', 'orange'); mp.locator('#config-add').click(); mp.get_by_text('Added!', exact=True).wait_for()
    set_factor(admin, micro, 11667)
    go(mp, 'basket', 'dark'); mp.locator('.price-notice').wait_for()
    ok(mp.locator('.price-notice').count() == 1 and mp.evaluate('document.documentElement.scrollWidth - innerWidth') <= 0, 'mobile dark: notice shown, no overflow')
    mp.screenshot(path=str(OUT / 'basket-price-notice-390-dark.png'), full_page=True)
    browser.close()
print('ERRORS', errors)
print(f'{sum(checks)} passed, {len(checks) - sum(checks)} failed')
sys.exit(0 if all(checks) and not errors else 1)
