"""Email verification and transactional email, against an isolated database with a fake mail server. No real credentials."""
import json, re, secrets, socketserver, threading, sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
import test_marketplace_integrity as base
from test_marketplace_integrity import isolated_database, listing, printer, user  # noqa: F401
from test_marketplace import app
from app import config, email_service, main, models

PASSWORD = 'Openlabs2026'

@pytest.fixture(autouse=True)
def mailbox(monkeypatch):
    """Everything sent lands in this list. Throttles start empty for each test."""
    sent = []
    def fake(message): sent.append(message)
    monkeypatch.setattr(email_service, 'deliver', fake)
    monkeypatch.setattr(email_service, 'configuration_problems', lambda: [])
    main.rate.clear()
    yield sent

def flush(): return email_service.process_due(base.SessionLocal)
def body(message, kind='plain'): return message.get_body((kind,)).get_content()
def token_in(message): return re.search(r'token=([A-Za-z0-9_-]+)', body(message))[1]
def link_in(message): return re.search(r'https?://\S+', body(message))[0]
def jobs(**match):
    with base.SessionLocal() as db:
        return [j for j in db.scalars(select(models.EmailJob).order_by(models.EmailJob.id)) if all(getattr(j, k) == v for k, v in match.items())]
def account(email):
    with base.SessionLocal() as db: return db.scalar(select(models.User).where(models.User.email == email))
def edit(email, **values):
    with base.SessionLocal() as db:
        u = db.scalar(select(models.User).where(models.User.email == email))
        for k, v in values.items(): setattr(u, k, v)
        db.commit()
def register(email='ada@example.org', username=None, password=PASSWORD):
    return TestClient(app).post('/api/auth/register', json={'email': email, 'username': username or 'u' + secrets.token_hex(5), 'password': password})
def login(email='ada@example.org', password=PASSWORD, client=None):
    return (client or TestClient(app)).post('/api/auth/login', json={'email': email, 'password': password})
def verify(token, client=None): return (client or TestClient(app)).post('/api/auth/verify', json={'token': token})
def verified_client(email='ada@example.org'):
    register(email); flush(); assert verify(token_in(mail_to(email)[-1])).status_code == 200
    client = TestClient(app); r = login(email, client=client); assert r.status_code == 200, r.text
    client.headers['X-CSRF-Token'] = r.json()['csrf_token']
    return client
mail_to = lambda address: [m for m in current_mail if m['To'] == address]
current_mail = []
@pytest.fixture(autouse=True)
def bind_mail(mailbox):
    global current_mail
    current_mail = mailbox

# Registration ----------------------------------------------------------------------------------

def test_registering_creates_an_unverified_account_and_a_verification_email_but_no_session(mailbox):
    client = TestClient(app)
    r = client.post('/api/auth/register', json={'email': 'Ada@Example.org', 'username': 'ada_lab', 'password': PASSWORD})
    assert r.status_code == 201 and r.json()['verification_required'] and r.json()['email'] == 'ada@example.org'
    assert 'csrf_token' not in r.json() and 'user' not in r.json() and 'ol3d_session' not in r.cookies
    assert client.get('/api/auth/me').status_code == 401
    u = account('ada@example.org')
    assert not u.email_verified and u.email_verified_at is None and not u.legacy_email_access
    assert not mailbox, 'a request only queues; the worker sends'
    assert flush() == 1 and mailbox[0]['To'] == 'ada@example.org'
    assert jobs(kind='verify_email')[0].status == 'sent'

def test_the_verification_email_has_both_parts_and_a_link_on_the_configured_address(monkeypatch, mailbox):
    monkeypatch.setattr(config, 'APP_PUBLIC_URL', 'https://labs.example.net')
    # A forged Host header cannot change where the link points.
    TestClient(app).post('/api/auth/register', headers={'host': 'evil.example.com', 'x-forwarded-host': 'evil.example.com'}, json={'email': 'ada@example.org', 'username': 'ada_lab', 'password': PASSWORD})
    flush(); message = mailbox[0]
    assert link_in(message).startswith('https://labs.example.net/#verify-email?token=')
    text, page = body(message), body(message, 'html')
    assert 'evil.example.com' not in text + page
    assert 'Welcome to OpenLabs3D' in text and 'expires in 24 hours' in text and "If you didn't create an account" in text
    assert 'Verify Email Address' in page and 'https://labs.example.net/#verify-email?token=' in page and '<table' in page
    assert message['Subject'] and message['Message-ID'] and message.get_content_type() == 'multipart/alternative'

def test_tokens_are_random_and_only_their_hash_is_stored(mailbox):
    register('a@example.org'); register('b@example.org'); flush()
    first, second = token_in(mailbox[0]), token_in(mailbox[1])
    assert first != second and len(first) >= 43
    with base.SessionLocal() as db:
        rows = list(db.scalars(select(models.AccountToken)))
        jobs_text = json.dumps([[j.context, j.last_error] for j in db.scalars(select(models.EmailJob))])
    assert len(rows) == 2 and not {r.token_hash for r in rows} & {first, second}
    assert first not in jobs_text and second not in jobs_text, 'the queue never holds a usable link'

def test_duplicate_registration_cannot_be_told_from_a_new_one_and_changes_nothing(mailbox):
    client = verified_client('ada@example.org'); before = account('ada@example.org')
    mailbox.clear()
    fresh, duplicate = register('new@example.org', 'new_user'), register('ADA@example.org', 'someone_else', 'OtherPassword2026')
    assert duplicate.status_code == fresh.status_code == 201
    strip = lambda r: {k: v for k, v in r.json().items() if k != 'email'}
    assert strip(duplicate) == strip(fresh) and 'ol3d_session' not in duplicate.cookies
    after = account('ada@example.org')
    assert after.password_hash == before.password_hash and after.username == before.username and after.email_verified
    with base.SessionLocal() as db: assert db.scalar(select(models.User).where(models.User.username == 'someone_else')) is None
    assert login().status_code == 200 and login(password='OtherPassword2026').status_code == 401
    flush()
    notice = mail_to('ada@example.org')[0]
    assert 'already has an account' in body(notice) and 'token=' not in body(notice), 'its owner is told, with no link to act on'
    assert client.get('/api/auth/me').status_code == 200

def test_a_taken_username_is_still_refused_and_existing_validation_stays():
    register('a@example.org', 'taken_name')
    assert register('b@example.org', 'TAKEN_NAME').status_code == 409
    assert register('not-an-email', 'valid_name').status_code == 422
    assert register('c@example.org', 'valid_name', 'nouppercase1').status_code == 422
    assert register('c@example.org', 'bad name!').status_code == 422

def test_simultaneous_registrations_of_one_address_make_one_account():
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda n: register('race@example.org', f'race_{n}').status_code, range(4)))
    assert statuses == [201] * 4
    with base.SessionLocal() as db: assert len(list(db.scalars(select(models.User).where(models.User.email == 'race@example.org')))) == 1

def test_registering_again_while_unverified_resends_when_the_password_matches(mailbox):
    register(); flush(); edit('ada@example.org'); mailbox.clear()
    with base.SessionLocal() as db:
        for j in db.scalars(select(models.EmailJob)): j.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    assert register().status_code == 201
    flush(); assert len(mailbox) == 1 and 'Verify Email Address' in body(mailbox[0])
    assert verify(token_in(mailbox[0])).status_code == 200 and login().status_code == 200

def test_someone_registering_an_address_first_cannot_keep_a_password_on_it(mailbox):
    """Pre-account hijacking: an attacker registers the victim's address, then the victim registers too."""
    attacker = 'AttackerPassword2026'; victim = 'VictimPassword2026'
    register(password=attacker); flush(); first_link = token_in(mailbox[0]); mailbox.clear()
    with base.SessionLocal() as db:
        for j in db.scalars(select(models.EmailJob)): j.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    assert register(password=victim).status_code == 201
    flush(); finish = mailbox[0]
    assert 'Choose a Password' in body(finish)
    assert verify(first_link).json()['detail']['code'] == 'invalid', 'the link sent for the earlier registration no longer works'
    assert TestClient(app).post('/api/auth/reset-password', json={'token': token_in(finish), 'password': 'ChosenByOwner2026'}).status_code == 200
    for password in (attacker, victim): assert login(password=password).status_code == 401
    assert login(password='ChosenByOwner2026').status_code == 200 and account('ada@example.org').email_verified

# Usernames -------------------------------------------------------------------------------------

def test_a_taken_username_says_nothing_about_the_address(mailbox):
    """Refused the same way for a registered and an unregistered address, or the refusal would reveal which it is."""
    verified_client('owner@example.org'); register('holder@example.org', 'taken_name'); mailbox.clear()
    answers = [register(email, 'taken_name') for email in ('owner@example.org', 'holder@example.org', 'nobody@example.org')]
    assert [r.status_code for r in answers] == [409] * 3 and len({r.text for r in answers}) == 1
    assert 'open the link we sent you' in answers[0].json()['detail']
    flush(); assert not mail_to('owner@example.org') and not mail_to('nobody@example.org'), 'a refusal sends nothing'
    with base.SessionLocal() as db: assert db.scalar(select(models.User).where(models.User.email == 'nobody@example.org')) is None

def test_deleting_an_account_releases_its_username_and_address(mailbox):
    client = verified_client('ada@example.org'); name = account('ada@example.org').username
    assert client.request('DELETE', '/api/profile', json={'password': PASSWORD}).status_code == 200
    assert TestClient(app).get('/api/auth/username', params={'username': name}).json()['available']
    assert register('ada@example.org', name).status_code == 201
    assert account('ada@example.org').username == name and not account('ada@example.org').email_verified
    mailbox.clear(); flush()
    assert verify(token_in(mail_to('ada@example.org')[-1])).status_code == 200 and login().status_code == 200

def test_an_administrator_deleting_an_account_releases_its_username_too(mailbox):
    verified_client('ada@example.org'); name = account('ada@example.org').username
    with base.SessionLocal() as db:
        admin = models.User(email='boss@example.org', username='boss', display_name='boss', role='admin', email_verified=True, password_hash=main.hasher.hash(PASSWORD)); db.add(admin); db.commit()
    boss = TestClient(app); boss.headers['X-CSRF-Token'] = login('boss@example.org', client=boss).json()['csrf_token']
    assert boss.request('DELETE', f"/api/admin/users/{account('ada@example.org').id}", json={'password': PASSWORD}).status_code == 200
    assert register('other@example.org', name).status_code == 201

def test_registering_again_while_unconfirmed_takes_the_new_username(mailbox):
    """It was silently dropped: the page answered as usual and the account kept the earlier name."""
    register('ada@example.org', 'first_choice'); flush(); age_jobs(5)
    assert register('ada@example.org', 'second_choice').status_code == 201
    assert account('ada@example.org').username == 'second_choice' and account('ada@example.org').display_name == 'second_choice'
    assert TestClient(app).get('/api/auth/username', params={'username': 'first_choice'}).json()['available']
    # With another password too: whoever holds the inbox finishes it, under the latest name.
    assert register('ada@example.org', 'third_choice', 'OtherPassword2026').status_code == 201
    assert account('ada@example.org').username == 'third_choice'

def test_registering_on_a_verified_address_never_renames_it(mailbox):
    verified_client('ada@example.org'); name = account('ada@example.org').username
    assert register('ada@example.org', 'hijacked_name').status_code == 201
    assert account('ada@example.org').username == name
    assert TestClient(app).get('/api/auth/username', params={'username': 'hijacked_name'}).json()['available']

def age_account(email, days):
    with base.SessionLocal() as db:
        u = db.scalar(select(models.User).where(models.User.email == email)); u.created_at = datetime.now(timezone.utc) - timedelta(days=days)
        for t in db.scalars(select(models.AccountToken).where(models.AccountToken.user_id == u.id)): t.expires_at = datetime.now(timezone.utc) - timedelta(days=days - 1)
        db.commit()

def test_a_sign_up_never_confirmed_gives_up_its_name_and_address(mailbox):
    register('gone@example.org', 'wanted_name'); flush(); age_account('gone@example.org', 8)
    email_service.purge(base.SessionLocal)
    assert account('gone@example.org') is None
    assert TestClient(app).get('/api/auth/username', params={'username': 'wanted_name'}).json()['available']
    assert register('someone@example.org', 'wanted_name').status_code == 201

def test_only_abandoned_sign_ups_are_removed(mailbox):
    register('recent@example.org'); flush()
    register('verified@example.org'); edit('verified@example.org', email_verified=True); age_account('verified@example.org', 90)
    register('legacy@example.org'); edit('legacy@example.org', legacy_email_access=True); age_account('legacy@example.org', 90)
    register('livelink@example.org'); flush(); age_account('livelink@example.org', 8)
    with base.SessionLocal() as db:
        u = db.scalar(select(models.User).where(models.User.email == 'livelink@example.org'))
        for t in db.scalars(select(models.AccountToken).where(models.AccountToken.user_id == u.id)): t.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
    email_service.purge(base.SessionLocal)
    for email in ('recent@example.org', 'verified@example.org', 'legacy@example.org', 'livelink@example.org'): assert account(email) is not None, email

def test_retention_follows_the_configuration(monkeypatch, mailbox):
    monkeypatch.setattr(config, 'UNVERIFIED_ACCOUNT_RETENTION_DAYS', 30)
    register('patient@example.org'); flush(); age_account('patient@example.org', 8)
    email_service.purge(base.SessionLocal)
    assert account('patient@example.org') is not None

# Verification ----------------------------------------------------------------------------------

def test_a_valid_link_verifies_once_and_records_when(mailbox):
    register(); flush(); token = token_in(mailbox[0])
    r = verify(token)
    assert r.status_code == 200 and r.json()['status'] == 'verified' and 'ol3d_session' not in r.cookies
    u = account('ada@example.org')
    assert u.email_verified and u.email_verified_at is not None
    reused = verify(token)
    assert reused.status_code == 400 and reused.json()['detail']['code'] == 'used'

def test_expired_and_unknown_links_are_refused_and_do_not_verify(mailbox):
    register(); flush(); token = token_in(mailbox[0])
    with base.SessionLocal() as db:
        for row in db.scalars(select(models.AccountToken)): row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    expired = verify(token)
    assert expired.status_code == 400 and expired.json()['detail']['code'] == 'expired'
    unknown = verify('x' * 43)
    assert unknown.status_code == 400 and unknown.json()['detail']['code'] == 'invalid'
    assert not account('ada@example.org').email_verified and login().status_code == 403

def test_expiry_follows_the_configuration(monkeypatch, mailbox):
    monkeypatch.setattr(config, 'EMAIL_VERIFICATION_EXPIRY_HOURS', 2)
    register(); flush()
    assert 'expires in 2 hours' in body(mailbox[0])
    with base.SessionLocal() as db: row = db.scalar(select(models.AccountToken))
    left = row.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(hours=1, minutes=59) < left <= timedelta(hours=2)

def test_a_link_of_another_purpose_does_not_verify(mailbox):
    client = verified_client(); mailbox.clear()
    TestClient(app).post('/api/auth/forgot-password', json={'email': 'ada@example.org'}); flush()
    reset = token_in(mailbox[0])
    assert verify(reset).json()['detail']['code'] == 'invalid'
    assert client.get('/api/auth/me').status_code == 200

def test_simultaneous_verifications_succeed_exactly_once(mailbox):
    register(); flush(); token = token_in(mailbox[0])
    # A pool of real concurrent requests against one token.
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: verify(token).status_code, range(6)))
    assert results.count(200) == 1 and results.count(400) == 5, results
    with base.SessionLocal() as db:
        assert len(list(db.scalars(select(models.Activity).where(models.Activity.action == 'user.email_verified')))) == 1

def test_verification_attempts_are_rate_limited():
    for _ in range(60): assert verify('x' * 43).status_code == 400
    assert verify('x' * 43).status_code == 429

# Login and restrictions ------------------------------------------------------------------------

def test_login_before_verification_is_refused_and_says_why_only_with_the_right_password(mailbox):
    register(); flush()
    wrong = login(password='WrongPassword2026')
    assert wrong.status_code == 401 and wrong.json() == login('nobody@example.org').json(), 'indistinguishable from an unknown address'
    client = TestClient(app); r = login(client=client)
    assert r.status_code == 403 and r.json()['detail']['code'] == 'email_unverified' and 'ol3d_session' not in r.cookies
    assert verify(token_in(mailbox[0])).status_code == 200
    assert login(client=client).status_code == 200 and client.get('/api/auth/me').json()['user']['email_verified']

def test_login_takes_as_long_for_an_unknown_address(monkeypatch):
    checked = []
    real = main.hasher.verify
    monkeypatch.setattr(main.hasher.__class__, 'verify', lambda self, stored, password: (checked.append(stored), real(stored, password))[1])
    login('nobody@example.org')
    assert checked == [main.NO_ACCOUNT_HASH], 'a password hash is still checked'

def test_a_session_cannot_outlive_the_requirement(mailbox):
    """Enforced for every request, not only at login: a stray session of an unverified account is signed out."""
    client = verified_client(); assert client.get('/api/auth/me').status_code == 200
    edit('ada@example.org', email_verified=False)
    assert client.get('/api/auth/me').status_code == 401 and client.get('/api/cart').status_code == 401

def test_legacy_unverified_accounts_sign_in_but_cannot_use_protected_actions(mailbox):
    register(); edit('ada@example.org', legacy_email_access=True)
    client = TestClient(app); r = login(client=client); assert r.status_code == 200
    client.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert not client.get('/api/auth/me').json()['user']['email_verified'], 'never shown as verified'
    with base.SessionLocal() as db:
        owner = user(db, 'admin'); printer(db, user(db, 'host'), {'PLA': {'black': '#000000'}}); p = listing(db, owner); db.commit(); pid = p.id
    line = {'listing_id': pid, 'material': 'PLA', 'color': 'black', 'quantity': 1}
    assert base.checkout(client, [{**line, 'unit_price_cents': 1800}], line).status_code == 403, 'cannot order'
    assert client.post('/api/listings', json={}).status_code == 403, 'cannot create a listing'
    assert client.put('/api/host/equipment-application', json={'submit': True, 'printers': []}).status_code == 403, 'cannot apply as a host'

def test_a_host_who_is_not_verified_cannot_accept_a_job(mailbox):
    from test_marketplace_integrity import place_order
    with base.SessionLocal() as db:
        admin, host, buyer = user(db, 'admin'), user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000'}}); p = listing(db, admin); db.commit(); ids = host.id, buyer.id, p.id
    order = place_order(ids[1], ids[2])
    client = base.login(ids[0])
    with base.SessionLocal() as db:
        u = db.get(models.User, ids[0]); u.email_verified, u.legacy_email_access = False, True; db.commit()
    assert client.post(f"/api/host/jobs/{order['jobs'][0]['id']}/accept").status_code == 403

# Resend ----------------------------------------------------------------------------------------

def resend(email='ada@example.org', client=None): return (client or TestClient(app)).post('/api/auth/resend-verification', json={'email': email})
def age_jobs(minutes):
    with base.SessionLocal() as db:
        for j in db.scalars(select(models.EmailJob)): j.created_at = j.created_at.replace(tzinfo=timezone.utc) - timedelta(minutes=minutes)
        db.commit()

def test_resend_answers_the_same_for_every_address(mailbox):
    register('waiting@example.org'); verified_client('done@example.org'); flush(); mailbox.clear(); age_jobs(5)
    answers = [resend(a) for a in ('waiting@example.org', 'waiting@example.org', 'done@example.org', 'nobody@example.org')]
    assert {r.status_code for r in answers} == {200} and len({json.dumps(r.json()) for r in answers}) == 1
    assert 'If an account requiring verification exists' in answers[0].json()['message']
    flush()
    assert [m['To'] for m in mailbox] == ['waiting@example.org'], 'one message, only to the address that needs it'

def test_resend_has_a_cooldown_and_replaces_the_earlier_link(mailbox):
    register(); flush(); first = token_in(mailbox[0])
    resend(); assert flush() == 0, 'within the cooldown nothing more is sent'
    age_jobs(2)
    resend(); assert flush() == 1
    second = token_in(mailbox[1])
    assert verify(first).json()['detail']['code'] == 'invalid', 'the earlier link no longer works'
    assert verify(second).status_code == 200

def test_resend_has_an_hourly_limit_per_address(mailbox):
    register(); flush()
    for _ in range(9):
        age_jobs(2); main.rate.clear(); resend()
    flush()
    assert len(mailbox) == config.EMAIL_RESEND_HOURLY_LIMIT, 'an address cannot be flooded'

def test_resend_is_rate_limited_per_client():
    for n in range(30): assert resend(f'{n}@example.org').status_code == 200
    assert resend('more@example.org').status_code == 429

def test_duplicate_registrations_cannot_flood_an_address(mailbox):
    verified_client(); mailbox.clear()
    for _ in range(4): register()
    flush()
    assert len(mailbox) == 1

def signed_in_legacy(email='ada@example.org'):
    register(email); edit(email, legacy_email_access=True); flush(); age_jobs(5)
    client = TestClient(app); client.headers['X-CSRF-Token'] = login(email, client=client).json()['csrf_token']
    return client

def test_a_page_open_from_before_the_address_was_required_can_still_resend(mailbox):
    """A tab loaded before an update sends an empty body: signed in, that means the account's own address."""
    client = signed_in_legacy(); mailbox.clear()
    r = client.post('/api/auth/resend-verification', json={})
    assert r.status_code == 200 and 'on its way to ada@example.org' in r.json()['message']
    assert flush() == 1 and mailbox[0]['To'] == 'ada@example.org'
    assert TestClient(app).post('/api/auth/resend-verification', json={}).status_code == 422, 'signed out, an address is needed'

def test_someone_signed_in_is_told_what_happened_to_their_own_address(mailbox):
    client = signed_in_legacy(); mailbox.clear()
    assert 'on its way' in client.post('/api/auth/resend-verification', json={'email': 'ada@example.org'}).json()['message']
    assert 'a moment ago' in client.post('/api/auth/resend-verification', json={'email': 'ada@example.org'}).json()['message']
    other = client.post('/api/auth/resend-verification', json={'email': 'someone-else@example.org'}).json()['message']
    assert other == 'If an account requiring verification exists for this address, a new verification email will be sent.', 'nothing about anyone else'

def test_retyping_your_own_unverified_address_sends_a_verification(mailbox):
    client = signed_in_legacy(); mailbox.clear()
    r = client.post('/api/auth/change-email', json={'email': 'ada@example.org', 'current_password': PASSWORD})
    assert r.status_code == 200 and 'not verified yet' in r.json()['message'] and r.json()['pending_email'] is None
    flush(); assert 'Verify Email Address' in body(mailbox[0]) and mailbox[0]['To'] == 'ada@example.org'
    verified = verified_client('done@example.org')
    assert 'already your email address' in verified.post('/api/auth/change-email', json={'email': 'done@example.org', 'current_password': PASSWORD}).json()['message']

def test_the_mail_capture_is_only_ever_named_in_development(monkeypatch, mailbox):
    monkeypatch.setenv('MAIL_CAPTURE_URL', 'http://127.0.0.1:8025')
    monkeypatch.setattr(config, 'APP_ENV', 'development')
    assert register('a@example.org').json()['mail_capture_url'] == 'http://127.0.0.1:8025'
    assert login('a@example.org').json()['detail']['mail_capture_url'] == 'http://127.0.0.1:8025'
    monkeypatch.setattr(config, 'APP_ENV', 'production')
    assert 'mail_capture_url' not in register('b@example.org').json()
    assert 'mail_capture_url' not in login('b@example.org').json()['detail']
    assert 'mail_capture_url' not in resend('b@example.org').json()

# Delivery --------------------------------------------------------------------------------------

def failing(reason='TimeoutError', permanent=False):
    def send(message): raise email_service.DeliveryError(reason, permanent)
    return send

def test_a_delivery_failure_keeps_the_account_and_retries_with_growing_delays(monkeypatch, mailbox):
    monkeypatch.setattr(email_service, 'deliver', failing())
    r = register()
    assert r.status_code == 201, 'registration does not depend on the mail server'
    assert flush() == 0
    job = jobs()[0]
    assert job.status == 'pending' and job.attempts == 1 and job.last_error == 'TimeoutError'
    wait = job.next_attempt_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(seconds=50) < wait <= timedelta(seconds=60)
    assert flush() == 0 and jobs()[0].attempts == 1, 'not retried before it is due'
    assert account('ada@example.org') is not None

def test_a_message_is_sent_when_the_server_comes_back_and_old_attempts_leave_no_valid_link(monkeypatch, mailbox):
    monkeypatch.setattr(email_service, 'deliver', failing())
    register(); flush()
    with base.SessionLocal() as db: stale = db.scalar(select(models.AccountToken)).token_hash; j = db.scalar(select(models.EmailJob)); j.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
    monkeypatch.setattr(email_service, 'deliver', lambda message: mailbox.append(message))
    assert flush() == 1
    with base.SessionLocal() as db: rows = list(db.scalars(select(models.AccountToken)))
    assert len(rows) == 1 and rows[0].token_hash != stale
    assert verify(token_in(mailbox[0])).status_code == 200

def test_retries_stop_after_the_last_attempt(monkeypatch, mailbox):
    monkeypatch.setattr(email_service, 'deliver', failing())
    register()
    for _ in range(len(email_service.RETRY_DELAYS) + 1):
        flush()
        with base.SessionLocal() as db: j = db.scalar(select(models.EmailJob)); j.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
    job = jobs()[0]
    assert job.status == 'failed' and job.attempts == len(email_service.RETRY_DELAYS) + 1
    assert flush() == 0 and jobs()[0].attempts == job.attempts

def test_a_refused_recipient_is_not_retried(monkeypatch):
    monkeypatch.setattr(email_service, 'deliver', failing('SMTPRecipientsRefused 550', True))
    register(); flush()
    assert jobs()[0].status == 'failed' and jobs()[0].attempts == 1

def test_a_message_that_no_longer_applies_is_dropped(mailbox):
    register(); edit('ada@example.org', email_verified=True); flush()
    assert not mailbox and jobs()[0].status == 'cancelled'

def test_a_sender_that_died_mid_send_does_not_lose_the_message(mailbox):
    register()
    with base.SessionLocal() as db:
        j = db.scalar(select(models.EmailJob)); j.status = 'sending'; j.claimed_until = datetime.now(timezone.utc) + timedelta(minutes=1); db.commit()
    assert flush() == 0
    with base.SessionLocal() as db:
        j = db.scalar(select(models.EmailJob)); j.claimed_until = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
    assert flush() == 1

def test_old_messages_are_not_delivered_after_a_long_outage(mailbox):
    register()
    with base.SessionLocal() as db:
        j = db.scalar(select(models.EmailJob)); j.created_at = datetime.now(timezone.utc) - timedelta(hours=email_service.MAX_AGE_HOURS + 1); db.commit()
    assert flush() == 0 and not mailbox and jobs()[0].status == 'failed'

def test_finished_messages_and_old_links_are_purged(mailbox):
    register(); flush()
    with base.SessionLocal() as db:
        j = db.scalar(select(models.EmailJob)); j.created_at = datetime.now(timezone.utc) - timedelta(days=31)
        t = db.scalar(select(models.AccountToken)); t.expires_at = datetime.now(timezone.utc) - timedelta(days=8); db.commit()
    email_service.purge(base.SessionLocal)
    assert not jobs()
    with base.SessionLocal() as db: assert db.scalar(select(models.AccountToken)) is None

def test_nothing_is_attempted_while_mail_is_misconfigured(monkeypatch, mailbox):
    monkeypatch.setattr(email_service, 'configuration_problems', lambda: ['SMTP_HOST is not set'])
    assert register().status_code == 201 and flush() == 0
    assert jobs()[0].status == 'pending' and jobs()[0].attempts == 0

def test_logs_hold_no_address_or_link(monkeypatch, caplog, mailbox):
    monkeypatch.setattr(email_service, 'deliver', failing('SMTPDataError 451'))
    with caplog.at_level('INFO'):
        register(); flush()
    assert 'attempt 1' in caplog.text and 'ada@example.org' not in caplog.text and 'token' not in caplog.text

# Email changes ---------------------------------------------------------------------------------

def change(client, email, password=PASSWORD): return client.post('/api/auth/change-email', json={'email': email, 'current_password': password})

def test_changing_email_keeps_the_verified_address_until_the_new_one_is_confirmed(mailbox):
    client = verified_client(); mailbox.clear()
    assert change(client, 'wrong@example.org', 'WrongPassword2026').status_code == 401
    r = change(client, 'New@Example.org')
    assert r.status_code == 200 and r.json()['pending_email'] == 'new@example.org'
    me = client.get('/api/auth/me').json()['user']
    assert me['email'] == 'ada@example.org' and me['email_verified'] and me['pending_email'] == 'new@example.org'
    flush(); confirm = mail_to('new@example.org')[0]
    assert 'stays active' in body(confirm)
    assert login().status_code == 200, 'the old address still signs in'
    assert login('new@example.org').status_code == 401, 'the new one does not yet'
    r = verify(token_in(confirm), client)
    assert r.status_code == 200 and r.json()['status'] == 'email_changed'
    me = client.get('/api/auth/me').json()['user']
    assert me['email'] == 'new@example.org' and me['email_verified'] and me['pending_email'] is None
    assert login('new@example.org').status_code == 200 and login().status_code == 401
    flush(); notice = mail_to('ada@example.org')[-1]
    assert 'was changed' in body(notice) and 'new@example.org' not in body(notice) and 'n***@example.org' in body(notice)

def test_a_taken_address_looks_the_same_and_cannot_be_confirmed(mailbox):
    verified_client('owner@example.org'); client = verified_client(); mailbox.clear()
    free, taken = change(client, 'free@example.org').json(), change(client, 'owner@example.org').json()
    assert free['message'] == taken['message'] and taken['pending_email'] == 'owner@example.org'
    flush()
    assert not any('token=' in body(m) for m in mail_to('owner@example.org')), 'no link exists for a taken address'
    assert client.get('/api/auth/me').json()['user']['email'] == 'ada@example.org'

def test_an_address_registered_meanwhile_stops_the_change(mailbox):
    client = verified_client(); mailbox.clear()
    change(client, 'wanted@example.org'); flush(); token = token_in(mail_to('wanted@example.org')[0])
    register('wanted@example.org'); flush()
    r = verify(token, client)
    assert r.status_code == 409 and r.json()['detail']['code'] == 'conflict'
    me = client.get('/api/auth/me').json()['user']
    assert me['email'] == 'ada@example.org' and me['pending_email'] is None

def test_asking_for_another_address_cancels_the_earlier_link(mailbox):
    client = verified_client(); mailbox.clear()
    change(client, 'first@example.org'); flush(); first = token_in(mail_to('first@example.org')[0])
    change(client, 'second@example.org'); flush()
    assert verify(first).json()['detail']['code'] == 'invalid'
    assert verify(token_in(mail_to('second@example.org')[0])).status_code == 200
    assert account('second@example.org') is not None

def test_cancelling_a_change_invalidates_its_link(mailbox):
    client = verified_client(); mailbox.clear()
    change(client, 'new@example.org'); flush(); token = token_in(mail_to('new@example.org')[0])
    assert client.delete('/api/auth/change-email').json()['pending_email'] is None
    assert verify(token).json()['detail']['code'] == 'invalid'
    assert client.get('/api/auth/me').json()['user']['email'] == 'ada@example.org'

def test_a_change_cancels_links_sent_to_the_old_address_and_other_sessions(mailbox):
    client = verified_client(); other = TestClient(app); login(client=other); mailbox.clear()
    TestClient(app).post('/api/auth/forgot-password', json={'email': 'ada@example.org'}); flush(); reset = token_in(mailbox[0])
    change(client, 'new@example.org'); flush()
    assert verify(token_in(mail_to('new@example.org')[0]), client).status_code == 200
    assert TestClient(app).post('/api/auth/reset-password', json={'token': reset, 'password': 'Another2026Pass'}).status_code == 400
    assert client.get('/api/auth/me').status_code == 200 and other.get('/api/auth/me').status_code == 401

def test_repeating_the_same_change_in_its_cooldown_keeps_the_link_already_sent(mailbox):
    client = verified_client(); mailbox.clear()
    change(client, 'new@example.org'); flush(); token = token_in(mail_to('new@example.org')[0])
    change(client, 'new@example.org'); assert flush() == 0
    assert verify(token).status_code == 200

def test_legacy_accounts_become_verified_by_confirming_a_new_address(mailbox):
    register(); edit('ada@example.org', legacy_email_access=True)
    client = TestClient(app); client.headers['X-CSRF-Token'] = login(client=client).json()['csrf_token']; mailbox.clear()
    change(client, 'new@example.org'); flush()
    assert verify(token_in(mail_to('new@example.org')[-1])).status_code == 200
    u = account('new@example.org')
    assert u.email_verified and u.email_verified_at is not None and not u.legacy_email_access

# Existing accounts -----------------------------------------------------------------------------

def test_existing_accounts_keep_working_through_the_migration(tmp_path):
    """The real migration on a database like the one deployed: nothing is locked out, nothing is claimed."""
    import os, subprocess, sys
    backend = Path(__file__).resolve().parents[1]; path = tmp_path / 'legacy.db'
    env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + str(path), 'UPLOAD_DIR': str(tmp_path / 'uploads')}
    run = lambda *args: subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=backend, env=env, check=True, capture_output=True, timeout=120)
    run('upgrade', '75a_username_display_name')
    con = sqlite3.connect(path); columns = 'email,password_hash,display_name,username,role,email_verified,active,created_at,updated_at'
    for email, verified in (('verified@example.org', 1), ('never@example.org', 0)):
        con.execute(f"INSERT INTO users ({columns}) VALUES (?,'h','n',?,'buyer',?,1,'2026-01-01 00:00:00','2026-01-01 00:00:00')", (email, email[:5], verified))
    con.commit(); con.close()
    run('upgrade', 'head')
    con = sqlite3.connect(path)
    rows = {r[0]: r[1:] for r in con.execute('SELECT email, email_verified, email_verified_at, legacy_email_access, pending_email FROM users')}
    assert rows['verified@example.org'] == (1, None, 0, None), 'already verified: the date is not invented'
    assert rows['never@example.org'] == (0, None, 1, None), 'may sign in, and is not claimed as verified'
    assert con.execute('SELECT count(*) FROM email_jobs').fetchone()[0] == 0, 'nobody is emailed by the migration'
    con.close()
    run('downgrade', '75a_username_display_name'); run('upgrade', 'head')

def test_a_verified_account_and_a_legacy_account_can_sign_in(mailbox):
    register('a@example.org'); edit('a@example.org', email_verified=True)
    register('b@example.org'); edit('b@example.org', legacy_email_access=True)
    assert login('a@example.org').status_code == 200 and login('b@example.org').status_code == 200
    register('c@example.org'); assert login('c@example.org').status_code == 403

def test_a_legacy_account_can_ask_for_a_link_and_become_verified(mailbox):
    register(); edit('ada@example.org', legacy_email_access=True); flush(); mailbox.clear(); age_jobs(5)
    resend(); flush(); assert verify(token_in(mailbox[0])).status_code == 200
    u = account('ada@example.org'); assert u.email_verified and not u.legacy_email_access

def test_password_reset_goes_through_the_queue_and_confirms_the_address(mailbox):
    register(); flush(); mailbox.clear()
    r = TestClient(app).post('/api/auth/forgot-password', json={'email': 'ada@example.org'})
    assert r.status_code == 200 and r.json() == TestClient(app).post('/api/auth/forgot-password', json={'email': 'nobody@example.org'}).json()
    assert not mailbox; flush(); assert 'Reset Password' in body(mailbox[0]) and 'expires in 60 minutes' in body(mailbox[0])
    assert TestClient(app).post('/api/auth/reset-password', json={'token': token_in(mailbox[0]), 'password': 'NewPassword2026'}).status_code == 200
    assert login(password='NewPassword2026').status_code == 200

# A real SMTP conversation ------------------------------------------------------------------------

class FakeSmtp(socketserver.StreamRequestHandler):
    """Just enough of SMTP to see what the client does. Offers no STARTTLS unless told to, and no AUTH."""
    def handle(self):
        self.write('220 fake')
        while True:
            line = self.rfile.readline().decode(errors='replace').strip()
            if not line: return
            self.server.lines.append(line); verb = line.split(' ')[0].upper()
            if verb == 'EHLO': self.write('250-fake\r\n250 SIZE 100000' if not self.server.starttls else '250-fake\r\n250 STARTTLS')
            elif verb == 'DATA':
                self.write('354 go')
                while self.rfile.readline().strip() != b'.': pass
                self.write(self.server.after_data)
            elif verb == 'RCPT': self.write(self.server.rcpt)
            elif verb == 'QUIT': self.write('221 bye'); return
            else: self.write('250 ok')
    def write(self, text): self.wfile.write((text + '\r\n').encode())

@pytest.fixture
def smtp_server():
    class Server(socketserver.ThreadingTCPServer): allow_reuse_address = True; daemon_threads = True
    server = Server(('127.0.0.1', 0), FakeSmtp); server.lines = []; server.starttls = False; server.rcpt = '250 ok'; server.after_data = '250 queued'
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown(); server.server_close()

def settings(server, **extra):
    values = dict(host='127.0.0.1', port=server.server_address[1], username='', password='', from_email='noreply@example.org', from_name='OpenLabs3D', reply_to='', starttls=False, use_ssl=False, timeout=3)
    return email_service.SmtpSettings(**{**values, **extra})
def sample(): return email_service.compose('ada@example.org', email_service.test_message(None, None, {}))

def test_smtp_sends_over_a_real_connection(smtp_server):
    email_service.send_smtp(sample(), settings(smtp_server))
    verbs = [line.split(' ')[0].upper() for line in smtp_server.lines]
    assert verbs[:4] == ['EHLO', 'MAIL', 'RCPT', 'DATA'] and any('ada@example.org' in line for line in smtp_server.lines)

def test_smtp_will_not_continue_when_encryption_is_not_offered(smtp_server):
    with pytest.raises(email_service.DeliveryError) as refused:
        email_service.send_smtp(sample(), settings(smtp_server, starttls=True, username='user', password='secret-password'))
    assert refused.value.reason == 'SMTPNotSupportedError' and not refused.value.permanent
    assert not any(line.split(' ')[0].upper() in ('AUTH', 'MAIL') for line in smtp_server.lines), 'no credentials, no message'

def test_smtp_errors_are_classified_without_their_text(smtp_server):
    smtp_server.rcpt = '550 no such user ada@example.org'
    with pytest.raises(email_service.DeliveryError) as refused: email_service.send_smtp(sample(), settings(smtp_server))
    assert refused.value.permanent and refused.value.reason == 'SMTPRecipientsRefused 550'
    smtp_server.rcpt = '451 greylisted'
    with pytest.raises(email_service.DeliveryError) as later: email_service.send_smtp(sample(), settings(smtp_server))
    assert not later.value.permanent
    smtp_server.rcpt = '250 ok'; smtp_server.after_data = '554 rejected as spam'
    with pytest.raises(email_service.DeliveryError) as data: email_service.send_smtp(sample(), settings(smtp_server))
    assert data.value.permanent and data.value.reason == 'SMTPDataError 554'

def test_an_unreachable_server_times_out_as_a_temporary_failure():
    with pytest.raises(email_service.DeliveryError) as down:
        email_service.send_smtp(sample(), email_service.SmtpSettings(host='127.0.0.1', port=9, username='', password='', from_email='a@example.org', from_name='x', reply_to='', starttls=False, use_ssl=False, timeout=1))
    assert not down.value.permanent

# Configuration ---------------------------------------------------------------------------------

@pytest.fixture
def real_configuration(monkeypatch):
    import importlib
    monkeypatch.undo()
    for name in ('SMTP_HOST', 'SMTP_FROM', 'SMTP_FROM_EMAIL', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_USE_STARTTLS', 'SMTP_STARTTLS', 'SMTP_USE_SSL', 'MAIL_ALLOW_REAL_DELIVERY'): monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MAIL_TRANSPORT', 'smtp')
    return monkeypatch

def test_production_needs_encryption_and_an_https_address(real_configuration):
    m = real_configuration
    m.setattr(config, 'APP_ENV', 'production'); m.setattr(config, 'APP_PUBLIC_URL', 'http://labs.example.net')
    m.setenv('SMTP_HOST', 'smtp.example.net'); m.setenv('SMTP_FROM_EMAIL', 'noreply@example.net'); m.setenv('SMTP_USE_STARTTLS', 'false')
    problems = ' '.join(email_service.configuration_problems())
    assert 'SMTP_USE_STARTTLS' in problems and 'https://' in problems
    m.setenv('SMTP_USE_STARTTLS', 'true'); m.setattr(config, 'APP_PUBLIC_URL', 'https://labs.example.net')
    assert email_service.configuration_problems() == []
    m.setenv('MAIL_TRANSPORT', 'file'); assert email_service.configuration_problems()

def test_development_cannot_reach_a_real_mail_server_by_accident(real_configuration):
    m = real_configuration
    m.setattr(config, 'APP_ENV', 'development'); m.setenv('SMTP_HOST', 'smtp.real-provider.example'); m.setenv('SMTP_FROM_EMAIL', 'a@example.org')
    assert 'local capture' in ' '.join(email_service.configuration_problems())
    m.setenv('SMTP_HOST', 'mailpit'); m.setenv('SMTP_USE_STARTTLS', 'false')
    assert email_service.configuration_problems() == []

def test_problems_never_include_secret_values(real_configuration):
    m = real_configuration
    m.setenv('SMTP_USERNAME', 'user-secret'); m.setenv('SMTP_HOST', 'host-secret.example'); m.setattr(config, 'APP_ENV', 'production')
    assert 'secret' not in ' '.join(email_service.configuration_problems())

def test_the_older_setting_names_still_work(real_configuration):
    m = real_configuration
    m.setenv('SMTP_FROM', 'Labs <old@example.org>'); m.setenv('SMTP_STARTTLS', 'false')
    s = email_service.smtp_settings()
    assert (s.from_email, s.from_name, s.starttls) == ('old@example.org', 'Labs', False)

def test_credentials_are_not_in_the_frontend_or_any_response(real_configuration):
    m = real_configuration
    m.setenv('SMTP_PASSWORD', 'secret-password'); m.setenv('SMTP_USERNAME', 'secret-user')
    r = TestClient(app).get('/api/settings')
    assert 'secret' not in r.text
