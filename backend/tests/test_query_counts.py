"""How many SQL statements a page's data takes. A page of work must cost a fixed number of statements: a count that
grows with the rows is the N+1 pattern. QC_ORDERS sets the larger size and QC_OUT saves the measurements as JSON."""
import json, os, time
from fastapi.testclient import TestClient
from sqlalchemy import event
import test_marketplace_integrity as base
from test_marketplace_integrity import isolated_database, listing, login, place_order, printer, user  # noqa: F401
from test_marketplace import app

BLACK = {'PLA': {'black': '#000000'}}
ROUTES = {
    'buyer': ['/api/orders?paginated=true&per_page=50', '/api/cart', '/api/auth/me'],
    'host': ['/api/host/jobs?scope=active', '/api/host/jobs?scope=history&per_page=50', '/api/host/equipment', '/api/host/materials'],
    'admin': ['/api/admin/orders?paginated=true&per_page=50', '/api/admin/orders?paginated=true&scope=history&per_page=50', '/api/admin/overview', '/api/admin/users', '/api/admin/hosts', '/api/admin/activity', '/api/admin/listings', '/api/listings/mine'],
    'guest': ['/api/listings?per_page=50', '/api/categories', '/api/settings'],
}

def statements(client, url):
    seen = []
    def note(conn, cursor, statement, params, context, many): seen.append(statement)
    engine = base.SessionLocal.kw['bind']
    event.listen(engine, 'before_cursor_execute', note)
    started = time.perf_counter(); r = client.get(url); took = time.perf_counter() - started
    event.remove(engine, 'before_cursor_execute', note)
    assert r.status_code == 200, (url, r.status_code, r.text[:200])
    return {'statements': len(seen), 'kb': round(len(r.content) / 1024, 1), 'ms': round(took * 1000, 1)}

def grow(market, orders, hosts, products):
    """Adds hosts, products, orders, basket lines and accepted jobs to the same marketplace."""
    with base.SessionLocal() as db:
        for _ in range(hosts): printer(db, user(db, 'host'), BLACK)
        made = [listing(db, db.get(base.models.User, market['admin']), price=1800 + len(market['listings']) + k) for k in range(products)]; db.commit()
        market['listings'] += [p.id for p in made]
    buyer, host = login(market['buyer']), login(market['host'])
    placed = [place_order(market['buyer'], market['listings'][k % len(market['listings'])]) for k in range(orders)]
    for pid in market['listings'][-products:]:
        r = buyer.post('/api/cart', json={'listing_id': pid, 'material': 'PLA', 'color': 'black', 'quantity': 1, 'expected_unit_price_cents': buyer.post(f'/api/listings/{pid}/quote', json={'material': 'PLA', 'color': 'black', 'quantity': 1}).json()['unit_price_cents']})
        assert r.status_code == 200, r.text
    for order in placed[:orders // 3]:
        for job in order['jobs']: assert host.post(f"/api/host/jobs/{job['id']}/accept").status_code == 200

def measure(market):
    clients = {who: login(market[who]) for who in ('admin', 'host', 'buyer')}; clients['guest'] = TestClient(app)
    return {url: statements(clients[who], url) for who, urls in ROUTES.items() for url in urls}

def test_statement_counts_do_not_grow_with_the_rows():
    with base.SessionLocal() as db:
        admin, host, buyer = user(db, 'admin'), user(db, 'host'), user(db, 'buyer'); printer(db, host, BLACK); db.commit()
        market = {'admin': admin.id, 'host': host.id, 'buyer': buyer.id, 'listings': []}
    grow(market, orders=6, hosts=2, products=2); small = measure(market)
    grow(market, orders=int(os.environ.get('QC_ORDERS', 24)), hosts=6, products=6); large = measure(market)
    if os.environ.get('QC_OUT'): json.dump({'small': small, 'large': large}, open(os.environ['QC_OUT'], 'w'), indent=1)
    grew = {url: (small[url]['statements'], large[url]['statements']) for url in small if large[url]['statements'] > small[url]['statements']}
    assert not grew, grew
