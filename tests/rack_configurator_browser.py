"""Design Your Rack in real browsers, from a visitor's first change to a host's download.

Isolated: start scripts/rack_preview.py first, which uses its own temporary database and real CAD.
    python scripts/rack_preview.py 8094 /tmp/rack-qa &
    python tests/rack_configurator_browser.py http://127.0.0.1:8094 [screenshot directory] [chromium firefox webkit]
"""
import json, os, re, secrets, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8094'
SHOTS = Path(sys.argv[2] if len(sys.argv) > 2 else '/tmp/rack-shots'); SHOTS.mkdir(parents=True, exist_ok=True)
ENGINES = sys.argv[3:] or ['chromium', 'firefox', 'webkit']
PASSWORD = 'Preview-only-1'
SIZES = {'desktop': (1440, 900), 'laptop': (1280, 720), 'tablet': (820, 1100), 'mobile': (390, 844)}
BUILD_MS = 180_000
results, skipped, teardown_cancels = [], [], []

def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('ok  ' if ok else 'FAIL'), name, detail if not ok else '', flush=True)

def wait_js(page, expression, arg=None, timeout=15000):
    """Wait for a page condition from here, rather than with wait_for_function, which needs eval: the real site's Content
    Security Policy refuses that, and these tests run under the real policy on purpose."""
    deadline = time.monotonic() + timeout / 1000
    expression = expression if '=>' in expression else f'() => ({expression})'
    while True:
        try:
            if page.evaluate(expression, arg): return
        except Exception as exc:
            if 'context was destroyed' not in str(exc) and 'navigation' not in str(exc).lower(): raise
        if time.monotonic() > deadline: raise TimeoutError(f'Condition not met in {timeout} ms: {expression[:120]}')
        page.wait_for_timeout(100)

def watch(page, errors):
    # WebKit reports a fetch cancelled by a page being torn down as "due to access control checks", at the instant the next
    # main-frame navigation starts (measured: 0.00 s). Only that exact signature in that instant is not an error: the same
    # message at any other moment is a real access failure, and fails the test.
    navigation = {'at': 0.0}
    page.on('request', lambda r: navigation.update(at=time.monotonic()) if r.is_navigation_request() else None)
    def on_page_error(error):
        if 'due to access control checks' in str(error) and time.monotonic() - navigation['at'] < .2:
            teardown_cancels.append(str(error)[:120]); return
        errors.append('pageerror: ' + str(error)[:300])
    page.on('pageerror', on_page_error)
    page.on('console', lambda m: errors.append('console: ' + m.text[:300]) if m.type == 'error' and '401' not in m.text and '403' not in m.text and '422' not in m.text and '409' not in m.text else None)

def open_rack(page, route='design-rack'):
    page.goto(f'{BASE}/#{route}')
    page.wait_for_selector('#rk-root', timeout=30000)
    wait_js(page, "document.querySelector('#rk-metrics dd')?.textContent !== '—'", timeout=30000)

def exact(page): page.wait_for_selector('#rk-state.is-exact', timeout=BUILD_MS)
def clear_draft(page):
    # Settle first: tearing a page down with requests in flight is reported as an error by WebKit, though nothing is wrong.
    page.wait_for_load_state('networkidle')
    page.evaluate("try{localStorage.removeItem('ol3d-rack-draft')}catch(e){}")
def set_count(page, family, value):
    field = page.locator(f'input[data-count="{family}"]')
    field.fill(str(value)); field.blur()
    wait_js(page, "f => document.querySelector(`[data-family=\"${f[0]}\"] input`).value == f[1]", arg=[family, str(value)])
    page.wait_for_timeout(500)
def plan_of(page):
    # The page's own request: what it believes the rack to be.
    return page.evaluate("""async () => { const r = await fetch('/api/racks/plan', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(JSON.parse(localStorage.getItem('ol3d-rack-draft')).config)}); return r.json(); }""")
def choose(page, name, value):
    """Click a choice the way a person does: its visible label, not the hidden radio inside it."""
    page.locator(f'label:has(input[name="{name}"][value="{value}"])').click()
    wait_js(page, "a => document.querySelector(`input[name=\"${a[0]}\"][value=\"${a[1]}\"]`)?.checked", arg=[name, value], timeout=5000)
def advanced(page):
    if page.get_attribute('#rk-advanced-toggle', 'aria-expanded') != 'true': page.click('#rk-advanced-toggle')
    page.wait_for_selector('#rk-advanced:not([hidden])', timeout=3000)
def open_editor(page):
    if page.evaluate("document.querySelector('#rk-root').classList.contains('is-phone')"):
        page.locator('.rk-rows [data-sheet="rk-layout-section"]').click(); page.wait_for_selector('#rk-bs[open]', timeout=3000)
    page.click('#rk-edit-layout'); page.wait_for_selector('.rk-pos[role=button]', timeout=8000)
def overflow(page): return page.evaluate('document.documentElement.scrollWidth - innerWidth')
def login(page, email):
    page.goto(BASE + '/#home'); page.wait_for_load_state('networkidle')
    status = page.evaluate("""async ([email, password]) => (await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email, password})})).status""", [email, PASSWORD])
    assert status == 200, f'sign-in returned {status}'
    page.reload(); page.wait_for_load_state('networkidle')

def visitor_journey(browser, engine):
    context = browser.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='light')
    page = context.new_page(); errors = []; watch(page, errors)
    page.goto(BASE + '/#home'); page.wait_for_selector('.hero')
    check(f'{engine}: the home page leads to the configurator', page.locator('.hero a[href="#design-rack"]').count() == 1)
    page.click('.topbar a[href="#design-rack"]'); page.wait_for_selector('#rk-root', timeout=30000)
    check(f'{engine}: a route title describes the page', 'Design Your Rack' in page.title(), page.title())
    clear_draft(page); page.reload(); open_rack(page)
    # Quantities
    set_count(page, 'conical-50', 15); set_count(page, 'conical-15', 5); set_count(page, 'micro-1.5', 0)
    plan = plan_of(page)
    check(f'{engine}: changing quantities replans', plan['ok'] and len(plan['tubes']) == 20, str(plan.get('issues')))
    wait_js(page, "document.querySelector('#rk-metrics').innerText.includes('20 tubes')", timeout=8000)
    check(f'{engine}: the page shows the plan', True)
    page.inner_text('#rk-metrics')
    page.click('.rk-cell[data-family="conical-15"] [data-step="1"]'); wait_js(page, "document.querySelector('#rk-metrics').innerText.includes('21 tubes')", timeout=8000)
    check(f'{engine}: the stepper updates without reloading', True)
    page.click('.rk-cell[data-family="conical-15"] [data-step="-1"]'); wait_js(page, "document.querySelector('#rk-metrics').innerText.includes('20 tubes')", timeout=8000)
    # Presets go through the same model
    page.click('[data-preset="microtube"]'); wait_js(page, "document.querySelector('#rk-metrics').innerText.includes('24 tubes')", timeout=10000)
    check(f'{engine}: a preset fills the same controls', page.input_value('input[data-count="micro-1.5"]') == '24')
    check(f'{engine}: three clear starting points', page.locator('[data-preset]').count() == 3)
    advanced(page)
    # Style
    page.click('[data-preset="mixed-falcon"]'); wait_js(page, "document.querySelector('#rk-metrics').innerText.includes('20 tubes')", timeout=10000)
    check(f'{engine}: premium offers edge choices', page.locator('#rk-edge-row').is_visible())
    choose(page, 'rk-style', 'lightweight'); page.wait_for_timeout(600)
    check(f'{engine}: lightweight hides them', not page.locator('#rk-edge-row').is_visible())
    light = plan_of(page)['metrics']['volume_mm3']
    choose(page, 'rk-style', 'premium'); page.wait_for_timeout(600)
    check(f'{engine}: the two styles are different objects', plan_of(page)['metrics']['volume_mm3'] > 2 * light)
    # Label
    page.fill('#rk-text', 'Proserpio Lab'); page.wait_for_timeout(700)
    check(f'{engine}: a label shows its options', page.locator('#rk-face').is_visible() and page.locator('#rk-label-style-row').is_visible())
    check(f'{engine}: a label is planned as geometry', plan_of(page)['label']['text'] == 'Proserpio Lab')
    page.fill('#rk-text', 'Molecular Biology and Sample Preparation Group'); page.wait_for_timeout(700)
    problem = page.inner_text('#rk-problems')
    if 'too long' in problem:
        check(f'{engine}: an over-long label says how to fix it', 'Shorten' in problem, problem)
        check(f'{engine}: an over-long label blocks the basket with a reason', page.locator('#rk-add').is_disabled() and 'problem' in page.inner_text('#rk-why'))
    page.fill('#rk-text', 'Proserpio Lab'); page.wait_for_timeout(700)
    # Too large: named dimension, nothing scaled, no purchase
    page.fill('input[data-count="conical-50"]', '60'); page.locator('input[data-count="conical-50"]').blur()
    wait_js(page, "document.querySelector('#rk-problems').innerText.includes('for the currently available printers')", timeout=10000)
    check(f'{engine}: an oversized rack explains itself in plain words and cannot be bought', page.locator('#rk-add').is_disabled() and page.locator('#rk-buy').is_disabled() and 'reducing the number of tubes' in page.inner_text('#rk-problems') and page.inner_text('#rk-why') != '')
    open_editor(page); page.wait_for_selector('.rk-limit', timeout=5000)
    check(f'{engine}: the layout editor shows the printable area', page.locator('.rk-limit').count() == 1)
    page.click('#rk-done'); page.wait_for_timeout(500)
    check(f'{engine}: looking at the layout and changing nothing keeps it automatic', page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.mode") == 'auto')
    # Undo through a keyboard shortcut restores the previous design
    page.locator('#rk-h-tubes').click()
    page.keyboard.press('Control+z'); wait_js(page, "document.querySelector('input[data-count=\"conical-50\"]').value == '15'", timeout=5000)
    check(f'{engine}: undo restores the previous design', True)
    # Manual mode, at real size, with keyboard alternatives
    set_count(page, 'conical-15', 0); set_count(page, 'conical-50', 4)
    open_editor(page)
    check(f'{engine}: Edit layout opens the top view with each position', page.locator('.rk-pos').count() == 4)
    check(f'{engine}: the rack stays in view in 3D while editing', page.locator('#rk-edit-rail #rk-view-3d').is_visible())
    radius = lambda i: float(page.locator(f'.rk-pos[data-i="{i}"] .rk-pos-bore').get_attribute('r'))
    check(f'{engine}: positions are drawn at their real size', abs(radius(0) * 2 - 30.9) < .3, str(radius(0)))
    first = page.locator('.rk-pos[data-i="0"]')
    first.focus(); page.keyboard.press('ArrowRight'); page.wait_for_timeout(300)
    config = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions")
    start = config[0]['x']
    page.keyboard.press('Shift+ArrowLeft'); page.wait_for_timeout(300)
    moved = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions")[0]['x']
    check(f'{engine}: arrow keys move a position', abs(moved - (start - 5)) < .01, f'{start} {moved}')
    check(f'{engine}: the arrow pad appears for a selection', page.locator('#rk-nudge').is_visible())
    # Drag one onto another: refused visibly and in words
    box_a, box_b = page.locator('.rk-pos[data-i="1"]').bounding_box(), page.locator('.rk-pos[data-i="0"]').bounding_box()
    page.mouse.move(box_a['x'] + box_a['width'] / 2, box_a['y'] + box_a['height'] / 2); page.mouse.down()
    page.mouse.move(box_b['x'] + box_b['width'] * .5 + box_b['width'] * .62, box_b['y'] + box_b['height'] / 2 + 3, steps=6)
    check(f'{engine}: dragging against another shows the conflict at once', page.locator('.rk-pos.is-bad').count() >= 2)
    page.mouse.up(); wait_js(page, "/overlap|wall|touch/.test(document.querySelector('#rk-problems').innerText)", timeout=8000)
    check(f'{engine}: an overlap is refused in words', page.locator('#rk-add').is_disabled())
    page.click('[data-act=undo]'); wait_js(page, "!/overlap/.test(document.querySelector('#rk-problems').innerText)", timeout=8000)
    check(f'{engine}: undo removes the conflict', True)
    # Dropped onto another tube, the two change places.
    before = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions")
    box_a, box_b = page.locator('.rk-pos[data-i="1"]').bounding_box(), page.locator('.rk-pos[data-i="0"]').bounding_box()
    page.mouse.move(box_a['x'] + box_a['width'] / 2, box_a['y'] + box_a['height'] / 2); page.mouse.down()
    page.mouse.move(box_b['x'] + box_b['width'] / 2 + 1, box_b['y'] + box_b['height'] / 2 + 1, steps=6)
    check(f'{engine}: a swap is previewed', page.locator('.rk-pos.is-swap').count() == 1)
    page.mouse.up(); page.wait_for_timeout(400)
    after = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions")
    check(f'{engine}: dropped on another tube, the two swap', after[1]['x'] == before[0]['x'] and after[1]['y'] == before[0]['y'] and after[0]['x'] == before[1]['x'], f'{before[:2]} {after[:2]}')
    # Several at once: a box across empty space selects them.
    sheet = page.locator('#rk-svg').bounding_box()
    page.mouse.move(sheet['x'] + 14, sheet['y'] + 14); page.mouse.down(); page.mouse.move(sheet['x'] + sheet['width'] - 14, sheet['y'] + sheet['height'] - 14, steps=4); page.mouse.up(); page.wait_for_timeout(200)
    check(f'{engine}: dragging across empty space selects a group', page.locator('.rk-pos.is-picked').count() == 4 and 'positions' in page.inner_text('#rk-picked'))
    page.keyboard.press('Escape'); page.wait_for_timeout(150)
    check(f'{engine}: Escape clears the selection', page.locator('.rk-pos.is-picked').count() == 0)
    # Add by choosing a tube, then clicking
    page.click('[data-arm="micro-1.5-generic"]')
    page.mouse.click(sheet['x'] + 12, sheet['y'] + sheet['height'] / 2); wait_js(page, "document.querySelectorAll('.rk-pos').length === 5", timeout=5000)
    check(f'{engine}: a tube can be placed by clicking', True)
    page.keyboard.press('Escape')
    page.locator('.rk-pos').last.focus(); page.keyboard.press('Delete'); wait_js(page, "document.querySelectorAll('.rk-pos').length === 4", timeout=5000)
    check(f'{engine}: Delete removes a position', True)
    # A suggestion is offered, never imposed.
    mine = page.evaluate("JSON.stringify(JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions)")
    page.click('[data-act=optimize]'); page.wait_for_selector('#rk-suggest:not([hidden])', timeout=8000)
    check(f'{engine}: a suggested layout says what it would change and changes nothing yet', 'mm' in page.inner_text('#rk-suggest-text') and page.evaluate("JSON.stringify(JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions)") == mine)
    page.click('[data-act=use-suggestion]'); page.wait_for_timeout(900)
    check(f'{engine}: the suggestion leaves a valid layout', plan_of(page)['ok'])
    page.click('[data-act=automatic]'); page.wait_for_timeout(600)
    check(f'{engine}: returning to automatic keeps the tubes', page.input_value('input[data-count="conical-50"]') == '4')
    # The exact model, and materials
    exact(page)
    check(f'{engine}: the exact model replaces the quick preview', 'Measured on the model' in page.inner_text('#rk-metrics'))
    check(f'{engine}: price is not called final before checkout', page.locator('#rk-metrics [title*="confirmed at checkout"]').count() == 1)
    names = [e.get_attribute('value') for e in page.locator('input[name=rk-material]').all()]
    check(f'{engine}: materials come from host stock', set(names) == {'PLA', 'PETG'}, str(names))
    {m: None for m in names}
    choose(page, 'rk-material', 'PETG'); page.wait_for_timeout(200)
    petg = {e.get_attribute('value') for e in page.locator('input[name=rk-color]').all()}
    check(f'{engine}: colours follow the chosen material', petg == {'black', 'orange'}, str(petg))
    price_petg = page.inner_text('#rk-bar-price')
    choose(page, 'rk-material', 'PLA'); page.wait_for_timeout(200)
    check(f'{engine}: the price follows the material', page.inner_text('#rk-bar-price') != price_petg)
    # A visitor is sent to sign in, and keeps the design
    page.click('#rk-add'); wait_js(page, "location.hash === '#account'", timeout=5000)
    check(f'{engine}: a visitor signs in to buy', True)
    draft = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft'))")
    check(f'{engine}: the design waits for them', draft['config']['style'] == 'premium' and draft['config']['label']['text'] == 'Proserpio Lab')
    # Signing in on that page brings them back to the same design.
    page.wait_for_selector('#real-login', timeout=8000)
    page.fill('#real-login input[name=email]', 'buyer@example.org'); page.fill('#real-login input[name=password]', PASSWORD)
    page.locator('#real-login button[type=submit], #real-login button:not([type=button])').first.click()
    wait_js(page, "location.hash === '#design-rack'", timeout=10000); page.wait_for_selector('#rk-root', timeout=10000)
    check(f'{engine}: signing in returns to the design', page.input_value('#rk-text') == 'Proserpio Lab')
    page.evaluate("fetch('/api/auth/me').then(r => r.json()).then(d => fetch('/api/auth/logout', {method: 'POST', headers: {'X-CSRF-Token': d.csrf_token}}))")
    check(f'{engine}: no errors in the visitor journey', not errors, str(errors[:5]))
    context.close()

def buyer_and_host(browser, engine):
    context = browser.new_context(viewport={'width': 1366, 'height': 860}, color_scheme='dark')
    page = context.new_page(); errors = []; watch(page, errors)
    login(page, 'buyer@example.org'); page.wait_for_selector('.topbar a[href="#design-rack"]')
    page.goto(BASE + '/#design-rack'); page.wait_for_selector('#rk-root', timeout=30000); clear_draft(page); page.reload(); open_rack(page)
    label = 'QA ' + secrets.token_hex(2).upper()
    set_count(page, 'conical-50', 2); set_count(page, 'conical-15', 2); set_count(page, 'micro-1.5', 0)
    page.fill('#rk-text', label); page.wait_for_timeout(600)
    name = f'{engine} rack {secrets.token_hex(2)}'
    page.fill('#rk-name', name); page.click('#rk-save')
    wait_js(page, "/^#design-rack\\/\\d+$/.test(location.hash)", timeout=8000)
    design = re.search(r'(\d+)$', page.evaluate('location.hash')).group(1)
    check(f'{engine}: a design is saved', page.inner_text('#rk-save-label') == 'Save changes')
    page.goto(BASE + '/#my-designs'); page.wait_for_selector('.rk-design', timeout=10000)
    card = page.locator('.rk-design', has_text=name)
    check(f'{engine}: My designs lists it', card.count() == 1 and '2 × 50 mL' in card.inner_text())
    card_id = card.get_attribute('data-id')
    held = page.locator(f'.rk-design[data-id="{card_id}"]')     # its text changes while it is being renamed
    held.locator('[data-rename]').click(); held.locator('form input').fill(name + ' renamed'); held.locator('form button').click()
    page.wait_for_selector(f'.rk-design:has-text("{name} renamed")', timeout=5000)
    check(f'{engine}: a design can be renamed', True)
    page.locator('.rk-design', has_text=name).locator('[data-duplicate]').click()
    page.wait_for_selector(f'.rk-design:has-text("{name} renamed copy")', timeout=5000)
    check(f'{engine}: a design can be duplicated', True)
    copy = page.locator('.rk-design', has_text=f'{name} renamed copy')
    copy.locator('[data-delete]').click(); copy.locator('[data-confirm-delete]').click()
    wait_js(page, "n => ![...document.querySelectorAll('.rk-design')].some(e => e.innerText.includes(n))", arg=f'{name} renamed copy', timeout=5000)
    check(f'{engine}: a draft can be deleted after confirming', True)
    # Reopen, and the exact selections are there; then edit it
    page.locator('.rk-design', has_text=name).locator('h2 a').click(); page.wait_for_selector('#rk-root', timeout=10000); wait_js(page, "document.querySelector('#rk-metrics dd')?.textContent !== '—'", timeout=20000)
    check(f'{engine}: reopening restores the design', page.input_value('input[data-count="conical-15"]') == '2' and page.input_value('#rk-text') == label and page.input_value('#rk-name').endswith('renamed'))
    exact(page)
    choose(page, 'rk-material', 'PETG'); page.wait_for_timeout(200)
    choose(page, 'rk-color', 'orange'); page.wait_for_timeout(200)
    shown = page.inner_text('#rk-bar-price')
    page.click('#rk-add'); page.wait_for_selector('#rk-add.is-added', timeout=15000)
    check(f'{engine}: the rack joins the basket', True)
    page.goto(BASE + '/#basket'); page.wait_for_selector('.cart-line', timeout=10000)
    line = page.locator('.cart-line', has_text='Custom rack')
    check(f'{engine}: the basket shows it at the quoted price', line.count() >= 1 and shown in line.first.inner_text(), line.first.inner_text() if line.count() else 'no line')
    check(f'{engine}: the basket keeps the exact material and colour', 'PETG' in line.first.inner_text() and 'Orange' in line.first.inner_text())
    wait_js(page, "document.querySelector('.cart-line .row-thumb img')?.complete", timeout=10000)
    check(f'{engine}: the basket shows its picture', page.evaluate("document.querySelector('.cart-line .row-thumb img').naturalWidth") > 0)
    page.click('a[href="#checkout-cart"]'); page.wait_for_selector('#checkout-form', timeout=10000)
    for key, value in (('first_name', 'Test'), ('last_name', 'Buyer'), ('phone', '+39 011 1234567')):
        if not page.input_value(f'#checkout-form [name={key}]'): page.fill(f'#checkout-form [name={key}]', value)
    page.click('#checkout-form .summary-card .primary'); wait_js(page, "location.hash === '#orders'", timeout=15000)
    check(f'{engine}: checkout places the order', True)
    page.wait_for_selector('.bo-card', timeout=10000)
    order_text = page.locator('.bo-card').first.inner_text()
    check(f'{engine}: the order shows what the rack is', 'Custom rack' in order_text and label in order_text, order_text[:300])
    # Edit the design afterwards: the order stays as bought.
    page.goto(f'{BASE}/#design-rack/{design}'); page.wait_for_selector('#rk-root', timeout=10000); wait_js(page, "document.querySelector('#rk-metrics dd')?.textContent !== '—'", timeout=20000)
    set_count(page, 'conical-50', 3); page.click('#rk-save'); page.wait_for_timeout(800)
    orders = page.evaluate("fetch('/api/orders').then(r => r.json())")
    bought = next(o for o in orders if any(label in json.dumps(i.get('rack')) for i in o['items']))
    check(f'{engine}: editing a design leaves the order alone', bought['items'][0]['rack']['tubes'][0]['quantity'] == 2)
    page.goto(BASE + '/#my-designs'); page.wait_for_selector('.rk-ordered', timeout=10000)
    check(f'{engine}: a design remembers what was ordered', 'Ordered' in page.locator('.rk-design', has_text=name).inner_text())
    check(f'{engine}: no errors for the buyer', not errors, str(errors[:5]))
    job = bought['jobs'][0]['id']
    context.close()
    # The host who can print it
    context = browser.new_context(viewport={'width': 1366, 'height': 860}, accept_downloads=True)
    page = context.new_page(); errors = []; watch(page, errors)
    login(page, 'host@example.org')
    listed = page.evaluate("fetch('/api/host/jobs').then(r => r.json())")
    check(f'{engine}: an eligible host sees the job', any(j['id'] == job for j in listed))
    accepted = page.evaluate("async job => { const me = await (await fetch('/api/auth/me')).json(); return (await fetch(`/api/host/jobs/${job}/accept`, {method:'POST', headers:{'X-CSRF-Token': me.csrf_token}})).status }", job)
    check(f'{engine}: the host accepts it', accepted == 200, str(accepted))
    page.goto(BASE + '/#host/jobs'); page.wait_for_selector(f'a[href="/api/jobs/{job}/cad?format=3mf"]', state='attached', timeout=15000)
    check(f'{engine}: the host is offered STL and 3MF', page.locator(f'a[href="/api/jobs/{job}/cad"]').count() >= 1)
    stl = page.evaluate("async job => { const r = await fetch(`/api/jobs/${job}/cad`); return [r.status, r.headers.get('x-content-sha256'), (await r.arrayBuffer()).byteLength]; }", job)
    check(f'{engine}: the host downloads the exact file', stl[0] == 200 and len(stl[1]) == 64 and stl[2] > 5000, str(stl))
    spec = page.evaluate("async job => (await fetch(`/api/jobs/${job}/rack`)).json()", job)
    check(f'{engine}: the host reads the specification as sold', spec['label']['text'] == label and len(spec['tubes']) == 4)
    check(f'{engine}: no errors for the host', not errors, str(errors[:5]))
    context.close()

def checkout_page(page):
    page.wait_for_selector('#checkout-form', timeout=15000)
    page.click('#checkout-form .summary-card .primary')
    wait_js(page, "location.hash === '#orders'", timeout=20000)

def api_status(page, path, method='POST'):
    return page.evaluate("""async ([path, method]) => { const me = await (await fetch('/api/auth/me')).json(); return (await fetch(path, {method, headers: {'X-CSRF-Token': me.csrf_token}})).status }""", [path, method])

def buy_now_and_eligibility(browser, engine):
    """The whole marketplace path for a rack only the larger printer can make, in a finish only one host stocks."""
    context = browser.new_context(viewport={'width': 1366, 'height': 860}); page = context.new_page(); errors = []; watch(page, errors)
    login(page, 'buyer@example.org')
    page.goto(BASE + '/#design-rack'); page.wait_for_selector('#rk-root', timeout=30000); clear_draft(page); page.reload(); open_rack(page)
    set_count(page, 'conical-50', 15); set_count(page, 'conical-15', 5); set_count(page, 'micro-1.5', 0)
    # Black PLA is the one finish both hosts stock, so both printers' areas are on offer.
    wait_js(page, "document.querySelector('input[name=rk-color][value=black]')", timeout=10000); choose(page, 'rk-material', 'PLA'); choose(page, 'rk-color', 'black')
    advanced(page)
    wait_js(page, "document.querySelector('#rk-envelope').textContent.includes('170')", timeout=8000)
    options = page.locator('#rk-envelope option').all_inner_texts()
    check(f'{engine}: printing areas come from real printers', any('246' in o for o in options) and any('170' in o for o in options), str(options))
    page.select_option('#rk-envelope', '180,180,180')
    wait_js(page, "document.querySelector('#rk-problems').innerText.includes('printing area you chose')", timeout=8000)
    check(f'{engine}: a printing area too small for the tubes blocks buying and explains', page.locator('#rk-buy').is_disabled() and page.locator('#rk-add').is_disabled())
    page.select_option('#rk-envelope', '256,256,256'); wait_js(page, "!document.querySelector('#rk-problems').innerText.includes('printing area you chose')", timeout=8000)
    label = 'E2E ' + secrets.token_hex(2).upper()
    page.fill('#rk-text', label); page.fill('#rk-name', f'Journey {label}'); page.wait_for_timeout(600)
    exact(page)
    choose(page, 'rk-material', 'PETG'); choose(page, 'rk-color', 'orange')
    wait_js(page, "document.querySelector('#rk-finish').innerText.includes('can print this rack in PETG')", timeout=8000)
    check(f'{engine}: the compatible hosts are counted for this exact finish', '1 host' in page.inner_text('#rk-finish'), page.inner_text('#rk-finish'))
    options = page.locator('#rk-envelope option').all_inner_texts()
    check(f'{engine}: printers without this finish leave the printing areas', not any('170' in o for o in options), str(options))
    check(f'{engine}: the price says it is a prototype price', 'Prototype price' in page.inner_text('#rk-metrics') and page.locator('#rk-metrics [title*="prototype manufacturing price"]').count() == 1)
    check(f'{engine}: the prototype notice is on the page', 'not yet been physically validated' in page.inner_text('#rk-root'))
    wait_js(page, "!document.querySelector('#rk-buy').disabled", timeout=30000)
    shown = page.inner_text('#rk-bar-price')
    page.click('#rk-buy'); page.wait_for_selector('#checkout-form', timeout=20000)
    summary = page.inner_text('#checkout-form .summary-card')
    check(f'{engine}: Buy Now reaches checkout at the shown price, named', shown in summary and 'Custom rack' in summary, summary[:200])
    checkout_page(page)
    page.wait_for_selector('.bo-card', timeout=15000)
    orders = page.evaluate("fetch('/api/orders').then(r => r.json())")
    bought = next(o for o in orders if any(label in json.dumps(i.get('rack')) for i in o['items']))
    item, job = bought['items'][0], bought['jobs'][0]['id']
    check(f'{engine}: the order is real and keeps the finish', item['material'] == 'PETG' and item['color'] == 'orange' and shown.replace('€', '') in f"{item['price_cents'] / 100:.2f}")
    check(f'{engine}: the order names the rack', item['rack']['name'] == f'Journey {label}' and item['rack']['label']['text'] == label)
    card = page.locator('.bo-card', has_text=bought['reference'])
    check(f'{engine}: My Orders shows a picture and what the rack is', 'Custom rack' in card.inner_text() and card.locator('img').count() >= 1, card.inner_text()[:200])
    public = page.evaluate("fetch('/api/listings?per_page=50').then(r => r.json())")
    check(f'{engine}: the rack is not in the public catalogue', not any(i['id'] == item['listing_id'] for i in public['items']) and all('Custom rack' not in i['title'] for i in public['items']))
    page.goto(BASE + '/#catalogue'); page.wait_for_selector('.rack-promo', timeout=15000)
    check(f'{engine}: the catalogue page lists no custom rack', 'Custom rack:' not in page.inner_text('#app'))
    page.goto(BASE + '/#orders'); page.wait_for_selector('.bo-card', timeout=15000)
    # Reorder: today's hosts and price, through the basket.
    again = page.evaluate("""async item => { const me = await (await fetch('/api/auth/me')).json(); const r = await fetch(`/api/racks/orders/${item}/reorder`, {method: 'POST', headers: {'X-CSRF-Token': me.csrf_token}}); return [r.status, await r.json()]; }""", item['id'])
    check(f'{engine}: Reorder revalidates the same rack and finish', again[0] == 200 and again[1]['listing_id'] == item['listing_id'] and again[1]['color'] == 'orange')
    check(f'{engine}: no errors on the buyer journey', not errors, str(errors[:4]))
    context.close()
    # A host whose printer is too small, and who lacks the colour: not offered it, and refused if it asks anyway.
    context = browser.new_context(viewport={'width': 1366, 'height': 860}); page = context.new_page(); errors = []; watch(page, errors)
    login(page, 'smallhost@example.org')
    jobs = page.evaluate("fetch('/api/host/jobs').then(r => r.json())")
    check(f'{engine}: an incompatible host is not offered the job', not any(j['id'] == job for j in jobs))
    check(f'{engine}: the backend refuses a direct acceptance', api_status(page, f'/api/host/jobs/{job}/accept') == 403)
    check(f'{engine}: an unassigned host cannot download the model', page.evaluate("async j => (await fetch(`/api/jobs/${j}/cad`)).status", job) == 404 and page.evaluate("async j => (await fetch(`/api/jobs/${j}/cad?format=3mf`)).status", job) == 404)
    context.close()
    # The host who can make it.
    context = browser.new_context(viewport={'width': 1366, 'height': 860}); page = context.new_page(); errors = []; watch(page, errors)
    login(page, 'host@example.org')
    page.goto(BASE + '/#host/jobs'); opener = page.locator(f'[data-job-details="{job}"]').first; opener.wait_for(timeout=20000); opener.click()
    page.wait_for_selector('dialog[open]', timeout=8000)
    dialog = page.inner_text('dialog[open]').lower()
    check(f'{engine}: the host sees the full specification', all(x.lower() in dialog for x in (label, '15 × 50 mL conical', 'PETG', 'Print upright', 'Estimated plastic')), dialog[:500])
    page.keyboard.press('Escape')
    check(f'{engine}: the compatible host accepts', api_status(page, f'/api/host/jobs/{job}/accept') == 200)
    files = page.evaluate("""async j => { const out = {}; for (const f of ['', '?format=3mf']) { const r = await fetch(`/api/jobs/${j}/cad${f}`); const b = await r.arrayBuffer(); const h = [...new Uint8Array(await crypto.subtle.digest('SHA-256', b))].map(x => x.toString(16).padStart(2, '0')).join(''); out[f || 'stl'] = [r.status, r.headers.get('x-content-sha256'), h, b.byteLength]; } return out; }""", job) if BASE.startswith(('http://localhost', 'http://127')) else {}
    for key, (status, header, digest, size) in files.items():
        check(f'{engine}: the {key} download matches its recorded checksum', status == 200 and header == digest and size > 5000, f'{status} {size}')
    data = page.evaluate("fetch('/api/host/jobs').then(r => r.json())"); mine = next(j for j in data if j['id'] == job)
    check(f'{engine}: the file is the one pinned on the order', mine['item']['cad_sha256'] == files['stl'][1] and mine['status'] == 'accepted')
    check(f'{engine}: the job moves on through the normal stages', page.evaluate("""async j => { const me = await (await fetch('/api/auth/me')).json(); return (await fetch(`/api/host/jobs/${j}/status`, {method:'POST', headers:{'X-CSRF-Token': me.csrf_token,'Content-Type':'application/json'}, body: JSON.stringify({status:'ready'})})).status }""", job) == 200)
    check(f'{engine}: no errors for the compatible host', not errors, str(errors[:4]))
    context.close()

def basic_and_advanced(browser, engine):
    """Simple by default; the two modes are one configuration, and showing or hiding options changes nothing."""
    context = browser.new_context(viewport={'width': 1440, 'height': 900}); page = context.new_page(); errors = []; watch(page, errors)
    page.goto(BASE + '/#design-rack'); page.wait_for_selector('#rk-root', timeout=30000); clear_draft(page); page.reload(); open_rack(page)
    check(f'{engine}: Basic is the default', page.get_attribute('#rk-advanced-toggle', 'aria-expanded') == 'false' and not page.locator('#rk-advanced').is_visible())
    for selector, what in (('#rk-count-conical-50', 'tube quantities'), ('input[name=rk-style]', 'design style'), ('#rk-text', 'laboratory name'), ('#rk-buy', 'Buy now'), ('#rk-add', 'Add to basket'), ('#rk-save', 'Save design')):
        check(f'{engine}: Basic offers {what}', page.locator(selector).count() >= 1)
    check(f'{engine}: Basic hides technical choices', not any(page.locator(s).is_visible() for s in ('#rk-auto-options', '#rk-clearance', '#rk-envelope', '#rk-font')))
    check(f'{engine}: Pattern and the Automatic/By hand choice are gone', page.locator('#rk-arrangement').count() == 0 and page.locator('input[name=rk-mode]').count() == 0)
    check(f'{engine}: design cards show real renders', page.evaluate("[...document.querySelectorAll('.rk-style img')].every(i => i.complete && i.naturalWidth > 0)"))
    check(f'{engine}: tubes do not hide the rack by default', not page.is_checked('#rk-show-tubes'))
    for option in ('rk-style',):
        choose(page, option, 'premium')
    wait_js(page, "!document.querySelector('#rk-root').classList.contains('is-planning')", timeout=5000); page.wait_for_timeout(1100); exact(page); page.wait_for_load_state('networkidle')
    before = page.locator('#rk-canvas').bounding_box()
    hash_before = plan_of(page)['hash']
    seen = []; page.on('request', lambda r: seen.append(r.url) if '/api/racks' in r.url else None)
    page.evaluate("document.querySelector('#rk-advanced-toggle').click()"); page.wait_for_timeout(500)     # without Playwright scrolling to it, which would move a sticky element
    after = page.locator('#rk-canvas').bounding_box()
    check(f'{engine}: opening Advanced does not move the preview', all(abs(before[k] - after[k]) < 1 for k in before), f'{before} {after}')
    check(f'{engine}: opening Advanced does not plan or build again', not seen, str(seen[:3]))
    choose(page, 'rk-spacing', 'roomy')
    page.fill('#rk-text', 'Mode Test'); page.wait_for_timeout(500)
    page.select_option('#rk-font', 'serif'); page.select_option('#rk-size', '10'); page.select_option('#rk-clearance', '0.2')
    page.wait_for_timeout(700)
    wanted = plan_of(page)['hash']
    check(f'{engine}: Advanced values reach the real CAD', wanted != hash_before)
    check(f'{engine}: the toggle says how many values differ', 'changed' in page.inner_text('#rk-advanced-toggle'))
    page.click('#rk-advanced-toggle'); page.wait_for_timeout(300)
    check(f'{engine}: hidden options stay in force', plan_of(page)['hash'] == wanted and 'changed' in page.inner_text('#rk-advanced-toggle'))
    page.click('#rk-advanced-toggle'); page.wait_for_timeout(200)
    check(f'{engine}: reopening shows the same values', page.is_checked('input[name=rk-spacing][value=roomy]') and page.input_value('#rk-font') == 'serif' and page.input_value('#rk-size') == '10' and page.input_value('#rk-clearance') == '0.2')
    page.reload(); open_rack(page)
    check(f'{engine}: a reload keeps the mode and the values', page.get_attribute('#rk-advanced-toggle', 'aria-expanded') == 'true' and page.is_checked('input[name=rk-spacing][value=roomy]'))
    page.click('#rk-reset-advanced'); page.wait_for_timeout(800)
    config = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config")
    check(f'{engine}: Reset clears only advanced values', config['layout']['spacing'] == 'standard' and config['label']['font'] == 'sans' and config['clearance_adjust_mm'] == 0 and config['label']['text'] == 'Mode Test' and config['style'] == 'premium' and config['tubes'][0]['quantity'] == 24)
    open_editor(page)
    page.locator('.rk-pos[data-i="0"]').focus(); page.keyboard.press('ArrowLeft'); page.wait_for_timeout(300)
    page.click('#rk-done'); page.wait_for_timeout(300)
    page.click('#rk-advanced-toggle'); page.wait_for_timeout(300)
    check(f'{engine}: hiding Advanced keeps a hand-made layout', page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.mode") == 'manual' and 'by hand' in page.inner_text('#rk-layouts') and page.locator('#rk-view-3d').is_visible())
    page.click('#rk-auto-layout'); page.wait_for_timeout(500)
    for view in ('top', 'iso'):
        page.click(f'.rk-viewtools [data-view="{view}"]:not([aria-label])') if view == 'top' else page.click('.rk-viewtools [aria-label="Reset view"]')
    check(f'{engine}: the viewer has top, reset and full screen', page.locator('#rk-fullscreen').is_visible())
    check(f'{engine}: no errors switching modes', not errors, str(errors[:4]))
    context.close()

def layout_and_height(browser, engine):
    """The main decisions, made directly: tubes, a layout that is drawn, and a height whose limits come from the tubes."""
    context = browser.new_context(viewport={'width': 1440, 'height': 900}); page = context.new_page(); errors = []; watch(page, errors)
    page.goto(BASE + '/#design-rack'); page.wait_for_selector('#rk-root', timeout=30000); clear_draft(page); page.reload(); open_rack(page)
    drag_to = lambda value: page.locator('#rk-height').evaluate("(e, v) => { e.value = v; e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }", value)
    # A beginner: 24 x 1.5 mL, Premium, low profile, without opening anything.
    choose(page, 'rk-style', 'premium'); page.wait_for_timeout(500); exact(page)
    limits = plan_of(page)['height']
    check(f'{engine}: height shows real limits for these tubes', limits['min'] < limits['recommended'] <= limits['max'] and float(page.get_attribute('#rk-height', 'min')) == limits['min'], str(limits))
    drag_to(limits['min']); page.wait_for_timeout(700); exact(page)
    plan = plan_of(page)
    check(f'{engine}: the lowest height is what the CAD makes', abs(plan['dims'][2] - limits['min']) < .01 and abs(page.evaluate("h => fetch('/api/racks/builds/' + h).then(r => r.json())", plan['hash'])['metrics']['dims_mm'][2] - limits['min']) < .06, str(plan['dims']))
    check(f'{engine}: the panel never needed opening', page.get_attribute('#rk-advanced-toggle', 'aria-expanded') == 'false')
    check(f'{engine}: the height is explained in measurements', 'mm deep' in page.inner_text('#rk-height-note'))
    page.click('#rk-height-reset'); page.wait_for_timeout(600)
    check(f'{engine}: one action returns to the recommended height', abs(plan_of(page)['dims'][2] - limits['recommended']) < .01 and page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.height_mm") is None)
    # Undo takes back a whole slider movement in one step.
    drag_to(limits['min']); page.wait_for_timeout(300); page.locator('#rk-h-tubes').click(); page.keyboard.press('Control+z'); page.wait_for_timeout(500)
    check(f'{engine}: undo takes back the height', page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.height_mm") is None)
    # Layouts are drawn, real and different.
    page.click('[data-preset="mixed-falcon"]'); page.wait_for_timeout(700); exact(page)
    options = page.evaluate("[...document.querySelectorAll('input[name=rk-layout]')].map(e => e.value)")
    check(f'{engine}: a mixed rack is offered layouts that really differ, drawn from above', len(options) >= 2 and page.locator('.rk-layout-option svg circle').count() == 20 * len(options), str(options))
    size_before = plan_of(page)['dims']
    choose(page, 'rk-layout', options[1]); page.wait_for_timeout(700); exact(page)
    check(f'{engine}: choosing a layout changes the rack', plan_of(page)['dims'][:2] != size_before[:2])
    # A height that cannot work: explained, with the way out, and nothing is built or sold.
    seen = []; page.on('request', lambda r: seen.append(r.url) if r.method == 'POST' and r.url.endswith('/api/racks/builds') else None)
    page.fill('#rk-height-mm', '10'); page.locator('#rk-height-mm').blur(); wait_js(page, "document.querySelector('#rk-problems').innerText.includes('needs at least')", timeout=8000); page.wait_for_timeout(1000)
    limit = plan_of(page)['height']['min']
    check(f'{engine}: too low a height states the real minimum', f'{limit:g} mm' in page.inner_text('#rk-problems'), page.inner_text('#rk-problems'))
    check(f'{engine}: too low a height blocks buying and building', page.locator('#rk-buy').is_disabled() and page.locator('#rk-add').is_disabled() and not seen, str(seen))
    page.click('.rk-issue-action'); page.wait_for_timeout(700); exact(page)
    check(f'{engine}: one action moves it to the nearest height that works', abs(plan_of(page)['dims'][2] - limit) < .01 and 'needs at least' not in page.inner_text('#rk-problems'))
    # A rack cannot quietly become impossible: adding taller tubes moves the height, and says so.
    page.click('[data-preset="microtube"]'); page.wait_for_timeout(600); exact(page); low = plan_of(page)['height']['min']; drag_to(low); page.wait_for_timeout(500)
    set_count(page, 'conical-50', 2); page.wait_for_timeout(800)
    plan = plan_of(page)
    check(f'{engine}: adding taller tubes moves a low height to what they need', plan['ok'] and plan['dims'][2] >= plan['height']['min'], str(plan['issues'][:1]))
    page.evaluate("localStorage.removeItem('ol3d-rack-draft')")
    check(f'{engine}: no errors adjusting layout and height', not errors, str(errors[:3]))
    context.close()

def phone_journey(browser, engine):
    """The phone is its own way of working: a real purchase with no mouse and no desktop controls."""
    options = {'viewport': {'width': 390, 'height': 844}, 'device_scale_factor': 2}
    if engine != 'firefox': options.update(has_touch=True, is_mobile=engine == 'chromium')
    context = browser.new_context(**options); page = context.new_page(); errors = []; watch(page, errors)
    login(page, 'buyer@example.org')
    page.goto(BASE + '/#design-rack'); page.wait_for_selector('#rk-root', timeout=30000); clear_draft(page); page.reload(); open_rack(page)
    check(f'{engine} phone: it is the phone layout', page.evaluate("document.querySelector('#rk-root').classList.contains('is-phone')"))
    tap = (lambda s: page.tap(s)) if engine != 'firefox' else (lambda s: page.click(s))
    check(f'{engine} phone: the first screen has the model, the tubes and the buy button', page.locator('#rk-canvas').is_visible() and page.locator('input[data-count="micro-1.5"]').is_visible() and page.locator('#rk-buy').is_visible())
    box = page.locator('.rk-stepper button').first.bounding_box()
    check(f'{engine} phone: steppers are thumb-sized', box['height'] >= 44 and box['width'] >= 44, str(box))
    check(f'{engine} phone: nothing scrolls sideways', overflow(page) <= 0)
    # The compact model does not take gestures: a thumb on it scrolls the page.
    # This browser build may have no WebGL here; the viewer then explains itself instead.
    try: page.wait_for_selector('#rk-canvas canvas', state='attached', timeout=8000); has_3d = True
    except Exception: has_3d = False
    if has_3d: check(f'{engine} phone: the compact model leaves touches to the page', page.evaluate("getComputedStyle(document.querySelector('#rk-canvas canvas')).pointerEvents") == 'none')
    if engine == 'chromium':
        cdp = context.new_cdp_session(page); start = page.evaluate('scrollY'); area = page.locator('#rk-canvas').bounding_box()
        x, y = area['x'] + area['width'] / 2, area['y'] + area['height'] / 2
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
        for k in range(1, 11): cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y - k * 14}]}); page.wait_for_timeout(15)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); page.wait_for_timeout(400)
        check(f'{engine} phone: a swipe across the model scrolls the page, and opens nothing', page.evaluate('scrollY') > start + 40 and not page.evaluate("document.querySelector('#rk-focus').open"), f"{start} {page.evaluate('scrollY')}")
        page.evaluate('scrollTo(0, 0)'); page.wait_for_timeout(200)
    tap('#rk-fullscreen'); page.wait_for_selector('#rk-focus[open]', timeout=3000); page.wait_for_timeout(300)
    if has_3d: check(f'{engine} phone: the focused model takes gestures and fills the screen', page.evaluate("getComputedStyle(document.querySelector('#rk-canvas canvas')).pointerEvents") == 'auto' and page.locator('#rk-canvas').bounding_box()['height'] > 700)
    tap('#rk-focus-close'); page.wait_for_timeout(300)
    check(f'{engine} phone: closing brings it back, with its place kept', page.locator('.rk-stage > #rk-view-3d').count() == 1 and page.locator('#rk-canvas').bounding_box()['height'] < 300)
    # Beginner: tubes, style, low, a name. Without Advanced.
    tap('label.rk-style:has(input[value=premium])'); page.wait_for_timeout(400)
    page.locator('#rk-height').evaluate("e => { e.value = e.min; e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }"); page.wait_for_timeout(500)
    row = '.rk-rows [data-sheet="rk-label-section"]'
    page.locator(row).scroll_into_view_if_needed(); tap(row); page.wait_for_selector('#rk-bs[open]', timeout=3000)
    label = 'Phone ' + secrets.token_hex(2).upper()
    page.fill('#rk-text', label); page.wait_for_timeout(600)
    check(f'{engine} phone: the name field fills its sheet', page.locator('#rk-text').bounding_box()['width'] > 300)
    tap('#rk-bs-close'); page.wait_for_timeout(250)
    check(f'{engine} phone: closing a sheet returns the focus and keeps the value', page.evaluate("document.activeElement.dataset.sheet") == 'rk-label-section' and page.inner_text('#rk-row-name') == label)
    # Mixed rack, then a hand edit in the fullscreen editor, with no dragging.
    set_count(page, 'micro-1.5', 8); page.wait_for_timeout(500)
    page.locator('.rk-rows [data-sheet="rk-layout-section"]').scroll_into_view_if_needed(); tap('.rk-rows [data-sheet="rk-layout-section"]'); page.wait_for_selector('#rk-bs[open]', timeout=3000)
    tap('#rk-edit-layout'); page.wait_for_selector('.rk-pos[role=button]', timeout=8000); page.wait_for_timeout(400)
    stage = page.locator('.rk-stage').bounding_box()
    check(f'{engine} phone: the editor takes the whole screen', stage['height'] >= 800 and stage['y'] == 0 and not page.locator('#rk-bar-price').is_visible(), str(stage))
    page.locator('.rk-pos[data-i="0"]').click(); page.wait_for_selector('#rk-nudge:not([hidden])', timeout=3000)
    start = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions[0]")
    tap('[data-move="-1,0"]'); page.wait_for_timeout(300)
    moved = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions[0]")
    check(f'{engine} phone: the arrows move a tube, no dragging needed', moved['x'] < start['x'], f'{start} {moved}')
    if engine == 'chromium':
        at = page.locator('.rk-pos[data-i="1"]').bounding_box(); x, y = at['x'] + at['width'] / 2, at['y'] + at['height'] / 2; scrolled = page.evaluate('scrollY')
        before = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions[1]")
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
        for k in range(1, 6): cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y - k * 4}]})
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); page.wait_for_timeout(400)
        after = page.evaluate("JSON.parse(localStorage.getItem('ol3d-rack-draft')).config.layout.positions[1]")
        check(f'{engine} phone: a finger can drag a tube, and the screen does not scroll', after['y'] > before['y'] and page.evaluate('scrollY') == scrolled, f'{before} {after}')
    tap('#rk-edit-3d'); page.wait_for_timeout(300)
    if has_3d: check(f'{engine} phone: the same rack is a tap away in 3D', page.locator('#rk-canvas canvas').is_visible())
    tap('#rk-edit-3d'); page.wait_for_timeout(150)
    tap('#rk-done'); page.wait_for_timeout(400)
    check(f'{engine} phone: the edit is kept on returning', page.inner_text('#rk-row-layout') == 'By hand' and page.input_value('input[data-count="micro-1.5"]') == '8')
    exact(page); wait_js(page, "!document.querySelector('#rk-buy').disabled", timeout=30000)
    shown = page.inner_text('#rk-bar-price')
    tap('#rk-buy'); page.wait_for_selector('#checkout-form', timeout=20000)
    check(f'{engine} phone: Buy now reaches checkout at the shown price', shown in page.inner_text('#checkout-form .summary-card'))
    checkout_page(page); page.wait_for_selector('.bo-card', timeout=15000)
    orders = page.evaluate("fetch('/api/orders').then(r => r.json())")
    check(f'{engine} phone: the order is in My Orders, with its name', any(label in json.dumps(i.get('rack')) for o in orders for i in o['items']))
    check(f'{engine} phone: no errors on the journey', not errors, str(errors[:3]))
    context.close()
    # Other screens: sizes that have to work, on their side, and small.
    for w, h in ((320, 568), (360, 640), (430, 932), (844, 390)):
        context = browser.new_context(viewport={'width': w, 'height': h}); page = context.new_page(); errors = []; watch(page, errors)
        page.goto(BASE + '/#design-rack'); page.wait_for_selector('#rk-root', timeout=30000); page.wait_for_timeout(700)
        check(f'{engine} {w}x{h}: no sideways scrolling, phone layout, buy button in view', overflow(page) <= 0 and page.evaluate("document.querySelector('#rk-root').classList.contains('is-phone')") and page.locator('#rk-buy').is_visible())
        open_editor(page); page.wait_for_timeout(250)
        svg = page.locator('#rk-svg').bounding_box()
        check(f'{engine} {w}x{h}: the editor has a usable sheet, and its actions do not overlap', svg['height'] > 150 and svg['width'] > 200 and page.locator('#rk-done').is_visible() and overflow(page) <= 0, str(svg))
        page.click('#rk-done'); context.close()

def viewer_is_the_product(browser, engine):
    """What the viewer shows is the mesh of the solid the files come from, for the rack now configured, measured in the page."""
    context = browser.new_context(viewport={'width': 1366, 'height': 860}); page = context.new_page(); errors = []; watch(page, errors)
    page.goto(BASE + '/#design-rack'); page.wait_for_selector('#rk-root', timeout=30000); clear_draft(page); page.reload(); open_rack(page)
    if not page.evaluate("!!document.createElement('canvas').getContext('webgl')"):
        check(f'{engine}: this browser has no WebGL here, so the viewer comparison does not apply', True); context.close(); return
    def agree(name):
        wait_js(page, "!document.querySelector('#rk-root').classList.contains('is-planning')", timeout=8000); exact(page)
        plan = plan_of(page); build = page.evaluate("h => fetch('/api/racks/builds/' + h).then(r => r.json())", plan['hash']); shown = page.evaluate('__rackViewer.shown()')
        same = shown['kind'] == 'exact' and shown['hash'] == plan['hash'] == build['hash']
        size = all(abs(a - b) < .25 for a, b in zip(shown.get('dims', [0, 0, 0]), build['metrics']['dims_mm']))
        solid = abs(shown.get('volume', 0) - build['metrics']['volume_mm3']) < build['metrics']['volume_mm3'] * .02
        check(f'{engine}: {name}: the viewer shows the exact model of this rack, at its measured size and volume', same and size and solid, f"{shown} {build['metrics']['dims_mm']} {build['metrics']['volume_mm3']}")
    page.click('[data-preset="mixed-falcon"]'); page.wait_for_timeout(300); agree('Premium mixed')
    page.fill('#rk-text', 'Viewer Check'); page.wait_for_timeout(500); agree('Premium named')
    choose(page, 'rk-style', 'lightweight'); page.wait_for_timeout(300); agree('Lightweight')
    choose(page, 'rk-style', 'premium'); page.wait_for_timeout(300); agree('back to Premium, from the cache')
    # The label stops claiming "exact" the moment the rack changes.
    step = page.locator('.rk-cell[data-family="conical-15"] [data-step="1"]')
    step.click()
    check(f'{engine}: a change at once stops saying "Exact model"', page.evaluate("!document.querySelector('#rk-state').classList.contains('is-exact')"))
    # Quick changes: only the last one may end up on screen.
    for _ in range(4): step.click(); page.wait_for_timeout(120)
    page.wait_for_timeout(300); agree('after rapid changes')
    check(f'{engine}: no errors comparing the viewer', not errors, str(errors[:3]))
    context.close()

def screens(browser, engine):
    """Every width in both themes: no sideways scrolling, controls reachable, and a picture to inspect."""
    for theme in ('light', 'dark'):
        for size, (w, h) in SIZES.items():
            touch = size == 'mobile'
            context = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme, **({'has_touch': True} if touch and engine != 'firefox' else {}))
            page = context.new_page(); errors = []; watch(page, errors)
            open_rack(page)
            page.evaluate("t => applyTheme(t)", theme)
            for family, n in (('conical-50', 6), ('conical-15', 10), ('micro-1.5', 24), ('micro-0.5', 12)): set_count(page, family, n)
            wait_js(page, "document.querySelector('#rk-metrics').innerText.includes('52 tubes')", timeout=15000)
            page.wait_for_timeout(1400)
            check(f'{engine} {size} {theme}: no sideways scrolling', overflow(page) <= 0, str(overflow(page)))
            bar = page.locator('#rk-add').bounding_box()
            check(f'{engine} {size} {theme}: the main action is in view', bar and bar['y'] + bar['height'] <= h and bar['x'] >= 0 and bar['x'] + bar['width'] <= w, str(bar))
            small = page.evaluate("""() => [...document.querySelectorAll('.rk-stepper button, .rk-card span, .rk-chip span, .rk-style span, #rk-advanced-toggle, .rk-viewtools button, #rk-add, #rk-buy, #rk-save')].filter(e => e.offsetParent && e.getBoundingClientRect().height < 24).length""")
            check(f'{engine} {size} {theme}: targets are large enough', small == 0, str(small))
            page.screenshot(path=SHOTS / f'{engine}-{size}-{theme}-3d.png')
            if page.evaluate("document.querySelector('#rk-root').classList.contains('is-phone')"):
                page.locator('.rk-rows [data-sheet="rk-advanced-section"]').click(); page.wait_for_selector('#rk-bs[open]', timeout=3000)
                page.screenshot(path=SHOTS / f'{engine}-{size}-{theme}-advanced.png'); page.click('#rk-bs-close'); page.wait_for_timeout(150)
            else:
                advanced(page); page.screenshot(path=SHOTS / f'{engine}-{size}-{theme}-advanced.png')
            check(f'{engine} {size} {theme}: advanced options do not scroll sideways', overflow(page) <= 0, str(overflow(page)))
            open_editor(page); page.wait_for_timeout(250)
            page.screenshot(path=SHOTS / f'{engine}-{size}-{theme}-plan.png')
            check(f'{engine} {size} {theme}: the editor does not scroll sideways, and Done is in view', overflow(page) <= 0 and page.locator('#rk-done').is_visible())
            page.click('#rk-done')
            check(f'{engine} {size} {theme}: no errors', not errors, str(errors[:3]))
            context.close()

def accessibility(browser, engine):
    context = browser.new_context(viewport={'width': 1280, 'height': 800}, reduced_motion='reduce')
    page = context.new_page(); open_rack(page)
    unnamed = page.evaluate("""() => [...document.querySelectorAll('#rk-root input, #rk-root select, #rk-root button, #rk-root a')].filter(e => e.offsetParent !== null || e.type === 'radio').filter(e => { const name = (e.getAttribute('aria-label') || (e.labels && [...e.labels].map(l => l.textContent).join('')) || e.textContent || e.title || '').trim(); return !name; }).map(e => e.outerHTML.slice(0, 120))""")
    check(f'{engine}: every control has a name', not unnamed, str(unnamed[:4]))
    headings = page.evaluate("[...document.querySelectorAll('#rk-root h1, #rk-root h2')].map(h => h.tagName)")
    check(f'{engine}: one h1 and an ordered outline', headings.count('H1') == 1 and headings[0] == 'H1', str(headings))
    check(f'{engine}: a text summary carries the design', 'Lightweight' in page.inner_text('#rk-summary') or 'Premium' in page.inner_text('#rk-summary') or 'holds no tubes' in page.inner_text('#rk-summary'))
    check(f'{engine}: the positions are available as a table', page.locator('#rk-positions th[scope=row]').count() >= 1 or page.locator('#rk-positions tbody tr').count() >= 1)
    # Keyboard: Tab reaches controls in order and focus is visible.
    page.locator('#rk-count-conical-50').focus(); page.keyboard.press('Tab')
    focused = page.evaluate("document.activeElement.getAttribute('aria-label') || document.activeElement.id")
    outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    check(f'{engine}: keyboard focus moves on and shows', bool(focused) and outline != 'none', f'{focused} {outline}')
    toggle = page.locator('#rk-advanced-toggle')
    check(f'{engine}: Advanced options is a real disclosure', toggle.get_attribute('aria-expanded') == 'false' and toggle.get_attribute('aria-controls') == 'rk-advanced' and page.evaluate("document.querySelector('#rk-advanced-toggle').tagName") == 'BUTTON')
    toggle.focus(); page.keyboard.press('Enter')
    check(f'{engine}: the keyboard opens it', toggle.get_attribute('aria-expanded') == 'true' and page.locator('#rk-auto-options').is_visible())
    slider = page.locator('#rk-height')
    slider.focus(); before = page.input_value('#rk-height'); page.keyboard.press('ArrowLeft'); page.wait_for_timeout(200)
    check(f'{engine}: the height slider works from the keyboard and says what it is', page.input_value('#rk-height') != before and 'millimetres' in (slider.get_attribute('aria-valuetext') or ''))
    page.click('#rk-edit-layout'); page.wait_for_selector('.rk-pos[role=button]', timeout=8000)
    check(f'{engine}: the editor takes the keyboard focus to its heading', page.evaluate("document.activeElement.id") == 'rk-edit-title')
    check(f'{engine}: every position can be reached by keyboard', page.locator('.rk-pos[tabindex="0"]').count() == page.locator('.rk-pos').count())
    page.click('#rk-done')
    context.close()

with sync_playwright() as pw:
    for engine in ENGINES:
        options = {'args': ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader']} if engine == 'chromium' else {}
        try: browser = getattr(pw, engine).launch(**options)
        except Exception as exc:
            print(f'SKIPPED {engine}: it cannot start on this machine: {str(exc).splitlines()[0][:160]}', flush=True); skipped.append(engine); continue
        for step in (basic_and_advanced, layout_and_height, phone_journey, viewer_is_the_product, visitor_journey, buyer_and_host, buy_now_and_eligibility, accessibility, screens):
            if os.environ.get('RACK_STEPS') and step.__name__ not in os.environ['RACK_STEPS']: continue
            try: step(browser, engine)
            except Exception as exc:
                check(f'{engine}: {step.__name__} ran to the end', False, f'{type(exc).__name__}: {str(exc)[:600]}')
        browser.close()
failed = [r for r in results if not r[1]]
print(f'\n{len(results) - len(failed)} of {len(results)} checks passed' + (f'; not run in: {", ".join(skipped)}' if skipped else '') + f'; requests cancelled by page teardown: {len(teardown_cancels)}')
for name, _, detail in failed: print('FAILED', name, detail[:300])
(SHOTS / 'results.json').write_text(json.dumps([{'check': n, 'ok': o, 'detail': d} for n, o, d in results], indent=1))
sys.exit(1 if failed else 0)
