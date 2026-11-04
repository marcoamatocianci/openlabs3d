"""Sign-in with Google, with the provider mocked but real signed tokens: every check on them really runs."""
import re, secrets, time
from urllib.parse import parse_qs, urlparse
import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from sqlalchemy import select
import test_marketplace_integrity as base
from test_marketplace_integrity import isolated_database, listing, place_order, printer, user  # noqa: F401
from test_marketplace import app
from app import email_service, identity, main, models

CLIENT = 'test-client.apps.googleusercontent.com'; PASSWORD = 'Openlabs2026'; KEY = RSAKey.generate_key(2048, {'kid': 'k1'})
GOOGLE = identity.PROVIDERS['google']

def token(nonce, key=KEY, **over):
    now = int(time.time())
    claims = {'iss': 'https://accounts.google.com', 'aud': CLIENT, 'sub': 'g-1', 'email': 'ada@gmail.com', 'email_verified': True, 'given_name': 'Ada', 'family_name': 'Bench', 'iat': now, 'exp': now + 600, 'nonce': nonce, **over}
    return jwt.encode({'alg': 'RS256', 'kid': 'k1'}, {k: v for k, v in claims.items() if v is not None}, key)

@pytest.fixture(autouse=True)
def google(monkeypatch):
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', CLIENT); monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_SECRET', 'test-secret')
    monkeypatch.setattr(email_service, 'configuration_problems', lambda: [])
    state = {'over': {}, 'key': KEY, 'codes': [], 'sent': []}
    monkeypatch.setattr(email_service, 'deliver', lambda m: state['sent'].append(m))
    def exchange(provider, code, verifier):
        state['codes'].append((code, verifier))
        return {'id_token': token(state['nonce'], state['key'], **state['over'])}
    monkeypatch.setattr(identity, 'exchange_code', exchange)
    monkeypatch.setattr(identity, 'fetch_jwks', lambda provider, refresh=False: KeySet([KEY]).as_dict(private=False))
    main.rate.clear()
    return state

def begin(client, google):
    r = client.get('/api/auth/google/start', follow_redirects=False)
    assert r.status_code == 302
    q = {k: v[0] for k, v in parse_qs(urlparse(r.headers['location']).query).items()}
    google['nonce'] = q['nonce']
    return q
def back(client, q, **extra):
    return client.get('/api/auth/google/callback', params={'state': q['state'], 'code': 'c', **extra}, follow_redirects=False)
def google_login(client, google):
    return back(client, begin(client, google))
def where(r): return r.headers['location']
def signed_up(email='ada@example.org', **values):
    with base.SessionLocal() as db:
        u = models.User(email=email, username='u' + secrets.token_hex(4), display_name='x', password_hash=main.hasher.hash(PASSWORD), role=values.pop('role', 'buyer'), email_verified=values.pop('email_verified', True), **values); db.add(u); db.commit(); return u.id
def session(email='ada@example.org'):
    c = TestClient(app); r = c.post('/api/auth/login', json={'email': email, 'password': PASSWORD}); assert r.status_code == 200, r.text
    c.headers['X-CSRF-Token'] = r.json()['csrf_token']; return c
def link(client, google):
    r = client.post('/api/auth/google/connect', json={'password': PASSWORD}); assert r.status_code == 200, r.text
    q = {k: v[0] for k, v in parse_qs(urlparse(r.json()['url']).query).items()}; google['nonce'] = q['nonce']
    return back(client, q)
def users():
    with base.SessionLocal() as db: return list(db.scalars(select(models.User)))
def identities():
    with base.SessionLocal() as db: return list(db.scalars(select(models.UserIdentity)))

def test_the_request_to_google_is_minimal_and_protected(google):
    q = begin(TestClient(app), google)
    assert q['scope'] == 'openid email profile' and q['response_type'] == 'code' and q['code_challenge_method'] == 'S256' and q['code_challenge']
    assert q['state'] and q['nonce'] and q['client_id'] == CLIENT and q['redirect_uri'].endswith('/api/auth/google/callback')
    with base.SessionLocal() as db:
        flow = db.scalar(select(models.OAuthFlow))
        assert flow.state_hash != q['state'], 'the state is stored hashed'

def test_the_redirect_uri_comes_from_configuration_not_the_request(google, monkeypatch):
    monkeypatch.setenv('GOOGLE_OAUTH_REDIRECT_URI', 'https://labs.example.net/api/auth/google/callback')
    r = TestClient(app).get('/api/auth/google/start', headers={'host': 'evil.example.com'}, follow_redirects=False)
    assert parse_qs(urlparse(r.headers['location']).query)['redirect_uri'] == ['https://labs.example.net/api/auth/google/callback']

def test_not_configured_means_not_offered(monkeypatch):
    monkeypatch.delenv('GOOGLE_OAUTH_CLIENT_SECRET')
    c = TestClient(app)
    assert c.get('/api/auth/providers').json() == {'google': False} and c.get('/api/auth/google/start', follow_redirects=False).status_code == 404

def test_first_google_sign_in_creates_a_verified_buyer_with_a_session(google):
    c = TestClient(app); r = google_login(c, google)
    assert r.status_code == 303 and where(r) == '/#catalogue'
    me = c.get('/api/auth/me').json()['user']
    assert me['email'] == 'ada@gmail.com' and me['role'] == 'buyer' and me['email_verified'] and me['first_name'] == 'Ada' and me['username'] == 'ada'
    assert [i.subject for i in identities()] == ['g-1'] and not google['sent'], 'no redundant verification email'
    cookie = r.headers.get_list('set-cookie'); assert any('ol3d_session' in x and 'HttpOnly' in x and 'SameSite=lax' in x for x in cookie)

def test_a_taken_username_gets_a_unique_one(google):
    with base.SessionLocal() as db: db.add(models.User(email='z@example.org', username='ada', display_name='ada', password_hash='x', role='buyer', email_verified=True)); db.commit()
    c = TestClient(app); google_login(c, google)
    assert re.fullmatch(r'ada_[0-9a-f]{6}', c.get('/api/auth/me').json()['user']['username'])

def test_returning_finds_the_same_account_by_subject_even_if_the_address_changed(google):
    c = TestClient(app); google_login(c, google); first = c.get('/api/auth/me').json()['user']['id']
    google['over'] = {'email': 'renamed@gmail.com'}
    d = TestClient(app); google_login(d, google); me = d.get('/api/auth/me').json()['user']
    assert me['id'] == first and me['email'] == 'ada@gmail.com' and len(users()) == 1

def test_a_matching_address_never_merges_or_signs_in(google):
    uid = signed_up('ada@gmail.com'); c = TestClient(app); r = google_login(c, google)
    assert where(r) == '/#account?auth_error=email_exists' and c.get('/api/auth/me').status_code == 401
    assert not identities() and len(users()) == 1
    assert session('ada@gmail.com').get('/api/auth/me').json()['user']['id'] == uid, 'the password still works'

def test_an_unconfirmed_sign_up_with_that_address_is_not_taken_over_either(google):
    signed_up('ada@gmail.com', email_verified=False); c = TestClient(app)
    assert where(google_login(c, google)) == '/#account?auth_error=email_exists' and not identities()

def test_an_address_google_has_not_verified_creates_nothing(google):
    google['over'] = {'email_verified': False}
    r = google_login(TestClient(app), google)
    assert where(r) == '/#account?auth_error=email_not_verified' and not users()

@pytest.mark.parametrize('over', [{'iss': 'https://evil.example.com'}, {'aud': 'another-client'}, {'exp': 1000}, {'nonce': 'replayed'}, {'sub': None}, {'iss': None}])
def test_bad_identity_tokens_are_refused(google, over):
    google['over'] = over; c = TestClient(app); r = google_login(c, google)
    assert where(r) == '/#account?auth_error=sign_in_failed' and not users() and c.get('/api/auth/me').status_code == 401

def test_a_token_signed_by_another_key_is_refused(google):
    google['key'] = RSAKey.generate_key(2048, {'kid': 'k1'}); r = google_login(TestClient(app), google)
    assert where(r) == '/#account?auth_error=sign_in_failed' and not users()

def test_a_failed_exchange_is_refused(google, monkeypatch):
    def boom(*a): raise RuntimeError('invalid_grant')
    monkeypatch.setattr(identity, 'exchange_code', boom)
    assert where(google_login(TestClient(app), google)) == '/#account?auth_error=sign_in_failed'

def test_wrong_state_replay_and_another_browser_are_refused(google):
    c = TestClient(app); q = begin(c, google)
    assert where(c.get('/api/auth/google/callback', params={'state': 'forged', 'code': 'c'}, follow_redirects=False)).endswith('sign_in_failed')
    other = TestClient(app)
    assert where(back(other, q)).endswith('sign_in_failed') and not google['codes'], 'login CSRF: another browser cannot finish it'
    assert where(back(c, q)) == '/#catalogue'
    c.cookies.set(identity.FLOW_COOKIE, 'x', path='/api/auth')
    assert where(back(c, q)).endswith('sign_in_failed') and len(google['codes']) == 1, 'used once'

def test_an_expired_attempt_is_refused(google):
    from datetime import datetime, timedelta, timezone
    c = TestClient(app); q = begin(c, google)
    with base.SessionLocal() as db: db.scalar(select(models.OAuthFlow)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
    assert where(back(c, q)).endswith('sign_in_failed')

def test_cancelling_at_google_creates_nothing(google):
    c = TestClient(app); q = begin(c, google)
    r = c.get('/api/auth/google/callback', params={'state': q['state'], 'error': 'access_denied'}, follow_redirects=False)
    assert where(r).endswith('sign_in_cancelled') and not users()

def test_sign_in_rotates_the_session(google):
    signed_up(); c = session(); old = c.cookies['ol3d_session']
    r = c.post('/api/auth/login', json={'email': 'ada@example.org', 'password': PASSWORD}); new = c.cookies['ol3d_session']
    assert new != old
    stale = TestClient(app); stale.cookies.set('ol3d_session', old)
    assert stale.get('/api/auth/me').status_code == 401

def test_explicit_linking_then_either_method_reaches_one_account(google):
    uid = signed_up(); c = session()
    assert c.post('/api/auth/google/connect', json={'password': 'WrongPassword1'}).status_code == 401, 'needs the password again'
    r = link(c, google); assert where(r) == '/#account?auth_notice=google_connected'
    assert c.get('/api/auth/sign-in-methods').json()['providers'][0] == {'name': 'google', 'label': 'Google', 'available': True, 'connected': True, 'email': 'ada@gmail.com'}
    g = TestClient(app); google_login(g, google)
    me = g.get('/api/auth/me').json()['user']; assert me['id'] == uid and me['email'] == 'ada@example.org', 'the account address does not change'
    email_service.process_due(base.SessionLocal); assert any('connected' in m.get_body(('plain',)).get_content() for m in google['sent'])

def test_linking_requires_the_same_session_that_started_it(google):
    signed_up(); signed_up('b@example.org'); a = session(); r = a.post('/api/auth/google/connect', json={'password': PASSWORD})
    q = {k: v[0] for k, v in parse_qs(urlparse(r.json()['url']).query).items()}; google['nonce'] = q['nonce']
    a.post('/api/auth/logout'); b = session('b@example.org'); b.cookies.set(identity.FLOW_COOKIE, a.cookies.get(identity.FLOW_COOKIE) or '', path='/api/auth')
    assert not identities() and where(back(b, q)).endswith(('link_session', 'sign_in_failed')) and not identities()

def test_one_google_account_cannot_link_to_two_accounts(google):
    signed_up(); signed_up('b@example.org'); link(session(), google)
    assert where(link(session('b@example.org'), google)).endswith('identity_in_use') and len(identities()) == 1

def test_disconnecting_needs_the_password_and_another_way_in(google):
    signed_up(); c = session(); link(c, google)
    assert c.post('/api/auth/google/disconnect', json={'password': 'WrongPassword1'}).status_code == 401
    assert c.post('/api/auth/google/disconnect', json={'password': PASSWORD}).status_code == 200 and not identities()
    g = TestClient(app); google['over'] = {'sub': 'g-2', 'email': 'two@gmail.com'}; google_login(g, google)
    g.headers['X-CSRF-Token'] = g.get('/api/auth/me').json()['csrf_token']
    assert g.post('/api/auth/google/disconnect', json={'password': ''}).status_code == 409 and len([i for i in identities() if i.subject == 'g-2']) == 1

def google_only(google):
    g = TestClient(app); google_login(g, google); g.headers['X-CSRF-Token'] = g.get('/api/auth/me').json()['csrf_token']; return g

def test_google_only_users_have_no_password_and_are_told(google):
    g = google_only(google)
    assert g.get('/api/auth/sign-in-methods').json()['password'] is False
    assert TestClient(app).post('/api/auth/login', json={'email': 'ada@gmail.com', 'password': PASSWORD}).status_code == 401
    assert g.post('/api/auth/change-email', json={'email': 'n@example.org', 'current_password': 'x'}).status_code == 409
    assert g.request('DELETE', '/api/profile', json={'password': 'x'}).status_code == 409
    TestClient(app).post('/api/auth/forgot-password', json={'email': 'ada@gmail.com'}); email_service.process_due(base.SessionLocal)
    text = google['sent'][-1].get_body(('plain',)).get_content(); assert 'Google manages that password' in text

def test_a_google_user_can_add_a_password_and_then_use_both_then_disconnect(google):
    g = google_only(google); assert g.post('/api/auth/password-link').status_code == 200
    email_service.process_due(base.SessionLocal); t = re.search(r'token=([\w-]+)', google['sent'][-1].get_body(('plain',)).get_content())[1]
    assert TestClient(app).post('/api/auth/reset-password', json={'token': t, 'password': 'ChosenPass2026'}).status_code == 200
    email_service.process_due(base.SessionLocal); assert 'was changed' in google['sent'][-1].get_body(('plain',)).get_content()
    p = TestClient(app); r = p.post('/api/auth/login', json={'email': 'ada@gmail.com', 'password': 'ChosenPass2026'}); assert r.status_code == 200
    p.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert p.post('/api/auth/google/disconnect', json={'password': 'ChosenPass2026'}).status_code == 200

def test_changing_a_password_notifies(google):
    signed_up(); c = session(); assert c.post('/api/auth/change-password', json={'current_password': PASSWORD, 'password': 'NewPassword2026'}).status_code == 200
    email_service.process_due(base.SessionLocal); assert google['sent'][-1]['Subject'] == 'Your OpenLabs3D password was changed'

@pytest.mark.parametrize('role', ['host', 'admin'])
def test_roles_never_change_through_google(google, role):
    uid = signed_up(role=role); c = session(); assert where(link(c, google)) == '/#account?auth_notice=google_connected'
    g = TestClient(app); r = google_login(g, google); assert where(r) == f'/#{role}'
    with base.SessionLocal() as db: assert db.get(models.User, uid).role == role

def test_a_new_google_user_gets_no_privileges(google):
    g = google_only(google)
    assert g.get('/api/admin/users').status_code == 403 and g.get('/api/host/jobs').status_code in (403, 404)

def test_orders_stay_with_the_account_and_jobs_with_their_host(google):
    with base.SessionLocal() as db:
        admin, host, buyer = user(db, 'admin'), user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000'}}); p = listing(db, admin); db.commit(); ids = host.id, buyer.id, p.id
    order = place_order(ids[1], ids[2]); b = base.login(ids[1]); csrf = b.get('/api/auth/me').json()['csrf_token']; b.headers['X-CSRF-Token'] = csrf
    with base.SessionLocal() as db: db.get(models.User, ids[1]).password_hash = main.hasher.hash(PASSWORD); db.commit()
    assert link(b, google).status_code == 303
    g = TestClient(app); google_login(g, google)
    assert g.get('/api/auth/me').json()['user']['id'] == ids[1] and [o['id'] for o in g.get('/api/orders').json()] == [order['id']]
    assert g.get('/api/admin/orders').status_code == 403

def test_signing_out_others_keeps_this_session(google):
    signed_up(); a, b = session(), session()
    assert a.post('/api/auth/sessions/sign-out-others').status_code == 200 and a.get('/api/auth/me').status_code == 200 and b.get('/api/auth/me').status_code == 401

def test_a_shared_address_does_not_lock_out_colleagues(google):
    for n in range(20): assert TestClient(app).post('/api/auth/register', json={'email': f'c{n}@example.org', 'username': f'colleague_{n}', 'password': PASSWORD}).status_code == 201
    signed_up(); bad = TestClient(app)
    for n in range(20): assert bad.post('/api/auth/login', json={'email': f'nobody{n}@example.org', 'password': 'x'}).status_code == 401
    assert session().get('/api/auth/me').status_code == 200, 'one colleague typing wrong addresses locks nobody else out'
    for _ in range(5): TestClient(app).post('/api/auth/login', json={'email': 'ada@example.org', 'password': 'wrong'})
    assert TestClient(app).post('/api/auth/login', json={'email': 'ada@example.org', 'password': PASSWORD}).status_code == 429, 'one account is still protected'

def test_deleting_an_account_removes_its_identity(google):
    signed_up(); c = session(); link(c, google)
    assert c.request('DELETE', '/api/profile', json={'password': PASSWORD}).status_code == 200 and not identities()
