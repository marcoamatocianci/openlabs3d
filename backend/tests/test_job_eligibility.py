"""Who may see and accept a printing job (availability.job_ineligibility), end to end over HTTP.

Hosts never manufacture their own orders, and a job needs one approved printer that fits the line
as sold and offers its exact material and shade. Isolated database; never the development one."""
import hashlib
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from app import config, database, models
from app.main import app
from app.availability import job_ineligibility, set_host_inventory
from app.equipment import seed_equipment
from app.pricing import OWN_PRINTERS_ONLY
from order_fixtures import CONTACT, ADDRESS

ORANGE, OTHER_ORANGE, BLUE, YELLOW = '#e66a3c', '#ff8800', '#2255cc', '#f2c230'
FULL = ((200, ('PLA', 'PETG')),)        # one 200 mm printer approved for PLA and PETG

@pytest.fixture
def market(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'eligibility.db'), connect_args={'check_same_thread': False, 'timeout': 10})
    database.Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'SessionLocal', sessions)
    monkeypatch.setattr(config, 'UPLOAD_DIR', tmp_path / 'data' / 'uploads')
    from app import custom_requests
    monkeypatch.setattr(custom_requests, 'STORAGE', tmp_path / 'data' / 'requests')
    clients, ids = {}, {}
    with sessions() as db:
        seed_equipment(db)
        # hostbuyer is an approved printing host who also buys.
        for name, role in [('buyer', 'buyer'), ('hostbuyer', 'host'), ('other', 'host'), ('third', 'host'), ('admin', 'admin')]:
            u = models.User(email=name + '@example.org', password_hash='unused', display_name=name, role=role, email_verified=True, first_name='Test', last_name=name, phone='123456789', country='IT', city='Torino')
            db.add(u); db.flush(); ids[name] = u.id
            token = secrets.token_urlsafe(32)
            db.add(models.LoginSession(user_id=u.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), csrf='test-csrf', expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
            c = TestClient(app); c.cookies.set('ol3d_session', token); c.headers['X-CSRF-Token'] = 'test-csrf'; clients[name] = c
            if role == 'host': db.add(models.HostApplication(user_id=u.id, status='approved'))
        rack = models.Listing(owner_id=ids['admin'], title='24-position microtube rack', status='approved', material='PLA', configuration='{"materials":{"PLA":10000,"PETG":12000}}', cad_dimensions='[100,100,100]', price_cents=1000)
        db.add(rack); db.commit()
    yield SimpleNamespace(clients=clients, ids=ids, rack=rack.id, sessions=sessions)
    for c in clients.values(): c.close()
    engine.dispose()

def equip(m, name, stock, printers=FULL):
    """Replace a host's approved printers ((x size in mm, approved materials), ...) and stock."""
    with m.sessions() as db:
        uid = m.ids[name]
        db.execute(delete(models.HostPrinter).where(models.HostPrinter.user_id == uid))
        for size, materials in printers:
            db.add(models.HostPrinter(user_id=uid, manufacturer='Custom', model=f'Printer {size}', technology='FDM', x=size, y=200, z=200, quantity=1, capabilities=json.dumps(list(materials))))
        set_host_inventory(db, uid, stock); db.commit()

def place(m, buyer, *lines, dims='[100,100,100]', text=''):
    """An order as stored at checkout, one job per line (material, colour, hex)."""
    with m.sessions() as db:
        order = models.Order(buyer_id=m.ids[buyer], reference='OL3D-' + secrets.token_hex(8).upper(), idempotency_key=secrets.token_hex(16), contact=CONTACT, address=ADDRESS, total_cents=1000 * len(lines))
        db.add(order); db.flush(); jobs = []
        for material, color, hex in lines:
            item = models.OrderItem(order_id=order.id, listing_id=m.rack, title='24-position microtube rack', material=material, color=color, color_hex=hex, dimensions=text, manufacturing_dimensions=dims, quantity=2, price_cents=1000)
            db.add(item); db.flush()
            job = models.PrintingJob(order_id=order.id, item_id=item.id); db.add(job); db.flush(); jobs.append(job.id)
        db.commit()
        return order.id, jobs

def checkout(m, name, material, color):
    """Buy one line through the real checkout, at the price this buyer is quoted."""
    c = m.clients[name]
    line = {'listing_id': m.rack, 'material': material, 'color': color, 'quantity': 1}
    q = c.post(f'/api/listings/{m.rack}/quote', json={k: line[k] for k in ('material', 'color', 'quantity')})
    price = q.json()['unit_price_cents'] if q.status_code == 200 else 0
    contact = {'first_name': 'Test', 'last_name': 'User', 'phone': '123456789', 'country': 'IT', 'city': 'Torino', 'street': 'Via Roma 1'}
    return c.post('/api/checkout', json={'idempotency_key': secrets.token_hex(16), 'contact': contact, 'direct': line, 'confirmed': [{**line, 'unit_price_cents': price}]})

def offered(m, name):
    return {j['id'] for j in m.clients[name].get('/api/host/jobs').json() if j['status'] == 'available'}

def reason(m, job_id, name):
    with m.sessions() as db:
        return job_ineligibility(db.get(models.PrintingJob, job_id), m.ids[name])

def job_row(m, job_id):
    with m.sessions() as db:
        job = db.get(models.PrintingJob, job_id)
        return job.status, job.host_id


def test_host_never_sees_or_accepts_their_own_order(market):
    m = market
    for name in ('hostbuyer', 'other'): equip(m, name, {'PETG': {'orange': ORANGE}})
    order = checkout(m, 'hostbuyer', 'PETG', 'orange')
    assert order.status_code == 201, order.text
    job_id = order.json()['jobs'][0]['id']
    assert job_id not in offered(m, 'hostbuyer')
    assert reason(m, job_id, 'hostbuyer') == 'own_order'
    refused = m.clients['hostbuyer'].post(f'/api/host/jobs/{job_id}/accept')
    assert refused.status_code == 403 and 'your own order' in refused.json()['detail']
    assert job_row(m, job_id) == ('available', None)
    # Another capable host is offered it and takes it.
    assert job_id in offered(m, 'other')
    assert m.clients['other'].post(f'/api/host/jobs/{job_id}/accept').status_code == 200
    # The host still sees it as a buyer in My Orders.
    mine = m.clients['hostbuyer'].get('/api/orders').json()
    assert [o['id'] for o in mine] == [order.json()['id']] and mine[0]['jobs'][0]['host_id'] == m.ids['other']
    assert mine[0]['status'] == 'accepted'

def test_claim_refuses_own_order_even_without_the_eligibility_check(market, monkeypatch):
    # The conditional UPDATE repeats the rule, so the claim holds even if the check is bypassed.
    m = market
    equip(m, 'hostbuyer', {'PETG': {'orange': ORANGE}})
    _, [job_id] = place(m, 'hostbuyer', ('PETG', 'orange', ORANGE))
    from app import operations
    monkeypatch.setattr(operations, 'job_ineligibility', lambda job, host: None)
    assert m.clients['hostbuyer'].post(f'/api/host/jobs/{job_id}/accept').status_code == 409
    assert job_row(m, job_id) == ('available', None)

def test_buyers_are_not_offered_what_only_their_own_printers_make(market):
    m = market
    equip(m, 'hostbuyer', {'PETG': {'orange': ORANGE}})
    equip(m, 'other', {'PLA': {'black': '#000000'}})
    anyone = TestClient(app)
    assert 'orange' in anyone.get(f'/api/listings/{m.rack}/availability').json()['colors_by_material']['PETG']
    assert 'orange' in m.clients['buyer'].get(f'/api/listings/{m.rack}/availability').json()['colors_by_material']['PETG']
    assert 'PETG' not in m.clients['hostbuyer'].get(f'/api/listings/{m.rack}/availability').json()['materials']
    config = {'material': 'PETG', 'color': 'orange', 'quantity': 1}
    assert anyone.post(f'/api/listings/{m.rack}/quote', json=config).status_code == 200
    for response in (m.clients['hostbuyer'].post(f'/api/listings/{m.rack}/quote', json=config),
                     m.clients['hostbuyer'].post('/api/cart', json={'listing_id': m.rack, **config}),
                     checkout(m, 'hostbuyer', 'PETG', 'orange')):
        assert response.status_code == 422 and response.json()['detail'] == OWN_PRINTERS_ONLY
    with m.sessions() as db: assert db.scalar(select(func.count()).select_from(models.Order)) == 0
    # Shade keys are worked out over every host, so both buyers see the same key for the same shade.
    equip(m, 'other', {'PETG': {'orange': OTHER_ORANGE}})
    keys = lambda name: set(m.clients[name].get(f'/api/listings/{m.rack}/availability').json()['colors_by_material']['PETG'])
    assert keys('buyer') == {'orange~e66a3c', 'orange~ff8800'} and keys('hostbuyer') == {'orange~ff8800'}
    order = checkout(m, 'hostbuyer', 'PETG', 'orange~ff8800')
    assert order.status_code == 201, order.text
    assert order.json()['items'][0]['color_hex'] == OTHER_ORANGE

def test_a_product_only_the_viewers_own_printers_make_says_so(market):
    # The configurator explains the empty offer instead of calling the product unavailable to everyone.
    m = market
    equip(m, 'hostbuyer', {'PETG': {'orange': ORANGE}})
    view = lambda client: client.get(f'/api/listings/{m.rack}/availability').json()
    mine = view(m.clients['hostbuyer'])
    assert mine['materials'] == {} and mine['own_printers_only'] is True
    for client in (m.clients['buyer'], TestClient(app)):
        assert view(client)['own_printers_only'] is False and 'PETG' in view(client)['materials']
    equip(m, 'hostbuyer', {})                      # nobody can make it: plainly unavailable
    assert view(m.clients['hostbuyer'])['own_printers_only'] is False and view(m.clients['buyer'])['materials'] == {}
    equip(m, 'hostbuyer', {'PETG': {'orange': ORANGE}}); equip(m, 'other', {'PETG': {'orange': ORANGE}})
    mine = view(m.clients['hostbuyer'])            # another host offers it: buyable again
    assert mine['own_printers_only'] is False and 'orange' in mine['colors_by_material']['PETG']

CASES = {
    'exact material and shade':              ({'PETG': {'orange': ORANGE}}, FULL, None),
    'PLA orange, job needs PETG orange':     ({'PLA': {'orange': ORANGE}}, FULL, 'material'),
    'PLA orange and PETG blue':              ({'PLA': {'orange': ORANGE}, 'PETG': {'blue': BLUE}}, FULL, 'color'),
    'PETG blue, job needs PETG orange':      ({'PETG': {'blue': BLUE}}, FULL, 'color'),
    'another orange shade':                  ({'PETG': {'orange': OTHER_ORANGE}}, FULL, 'color'),
    'stock but no approved printer':         ({'PETG': {'orange': ORANGE}}, (), 'printer'),
    'stock but printer too small':           ({'PETG': {'orange': ORANGE}}, ((50, ('PLA', 'PETG')),), 'printer'),
    'printer not approved for PETG':         ({'PETG': {'orange': ORANGE}}, ((200, ('PLA',)),), 'material'),
    'PETG only on a printer too small':      ({'PETG': {'orange': ORANGE}}, ((200, ('PLA',)), (50, ('PETG',))), 'material'),
}

@pytest.mark.parametrize('case', CASES)
def test_material_and_colour_match_together_on_one_fitting_printer(market, case):
    m = market
    stock, printers, expected = CASES[case]
    equip(m, 'other', stock, printers)
    _, [job_id] = place(m, 'buyer', ('PETG', 'orange', ORANGE))
    assert reason(m, job_id, 'other') == expected
    assert (job_id in offered(m, 'other')) == (expected is None)
    accept = m.clients['other'].post(f'/api/host/jobs/{job_id}/accept')
    assert accept.status_code == (200 if expected is None else 403), accept.text
    assert job_row(m, job_id) == (('accepted', m.ids['other']) if expected is None else ('available', None))

def test_inactive_or_unapproved_hosts_are_not_eligible(market):
    m = market
    equip(m, 'other', {'PETG': {'orange': ORANGE}})
    _, [job_id] = place(m, 'buyer', ('PETG', 'orange', ORANGE))
    with m.sessions() as db:
        db.scalar(select(models.HostApplication).where(models.HostApplication.user_id == m.ids['other'])).status = 'suspended'; db.commit()
    assert reason(m, job_id, 'other') == 'host'
    assert m.clients['other'].post(f'/api/host/jobs/{job_id}/accept').status_code == 403
    assert reason(m, job_id, 'admin') == 'host'       # accounts that are not hosts at all
    assert job_row(m, job_id) == ('available', None)

def test_acceptance_revalidates_current_stock(market):
    m = market
    equip(m, 'other', {'PETG': {'orange': ORANGE}})
    _, [job_id] = place(m, 'buyer', ('PETG', 'orange', ORANGE))
    assert job_id in offered(m, 'other')
    # The host removes PETG orange after the list was shown, then accepts the job still on screen.
    assert m.clients['other'].put('/api/host/materials', json={'material_colors': {'PETG': {'blue': BLUE}}}).status_code == 200
    refused = m.clients['other'].post(f'/api/host/jobs/{job_id}/accept')
    assert refused.status_code == 403 and 'do not stock PETG' in refused.json()['detail']
    assert job_row(m, job_id) == ('available', None) and job_id not in offered(m, 'other')
    assert m.clients['other'].put('/api/host/materials', json={'material_colors': {'PETG': {'orange': ORANGE}}}).status_code == 200
    assert m.clients['other'].post(f'/api/host/jobs/{job_id}/accept').status_code == 200

def test_two_eligible_hosts_accept_at_once_and_only_one_succeeds(market):
    m = market
    for name in ('other', 'third', 'hostbuyer'): equip(m, name, {'PETG': {'orange': ORANGE}})
    _, [job_id] = place(m, 'hostbuyer', ('PETG', 'orange', ORANGE))
    claim = lambda name: m.clients[name].post(f'/api/host/jobs/{job_id}/accept').status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        statuses = dict(zip(('other', 'third', 'hostbuyer'), pool.map(claim, ('other', 'third', 'hostbuyer'))))
    assert [statuses['other'], statuses['third']].count(200) == 1, statuses
    assert all(code in (200, 409, 503) for code in (statuses['other'], statuses['third']))
    assert statuses['hostbuyer'] in (403, 409, 503)   # never the buyer, whether or not the job was taken first
    status, host = job_row(m, job_id)
    assert status == 'accepted' and host == m.ids['other' if statuses['other'] == 200 else 'third']

def test_each_line_of_a_multi_item_order_needs_a_capable_host(market):
    # One job per order line: a host takes only lines they can make, and no line is dropped.
    m = market
    equip(m, 'other', {'PLA': {'orange': ORANGE}})
    equip(m, 'third', {'PETG': {'yellow': YELLOW}})
    order_id, (rack_job, petg_job) = place(m, 'buyer', ('PLA', 'orange', ORANGE), ('PETG', 'yellow', YELLOW))
    assert rack_job in offered(m, 'other') and petg_job not in offered(m, 'other')
    assert m.clients['other'].post(f'/api/host/jobs/{petg_job}/accept').status_code == 403
    assert m.clients['other'].post(f'/api/host/jobs/{rack_job}/accept').status_code == 200
    order = m.clients['buyer'].get('/api/orders').json()[0]
    assert order['id'] == order_id and [i['material'] for i in order['items']] == ['PLA', 'PETG']
    assert {j['id']: j['status'] for j in order['jobs']} == {rack_job: 'accepted', petg_job: 'available'} and order['status'] == 'pending'
    assert offered(m, 'third') == {petg_job}
    assert m.clients['third'].post(f'/api/host/jobs/{petg_job}/accept').status_code == 200
    assert m.clients['buyer'].get('/api/orders').json()[0]['status'] == 'accepted'

def test_jobs_are_sized_as_sold_not_from_the_listings_current_model(market):
    m = market
    equip(m, 'other', {'PETG': {'orange': ORANGE}})          # 200 mm printer
    _, [sold_small] = place(m, 'buyer', ('PETG', 'orange', ORANGE), dims='[100,100,100]')
    _, [sold_large] = place(m, 'buyer', ('PETG', 'orange', ORANGE), dims='[300,100,100]')
    _, [legacy_text] = place(m, 'buyer', ('PETG', 'orange', ORANGE), dims='[]', text='250 x 80 x 40 mm')
    _, [legacy_none] = place(m, 'buyer', ('PETG', 'orange', ORANGE), dims='[]', text='fits 2 mL tubes')
    with m.sessions() as db:
        db.get(models.Listing, m.rack).cad_dimensions = '[400,400,400]'; db.commit()   # a later, larger model
    assert reason(m, sold_small, 'other') is None
    assert reason(m, sold_large, 'other') == 'printer'
    assert reason(m, legacy_text, 'other') == 'printer'       # the size recorded with the line
    assert reason(m, legacy_none, 'other') == 'printer'       # no size recorded: the product's model
    with m.sessions() as db:
        db.get(models.Listing, m.rack).cad_dimensions = '[100,100,100]'; db.commit()
    assert reason(m, legacy_none, 'other') is None
    assert offered(m, 'other') == {sold_small, legacy_none}

def test_custom_requests_never_become_jobs_and_stay_in_my_requests(market):
    m = market
    for name in ('hostbuyer', 'other'): equip(m, name, {'PETG': {'orange': ORANGE}})
    payload = {'idempotency_key': secrets.token_hex(16), 'title': 'Rack for 50 mL tubes', 'application': 'Holds six 50 mL conical tubes upright on the bench.', 'dimensions': '120 x 80 x 60 mm', 'quantity': 2, 'material': 'PETG'}
    submitted = m.clients['hostbuyer'].post('/api/custom-requests', data={'payload': json.dumps(payload)})
    assert submitted.status_code == 201, submitted.text
    with m.sessions() as db: assert db.scalar(select(func.count()).select_from(models.PrintingJob)) == 0
    assert offered(m, 'hostbuyer') == set() and offered(m, 'other') == set()
    assert [r['id'] for r in m.clients['hostbuyer'].get('/api/custom-requests').json()] == [submitted.json()['id']]

def test_administrators_see_eligibility_and_existing_self_assignments(market):
    m = market
    equip(m, 'hostbuyer', {'PETG': {'orange': ORANGE}})
    equip(m, 'other', {'PETG': {'orange': ORANGE}})
    _, [open_job] = place(m, 'hostbuyer', ('PETG', 'orange', ORANGE))
    _, [only_buyer] = place(m, 'hostbuyer', ('PLA', 'orange', ORANGE))
    equip(m, 'hostbuyer', {'PETG': {'orange': ORANGE}, 'PLA': {'orange': ORANGE}})
    # A job a host accepted from their own order before the rule existed.
    legacy_order, [legacy] = place(m, 'hostbuyer', ('PETG', 'orange', ORANGE))
    with m.sessions() as db:
        job = db.get(models.PrintingJob, legacy); job.status, job.host_id = 'accepted', m.ids['hostbuyer']
        db.get(models.Order, legacy_order).status = 'accepted'; db.commit()
    admin = m.clients['admin']
    jobs = {j['id']: j for o in admin.get('/api/admin/orders').json() for j in o['jobs']}
    assert jobs[legacy]['conflict'] == 'own_order' and jobs[open_job]['conflict'] == ''
    why = {h['host_id']: h['reason'] for h in jobs[open_job]['eligibility']}
    assert why[m.ids['hostbuyer']] == 'buyer of this order' and why[m.ids['other']] == ''
    assert why[m.ids['third']] == 'no approved printer large enough'
    assert all(h['reason'] for h in jobs[only_buyer]['eligibility'])
    overview = admin.get('/api/admin/overview').json()
    assert overview['self_assigned_jobs'] == 1 and overview['unmatched_jobs'] == 1
    # Each overview warning opens exactly the orders behind it.
    flagged = lambda attention: [o['id'] for o in admin.get('/api/admin/orders', params={'paginated': True, 'attention': attention}).json()['items']]
    assert flagged('own-order') == [legacy_order]
    assert flagged('unmatched') == [next(o['id'] for o in admin.get('/api/admin/orders').json() if any(j['id'] == only_buyer for j in o['jobs']))]
    assert admin.get('/api/admin/orders', params={'paginated': True, 'attention': 'other'}).status_code == 422
    # Finished ones stay marked on the order but no longer need attention.
    with m.sessions() as db: db.get(models.PrintingJob, legacy).status = 'completed'; db.commit()
    assert admin.get('/api/admin/overview').json()['self_assigned_jobs'] == 0 and flagged('own-order') == []
    assert next(j for o in admin.get('/api/admin/orders').json() for j in o['jobs'] if j['id'] == legacy)['conflict'] == 'own_order'
    with m.sessions() as db: db.get(models.PrintingJob, legacy).status = 'accepted'; db.commit()
    detail = admin.get(f'/api/admin/jobs/{open_job}/eligibility')
    assert detail.status_code == 200 and {h['host_id'] for h in detail.json()['hosts'] if not h['reason']} == {m.ids['other']}
    assert m.clients['other'].get(f'/api/admin/jobs/{open_job}/eligibility').status_code == 403
    # Reported, never changed: the host still holds and can see the job, and nothing was cancelled.
    assert job_row(m, legacy) == ('accepted', m.ids['hostbuyer'])
    assert legacy in {j['id'] for j in m.clients['hostbuyer'].get('/api/host/jobs').json()}
    assert m.clients['hostbuyer'].get('/api/orders').json() and all(o['status'] != 'cancelled' for o in m.clients['hostbuyer'].get('/api/orders').json())
