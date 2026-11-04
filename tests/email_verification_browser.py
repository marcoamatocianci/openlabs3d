"""The whole experience, with real SMTP into the local Mailpit: register, receive the email, click the link, sign in. In
Bright and Dark, on desktop and phone sizes, with screenshots. No real mail service or credentials are involved.
    docker compose up -d mailpit
    EMAIL_QA_DIR=DIR uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/email_preview.py
    EMAIL_QA_DIR=DIR uv run --no-project --python 3.12 --with playwright python tests/email_verification_browser.py OUTPUT_DIR
AXE_JS=path/to/axe.min.js adds an automated accessibility scan of each page."""
import json, os, re, secrets, sqlite3, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get('EMAIL_QA_URL', 'http://127.0.0.1:18103'); MAILPIT = os.environ.get('MAILPIT_URL', 'http://127.0.0.1:8025'); DB = Path(os.environ['EMAIL_QA_DIR']) / 'qa.db'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
AXE = Path(os.environ['AXE_JS']).read_text() if os.environ.get('AXE_JS') else None
PASSWORD = 'Openlabs2026'; checks, errors, axe_found = [], [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
def mailpit(path): return json.load(urllib.request.urlopen(MAILPIT + path, timeout=5))
def messages(address): return mailpit('/api/v1/search?query=' + urllib.parse.quote(f'to:"{address}"'))['messages']
def wait_mail(address, count=1, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        found = messages(address)
        if len(found) >= count: return mailpit('/api/v1/message/' + found[0]['ID'])   # newest first
        time.sleep(0.2)
    raise AssertionError(f'{count} message(s) for {address} did not arrive')
def link_of(message): return re.search(r'http://\S+token=[A-Za-z0-9_-]+', message['Text'])[0]
def settled(p, ms=250): p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)
visitors = iter(range(1, 250))
def page_for(browser, width, theme):
    # Each visitor has its own address, so the per-address limits do not carry between them. (No proxy in front of the fixture.)
    ctx = browser.new_context(viewport={'width': width, 'height': 900}, color_scheme=theme, bypass_csp=True, extra_http_headers={'X-Real-IP': f'203.0.113.{next(visitors)}'}); p = ctx.new_page()
    p.on('pageerror', lambda e: errors.append(str(e)))
    return ctx, p
def fits(p): return p.evaluate('document.documentElement.scrollWidth <= innerWidth')
def scan(p, name):
    if not AXE: return
    p.evaluate(AXE)
    found = p.evaluate("axe.run(document, {runOnly:{type:'tag', values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}).then(r => r.violations.map(v => v.id + ': ' + v.nodes.map(n => n.target.join(' ')).slice(0, 3).join(', ')))")
    axe_found.extend(f'{name}: {v}' for v in found)
def shot(p, name): p.screenshot(path=str(OUT / f'{name}.png'), full_page=True)
def expire_tokens():
    con = sqlite3.connect(DB); con.execute('UPDATE account_tokens SET expires_at = ?', ((datetime.now(timezone.utc) - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S.%f'),)); con.commit(); con.close()
def row(email, column):
    con = sqlite3.connect(DB); value = con.execute(f'SELECT {column} FROM users WHERE email = ?', (email,)).fetchone(); con.close()
    return value[0] if value else None
def fill_register(p, address, username):
    form = p.locator('#real-register'); form.locator('[name=username]').fill(username); form.locator('[name=email]').fill(address)
    form.locator('[name=password]').first.fill(PASSWORD)
    extra = form.locator('[name=confirm_password], [name=password_confirm]')
    if extra.count(): extra.fill(PASSWORD)
    form.locator('button.primary').click()
def sign_in(p, address, password=PASSWORD):
    form = p.locator('#real-login'); form.locator('[name=email]').fill(address); form.locator('[name=password]').fill(password); form.locator('button.primary').click()

with sync_playwright() as pw:
    # ENGINE=firefox|webkit runs it on another engine; WEBKIT_EXEC may point at a specific WebKit binary.
    engine = os.environ.get('ENGINE', 'chromium'); launch = {'executable_path': CHROME} if engine == 'chromium' else {'executable_path': os.environ['WEBKIT_EXEC']} if engine == 'webkit' and os.environ.get('WEBKIT_EXEC') else {}
    browser = getattr(pw, engine).launch(**launch)
    for width, device in ((1366, 'desktop'), (390, 'phone')):
        for theme, mode in (('light', 'bright'), ('dark', 'dark')):
            label = f'{device} {mode}'; tag = f'{device}-{mode}'; run = secrets.token_hex(4); address = f'new-{run}@example.org'
            ctx, p = page_for(browser, width, theme)
            # Register.
            p.goto(BASE + '/#account?mode=register'); settled(p); fill_register(p, address, 'u_' + run)
            p.wait_for_selector('#auth-message-title:has-text("Check your inbox")'); settled(p)
            text = p.locator('#app').inner_text()
            ok(address in text and 'Please verify your email to activate your OpenLabs3D account' in text, f'{label}: Check your inbox names the address')
            ok(p.locator('#resend-button').is_disabled() and ' s)' in p.locator('#resend-button').inner_text(), f'{label}: resend waits for its cooldown')
            ok(ctx.request.get(BASE + '/api/auth/me').status == 401, f'{label}: registering does not sign in')
            ok(row(address, 'email_verified') == 0, f'{label}: the account starts unverified')
            ok(p.locator('#mail-capture a').get_attribute('href') == MAILPIT and 'does not reach real inboxes' in text, f'{label}: in development the page says where the mail really goes')
            ok(fits(p), f'{label}: no sideways scrolling'); shot(p, f'{tag}-check-inbox'); scan(p, f'{label} check inbox')
            # A name already in use is refused with a way forward, and a deleted account gives its name back.
            ctx2, q = page_for(browser, width, theme); q.goto(BASE + '/#account?mode=register'); settled(q); q.locator('#real-register [name=username]').fill('u_' + run); q.wait_for_function("document.querySelector('#real-register .username-status').textContent.includes('sign in to ask for a new link')")
            ok(True, f'{label}: a name held by an unconfirmed sign-up says how to continue'); shot(q, f'{tag}-username-taken'); ctx2.close()
            # The email.
            message = wait_mail(address); url = link_of(message)
            ok(message['Subject'] == 'Verify your OpenLabs3D email address' and message['From']['Address'] == 'noreply@openlabs3d.local' and message['From']['Name'] == 'OpenLabs3D', f'{label}: received through SMTP with subject and sender')
            ok(url.startswith(BASE + '/#verify-email?token=') and url in message['HTML'] and 'Verify Email Address' in message['HTML'] and 'expires in 24 hours' in message['Text'], f'{label}: HTML and plain text both carry the link and its expiry')
            # Sign-in before verifying.
            p.goto(BASE + '/#account'); settled(p); sign_in(p, address, 'WrongPassword2026'); p.wait_for_selector('.toast, #toast', timeout=3000); settled(p)
            ok(p.locator('#login-verify').count() == 0, f'{label}: a wrong password says nothing about verification')
            sign_in(p, address); p.wait_for_selector('#login-verify'); settled(p)
            ok('verify your email' in p.locator('#login-verify').inner_text().lower() and ctx.request.get(BASE + '/api/auth/me').status == 401, f'{label}: signing in first is refused, and says why')
            ok(fits(p), f'{label}: the notice fits'); shot(p, f'{tag}-login-unverified'); scan(p, f'{label} sign in, unverified')
            time.sleep(3.2)   # past the fixture's short cooldown
            p.locator('#login-resend').click(); p.wait_for_function("document.querySelector('#login-resend-status').textContent.includes('If an account requiring verification')")
            ok(True, f'{label}: resend from sign-in answers generically'); url = link_of(wait_mail(address, 2))
            # The link.
            p.goto(url); p.wait_for_selector('#auth-message-title:has-text("Email verified")'); settled(p, 100)
            ok('token=' not in p.url, f'{label}: the token leaves the address bar'); ok(row(address, 'email_verified') == 1, f'{label}: the server records it as verified')
            ok(fits(p), f'{label}: success page fits'); shot(p, f'{tag}-verified'); scan(p, f'{label} verified')
            p.wait_for_selector('#real-login', timeout=7000); ok(True, f'{label}: it moves on to sign in')
            sign_in(p, address); p.wait_for_function("typeof account !== 'undefined' && account && account.email_verified"); settled(p)
            ok(ctx.request.get(BASE + '/api/auth/me').json()['user']['email_verified'], f'{label}: signing in now works')
            # The same link again, and links that do not work.
            ctx.close(); ctx, p = page_for(browser, width, theme)
            p.goto(url); p.wait_for_selector('#auth-message-title:has-text("already been used")'); settled(p); ok(fits(p), f'{label}: a used link says so'); shot(p, f'{tag}-used'); scan(p, f'{label} used')
            p.goto(BASE + '/#verify-email?token=' + 'x' * 43); p.wait_for_selector('#auth-message-title:has-text("isn\'t valid")'); settled(p)
            ok(p.locator('#resend-form input[name=email]').count() == 1, f'{label}: an invalid link offers a new one'); ok(fits(p), f'{label}: invalid page fits'); shot(p, f'{tag}-invalid'); scan(p, f'{label} invalid')
            # An expired link, then a new one from its page.
            late = f'late-{run}@example.org'; ctx.request.post(BASE + '/api/auth/register', data={'email': late, 'username': 'l_' + run, 'password': PASSWORD})
            old = link_of(wait_mail(late)); expire_tokens(); p.goto(old); p.wait_for_selector('#auth-message-title:has-text("expired")'); settled(p); ok(fits(p), f'{label}: expired page fits'); shot(p, f'{tag}-expired'); scan(p, f'{label} expired')
            ok(row(late, 'email_verified') == 0, f'{label}: an expired link verifies nothing')
            time.sleep(3.2); p.locator('#resend-form input[name=email]').fill(late); p.locator('#resend-button').click(); p.wait_for_function("document.querySelector('#resend-status').textContent.includes('If an account requiring verification')")
            fresh = link_of(wait_mail(late, 2)); ok(fresh != old, f'{label}: a new link arrives'); p.goto(fresh); p.wait_for_selector('#auth-message-title:has-text("Email verified")'); ok(row(late, 'email_verified') == 1, f'{label}: and it works')
            ctx.close()
            # Changing the address in Account settings.
            ctx, p = page_for(browser, width, theme); owner = f'owner-{run}@example.org'; ctx.request.post(BASE + '/api/auth/register', data={'email': owner, 'username': 'o_' + run, 'password': PASSWORD})
            first = link_of(wait_mail(owner)); p.goto(first); p.wait_for_selector('#auth-message-title:has-text("Email verified")')
            p.goto(BASE + '/#account'); p.reload(); p.wait_for_selector('#real-login'); settled(p); sign_in(p, owner); p.wait_for_function("typeof account !== 'undefined' && account"); p.goto(BASE + '/#account'); p.wait_for_selector('#email-form', state='attached'); settled(p)
            target = f'moved-{run}@example.org'
            p.locator('[data-reveal=email-form]').first.click(); p.locator('#email-form [name=email]').fill(target); p.locator('#email-form [name=current_password]').fill(PASSWORD); p.locator('#email-form button.primary').click()
            p.wait_for_selector('#email-pending'); settled(p)
            ok(target in p.locator('#email-pending').inner_text() and owner in p.locator('#account-profile ~ .settings-rows').inner_text() and row(owner, 'email_verified') == 1, f'{label}: the old address stays until the new one is confirmed')
            ok(fits(p), f'{label}: Account settings fits'); shot(p, f'{tag}-email-pending'); scan(p, f'{label} email change pending')
            confirm = wait_mail(target); ok(confirm['Subject'] == 'Confirm your new OpenLabs3D email address', f'{label}: the new address gets a confirmation link')
            p.goto(link_of(confirm)); p.wait_for_selector('#auth-message-title:has-text("Email address changed")'); settled(p)
            ok(target in p.locator('#app').inner_text() and row(target, 'email_verified') == 1 and row(owner, 'email_verified') is None, f'{label}: confirming changes the address'); shot(p, f'{tag}-email-changed')
            ok('was changed' in wait_mail(owner, 2)['Text'], f'{label}: the old address is told')
            p.wait_for_selector('#email-form', state='attached', timeout=7000); settled(p); ok(p.locator('#email-pending').count() == 0, f'{label}: nothing is pending any more')
            ctx.close()
            # Forgetting a password goes through the same mail service. The link also confirms the address.
            ctx, p = page_for(browser, width, theme); who = f'forgot-{run}@example.org'; ctx.request.post(BASE + '/api/auth/register', data={'email': who, 'username': 'f_' + run, 'password': PASSWORD}); wait_mail(who)
            p.goto(BASE + '/#forgot-password'); p.wait_for_selector('#token-form [name=email]'); settled(p); p.locator('#token-form [name=email]').fill(who); p.locator('#token-form button.primary').click()
            p.wait_for_function("document.querySelector('#token-result').textContent.includes('reset message')")
            reset = wait_mail(who, 2); ok(reset['Subject'] == 'Reset your OpenLabs3D password' and '#reset?token=' in reset['Text'] and 'expires in 60 minutes' in reset['Text'], f'{label}: the reset email arrives')
            p.goto(link_of(reset)); p.wait_for_selector('#token-form [name=password]'); settled(p); p.locator('#token-form [name=password]').first.fill('ResetPassword2026'); p.locator('#token-form button.primary').click()
            p.wait_for_function("document.querySelector('#token-result').textContent.includes('Password reset')")
            ok(row(who, 'email_verified') == 1, f'{label}: choosing a password from the link confirms the address'); ok(fits(p), f'{label}: reset page fits'); shot(p, f'{tag}-reset')
            p.goto(BASE + '/#account'); p.wait_for_selector('#real-login'); settled(p); sign_in(p, who, 'ResetPassword2026'); p.wait_for_function("typeof account !== 'undefined' && account")
            ok(ctx.request.get(BASE + '/api/auth/me').status == 200, f'{label}: and the new password signs in')
            ctx.close()
            # A legacy account signs in, is not shown as verified, and can get verified from Account settings.
            ctx, p = page_for(browser, width, theme); old = f'old-{run}@example.org'; ctx.request.post(BASE + '/api/auth/register', data={'email': old, 'username': 'old_' + run, 'password': PASSWORD}); wait_mail(old)
            con = sqlite3.connect(DB); con.execute('UPDATE users SET legacy_email_access = 1 WHERE email = ?', (old,)); con.commit(); con.close()
            p.goto(BASE + '/#account'); settled(p); sign_in(p, old); p.wait_for_function("typeof account !== 'undefined' && account"); p.goto(BASE + '/#account'); p.wait_for_selector('#resend-verification'); settled(p)
            ok('Not verified' in p.locator('#app').inner_text(), f'{label}: a legacy account signs in and is shown as not verified'); shot(p, f'{tag}-legacy'); scan(p, f'{label} legacy')
            time.sleep(3.2); p.locator('#resend-verification').click(); p.wait_for_selector('#mail-capture a')
            ok(p.locator('#mail-capture a').get_attribute('href') == MAILPIT and p.locator('#resend-verification').is_disabled(), f'{label}: Send verification email works, and says where development mail goes'); shot(p, f'{tag}-legacy-sent')
            fresh = wait_mail(old, 2); p.goto(link_of(fresh)); p.wait_for_selector('#auth-message-title:has-text("Email verified")'); settled(p, 100)
            ok(row(old, 'email_verified') == 1 and row(old, 'legacy_email_access') == 0, f'{label}: its link verifies a legacy account')
            ctx.close()
    # Nothing can be learned about an address from these answers.
    ctx, p = page_for(browser, 1366, 'light'); p.goto(BASE + '/#home'); before = len(messages('nobody-here@example.org'))
    answers = [ctx.request.post(BASE + '/api/auth/resend-verification', data={'email': e}).text() for e in ('nobody-here@example.org', 'verified@example.org')]
    ok(answers[0] == answers[1], 'resend answers the same for an unknown and a verified address'); time.sleep(1); ok(len(messages('nobody-here@example.org')) == before, 'no mail goes to an unknown address')
    ctx.close()
    # The email itself, as a mail client shows it.
    sample = messages('verified@example.org')
    ctx, p = page_for(browser, 1366, 'light'); address = f'look-{secrets.token_hex(4)}@example.org'; ctx.request.post(BASE + '/api/auth/register', data={'email': address, 'username': 'x_' + secrets.token_hex(4), 'password': PASSWORD}); message = wait_mail(address)
    for width in (720, 360):
        p.set_viewport_size({'width': width, 'height': 800}); p.goto(f"{MAILPIT}/view/{message['ID']}.html"); settled(p)
        ok(p.evaluate('document.documentElement.scrollWidth <= innerWidth') and p.locator('a:has-text("Verify Email Address")').is_visible() and p.evaluate("[...document.images].every(i => i.naturalWidth > 0)"), f'email at {width} px: fits, the button shows and the logo loads')
        shot(p, f'email-{width}')
    size = len(message['HTML']); ok(size < 16000 and not message.get('Attachments'), f'the email is light ({size} bytes of HTML, no attachments)')
    ctx.close(); browser.close()
ok(not errors, 'no page errors: ' + '; '.join(errors[:3]))
if AXE: ok(not axe_found, 'axe found no violations: ' + '; '.join(axe_found[:6]))
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
