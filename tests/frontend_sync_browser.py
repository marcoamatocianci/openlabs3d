"""The page follows the server when someone else changes things while it is open: a refused action leaves the board
showing what the server now says, in place and without reloading the page. Mutates the workflow fixture (restart it
afterwards).
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/frontend_sync_browser.py [BASE_URL]"""
import os, sys
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
class Actor:
    def __init__(self, browser, who):
        self.ctx = browser.new_context(viewport={'width': 1366, 'height': 900})
        r = self.ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}); assert r.ok
        self.csrf = r.json()['csrf_token']; self.p = None
    def get(self, path):
        r = self.ctx.request.get(BASE + '/api' + path); assert r.ok, (path, r.status); return r.json()
    def post(self, path, body=None):
        return self.ctx.request.post(BASE + '/api' + path, data=body or {}, headers={'X-CSRF-Token': self.csrf})
    def open(self, route):
        self.p = self.p or self.ctx.new_page()
        self.p.on('pageerror', lambda e: errors.append(str(e)))
        self.p.goto(f'{BASE}/#{route}'); settled(self.p); self.p.evaluate('window.__same_document = true'); return self.p
def settled(p, ms=300): p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)
def same_document(p): return p.evaluate('window.__same_document === true')
def stage_counts(p, board):
    return p.evaluate(f"Object.fromEntries([...document.querySelectorAll('{board} .sb-col')].map(c => [c.dataset.stage, +c.dataset.count]))")
def board_matches_server(p, board, data):
    server = {g['key']: g['count'] for g in data['scopes']['active']['groups']}
    return stage_counts(p, board) == server, stage_counts(p, board), server

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    host, admin, buyer = (Actor(browser, w) for w in ('host', 'admin', 'buyer'))

    # An available job that goes away while this host is looking at it.
    p = host.open('host/jobs?group=available')
    job = next(j for j in host.get('/host/jobs?scope=active')['items'] if j['status'] == 'available')
    r = admin.post(f"/admin/orders/{job['order_id']}/cancel", {'reason': 'Changed while the host was looking', 'shipped_acknowledged': True}); assert r.ok, r.text()
    card = p.locator(f'[data-job-card="{job["id"]}"]')
    ok(card.count() == 1, 'the page still shows the job that just went away')
    card.locator('[data-job]').first.click(); p.wait_for_selector('dialog[open]'); p.locator('dialog[open] [data-ad-confirm]').click(); p.wait_for_timeout(350)
    ok(p.locator('#action-dialog .ad-error').inner_text().strip() != '', 'accepting it is refused, with the reason in the dialog')
    p.locator('dialog[open] [data-ad-cancel]').first.click(); settled(p)
    ok(p.locator(f'[data-job-card="{job["id"]}"]').count() == 0, 'closing the dialog removes the job from the page')
    same, shown, server = board_matches_server(p, '#host-jobs-board', host.get('/host/jobs?scope=active'))
    ok(same, f'every stage count matches the server {shown} {server}'); ok(same_document(p), 'without reloading the page')

    # An order cancelled by an administrator while its host holds the job.
    job = next(j for j in host.get('/host/jobs?scope=active')['items'] if j['status'] in ('accepted', 'printing') and j['host_id'])
    p = host.open('host/jobs?group=in-production')
    r = admin.post(f"/admin/orders/{job['order_id']}/cancel", {'reason': 'Changed while the host was looking', 'shipped_acknowledged': True}); assert r.ok, r.text()
    ok(p.locator(f'[data-job-card="{job["id"]}"]').count() == 1, 'the page still shows the job of the order just cancelled')
    p.locator(f'[data-job-card="{job["id"]}"] [data-job]').first.click(); p.wait_for_selector('dialog[open]'); p.locator('dialog[open] [data-ad-confirm]').click(); p.wait_for_timeout(350)
    ok(p.locator('#action-dialog .ad-error').inner_text().strip() != '', 'the next step is refused, with the reason in the dialog')
    p.locator('dialog[open] [data-ad-cancel]').first.click(); settled(p)
    ok(p.locator(f'#host-jobs-board .sb-col[data-stage="in-production"] [data-job-card="{job["id"]}"]').count() == 0, 'closing the dialog takes the cancelled job out of In production')
    same, shown, server = board_matches_server(p, '#host-jobs-board', host.get('/host/jobs?scope=active'))
    ok(same, f'every stage count matches the server {shown} {server}'); ok(same_document(p), 'without reloading the page')

    # A delivery the buyer already confirmed in another tab.
    data = buyer.get('/orders?paginated=true&scope=active&per_page=50')
    order = next((o for o in data['items'] if any(j['status'] == 'shipped' for j in o['jobs'])), None)
    ok(order is not None, 'the fixture has an order on its way to the buyer')
    target = next(j for j in order['jobs'] if j['status'] == 'shipped')
    p = buyer.open('orders?group=shipping')
    assert buyer.post(f"/orders/{order['id']}/jobs/{target['id']}/received").ok
    button = p.locator(f'[data-received="{order["id"]}:{target["id"]}"]').first
    ok(button.count() == 1, 'the page still offers Mark as received')
    button.click(); p.wait_for_selector('dialog[open]'); p.locator('dialog[open] [data-ad-confirm]').click(); p.wait_for_timeout(350)
    if p.locator('dialog[open]').count(): p.locator('dialog[open] [data-ad-cancel]').first.click()
    settled(p)
    fresh = buyer.get('/orders?paginated=true&scope=active&per_page=50')
    same, shown, server = board_matches_server(p, '#bo-board', fresh)
    ok(same, f'after it, every stage count matches the server {shown} {server}')
    ok(p.locator(f'[data-received="{order["id"]}:{target["id"]}"]').count() == 0, 'Mark as received is no longer offered for that product'); ok(same_document(p), 'without reloading the page')

    # An order a host accepts while its buyer is deleting it.
    pending = next(o for o in buyer.get('/orders?paginated=true&scope=active&per_page=50')['items'] if o['status'] == 'pending' and all(j['status'] == 'available' for j in o['jobs']))
    p = buyer.open('orders?group=pending')
    r = host.post(f"/host/jobs/{pending['jobs'][0]['id']}/accept"); assert r.ok, r.text()
    p.locator(f'[data-order-details="{pending["id"]}"]').first.click(); p.wait_for_selector('#modal[open]')
    p.locator(f'#modal [data-delete-order="{pending["id"]}"]').click(); p.wait_for_selector('#action-dialog[open]'); p.locator('#action-dialog [data-ad-confirm]').click(); p.wait_for_timeout(350)
    ok(p.locator('#action-dialog .ad-error').inner_text().strip() != '', 'deleting the order a host just accepted is refused, with the reason')
    p.locator('#action-dialog [data-ad-cancel]').first.click(); settled(p)
    ok(p.locator(f'#modal [data-delete-order="{pending["id"]}"]').count() == 0, 'its details no longer offer Delete')
    if p.locator('#modal[open]').count(): p.keyboard.press('Escape'); settled(p, 100)
    same, shown, server = board_matches_server(p, '#bo-board', buyer.get('/orders?paginated=true&scope=active&per_page=50'))
    ok(same, f'every stage count matches the server {shown} {server}'); ok(same_document(p), 'without reloading the page')

    # Shipped by the host while the buyer's page is open: the next visit to the page reads the server again.
    data = host.get('/host/jobs?scope=active')
    p = admin.open('admin/orders?group=in-progress'); before = stage_counts(p, '#admin-orders-board')
    held = next(j for j in data['items'] if j['status'] == 'ready' and j['host_id'])
    assert host.post(f"/host/jobs/{held['id']}/status", {'status': 'shipped', 'carrier': 'Courier', 'tracking_number': 'SYNC1'}).ok
    p.evaluate("location.hash = '#admin/users'"); settled(p); p.evaluate("location.hash = '#admin/orders?group=in-progress'"); settled(p)
    same, shown, server = board_matches_server(p, '#admin-orders-board', admin.get('/admin/orders?paginated=true&scope=active&per_page=1'))
    ok(same, f'returning to the admin board shows the server state {shown} {server}'); ok(same_document(p), 'without reloading the page')
    browser.close()
ok(not errors, 'no page errors: ' + '; '.join(errors[:3]))
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
