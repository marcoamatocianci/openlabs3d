"""Adversarial checks from the stabilization audit (docs/architecture/STABILIZATION_AUDIT.md): what the integrity
tests did not try. Lying clients, rule changes, races, removed products, colour keys that change in a basket, payload
leaks and direct requests. The helpers and the isolated database come from test_marketplace_integrity."""
import hashlib, json, secrets
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
import test_marketplace_integrity as base
from test_marketplace_integrity import isolated_database, CAD_DIR, CONTACT_FORM, checkout, listing, login, orders_of, place_order, printer, set_price, stl, user  # noqa: F401
from test_marketplace import app
from app import models

BLACK = {'PLA': {'black': '#000000'}}

def market(price=1800, rules=None, cad=None, colors=BLACK):
    """A host who can make it, a buyer, an administrator and a published listing."""
    with base.SessionLocal() as db:
        admin, host, buyer = user(db, 'admin'), user(db, 'host'), user(db, 'buyer'); printer(db, host, colors)
        p = listing(db, admin, price=price, rules=rules, cad=cad if cad is not None else stl(10)); db.commit()
        return {'admin': admin.id, 'host': host.id, 'buyer': buyer.id, 'listing': p.id, 'cad': p.cad_path}

def line(m, quantity=1, material='PLA', color='black'):
    return {'listing_id': m['listing'], 'material': material, 'color': color, 'quantity': quantity}

# 4. Checkout price integrity ----------------------------------------------------------------------

def test_the_18_to_22_scenario_from_basket_to_order():
    m = market(price=1800); buyer = login(m['buyer'])
    item = buyer.post('/api/cart', json={**line(m), 'expected_unit_price_cents': 1800}).json()[0]
    assert (item['unit_price_cents'], item['price_changed']) == (1800, False)
    set_price(m['listing'], 2200)
    item = buyer.get('/api/cart').json()[0]
    assert item['price_changed'] and item['price_change']['previous_unit_price_cents'] == 1800 and item['price_change']['current_unit_price_cents'] == 2200
    assert '€18.00' in item['price_change']['message'] and '€22.00' in item['price_change']['message'], 'both amounts are shown'
    # Whatever the client says it saw, nothing is ordered until the new price is accepted.
    for said in (1800, 2200, 1):
        refused = checkout(buyer, [{**line(m), 'unit_price_cents': said}])
        assert refused.status_code == 409 and refused.json()['detail']['code'] == 'price_changed', said
    assert orders_of(m['buyer']) == 0
    assert buyer.post(f"/api/cart/{item['id']}/accept-price", json={'unit_price_cents': 1800}).status_code == 409, 'accepting an old amount is refused'
    assert buyer.post(f"/api/cart/{item['id']}/accept-price", json={'unit_price_cents': 2200}).json()[0]['price_changed'] is False
    order = checkout(buyer, [{**line(m), 'unit_price_cents': 2200}])
    assert order.status_code == 201 and order.json()['total_cents'] == 2200 and order.json()['items'][0]['price_cents'] == 2200

@pytest.mark.parametrize('said', [0, 1, 1799, 1801])
def test_client_prices_are_never_trusted(said):
    m = market(price=1800); buyer = login(m['buyer'])
    assert checkout(buyer, [{**line(m), 'unit_price_cents': said}], direct=line(m)).status_code == 409
    legacy = buyer.post('/api/orders', json={'idempotency_key': secrets.token_hex(12), 'contact': json.dumps(CONTACT_FORM), 'address': json.dumps(CONTACT_FORM),
                                             'items': [{**line(m), 'expected_price_cents': said}]})
    assert legacy.status_code in (409, 422) and orders_of(m['buyer']) == 0

def test_a_material_surcharge_or_discount_change_is_also_a_price_change():
    rules = {'materials': {'PLA': 10000}, 'discounts': {5: 1000}}
    m = market(price=1000, rules=rules); buyer = login(m['buyer']); five = line(m, quantity=5)
    item = buyer.post('/api/cart', json=five).json()[0]; assert item['unit_price_cents'] == 900
    with base.SessionLocal() as db:
        db.get(models.Listing, m['listing']).configuration = json.dumps({'materials': {'PLA': 12000}, 'discounts': {}}); db.commit()
    changed = buyer.get('/api/cart').json()[0]
    assert changed['price_changed'] and changed['unit_price_cents'] == 1200
    assert checkout(buyer, [{**five, 'unit_price_cents': 900}]).status_code == 409 and orders_of(m['buyer']) == 0

def test_totals_are_integer_cents_across_lines_and_discounts():
    rules = {'materials': {'PLA': 10333}, 'discounts': {3: 777}}
    m = market(price=1999, rules=rules); buyer = login(m['buyer'])
    q = buyer.post(f"/api/listings/{m['listing']}/quote", json={'material': 'PLA', 'color': 'black', 'quantity': 3}).json()
    assert isinstance(q['unit_price_cents'], int) and q['total_cents'] == q['unit_price_cents'] * 3
    order = checkout(buyer, [{**line(m, 3), 'unit_price_cents': q['unit_price_cents']}], direct=line(m, 3)).json()
    assert order['total_cents'] == q['total_cents']

def test_an_order_keeps_its_price_and_description_whatever_the_listing_becomes():
    m = market(price=1800); buyer = login(m['buyer'])
    order = checkout(buyer, [{**line(m), 'unit_price_cents': 1800}], direct=line(m)).json()
    with base.SessionLocal() as db:
        p = db.get(models.Listing, m['listing']); title = p.title; p.price_cents, p.title, p.material = 9900, 'Renamed', 'PETG'; db.commit()
    kept = next(o for o in buyer.get('/api/orders').json() if o['id'] == order['id'])
    assert (kept['total_cents'], kept['items'][0]['price_cents'], kept['items'][0]['title'], kept['items'][0]['material']) == (1800, 1800, title, 'PLA')

def test_a_price_change_racing_a_checkout_never_charges_an_unconfirmed_amount(tmp_path):
    """Run repeatedly: whichever lands first, an order exists only at the amount the buyer confirmed."""
    m = market(price=1800); buyer = login(m['buyer']); admin = login(m['admin'])
    for n in range(6):
        set_price(m['listing'], 1800)
        def order(_): return checkout(buyer, [{**line(m), 'unit_price_cents': 1800}], direct=line(m)).status_code
        def change(_):
            with base.SessionLocal() as db: db.get(models.Listing, m['listing']).price_cents = 2200; db.commit()
        with ThreadPoolExecutor(max_workers=2) as pool: code, _ = pool.submit(order, 0).result(), pool.submit(change, 0).result()
        assert code in (201, 409, 503)
    with base.SessionLocal() as db:
        assert {i.price_cents for i in db.scalars(select(models.OrderItem))} <= {1800}, 'never 2200'

# 5. Immutable CAD versions ------------------------------------------------------------------------

def test_new_orders_get_the_new_model_and_old_ones_keep_theirs():
    v1, v2 = stl(10), stl(14); m = market(cad=v1); admin = login(m['admin']); host = login(m['host'])
    first = place_order(m['buyer'], m['listing'])
    assert admin.post(f"/api/listings/{m['listing']}/cad", files={'file': ('v2.stl', v2)}).status_code == 200
    with base.SessionLocal() as db:
        p = db.get(models.Listing, m['listing']); p.status = 'approved'; db.commit()
    second = place_order(m['buyer'], m['listing'])
    for order, expected in ((first, v1), (second, v2)):
        job = order['jobs'][0]['id']; assert host.post(f'/api/host/jobs/{job}/accept').status_code == 200
        got = host.get(f'/api/jobs/{job}/cad'); assert got.content == expected and got.headers['x-content-sha256'] == hashlib.sha256(expected).hexdigest()

def test_a_removed_or_unpublished_product_does_not_break_or_change_an_accepted_job():
    v1 = stl(10); m = market(cad=v1); admin = login(m['admin']); host = login(m['host'])
    job = place_order(m['buyer'], m['listing'])['jobs'][0]['id']; host.post(f'/api/host/jobs/{job}/accept')
    assert admin.post(f"/api/admin/products/{m['listing']}/remove").status_code == 200
    assert host.get(f'/api/jobs/{job}/cad').content == v1

def test_a_reassigned_job_gives_the_new_host_the_purchased_version():
    v1, v2 = stl(10), stl(14); m = market(cad=v1); admin = login(m['admin']); first = login(m['host'])
    with base.SessionLocal() as db:
        other = user(db, 'host'); printer(db, other, BLACK); db.commit(); other_id = other.id
    job = place_order(m['buyer'], m['listing'])['jobs'][0]['id']; first.post(f'/api/host/jobs/{job}/accept')
    admin.post(f"/api/listings/{m['listing']}/cad", files={'file': ('v2.stl', v2)})
    assert admin.post(f'/api/admin/jobs/{job}/reopen').status_code == 200
    second = login(other_id); assert second.post(f'/api/host/jobs/{job}/accept').status_code == 200
    assert second.get(f'/api/jobs/{job}/cad').content == v1

def test_an_unverifiable_old_line_stays_flagged_and_is_never_given_a_guessed_file():
    m = market(); host = login(m['host'])
    job = place_order(m['buyer'], m['listing'])['jobs'][0]['id']; host.post(f'/api/host/jobs/{job}/accept')
    with base.SessionLocal() as db:
        item = db.get(models.PrintingJob, job).item; item.cad_path, item.cad_sha256, item.cad_status = '', '', 'none'; db.commit()
    assert host.get(f'/api/jobs/{job}/cad').status_code == 404, 'the listing’s current model is not substituted'

# 6. File authorisation ----------------------------------------------------------------------------

def test_every_way_to_a_manufacturing_file_refuses_the_wrong_person():
    m = market(); job = place_order(m['buyer'], m['listing'])['jobs'][0]['id']
    with base.SessionLocal() as db:
        stranger_host = user(db, 'host'); printer(db, stranger_host, BLACK); stranger = user(db, 'buyer'); db.commit(); sh, s = stranger_host.id, stranger.id
    host = login(m['host']); host.post(f'/api/host/jobs/{job}/accept')
    anonymous = TestClient(app)
    assert anonymous.get(f'/api/jobs/{job}/cad').status_code == 401
    assert anonymous.get(f"/api/listings/{m['listing']}/cad").status_code == 401
    for client in (login(sh), login(s), login(m['buyer'])):
        assert client.get(f'/api/jobs/{job}/cad').status_code == 404
        assert client.get(f"/api/listings/{m['listing']}/cad").status_code == 403
    assert host.get(f"/api/listings/{m['listing']}/cad").status_code == 403, 'hosts get the order’s file, not the listing’s'
    # The file names are not reachable another way, whatever the client tries.
    for path in (f"/api/cad/{m['cad']}", f"/cad/{m['cad']}", f"/data/cad/{m['cad']}", f"/api/jobs/{job}/cad/../../../data/cad/{m['cad']}"):
        assert anonymous.get(path).status_code in (401, 404, 405)
    assert host.get(f'/api/jobs/{job}/cad').status_code == 200

def test_a_suspended_account_loses_files_at_once():
    m = market(); host = login(m['host']); job = place_order(m['buyer'], m['listing'])['jobs'][0]['id']; host.post(f'/api/host/jobs/{job}/accept')
    assert host.get(f'/api/jobs/{job}/cad').status_code == 200
    with base.SessionLocal() as db: db.get(models.User, m['host']).active = False; db.commit()
    assert host.get(f'/api/jobs/{job}/cad').status_code in (401, 403)

def test_payloads_do_not_reveal_storage_paths():
    m = market(); buyer = login(m['buyer']); host = login(m['host'])
    order = place_order(m['buyer'], m['listing']); job = order['jobs'][0]['id']; host.post(f'/api/host/jobs/{job}/accept')
    for payload in (host.get('/api/host/jobs?scope=active').json(), buyer.get('/api/orders').json(), login(m['admin']).get('/api/admin/orders').json()):
        text = json.dumps(payload)
        assert m['cad'] not in text and '"cad_path"' not in text

def test_a_draft_products_previews_stay_private():
    m = market(); pid = m['listing']; stem = m['cad'].split('.')[0]
    with base.SessionLocal() as db: db.get(models.Listing, pid).status = 'draft'; db.commit()
    (base.CAD_DIR.parent / 'renders' / stem).mkdir(parents=True, exist_ok=True); (base.CAD_DIR.parent / 'renders' / stem / 'model.glb').write_bytes(b'glb')
    assert TestClient(app).get(f'/api/listings/{pid}/visuals/{stem}/model.glb').status_code == 404
    assert login(m['buyer']).get(f'/api/listings/{pid}/visuals/{stem}/model.glb').status_code == 404
    assert login(m['admin']).get(f'/api/listings/{pid}/visuals/{stem}/model.glb').status_code == 200

def test_a_replaced_models_old_preview_is_not_served():
    m = market(); pid = m['listing']; old = m['cad'].split('.')[0]; (base.CAD_DIR.parent / 'renders' / old).mkdir(parents=True, exist_ok=True); (base.CAD_DIR.parent / 'renders' / old / 'model.glb').write_bytes(b'glb')
    login(m['admin']).post(f'/api/listings/{pid}/cad', files={'file': ('v2.stl', stl(14))})
    with base.SessionLocal() as db: db.get(models.Listing, pid).status = 'approved'; db.commit()
    assert TestClient(app).get(f'/api/listings/{pid}/visuals/{old}/model.glb').status_code == 404

# 7. Exact material and colour ---------------------------------------------------------------------

def test_a_basket_line_never_silently_becomes_another_shade():
    m = market(colors={'PLA': {'orange': '#f58b1f'}}); buyer = login(m['buyer'])
    item = buyer.post('/api/cart', json=line(m, color='orange')).json()[0]; assert item['color_hex'] == '#f58b1f'
    with base.SessionLocal() as db:
        other = user(db, 'host'); printer(db, other, {'PLA': {'orange': '#e66a3c'}}); db.commit()
    # The name now has two shades: the old key is not quietly mapped to either of them.
    after = buyer.get('/api/cart').json()[0]
    assert after['available'] is False and 'unavailable_reason' in after
    assert checkout(buyer, [{**line(m, color='orange'), 'unit_price_cents': 1800}]).status_code == 422 and orders_of(m['buyer']) == 0
    colors = buyer.get(f"/api/listings/{m['listing']}/availability").json()['colors_by_material']['PLA']
    assert set(colors) == {'orange~f58b1f', 'orange~e66a3c'}

def test_the_order_records_the_shade_and_only_that_shades_host_can_take_it():
    m = market(colors={'PLA': {'orange': '#f58b1f'}})
    with base.SessionLocal() as db:
        other = user(db, 'host'); printer(db, other, {'PLA': {'orange': '#e66a3c'}}); db.commit(); other_id = other.id
    buyer = login(m['buyer']); key = 'orange~e66a3c'
    q = buyer.post(f"/api/listings/{m['listing']}/quote", json={'material': 'PLA', 'color': key, 'quantity': 1}).json()
    order = checkout(buyer, [{**line(m, color=key), 'unit_price_cents': q['unit_price_cents']}], direct=line(m, color=key)).json(); job = order['jobs'][0]['id']
    assert order['items'][0]['color_hex'] == '#e66a3c'
    assert job not in [j['id'] for j in login(m['host']).get('/api/host/jobs?scope=active').json()['items']]
    assert login(m['host']).post(f'/api/host/jobs/{job}/accept').status_code == 403
    assert login(other_id).post(f'/api/host/jobs/{job}/accept').status_code == 200

def test_a_colour_in_another_material_does_not_count():
    m = market(colors={'PETG': {'orange': '#f58b1f'}}, rules={'materials': {'PLA': 10000, 'PETG': 10000}}); buyer = login(m['buyer'])
    assert buyer.post(f"/api/listings/{m['listing']}/quote", json={'material': 'PLA', 'color': 'orange', 'quantity': 1}).status_code == 422

# 8. Administrative cancellation: unauthorised and forged requests -----------------------------------

def test_cancellation_cannot_be_forged():
    m = market(); order = place_order(m['buyer'], m['listing']); url = f"/api/admin/orders/{order['id']}/cancel"
    assert TestClient(app).post(url, json={'reason': 'Anonymous'}).status_code == 401
    for who in (m['buyer'], m['host']):
        assert login(who).post(url, json={'reason': 'Not an administrator'}).status_code == 403
    admin = login(m['admin']); no_csrf = TestClient(app); no_csrf.cookies = admin.cookies
    assert no_csrf.post(url, json={'reason': 'No CSRF token'}).status_code == 403
    assert admin.post(url, json={'reason': 'x'}).status_code == 422, 'a reason is required'
    assert admin.post(url, json={'reason': 'Valid reason', 'extra': 1}).status_code == 422
    with base.SessionLocal() as db: assert db.get(models.Order, order['id']).status == 'pending'

# 3. History sorting runs in the database -------------------------------------------------------------

def history(buyer_count=7):
    """Cancelled orders with distinct references and creation times, plus another buyer's."""
    from datetime import datetime, timedelta, timezone
    m = market(); admin = login(m['admin']); host = login(m['host']); ids = []
    for n in range(buyer_count):
        order = place_order(m['buyer'], m['listing']); ids.append(order['id']); host.post(f"/api/host/jobs/{order['jobs'][0]['id']}/accept")
        assert admin.post(f"/api/admin/orders/{order['id']}/cancel", json={'reason': 'History fixture'}).status_code == 200
    with base.SessionLocal() as db:
        other = user(db, 'buyer'); db.commit(); other_id = other.id
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Same time for two of them: only the id can keep their order stable across pages.
        for n, oid in enumerate(ids):
            db.get(models.Order, oid).created_at = start + timedelta(days=min(n, 5))
            db.scalar(select(models.PrintingJob).where(models.PrintingJob.order_id == oid)).updated_at = start + timedelta(days=min(n, 5))
        db.commit()
    return m, ids, other_id

@pytest.mark.parametrize('path, key', [('/api/orders?paginated=true&scope=history&group=cancelled', 'buyer'), ('/api/admin/orders?paginated=true&scope=history&group=cancelled', 'admin'), ('/api/host/jobs?scope=history&group=cancelled', 'host')])
def test_sorted_history_pages_do_not_overlap_or_skip(path, key):
    m, ids, _ = history(); client = login(m[key])
    def walk(sort):
        seen, page = [], 1
        while True:
            data = client.get(f'{path}&sort={sort}&per_page=3&page={page}').json()
            seen += [i.get('order_id', i['id']) for i in data['items']]
            assert data['total'] == len(ids)
            if page >= data['pages']: return seen
            page += 1
    newest, oldest = walk('newest'), walk('oldest')
    assert sorted(newest) == sorted(ids) and len(set(newest)) == len(ids), 'every record once, across pages'
    assert oldest == ids and newest == list(reversed(ids)), 'creation order, with the id breaking the tie'
    by_reference = walk('reference')
    with base.SessionLocal() as db:
        expected = [o.id for o in sorted((db.get(models.Order, i) for i in ids), key=lambda o: o.reference)]
    assert by_reference == expected

def test_sorted_columns_respect_the_sort_and_their_page_size():
    m, ids, _ = history(); admin = login(m['admin'])
    board = admin.get('/api/admin/orders?paginated=true&scope=history&columns=true&per_page=4&sort=oldest').json()
    cancelled = next(c for c in board['columns'] if c['key'] == 'cancelled')
    assert [o['id'] for o in cancelled['items']] == ids[:4] and cancelled['total'] == 7 and cancelled['pages'] == 2

@pytest.mark.parametrize('path', ['/api/orders?paginated=true&scope=history', '/api/admin/orders?paginated=true&scope=history', '/api/host/jobs?scope=history'])
@pytest.mark.parametrize('sort', ['price;DROP TABLE orders', 'created_at', '', 'id desc'])
def test_unknown_sorts_are_refused(path, sort):
    m = market(); who = {'/api/orders': m['buyer'], '/api/admin': m['admin'], '/api/host': m['host']}[next(k for k in ('/api/orders', '/api/admin', '/api/host') if path.startswith(k))]
    assert login(who).get(f'{path}&sort={sort}').status_code == 422

def test_sorting_keeps_ownership():
    m, ids, other_id = history(3)
    other = login(other_id)
    for sort in ('newest', 'oldest', 'reference'):
        assert other.get(f'/api/orders?paginated=true&scope=history&sort={sort}').json()['total'] == 0
    with base.SessionLocal() as db:
        stranger = user(db, 'host'); printer(db, stranger, BLACK); db.commit(); sid = stranger.id
    assert login(sid).get('/api/host/jobs?scope=history&sort=reference').json()['total'] == 0

def test_sorted_history_page_costs_the_same_however_long_the_history_is():
    from sqlalchemy import event
    m, ids, _ = history(8); buyer = login(m['buyer']); count = {'n': 0}
    def counter(*a): count['n'] += 1
    event.listen(base.engine, 'before_cursor_execute', counter)
    try:
        buyer.get('/api/orders?paginated=true&scope=history&group=cancelled&sort=reference&per_page=2'); few = count['n']; count['n'] = 0
        buyer.get('/api/orders?paginated=true&scope=history&group=cancelled&sort=reference&per_page=8'); many = count['n']
    finally: event.remove(base.engine, 'before_cursor_execute', counter)
    assert many == few, f'{few} queries for 2 orders, {many} for 8'
