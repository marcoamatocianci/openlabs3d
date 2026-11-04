"""What automated rules cannot check: keyboard paths, focus trapping and return, dialog names, announced states and
reduced motion. Against the workflow fixture. Read-only. This is keyboard testing, not screen-reader testing.
    uv run --no-project --python 3.12 --with playwright python tests/keyboard_browser.py [BASE_URL]"""
import os, sys
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
def session(browser, who=None, w=1366, h=900, motion='no-preference'):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, reduced_motion=motion)
    if who: assert ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}).ok
    p = ctx.new_page(); p.on('pageerror', lambda e: errors.append(str(e))); return ctx, p
def settled(p, ms=350): p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)
def inside(p, sel): return p.evaluate("s => { const d = document.querySelector(s), a = document.activeElement; return !!d && d.contains(a) && a !== document.body; }", sel)
def trapped(p, sel, presses=40):
    for key in ('Tab', 'Shift+Tab'):
        for _ in range(presses):
            p.keyboard.press(key)
            if not inside(p, sel): return False
    return True
def dialog_name(p, sel): return p.evaluate("""s => { const d = document.querySelector(s), id = d.getAttribute('aria-labelledby'); return (id && document.getElementById(id)?.textContent.trim()) || d.getAttribute('aria-label') || ''; }""", sel)
def active(p): return p.evaluate("(() => { const a = document.activeElement; return (a.getAttribute('data-sb-open') || a.getAttribute('data-sb-expand') || a.id || a.className || a.tagName).toString().slice(0, 40); })()")

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    ctx, p = session(browser, 'host'); p.goto(BASE + '/#host/jobs?group=in-production'); p.wait_for_selector('#host-jobs-board'); settled(p)
    p.keyboard.press('Tab')
    ok(p.evaluate("document.activeElement.matches('.skip-link')"), 'the first Tab reaches Skip to content')
    p.keyboard.press('Enter'); ok(p.evaluate("document.activeElement.id") == 'app', 'and it moves focus to the content')

    # Stage headers.
    head = p.locator('.sb-col.is-open .sb-head')
    ok(p.evaluate("document.querySelector('.sb-col.is-open .sb-head').tagName") == 'BUTTON' and head.get_attribute('aria-expanded') == 'true' and head.get_attribute('aria-controls'), 'the open header is a real button with its expanded state')
    ok(p.evaluate("[...document.querySelectorAll('.sb-mosaic .sb-head')].every(h => h.getAttribute('aria-expanded') === 'false')"), 'collapsed panels announce collapsed')
    ok(p.evaluate("(() => { const s = document.querySelector('.sb-col.is-open'), t = document.getElementById(s.getAttribute('aria-labelledby')); return !!t && t.textContent.trim().length > 0; })()"), 'each stage is a labelled region')
    head.focus(); p.keyboard.press('Space'); p.wait_for_timeout(420)
    ok(p.locator('#host-jobs-board').get_attribute('data-open') == 'none' and p.evaluate("document.activeElement.matches('.sb-mosaic .sb-head')"), 'Space collapses; focus stays on that stage')
    p.keyboard.press('Enter'); p.wait_for_timeout(420)
    ok(p.locator('#host-jobs-board').get_attribute('data-open') == 'in-production', 'Enter opens it again')
    # Tab order follows what is on screen.
    p.keyboard.press('Tab'); first = active(p); p.keyboard.press('Tab'); second = active(p)
    ok(first == 'in-production' and p.evaluate("!!document.activeElement.closest('.sb-col.is-open')"), f'Tab goes from the header to Expand section, then into the cards ({first}, {second})')

    # Expand section.
    p.locator('.sb-col.is-open [data-sb-expand]').focus(); p.keyboard.press('Enter'); p.wait_for_selector('#section-dialog[open]'); p.wait_for_timeout(260)
    ok(dialog_name(p, '#section-dialog') == 'In production', 'Expand section: the dialog has a name')
    ok(trapped(p, '#section-dialog'), 'Expand section: Tab and Shift+Tab stay inside')
    p.evaluate("document.querySelector('#section-dialog #ss-q').value = ''"); p.locator('#section-dialog [data-ss-close]').focus(); p.keyboard.press('Escape'); p.wait_for_selector('#section-dialog', state='hidden')
    ok(p.evaluate("document.activeElement.matches('[data-sb-expand]')"), 'Expand section: Escape closes; focus returns to its button')

    # Job details.
    details = p.locator('.sb-col.is-open [data-job-details]').first; details.focus(); p.keyboard.press('Enter'); p.wait_for_selector('#modal[open]'); p.wait_for_timeout(200)
    ok(dialog_name(p, '#modal') != '', f'Job details: the dialog has a name ({dialog_name(p, "#modal")[:40]})')
    ok(inside(p, '#modal'), 'Job details: focus moves inside')
    ok(trapped(p, '#modal'), 'Job details: Tab and Shift+Tab stay inside')
    p.keyboard.press('Escape'); p.wait_for_selector('#modal', state='hidden')
    ok(p.evaluate("document.activeElement.matches('[data-job-details]')"), 'Job details: Escape closes; focus returns to Details')

    # A step's confirmation.
    step = p.locator('.sb-col.is-open [data-job]').first; step.focus(); p.keyboard.press('Enter'); p.wait_for_selector('#action-dialog[open]'); p.wait_for_timeout(120)
    ok(dialog_name(p, '#action-dialog') != '' and trapped(p, '#action-dialog', 12), 'Confirmation: named, and focus stays inside')
    p.keyboard.press('Escape'); p.wait_for_selector('#action-dialog', state='hidden')
    ok(p.evaluate("document.activeElement.matches('[data-job]')"), 'Confirmation: Escape cancels; focus returns to the button')

    # Account menu.
    p.wait_for_timeout(120)   # focus returns to the step's button as the dialog finishes closing
    menu = p.locator('#user-menu-button'); menu.focus(); p.keyboard.press('Enter'); p.wait_for_function("document.querySelector('#user-menu-button').getAttribute('aria-expanded') === 'true'", timeout=1500)
    ok(menu.get_attribute('aria-expanded') == 'true', 'Account menu: Enter opens it, and it says so')
    p.keyboard.press('ArrowDown'); ok(p.evaluate("!!document.activeElement.closest('.dropdown-menu')"), 'Account menu: arrows move into it')
    p.keyboard.press('Escape'); p.wait_for_timeout(60)
    ok(menu.get_attribute('aria-expanded') == 'false' and p.evaluate("document.activeElement.matches('[data-dropdown]')"), 'Account menu: Escape closes; focus returns')

    # Search and pagination controls have names.
    ok(p.evaluate("(() => { const i = document.querySelector('[data-filter-list]'); return i.closest('label')?.textContent.trim().length > 0; })()"), 'the search field is labelled')
    ctx.close()

    # Orders and their dialogs.
    ctx, p = session(browser, 'buyer'); p.goto(BASE + '/#orders?group=in-progress'); p.wait_for_selector('#bo-board'); settled(p)
    d = p.locator('.sb-col.is-open [data-order-details]').first; d.focus(); p.keyboard.press('Enter'); p.wait_for_selector('#modal[open]'); p.wait_for_timeout(200)
    ok(dialog_name(p, '#modal') != '' and trapped(p, '#modal'), 'Order details: named, and focus stays inside')
    p.keyboard.press('Escape'); p.wait_for_selector('#modal', state='hidden')
    ok(p.evaluate("document.activeElement.matches('[data-order-details]')"), 'Order details: focus returns')
    ctx.close()

    # Mobile: the menu button and the pills.
    ctx, p = session(browser, 'host', 390, 844); p.goto(BASE + '/#host/jobs?group=available'); p.wait_for_selector('#host-jobs-board'); settled(p)
    toggle = p.locator('[data-nav-toggle]')
    ok(toggle.get_attribute('aria-expanded') == 'false' and toggle.get_attribute('aria-label'), 'phone: the menu button is labelled, with its state')
    pill = p.locator('.sb-pills [data-sb-open="ready"]'); pill.focus(); p.keyboard.press('Enter'); p.wait_for_timeout(250)
    ok(pill.get_attribute('aria-pressed') == 'true' and p.locator('.sb-pills [aria-pressed="true"]').count() == 1, 'phone: stage pills say which is selected')
    ctx.close()

    # Reduced motion.
    ctx, p = session(browser, 'host', motion='reduce'); p.goto(BASE + '/#host/jobs?group=available'); p.wait_for_selector('#host-jobs-board'); settled(p)
    moving = p.evaluate("() => { document.querySelector('.sb-mosaic [data-sb-open]').click(); return document.getAnimations().filter(a => a.playState === 'running' && a.effect?.getTiming().duration > 0 && !(a.animationName === 'spin')).map(a => a.animationName || a.transitionProperty || 'waapi'); }")
    ok(not moving, f'reduced motion: switching stage starts no animation {moving}')
    ctx.close()
    ok(not errors, 'no page errors: ' + '; '.join(errors[:4]))
    browser.close()
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
