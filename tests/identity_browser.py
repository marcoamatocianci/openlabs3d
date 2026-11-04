"""Sign-in pages and Account settings with a local fake Google, Bright and Dark, desktop and phone.
    docker compose up -d mailpit
    EMAIL_QA_DIR=DIR uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/identity_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/identity_browser.py OUTPUT_DIR
AXE_JS=path/to/axe.min.js adds an accessibility scan."""
import os, secrets, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True); BASE = 'http://127.0.0.1:18104'; PASSWORD = 'TestPassword2026'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'); AXE = Path(os.environ['AXE_JS']).read_text() if os.environ.get('AXE_JS') else None
checks, errors, found = [], [], []
def ok(c, m): checks.append(bool(c)); print(('PASS ' if c else 'FAIL ') + m, flush=True)
def settled(p, ms=300): p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)
def fits(p): return p.evaluate('document.documentElement.scrollWidth <= innerWidth')
def scan(p, name):
    if AXE:
        p.evaluate(AXE); found.extend(f'{name}: {v}' for v in p.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}}).then(r=>r.violations.map(v=>v.id+' '+v.nodes[0].target.join(' ')))"))
n = iter(range(1, 250))
def page(b, w, theme):
    ctx = b.new_context(viewport={'width': w, 'height': 900}, color_scheme=theme, bypass_csp=True, extra_http_headers={'X-Real-IP': f'203.0.113.{next(n)}'}); p = ctx.new_page(); p.on('pageerror', lambda e: errors.append(str(e))); return ctx, p
def me(ctx): r = ctx.request.get(BASE + '/api/auth/me'); return r.json()['user'] if r.ok else None
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=CHROME)
    for w, dev in ((1366, 'desktop'), (390, 'phone')):
        for theme, mode in (('light', 'bright'), ('dark', 'dark')):
            L = f'{dev} {mode}'; tag = f'{dev}-{mode}'; run = secrets.token_hex(4); ctx, p = page(b, w, theme)
            nxt = lambda **who: ctx.request.post(BASE + '/fake-google/next', data=who)
            p.goto(BASE + '/#account'); p.wait_for_selector('.google-btn >> visible=true'); settled(p)
            ok(p.locator('.google-btn:visible').count() == 2 and p.locator('.auth-separator:visible').first.inner_text().lower() == 'or continue with email' and fits(p), f'{L}: both forms offer Google, then email'); p.screenshot(path=str(OUT / f'{tag}-sign-in.png'), full_page=True); scan(p, L + ' sign in')
            p.goto(BASE + '/#account?mode=register'); settled(p); p.screenshot(path=str(OUT / f'{tag}-register.png'), full_page=True)
            # First time.
            mail = f'g{run}@gmail.com'; nxt(sub='s' + run, email=mail, email_verified=True, given_name='Ada', family_name='Bench')
            p.locator('.google-btn:visible').first.click(); p.wait_for_function("location.hash.startsWith('#catalogue') && typeof account !== 'undefined' && account"); u = me(ctx)
            ok(u and u['email'] == mail and u['role'] == 'buyer' and u['email_verified'], f'{L}: first Google sign-in makes a verified buyer')
            p.goto(BASE + '/#account'); p.wait_for_selector('#password-link'); settled(p)
            t = p.locator('#settings-security').inner_text()
            ok('Security & Sign-In Methods' in t and mail in t and 'Google manages' in t and p.locator('#settings-security :text("Disconnect Google")').count() == 0 and fits(p), f'{L}: a Google-only account is told, and cannot remove its only way in'); p.locator('#settings-security').screenshot(path=str(OUT / f'{tag}-google-only.png')); scan(p, L + ' google only')
            ctx.close()
            # An address already registered is never joined.
            ctx, p = page(b, w, theme); nxt = lambda **who: ctx.request.post(BASE + '/fake-google/next', data=who)
            nxt(sub='x' + run, email='verified@example.org', email_verified=True); p.goto(BASE + '/#account'); p.wait_for_selector('.google-btn >> visible=true'); p.locator('.google-btn:visible').first.click(); p.wait_for_selector('#auth-message'); settled(p)
            ok('never joined automatically' in p.locator('#auth-message').inner_text() and not me(ctx) and 'auth_error' not in p.url and fits(p), f'{L}: a matching address is refused, and says what to do'); p.screenshot(path=str(OUT / f'{tag}-email-exists.png')); scan(p, L + ' refused')
            # Explicit linking.
            r = ctx.request.post(BASE + '/api/auth/register', data={'email': f'p{run}@example.org', 'username': 'p' + run, 'password': PASSWORD}); assert r.ok
            import re, sqlite3; con = sqlite3.connect(Path(os.environ['EMAIL_QA_DIR']) / 'qa.db'); con.execute('UPDATE users SET email_verified=1 WHERE username=?', ('p' + run,)); con.commit(); con.close()
            f = p.locator('#real-login'); f.locator('[name=email]').fill(f'p{run}@example.org'); f.locator('[name=password]').fill(PASSWORD); f.locator('button.primary').click(); p.wait_for_function("typeof account !== 'undefined' && account"); p.goto(BASE + '/#account'); p.wait_for_selector('[data-reveal=google-connect]'); settled(p)
            p.locator('[data-reveal=google-connect]').first.click(); nxt(sub='l' + run, email=f'l{run}@gmail.com', email_verified=True); c = p.locator('#google-connect'); c.locator('[name=password]').fill('WrongPassword1'); c.locator('.primary').click(); p.wait_for_function("document.querySelector('#google-connect .form-error').textContent.includes('Incorrect')"); ok(True, f'{L}: connecting needs the right password')
            c.locator('[name=password]').fill(PASSWORD); c.locator('.primary').click(); p.wait_for_selector('#auth-message:has-text("Google is connected")'); p.wait_for_selector('[data-reveal=google-disconnect]'); settled(p)
            ok(f'l{run}@gmail.com' in p.locator('#settings-security').inner_text() and me(ctx)['email'] == f'p{run}@example.org' and fits(p), f'{L}: linked, and the account address is unchanged'); p.locator('#settings-security').screenshot(path=str(OUT / f'{tag}-connected.png')); scan(p, L + ' connected')
            p.locator('[data-reveal=google-disconnect]').first.click(); d = p.locator('#google-disconnect'); d.locator('[name=password]').fill(PASSWORD); d.locator('.primary').click(); p.wait_for_selector('[data-reveal=google-connect]'); ok(True, f'{L}: disconnecting works')
            ctx.close()
    b.close()
ok(not errors, 'no page errors: ' + '; '.join(errors[:3]))
if AXE: ok(not found, 'axe: ' + '; '.join(found[:6]))
print(f'{sum(checks)}/{len(checks)} checks passed'); sys.exit(0 if all(checks) else 1)
