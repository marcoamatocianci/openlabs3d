"""Expand section: the open stage's items in a large dialog, on every kind of stage board, against the isolated
workflow fixture. Real jobs and orders move through real actions (this suite changes the fixture; restart it
first). Layouts with many items rewrite the host's real response in the browser.
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/section_modal_browser.py OUTPUT_DIR [BASE_URL]"""
import copy, os, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
DIALOG = '#section-dialog'
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)

def session(browser, who, w=1440, h=900, theme='light', touch=False, motion='no-preference', counts=None):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme, has_touch=touch, is_mobile=touch, reduced_motion=motion)
    login = ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}); assert login.ok
    ctx.csrf = login.json()['csrf_token']
    if counts:
        def rewrite(route):
            response = route.fetch(); data = response.json(); groups = data['scopes']['active']['groups']
            templates = {g['key']: next((j for j in data['items'] if j['status'] in g['statuses']), data['items'][0]) for g in groups}
            items, next_id = [], 900000
            for g, n in zip(groups, counts):
                g['count'] = n
                for k in range(n):
                    item = copy.deepcopy(templates[g['key']]); item['id'] = next_id; next_id += 1; item['status'] = g['statuses'][0]
                    item['item']['title'] = f'{g["key"]} rack {k + 1:03d}'; items.append(item)
            data['items'] = items; data['total'] = data['per_page'] = len(items); data['scopes']['active']['total'] = len(items)
            route.fulfill(response=response, json=data)
        ctx.route(re.compile(r'/api/host/jobs\?scope=active$'), rewrite)
    page = ctx.new_page(); page.api = []
    page.on('pageerror', lambda e: errors.append(f'{who} {w}: {e}'))
    # A refused request is logged by the browser; suites that provoke one say so.
    page.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(f'{who} {w}: {m.text}'))
    page.on('dialog', lambda d: (errors.append('native dialog: ' + d.message), d.dismiss()))
    page.on('request', lambda r: '/api/' in r.url and page.api.append((r.method, r.url.split('/api/')[1])))
    return ctx, page

def settled(page): page.wait_for_function("!document.querySelector('.ws-main[aria-busy], #bo-results[aria-busy=true], #section-dialog .ss-body[aria-busy]')")
def go(page, hash_, board):
    page.goto(BASE + '/#' + hash_); page.wait_for_selector(board); settled(page)
def expand(page):
    page.locator('[data-stage-board] .sb-col.is-open [data-sb-expand]').click(); page.wait_for_selector(DIALOG + '[open]')
def close(page):
    page.locator(DIALOG + ' [data-ss-close]').click(); page.wait_for_selector(DIALOG, state='hidden')
def confirm(page):
    page.wait_for_selector('#action-dialog[open]'); page.locator('#action-dialog [data-ad-confirm]').click(); page.wait_for_selector('#action-dialog', state='hidden')
def ids(page, attr, scope=DIALOG): return page.evaluate("([s, a]) => [...document.querySelectorAll(s + ' [' + a + ']')].map(e => +e.getAttribute(a))", [scope, attr])
def count_text(page): return page.locator(DIALOG + ' #ss-count').inner_text()
def is_open(page, sel=DIALOG): return page.evaluate("s => !!document.querySelector(s)?.open", sel)
def focus_inside(page): return page.evaluate("s => { const d = document.querySelector(s), a = document.activeElement; return !!d && d.contains(a) && a !== d; }", DIALOG)
def sort_by(page, key): page.evaluate("k => uiSelectSet(document.querySelector('[data-select=ss-sort]'), k)", key)
def wait_cards(page, n, attr): page.wait_for_function("([d, a, n]) => document.querySelectorAll(d + ' [' + a + ']').length === n", arg=[DIALOG, attr, n])
JOBS = lambda ctx: ctx.request.get(BASE + '/api/host/jobs?scope=active').json()

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)

    # ---------- Expand section: only on the open stage; two distinct steps ----------
    host, p = session(browser, 'host')
    data = JOBS(host); groups = {g['key']: g for g in data['scopes']['active']['groups']}
    of = lambda key, items=None: [j for j in (items or data['items']) if j['status'] in groups[key]['statuses']]
    go(p, 'host/jobs?group=in-production', '#host-jobs-board'); p.evaluate('window.__same = 1')
    visible = p.evaluate("[...document.querySelectorAll('[data-sb-expand]')].filter(b => b.checkVisibility()).map(b => b.dataset.sbExpand)")
    ok(visible == ['in-production'], f'Expand section appears only on the open stage {visible}')
    ok(p.evaluate("[...document.querySelectorAll('.sb-mosaic [data-sb-expand]')].every(b => !b.checkVisibility())"), 'no collapsed panel offers it')
    label = p.locator('.sb-col.is-open [data-sb-expand]')
    ok('Expand section' in label.inner_text() and label.get_attribute('aria-haspopup') == 'dialog' and 'In production' in label.get_attribute('aria-label'), 'it is labelled, and announces a dialog')
    p.locator('.sb-mosaic [data-sb-open="available"]').click(); p.wait_for_timeout(400)
    ok(not is_open(p) and p.locator('.sb-col.is-open').get_attribute('data-stage') == 'available', 'first click: a collapsed stage expands in the board, and no dialog opens')
    ok(p.evaluate("[...document.querySelectorAll('[data-sb-expand]')].filter(b => b.checkVisibility()).map(b => b.dataset.sbExpand)") == ['available'], 'the action follows the open stage')

    # ---------- The dialog: right stage, no request, proper modal ----------
    p.api.clear(); expand(p); p.wait_for_timeout(280)
    ok(is_open(p) and p.locator(DIALOG + ' #ss-title').inner_text() == 'Available', 'second click: the dialog opens on that stage')
    ok(not p.api, f'opening it makes no request {p.api}')
    wanted = [j['id'] for j in of('available')]
    ok(sorted(ids(p, 'data-job-card')) == sorted(wanted), f'it shows every job of the stage {ids(p, "data-job-card")}')
    ok(count_text(p) == f'{len(wanted)} manufacturing job{"" if len(wanted) == 1 else "s"}', 'its count: ' + count_text(p))
    box = p.locator(DIALOG).bounding_box()
    ok(.85 <= box['width'] / 1440 <= .95 and box['height'] / 900 >= .85, f'about 92% of the screen ({box["width"]:.0f} × {box["height"]:.0f})')
    ok(p.evaluate("(() => { const d = document.querySelector('#section-dialog'); return d.matches(':modal') && d.getAttribute('aria-labelledby') === 'ss-title' && d.getAttribute('aria-describedby') === 'ss-count' && !!document.getElementById('ss-title'); })()"), 'native modal dialog, labelled and described')
    ok(p.evaluate("document.activeElement.id") == 'ss-q', 'focus starts in the search field')
    start = p.evaluate('scrollY'); p.mouse.move(8, 8); p.mouse.wheel(0, 500); p.wait_for_timeout(120)
    ok(p.evaluate("getComputedStyle(document.documentElement).overflow") == 'hidden' and p.evaluate('scrollY') == start, 'the page behind cannot scroll')
    ok(p.evaluate("(() => { const seen = new Set(), dup = []; document.querySelectorAll('[id]').forEach(e => { if (seen.has(e.id)) dup.push(e.id); seen.add(e.id); }); return dup; })()") == [], 'no duplicate ids between the dialog and the board')
    inside = True
    for _ in range(24): p.keyboard.press('Tab'); inside = inside and focus_inside(p)
    ok(inside, 'Tab cycles inside the dialog')
    p.evaluate("document.querySelector('#section-dialog [data-ss-close]').focus()"); p.keyboard.press('Shift+Tab')
    ok(focus_inside(p), 'Shift+Tab stays inside too')
    p.keyboard.press('Escape'); p.wait_for_selector(DIALOG, state='hidden')
    ok(p.evaluate("document.activeElement.matches('.sb-col.is-open [data-sb-expand]')"), 'Escape closes it; focus returns to Expand section')
    ok(p.evaluate("getComputedStyle(document.documentElement).overflow") != 'hidden', 'the page can scroll again')
    expand(p); close(p)
    ok(p.evaluate("document.activeElement.matches('.sb-col.is-open [data-sb-expand]')"), 'so does the close button')
    expand(p); p.wait_for_timeout(250); p.mouse.click(8, 8); p.wait_for_selector(DIALOG, state='hidden')
    ok(not is_open(p), 'so does a click on the dimmed page')

    # ---------- Search and sort, locally: no request ----------
    p.locator('.sb-mosaic [data-sb-open="in-production"]').click(); p.wait_for_timeout(350)
    p.api.clear(); expand(p)
    production = of('in-production'); total = len(production)
    p.fill(DIALOG + ' #ss-q', 'microtube'); p.wait_for_timeout(350)
    matching = [j['id'] for j in production if 'microtube' in j['item']['title'].lower()]
    ok(sorted(ids(p, 'data-job-card')) == sorted(matching) and count_text(p) == f'{len(matching)} of {total} manufacturing jobs', f'search filters the cards: {count_text(p)}')
    p.fill(DIALOG + ' #ss-q', 'no such product'); p.wait_for_timeout(350)
    ok(not ids(p, 'data-job-card') and 'matches “no such product”' in p.locator(DIALOG + ' .ss-empty').inner_text(), 'no match says so')
    p.keyboard.press('Escape'); p.wait_for_timeout(350)
    ok(len(ids(p, 'data-job-card')) == total and count_text(p) == f'{total} manufacturing jobs' and is_open(p) and p.input_value(DIALOG + ' #ss-q') == '', 'with text in the search, Escape clears it (every job back) and keeps the dialog open')
    trigger = p.locator(DIALOG + ' [data-select=ss-sort] .cf-trigger'); trigger.click()
    options = p.locator(DIALOG + ' [data-select=ss-sort] [role=option]').all_inner_texts()
    ok(options == ['Most recent', 'Oldest', 'Longest in this stage', 'Order reference'], f'sort options {options}')
    p.keyboard.press('Escape'); p.wait_for_timeout(120)
    ok(is_open(p) and not p.locator(DIALOG + ' [data-select=ss-sort] [role=option]').first.is_visible(), 'Escape closes the open dropdown, not the dialog')
    orders = {'recent': sorted(production, key=lambda j: -j['id']), 'oldest': sorted(production, key=lambda j: j['id']),
              'stage': sorted(production, key=lambda j: j['updated_at']), 'reference': sorted(production, key=lambda j: j['order_reference'])}
    for key, order in orders.items():
        sort_by(p, key); p.wait_for_timeout(120)
        drawn = ids(p, 'data-job-card')
        if key == 'reference': ok(p.evaluate("[...document.querySelectorAll('#section-dialog [data-job-card]')].map(c => c.querySelector('.jc-spec:last-of-type')?.textContent || '')") and [next(j['order_reference'] for j in production if j['id'] == i) for i in drawn] == [j['order_reference'] for j in order], 'sort: order reference')
        else: ok(drawn == [j['id'] for j in order], f'sort: {key} {drawn}')
    ok(not p.api, f'search and sort of a complete stage make no request {p.api}')
    sort_by(p, 'recent'); close(p)

    # ---------- Details: one controlled dialog above, focus and scroll kept ----------
    expand(p); first = ids(p, 'data-job-details')[0]
    details = p.locator(f'{DIALOG} [data-job-details="{first}"]'); details.click(); p.wait_for_selector('#modal[open]')
    ok(is_open(p) and p.evaluate("[...document.querySelectorAll('dialog[open]')].length") == 2, 'Details opens above the section, which stays where it was')
    ok('0.28' in p.evaluate("getComputedStyle(document.querySelector('#modal'), '::backdrop').backgroundColor") and p.evaluate("getComputedStyle(document.querySelector('#modal'), '::backdrop').backdropFilter") == 'none', 'under a lighter scrim: one dimmed page, no second blur')
    p.screenshot(path=str(OUT / 'details-above-section-1440.png'))
    p.keyboard.press('Escape'); p.wait_for_selector('#modal', state='hidden')
    ok(is_open(p) and p.evaluate(f"document.activeElement.matches('{DIALOG} [data-job-details=\"{first}\"]')"), 'Escape closes Details only; focus returns to its button in the section')
    close(p)

    # ---------- Actions: the board and the dialog stay in step ----------
    p.locator('.sb-mosaic [data-sb-open="available"]').click(); p.wait_for_timeout(350)
    expand(p); before = ids(p, 'data-job-card'); job = before[0]
    button = p.locator(f'{DIALOG} [data-job="{job}"]'); button.click(); p.wait_for_selector('#action-dialog[open]')
    p.keyboard.press('Escape'); p.wait_for_selector('#action-dialog', state='hidden')
    ok(p.evaluate(f"document.activeElement.matches('{DIALOG} [data-job=\"{job}\"]')") and is_open(p), 'cancelling the step returns focus to its button')
    p.api.clear(); button.click(); confirm(p)
    wait_cards(p, len(before) - 1, 'data-job-card')
    ok(job not in ids(p, 'data-job-card') and count_text(p) == f'{len(before) - 1} manufacturing job{"" if len(before) == 2 else "s"}', f'accepted: the job leaves the Available section, and its count follows ({count_text(p)})')
    settled(p)
    ok(p.locator(f'#host-jobs-board .sb-col[data-stage="in-production"] [data-job-card="{job}"]').count() == 1 and p.locator('#host-jobs-board .sb-col.is-open').get_attribute('data-stage') == 'available', 'the board behind has it under In production; the same stage stays open')
    ok(p.evaluate("Object.fromEntries([...document.querySelectorAll('#host-jobs-board .sb-col')].map(c => [c.dataset.stage, +c.querySelector('.sb-head [data-sb-count]').textContent]))") == {g['key']: g['count'] for g in JOBS(host)['scopes']['active']['groups']}, 'board counts equal the server’s')
    reads = [u for m, u in p.api if m == 'GET' and u.startswith('host/jobs?scope=active')]
    ok(sum(1 for m, u in p.api if m == 'POST') == 1 and len(reads) == 1, f'one write and one read of the jobs: no duplicate requests {p.api}')
    ok(focus_inside(p), 'focus stays in the dialog, on the card now in its place')
    ok(p.locator(DIALOG + ' #toast').count() == 1 and p.locator('#toast').is_visible(), 'the confirmation shows above the dialog')
    ok(p.evaluate('window.__same') == 1, 'no page reload')
    p.screenshot(path=str(OUT / 'after-accept-1440.png'))
    close(p)
    # The same job, next step, from its new stage.
    p.locator('.sb-mosaic [data-sb-open="in-production"]').click(); p.wait_for_timeout(350); expand(p)
    production_now = ids(p, 'data-job-card'); p.locator(f'{DIALOG} [data-job="{job}"]').click(); confirm(p)
    wait_cards(p, len(production_now) - 1, 'data-job-card'); settled(p)
    ok(p.locator(f'#host-jobs-board .sb-col[data-stage="ready"] [data-job-card="{job}"]').count() == 1 and next(j for j in JOBS(host)['items'] if j['id'] == job)['status'] == 'ready', 'Mark ready to ship from the section: it moves to Ready to ship, on the server too')
    ok(p.locator(f'{DIALOG} [data-job-card="{job}"]').count() == 0, 'and is gone from In production')
    close(p)
    # Empty the stage from the section: its message, and focus somewhere sensible afterwards.
    p.locator('.sb-mosaic [data-sb-open="ready"]').click(); p.wait_for_timeout(350); expand(p)
    for k, jid in enumerate(ids(p, 'data-job-card')):
        p.locator(f'{DIALOG} [data-job="{jid}"]').click(); p.wait_for_selector('#action-dialog[open]')
        p.fill('#shipment-form input[name=carrier]', 'DHL'); p.fill('#shipment-form input[name=tracking_number]', f'SM{k}'); confirm(p)
        p.wait_for_function(f"!document.querySelector('{DIALOG} [data-job-card=\"{jid}\"]')"); settled(p)
    ok(p.locator(DIALOG + ' .ss-empty').is_visible() and 'Nothing in Ready to ship right now' in p.locator(DIALOG + ' .ss-empty').inner_text() and count_text(p) == '0 manufacturing jobs', 'the last job shipped: the section says the stage is empty')
    close(p)
    ok(p.evaluate("document.activeElement.matches('.sb-col.is-open .sb-head')") and not p.locator('.sb-col.is-open [data-sb-expand]').is_visible(), 'closing: an empty stage has no Expand section; focus goes to its heading')
    ok(not errors, 'no page errors so far: ' + '; '.join(errors[:4]))
    host.close()

    # ---------- Many items: cards drawn in batches, every one reachable ----------
    ctx, p = session(browser, 'host', counts=[2, 60, 0, 1]); go(p, 'host/jobs?group=in-production', '#host-jobs-board'); p.api.clear(); expand(p)
    ok(len(ids(p, 'data-job-card')) == 24 and count_text(p) == '60 manufacturing jobs' and p.locator(DIALOG + ' .ss-more-note').inner_text() == '24 of 60 shown', 'of 60 jobs: 24 cards drawn, and it says so')
    more = p.locator(DIALOG + ' [data-ss-more]'); more.click(); p.wait_for_function(f"document.querySelectorAll('{DIALOG} [data-job-card]').length === 48")
    ok(p.evaluate(f"document.activeElement === document.querySelectorAll('{DIALOG} .ss-list > *')[24]"), 'Show more: focus moves to the first new card')
    more.click(); wait_cards(p, 60, 'data-job-card')
    ok(not more.is_visible(), 'every job reachable; Show more is gone')
    p.fill(DIALOG + ' #ss-q', 'in-production rack 057'); p.wait_for_timeout(350)
    ok(len(ids(p, 'data-job-card')) == 1 and count_text(p) == '1 of 60 manufacturing jobs', 'search finds a job far beyond the first batch')
    p.fill(DIALOG + ' #ss-q', ''); p.wait_for_timeout(350)
    ok(len(ids(p, 'data-job-card')) == 24, 'clearing the search starts from the first batch again')
    sort_by(p, 'oldest'); p.wait_for_timeout(120)
    ok(ids(p, 'data-job-card')[0] == min(ids(p, 'data-job-card')), 'sorting works across all 60, not only those drawn')
    ok(not [u for m, u in p.api], f'no request for any of it {p.api}')
    close(p); ctx.close()
    ctx, p = session(browser, 'host', counts=[2, 0, 1, 1]); go(p, 'host/jobs?group=in-production', '#host-jobs-board')
    ok(not p.locator('.sb-col.is-open [data-sb-expand]').is_visible(), 'an empty open stage offers no Expand section')
    ctx.close()

    # ---------- Paged stages: every record reachable through the server ----------
    buyer, b = session(browser, 'buyer'); admin, a = session(browser, 'admin')
    post = lambda ctx, path, data: ctx.request.post(f'{BASE}/api/{path}', data=data, headers={'x-csrf-token': ctx.csrf})
    listing = buyer.request.get(BASE + '/api/listings?per_page=12').json()['items'][0]
    offer = buyer.request.get(f'{BASE}/api/listings/{listing["id"]}/availability').json()
    material = next(iter(offer['materials'])); color = next(iter(offer['colors_by_material'][material])); line = {'listing_id': listing['id'], 'material': material, 'color': color, 'quantity': 1}
    price = post(buyer, f'listings/{listing["id"]}/quote', {'material': material, 'color': color, 'quantity': 1}).json()['unit_price_cents']
    contact = {'first_name': 'Q', 'last_name': 'A', 'phone': '+39 011 1234567', 'street': 'Via QA 1', 'city': 'Torino', 'country': 'IT', 'postal_code': '10100', 'region': 'Piedmont'}
    placed = []
    for n in range(14):
        r = post(buyer, 'checkout', {'contact': contact, 'direct': line, 'confirmed': [{**line, 'unit_price_cents': price}], 'idempotency_key': f'section-modal-{n}-{os.getpid()}'}); assert r.ok, r.text()
        placed.append(r.json())
    for order in placed: assert post(admin, f'admin/orders/{order["id"]}/cancel', {'reason': 'Section dialog check'}).ok
    full = {o['id']: o for o in admin.request.get(BASE + '/api/admin/orders').json() if o['status'] == 'cancelled'}; total = len(full)
    go(a, 'admin/orders?scope=history&group=cancelled', '#admin-orders-board'); a.api.clear(); expand(a)
    ok(len(ids(a, 'data-order-card')) == 12 and count_text(a) == f'{total} orders' and not a.api, f'paged stage: first page, the true total ({count_text(a)}), no request to open')
    a.locator(DIALOG + ' [data-ss-more]').click(); wait_cards(a, total, 'data-order-card')
    pages = [u for m, u in a.api if u.startswith('admin/orders?')]
    ok(len(pages) == 1 and 'page=2' in pages[0], f'Show more loads the next page, once {pages}')
    ok(sorted(ids(a, 'data-order-card')) == sorted(full) and not a.locator(DIALOG + ' .ss-more').is_visible(), 'every cancelled order is reachable')
    ok(sorted(ids(a, 'data-order-card', '#admin-orders-board .sb-col[data-stage="cancelled"]')) == sorted(full), 'the board has the same page now: both show one list')
    close(a); a.reload(); a.wait_for_selector('#admin-orders-board'); settled(a); a.api.clear(); expand(a)
    last = sorted(full.values(), key=lambda o: o['created_at'])[0]
    a.locator(DIALOG + ' #ss-q').press_sequentially(last['reference'], delay=8)
    a.wait_for_function(f"document.querySelectorAll('{DIALOG} [data-order-card]').length === 1"); settled(a)
    searches = [u for m, u in a.api if 'q=' + last['reference'] in u]
    ok(ids(a, 'data-order-card') == [last['id']] and count_text(a) == f'1 of {total} orders', f'search reaches an order beyond the first page ({count_text(a)})')
    ok(len(searches) == 1 and len([u for m, u in a.api if u.startswith('admin/orders?')]) <= 2, f'typing sends one search, not one per key {a.api}')
    a.api.clear(); a.fill(DIALOG + ' #ss-q', ''); a.wait_for_function(f"document.querySelectorAll('{DIALOG} [data-order-card]').length === 12")
    ok(not a.api, 'clearing it needs no request')
    oldest = [o['id'] for o in sorted(full.values(), key=lambda o: (o['created_at'], o['id']))]
    a.api.clear(); sort_by(a, 'oldest'); a.wait_for_function("([d, id]) => document.querySelector(d + ' [data-order-card]')?.dataset.orderCard == id", arg=[DIALOG, oldest[0]]); settled(a)
    calls = [u for m, u in a.api if u.startswith('admin/orders?')]
    ok(ids(a, 'data-order-card') == oldest[:12] and count_text(a) == f'{total} orders', 'Oldest: the server sorts and returns one page; the order is true')
    ok(len(calls) == 1 and 'sort=oldest' in calls[0] and 'per_page=12' in calls[0], f'one request, not the whole history {calls}')
    a.locator(DIALOG + ' [data-ss-more]').click(); wait_cards(a, total, 'data-order-card'); settled(a)
    drawn = ids(a, 'data-order-card')
    ok(drawn == oldest, 'Show more continues in that order')
    a.locator(f'{DIALOG} [data-admin-order="{drawn[-1]}"]').click(); a.wait_for_selector('#modal[open]')
    ok(full[drawn[-1]]['reference'] in a.locator('#modal').inner_text(), 'Details works for a card from a later page')
    a.keyboard.press('Escape'); a.wait_for_selector('#modal', state='hidden'); close(a)

    # Admin: cancelling an active order from its section.
    go(a, 'admin/orders?group=pending', '#admin-orders-board'); expand(a)
    pending = ids(a, 'data-order-card'); target = pending[0]
    ok(a.locator(DIALOG + ' #ss-title').inner_text() == 'Pending', 'admin orders: Pending section')
    a.locator(f'{DIALOG} [data-cancel-order="{target}"]').click(); a.wait_for_selector('#action-dialog[open]')
    a.fill('#cancel-order-form textarea', 'Checked from the section dialog'); confirm(a)
    wait_cards(a, len(pending) - 1, 'data-order-card'); settled(a)
    ok(target not in ids(a, 'data-order-card') and a.locator(f'#admin-orders-board [data-order-card="{target}"]').count() == 0 and focus_inside(a), 'the cancelled order leaves the section and the board; focus stays in the section')
    close(a)
    # (Approvals are covered with their own data in tests/history_views_browser.js.)

    # ---------- My orders: the same component, the buyer's own cards and actions ----------
    go(b, 'orders', '#bo-board')
    ok(b.locator('#bo-board.sb .sb-mosaic').count() == 1 and b.locator('[data-wf-board], .wf-column').count() == 0, 'My orders uses the shared board: one component')
    current = buyer.request.get(BASE + '/api/orders?paginated=true&per_page=50').json(); shipping = [g for g in current['scopes']['active']['groups'] if g['key'] == 'shipping'][0]
    b.locator('#bo-board [data-sb-open="shipping"]:visible').first.click(); b.wait_for_timeout(350); b.evaluate('window.__same = 1')
    b.api.clear(); expand(b)
    orders_now = [o for o in current['items'] if o['status'] in shipping['statuses']]
    ok(sorted(ids(b, 'data-order-id')) == sorted(o['id'] for o in orders_now) and not b.api, f'the Shipping section shows its orders, no request ({count_text(b)})')
    text = b.locator(DIALOG + ' .bo-card').first.inner_text()
    ok(orders_now[0]['reference'] in text or any(o['reference'] in text for o in orders_now), 'with the reference')
    ok(b.locator(DIALOG + ' [data-received]').count() >= 1 and b.locator(DIALOG + ' .bo-shipment').first.is_visible() and b.locator(DIALOG + ' .bo-progress').count() >= 1, 'with progress, tracking and Mark as received')
    b.wait_for_timeout(280); b.screenshot(path=str(OUT / 'orders-section-1440.png'))
    oid = ids(b, 'data-order-id')[0]
    b.locator(f'{DIALOG} [data-order-details="{oid}"]').click(); b.wait_for_selector('#modal[open]')
    b.keyboard.press('Escape'); b.wait_for_selector('#modal', state='hidden')
    ok(is_open(b) and b.evaluate(f"!!document.activeElement.closest('{DIALOG}')"), 'Details from the section returns to it')
    n = len(ids(b, 'data-order-id')); received = b.locator(f'{DIALOG} [data-received]').first; order_of = int(received.get_attribute('data-received').split(':')[0]); received.click(); confirm(b)
    b.wait_for_function(f"!document.querySelector('{DIALOG} [data-order-id=\"{order_of}\"] [data-received]') || document.querySelectorAll('{DIALOG} [data-order-id]').length !== {n}"); settled(b)
    after = {o['id']: o for o in buyer.request.get(BASE + '/api/orders').json()}
    ok(all(j['status'] != 'shipped' for j in after[order_of]['jobs'][:1]) or after[order_of]['status'] != 'shipped', 'Mark as received works from the section')
    ok(b.evaluate('window.__same') == 1 and focus_inside(b), 'no reload; focus stays in the dialog')
    ok(b.evaluate("[...document.querySelectorAll('#bo-board .sb-col')].find(c => c.dataset.stage === 'shipping').querySelector('.sb-head [data-sb-count]').textContent") == count_text(b).split(' ')[0], 'the board and the section agree on the count')
    close(b)
    go(b, 'orders?scope=history&group=cancelled', '#bo-history-board'); b.api.clear(); expand(b)
    ok(len(ids(b, 'data-order-id')) == 12 and not b.api, 'Previous orders: paged the same way')
    target = placed[0]['reference']; b.locator(DIALOG + ' #ss-q').press_sequentially(target, delay=5)
    b.wait_for_function(f"document.querySelectorAll('{DIALOG} [data-order-id]').length === 1"); settled(b)
    ok(target in b.locator(DIALOG + ' .ss-list').inner_text() and len([u for m, u in b.api if 'q=' + target in u]) == 1, 'and search reaches the server, once')
    close(b); buyer.close(); admin.close()

    # ---------- Leaving the page closes it; reduced motion is instant ----------
    ctx, p = session(browser, 'host'); go(p, 'host', '.ho-stats'); p.locator('.ho-stat[data-stage="available"]').click(); p.wait_for_selector('#host-jobs-board'); settled(p); expand(p)
    p.go_back(); p.wait_for_selector('.ho-stats')
    ok(not is_open(p) and p.evaluate("!document.documentElement.classList.contains('section-open')"), 'Back closes the section, and leaves the page scrollable')
    ctx.close()
    ctx, p = session(browser, 'host', motion='reduce'); go(p, 'host/jobs?group=shipped', '#host-jobs-board'); expand(p)
    ok(p.evaluate("(document.querySelector('[data-ss-close]').click(), !document.querySelector('#section-dialog').open)"), 'reduced motion: closes at once')
    ctx.close()

    # ---------- Every width, Bright and Dark ----------
    for w, h, touch in ((320, 700, True), (390, 844, True), (768, 1024, True), (1024, 768, False), (1280, 800, False), (1440, 900, False)):
        for theme in ('light', 'dark'):
            ctx, p = session(browser, 'host', w, h, theme, touch, counts=[2, 8, 1, 1]); go(p, 'host/jobs?group=in-production', '#host-jobs-board')
            action = p.locator('.sb-col.is-open [data-sb-expand]')
            ok(action.is_visible() and p.evaluate('document.documentElement.scrollWidth - innerWidth') <= 0, f'{w} {theme}: Expand section offered; no page overflow')
            target = action.bounding_box(); ok(target['height'] >= (44 if touch else 30) and target['width'] >= (44 if touch else 30), f'{w} {theme}: a comfortable target ({target["width"]:.0f} × {target["height"]:.0f})')
            if theme == 'light' or w in (390, 1440): p.wait_for_timeout(500); p.screenshot(path=str(OUT / f'board-{w}-{theme}.png'))
            expand(p); p.wait_for_timeout(260)
            s = p.evaluate("""(() => { const d = document.querySelector('#section-dialog'), r = d.getBoundingClientRect(), list = d.querySelector('.ss-list'), body = d.querySelector('.ss-body'), close = d.querySelector('[data-ss-close]').getBoundingClientRect();
              const cards = [...list.children].map(c => c.getBoundingClientRect()); const inner = [...list.querySelectorAll('.jc-title, .jc-primary, .wf-link')];
              return {w:r.width / innerWidth, h:r.height / innerHeight, fits:r.left >= 0 && r.right <= innerWidth + .5 && r.top >= 0 && r.bottom <= innerHeight + .5, columns:getComputedStyle(list).gridTemplateColumns.split(' ').length,
                over:list.scrollWidth - list.clientWidth, bodyOver:body.scrollWidth - body.clientWidth, scrolls:body.scrollHeight > body.clientHeight && getComputedStyle(body).overflowY === 'auto', closeSize:Math.min(close.width, close.height),
                inCard:[...list.children].every(c => [...c.querySelectorAll('*')].every(e => { const x = e.getBoundingClientRect(); const y = c.getBoundingClientRect(); return !x.width || (x.left >= y.left - 1 && x.right <= y.right + 1); })), active:document.activeElement.id}; })()""")
            ok(s['fits'] and s['over'] <= 0 and s['bodyOver'] <= 0 and s['inCard'], f'{w} {theme}: fits the screen, nothing overflows a card {s}')
            ok(s['scrolls'] and s['closeSize'] >= (44 if touch else 40), f'{w} {theme}: scrolls inside; a prominent close button ({s["closeSize"]:.0f} px)')
            ok(s['w'] >= (.96 if w <= 640 else .85) and s['h'] >= (.96 if w <= 640 else .85), f'{w} {theme}: {s["w"]:.0%} × {s["h"]:.0%} of the screen')
            ok(s['columns'] == (1 if w <= 768 else 2), f'{w} {theme}: {s["columns"]} column(s) of cards')
            ok((s['active'] != 'ss-q') == touch, f'{w} {theme}: focus {"avoids the on-screen keyboard" if touch else "starts in search"}')
            if theme == 'light' or w in (390, 1440): p.screenshot(path=str(OUT / f'section-{w}-{theme}.png'))
            close(p); ctx.close()

    ok(not errors, 'no page errors: ' + '; '.join(errors[:5]))
    browser.close()
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
