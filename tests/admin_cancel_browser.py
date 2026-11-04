"""Admin order cancellation in the browser, against the isolated workflow fixture: available at every stage
before completion, a confirmation with each product's stage, a production warning, a required reason, an
explicit acknowledgement for shipped products, in-place refresh, and history afterwards.
Start a fresh fixture first (this suite cancels orders):
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/admin_cancel_browser.py OUTPUT_DIR [BASE_URL]"""
import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)

def session(browser, who, w=1440, h=900, theme='light'):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme)
    login = ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}); assert login.ok
    ctx.csrf = login.json()['csrf_token']
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(f'{who} {w}: {e}'))
    # 409 responses are expected where the suite provokes a conflict; anything else is an error.
    page.on('console', lambda m: m.type == 'error' and '409' not in m.text and errors.append(f'{who} {w}: {m.text}'))
    page.on('dialog', lambda d: (errors.append('native dialog: ' + d.message), d.dismiss()))
    return ctx, page

def api(ctx, path): return ctx.request.get(BASE + '/api' + path).json()
def overflow(page): return page.evaluate('document.documentElement.scrollWidth - innerWidth')
def ready(page): page.wait_for_selector('#admin-orders-board'); page.wait_for_function("!document.querySelector('.ws-main[aria-busy]')")
def card(page, oid): return page.locator(f'[data-order-card="{oid}"]')
def open_stage(page, stage):
    page.locator(f'#admin-orders-board [data-sb-open="{stage}"]:visible').first.click()
    page.wait_for_selector(f'#admin-orders-board .sb-col.is-open[data-stage="{stage}"]')
DIALOG = '#action-dialog'

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    admin, page = session(browser, 'admin')
    orders = {o['id']: o for o in api(admin, '/admin/orders')}
    def find(status, jobs):
        return next(o['id'] for o in orders.values() if o['status'] == status and len(o['jobs']) == jobs)
    accepted, pair, printing, mixed = find('accepted', 1), find('accepted', 2), find('printing', 1), find('printing', 3)
    ready_one, shipped, completed, cancelled = find('ready', 1), find('shipped', 1), find('completed', 1), find('cancelled', 1)
    ok(orders[accepted]['jobs'][0]['status'] == 'accepted' and orders[ready_one]['jobs'][0]['status'] == 'ready', 'fixture: accepted job, and a job marked ready without a printing report')

    # ---------- Every active order can be cancelled; closed orders cannot ----------
    page.goto(BASE + '/#admin/orders?group=in-progress'); ready(page)
    page.evaluate('window.__sameDocument = 1')
    for oid in (accepted, pair, printing, mixed, ready_one):
        ok(card(page, oid).locator('[data-cancel-order]').count() == 1, f'in production: Cancel order on {orders[oid]["reference"]} ({orders[oid]["status"]})')
    link = card(page, printing).locator('[data-cancel-order]')
    ok(link.evaluate("e => e.classList.contains('wf-link') && e.classList.contains('danger-link')"), 'the card action is a secondary text link in the danger colour')
    open_stage(page, 'shipping')
    ok(card(page, shipped).locator('[data-cancel-order]').count() == 1, 'shipped orders: Cancel order offered (exceptional resolution)')

    # ---------- A job the host reported printing: warning, reason required, in-place update ----------
    open_stage(page, 'in-progress')
    card(page, printing).locator('[data-cancel-order]').click()
    page.wait_for_selector(DIALOG + '[open]')
    d = page.locator(DIALOG)
    ok(d.locator('#ad-title').inner_text() == 'Cancel this order?', 'confirmation dialog opens')
    ok(orders[printing]['reference'] in d.locator('.ac-summary').inner_text(), 'the dialog names the order and its stage')
    ok('Printing reported' in d.locator('.ac-job').inner_text() and 'Will be cancelled' in d.locator('.ac-job').inner_text(), "each product's stage and what cancelling does to it")
    ok('Manufacturing may already have started' in d.locator('.banner.warning').inner_text() and d.locator('.banner.danger').count() == 0, 'production warning; no shipped warning')
    ok(d.locator('input[name=acknowledged]').count() == 0, 'no acknowledgement needed when nothing shipped')
    ok(d.locator('[data-ad-confirm]').evaluate("b => b.classList.contains('danger')"), 'the confirm button is the danger button')
    ok(page.evaluate("document.activeElement === document.querySelector('#cancel-order-form textarea')"), 'focus starts in the reason field')
    d.locator('[data-ad-confirm]').click()
    ok('Give a reason' in d.locator('.ad-error').inner_text() and d.locator('textarea[aria-invalid=true]').count() == 1, 'an empty reason is refused in the dialog')
    ok(next(o for o in api(admin, '/admin/orders') if o['id'] == printing)['status'] == 'printing', 'nothing was sent without a reason')
    page.screenshot(path=str(OUT / 'cancel-printing-1440-light.png'))
    d.locator('textarea').fill('Buyer withdrew the request after a lab move.')
    d.locator('[data-ad-confirm]').click(); page.wait_for_selector(DIALOG, state='hidden')
    page.wait_for_selector('#toast', state='visible'); card(page, printing).wait_for(state='detached'); ready(page)
    ok('cancelled' in page.locator('#toast').inner_text(), 'success message: ' + page.locator('#toast').inner_text())
    ok(card(page, printing).count() == 0 and page.evaluate('window.__sameDocument') == 1, 'the order leaves the active board without a page reload')
    after = next(o for o in api(admin, '/admin/orders') if o['id'] == printing)
    ok(after['status'] == 'cancelled' and after['jobs'][0]['status'] == 'cancelled' and after['jobs'][0]['host_id'], 'order and job cancelled; the host assignment stays on record')
    ok(any(e['action'] == 'order.cancelled' and e['detail'] == 'Buyer withdrew the request after a lab move.' for e in after['history']), 'the reason is recorded in the order history')

    # ---------- From the details dialog: Escape keeps the order; then cancel an accepted job ----------
    card(page, accepted).locator('[data-admin-order]').click(); page.wait_for_selector('#modal[open]')
    page.locator('#modal [data-cancel-order]').click(); page.wait_for_selector(DIALOG + '[open]')
    ok(not page.evaluate("document.querySelector('#modal').open"), 'details close when the cancellation opens')
    ok('Accepted, printing start not reported' in d.locator('.ac-job').inner_text() and d.locator('.banner.warning').count() == 1, 'accepted job: the warning shows even without a printing report')
    page.keyboard.press('Escape'); page.wait_for_selector(DIALOG, state='hidden')
    ok(next(o for o in api(admin, '/admin/orders') if o['id'] == accepted)['status'] == 'accepted', 'Escape cancels nothing')
    ok(page.evaluate(f"document.activeElement?.closest('[data-order-card=\"{accepted}\"]') !== null"), 'focus returns to the order card')
    card(page, accepted).locator('[data-cancel-order]').click(); page.wait_for_selector(DIALOG + '[open]')
    d.locator('textarea').fill('Duplicate of another order.'); d.locator('[data-ad-confirm]').click(); page.wait_for_selector(DIALOG, state='hidden')
    card(page, accepted).wait_for(state='detached'); ready(page)
    ok(card(page, accepted).count() == 0 and next(o for o in api(admin, '/admin/orders') if o['id'] == accepted)['status'] == 'cancelled', 'accepted order cancelled')

    # ---------- Partly shipped: exceptional cancellation needs the acknowledgement ----------
    card(page, mixed).locator('[data-cancel-order]').click(); page.wait_for_selector(DIALOG + '[open]')
    fates = d.locator('.ac-fate').all_inner_texts()
    ok(sorted(fates) == ['Kept as is', 'Will be cancelled', 'Will be cancelled'], 'shipped product kept, the others cancelled: ' + ', '.join(fates))
    ok('Exceptional cancellation' in d.locator('.banner.danger').inner_text() and d.locator('.banner.warning').count() == 1, 'shipped warning and production warning')
    page.screenshot(path=str(OUT / 'cancel-partly-shipped-1440-light.png'))
    d.locator('textarea').fill('Lab closed; buyer keeps the rack already delivered.')
    d.locator('[data-ad-confirm]').click()
    ok('Confirm that shipped' in d.locator('.ad-error').inner_text() and page.evaluate(f"document.querySelector('{DIALOG}').open"), 'refused until the shipped products are acknowledged')
    d.locator('input[name=acknowledged]').check(); d.locator('[data-ad-confirm]').click(); page.wait_for_selector(DIALOG, state='hidden')
    card(page, mixed).wait_for(state='detached'); ready(page)
    after = next(o for o in api(admin, '/admin/orders') if o['id'] == mixed)
    ok(after['status'] == 'cancelled' and sorted(j['status'] for j in after['jobs']) == ['cancelled', 'cancelled', 'shipped'], 'only the unshipped jobs are cancelled')
    ok(next(j for j in after['jobs'] if j['status'] == 'shipped')['shipment']['tracking_number'], 'the shipment record is kept')

    # ---------- Changed meanwhile: the host ships while the dialog is open ----------
    host, _ = session(browser, 'host')
    card(page, ready_one).locator('[data-cancel-order]').click(); page.wait_for_selector(DIALOG + '[open]')
    job = orders[ready_one]['jobs'][0]['id']
    shipped_now = host.request.post(f'{BASE}/api/host/jobs/{job}/status', data={'status': 'shipped', 'carrier': 'DHL', 'tracking_number': 'RACE1'}, headers={'x-csrf-token': host.csrf})
    ok(shipped_now.ok, 'host ships the job while the dialog is open')
    d.locator('textarea').fill('Buyer cancelled by phone.'); d.locator('[data-ad-confirm]').click()
    page.wait_for_function(f"document.querySelector('{DIALOG} .ad-error').textContent.length > 0")
    ok('already shipped' in d.locator('.ad-error').inner_text(), 'the conflict is explained in the dialog: ' + d.locator('.ad-error').inner_text())
    ok(next(o for o in api(admin, '/admin/orders') if o['id'] == ready_one)['status'] == 'shipped', 'nothing was cancelled behind the shipment')
    d.locator('.ad-foot [data-ad-cancel]').click(); page.wait_for_selector(DIALOG, state='hidden')
    page.wait_for_selector(f'.sb-col[data-stage="shipping"] [data-order-card="{ready_one}"]', state='attached', timeout=10000); ready(page)
    ok(page.locator(f'.sb-col[data-stage="in-progress"] [data-order-card="{ready_one}"]').count() == 0, 'the board refreshes on close: the order is now in Shipping')

    # ---------- History: cancelled orders, with the reason in Details; no cancel action ----------
    page.goto(BASE + '/#admin/orders?scope=history&group=cancelled')
    page.wait_for_selector(f'.sb-col.is-open[data-stage="cancelled"] [data-order-card="{printing}"]'); ready(page)
    for oid in (printing, accepted, mixed, cancelled):
        ok(card(page, oid).count() == 1, f'Order history lists {orders[oid]["reference"]}')
    ok(page.locator('#admin-orders-board [data-cancel-order]').count() == 0, 'no Cancel order in history')
    card(page, printing).locator('[data-admin-order]').click(); page.wait_for_selector('#modal[open]')
    ok('Buyer withdrew the request after a lab move.' in page.locator('#modal .bo-history').inner_text(), 'the reason shows in the order history for administrators')
    ok('Cancelled by an administrator while printing' in page.locator('#modal .bo-history').inner_text(), 'where the job was is recorded')
    page.keyboard.press('Escape')
    open_stage(page, 'completed')
    ok(card(page, completed).locator('[data-cancel-order]').count() == 0, 'completed orders cannot be cancelled')

    # ---------- Host and buyer: cancelled work leaves the active views and stays in history ----------
    hp = host.new_page(); hp.on('pageerror', lambda e: errors.append(f'host: {e}'))
    hp.goto(BASE + '/#host/jobs'); hp.wait_for_selector('[data-stage-board]'); hp.wait_for_function("!document.querySelector('.ws-main[aria-busy]')")
    gone = [j['id'] for oid in (printing, accepted) for j in orders[oid]['jobs']]
    ok(all(hp.locator(f'[data-job-card="{j}"]').count() == 0 for j in gone), 'host: cancelled jobs are off the Printing jobs board')
    hp.goto(BASE + '/#host/jobs?scope=history&group=cancelled'); hp.wait_for_function("!document.querySelector('.ws-main[aria-busy]')")
    hp.wait_for_selector('[data-job-card]', state='attached')
    ok(all(hp.locator(f'[data-job-card="{j}"]').count() == 1 for j in gone), 'host: they are in Job history')
    buyer, bp = session(browser, 'buyer')
    current = {o['id'] for o in api(buyer, '/orders?paginated=true&scope=active&per_page=50')['items']}
    previous = {o['id'] for o in api(buyer, '/orders?paginated=true&scope=history&group=cancelled&per_page=50')['items']}
    ok(not {printing, accepted, mixed} & current and {printing, accepted, mixed} <= previous, 'buyer: cancelled orders moved to Previous orders')
    ok(all('detail' not in e for o in api(buyer, '/orders') for e in o['history']), "buyer: administrators' notes are not exposed")

    # ---------- Mobile, dark: the dialog fits ----------
    for w, theme in ((390, 'dark'), (1440, 'dark'), (390, 'light')):
        ctx, mp = session(browser, 'admin', w, 844 if w == 390 else 900, theme)
        mp.goto(BASE + '/#admin/orders?group=in-progress'); ready(mp)
        mp.locator(f'[data-order-card="{pair}"] [data-cancel-order]').click(); mp.wait_for_selector(DIALOG + '[open]')
        box = mp.locator(DIALOG).bounding_box()
        ok(box['x'] >= 0 and box['x'] + box['width'] <= w + 0.5 and box['height'] <= mp.viewport_size['height'], f'{w} {theme}: the dialog fits the screen')
        ok(overflow(mp) <= 0, f'{w} {theme}: no horizontal overflow')
        foot = mp.locator(DIALOG + ' .ad-foot [data-ad-confirm]').bounding_box()
        ok(foot['y'] + foot['height'] <= mp.viewport_size['height'], f'{w} {theme}: the confirm button is reachable')
        mp.screenshot(path=str(OUT / f'cancel-dialog-{w}-{theme}.png'))
        ctx.close()

    ok(not errors, 'no page errors: ' + '; '.join(errors[:5]))
    browser.close()

print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
