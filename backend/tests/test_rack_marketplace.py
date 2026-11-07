"""Custom racks in the marketplace, over HTTP: every existing rule still applies, and private means private.

CAD is replaced by a small stand-in file here (test_rack_geometry.py covers real CAD), so this runs anywhere."""
import hashlib, json, secrets, shutil, struct
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, func
from app import config, models
from db_fixtures import isolate
from app.availability import job_ineligibility, set_host_inventory
from app.main import app
from app.equipment import seed_equipment
from app.rack import queue
from app.rack.planner import plan
from app.rack.schema import RackConfiguration

P50, P15 = 'conical-50-generic', 'conical-15-generic'
CONTACT = {'first_name': 'Test', 'last_name': 'Buyer', 'phone': '+39 011 1234567', 'email': 'buyer@example.org', 'country': 'IT', 'city': 'Torino', 'street': 'Via Roma 1', 'postal_code': '10100', 'region': 'TO', 'additional': ''}
RED, BLUE = '#d9424d', '#2255cc'

def rack_body(tubes=None, style='lightweight', **extra):
    return {'tubes': [{'profile_id': p, 'quantity': n} for p, n in ({P50: 4} if tubes is None else tubes).items()], 'style': style, **extra}

@pytest.fixture
def market(tmp_path, monkeypatch):
    engine, sessions, cleanup = isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(config, 'UPLOAD_DIR', tmp_path / 'data' / 'uploads' / 'products')
    clients, ids = {'guest': TestClient(app)}, {}
    with sessions() as db:
        seed_equipment(db)
        for name, role in [('buyer', 'buyer'), ('other', 'buyer'), ('host', 'host'), ('smallhost', 'host'), ('hostbuyer', 'host'), ('admin', 'admin')]:
            u = models.User(email=name + '@example.org', password_hash='unused', display_name=name, username=name, role=role, email_verified=True, first_name='Test', last_name=name, phone='123456789', country='IT', city='Torino', street='Via Roma 1')
            db.add(u); db.flush(); ids[name] = u.id
            token = secrets.token_urlsafe(32)
            db.add(models.LoginSession(user_id=u.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), csrf='test-csrf', expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
            c = TestClient(app); c.cookies.set('ol3d_session', token); c.headers['X-CSRF-Token'] = 'test-csrf'; clients[name] = c
            if role == 'host': db.add(models.HostApplication(user_id=u.id, status='approved'))
        def equip(uid, x, y, z, stock):
            db.add(models.HostPrinter(user_id=uid, manufacturer='Custom', model=f'P{x}', technology='FDM', x=x, y=y, z=z, quantity=1, capabilities=json.dumps(['PLA', 'PETG'])))
            set_host_inventory(db, uid, stock)
        equip(ids['host'], 256, 256, 256, {'PLA': {'red': RED, 'blue': BLUE}, 'PETG': {'red': RED}})
        equip(ids['smallhost'], 100, 100, 256, {'PLA': {'red': RED}})
        db.commit()
    yield SimpleNamespace(clients=clients, ids=ids, sessions=sessions, tmp=tmp_path)
    for c in clients.values(): c.close()
    cleanup()

def stand_in_build(m, body):
    """Mark a configuration's build ready, with a small closed mesh standing in for the real files."""
    result = plan(RackConfiguration(**body), [(256, 256, 256)])
    assert result['ok'], result['issues']
    directory = queue.build_path(result['hash']); directory.mkdir(parents=True, exist_ok=True)
    w, d, h = result['dims']
    x0, y0, x1, y1 = result['footprint']
    v = [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0), (x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    data = b' ' * 80 + struct.pack('<I', len(f)) + b''.join(struct.pack('<3f', 0, 0, 0) + b''.join(struct.pack('<3f', *v[i]) for i in tri) + b'\0\0' for tri in f)
    (directory / 'rack.stl').write_bytes(data)
    (directory / 'rack.3mf').write_bytes(b'PK\x03\x04 stand-in 3mf ' + result['hash'].encode())
    for name in ('render.webp', 'thumb.webp', 'preview.glb'): (directory / name).write_bytes(b'preview')
    metrics = {'volume_mm3': result['metrics']['volume_mm3'], 'area_mm2': result['metrics']['area_mm2'], 'holes': len(result['tubes']), 'dims_mm': result['dims']}
    with m.sessions() as db:
        row = queue.request_build(db, result['hash'], result['spec'])
        row.status, row.result = 'ready', json.dumps({'metrics': metrics, 'report': {'geometry_checked': [], 'manufacturing_estimated': [], 'requires_physical_test': ['fit']}, 'analysis': {'dimensions_mm': result['dims'], 'watertight': True}, 'notes': []})
        db.commit()
    return result

def to_cart(m, who='buyer', body=None, material='PLA', color='red', quantity=1, **extra):
    body = body or rack_body()
    stand_in_build(m, body)
    client = m.clients[who]
    listed = client.post('/api/racks/listing', json={'config': body, 'material': material, 'color': color, 'quantity': quantity, **extra})
    assert listed.status_code == 200, listed.text
    q = listed.json()
    added = client.post('/api/cart', json={'listing_id': q['listing_id'], 'material': material, 'color': color, 'quantity': quantity, 'expected_unit_price_cents': q['unit_price_cents']})
    assert added.status_code == 200, added.text
    return q

def checkout(m, who='buyer'):
    client = m.clients[who]
    confirmed = [{k: line[k] for k in ('listing_id', 'material', 'color', 'quantity', 'unit_price_cents')} for line in client.get('/api/cart').json()]
    return client.post('/api/checkout', json={'idempotency_key': secrets.token_hex(12), 'contact': {k: CONTACT[k] for k in CONTACT}, 'confirmed': confirmed})

def order(m, **kwargs):
    q = to_cart(m, **kwargs)
    response = checkout(m, kwargs.get('who', 'buyer'))
    assert response.status_code == 201, response.text
    return q, response.json()

# Configurator endpoints, open to visitors ---------------------------------------------------------------------------
def test_visitors_can_explore_and_generate_but_not_buy(market):
    guest = market.clients['guest']
    assert guest.get('/api/racks/catalog').status_code == 200
    result = guest.post('/api/racks/plan', json=rack_body()).json()
    assert result['ok'] and result['hash'] and 'spec' not in result
    assert result['availability']['materials']['PLA']['colors'] == {'red': RED, 'blue': BLUE}
    built = guest.post('/api/racks/builds', json=rack_body())
    assert built.status_code == 202 and built.json()['status'] == 'queued' and built.json()['hash'] == result['hash']
    assert guest.get('/api/racks/builds/' + result['hash']).json()['status'] == 'queued'
    assert guest.post('/api/racks/listing', json={'config': rack_body(), 'material': 'PLA', 'color': 'red'}).status_code == 401
    assert guest.get('/api/racks/designs').status_code == 401
    assert guest.post('/api/racks/designs', json={'config': rack_body()}).status_code == 401

def test_identical_geometry_is_queued_once_and_invalid_designs_never_queue(market):
    guest = market.clients['guest']
    for _ in range(3): assert guest.post('/api/racks/builds', json=rack_body()).status_code == 202
    with market.sessions() as db:
        assert db.scalar(select(func.count()).select_from(models.RackBuild)) == 1
    refused = guest.post('/api/racks/builds', json=rack_body({}))
    assert refused.status_code == 422 and refused.json()['detail']['code'] == 'invalid_rack'
    too_large = guest.post('/api/racks/builds', json=rack_body({P50: 60}))
    assert too_large.status_code == 422 and any(i['code'] == 'too_large' for i in too_large.json()['detail']['issues'])
    with market.sessions() as db:
        assert db.scalar(select(func.count()).select_from(models.RackBuild)) == 1

def test_new_builds_are_rate_limited_for_visitors(market):
    guest = market.clients['guest']
    statuses = [guest.post('/api/racks/builds', json=rack_body({P50: 1}, label={'text': f'L{n}'})).status_code for n in range(45)]
    assert 429 in statuses or 503 in statuses
    assert statuses[0] == 202

def test_the_queue_is_bounded(market):
    guest = market.clients['guest']
    with market.sessions() as db:
        for n in range(40): db.add(models.RackBuild(config_hash=f'{n:064x}', spec='{}', status='queued'))
        db.commit()
    assert guest.post('/api/racks/builds', json=rack_body()).status_code == 503

def test_cross_site_requests_are_refused(market):
    assert market.clients['guest'].post('/api/racks/plan', json=rack_body(), headers={'origin': 'https://evil.example'}).status_code == 403
    assert market.clients['guest'].post('/api/racks/builds', json=rack_body(), headers={'sec-fetch-site': 'cross-site'}).status_code == 403

def test_preview_is_served_and_manufacturing_files_are_not(market):
    result = stand_in_build(market, rack_body())
    guest = market.clients['guest']
    assert guest.get(f'/api/racks/builds/{result["hash"]}/preview.glb').status_code == 200
    data = guest.get(f'/api/racks/builds/{result["hash"]}').json()
    assert data['status'] == 'ready' and data['metrics']['basis'] == 'cad' and 'rack.stl' not in json.dumps(data)
    for path in (f'/api/racks/builds/{result["hash"]}/rack.stl', f'/api/racks/builds/{result["hash"]}/rack.3mf', f'/api/racks/builds/{result["hash"]}/..%2F..%2Fsecret', '/api/racks/builds/notahash'):
        assert guest.get(path).status_code in (404, 422)

def test_materials_and_colours_come_from_hosts_that_fit_the_rack(market):
    guest = market.clients['guest']
    small = guest.post('/api/racks/plan', json=rack_body({P15: 1}, label=None)).json()
    assert small['fit']['state'] == 'fits' and small['fit']['printers'] == 2
    large = guest.post('/api/racks/plan', json=rack_body({P50: 16})).json()
    # The 100 mm printer cannot take it, so only the larger host's stock counts; the small host's has no PETG anyway.
    assert large['ok'] and large['fit']['printers'] == 1 and set(large['availability']['materials']) == {'PLA', 'PETG'}
    assert large['availability']['materials']['PETG']['colors'] == {'red': RED}

def test_too_large_for_every_printer_explains_itself(market):
    result = market.clients['guest'].post('/api/racks/plan', json=rack_body({P50: 40})).json()
    assert not result['ok'] and result['fit']['state'] == 'too_large' and result['availability']['materials'] == {}
    assert 'for the currently available printers' in next(i for i in result['issues'] if i['code'] == 'too_large')['message']

def test_a_host_is_not_offered_what_only_its_own_printers_can_make(market):
    with market.sessions() as db:
        db.execute(delete(models.HostPrinter).where(models.HostPrinter.user_id == market.ids['smallhost']))
        db.commit()
    host = market.clients['host'].post('/api/racks/plan', json=rack_body()).json()
    assert host['availability']['materials'] == {} and host['availability']['own_printers_only'] and host['fit']['state'] == 'no_printers'
    assert market.clients['buyer'].post('/api/racks/plan', json=rack_body()).json()['availability']['materials']

# Selling a design --------------------------------------------------------------------------------------------------
def test_listing_needs_a_finished_build(market):
    response = market.clients['buyer'].post('/api/racks/listing', json={'config': rack_body(), 'material': 'PLA', 'color': 'red'})
    assert response.status_code == 409 and response.json()['detail']['code'] == 'build_pending'
    market.clients['buyer'].post('/api/racks/builds', json=rack_body())
    assert market.clients['buyer'].post('/api/racks/listing', json={'config': rack_body(), 'material': 'PLA', 'color': 'red'}).status_code == 409

def test_unavailable_material_and_colour_are_refused(market):
    stand_in_build(market, rack_body())
    client = market.clients['buyer']
    for material, color in (('PETG', 'blue'), ('ABS', 'red'), ('PLA', 'green')):
        assert client.post('/api/racks/listing', json={'config': rack_body(), 'material': material, 'color': color}).status_code == 422

def test_the_server_sets_the_price_and_a_changed_design_gets_a_new_one(market):
    q1 = to_cart(market)
    q2 = to_cart(market, body=rack_body({P50: 8}))
    assert q1['listing_id'] != q2['listing_id'] and q2['unit_price_cents'] > q1['unit_price_cents']
    client = market.clients['buyer']
    # Neither the listing nor the cart accepts a price from the client.
    assert client.post('/api/racks/listing', json={'config': rack_body(), 'material': 'PLA', 'color': 'red', 'unit_price_cents': 1}).status_code == 422
    lines = client.get('/api/cart').json()
    assert {l['listing_id']: l['unit_price_cents'] for l in lines} == {q1['listing_id']: q1['unit_price_cents'], q2['listing_id']: q2['unit_price_cents']}
    assert not any(l['price_changed'] for l in lines)
    # A lie about the price confirmed is refused at checkout.
    confirmed = [{k: l[k] for k in ('listing_id', 'material', 'color', 'quantity')} | {'unit_price_cents': 1} for l in lines]
    assert client.post('/api/checkout', json={'idempotency_key': secrets.token_hex(12), 'contact': CONTACT, 'confirmed': confirmed}).status_code == 409

def test_the_price_follows_the_material(market):
    q = to_cart(market, material='PETG')
    pla = market.clients['buyer'].post(f'/api/listings/{q["listing_id"]}/quote', json={'material': 'PLA', 'color': 'red', 'quantity': 1}).json()
    assert q['unit_price_cents'] != pla['unit_price_cents']

def test_the_same_design_is_one_listing_and_merges_in_the_basket(market):
    a, b = to_cart(market), to_cart(market)
    assert a['listing_id'] == b['listing_id']
    lines = market.clients['buyer'].get('/api/cart').json()
    assert len(lines) == 1 and lines[0]['quantity'] == 2

def test_a_private_listing_is_private(market):
    q = to_cart(market)
    lid = q['listing_id']
    buyer, other, guest, host, admin = (market.clients[k] for k in ('buyer', 'other', 'guest', 'host', 'admin'))
    assert buyer.get(f'/api/listings/{lid}').status_code == 200 and buyer.get(f'/api/listings/{lid}').json()['custom_rack']
    for client in (other, guest, host):
        assert client.get(f'/api/listings/{lid}').status_code == 404
        assert client.get(f'/api/listings/{lid}/availability').status_code == 404
        assert client.post(f'/api/listings/{lid}/quote', json={'material': 'PLA', 'color': 'red', 'quantity': 1}).status_code == 404
    assert admin.get(f'/api/listings/{lid}').status_code == 200
    # Never in any public or management list.
    assert all(i['id'] != lid for i in guest.get('/api/listings?per_page=50').json()['items'])
    assert all(i['id'] != lid for i in buyer.get('/api/listings?per_page=50').json()['items'])
    assert all(i['id'] != lid for i in buyer.get('/api/listings/mine').json())
    assert all(i['id'] != lid for i in admin.get('/api/admin/listings').json())
    # Somebody else cannot buy it, however they ask.
    line = {'listing_id': lid, 'material': 'PLA', 'color': 'red', 'quantity': 1}
    assert other.post('/api/cart', json=line).status_code == 422
    assert other.put('/api/cart', json=line).status_code == 422
    assert other.post('/api/orders', json={'idempotency_key': secrets.token_hex(12), 'contact': json.dumps({k: 'x' for k in ('first_name', 'last_name')} | {'phone': '123456789'}), 'address': json.dumps({'country': 'IT', 'city': 'Torino', 'street': 'x'}), 'items': [{**line, 'expected_price_cents': q['unit_price_cents']}]}).status_code == 422
    assert other.post('/api/checkout', json={'idempotency_key': secrets.token_hex(12), 'contact': CONTACT, 'direct': line, 'confirmed': [{**line, 'unit_price_cents': q['unit_price_cents']}]}).status_code == 422

def test_a_private_listing_cannot_be_edited_even_by_its_owner(market):
    q = to_cart(market, who='hostbuyer')
    lid = q['listing_id']
    client = market.clients['hostbuyer']      # a host, who may edit listings they own, but not these
    assert client.patch(f'/api/listings/{lid}', json={'price_cents': 1}).status_code == 403
    assert client.put(f'/api/listings/{lid}/pricing', json={'materials': {'PLA': 100}}).status_code == 403
    assert client.delete(f'/api/listings/{lid}').status_code == 403
    assert client.post(f'/api/listings/{lid}/cad', files={'file': ('x.stl', b'x')}).status_code == 403
    assert client.post(f'/api/listings/{lid}/submit').status_code == 403

def test_buyers_do_not_get_the_manufacturing_file(market):
    q = to_cart(market)
    assert market.clients['buyer'].get(f'/api/listings/{q["listing_id"]}/cad').status_code == 403
    assert market.clients['other'].get(f'/api/listings/{q["listing_id"]}/cad').status_code == 403

def test_administrators_do_not_buy(market):
    stand_in_build(market, rack_body())
    assert market.clients['admin'].post('/api/racks/listing', json={'config': rack_body(), 'material': 'PLA', 'color': 'red'}).status_code == 403

# Orders ------------------------------------------------------------------------------------------------------------
LABELLED = rack_body({P50: 4, P15: 2}, 'premium', label={'text': 'Proserpio Lab', 'style': 'engraved'})

def test_an_order_keeps_everything_needed_to_make_exactly_this_rack(market):
    result = plan(RackConfiguration(**LABELLED), [(256, 256, 256)])
    q, data = order(market, body=LABELLED, material='PLA', color='blue')
    assert data['total_cents'] == q['total_cents']
    item = data['items'][0]
    assert item['rack']['tubes'][0]['quantity'] == 4 and item['rack']['style'] == 'premium' and item['rack']['label']['text'] == 'Proserpio Lab'
    with market.sessions() as db:
        row = db.get(models.OrderItem, item['id'])
        snapshot = json.loads(row.rack_snapshot)
        assert row.material == 'PLA' and row.color == 'blue' and row.color_hex == BLUE and row.cad_status == 'pinned' and len(row.cad_sha256) == 64
        assert json.loads(row.manufacturing_dimensions) == result['dims']
        assert snapshot['hash'] == result['hash'] and snapshot['geometry_version'] == result['spec']['geometry_version']
        assert snapshot['config']['label']['text'] == 'Proserpio Lab' and len(snapshot['spec']['tubes']) == 6
        assert snapshot['files']['stl']['sha256'] == row.cad_sha256 and snapshot['pricing']['base_cents'] > 0
        assert snapshot['profiles'][P50]['body_diameter_mm'] == 30.0     # the dimensions as sold

def test_editing_or_deleting_the_design_never_changes_an_order(market):
    client = market.clients['buyer']
    design = client.post('/api/racks/designs', json={'name': 'Mine', 'config': rack_body()}).json()
    q, data = order(market, body=rack_body(), design_id=design['id'])
    item = data['items'][0]
    with market.sessions() as db: before = (db.get(models.OrderItem, item['id']).rack_snapshot, db.get(models.OrderItem, item['id']).cad_sha256, db.get(models.OrderItem, item['id']).price_cents)
    purchased = client.get(f'/api/racks/designs/{design["id"]}').json()['purchased']
    assert purchased[0]['item_id'] == item['id']
    assert client.put(f'/api/racks/designs/{design["id"]}', json={'config': rack_body({P50: 9}, 'premium')}).status_code == 200
    with market.sessions() as db:
        row = db.get(models.OrderItem, item['id'])
        assert (row.rack_snapshot, row.cad_sha256, row.price_cents) == before
        assert db.get(models.Listing, q['listing_id']).rack_snapshot == before[0]
    assert client.delete(f'/api/racks/designs/{design["id"]}').status_code == 200
    with market.sessions() as db:
        assert db.get(models.OrderItem, item['id']).rack_snapshot == before[0]
        assert db.get(models.Listing, q['listing_id']).rack_design_id is None
    assert client.get('/api/orders').json()[0]['items'][0]['price_cents'] == before[2]

def test_the_manufacturing_file_survives_cleaning_the_build_cache(market):
    _, data = order(market)
    job = data['jobs'][0]
    with market.sessions() as db:
        rack_hash = json.loads(db.get(models.OrderItem, data['items'][0]['id']).rack_snapshot)['hash']
    shutil.rmtree(queue.build_path(rack_hash))
    host = market.clients['host']
    assert host.post(f'/api/host/jobs/{job["id"]}/accept').status_code == 200
    assert host.get(f'/api/jobs/{job["id"]}/cad').status_code == 200

def test_host_eligibility_is_by_upright_fit_exact_shade_and_never_their_own_order(market):
    _, data = order(market, body=rack_body({P50: 16}))    # about 170 mm across: too wide for the 100 mm printer
    job = data['jobs'][0]
    with market.sessions() as db:
        row = db.get(models.PrintingJob, job['id'])
        assert job_ineligibility(row, market.ids['host']) is None
        assert job_ineligibility(row, market.ids['smallhost']) == 'printer'
    assert all(j['id'] != job['id'] for j in market.clients['smallhost'].get('/api/host/jobs').json())
    assert any(j['id'] == job['id'] for j in market.clients['host'].get('/api/host/jobs').json())
    assert market.clients['smallhost'].post(f'/api/host/jobs/{job["id"]}/accept').status_code == 403
    # The stock changes after the order: revalidated at acceptance.
    with market.sessions() as db:
        set_host_inventory(db, market.ids['host'], {'PLA': {'blue': BLUE}}); db.commit()
    assert market.clients['host'].post(f'/api/host/jobs/{job["id"]}/accept').status_code == 403
    with market.sessions() as db:
        set_host_inventory(db, market.ids['host'], {'PLA': {'red': RED}}); db.commit()
    assert market.clients['host'].post(f'/api/host/jobs/{job["id"]}/accept').status_code == 200

def test_a_rack_that_only_fits_by_tipping_over_is_not_offered(market):
    with market.sessions() as db:
        printer = db.scalar(select(models.HostPrinter).where(models.HostPrinter.user_id == market.ids['host']))
        printer.x, printer.y, printer.z = 60, 256, 256     # would fit a tall narrow rack only lying on its side
        db.commit()
    result = market.clients['buyer'].post('/api/racks/plan', json=rack_body({P50: 16})).json()
    assert result['fit']['state'] == 'too_large'

def test_a_host_does_not_take_its_own_rack(market):
    with market.sessions() as db:
        db.add(models.HostPrinter(user_id=market.ids['hostbuyer'], manufacturer='C', model='P', technology='FDM', x=256, y=256, z=256, quantity=1, capabilities=json.dumps(['PLA'])))
        set_host_inventory(db, market.ids['hostbuyer'], {'PLA': {'red': RED}}); db.commit()
    _, data = order(market, who='hostbuyer')
    job = data['jobs'][0]
    assert market.clients['hostbuyer'].post(f'/api/host/jobs/{job["id"]}/accept').status_code == 403
    assert market.clients['host'].post(f'/api/host/jobs/{job["id"]}/accept').status_code == 200

def test_files_reach_only_the_assigned_host_while_the_job_is_open(market):
    _, data = order(market, body=LABELLED)
    job = data['jobs'][0]['id']
    host, smallhost, buyer, admin, guest = (market.clients[k] for k in ('host', 'smallhost', 'buyer', 'admin', 'guest'))
    for client, status in ((guest, 401), (buyer, 404), (host, 404)):
        assert client.get(f'/api/jobs/{job}/cad').status_code == status
    assert host.get(f'/api/jobs/{job}/rack').status_code == 404
    assert host.post(f'/api/host/jobs/{job}/accept').status_code == 200
    stl = host.get(f'/api/jobs/{job}/cad')
    assert stl.status_code == 200 and stl.headers['content-disposition'].endswith('.stl"') and 'no-store' in stl.headers['cache-control']
    assert stl.headers['x-content-sha256'] == hashlib.sha256(stl.content).hexdigest()
    threemf = host.get(f'/api/jobs/{job}/cad?format=3mf')
    assert threemf.status_code == 200 and threemf.headers['content-disposition'].endswith('.3mf"')
    assert host.get(f'/api/jobs/{job}/cad?format=obj').status_code == 404
    spec = host.get(f'/api/jobs/{job}/rack').json()
    assert spec['label']['text'] == 'Proserpio Lab' and len(spec['tubes']) == 6 and spec['orientation'].startswith('upright')
    assert smallhost.get(f'/api/jobs/{job}/cad').status_code == 404 and smallhost.get(f'/api/jobs/{job}/rack').status_code == 404
    assert admin.get(f'/api/jobs/{job}/cad').status_code == 200
    # Through shipment and completion, access ends where it does for any product.
    assert host.post(f'/api/host/jobs/{job}/status', json={'status': 'ready'}).status_code == 200
    assert host.post(f'/api/host/jobs/{job}/status', json={'status': 'shipped', 'carrier': 'Poste', 'tracking_number': 'T1'}).status_code == 200
    assert host.get(f'/api/jobs/{job}/cad').status_code == 403 and host.get(f'/api/jobs/{job}/rack').status_code == 403

def test_tampered_manufacturing_files_are_refused(market):
    _, data = order(market)
    job = data['jobs'][0]['id']
    market.clients['host'].post(f'/api/host/jobs/{job}/accept')
    with market.sessions() as db:
        name = db.get(models.OrderItem, data['items'][0]['id']).cad_path
    path = config.UPLOAD_DIR.parent / 'cad' / name
    path.chmod(0o644); path.write_bytes(path.read_bytes() + b'tampered')
    assert market.clients['host'].get(f'/api/jobs/{job}/cad').status_code == 409

def test_hosts_see_the_picture_of_a_rack_they_may_take_and_no_more(market):
    q, data = order(market)
    lid = q['listing_id']
    with market.sessions() as db:
        listing = db.get(models.Listing, lid); job = listing.cad_file.asset.jobs[0]
        directory = job.output_dir
    base = f'/api/listings/{lid}/visuals/{directory}'
    assert market.clients['host'].get(base + '/thumb.webp').status_code == 200
    assert market.clients['host'].get(base + '/model.glb').status_code == 404      # the 3D model stays with its buyer
    assert market.clients['buyer'].get(base + '/model.glb').status_code == 200
    assert market.clients['other'].get(base + '/thumb.webp').status_code == 404
    assert market.clients['guest'].get(base + '/thumb.webp').status_code == 404
    assert data['jobs'][0]['item']['rack']['style'] == 'lightweight'

def test_cancellation_and_pending_deletion_behave_as_for_any_product(market):
    q, data = order(market)
    assert market.clients['buyer'].delete(f'/api/orders/{data["id"]}').status_code == 200
    with market.sessions() as db:
        assert db.get(models.Order, data['id']) is None and db.get(models.Listing, q['listing_id']) is not None
    _, data = order(market)
    job = data['jobs'][0]['id']
    market.clients['host'].post(f'/api/host/jobs/{job}/accept')
    assert market.clients['admin'].post(f'/api/admin/orders/{data["id"]}/cancel', json={'reason': 'Test cancel'}).status_code == 200
    assert market.clients['host'].get(f'/api/jobs/{job}/cad').status_code == 403

def test_a_full_journey_to_completion(market):
    _, data = order(market, body=LABELLED, material='PETG')
    job, client = data['jobs'][0]['id'], market.clients['host']
    assert client.post(f'/api/host/jobs/{job}/accept').status_code == 200
    assert client.post(f'/api/host/jobs/{job}/status', json={'status': 'printing'}).status_code == 200
    assert client.post(f'/api/host/jobs/{job}/status', json={'status': 'ready'}).status_code == 200
    assert client.post(f'/api/host/jobs/{job}/status', json={'status': 'shipped', 'carrier': 'Poste', 'tracking_number': 'T1'}).status_code == 200
    done = market.clients['buyer'].post(f'/api/orders/{data["id"]}/jobs/{job}/received')
    assert done.status_code == 200 and done.json()['status'] == 'completed'
    history = market.clients['buyer'].get('/api/orders').json()[0]
    assert history['items'][0]['rack']['label']['text'] == 'Proserpio Lab' and history['items'][0]['material'] == 'PETG'

# Saved designs -----------------------------------------------------------------------------------------------------
def test_saved_designs_belong_to_their_owner(market):
    buyer, other = market.clients['buyer'], market.clients['other']
    design = buyer.post('/api/racks/designs', json={'config': rack_body({P50: 2, P15: 2})}).json()
    assert design['name'] == '50 mL / 15 mL Mixed Rack'
    did = design['id']
    assert buyer.get('/api/racks/designs').json()[0]['id'] == did and other.get('/api/racks/designs').json() == []
    for call in (other.get(f'/api/racks/designs/{did}'), other.put(f'/api/racks/designs/{did}', json={'config': rack_body()}), other.patch(f'/api/racks/designs/{did}', json={'name': 'x'}), other.delete(f'/api/racks/designs/{did}'), other.post(f'/api/racks/designs/{did}/duplicate')):
        assert call.status_code == 404
    stand_in_build(market, rack_body())
    assert other.post('/api/racks/listing', json={'config': rack_body(), 'material': 'PLA', 'color': 'red', 'design_id': did}).status_code == 404
    assert buyer.patch(f'/api/racks/designs/{did}', json={'name': 'Renamed'}).json()['name'] == 'Renamed'
    copy = buyer.post(f'/api/racks/designs/{did}/duplicate').json()
    assert copy['name'] == 'Renamed copy' and copy['config'] == design['config'] and copy['id'] != did
    assert buyer.delete(f'/api/racks/designs/{did}').status_code == 200 and buyer.get(f'/api/racks/designs/{did}').status_code == 404

def test_default_names_do_not_collide(market):
    client = market.clients['buyer']
    names = [client.post('/api/racks/designs', json={'config': rack_body({P50: 3})}).json()['name'] for _ in range(3)]
    assert names == ['50 mL Rack', '50 mL Rack 01', '50 mL Rack 02']
    assert client.post('/api/racks/designs', json={'config': rack_body({}), 'name': 'Empty draft'}).json()['hash'] == ''

def test_designs_need_a_session_token_to_change(market):
    client = market.clients['buyer']
    assert client.post('/api/racks/designs', json={'config': rack_body()}, headers={'X-CSRF-Token': 'wrong'}).status_code == 403

def test_reorder_and_starting_again_from_an_order(market):
    q, data = order(market, material='PLA', color='blue')
    item = data['items'][0]['id']
    buyer, other = market.clients['buyer'], market.clients['other']
    assert other.post(f'/api/racks/orders/{item}/reorder').status_code == 404
    assert other.post(f'/api/racks/orders/{item}/design').status_code == 404
    again = buyer.post(f'/api/racks/orders/{item}/reorder').json()
    assert again['listing_id'] == q['listing_id'] and again['color'] == 'blue' and again['unit_price_cents'] == q['unit_price_cents']
    draft = buyer.post(f'/api/racks/orders/{item}/design').json()
    assert draft['config']['tubes'][0]['quantity'] == 4 and draft['id']

def test_an_account_without_orders_can_still_be_deleted(market):
    to_cart(market, who='other')
    market.clients['other'].post('/api/racks/designs', json={'config': rack_body()})
    from app.main import hasher
    with market.sessions() as db:
        db.get(models.User, market.ids['other']).password_hash = hasher.hash('Delete-me-1'); db.commit()
    response = market.clients["other"].request("DELETE", "/api/profile", json={"password": "Delete-me-1"}); assert response.status_code == 200, response.text
    with market.sessions() as db:
        assert db.scalar(select(func.count()).select_from(models.Listing).where(models.Listing.owner_id == market.ids['other'])) == 0
        assert db.scalar(select(func.count()).select_from(models.RackDesign).where(models.RackDesign.user_id == market.ids['other'])) == 0

def test_existing_products_are_untouched(market):
    with market.sessions() as db:
        db.add(models.Listing(owner_id=market.ids['admin'], title='Catalogue rack', status='approved', material='PLA', configuration='{"materials":{"PLA":10000}}', cad_dimensions='[110,85,52]', price_cents=1800, dimensions='110 × 85 × 52 mm', listing_type='official'))
        db.commit()
    guest, buyer = market.clients['guest'], market.clients['buyer']
    item = guest.get('/api/listings').json()['items'][0]
    assert item['title'] == 'Catalogue rack' and item['custom_rack'] is False
    assert guest.post(f'/api/listings/{item["id"]}/quote', json={'material': 'PLA', 'color': 'red', 'quantity': 1}).json()['unit_price_cents'] == 1800
    assert buyer.post('/api/cart', json={'listing_id': item['id'], 'material': 'PLA', 'color': 'red', 'quantity': 1}).status_code == 200
    data = checkout(market).json()
    assert data['items'][0]['rack'] is None and data['jobs'][0]['item']['rack'] is None
    # Parts other than racks may still be laid in any orientation that fits: 110 × 85 × 52 goes on a 100 × 100 × 256 printer on its side.
    with market.sessions() as db:
        assert job_ineligibility(db.get(models.PrintingJob, data['jobs'][0]['id']), market.ids['smallhost']) is None

# The build queue, without CAD ---------------------------------------------------------------------------------------
def test_builds_nobody_waits_for_are_dropped_without_work(market):
    result = plan(RackConfiguration(**rack_body()), [(256, 256, 256)])
    with market.sessions() as db:
        row = queue.request_build(db, result['hash'], result['spec'])
        row.last_requested_at = datetime.now(timezone.utc) - timedelta(seconds=queue.ABANDON_SECONDS + 5)
        db.commit()
    assert queue.claim(market.sessions) is None
    with market.sessions() as db:
        row = db.get(models.RackBuild, result['hash'])
        assert row.status == 'abandoned'
        again = queue.request_build(db, result['hash'], result['spec'])     # asked for again, it runs
        assert again.status == 'queued'
        db.commit()
    assert queue.claim(market.sessions)[0] == result['hash']
    assert queue.claim(market.sessions) is None       # claimed once: a second worker gets nothing

def test_a_crashed_build_is_retried_then_reported(market, monkeypatch):
    result = plan(RackConfiguration(**rack_body()), [(256, 256, 256)])
    with market.sessions() as db: queue.request_build(db, result['hash'], result['spec']); db.commit()
    monkeypatch.setattr(queue, '_run', lambda *a: (1, '', 'kernel crashed'))
    assert queue.work_once(market.sessions)
    with market.sessions() as db:
        row = db.get(models.RackBuild, result['hash']); assert row.status == 'queued' and 'kernel crashed' in row.last_error
        row.next_attempt_at = datetime.now(timezone.utc); db.commit()
    assert queue.work_once(market.sessions)
    with market.sessions() as db: assert db.get(models.RackBuild, result['hash']).status == 'failed'
    public = market.clients['guest'].get(f'/api/racks/builds/{result["hash"]}').json()
    assert public['status'] == 'failed' and public['error']
    assert not list(queue.builds_dir().glob('.work-*'))
    # Asked for again soon it stays failed, so a bad design cannot spin the worker. Later it gets another chance.
    with market.sessions() as db:
        assert queue.request_build(db, result['hash'], result['spec']).status == 'failed'
        db.get(models.RackBuild, result['hash']).finished_at = datetime.now(timezone.utc) - timedelta(seconds=queue.RETRY_FAILED_SECONDS + 5); db.commit()
        assert queue.request_build(db, result['hash'], result['spec']).status == 'queued'
        db.commit()

def test_old_builds_are_cleaned_but_recent_ones_stay(market):
    old, recent = stand_in_build(market, rack_body()), stand_in_build(market, rack_body({P50: 5}))
    with market.sessions() as db:
        db.get(models.RackBuild, old['hash']).last_requested_at = datetime.now(timezone.utc) - timedelta(days=queue.RETENTION_DAYS + 1); db.commit()
    assert queue.clean(market.sessions) == 1
    assert not queue.build_path(old['hash']).exists() and queue.build_path(recent['hash']).exists()

# Real printers decide what can be bought ---------------------------------------------------------------------------
def test_printing_areas_come_from_approved_printers_that_stock_the_finish(market):
    guest = market.clients['guest']
    every = guest.post('/api/racks/plan', json=rack_body()).json()['availability']['envelopes']
    assert [(e['x'], e['y'], e['z'], e['hosts']) for e in every] == [(256, 256, 256, 1), (100, 100, 256, 1)]
    assert every[0]['usable'] == [246, 246, 251]
    # PETG is only on the larger printer, so the smaller area is not offered for it.
    petg = guest.post('/api/racks/plan', json=rack_body(material='PETG', color='red')).json()['availability']
    assert [e['x'] for e in petg['envelopes']] == [256]
    # Colours count too: blue PLA is not on the 100 mm printer, red PLA is.
    assert [e['x'] for e in guest.post('/api/racks/plan', json=rack_body(material='PLA', color='blue')).json()['availability']['envelopes']] == [256]
    assert [e['x'] for e in guest.post('/api/racks/plan', json=rack_body(material='PLA', color='red')).json()['availability']['envelopes']] == [256, 100]

def test_unapproved_or_suspended_hosts_do_not_offer_a_printing_area(market):
    with market.sessions() as db:
        row = db.scalar(select(models.HostApplication).where(models.HostApplication.user_id == market.ids['host']))
        row.status = 'suspended'; db.commit()
    assert [e['x'] for e in market.clients['guest'].post('/api/racks/plan', json=rack_body({P15: 1})).json()['availability']['envelopes']] == [100]

def test_a_finish_no_host_can_make_says_so_and_cannot_be_bought(market):
    body = rack_body({P50: 4}, material='PLA', color='green')
    result = market.clients['guest'].post('/api/racks/plan', json=body).json()
    selection = result['availability']['selection']
    assert selection == {'material': 'PLA', 'color': 'green', 'hosts': 0, 'ok': False, 'message': selection['message']}
    assert selection['message'].startswith('No Printing Host currently supports this combination')
    assert result['availability']['materials']          # what can be made instead
    stand_in_build(market, rack_body({P50: 4}))
    refused = market.clients['buyer'].post('/api/racks/listing', json={'config': rack_body({P50: 4}), 'material': 'PLA', 'color': 'green'})
    assert refused.status_code == 422 and refused.json()['detail']['code'] == 'no_host'
    assert market.clients['buyer'].get('/api/cart').json() == []

def test_a_host_count_follows_the_size_of_the_rack(market):
    guest = market.clients['guest']
    assert guest.post('/api/racks/plan', json=rack_body({P15: 1}, material='PLA', color='red')).json()['availability']['selection']['hosts'] == 2
    assert guest.post('/api/racks/plan', json=rack_body({P50: 16}, material='PLA', color='red')).json()['availability']['selection']['hosts'] == 1

def test_a_chosen_area_is_enforced_by_the_server(market):
    body = rack_body({P50: 16}, layout={'envelope': {'x': 100, 'y': 100, 'z': 256}})
    result = market.clients['guest'].post('/api/racks/plan', json=body).json()
    assert not result['ok'] and result['fit']['state'] == 'too_large'
    assert market.clients['guest'].post('/api/racks/builds', json=body).status_code == 422

def test_the_measured_solid_decides_who_can_print_it(market):
    """The plan fits, but the solid measures larger: only the solid's size counts, and the job follows it."""
    body = rack_body({P15: 2})
    result = stand_in_build(market, body)
    with market.sessions() as db:
        row = db.get(models.RackBuild, result['hash']); stored = json.loads(row.result)
        stored['metrics']['dims_mm'] = [120.0, 60.0, 64.0]; row.result = json.dumps(stored); db.commit()
    listed = market.clients['buyer'].post('/api/racks/listing', json={'config': body, 'material': 'PLA', 'color': 'red'})
    assert listed.status_code == 200, listed.text
    with market.sessions() as db:
        listing = db.get(models.Listing, listed.json()['listing_id'])
        assert json.loads(listing.cad_dimensions) == [120.0, 60.0, 64.0] and listing.dimensions.startswith('120')
    market.clients['buyer'].post('/api/cart', json={'listing_id': listed.json()['listing_id'], 'material': 'PLA', 'color': 'red', 'quantity': 1})
    order = checkout(market).json()
    with market.sessions() as db:
        assert job_ineligibility(db.get(models.PrintingJob, order['jobs'][0]['id']), market.ids['smallhost']) == 'printer'

def test_stock_lost_after_the_quote_stops_checkout_cleanly(market):
    q = to_cart(market)
    with market.sessions() as db:
        for uid in (market.ids['host'], market.ids['smallhost']): set_host_inventory(db, uid, {'PLA': {'black': '#000000'}})
        db.commit()
    line = market.clients['buyer'].get('/api/cart').json()[0]
    assert line['available'] is False and line['unavailable_reason']
    response = market.clients['buyer'].post('/api/checkout', json={'idempotency_key': secrets.token_hex(12), 'contact': CONTACT, 'confirmed': [{'listing_id': q['listing_id'], 'material': 'PLA', 'color': 'red', 'quantity': 1, 'unit_price_cents': q['unit_price_cents']}]})
    assert response.status_code == 422
    with market.sessions() as db: assert db.scalar(select(func.count()).select_from(models.Order)) == 0

def test_buy_now_goes_straight_through_checkout_without_touching_the_basket(market):
    existing = to_cart(market, body=rack_body({P50: 8}))
    body = rack_body({P50: 4})
    stand_in_build(market, body)
    client = market.clients['buyer']
    q = client.post('/api/racks/listing', json={'config': body, 'material': 'PLA', 'color': 'blue', 'quantity': 2}).json()
    line = {'listing_id': q['listing_id'], 'material': 'PLA', 'color': 'blue', 'quantity': 2}
    order = client.post('/api/checkout', json={'idempotency_key': secrets.token_hex(12), 'contact': CONTACT, 'direct': line, 'confirmed': [{**line, 'unit_price_cents': q['unit_price_cents']}]})
    assert order.status_code == 201, order.text
    assert order.json()['items'][0]['quantity'] == 2 and order.json()['total_cents'] == q['unit_price_cents'] * 2
    assert [l['listing_id'] for l in client.get('/api/cart').json()] == [existing['listing_id']]
    assert order.json()['items'][0]['rack']['tubes'][0]['quantity'] == 4

def test_an_order_names_the_rack_and_later_renames_do_not_reach_it(market):
    client = market.clients['buyer']
    _, data = order(market, name='Bench rack A')
    item = data['items'][0]
    assert item['rack']['name'] == 'Bench rack A' and item['rack']['estimated_grams'] > 0 and item['rack']['pricing_status'] == 'prototype'
    client.post('/api/racks/listing', json={'config': rack_body(), 'material': 'PLA', 'color': 'red', 'name': 'Renamed later'})
    assert client.get('/api/orders').json()[0]['items'][0]['rack']['name'] == 'Bench rack A'

def test_administrators_set_the_rates_and_orders_keep_their_price(market):
    admin, buyer = market.clients['admin'], market.clients['buyer']
    assert buyer.get('/api/admin/rack-pricing').status_code == 403
    rates = admin.get('/api/admin/rack-pricing').json()
    assert rates['commercially_validated'] is False and rates['marketplace_fee_pct'] == 12
    q, data = order(market)
    assert admin.put('/api/admin/rack-pricing', json={**rates, 'material_eur_per_kg': {'PLA': 1}}).status_code == 422
    assert admin.put('/api/admin/rack-pricing', json={**rates, 'setup_eur': rates['setup_eur'] + 10}).status_code == 200
    assert buyer.put('/api/admin/rack-pricing', json=rates).status_code == 403
    # The estimate moves at once, an earlier order does not, and a reorder takes today's rates.
    assert market.clients['guest'].post('/api/racks/plan', json=rack_body()).json()['estimates']['base_cents'] > q['base_price_cents']
    assert buyer.get('/api/orders').json()[0]['items'][0]['price_cents'] == q['unit_price_cents']
    again = buyer.post(f"/api/racks/orders/{data['items'][0]['id']}/reorder").json()
    assert again['unit_price_cents'] > q['unit_price_cents']
    assert admin.get('/api/admin/rack-pricing').json()['setup_eur'] == rates['setup_eur'] + 10

def test_a_rack_never_reaches_a_public_or_published_surface(market):
    q, _ = order(market)
    lid = q['listing_id']
    for who in ('guest', 'buyer', 'host', 'admin'):
        for path in ('/api/listings?per_page=50', '/api/listings?featured=true', '/api/listings?q=Custom%20rack', '/api/listings?category=Tube%20racks'):
            assert all(i['id'] != lid for i in market.clients[who].get(path).json()['items'])
    assert all(i['id'] != lid for i in market.clients['host'].get('/api/listings/mine').json())
    assert market.clients['admin'].get('/api/admin/overview').json()['products'] == 0
