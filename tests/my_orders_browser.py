"""My Orders and branding browser check against the isolated order preview (temporary database):
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/orders_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/my_orders_browser.py OUTPUT_DIR [BASE_URL]
Set CHROME to a Chromium binary if Playwright's bundled browser is not installed."""
import json, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18100'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg)

# Mean colour of the opaque pixels of a product image, as drawn on screen.
MEAN = """img => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'); x.drawImage(img, 0, 0, 64, 64);
  const d = x.getImageData(0, 0, 64, 64).data; let r = 0, g = 0, b = 0, n = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
  return n ? [r / n, g / n, b / n] : null; }"""

def session(browser, w=1366, h=760, theme='light'):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme)
    assert ctx.request.post(BASE + '/api/auth/login', data={'email': 'buyer@example.org', 'password': 'TestPassword2026'}).ok
    page = ctx.new_page(); page.requests = []
    page.on('request', lambda r: page.requests.append(r.url.replace(BASE, '')))
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
    return ctx, page

def ready(page):
    # The list shown matches the filters in the URL and is no longer loading.
    page.wait_for_function("(() => { const f = buyerOrderFilters(), s = buyerOrdersShown; return !!s && s.category === f.category && s.sort === f.sort && s.page === f.page && !document.querySelector('#bo-results[aria-busy]'); })()")
    page.wait_for_selector('.bo-card')
    # Thumbnails on screen are recoloured and revealed; lazy ones off screen or in closed details wait.
    page.wait_for_function("[...document.querySelectorAll('.bo-thumb img[data-color]')].filter(i => i.checkVisibility() && i.getBoundingClientRect().top < innerHeight && i.getBoundingClientRect().bottom > 0).every(i => i.classList.contains('is-ready'))")

def click_chip(page, label):
    box = page.locator('#bo-toolbar .chip', has_text=label).first.bounding_box()
    page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    ctx, p = session(browser)
    p.goto(BASE + '/#orders'); ready(p)
    ok(sum('/api/orders?' in r for r in p.requests) == 1, 'initial load requests the order page once')
    ok(not any('/api/listings/' in r and '/visuals/' not in r for r in p.requests), 'no per-product listing requests for previews')

    # Configuration: the newest order (OL3D-QA-1015) has three lines with different colours.
    card = p.locator('.bo-card', has_text='OL3D-QA-1015')
    p.locator('#bo-toolbar').scroll_into_view_if_needed()
    swatches = card.locator('.bo-products').first.locator('.bo-swatch')
    ok(swatches.count() == 2, 'card preview lines each show their purchased colour swatch')
    ok(card.locator('.bo-config').first.inner_text() == 'PLA · Orange', 'material and colour name are shown together')
    ok(p.evaluate("getComputedStyle(document.querySelector('[data-order-id] .bo-swatch')).backgroundColor") == 'rgb(230, 97, 0)', 'swatch uses the checkout snapshot #e66100')
    imgs = card.locator('.bo-products').first.locator('img')
    orange, black = [imgs.nth(i).evaluate(MEAN) for i in range(2)]
    ok(orange and orange[0] > orange[2] + 40, f'orange line preview is tinted orange {orange and [round(v) for v in orange]}')
    ok(black and max(black) < 90, f'black line preview is tinted dark {black and [round(v) for v in black]}')
    ok(all(imgs.nth(i).evaluate("i => i.src.startsWith('data:image/')") for i in range(2)), 'previews are recoloured in the browser, not new renders')
    card.locator('summary').click()
    detail = card.locator('.bo-detail-body'); detail.scroll_into_view_if_needed(); ready(p)
    lines = detail.locator('.bo-product')
    ok(lines.count() == 3, 'order details list all three products')
    violet = lines.nth(2)
    ok(violet.locator('.bo-config').inner_text() == 'PLA · Custom violet' and violet.locator('.bo-swatch').count() == 0, 'line without a snapshot shows its recorded colour name and no invented swatch')
    ok(violet.locator('.bo-thumb[aria-label="Product preview unavailable"]').count() == 1, 'removed product falls back to a labelled placeholder')
    ok(detail.locator('.bo-job .bo-config').count() == 3, 'fulfilment rows repeat each line configuration')
    p.screenshot(path=str(OUT / 'orders-detail-1366-light.png'), full_page=True)

    # Legacy orders (before snapshots): neutral preview + recorded name, never a guessed colour.
    p.goto(BASE + '/#orders?category=all&sort=oldest&page=1'); ready(p)
    legacy = p.locator('.bo-card').first
    ok(legacy.locator('.bo-swatch').count() == 0 and 'PLA · Orange' in legacy.inner_text(), 'legacy order shows the colour name without a swatch')
    ok(legacy.locator('img').first.evaluate("i => !i.dataset.color && !i.src.startsWith('data:')"), 'legacy order keeps the neutral product render')

    # Filters: in place, one request, no scroll jump, highlighted immediately.
    p.goto(BASE + '/#orders?category=all&sort=newest&page=1'); ready(p)
    p.evaluate("window.__page = document.querySelector('.bo-page'); const t = document.querySelector('#bo-toolbar'); scrollTo(0, t.getBoundingClientRect().top + scrollY - 90)")
    # Slow the order API down so the in-between state can be observed.
    p.evaluate("(() => { const f = window.fetch; window.fetch = (u, o) => String(u).includes('/api/orders?') ? new Promise(r => setTimeout(r, 500)).then(() => f(u, o)) : f(u, o); })()")
    for label, category, statuses in (('Pending', 'pending', {'Awaiting host acceptance', 'Accepted · awaiting printing'}),
                                      ('In progress', 'in-progress', {'Production in progress', 'Ready for delivery'}),
                                      ('Completed', 'completed', {'Completed'}), ('Cancelled', 'cancelled', {'Cancelled'})):
        y = p.evaluate('scrollY'); p.requests.clear()
        click_chip(p, label)
        p.wait_for_function(f"document.querySelector('#bo-toolbar .chip[aria-current]').textContent.startsWith('{label}')", timeout=400)
        p.wait_for_timeout(250)
        busy = p.evaluate("[!!document.querySelector('#bo-results[aria-busy=true]'), document.querySelectorAll('.bo-card').length, getComputedStyle(document.querySelector('#bo-results')).opacity]")
        ok(busy[0] and busy[1] > 0 and float(busy[2]) < .9, f'{label}: highlighted at once; previous orders stay, dimmed, while loading {busy}')
        ready(p)
        api = [r for r in p.requests if '/api/' in r]
        shown = set(p.locator('.bo-card-head .status').all_inner_texts())
        ok(api == [f'/api/orders?category={category}&sort=newest&page=1&paginated=true&per_page=10'], f'{label}: exactly one API request {api}')
        ok(p.evaluate('window.__page === document.querySelector(".bo-page")'), f'{label}: page kept, not rebuilt')
        ok(abs(p.evaluate('scrollY') - y) < 2, f'{label}: scroll position kept ({y} -> {p.evaluate("scrollY")})')
        ok(shown and shown <= statuses, f'{label}: only {category} orders shown {shown}')
    ok(len(set(p.locator('.bo-card').evaluate_all('cs => cs.map(c => Math.round(c.getBoundingClientRect().width))'))) == 1, 'order cards keep one width')

    # History: back and forward restore filters without reloading the page.
    p.go_back(); ready(p)
    ok('category=completed' in p.url and p.locator('#bo-toolbar .chip[aria-current]').inner_text().startswith('Completed'), 'Back restores the previous filter')
    p.go_forward(); ready(p)
    ok('category=cancelled' in p.url and p.locator('#bo-toolbar .chip[aria-current]').inner_text().startswith('Cancelled'), 'Forward restores the next filter')
    ok(p.evaluate('window.__page === document.querySelector(".bo-page")'), 'history navigation keeps the page')

    # Rapid switching: the last choice wins, earlier responses are discarded.
    for label in ('All orders', 'Pending', 'In progress'):
        click_chip(p, label)
    ready(p); p.wait_for_timeout(400)
    ok('category=in-progress' in p.url and set(p.locator('.bo-card-head .status').all_inner_texts()) <= {'Production in progress', 'Ready for delivery'}, 'rapid clicks settle on the last filter')

    # Sort and pages.
    click_chip(p, 'All orders'); ready(p)
    p.select_option('#bo-sort', 'oldest'); ready(p)
    ok(p.locator('.bo-card h2').first.inner_text() == 'OL3D-QA-1001', 'oldest-first sort')
    ok(p.locator('#bo-sort').evaluate('s => s.value') == 'oldest', 'sort control keeps its value')
    p.evaluate("scrollTo(0, document.body.scrollHeight)"); p.locator('.bo-pagination a', has_text='Next').click(); ready(p)
    ok('page=2' in p.url and p.locator('.bo-pagination').inner_text().count('Page 2 of 2') == 1, 'Next opens page 2')
    ok(p.evaluate("document.querySelector('#bo-toolbar').getBoundingClientRect().top") >= 0, 'a new page scrolls back to the list start')
    p.reload(); ready(p)
    ok(p.locator('#bo-toolbar .chip[aria-current]').inner_text().startswith('All orders') and p.locator('#bo-sort').evaluate('s => s.value') == 'oldest', 'reload keeps filter and sort')

    # Branding: the light lockup in Bright mode, the reversed one in Dark mode; favicon from the new mark.
    def logo_state(page):
        return page.evaluate("""() => [...document.querySelectorAll('.brand-logo')].map(i => [i.closest('header,footer').tagName, i.classList.contains('brand-logo-dark'), getComputedStyle(i).display !== 'none', i.naturalWidth, Math.round(i.getBoundingClientRect().width), Math.round(i.getBoundingClientRect().height)])""")
    p.evaluate("applyTheme('light')"); p.evaluate("scrollTo(0, document.body.scrollHeight)"); p.wait_for_timeout(300)
    light = logo_state(p)
    ok(all(v == (not dark) for _, dark, v, *_ in light), f'Bright: only the light lockup is displayed {light}')
    ok(all(nat > 0 and abs(w / h - 431 / 96) < .08 for _, dark, v, nat, w, h in light if v), 'logo keeps its aspect ratio')
    p.evaluate("applyTheme('dark')"); p.wait_for_timeout(300)
    dark_state = logo_state(p)
    ok(all(v == dark for _, dark, v, *_ in dark_state) and all(nat > 0 for _, _, v, nat, *_ in dark_state if v), f'Dark: only the reversed lockup is displayed {dark_state}')
    ok(p.evaluate("document.querySelector('link[rel=icon]').href.endsWith('/assets/brand/favicon-32.png')"), 'favicon uses the new mark')
    ok(not any('openlabs3d-logo.png' in r for r in p.requests), 'the old 1.1 MB logo is no longer requested')
    p.evaluate("scrollTo(0, 0)"); p.screenshot(path=str(OUT / 'orders-1366-dark.png'), full_page=True)
    ctx.close()

    for width, theme in ((820, 'light'), (390, 'light'), (390, 'dark'), (820, 'dark')):
        ctx, p = session(browser, width, 900, theme)
        p.goto(BASE + '/#orders?category=all&sort=newest&page=1'); ready(p); p.evaluate(f"applyTheme('{theme}')")
        p.locator('.bo-card', has_text='OL3D-QA-1015').locator('summary').click(); p.wait_for_timeout(200)
        overflow = p.evaluate('document.documentElement.scrollWidth - innerWidth')
        ok(overflow <= 0, f'{width} {theme}: no horizontal overflow ({overflow})')
        top = p.evaluate("(() => { const t = document.querySelector('#topbar'), l = [...t.querySelectorAll('.brand-logo')].find(i => getComputedStyle(i).display !== 'none'), r = l.getBoundingClientRect(); return [Math.round(r.height), r.right <= t.querySelector('.topbar-actions').getBoundingClientRect().left + 1] })()")
        ok(top[0] >= 24 and top[1], f'{width} {theme}: topbar logo {top[0]} px tall, clear of the actions')
        p.screenshot(path=str(OUT / f'orders-{width}-{theme}.png'), full_page=True)
        ctx.close()
    browser.close()
print('ERRORS', errors)
print(f'{sum(checks)} passed, {len(checks) - sum(checks)} failed')
sys.exit(0 if all(checks) and not errors else 1)
