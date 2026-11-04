"""An action must not throw away where the reader was: depth loaded, search, sort, open stage, scroll. Against the
workflow fixture, with real orders and jobs placed through the API (this suite changes the fixture).
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/pagination_state_browser.py [BASE_URL]"""
import os, sys
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
DIALOG = '#section-dialog'
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
def session(browser, who, w=1366, h=900):
    ctx = browser.new_context(viewport={'width': w, 'height': h})
    login = ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}); assert login.ok
    ctx.csrf = login.json()['csrf_token']; p = ctx.new_page(); p.api = []
    p.on('pageerror', lambda e: errors.append(str(e)))
    p.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(m.text))
    p.on('request', lambda r: '/api/' in r.url and r.resource_type in ('fetch', 'xhr') and '/visuals/' not in r.url and p.api.append((r.method, r.url.split('/api/')[1])))
    return ctx, p
def settled(p, ms=250):
    p.wait_for_function("!document.querySelector('.ws-main[aria-busy], #bo-results[aria-busy=true], #section-dialog .ss-body[aria-busy]')"); p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)
def post(ctx, path, data=None): return ctx.request.post(f'{BASE}/api/{path}', data=data or {}, headers={'x-csrf-token': ctx.csrf})
def confirm(p): p.wait_for_selector('#action-dialog[open]'); p.locator('#action-dialog [data-ad-confirm]').click(); p.wait_for_selector('#action-dialog', state='hidden')
def cards(p, attr, scope=DIALOG): return p.evaluate("([s, a]) => [...document.querySelectorAll(s + ' [' + a + ']')].filter(e => e.checkVisibility()).map(e => +e.getAttribute(a))", [scope, attr])

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    buyer, _ = session(browser, 'buyer'); host, h = session(browser, 'host'); admin, a = session(browser, 'admin')
    listing = buyer.request.get(BASE + '/api/listings?per_page=12').json()['items'][0]
    offer = buyer.request.get(f'{BASE}/api/listings/{listing["id"]}/availability').json()
    material = next(iter(offer['materials'])); color = next(iter(offer['colors_by_material'][material])); line = {'listing_id': listing['id'], 'material': material, 'color': color, 'quantity': 1}
    price = post(buyer, f'listings/{listing["id"]}/quote', {'material': material, 'color': color, 'quantity': 1}).json()['unit_price_cents']
    contact = {'first_name': 'Q', 'last_name': 'A', 'phone': '+39 011 1234567', 'street': 'Via QA 1', 'city': 'Torino', 'country': 'IT', 'postal_code': '10100', 'region': 'Piedmont'}
    def place(n, tag):
        made = []
        for k in range(n):
            r = post(buyer, 'checkout', {'contact': contact, 'direct': line, 'confirmed': [{**line, 'unit_price_cents': price}], 'idempotency_key': f'depth-{tag}-{k}-{os.getpid()}'}); assert r.ok, r.text()
            made.append(r.json())
        return made
    production = place(30, 'host')
    for order in production: assert post(host, f'host/jobs/{order["jobs"][0]["id"]}/accept').ok
    pending = place(30, 'admin')

    # ---------- Printing jobs, the popup: 30+ jobs, an action far down the list ----------
    h.goto(BASE + '/#host/jobs?group=in-production'); h.wait_for_selector('#host-jobs-board'); settled(h)
    h.locator('.sb-col.is-open [data-sb-expand]').click(); h.wait_for_selector(DIALOG + '[open]'); settled(h)
    total = int(h.locator(DIALOG + ' #ss-count').inner_text().split()[0]); h.evaluate("document.querySelector('[data-select=ss-sort]') && uiSelectSet(document.querySelector('[data-select=ss-sort]'), 'oldest')"); h.wait_for_timeout(150)
    h.locator(DIALOG + ' [data-ss-more]').click(); h.wait_for_function(f"document.querySelectorAll('{DIALOG} [data-job-card]').length === {total}")
    before = cards(h, 'data-job-card'); target = before[-5]
    h.locator(f'{DIALOG} [data-job-card="{target}"]').scroll_into_view_if_needed(); scroll = h.evaluate(f"document.querySelector('{DIALOG} .ss-body').scrollTop"); h.api.clear()
    h.locator(f'{DIALOG} [data-job="{target}"]').click(); confirm(h)
    h.wait_for_function(f"!document.querySelector('{DIALOG} [data-job-card=\"{target}\"]')"); settled(h)
    after = cards(h, 'data-job-card')
    ok(len(after) == total - 1, f'{total} jobs loaded; one moves on: {len(after)} still showing, not the first 24')
    ok(after == [j for j in before if j != target], 'in the same order: the chosen sort survives')
    ok(h.evaluate("document.querySelector('[data-select=ss-sort] input[type=hidden]').value") == 'oldest', 'the sort control still says Oldest')
    ok(abs(h.evaluate(f"document.querySelector('{DIALOG} .ss-body').scrollTop") - scroll) < 200, 'the scroll position stays about where it was')
    ok(h.evaluate(f"!!document.activeElement.closest('{DIALOG} [data-job-card]')"), 'focus is on a nearby card')
    ok(sum(1 for m, u in h.api if m == 'GET' and u.startswith('host/jobs?scope=active') and 'group' not in u) == 1, f'one read to refresh {[u for m, u in h.api if m == "GET"]}')
    # A search inside the popup survives an action as well.
    h.fill(DIALOG + ' #ss-q', listing['title'][:6]); h.wait_for_timeout(350); matches = cards(h, 'data-job-card'); h.locator(f'{DIALOG} [data-job="{matches[0]}"]').click(); confirm(h)
    h.wait_for_function(f"!document.querySelector('{DIALOG} [data-job-card=\"{matches[0]}\"]')"); settled(h)
    ok(h.input_value(DIALOG + ' #ss-q') == listing['title'][:6] and 'of' in h.locator(DIALOG + ' #ss-count').inner_text(), 'the popup’s search survives an action')
    h.locator(DIALOG + ' [data-ss-close]').click(); h.wait_for_selector(DIALOG, state='hidden')

    # ---------- Printing jobs, the board: the page's search survives an action ----------
    field = '[data-filter-list="host-jobs-search"]'
    h.fill(field, listing['title'][:6]); shown = cards(h, 'data-job-card', '#host-jobs-board .sb-col.is-open')
    h.locator(f'#host-jobs-board .sb-col.is-open [data-job="{shown[0]}"]').click(); confirm(h)
    h.wait_for_function(f"!document.querySelector('#host-jobs-board .sb-col.is-open [data-job-card=\"{shown[0]}\"]')"); settled(h)
    ok(h.input_value(field) == listing['title'][:6], 'the page’s search box keeps what was typed after an action')
    ok(cards(h, 'data-job-card', '#host-jobs-board .sb-col.is-open') == shown[1:] and h.locator('#host-jobs-board').get_attribute('data-open') == 'in-production', 'and the same filtered list, in the same open stage')
    counts = h.evaluate("Object.fromEntries([...document.querySelectorAll('#host-jobs-board .sb-col')].map(c => [c.dataset.stage, c.querySelector('.sb-head [data-sb-count]').textContent]))")
    ok(int(counts['in-production']) == len(shown) - 1, f'its count still shows the matches {counts}')
    h.fill(field, ''); settled(h, 80)
    # The all-collapsed board stays collapsed through a refresh.
    h.locator('#host-jobs-board .sb-col.is-open .sb-head').click(); h.wait_for_timeout(420); h.evaluate('render()'); settled(h)
    ok(h.locator('#host-jobs-board').get_attribute('data-open') == 'none', 'a refresh keeps the all-collapsed board collapsed')

    # ---------- Admin orders: a paged stage, depth loaded, an order cancelled from deep in it ----------
    a.goto(BASE + '/#admin/orders?group=pending'); a.wait_for_selector('#admin-orders-board'); settled(a)
    stage = '#admin-orders-board .sb-col.is-open'; total = int(a.locator(stage + ' .sb-head [data-sb-count]').inner_text())
    ok(len(cards(a, 'data-order-card', stage)) == 12 and total > 24, f'pending: 12 of {total} first')
    a.locator(stage + ' [data-sb-more]').click(); a.wait_for_function("s => document.querySelectorAll(s + ' [data-order-card]').length === 24", arg=stage); settled(a)
    before = cards(a, 'data-order-card', stage); target = before[-2]; a.api.clear()
    a.locator(f'{stage} [data-cancel-order="{target}"]').click(); a.wait_for_selector('#action-dialog[open]'); a.fill('#cancel-order-form textarea', 'Depth check'); confirm(a)
    a.wait_for_function(f"!document.querySelector('{stage} [data-order-card=\"{target}\"]')"); settled(a)
    after = cards(a, 'data-order-card', stage)
    ok(len(after) == 24, f'still 24 showing after cancelling the 23rd, the gap filled by the next order ({len(after)})')
    ok(after[:22] == [o for o in before if o != target][:22] and target not in after, 'in the same order, without the cancelled one')
    reads = [u for m, u in a.api if m == 'GET' and u.startswith('admin/orders?') and 'columns=true' in u]
    ok(len(reads) == 1 and 'per_page=24' in reads[0], f'one read, for exactly that depth {reads}')
    a.locator(stage + ' [data-sb-more]').click(); settled(a)
    more = cards(a, 'data-order-card', stage)
    ok(len(more) == min(total - 1, 48) and len(set(more)) == len(more) and more[:24] == after, f'Load more continues without gaps or repeats ({len(more)})')
    # The popup and the board share that depth.
    a.locator(stage + ' [data-sb-expand]').click(); a.wait_for_selector(DIALOG + '[open]'); settled(a)
    ok(len(cards(a, 'data-order-card')) == min(24, len(more)) or len(cards(a, 'data-order-card')) >= 24, 'the popup opens with what the board has loaded')
    a.locator(DIALOG + ' [data-ss-close]').click(); a.wait_for_selector(DIALOG, state='hidden')
    # Another list starts from its own first page.
    a.evaluate("location.hash = '#admin/orders?scope=history&group=cancelled'"); a.wait_for_selector(stage + '[data-stage="cancelled"]'); settled(a)
    ok(len(cards(a, 'data-order-card', stage)) <= 12, 'Order history starts from its own first page: depth is per list')
    a.evaluate("location.hash = '#admin/orders?group=pending'"); a.wait_for_selector(stage + '[data-stage="pending"]'); settled(a)
    ok(len(cards(a, 'data-order-card', stage)) == len(more), 'returning to the active list keeps how far it was loaded')

    # ---------- Previous orders: the same depth through a redraw ----------
    for order in pending[:16]:
        if order['id'] != target: post(admin, f'admin/orders/{order["id"]}/cancel', {'reason': 'History depth check'})
    ctx, b = session(browser, 'buyer'); b.goto(BASE + '/#orders?scope=history&group=cancelled'); b.wait_for_selector('#bo-history-board'); settled(b)
    stage = '#bo-history-board .sb-col.is-open'
    b.locator(stage + ' [data-sb-more]').click(); b.wait_for_function("s => document.querySelectorAll(s + ' [data-order-id]').length > 12", arg=stage); settled(b)
    deep = cards(b, 'data-order-id', stage); b.evaluate('renderBuyerOrders()'); settled(b)
    ok(cards(b, 'data-order-id', stage) == deep and len(deep) > 12, f'Previous orders: a redraw keeps the {len(deep)} orders loaded')
    ctx.close()
    ok(not errors, 'no page errors: ' + '; '.join(errors[:4]))
    browser.close()
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
