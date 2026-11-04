"""Real concurrent requests (threads, separate connections) on the configured engine: run this file with
OPENLABS3D_TEST_POSTGRES_URL set to exercise PostgreSQL's advisory writer lock and row locking."""
import secrets, threading, time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import func, select
from test_marketplace_integrity import CONTACT_FORM, listing, login, printer, user, stl
import test_marketplace_integrity as integrity
from db_fixtures import isolate
from app import config, database, models

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    engine, factory, cleanup = isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(integrity, 'SessionLocal', factory)
    monkeypatch.setattr(config, 'UPLOAD_DIR', tmp_path / 'uploads' / 'products')
    yield factory
    cleanup()

BLACK = {'PLA': {'black': '#000000'}}

def order(factory, buyer_id, pid, key=None):
    client = login(buyer_id); direct = {'listing_id': pid, 'material': 'PLA', 'color': 'black', 'quantity': 1}
    price = client.post(f'/api/listings/{pid}/quote', json={'material': 'PLA', 'color': 'black', 'quantity': 1}).json()['unit_price_cents']
    return client.post('/api/checkout', json={'idempotency_key': key or secrets.token_hex(12), 'contact': CONTACT_FORM,
                                              'confirmed': [{**direct, 'unit_price_cents': price}], 'direct': direct})

def test_only_one_of_many_hosts_racing_for_a_job_gets_it(isolated):
    with isolated() as db:
        admin, buyer = user(db, 'admin'), user(db, 'buyer')
        hosts = [user(db, 'host') for _ in range(6)]
        for h in hosts: printer(db, h, BLACK)
        pid = listing(db, admin, cad=stl(10)).id; db.commit()
        buyer_id, host_ids = buyer.id, [h.id for h in hosts]
    placed = order(isolated, buyer_id, pid); assert placed.status_code == 201, placed.text
    job = placed.json()['jobs'][0]['id']
    clients = [login(h) for h in host_ids]; start = threading.Barrier(len(clients))
    def accept(client):
        start.wait(); return client.post(f'/api/host/jobs/{job}/accept').status_code
    with ThreadPoolExecutor(len(clients)) as pool: codes = list(pool.map(accept, clients))
    assert sorted(codes) == [200] + [409] * (len(clients) - 1), codes
    with isolated() as db:
        winner = host_ids[codes.index(200)]
        assert db.get(models.PrintingJob, job).host_id == winner and db.get(models.PrintingJob, job).status == 'accepted'
        assert db.scalar(select(func.count()).select_from(models.Activity).where(models.Activity.action == 'job.accepted')) == 1

def test_a_checkout_submitted_twice_at_once_makes_one_order(isolated):
    with isolated() as db:
        admin, buyer, host = user(db, 'admin'), user(db, 'buyer'), user(db, 'host'); printer(db, host, BLACK)
        pid = listing(db, admin).id; db.commit(); buyer_id = buyer.id
    key = secrets.token_hex(12); start = threading.Barrier(4)
    def submit(_):
        start.wait(); return order(isolated, buyer_id, pid, key)
    with ThreadPoolExecutor(4) as pool: results = list(pool.map(submit, range(4)))
    assert {r.status_code for r in results} <= {200, 201} and len({r.json()['id'] for r in results}) == 1
    with isolated() as db:
        assert db.scalar(select(func.count()).select_from(models.Order).where(models.Order.buyer_id == buyer_id)) == 1
        assert db.scalar(select(func.count()).select_from(models.PrintingJob)) == 1

def test_reads_are_not_blocked_by_a_write_in_progress(isolated):
    with isolated() as db:
        admin = user(db, 'admin'); pid = listing(db, admin).id; db.commit()
    reader = login(admin.id)   # signing in writes a session row, so it happens before the writer holds the lock
    held, release = threading.Event(), threading.Event()
    def writer():
        with isolated() as db:
            database.write_lock(db); db.get(models.Listing, pid).title = 'Being edited'; db.flush()
            held.set(); release.wait(10); db.commit()
    thread = threading.Thread(target=writer); thread.start(); assert held.wait(5)
    try:
        started = time.perf_counter(); r = reader.get(f'/api/listings/{pid}')
        assert r.status_code == 200 and r.json()['title'] != 'Being edited' and time.perf_counter() - started < 2
    finally:
        release.set(); thread.join()
