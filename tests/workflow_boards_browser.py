"""Workflow boards: the host overview, Printing jobs (expandable stage board) and My orders, against the
isolated workflow fixture.
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

def session(browser, who, w=1440, h=900, theme='light', touch=False):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme, has_touch=touch, is_mobile=touch)
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

    # ---------- Host overview: four stage counts, nothing operational ----------
    host, p = session(browser, 'host')
    requests = []
    p.on('request', lambda r: r.resource_type in ('fetch', 'xhr', 'document') and requests.append(r.url))
    data = api(host, '/host/jobs?scope=active')
    groups = data['scopes']['active']['groups']
    counts = lambda: {g['key']: g['count'] for g in api(host, '/host/jobs?scope=active')['scopes']['active']['groups']}
    ok([g['key'] for g in groups] == ['available', 'in-production', 'ready', 'shipped'], f'four host stages from the API {[g["key"] for g in groups]}')
    ok(next(g for g in groups if g['key'] == 'in-production')['statuses'] == ['accepted', 'printing'], 'In production holds accepted and printing jobs')
    p.goto(BASE + '/#host'); p.wait_for_selector('.ho-stats')
    cards = p.evaluate("[...document.querySelectorAll('.ho-stat')].map(c => [c.dataset.stage, +c.querySelector('.ho-stat-count').textContent, c.querySelector('.ho-stat-label').textContent])")
    ok([c[:2] for c in cards] == [[g['key'], g['count']] for g in groups], f'overview: four summary cards with the API counts {cards}')
    ok([c[2] for c in cards] == [g['label'] for g in groups], 'overview cards use the stage names of Printing jobs')
    ok(p.locator('#app [data-job-card], #app .line-thumb, #app [data-stage-board], #app [data-wf-board]').count() == 0, 'overview shows no job cards, previews or board')
    ok(p.locator('.ws-actions a[href="#host/jobs"]').inner_text().strip() == 'Manage printing jobs', 'overview: Manage printing jobs is the page action')
    ok(p.locator('.ho-summary').is_visible() and 'completed job' in p.locator('.ho-summary').inner_text(), 'overview: one line of activity')
    p.screenshot(path=str(OUT / 'overview-1440.png'), full_page=True)

    # A summary card opens Printing jobs on its stage.
    p.locator('.ho-stat[data-stage="ready"]').click(); board(p, '[data-stage-board]')
    ok(p.url.endswith('#host/jobs?group=ready') and p.locator('.sb-col.is-open').get_attribute('data-stage') == 'ready', 'Ready to ship card opens Printing jobs on Ready to ship')

    # ---------- Printing jobs: expandable board (desktop) ----------
    STAGES = """sel => Object.fromEntries([...document.querySelectorAll(sel + ' .sb-col')].map(c => [c.dataset.stage, [...c.querySelectorAll('[data-job-card]')].map(e => +e.dataset.jobCard)]))"""
    drawn = p.evaluate(STAGES, '#host-jobs-board')
    ok(list(drawn) == [g['key'] for g in groups], f'stages follow the API order {list(drawn)}')
    ok(all(len(drawn[g['key']]) == g['count'] for g in groups), 'stage counts match the API counts')
    ok(all(j['status'] in next(g['statuses'] for g in groups if j['id'] in drawn[g['key']]) for j in data['items']), 'every job sits in the stage of its status')
    ok(sorted(i for ids in drawn.values() for i in ids) == sorted(j['id'] for j in data['items']), 'each active job appears exactly once')
    ok(p.evaluate("[...document.querySelectorAll('#host-jobs-board .sb-head [data-sb-count]')].map(e => +e.textContent)") == [len(v) for v in drawn.values()], 'stage headers show their counts')
    ok(p.locator('#app').get_by_text('Start printing').count() == 0, 'no Start printing step anywhere')
    p.evaluate('window.__still = 1'); requests.clear()
    geometry = """() => { const b = document.querySelector('#host-jobs-board .sb-track').getBoundingClientRect(); return [...document.querySelectorAll('#host-jobs-board .sb-col')].map(c => { const r = c.getBoundingClientRect(), t = c.querySelector('.sb-title'); return {stage:c.dataset.stage, open:c.classList.contains('is-open'), share:r.width / b.width, width:r.width, top:r.top, cards:[...c.querySelectorAll('[data-job-card]')].filter(e => e.checkVisibility()).length, fits:t.scrollWidth <= t.clientWidth + 1 && t.checkVisibility()}; }); }"""
    for key in ('in-production', 'shipped', 'available', 'ready'):
        p.locator(f'#host-jobs-board .sb-head[data-sb-open="{key}"]').click(); p.wait_for_timeout(450)
        cols = p.evaluate(geometry)
        opened = [c for c in cols if c['open']]
        ok(len(opened) == 1 and opened[0]['stage'] == key, f'{key}: exactly one stage open')
        ok(.55 <= opened[0]['share'] <= .65, f'{key}: the open stage takes {opened[0]["share"]:.0%} of the board')
        ok(all(c['width'] >= 100 and c['cards'] == 0 and c['fits'] for c in cols if not c['open']), f'{key}: collapsed stages are compact (≥100 px), show no cards, and their names fit')
        ok(opened[0]['cards'] == len(drawn[key]), f'{key}: the open stage shows its {len(drawn[key])} cards')
        ok(len({round(c['top']) for c in cols}) == 1, f'{key}: the four stages sit side by side')
        ok(p.evaluate("[...document.querySelectorAll('#host-jobs-board .sb-head')].map(h => h.getAttribute('aria-expanded'))") == [str(s == key).lower() for s in drawn], f'{key}: aria-expanded marks only the open stage')
        ok(p.url.endswith(f'#host/jobs?group={key}'), f'{key}: the address remembers the stage')
    ok(p.evaluate('window.__still') == 1 and not requests, f'switching stages: no reload and no API request ({len(requests)})')
    labels = {'available': 'Accept job', 'in-production': 'Mark ready to ship', 'ready': 'Mark shipped'}
    for key, label in labels.items():
        texts = p.locator(f'#host-jobs-board [data-stage="{key}"] [data-job]').all_text_contents()
        ok(texts and set(texts) == {label}, f'{key}: the one main action is “{label}” ({len(texts)})')
    ok(p.locator('#host-jobs-board [data-stage="shipped"] [data-job]').count() == 0, 'Awaiting buyer: no host action')
    subs = p.evaluate("[...document.querySelectorAll('#host-jobs-board [data-stage=in-production] [data-job-card]')].map(c => [+c.dataset.jobCard, c.querySelector('.jc-sub')?.textContent])")
    status = {j['id']: j['status'] for j in data['items']}
    ok(subs and all(t == {'accepted': 'Accepted', 'printing': 'Printing'}[status[i]] for i, t in subs), 'In production cards say whether printing was reported')

    # Detailed cards: what to make and how, for which order, its value and time in stage.
    p.locator('#host-jobs-board .sb-head[data-sb-open="in-production"]').click(); p.wait_for_timeout(400); thumbs_ready(p)
    for el in p.locator('#host-jobs-board .sb-col.is-open [data-job-card]').all():
        el.scroll_into_view_if_needed(); el.locator('img.is-ready').wait_for(state='attached', timeout=8000)   # previews load lazily
        j = next(x for x in data['items'] if x['id'] == int(el.get_attribute('data-job-card'))); i = j['item']; text = el.inner_text()
        hexes = 'rgb(%d, %d, %d)' % tuple(int(i['color_hex'][k:k + 2], 16) for k in (1, 3, 5))
        ok(all(v in text for v in (i['title'], i['material'], j['order_reference'], f"× {i['quantity']}", i['dimensions'], i['cad_format'] + ' model'))
           and el.locator('.line-swatch').evaluate('e => getComputedStyle(e).backgroundColor') == hexes and el.locator('img').evaluate("i => i.src.startsWith('data:image/')")
           and re.search(r'(Accepted|Printing started) .*ago', text) and el.get_by_role('link', name=re.compile('Download')).count() == 1,
           f'card {j["id"]}: product, recoloured preview, material and swatch, quantity, size, model file, order, time in stage, download')
    p.screenshot(path=str(OUT / 'jobs-in-production-1440.png'), full_page=True)

    # Search counts the matches of every stage; the open one says when none of its own match.
    p.fill('[data-filter-list="host-jobs-search"]', 'microtube')
    matches = {k: sum(1 for i in v if 'Microtube' in next(j['item']['title'] for j in data['items'] if j['id'] == i)) for k, v in drawn.items()}
    ok(p.evaluate("[...document.querySelectorAll('#host-jobs-board .sb-head [data-sb-count]')].map(e => +e.textContent)") == list(matches.values()), f'search: stage counts become match counts {matches}')
    p.fill('[data-filter-list="host-jobs-search"]', 'no such product'); ok(p.locator('#host-jobs-search [data-filter-empty]').is_visible(), 'search with no match says so')
    p.fill('[data-filter-list="host-jobs-search"]', '')
    ok(p.evaluate("[...document.querySelectorAll('#host-jobs-board .sb-head [data-sb-count]')].map(e => +e.textContent)") == [len(v) for v in drawn.values()], 'clearing the search restores the counts')

    # Accept: the job goes straight to In production; the open stage stays, the next job takes focus.
    p.locator('#host-jobs-board .sb-head[data-sb-open="available"]').click(); p.wait_for_timeout(400)
    card = p.locator('#host-jobs-board .sb-col.is-open [data-job-card]').first
    job = next(j for j in data['items'] if j['id'] == int(card.get_attribute('data-job-card')))
    card.locator('[data-job-details]').click(); p.wait_for_selector('#modal[open]')
    ok(job['order_reference'] in p.locator('#modal').inner_text() and p.locator('#modal [data-details-printing]').count() == 0, 'details of an available job: order reference, no printing report')
    p.keyboard.press('Escape')
    before = counts()
    p.locator(f'#host-jobs-board [data-job="{job["id"]}"]').click(); confirm(p)
    p.wait_for_selector(f'#host-jobs-board [data-stage="in-production"] [data-job-card="{job["id"]}"]', state='attached'); board(p, '[data-stage-board]')
    after = p.evaluate(STAGES, '#host-jobs-board')
    ok(len(after['available']) == before['available'] - 1 and len(after['in-production']) == before['in-production'] + 1, 'accepted job is in In production at once')
    ok(p.locator('.sb-col.is-open').get_attribute('data-stage') == 'available' and p.evaluate('window.__still') == 1, 'Available stays open; no page reload')
    p.wait_for_function("document.activeElement?.closest('.sb-col.is-open')")
    ok(p.evaluate("document.activeElement.matches('[data-job], [data-job-details], .sb-head')"), 'focus stays in the open stage')
    ok(p.locator('#host-jobs-board .sb-col[data-stage="in-production"].sb-bump').count() == 1, 'In production lights up with its new count')
    ok(p.locator('#topbar [data-count-key=jobs]').inner_text() == str(len(after['available'])), 'navigation badge counts the remaining available jobs')
    ok(counts() == {k: len(v) for k, v in after.items()}, 'board and server agree after accepting')

    # In production: reporting the print start is optional; Mark ready to ship works from either status.
    p.locator('#host-jobs-board .sb-head[data-sb-open="in-production"]').click(); p.wait_for_timeout(400)
    ok(p.locator(f'#host-jobs-board [data-job="{job["id"]}"]').inner_text() == 'Mark ready to ship', 'accepted job: next step is Mark ready to ship')
    p.locator(f'#host-jobs-board [data-job-card="{job["id"]}"] [data-job-details]').click(); p.wait_for_selector('#modal[open]')
    ok(p.locator('#modal .ad-flow [aria-current=step]').inner_text().startswith('In production'), 'details: progress at In production')
    p.locator('#modal [data-details-printing]').click(); p.wait_for_selector('#action-dialog[open]')
    ok('Optional' in p.locator('#action-dialog').inner_text(), 'the printing report says it is optional'); confirm(p)
    p.wait_for_function(f"document.querySelector('#host-jobs-board [data-job-card=\"{job['id']}\"] .jc-sub')?.textContent === 'Printing'"); board(p, '[data-stage-board]')
    ok(api(host, '/host/jobs?scope=active&group=in-production')['items'] and next(j for j in api(host, '/host/jobs?scope=active')['items'] if j['id'] == job['id'])['status'] == 'printing', 'reported: printing, still In production')
    other = next(i for i in after['in-production'] if status.get(i) == 'accepted')
    p.locator(f'#host-jobs-board [data-job="{other}"]').click(); p.wait_for_selector('#action-dialog[open]')
    ok(p.locator('#action-dialog h2').inner_text() == 'Mark as ready to ship?', 'ready step from an accepted job'); confirm(p)
    p.wait_for_selector(f'#host-jobs-board [data-stage="ready"] [data-job-card="{other}"]', state='attached'); board(p, '[data-stage-board]')
    ok(True, 'an accepted job goes to Ready to ship without a printing step')
    for jid in (job['id'],):
        p.locator(f'#host-jobs-board [data-job="{jid}"]').click(); confirm(p)
        p.wait_for_selector(f'#host-jobs-board [data-stage="ready"] [data-job-card="{jid}"]', state='attached'); board(p, '[data-stage-board]')
    p.locator('#host-jobs-board .sb-head[data-sb-open="ready"]').click(); p.wait_for_timeout(400)
    p.locator(f'#host-jobs-board [data-job="{job["id"]}"]').click(); p.wait_for_selector('#action-dialog[open]')
    p.fill('#shipment-form [name=carrier]', 'Courier'); p.fill('#shipment-form [name=tracking_number]', 'QA-STAGE-1'); p.locator('#action-dialog [data-ad-confirm]').click()
    p.wait_for_selector(f'#host-jobs-board [data-stage="shipped"] [data-job-card="{job["id"]}"]', state='attached'); board(p, '[data-stage-board]')
    ok('QA-STAGE-1' in p.locator(f'#host-jobs-board [data-job-card="{job["id"]}"]').text_content(), 'shipped job: in Awaiting buyer with its tracking number')

    # Completed (the buyer confirms receipt): out of the board, into Job history.
    buyer_ctx, _ = session(browser, 'buyer')
    ok(buyer_ctx.request.post(f'{BASE}/api/orders/{job["order_id"]}/jobs/{job["id"]}/received', headers={'X-CSRF-Token': buyer_ctx.csrf}).ok, 'buyer confirms receipt')
    buyer_ctx.close()
    p.goto(BASE + '/#host/jobs'); board(p, '[data-stage-board]')
    ok(p.locator(f'[data-job-card="{job["id"]}"]').count() == 0, 'a completed job leaves the board')
    ok(p.locator('.sb-col.is-open').get_attribute('data-stage') == 'ready', 'returning to Printing jobs reopens the stage open last')
    p.locator('.ws-actions a', has_text='Job history').click(); p.wait_for_selector('#job-list .job-row')
    hist = api(host, '/host/jobs?scope=history')
    ok(p.locator('#ws-title').inner_text() == 'Job history' and p.locator(f'#job-list [data-job-details="{job["id"]}"]').count() == 1, 'Job history lists the completed job')
    ok(p.locator('#job-list .job-row').count() == hist['total'] and all(j['status'] in ('completed', 'cancelled') for j in hist['items']), 'Job history holds only closed jobs')
    p.locator(f'#job-list [data-job-details="{job["id"]}"]').click(); p.wait_for_selector('#modal[open]')
    ok(p.locator('#modal .ad-flow .done').count() == 4, 'a completed job shows every step done'); p.keyboard.press('Escape')
    p.locator('.ws-actions a', has_text='Active jobs').click(); board(p, '[data-stage-board]')

    # Overview and Printing jobs agree; legacy stage links still land on the right stage.
    final = p.evaluate(STAGES, '#host-jobs-board')
    p.goto(BASE + '/#host'); p.wait_for_selector('.ho-stats')
    ok({c[0]: c[1] for c in p.evaluate("[...document.querySelectorAll('.ho-stat')].map(c => [c.dataset.stage, +c.querySelector('.ho-stat-count').textContent])")} == {k: len(v) for k, v in final.items()} == counts(), 'overview counts match the board and the server')
    for link in ('host/jobs?group=accepted', 'host/jobs/accepted', 'host/jobs?group=in-progress'):
        p.goto(BASE + '/#' + link); board(p, '[data-stage-board]')
        ok(p.locator('.sb-col.is-open').get_attribute('data-stage') == 'in-production', f'#{link} opens In production')
    for theme in ('light', 'dark'):
        p.evaluate(f"applyTheme('{theme}')"); p.wait_for_timeout(200)
        ok(overflow(p) <= 0, f'1440 {theme}: no page overflow')
        p.screenshot(path=str(OUT / f'jobs-1440-{theme}.png'), full_page=True)
        p.goto(BASE + '/#host'); p.wait_for_selector('.ho-stats'); p.screenshot(path=str(OUT / f'overview-1440-{theme}.png'), full_page=True)
        p.goto(BASE + '/#host/jobs'); board(p, '[data-stage-board]')
    host.close()

    # ---------- Narrower: stage pills above one open stage; side by side again from 900 px ----------
    for w, theme in ((320, 'dark'), (390, 'light'), (768, 'dark'), (1024, 'light'), (900, 'dark')):
        ctx, q = session(browser, 'host', w, 860, theme, touch=w <= 430)
        q.goto(BASE + '/#host/jobs?group=available'); board(q, '[data-stage-board]')
        ok(overflow(q) <= 0, f'{w}px {theme}: no page overflow')
        pills = q.evaluate("[...document.querySelectorAll('.sb-pills .chip')].filter(c => c.checkVisibility()).map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height), r.right <= innerWidth, getComputedStyle(c).backgroundColor, c.getAttribute('aria-pressed')]; })")
        if w == 900:
            ok(not pills and len(q.evaluate("[...new Set([...document.querySelectorAll('.sb-col')].map(c => Math.round(c.getBoundingClientRect().top)))]")) == 1, '900px: the board is wide enough to expand side by side')
        else:
            rows = len({t for t, *_ in pills})
            ok(len(pills) == 4 and rows == (2 if w < 700 else 1) and all(h >= 44 and inside for _, h, inside, *_ in pills), f'{w}px: four 44 px stage pills in {rows} row(s), all on screen')
            ok([bg for *_, bg, pressed in pills if pressed == 'true'] == ['rgb(29, 53, 87)'], f'{w}px {theme}: the selected stage is navy')
            ok(q.evaluate("[...document.querySelectorAll('.sb-col')].filter(c => c.checkVisibility()).map(c => c.dataset.stage)") == ['available'], f'{w}px: only the open stage is shown')
            q.locator('.sb-pills [data-sb-open="ready"]').click(); q.wait_for_timeout(350)
            ok(q.evaluate("[...document.querySelectorAll('.sb-col')].filter(c => c.checkVisibility()).map(c => c.dataset.stage)") == ['ready'] and q.url.endswith('group=ready'), f'{w}px: a pill switches the stage')
            if w <= 390:
                fit = q.evaluate("(() => { const c = document.querySelector('.sb-col.is-open [data-job-card]'); if (!c) return true; const b = c.querySelector('.jc-primary'), r = c.getBoundingClientRect(), links = [...c.querySelectorAll('.wf-link')]; return b && b.getBoundingClientRect().width > r.width * .8 && b.getBoundingClientRect().height >= 44 && links.every(l => l.getBoundingClientRect().height >= 44); })()")
                ok(fit, f'{w}px touch: cards stack, with a full-width action and 44 px touch targets')
        q.screenshot(path=str(OUT / f'jobs-{w}-{theme}.png'), full_page=True)
        q.goto(BASE + '/#host'); q.wait_for_selector('.ho-stats')
        ok(overflow(q) <= 0, f'overview {w}px {theme}: no page overflow')
        q.screenshot(path=str(OUT / f'overview-{w}-{theme}.png'), full_page=True)
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
