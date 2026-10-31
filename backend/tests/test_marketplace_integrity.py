"""Price integrity, pinned manufacturing files, file access and colour identity."""
import hashlib, json, os, secrets, sqlite3, struct, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from test_marketplace import app
from app import config, database, models
from app.main import digest

CONTACT_FORM = {'first_name': 'Ada', 'last_name': 'Bench', 'phone': '+39 011 1234567', 'country': 'IT', 'city': 'Torino', 'street': 'Via Po 1'}
CAD_DIR = config.UPLOAD_DIR.parent / 'cad'
SessionLocal = engine = None

@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """A fresh marketplace per test: colour options depend on every host's stock."""
    global SessionLocal, engine
    engine = create_engine('sqlite:///' + str(tmp_path / 'integrity.db'), connect_args={'check_same_thread': False, 'timeout': 10})
    database.Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, 'engine', engine); monkeypatch.setattr(database, 'SessionLocal', SessionLocal)
    yield
    engine.dispose()

def stl(size):
    return b'test'.ljust(80, b'\0') + struct.pack('<I', 1) + struct.pack('<12fH', 0, 0, 1, 0, 0, 0, size, 0, 0, 0, size, size, 0)

def user(db, role, **extra):
    u = models.User(email=secrets.token_hex(6) + '@example.org', display_name=role.title(), password_hash='unused', role=role, email_verified=True, **extra)
    db.add(u); db.flush()
    if role == 'host': db.add(models.HostApplication(user_id=u.id, status='approved'))
    return u

def printer(db, host, colors, **size):
    """A printer approved for these materials; the colours join the host's shared inventory."""
    db.add(models.HostPrinter(user_id=host.id, manufacturer='QA', model=secrets.token_hex(3), technology='FDM', x=size.get('x', 300), y=300, z=300, quantity=1,
                              capabilities=json.dumps(sorted(colors))))
    for material, shades in colors.items():
        row = db.scalar(select(models.HostMaterial).where(models.HostMaterial.user_id == host.id, models.HostMaterial.material == material))
        if not row: row = models.HostMaterial(user_id=host.id, material=material, colors='{}'); db.add(row)
        row.colors = json.dumps({**json.loads(row.colors), **shades})
    db.flush()

def login(user_id):
    token = secrets.token_urlsafe(24)
    with SessionLocal() as db:
        db.add(models.LoginSession(token_hash=digest(token), user_id=user_id, csrf='csrf', expires_at=datetime.now(timezone.utc) + timedelta(days=1))); db.commit()
    client = TestClient(app); client.cookies.set('ol3d_session', token); client.headers['X-CSRF-Token'] = 'csrf'
    return client

def listing(db, owner, price=1800, rules=None, cad=None):
    p = models.Listing(owner_id=owner.id, title='Integrity rack ' + secrets.token_hex(3), description='Rack', category='Tube racks', price_cents=price, material='PLA',
                       dimensions='20 mm', compatibility='Tubes', status='approved', listing_type='official', cad_dimensions='[20, 20, 20]',
                       configuration=json.dumps(rules or {'materials': {'PLA': 10000, 'PETG': 10000}}))
    if cad is not None:
        CAD_DIR.mkdir(parents=True, exist_ok=True); name = secrets.token_hex(24) + '.stl'; (CAD_DIR / name).write_bytes(cad); p.cad_path = name
    db.add(p); db.flush(); return p

def checkout(client, confirmed, direct=None, key=None):
    body = {'idempotency_key': key or secrets.token_hex(12), 'contact': CONTACT_FORM, 'confirmed': confirmed}
    if direct: body['direct'] = direct
    return client.post('/api/checkout', json=body)

def set_price(listing_id, cents):
    with SessionLocal() as db: db.get(models.Listing, listing_id).price_cents = cents; db.commit()

def orders_of(user_id):
    with SessionLocal() as db: return db.scalar(select(func.count()).select_from(models.Order).where(models.Order.buyer_id == user_id))

# 1. Price integrity -------------------------------------------------------------------------------

def test_price_change_in_basket_needs_explicit_acceptance_each_time():
    with SessionLocal() as db:
        host, buyer = user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000'}})
        p = listing(db, host); db.commit(); pid, bid = p.id, buyer.id
    client = login(bid)
    line = {'listing_id': pid, 'material': 'PLA', 'color': 'black', 'quantity': 2}
    cart = client.post('/api/cart', json={**line, 'expected_unit_price_cents': 1800}).json()
    assert cart[0]['confirmed_unit_price_cents'] == 1800 and not cart[0]['price_changed']
    set_price(pid, 2100)
    row = client.get('/api/cart').json()[0]
    assert row['price_changed'] and row['unit_price_cents'] == 2100
    assert row['price_change']['message'] == 'The price of this product has changed from €18.00 to €21.00. Please review the updated price before continuing.'
    # Neither the old nor the new price can be submitted until the buyer accepts the change.
    for shown in (1800, 2100):
        r = checkout(client, [{**line, 'unit_price_cents': shown}])
        assert r.status_code == 409 and r.json()['detail']['code'] == 'price_changed', r.text
        assert r.json()['detail']['changes'][0]['previous_unit_price_cents'] == 1800
    assert orders_of(bid) == 0
    assert client.post(f"/api/cart/{row['id']}/accept-price", json={'unit_price_cents': 1800}).status_code == 409
    assert not client.post(f"/api/cart/{row['id']}/accept-price", json={'unit_price_cents': 2100}).json()[0]['price_changed']
    # It changes again before submission: a new confirmation is required.
    set_price(pid, 2300)
    r = checkout(client, [{**line, 'unit_price_cents': 2100}])
    assert r.status_code == 409 and 'from €21.00 to €23.00' in r.json()['detail']['message']
    assert orders_of(bid) == 0
    client.post(f"/api/cart/{row['id']}/accept-price", json={'unit_price_cents': 2300})
    r = checkout(client, [{**line, 'unit_price_cents': 2300}])
    assert r.status_code == 201, r.text
    assert [(i['price_cents'], i['quantity']) for i in r.json()['items']] == [(2300, 2)] and r.json()['total_cents'] == 4600
    assert client.get('/api/cart').json() == []

def test_stale_displayed_price_and_legacy_lines_are_flagged():
    with SessionLocal() as db:
        host, buyer = user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000', 'white': '#ffffff'}})
        p = listing(db, host); db.commit(); pid, bid = p.id, buyer.id
    client = login(bid)
    # The product page still showed €15.00: the basket keeps that price and flags the difference.
    row = client.post('/api/cart', json={'listing_id': pid, 'material': 'PLA', 'color': 'black', 'quantity': 1, 'expected_unit_price_cents': 1500}).json()[0]
    assert row['price_changed'] and 'from €15.00 to €18.00' in row['price_change']['message']
    client.post('/api/cart', json={'listing_id': pid, 'material': 'PLA', 'color': 'white', 'quantity': 1})
    with SessionLocal() as db:   # a line saved before prices were recorded
        db.scalar(select(models.CartItem).where(models.CartItem.user_id == bid, models.CartItem.color == 'white')).confirmed_unit_price_cents = None; db.commit()
    legacy = next(r for r in client.get('/api/cart').json() if r['color'] == 'white')
    assert legacy['price_changed'] and legacy['price_change']['message'] == 'Please review the current price of this product (€18.00) before continuing.'
    # Changing the quantity does not clear a pending review.
    assert client.put('/api/cart', json={'listing_id': pid, 'material': 'PLA', 'color': 'white', 'quantity': 3}).json()[1]['price_changed']

def test_multi_item_checkout_with_discounts_stores_the_confirmed_prices():
    with SessionLocal() as db:
        host, buyer = user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000'}, 'PETG': {'white': '#ffffff'}})
        p = listing(db, host, rules={'materials': {'PLA': 10000, 'PETG': 12000}, 'discounts': {'5': 1000}}); db.commit(); pid, bid = p.id, buyer.id
    client = login(bid)
    lines = [{'listing_id': pid, 'material': 'PLA', 'color': 'black', 'quantity': 5}, {'listing_id': pid, 'material': 'PETG', 'color': 'white', 'quantity': 1}]
    for line in lines: client.post('/api/cart', json=line)
    cart = client.get('/api/cart').json()
    assert [r['unit_price_cents'] for r in cart] == [1620, 2160] and not any(r['price_changed'] for r in cart)
    confirmed = [{**l, 'unit_price_cents': r['unit_price_cents']} for l, r in zip(lines, cart)]
    # A page that shows a different basket (another tab changed it) cannot be submitted.
    stale = [confirmed[0] | {'quantity': 4}, confirmed[1]]
    assert checkout(client, stale).json()['detail']['code'] == 'cart_changed'
    set_price(pid, 2000)   # only lines whose price changed are reported
    changes = checkout(client, confirmed).json()['detail']['changes']
    assert [(c['material'], c['previous_unit_price_cents'], c['current_unit_price_cents']) for c in changes] == [('PLA', 1620, 1800), ('PETG', 2160, 2400)]
    set_price(pid, 1800)
    order = checkout(client, confirmed).json()
    assert sorted((i['material'], i['price_cents']) for i in order['items']) == [('PETG', 2160), ('PLA', 1620)] and order['total_cents'] == 5 * 1620 + 2160

def test_buy_now_uses_the_price_shown_on_the_checkout_page():
    with SessionLocal() as db:
        host, buyer = user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000'}})
        p = listing(db, host); db.commit(); pid, bid = p.id, buyer.id
    client = login(bid)
    direct = {'listing_id': pid, 'material': 'PLA', 'color': 'black', 'quantity': 1}
    set_price(pid, 1900)
    r = checkout(client, [{**direct, 'unit_price_cents': 1800}], direct)
    assert r.status_code == 409 and 'from €18.00 to €19.00' in r.json()['detail']['message']
    assert checkout(client, [{**direct, 'unit_price_cents': 1900}], direct).json()['total_cents'] == 1900
    # Submitted prices are never trusted: a lower one is refused, not charged.
    assert checkout(client, [{**direct, 'unit_price_cents': 1}], direct).status_code == 409

# 2–3. Pinned manufacturing files and access ------------------------------------------------------

def place_order(buyer_id, pid, color='black', material='PLA'):
    client = login(buyer_id)
    direct = {'listing_id': pid, 'material': material, 'color': color, 'quantity': 1}
    price = client.post(f'/api/listings/{pid}/quote', json={k: direct[k] for k in ('material', 'color', 'quantity')}).json()['unit_price_cents']
    r = checkout(client, [{**direct, 'unit_price_cents': price}], direct)
    assert r.status_code == 201, r.text
    return r.json()

def test_orders_keep_the_cad_version_they_were_sold_with():
    v1, v2 = stl(10), stl(12)
    with SessionLocal() as db:
        admin, host, buyer = user(db, 'admin'), user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000'}})
        p = listing(db, admin, cad=v1); db.commit(); pid, aid, hid, bid, first_file, version = p.id, admin.id, host.id, buyer.id, p.cad_path, p.version
    order = place_order(bid, pid)
    with SessionLocal() as db:
        item = db.get(models.OrderItem, order['items'][0]['id'] if 'id' in order['items'][0] else db.scalar(select(models.OrderItem.id).where(models.OrderItem.order_id == order['id'])))
        assert (item.cad_status, item.cad_path, item.cad_sha256, item.listing_version) == ('pinned', first_file, hashlib.sha256(v1).hexdigest(), version)
    admin_client = login(aid)
    assert admin_client.post(f'/api/listings/{pid}/cad', files={'file': ('v2.stl', v2)}).status_code == 200
    assert (CAD_DIR / first_file).read_bytes() == v1, 'the purchased file is never overwritten'
    assert admin_client.get(f'/api/listings/{pid}/cad').content == v2
    host_client, job = login(hid), order['jobs'][0]['id']
    assert host_client.post(f'/api/host/jobs/{job}/accept').status_code == 200
    download = host_client.get(f'/api/jobs/{job}/cad')
    assert download.status_code == 200 and download.content == v1
    assert download.headers['x-content-sha256'] == hashlib.sha256(v1).hexdigest() and download.headers['x-openlabs3d-model-version'] == 'pinned'
    assert host_client.get('/api/host/jobs').json()[0]['item']['cad_status'] == 'pinned'
    # A tampered file is refused rather than sent for printing.
    (CAD_DIR / first_file).write_bytes(v2)
    assert host_client.get(f'/api/jobs/{job}/cad').status_code == 409
    (CAD_DIR / first_file).write_bytes(v1)

def test_manufacturing_files_follow_the_current_assignment():
    with SessionLocal() as db:
        admin, a, b, buyer = user(db, 'admin'), user(db, 'host'), user(db, 'host'), user(db, 'buyer')
        for h in (a, b): printer(db, h, {'PLA': {'black': '#000000'}})
        p = listing(db, admin, cad=stl(10)); db.commit(); pid, aid, ha, hb, bid = p.id, admin.id, a.id, b.id, buyer.id
    order = place_order(bid, pid); job = order['jobs'][0]['id']
    admin_c, host_a, host_b, buyer_c = login(aid), login(ha), login(hb), login(bid)
    url = f'/api/jobs/{job}/cad'
    assert [c.get(url).status_code for c in (host_a, host_b, buyer_c)] == [404, 404, 404], 'nobody is assigned yet'
    assert admin_c.get(url).status_code == 200
    host_a.post(f'/api/host/jobs/{job}/accept')
    assert [c.get(url).status_code for c in (host_a, host_b, buyer_c)] == [200, 404, 404]
    assert host_a.get(f'/api/listings/{pid}/cad').status_code == 403, 'hosts no longer get the listing model'
    # Reassignment: the previous host loses access, the new one gains it.
    assert admin_c.post(f'/api/admin/jobs/{job}/reopen').status_code == 200
    assert host_a.get(url).status_code == 404
    host_b.post(f'/api/host/jobs/{job}/accept')
    assert host_b.get(url).status_code == 200 and host_a.get(url).status_code == 404
    for status in ('printing', 'ready'):
        host_b.post(f'/api/host/jobs/{job}/status', json={'status': status}); assert host_b.get(url).status_code == 200
    assert host_b.post(f'/api/host/jobs/{job}/status', json={'status': 'shipped', 'carrier': 'Courier', 'tracking_number': 'T1'}).status_code == 200
    assert host_b.get(url).status_code == 403, 'shipped jobs no longer need the file'
    assert buyer_c.post(f"/api/orders/{order['id']}/jobs/{job}/received").status_code == 200
    assert host_b.get(url).status_code == 403, 'completed jobs no longer need the file'
    assert admin_c.get(url).status_code == 200, 'administrators keep access'
    # Cancellation and loss of host approval.
    second = place_order(bid, pid); job2 = second['jobs'][0]['id']
    host_a.post(f'/api/host/jobs/{job2}/accept'); assert host_a.get(f'/api/jobs/{job2}/cad').status_code == 200
    with SessionLocal() as db:
        db.scalar(select(models.HostApplication).where(models.HostApplication.user_id == ha)).status = 'suspended'; db.commit()
    assert host_a.get(f'/api/jobs/{job2}/cad').status_code == 403
    with SessionLocal() as db:
        db.scalar(select(models.HostApplication).where(models.HostApplication.user_id == ha)).status = 'approved'; db.commit()
    assert admin_c.post(f"/api/admin/orders/{second['id']}/cancel").status_code == 200
    assert host_a.get(f'/api/jobs/{job2}/cad').status_code == 403
    assert host_a.get('/api/jobs/999999/cad').status_code == 404

def test_existing_order_lines_are_frozen_and_flagged_by_the_migration(tmp_path):
    root = Path(__file__).resolve().parents[1]; path = tmp_path / 'migration.db'; uploads = tmp_path / 'uploads'
    (uploads / 'cad').mkdir(parents=True); name = 'a' * 48 + '.stl'; (uploads / 'cad' / name).write_bytes(stl(10))
    env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + str(path), 'UPLOAD_DIR': str(uploads), 'PYTHONPATH': str(root)}
    def alembic(*args): subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=root, env=env, check=True, capture_output=True)
    alembic('upgrade', '69a_cart_price_confirmation')
    def insert(db, table, **values):
        # Fill the remaining NOT NULL columns without a default, whatever the schema at this revision.
        for _, column, kind, notnull, default, key in db.execute(f'PRAGMA table_info({table})'):
            if notnull and default is None and not key and column not in values: values[column] = 0 if 'INT' in kind.upper() or 'BOOL' in kind.upper() else '2026-01-01' if 'DATE' in kind.upper() else ''
        db.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' * len(values))})", list(values.values()))
    with sqlite3.connect(path) as db:
        insert(db, 'users', id=1, email='m@example.org', username='m', role='buyer')
        for lid, cad in ((1, name), (2, '')): insert(db, 'listings', id=lid, owner_id=1, status='approved', listing_type='official', cad_path=cad, version=1, currency='EUR')
        insert(db, 'orders', id=1, reference='R', buyer_id=1, idempotency_key='k', status='pending', currency='EUR')
        for iid, lid in ((1, 1), (2, 2)): insert(db, 'order_items', id=iid, order_id=1, listing_id=lid, quantity=1)
    alembic('upgrade', 'head')
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT cad_status, cad_path, cad_sha256, listing_version FROM order_items ORDER BY id').fetchall()
    assert rows == [('unverified', name, hashlib.sha256(stl(10)).hexdigest(), None), ('none', '', '', None)]
    alembic('downgrade', '68a_order_color_snapshot'); alembic('upgrade', 'head')

# 4. Colour identity ------------------------------------------------------------------------------

def test_same_colour_name_in_different_shades_is_two_options():
    with SessionLocal() as db:
        admin, a, b, buyer = user(db, 'admin'), user(db, 'host'), user(db, 'host'), user(db, 'buyer')
        printer(db, a, {'PLA': {'orange': '#F58B1F', 'black': '#000000'}}); printer(db, b, {'PLA': {'orange': '#e66a3c', 'black': '#000000'}})
        p = listing(db, admin); db.commit(); pid, ha, hb, bid = p.id, a.id, b.id, buyer.id
    options = TestClient(app).get(f'/api/listings/{pid}/availability').json()['colors_by_material']['PLA']
    assert options == {'orange~f58b1f': '#f58b1f', 'black': '#000000', 'orange~e66a3c': '#e66a3c'}
    assert TestClient(app).post(f'/api/listings/{pid}/quote', json={'material': 'PLA', 'color': 'orange', 'quantity': 1}).status_code == 422
    order = place_order(bid, pid, color='orange~e66a3c')
    assert (order['items'][0]['color'], order['items'][0]['color_hex']) == ('orange~e66a3c', '#e66a3c')
    job = order['jobs'][0]['id']; host_a, host_b = login(ha), login(hb)
    assert job not in [j['id'] for j in host_a.get('/api/host/jobs').json()], 'host A stocks a different orange'
    assert host_a.post(f'/api/host/jobs/{job}/accept').status_code == 403
    # Host B changes stock afterwards: the order keeps the purchased shade and B keeps the job.
    assert host_b.post(f'/api/host/jobs/{job}/accept').status_code == 200
    with SessionLocal() as db:
        db.scalar(select(models.HostMaterial).where(models.HostMaterial.user_id == hb)).colors = json.dumps({'black': '#000000'}); db.commit()
    item = login(bid).get('/api/orders').json()[0]['items'][0]
    assert (item['color'], item['color_hex']) == ('orange~e66a3c', '#e66a3c')
    assert TestClient(app).get(f'/api/listings/{pid}/availability').json()['colors_by_material']['PLA'] == {'orange': '#f58b1f', 'black': '#000000'}

def test_jobs_match_hosts_on_the_purchased_shade():
    from app.availability import combinations, matches, supports
    with SessionLocal() as db:
        admin, a, b = user(db, 'admin'), user(db, 'host'), user(db, 'host')
        printer(db, a, {'PLA': {'yellow': '#f6c700'}}); printer(db, b, {'PLA': {'yellow': '#f8e45c'}})   # two hosts, two shades of "yellow"
        p = listing(db, admin); db.flush()
        assert combinations(p) == {'PLA': {'yellow~f6c700': '#f6c700', 'yellow~f8e45c': '#f8e45c'}}
        assert supports(p, 'PLA', 'yellow~f8e45c', b.id) and not supports(p, 'PLA', 'yellow~f8e45c', a.id) and not supports(p, 'PLA', 'yellow~000000', b.id)
        assert supports(p, 'PLA', 'yellow', b.id), 'lines without a recorded shade still match by name'
        assert not supports(p, 'PLA', 'yellow', b.id, '#123456')
        assert matches({('PLA', 'orange', '#e66a3c')}, 'PLA', 'orange', '#E66A3C')
        db.rollback()

def test_printer_lookup_is_per_request_and_never_stale():
    from app.availability import combinations
    with SessionLocal() as db:
        admin, a = user(db, 'admin'), user(db, 'host'); printer(db, a, {'PLA': {'black': '#000000'}})
        p = listing(db, admin); db.flush()
        assert combinations(p) == {'PLA': {'black': '#000000'}}
        stock = db.scalar(select(models.HostMaterial).where(models.HostMaterial.user_id == a.id))
        stock.colors = json.dumps({'white': '#ffffff'})          # pending, not flushed
        assert combinations(p) == {'PLA': {'white': '#ffffff'}}
        db.delete(db.scalar(select(models.HostPrinter).where(models.HostPrinter.user_id == a.id)))
        assert combinations(p) == {}
        db.rollback()
    with SessionLocal() as db:
        owner = user(db, 'admin'); h = user(db, 'host'); printer(db, h, {'PLA': {'black': '#000000'}})
        for _ in range(12): listing(db, owner)
        db.commit()
    statements = []
    def count(*args):
        if 'host_printers' in args[2]: statements.append(args[2])
    event.listen(engine, 'before_cursor_execute', count)
    try: TestClient(app).get('/api/listings?per_page=12')
    finally: event.remove(engine, 'before_cursor_execute', count)
    assert len(statements) == 1, 'one printer query for a whole catalogue page'
