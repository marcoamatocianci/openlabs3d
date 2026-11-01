"""Workflow boards: Printing jobs, the host overview and My orders, against the isolated workflow fixture.
Start a fresh fixture first (this suite accepts jobs, confirms deliveries and deletes an order):
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/workflow_boards_browser.py OUTPUT_DIR [BASE_URL]
Set CHROME to a Chromium binary if Playwright's bundled browser is not installed."""
import os, re, sys
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
    page.on('console', lambda m: m.type == 'error' and errors.append(f'{who} {w}: {m.text}'))
    page.on('dialog', lambda d: (errors.append('native dialog: ' + d.message), d.dismiss()))
    return ctx, page

def api(ctx, path): return ctx.request.get(BASE + '/api' + path).json()
def overflow(page): return page.evaluate('document.documentElement.scrollWidth - innerWidth')
def board(page, sel='[data-wf-board]'): page.wait_for_selector(sel); page.wait_for_function("!document.querySelector('.ws-main[aria-busy], #bo-results[aria-busy]')")
# {stage key: [ids]} as drawn, for job cards (data-job-card) or order cards (data-order-id).
COLUMNS = """([sel, attr]) => Object.fromEntries([...document.querySelectorAll(sel + ' .wf-column')].map(c => [c.dataset.stage, [...c.querySelectorAll('[' + attr + ']')].map(e => +e.getAttribute(attr))]))"""
def thumbs_ready(page):
    page.wait_for_function("[...document.querySelectorAll('.line-thumb img[data-color]')].filter(i => i.checkVisibility() && i.getBoundingClientRect().top < innerHeight && i.getBoundingClientRect().bottom > 0 && i.getBoundingClientRect().right > 0 && i.getBoundingClientRect().left < innerWidth).every(i => i.classList.contains('is-ready'))")
def confirm(page):
    page.wait_for_selector('#action-dialog[open]'); page.locator('#action-dialog [data-ad-confirm]').click(); page.wait_for_selector('#action-dialog', state='hidden')

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)

    # ---------- Printing jobs board (host, desktop) ----------
    host, p = session(browser, 'host')
    data = api(host, '/host/jobs?scope=active')
    groups = data['scopes']['active']['groups']
    p.goto(BASE + '/#host/jobs'); board(p)
    drawn = p.evaluate(COLUMNS, ['#host-jobs-board', 'data-job-card'])
    ok(list(drawn) == [g['key'] for g in groups], f'columns follow the API stages in order {list(drawn)}')
    ok(all(len(drawn[g['key']]) == g['count'] for g in groups), 'column counts match the API counts')
    ok(all(j['status'] in next(g['statuses'] for g in groups if j['id'] in drawn[g['key']]) for j in data['items']), 'every job sits in the column of its status')
    ok(sorted(i for ids in drawn.values() for i in ids) == sorted(j['id'] for j in data['items']), 'each active job appears exactly once')
    ok(not any(j['status'] in ('completed', 'cancelled') for j in data['items']), 'no completed or cancelled job on the board')
    ok(p.evaluate("[...document.querySelectorAll('#host-jobs-board .wf-column-head .segment-count')].map(e => parseInt(e.textContent))") == [len(v) for v in drawn.values()], 'column headers show their card counts')
    labels = {'available': 'Accept job', 'accepted': 'Start printing', 'in-progress': 'Mark ready', 'ready': 'Mark shipped'}
    for key, label in labels.items():
        texts = p.locator(f'#host-jobs-board [data-stage="{key}"] [data-job]').all_inner_texts()
        ok(texts and set(texts) == {label}, f'{key}: primary action is “{label}” ({len(texts)})')
    ok(p.locator('#host-jobs-board [data-stage="shipped"] [data-job]').count() == 0, 'shipped jobs have no host action')
    lane = p.evaluate("(() => { const b = document.querySelector('#host-jobs-board').getBoundingClientRect(), l = document.querySelector('#host-jobs-board .wf-lane').getBoundingClientRect(), a = document.querySelector('#host-jobs-board [data-stage=available]').getBoundingClientRect(); return [Math.round(l.width - b.width), l.top > a.top] })()")
    ok(lane[0] == 0 and lane[1], 'desktop: the shipped lane spans the board under the four action columns')
    ok(not p.locator('.wf-stages').first.is_visible(), 'desktop: stage strip hidden when every column fits')
    thumbs_ready(p)
    card = p.locator('#host-jobs-board [data-stage="available"] [data-job-card]').first
    job = next(j for j in data['items'] if j['id'] == int(card.get_attribute('data-job-card')))
    ok(card.locator('img').evaluate("i => i.src.startsWith('data:image/')"), 'job preview is recoloured with the ordered colour')
    ok(card.locator('.line-swatch').evaluate('e => getComputedStyle(e).backgroundColor') == 'rgb(%d, %d, %d)' % tuple(int(job['item']['color_hex'][i:i + 2], 16) for i in (1, 3, 5)), 'swatch shows the colour snapshot')
    ok(job['order_reference'] in card.inner_text() and f"× {job['item']['quantity']}" in card.inner_text() and job['item']['material'] in card.inner_text(), 'card shows order reference, material and quantity')
    p.screenshot(path=str(OUT / 'jobs-1440.png'), full_page=True)

    # Search filters cards; clearing restores them.
    p.fill('[data-filter-list="host-jobs-search"]', 'microtube')
    shown = p.evaluate("[...document.querySelectorAll('#host-jobs-board [data-job-card]')].filter(c => !c.hidden).map(c => c.querySelector('.wf-card-title').textContent)")
    ok(shown and all('Microtube' in t for t in shown), f'search keeps only matching jobs ({len(shown)})')
    p.fill('[data-filter-list="host-jobs-search"]', 'no such product'); ok(p.locator('#host-jobs-search [data-filter-empty]').is_visible(), 'search with no match says so')
    p.fill('[data-filter-list="host-jobs-search"]', '')

    # Details: everything about the job, its next step in the footer.
    card.locator('[data-job-details]').click(); p.wait_for_selector('#modal[open]')
    ok(job['order_reference'] in p.locator('#modal').inner_text() and p.locator('#modal [aria-current=step]').count() == 0, 'details: order reference, progress not started for an available job')
    p.locator('#modal [data-details-step]').click(); p.wait_for_selector('#action-dialog[open]')
    ok(not p.evaluate("document.querySelector('#modal').open"), 'the step closes the details before its confirmation opens')
    p.locator('#action-dialog [data-ad-cancel]').first.click()

    # Accept from the board: the card moves to Accepted, counts follow, no page reload, focus follows the job.
    p.evaluate('window.__still = 1')
    before = p.evaluate(COLUMNS, ['#host-jobs-board', 'data-job-card'])
    p.locator(f'#host-jobs-board [data-job="{job["id"]}"]').click(); confirm(p)
    p.wait_for_selector(f'#host-jobs-board [data-stage="accepted"] [data-job-card="{job["id"]}"]'); board(p)
    after = p.evaluate(COLUMNS, ['#host-jobs-board', 'data-job-card'])
    ok(len(after['available']) == len(before['available']) - 1 and len(after['accepted']) == len(before['accepted']) + 1, 'accepted job moves to the Accepted column')
    ok(p.evaluate('window.__still') == 1, 'no full page reload')
    p.wait_for_function(f"document.activeElement?.dataset.job === '{job['id']}'")
    ok(p.evaluate('document.activeElement.textContent') == 'Start printing', 'focus moves to the job’s next step')
    ok(p.locator('#topbar [data-count-key=jobs]').inner_text() == str(len(after['available'])), 'navigation badge counts the remaining available jobs')
    srv = api(host, '/host/jobs?scope=active')['scopes']['active']['groups']
    ok({g['key']: g['count'] for g in srv} == {k: len(v) for k, v in after.items()}, 'board and server agree after the step')
    ctx_overview = p.goto(BASE + '/#host/jobs?group=available'); board(p)
    ok(p.locator('#host-jobs-board [data-stage="available"]').evaluate("c => c.classList.contains('is-focus')"), 'a stage link marks its column')

    # Job history: completed and cancelled jobs, with details.
    p.goto(BASE + '/#host/jobs?scope=history'); p.wait_for_selector('#job-list .job-row')
    hist = api(host, '/host/jobs?scope=history')
    ok(p.locator('#job-list .job-row').count() == hist['total'] and all(j['status'] in ('completed', 'cancelled') for j in hist['items']), 'Job history lists the closed jobs')
    p.locator('#job-list [data-job-details]').first.click(); p.wait_for_selector('#modal[open]')
    ok(p.locator('#modal .ad-flow .done').count() == 5, 'a completed job shows every step done'); p.keyboard.press('Escape')

    # Overview: the same stages without the available pool, three cards per column at most.
    p.goto(BASE + '/#host'); board(p)
    ov = p.evaluate(COLUMNS, ['#host-overview-board', 'data-job-card'])
    ok(list(ov) == [g['key'] for g in groups if g['key'] != 'available'], f'overview reuses the stages {list(ov)}')
    ok(all(len(v) <= 3 for v in ov.values()), 'overview shows at most three cards per stage')
    p.screenshot(path=str(OUT / 'overview-1440.png'), full_page=True)
    host.close()

    # ---------- Printing jobs on phones: one column at a time ----------
    for w in (320, 390):
        ctx, q = session(browser, 'host', w, 800, 'dark' if w == 320 else 'light')
        q.goto(BASE + '/#host/jobs'); board(q)
        ok(overflow(q) <= 0, f'{w}px: no page overflow')
        geo = q.evaluate("(() => { const b = document.querySelector('#host-jobs-board'), c = b.children; return [b.clientWidth, c[0].getBoundingClientRect().width, c[1].getBoundingClientRect().left - b.getBoundingClientRect().left] })()")
        ok(geo[1] < geo[0] and geo[2] < geo[0], f'{w}px: one column wide, the next one peeks in {geo}')
        ok(q.locator('.wf-stages').is_visible() and q.locator('.wf-stages .chip.active').all_inner_texts()[0].startswith('Available'), f'{w}px: stage strip shows the stage in view')
        q.locator('.wf-stages [data-wf-jump$="-ready"]').click()
        q.wait_for_function("document.querySelector('.wf-stages .chip.active')?.dataset.wfJump.endsWith('-ready')")
        try: q.wait_for_function("Math.abs(document.querySelector('#host-jobs-board [data-stage=ready]').getBoundingClientRect().left - document.querySelector('#host-jobs-board').getBoundingClientRect().left) < 2", timeout=3000); aligned = True
        except Exception: aligned = False
        ok(aligned, f'{w}px: the strip scrolls Ready to ship to the start of the board')
        if w == 390:
            # A step keeps the reader on their column after the in-place refresh.
            left = q.evaluate("document.querySelector('#host-jobs-board').scrollLeft")
            jid = q.locator('#host-jobs-board [data-stage="ready"] [data-job]').first.get_attribute('data-job')
            q.locator(f'#host-jobs-board [data-job="{jid}"]').click(); q.wait_for_selector('#action-dialog[open]')
            q.fill('#shipment-form [name=carrier]', 'Courier'); q.fill('#shipment-form [name=tracking_number]', 'QA-BOARD-1'); q.locator('#action-dialog [data-ad-confirm]').click()
            q.wait_for_selector(f'#host-jobs-board [data-stage="shipped"] [data-job-card="{jid}"]'); board(q); q.wait_for_timeout(300)
            ok(abs(q.evaluate("document.querySelector('#host-jobs-board').scrollLeft") - left) <= 2 or q.evaluate(f"document.activeElement?.dataset.jobDetails === '{jid}'"), '390px: the board stays where the reader was (or follows the job)')
        q.screenshot(path=str(OUT / f'jobs-{w}.png'), full_page=True)
        ctx.close()

    # ---------- My orders board (buyer) ----------
    buyer, b = session(browser, 'buyer')
    orders = api(buyer, '/orders?paginated=true&per_page=50')
    ogroups = orders['scopes']['active']['groups']
    b.goto(BASE + '/#orders'); board(b, '#bo-board')
    drawn = b.evaluate(COLUMNS, ['#bo-board', 'data-order-id'])
    ok(list(drawn) == ['pending', 'in-progress', 'shipping'], f'order columns {list(drawn)}')
    ok(all(o['status'] in next(g['statuses'] for g in ogroups if o['id'] in drawn[g['key']]) for o in orders['items']), 'every order sits in the column of its status')
    ok(sorted(i for v in drawn.values() for i in v) == sorted(o['id'] for o in orders['items']), 'each current order appears once (multi-product orders included)')
    mixed = next(o for o in orders['items'] if len({j['status'] for j in o['jobs']}) > 2)
    mcard = b.locator(f'#bo-board [data-order-id="{mixed["id"]}"]')
    ok(mixed['id'] in drawn['in-progress'] and 'Partly shipped' in mcard.locator('.bo-card-stage').inner_text(), 'mixed order: In progress, marked partly shipped')
    ok('1 shipped · 1 in production · 1 awaiting a host' in mcard.inner_text(), 'mixed order: every product stage is counted on the card')
    ok(mcard.locator('[data-received]').count() == 1, 'mixed order: the shipped product can be confirmed from the card')
    thumbs_ready(b)
    first = mixed['items'][0]
    ok(mcard.locator('.bo-line').first.locator('.line-swatch').evaluate('e => getComputedStyle(e).backgroundColor') == 'rgb(%d, %d, %d)' % tuple(int(first['color_hex'][i:i + 2], 16) for i in (1, 3, 5)), 'order card shows the colour bought')
    b.screenshot(path=str(OUT / 'orders-1440.png'), full_page=True)

    # Details dialog: each product with its own stage; the address can be changed until something ships.
    pending = next(o for o in orders['items'] if o['status'] == 'pending' and len(o['jobs']) == 1)
    b.locator(f'#bo-board [data-order-id="{pending["id"]}"] [data-order-details]').click(); b.wait_for_selector('#modal[open]')
    ok(b.locator('#modal .bo-detail-line').count() == len(pending['items']) and b.locator('#modal [data-change-address]').is_enabled(), 'details: products listed, address editable')
    b.locator('#modal [data-change-address]').click(); b.wait_for_selector('#action-dialog[open]')
    b.fill('#order-address-form [name=street]', 'Via Board 9'); confirm(b)
    b.wait_for_function("document.querySelector('#modal[open] address')?.textContent.includes('Via Board 9')")
    ok(True, 'address change refreshes the open details')
    b.locator('#modal [data-delete-order]').click(); b.wait_for_selector('#action-dialog[open]')
    ok(b.evaluate("document.activeElement.matches('[data-ad-cancel]')"), 'delete confirmation starts on Cancel'); confirm(b)
    b.wait_for_function(f"!document.querySelector('#bo-board [data-order-id=\"{pending['id']}\"]')")
    ok(not b.evaluate("document.querySelector('#modal').open"), 'deleted order: details closed, card gone')

    # Confirm delivery from the board: the order completes and moves to Previous orders.
    shipped = next(o for o in orders['items'] if o['status'] == 'shipped')
    b.locator(f'#bo-board [data-order-id="{shipped["id"]}"] [data-received]').click(); confirm(b)
    b.wait_for_function(f"!document.querySelector('#bo-board [data-order-id=\"{shipped['id']}\"]')")
    ok('Previous orders' in b.locator('#toast').inner_text(), 'completed order: the toast says where it went')
    b.locator('#bo-toolbar .scope-history').click(); b.wait_for_selector('.bo-history-list')
    ok(b.locator(f'.bo-row[data-order-id="{shipped["id"]}"]').count() == 1, 'it is in Previous orders')
    b.fill('#bo-q', shipped['reference'][-6:]); b.press('#bo-q', 'Enter')
    b.wait_for_function(f"document.querySelectorAll('.bo-row').length === 1 && document.querySelector('.bo-row').dataset.orderId === '{shipped['id']}'")
    ok(True, 'previous orders: search by reference')
    b.locator('.bo-row [data-order-details]').click(); b.wait_for_selector('#modal[open]')
    ok(b.locator('#modal .bo-progress .current').count() == 1 and b.locator('#modal [data-change-address]').is_disabled(), 'previous order details: received, address locked')
    b.keyboard.press('Escape')
    buyer.close()

    for w, theme in ((375, 'dark'), (768, 'light')):
        ctx, q = session(browser, 'buyer', w, 900, theme)
        q.goto(BASE + '/#orders'); board(q, '#bo-board')
        ok(overflow(q) <= 0, f'orders {w}px {theme}: no page overflow')
        ok(q.locator('.wf-stages').is_visible() == (w < 600), f'orders {w}px: stage strip only when the columns do not fit')
        q.screenshot(path=str(OUT / f'orders-{w}-{theme}.png'), full_page=True)
        ctx.close()
    browser.close()

print(f'{sum(checks)}/{len(checks)} checks passed')
if errors: print('Console errors:', *errors[:10], sep='\n  ')
sys.exit(0 if all(checks) and not errors else 1)
