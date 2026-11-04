"""Automated accessibility scan with axe-core (WCAG 2.2 A/AA rules) of every kind of page and dialog, in Bright and
Dark, against the workflow fixture. Automated rules find perhaps a third of real problems: this is not screen-reader
testing. Read-only. Needs axe.min.js from the axe-core npm package (AXE_JS=path, or tests/vendor/axe.min.js).
    uv run --no-project --python 3.12 --with playwright python tests/accessibility_browser.py OUTPUT.json [BASE_URL]"""
import collections, json, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUTPUT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
AXE = Path(os.environ.get('AXE_JS') or Path(__file__).parent / 'vendor' / 'axe.min.js').read_text()
RUN = """async scope => { const r = await axe.run(scope ? document.querySelector(scope) : document, {runOnly:{type:'tag', values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});
  return r.violations.map(v => ({id:v.id, impact:v.impact, help:v.help, nodes:v.nodes.slice(0, 4).map(n => ({target:n.target.join(' '), html:n.html.slice(0, 140), why:(n.any[0]?.message || n.all[0]?.message || '').slice(0, 150)})), count:v.nodes.length})); }"""
def settled(p, ms=500): p.wait_for_load_state('networkidle'); p.wait_for_timeout(ms)
def dialog(selector):
    return lambda p: (p.locator(selector).first.click(), p.wait_for_selector('dialog[open]'), p.wait_for_timeout(300))
SCENES = [
    (None, 'home', None, None), (None, 'catalogue', None, None), (None, 'account', None, None),
    ('buyer', 'orders', None, None), ('buyer', 'orders?group=none', None, None), ('buyer', 'orders?scope=history', None, None), ('buyer', 'my-requests', None, None), ('buyer', 'account', None, None), ('buyer', 'basket', None, None),
    ('buyer', 'orders?group=in-progress', 'Expand section', dialog('.sb-col.is-open [data-sb-expand]')),
    ('buyer', 'orders?group=in-progress', 'Order details', dialog('.sb-col.is-open [data-order-details]')),
    ('host', 'host', None, None), ('host', 'host/jobs?group=available', None, None), ('host', 'host/jobs?group=none', None, None), ('host', 'host/jobs?scope=history', None, None), ('host', 'my-printers', None, None), ('host', 'my-listings', None, None),
    ('host', 'host/jobs?group=in-production', 'Expand section', dialog('.sb-col.is-open [data-sb-expand]')),
    ('host', 'host/jobs?group=in-production', 'Job details', dialog('.sb-col.is-open [data-job-details]')),
    ('host', 'host/jobs?group=available', 'Step confirmation', dialog('.sb-col.is-open [data-job]')),
    ('host', 'host/jobs?group=in-production', 'Mark shipped form', None),
    ('admin', 'admin', None, None), ('admin', 'admin/orders?group=in-progress', None, None), ('admin', 'admin/orders?group=none', None, None), ('admin', 'admin/pending', None, None), ('admin', 'admin/pending?scope=history', None, None), ('admin', 'admin/users', None, None), ('admin', 'admin/requests', None, None),
    ('admin', 'admin/orders?group=in-progress', 'Cancel order', dialog('.sb-col.is-open [data-cancel-order]')),
    ('admin', 'admin/orders?group=in-progress', 'Order details', dialog('.sb-col.is-open [data-admin-order]')),
]
report, totals, by_rule = {}, collections.Counter(), collections.defaultdict(list)
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    for theme in ('light', 'dark'):
        for width in (1366, 390):
            for who, route, name, action in SCENES:
                if name and not action: continue
                ctx = browser.new_context(viewport={'width': width, 'height': 900}, color_scheme=theme, bypass_csp=True)
                if who: assert ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}).ok
                p = ctx.new_page(); p.goto(f'{BASE}/#{route}'); settled(p); p.evaluate(f"applyTheme('{theme}')"); p.wait_for_timeout(150)
                try:
                    if action: action(p)
                    p.add_script_tag(content=AXE)
                    found = p.evaluate(RUN, 'dialog[open]' if action else None)
                except Exception as e:
                    found = [{'id':'scene-error', 'impact':'serious', 'help':str(e)[:200], 'nodes':[], 'count':1}]
                key = f"{who or 'anon'} #{route}{' + ' + name if name else ''} [{theme} {width}]"
                report[key] = found
                for v in found:
                    totals[v['impact']] += v['count']; by_rule[v['id']].append((key, v))
                ctx.close()
    browser.close()
summary = {rule: {'impact':items[0][1]['impact'], 'help':items[0][1]['help'], 'scenes':len(items), 'nodes':sum(v['count'] for _, v in items), 'example':items[0][1]['nodes'][:2], 'where':sorted({k.split(' [')[0] for k, _ in items})[:6]} for rule, items in by_rule.items()}
json.dump({'summary':summary, 'scenes':report}, open(OUTPUT, 'w'), indent=1)
print('scenes', len(report), 'violations by impact', dict(totals))
for rule, s in sorted(summary.items(), key=lambda x: -x[1]['nodes']):
    print(f"{s['impact']:<9} {rule:<26} nodes {s['nodes']:<5} scenes {s['scenes']:<3} {s['help'][:70]}")
    for n in s['example'][:1]: print('   e.g.', n['target'][:70], '|', n['why'][:110])
    print('   in', '; '.join(s['where'])[:150])
sys.exit(0 if not summary else 1)
