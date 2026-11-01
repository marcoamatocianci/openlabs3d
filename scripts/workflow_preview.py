"""Isolated workflow-board fixtures: the catalogue fixture (scripts/catalogue_preview.py) plus orders and
printing jobs in every stage, placed and advanced through the real API (temporary database and files).
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
Serves http://127.0.0.1:18102 (WORKFLOW_QA_PORT). Accounts (password TestPassword2026): buyer, host, other
and admin @example.org.

Buyer orders by fixture key (references are assigned by the server):
  pending-a, pending-b         available (the host may accept them)
  accepted                    accepted by host
  printing                    printing
  ready                       ready to ship
  shipped                     shipped, with a tracking link (the buyer must confirm receipt)
  mixed                       three products: shipped, printing and still available (order: printing)
  pair                        two products, both accepted (order: accepted)
  completed                   received by the buyer (history)
  cancelled                   cancelled by an administrator (history)
"""
import http.cookiejar, json, os, runpy, threading, time, urllib.error, urllib.request
from pathlib import Path
import uvicorn
root = Path(__file__).resolve().parents[1]
namespace = runpy.run_path(str(root / 'scripts/catalogue_preview.py'))
app = namespace['namespace']['app']   # catalogue_preview runs account_preview, which builds the app
PORT = int(os.getenv('WORKFLOW_QA_PORT', '18102')); BASE = f'http://127.0.0.1:{PORT}'
# Serve first, then place and advance the orders through the HTTP API like a browser would.
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning'))
thread = threading.Thread(target=server.run, daemon=True); thread.start()
while not server.started: time.sleep(0.05)

CONTACT = {'first_name': 'Ada', 'last_name': 'Bench', 'phone': '+39 011 1234567', 'email': 'ada@example.org',
           'country': 'IT', 'city': 'Torino', 'street': 'Via Po 1', 'postal_code': '10123'}

class Client:
    def __init__(self, who):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())); self.csrf = ''
        self.csrf = self.post('/api/auth/login', {'email': who + '@example.org', 'password': 'TestPassword2026'})['csrf_token']
    def call(self, method, path, body=None, expect=200):
        request = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf})
        try:
            with self.opener.open(request) as r: status, data = r.status, r.read()
        except urllib.error.HTTPError as e: status, data = e.code, e.read()
        assert status == expect, (method, path, status, data[:300])
        return json.loads(data or b'null')
    def get(self, path): return self.call('GET', path)
    def post(self, path, body=None, expect=200): return self.call('POST', path, body if body is not None else {}, expect)

buyer, host, admin = Client('buyer'), Client('host'), Client('admin')
products = {p['collection_key']: p['id'] for p in buyer.get('/api/listings?per_page=12')['items']}
print('WORKFLOW_PRODUCTS=' + json.dumps(products), flush=True)

def place(key, lines):
    """Checkout of one or more lines (listing key, material, colour, quantity) at the quoted prices."""
    confirmed = []
    for listing, material, color, quantity in lines:
        line = {'listing_id': products[listing], 'material': material, 'color': color, 'quantity': quantity}
        price = buyer.post(f'/api/listings/{line["listing_id"]}/quote', {'material': material, 'color': color, 'quantity': quantity})['unit_price_cents']
        confirmed.append({**line, 'unit_price_cents': price})
        if len(lines) > 1: buyer.post('/api/cart', {**line, 'expected_unit_price_cents': price})
    body = {'idempotency_key': f'workflow-preview-{key}', 'contact': CONTACT, 'confirmed': confirmed}
    if len(lines) == 1: body['direct'] = {k: v for k, v in confirmed[0].items() if k != 'unit_price_cents'}
    return buyer.post('/api/checkout', body, expect=201)

STEPS = ['accepted', 'printing', 'ready', 'shipped']
def advance(job, until):
    host.post(f'/api/host/jobs/{job}/accept')
    for step in STEPS[1:STEPS.index(until) + 1]:
        extra = {'carrier': 'DHL Express', 'tracking_number': f'JD{job:06d}', 'tracking_url': f'https://www.dhl.com/track?id=JD{job:06d}', 'note': 'Packed with foam inserts.'} if step == 'shipped' else {}
        host.post(f'/api/host/jobs/{job}/status', {'status': step, **extra})

orders = {}
for key, lines in [
        ('completed', [('15ml-rack', 'PETG', 'white', 1)]),
        ('cancelled', [('microtube-rack', 'PLA', 'black~1b1b1b', 1)]),
        ('pair', [('microtube-rack', 'PLA', 'cream', 2), ('50ml-rack', 'PETG', 'signal-red', 1)]),
        ('mixed', [('microtube-rack', 'PLA', 'orange', 1), ('15ml-rack', 'PETG', 'cream', 2), ('50ml-rack', 'PLA', 'black~1b1b1b', 1)]),
        ('shipped', [('microtube-rack', 'PLA', 'cream', 2)]),
        ('ready', [('15ml-rack', 'PETG', 'signal-red', 1)]),
        ('printing', [('microtube-rack', 'PLA', 'signal-red', 3)]),
        ('accepted', [('50ml-rack', 'PLA', 'black~1b1b1b', 1)]),
        ('pending-a', [('microtube-rack', 'PLA', 'orange', 2)]),
        ('pending-b', [('15ml-rack', 'PETG', 'white', 1)])]:
    orders[key] = place(key, lines)
jobs = {key: [j['id'] for j in o['jobs']] for key, o in orders.items()}
advance(jobs['completed'][0], 'shipped')
buyer.post(f'/api/orders/{orders["completed"]["id"]}/jobs/{jobs["completed"][0]}/received')
admin.post(f'/api/admin/orders/{orders["cancelled"]["id"]}/cancel')
for job in jobs['pair']: advance(job, 'accepted')
advance(jobs['mixed'][0], 'shipped'); advance(jobs['mixed'][1], 'printing')
advance(jobs['shipped'][0], 'shipped'); advance(jobs['ready'][0], 'ready')
advance(jobs['printing'][0], 'printing'); advance(jobs['accepted'][0], 'accepted')
summary = buyer.get('/api/orders')
print('WORKFLOW_ORDERS=' + ', '.join(f'{o["reference"]}:{o["status"]}' for o in summary), flush=True)

print(f'Workflow fixture ready on {BASE}', flush=True)
thread.join()
