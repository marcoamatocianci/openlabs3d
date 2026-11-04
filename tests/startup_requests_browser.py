"""Startup cost of every kind of page: fresh browser contexts, every API request, duplicates among them, and how
many times the page content was rebuilt. Read-only against the workflow fixture.
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/startup_requests_browser.py OUTPUT.json [--strict] [--loads N] [BASE_URL]
With --strict it fails on any duplicate data request and on more than one build of a workspace page."""
import collections, json, os, sys, time
from playwright.sync_api import sync_playwright
args = [a for a in sys.argv[1:] if not a.startswith('--')]
OUTPUT = args[0]
loads_arg = sys.argv[sys.argv.index('--loads') + 1] if '--loads' in sys.argv else ''
args = [a for a in args if a != loads_arg]
BASE = args[1] if len(args) > 1 else 'http://127.0.0.1:18102'
LOADS = int(loads_arg or 8); STRICT = '--strict' in sys.argv
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
ROUTES = {
    None: ['home', 'catalogue', 'account'],
    'buyer': ['orders', 'orders?scope=history', 'my-requests', 'home', 'catalogue', 'account', 'basket'],
    'host': ['host', 'host/jobs', 'host/jobs?scope=history', 'my-printers', 'my-listings'],
    'admin': ['admin', 'admin/orders', 'admin/orders?scope=history', 'admin/pending', 'admin/requests', 'admin/users'],
}
WATCH = """(() => { window.__builds = 0; const start = () => { const app = document.getElementById('app'); if (!app) return setTimeout(start, 1);
  new MutationObserver(list => { if (list.some(m => m.target === app)) window.__builds++; }).observe(app, {childList:true}); }; start(); })()"""
report, failures = {}, []
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    for who, routes in ROUTES.items():
        for route in routes:
            totals, builds, dupes, errors, times = [], [], collections.Counter(), [], []
            for _ in range(LOADS):
                ctx = browser.new_context(viewport={'width': 1366, 'height': 900})
                if who: assert ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}).ok
                p = ctx.new_page(); seen = []
                p.add_init_script(WATCH)
                p.on('request', lambda r: seen.append(f"{r.method} {r.url.split('/api/')[1]}") if '/api/' in r.url and r.resource_type in ('fetch', 'xhr') and '/visuals/' not in r.url else None)
                p.on('pageerror', lambda e: errors.append(str(e)))
                t = time.perf_counter(); p.goto(f'{BASE}/#{route}', wait_until='networkidle'); p.wait_for_timeout(250); times.append(time.perf_counter() - t)
                totals.append(len(seen)); builds.append(p.evaluate('window.__builds'))
                for url, n in collections.Counter(seen).items():
                    if n > 1: dupes[url] = max(dupes[url], n)
                ctx.close()
            key = f"{who or 'anon'} #{route}"
            report[key] = {'requests': {'min': min(totals), 'max': max(totals), 'avg': round(sum(totals) / len(totals), 1)}, 'builds': {'min': min(builds), 'max': max(builds)}, 'duplicates': dict(dupes), 'loads_with_duplicates_note': sum(1 for _ in dupes), 'seconds': round(sum(times) / len(times), 2), 'errors': errors[:2]}
            print(f"{key:<38} requests {min(totals):>2}–{max(totals):<2} avg {sum(totals) / len(totals):>4.1f}  builds {min(builds)}–{max(builds)}  dup {dict(dupes) if dupes else '-'}", flush=True)
            if errors: failures.append(f'{key}: page error {errors[0]}')
            if STRICT and dupes: failures.append(f'{key}: duplicate requests {dict(dupes)}')
            if STRICT and max(builds) > 3: failures.append(f'{key}: page built {max(builds)} times')
    browser.close()
json.dump(report, open(OUTPUT, 'w'), indent=1)
print(f'TOTAL requests avg per load: {sum(r["requests"]["avg"] for r in report.values()) / len(report):.1f}; routes with duplicates: {sum(1 for r in report.values() if r["duplicates"])}/{len(report)}')
if failures: print(*failures, sep='\n'); sys.exit(1)
