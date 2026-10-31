"""My Orders shows the configuration that was bought: colour snapshots, previews and bounded queries."""
import json, struct, threading
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from order_fixtures import CONTACT, ADDRESS, provision_test_host
from test_marketplace import app, register, headers, SessionLocal
from app import config, models
from app.database import engine

REVISION = 'c' * 48

def fixture_host(db):
    provision_test_host(db)
    return db.scalar(select(models.User).where(models.User.role == 'host').order_by(models.User.id.desc()))

def approved_listing(db, owner_id, title='Snapshot rack', render=True):
    listing = models.Listing(owner_id=owner_id, title=title, description='Rack', category='Tube racks', price_cents=1200, material='PETG',
                             dimensions='20 mm', compatibility='Tubes', status='approved', cad_dimensions='[10, 10, 10]', configuration='{"materials": {"PETG": 10000, "PLA": 10000}}',
                             cad_path=REVISION + '.stl' if render else '')
    db.add(listing); db.flush()
    if render:
        folder = config.UPLOAD_DIR.parent / 'renders' / REVISION; folder.mkdir(parents=True, exist_ok=True)
        (folder / 'status.json').write_text('{"status":"ready"}')
    return listing

def order(client, token, key, lines):
    payload = {'idempotency_key': key, 'contact': CONTACT, 'address': ADDRESS, 'items': lines}
    response = client.post('/api/orders', json=payload, headers=headers(token))
    assert response.status_code == 201, response.text
    return response.json()

def test_order_lines_keep_the_purchased_colour_after_stock_changes():
    buyer = TestClient(app); token = register(buyer, 'colour-buyer@example.org')
    with SessionLocal() as db:
        host = fixture_host(db); listing = approved_listing(db, host.id); db.commit(); listing_id, host_id = listing.id, host.id
    created = order(buyer, token, 'colour_snapshot_key_0001', [
        {'listing_id': listing_id, 'material': 'PETG', 'color': 'signal-red', 'quantity': 2, 'expected_price_cents': 1200},
        {'listing_id': listing_id, 'material': 'PLA', 'color': 'aqua-blue', 'quantity': 1, 'expected_price_cents': 1200}])
    lines = {(i['material'], i['color']): i for i in created['items']}
    assert lines[('PETG', 'signal-red')]['color_hex'] == '#d9424d' and lines[('PETG', 'signal-red')]['quantity'] == 2
    assert lines[('PLA', 'aqua-blue')]['color_hex'] == '#429fb7'
    # Each fulfilment job carries the same snapshot for its own line.
    assert {(j['item']['color'], j['item']['color_hex']) for j in created['jobs']} == {('signal-red', '#d9424d'), ('aqua-blue', '#429fb7')}
    with SessionLocal() as db:
        printer = db.scalar(select(models.HostPrinter).where(models.HostPrinter.user_id == host_id))
        printer.material_colors = json.dumps({'PETG': {'signal-red': '#010101'}, 'PLA': {}}); db.commit()
    again = buyer.get('/api/orders?paginated=true').json()['items'][0]
    assert {(i['color'], i['color_hex']) for i in again['items']} == {('signal-red', '#d9424d'), ('aqua-blue', '#429fb7')}

def test_legacy_lines_without_a_colour_snapshot_are_not_guessed():
    buyer = TestClient(app); register(buyer, 'legacy-colour@example.org')
    uid = buyer.get('/api/auth/me').json()['user']['id']
    with SessionLocal() as db:
        host = fixture_host(db); listing = approved_listing(db, host.id, 'Legacy rack')
        o = models.Order(buyer_id=uid, reference='QA-LEGACY-COLOUR', idempotency_key='qa-legacy-colour', contact=CONTACT, address=ADDRESS, total_cents=1200)
        db.add(o); db.flush()
        db.add(models.OrderItem(order_id=o.id, listing_id=listing.id, title='Legacy rack', material='PETG', color='signal-red', dimensions='20 mm', quantity=1, price_cents=1200))
        db.commit()
    item = buyer.get('/api/orders').json()[0]['items'][0]
    # The current stock still offers signal-red as #d9424d, but that is not what was recorded.
    assert (item['color'], item['color_hex']) == ('signal-red', '')

def test_order_previews_follow_listing_visibility():
    buyer = TestClient(app); token = register(buyer, 'preview-buyer@example.org')
    with SessionLocal() as db:
        host = fixture_host(db); listing = approved_listing(db, host.id, 'Preview rack')
        plain = approved_listing(db, host.id, 'No render rack', render=False); db.commit(); listing_id, plain_id = listing.id, plain.id
    created = order(buyer, token, 'preview_visibility_0001', [
        {'listing_id': listing_id, 'material': 'PETG', 'color': 'black', 'quantity': 1, 'expected_price_cents': 1200},
        {'listing_id': plain_id, 'material': 'PETG', 'color': 'black', 'quantity': 1, 'expected_price_cents': 1200}])
    thumbs = {i['listing_id']: i['thumbnail'] for i in created['items']}
    assert thumbs[listing_id] == f'/api/listings/{listing_id}/visuals/{REVISION}/thumb.webp' and thumbs[plain_id] == ''
    with SessionLocal() as db:
        db.get(models.Listing, listing_id).removed = True; db.commit()
    # A removed product no longer exposes a preview URL; the order snapshot itself is unchanged.
    item = next(i for i in buyer.get('/api/orders').json()[0]['items'] if i['listing_id'] == listing_id)
    assert item['thumbnail'] == '' and item['title'] == 'Preview rack' and item['color'] == 'black'

def test_order_pages_use_a_fixed_number_of_queries():
    buyer = TestClient(app); register(buyer, 'query-buyer@example.org')
    uid = buyer.get('/api/auth/me').json()['user']['id']
    with SessionLocal() as db:
        host = fixture_host(db); listing = approved_listing(db, host.id, 'Query rack')
        for n in range(8):
            o = models.Order(buyer_id=uid, reference=f'QA-QUERIES-{n}', idempotency_key=f'qa-queries-{n}', contact=CONTACT, address=ADDRESS, total_cents=2400)
            db.add(o); db.flush()
            for k in range(2):
                item = models.OrderItem(order_id=o.id, listing_id=listing.id, title='Query rack', material='PETG', color='black', color_hex='#000000', dimensions='20 mm', quantity=1, price_cents=1200)
                db.add(item); db.flush(); db.add(models.PrintingJob(order_id=o.id, item_id=item.id))
            db.add(models.Activity(actor_id=uid, action='order.created', subject=f'order:{o.id}'))
        db.commit()
    statements = []
    def count(*args): statements.append(args[2])
    def queries(per_page):
        statements.clear(); event.listen(engine, 'before_cursor_execute', count)
        try: data = buyer.get(f'/api/orders?paginated=true&per_page={per_page}').json()
        finally: event.remove(engine, 'before_cursor_execute', count)
        assert len(data['items']) == per_page and all(o['history'] and len(o['jobs']) == 2 for o in data['items'])
        return len(statements)
    assert queries(2) == queries(8)

def test_host_job_list_checks_each_product_once(monkeypatch):
    from app import operations
    calls = []
    original = operations.combinations
    monkeypatch.setattr(operations, 'combinations', lambda product, host_id=None: calls.append(product.id) or original(product, host_id))
    buyer = TestClient(app); register(buyer, 'jobs-buyer@example.org')
    uid = buyer.get('/api/auth/me').json()['user']['id']
    with SessionLocal() as db:
        host = fixture_host(db); listing = approved_listing(db, host.id, 'Jobs rack', render=False)
        for n in range(3):
            o = models.Order(buyer_id=uid, reference=f'QA-JOBS-{n}', idempotency_key=f'qa-jobs-{n}', contact=CONTACT, address=ADDRESS, total_cents=1200)
            db.add(o); db.flush()
            item = models.OrderItem(order_id=o.id, listing_id=listing.id, title='Jobs rack', material='PETG', color='black', dimensions='20 mm', quantity=1, price_cents=1200)
            db.add(item); db.flush(); db.add(models.PrintingJob(order_id=o.id, item_id=item.id))
        db.commit(); host_email, listing_id = host.email, listing.id
    # The fixture host has no password: sign it in with a session row, as the login route would.
    import secrets
    from datetime import datetime, timedelta, timezone
    from app.main import digest
    token = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        user = db.scalar(select(models.User).where(models.User.email == host_email))
        db.add(models.LoginSession(token_hash=digest(token), user_id=user.id, csrf='csrf', expires_at=datetime.now(timezone.utc) + timedelta(days=1))); db.commit()
    client = TestClient(app); client.cookies.set('ol3d_session', token)
    jobs = client.get('/api/host/jobs').json()
    assert len([j for j in jobs if j['item']['listing_id'] == listing_id]) == 3
    assert calls.count(listing_id) == 1

STL = b'test'.ljust(80, b'\0') + struct.pack('<I', 1) + struct.pack('<12fH', 0, 0, 1, 0, 0, 0, 10, 0, 0, 0, 10, 10, 0)

def test_concurrent_render_requests_for_one_model_run_blender_once(tmp_path, monkeypatch):
    from app import render_product
    from PIL import Image
    started, release, runs = threading.Event(), threading.Event(), []
    def fake_blender(command, **kwargs):
        runs.append(command); started.set(); release.wait(5)
        work = __import__('pathlib').Path(command[-1]).parent
        Image.new('RGBA', (64, 64), (128, 128, 128, 255)).save(work / 'render.png'); (work / 'model.glb').write_bytes(b'glTF')
    monkeypatch.setattr(render_product.subprocess, 'run', fake_blender)
    source = tmp_path / 'cad' / ('d' * 48 + '.stl'); source.parent.mkdir(); source.write_bytes(STL)
    first = threading.Thread(target=render_product.render_asset, args=(source,)); first.start()
    assert started.wait(5)
    assert render_product.render_asset(source) is True   # dropped while the first render is running
    release.set(); first.join(5)
    assert len(runs) == 1
    assert json.loads((tmp_path / 'renders' / ('d' * 48) / 'status.json').read_text())['status'] == 'ready'
    render_product.render_asset(source)                    # a later request renders again
    assert len(runs) == 2
