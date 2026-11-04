"""Admin Approvals keeps its colours meaningful under the board's hierarchy: a pending queue is amber only on its
open header and in small status dots; inactive stages stay neutral; decisions keep green (approved), red (rejected)
and neutral (added unverified). Against scripts/equipment_preview.py; the decision types the fixture lacks are added
to the real history response in the browser, so the real page draws them. Read-only.
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/equipment_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/approval_colors_browser.py OUTPUT_DIR [BASE_URL]"""
import os, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18099'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
LOOK = """(board) => {
  const parse = v => { const n = v.match(/-?[\\d.]+(?:e-?\\d+)?/g).map(Number); return v.startsWith('color(') ? {c:n.slice(0, 3).map(x => x * 255), a:n[3] ?? 1} : {c:n.slice(0, 3), a:n[3] ?? 1}; };
  const over = (top, under) => { const t = parse(top); return t.c.map((x, i) => x * t.a + under[i] * (1 - t.a)); };
  const chroma = c => Math.max(...c) - Math.min(...c), page = over(getComputedStyle(document.body).backgroundColor, [255, 255, 255]), b = document.querySelector(board);
  const hue = c => { const [r, g, b] = c, m = Math.max(r, g, b), d = m - Math.min(r, g, b); if (!d) return null; return Math.round(60 * (m === r ? ((g - b) / d + 6) % 6 : m === g ? (b - r) / d + 2 : (r - g) / d + 4)); };
  const tile = col => { const s = getComputedStyle(col), bg = over(s.backgroundColor, page), icon = col.querySelector('.sb-icon'), dot = getComputedStyle(icon, '::after'); return {stage:col.dataset.stage, chroma:chroma(bg), border:chroma(over(s.borderTopColor, page)), iconBg:parse(getComputedStyle(icon).backgroundColor).a, dot:parseFloat(dot.width) || 0, dotColor:parse(dot.backgroundColor).c.map(Math.round).join(','), tone:s.getPropertyValue('--tone-fg').trim(), look:[s.backgroundColor, s.borderTopColor, s.boxShadow].join('|')}; };
  const open = b.querySelector('.sb-col.is-open'), band = open ? over(getComputedStyle(open.querySelector('.sb-top')).backgroundColor, over(getComputedStyle(open).backgroundColor, page)) : null;
  return {pageChroma:chroma(page), band:band && chroma(band), bandHue:band && hue(band), tiles:[...b.querySelectorAll('.sb-mosaic > .sb-col')].map(tile), open:b.dataset.open};
}"""
BADGES = """() => Object.fromEntries([...document.querySelectorAll('#approval-history-board .sb-col.is-open [data-decision-card]')].map(c => { const b = c.querySelector('.status'), s = getComputedStyle(b), i = c.querySelector('.jc-icon'); return [b.textContent.trim(), {color:s.color, bg:s.backgroundColor, icon:getComputedStyle(i).color, kind:i.dataset.decision}]; }))"""
VAR = "n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()"
def rgb(page, name): return page.evaluate("n => { const e = document.createElement('i'); e.style.color = `var(${n})`; document.body.append(e); const c = getComputedStyle(e).color; e.remove(); return c; }", name)

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    for theme in ('light', 'dark'):
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900}, color_scheme=theme)
        assert ctx.request.post(BASE + '/api/auth/login', data={'email': 'admin@example.org', 'password': 'TestPassword2026'}).ok
        def history(route):
            response = route.fetch(); data = response.json(); column = next(c for c in data['columns'] if c['key'] == 'hosts')
            sample = lambda n, decision, reason='': {'id': 900000 + n, 'kind': 'hosts', 'decision': decision, 'title': f'Sample {decision}', 'submitter': 'sample', 'reviewer': 'admin', 'reason': reason, 'created_at': '2026-11-01T10:00:00', 'link': ''}
            column['items'] = [sample(1, 'approved'), sample(2, 'rejected', 'Printer not suitable'), sample(3, 'verified'), sample(4, 'added')]; column['total'] = 4; data['total'] = sum(c['total'] for c in data['columns'])
            route.fulfill(response=response, json=data)
        ctx.route(re.compile(r'/api/admin/approvals/history\?columns=true'), history)
        p = ctx.new_page()
        p.on('pageerror', lambda e: errors.append(f'{theme}: {e}')); p.on('console', lambda m: m.type == 'error' and errors.append(f'{theme}: {m.text}')); p.on('dialog', lambda d: (errors.append('native: ' + d.message), d.dismiss()))
        p.goto(BASE + '/#admin/pending?type=printers'); p.wait_for_selector('#approvals-board'); p.wait_for_function("!document.querySelector('.ws-main[aria-busy]')"); p.wait_for_timeout(500); p.mouse.move(2, 2)

        # Pending: amber means "waiting for review". Only the open header carries it; the others keep a small dot.
        s = p.evaluate(LOOK, '#approvals-board'); warning = rgb(p, '--warning-fg')
        icon_color = p.evaluate("getComputedStyle(document.querySelector('#approvals-board .sb-col.is-open .sb-icon')).color")
        ok(icon_color == warning and (theme == 'dark' or 20 <= (s['bandHue'] if s['bandHue'] is not None else -1) <= 60), f'{theme} pending: amber belongs to the open queue’s header (icon {icon_color}, band hue {s["bandHue"]})')
        ok(all(t['chroma'] <= s['pageChroma'] + 3 and t['iconBg'] == 0 and t['border'] <= s['pageChroma'] + 25 for t in s['tiles']), f'{theme} pending: inactive queues stay neutral {[round(t["chroma"]) for t in s["tiles"]]} (page {s["pageChroma"]:.0f})')
        ok(all(t['dot'] and t['dot'] <= 8 and f'rgb({t["dotColor"].replace(",", ", ")})' == warning for t in s['tiles']), f'{theme} pending: each keeps one small amber status dot ({warning})')
        p.screenshot(path=str(OUT / f'approvals-pending-{theme}.png'))
        # The overview: equal tiles, explicit and remembered.
        p.locator('#approvals-board .sb-col.is-open .sb-head').click(); p.mouse.move(2, 2); p.wait_for_timeout(450)
        s = p.evaluate(LOOK, '#approvals-board')
        icons = p.evaluate("[...document.querySelectorAll('#approvals-board .sb-col .sb-icon')].map(i => getComputedStyle(i).color)")
        alphas = p.evaluate("[...document.querySelectorAll('#approvals-board .sb-col')].map(c => { const v = getComputedStyle(c).backgroundColor, n = v.match(/-?[\\d.]+/g).map(Number); return n[3] ?? 1; })")
        ok(s['open'] == 'none' and len(s['tiles']) == 4 and len({t['look'] for t in s['tiles']}) == 1 and set(icons) == {warning} and max(alphas) < .8, f'{theme} pending: collapsed, four equal tiles in the queues’ amber, translucent (alpha {max(alphas):.2f})')
        ok('type=none' in p.url, f'{theme} pending: all collapsed is in the address ({p.url.split("#")[1]})')
        p.screenshot(path=str(OUT / f'approvals-overview-{theme}.png'))
        p.reload(); p.wait_for_selector('#approvals-board'); p.wait_for_function("!document.querySelector('.ws-main[aria-busy]')")
        ok(p.locator('#approvals-board').get_attribute('data-open') == 'none', f'{theme} pending: a reload keeps it')
        p.locator('#approvals-board .sb-mosaic [data-sb-open="printers"]').click(); p.wait_for_timeout(420)
        ok(p.locator('#approvals-board').get_attribute('data-open') == 'printers' and p.locator('#approvals-board .sb-col.is-open [data-sb-expand]').is_visible(), f'{theme} pending: a tile opens its queue')

        # History: the decision colours are unchanged; the stage itself stays neutral.
        p.goto(BASE + '/#admin/pending?scope=history&type=hosts'); p.wait_for_selector('#approval-history-board'); p.wait_for_function("!document.querySelector('.ws-main[aria-busy]')"); p.wait_for_timeout(300); p.mouse.move(2, 2)
        b = p.evaluate(BADGES)
        ok(set(b) == {'Approved', 'Rejected', 'Specs verified', 'Added unverified'}, f'{theme} history: every decision type drawn {sorted(b)}')
        success, danger, neutral = rgb(p, '--success-fg'), rgb(p, '--danger-fg'), rgb(p, '--neutral-fg')
        ok(b['Approved']['color'] == success and b['Specs verified']['color'] == success, f'{theme} history: Approved and Specs verified are green')
        ok(b['Rejected']['color'] == danger, f'{theme} history: Rejected is red')
        ok(b['Added unverified']['color'] == neutral, f'{theme} history: Added unverified is neutral')
        ok(b['Approved']['icon'] == success and b['Rejected']['icon'] == danger and b['Approved']['kind'] == 'approved' and b['Rejected']['kind'] == 'rejected', f'{theme} history: the icons agree')
        s = p.evaluate(LOOK, '#approval-history-board')
        ok(all(t['chroma'] <= s['pageChroma'] + 3 for t in s['tiles']) and len({t['dotColor'] for t in s['tiles']}) == 1, f'{theme} history: other decision types stay neutral, with one neutral dot')
        p.screenshot(path=str(OUT / f'approvals-history-{theme}.png'))
        ctx.close()
    ok(not errors, 'no page errors: ' + '; '.join(errors[:4]))
    browser.close()
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
