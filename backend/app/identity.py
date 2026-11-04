"""Sign-in through external providers (OpenID Connect, authorization code with PKCE). Every provider leads to the one
internal account: an identity is (provider, the provider's stable subject), never an email address. Matching addresses
never merge accounts; linking happens only from a signed-in session. To add a provider: add it to PROVIDERS."""
import logging, os, re, secrets, threading, time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import httpx
from authlib.integrations.httpx_client import OAuth2Client
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from joserfc import jwt
from joserfc.jwk import KeySet
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import config, email_service, models
from .database import get_db
from .main import UNUSABLE_PASSWORD, current, digest, fail, mutate, may_sign_in, new_session, password_matches, session_limit

router = APIRouter(prefix='/api')
log = logging.getLogger('openlabs3d.identity')
FLOW_COOKIE = 'ol3d_oauth'
FLOW_MINUTES = 10

@dataclass
class Provider:
    name: str; label: str; authorize_url: str; token_url: str; jwks_url: str; issuers: tuple; env: str

PROVIDERS = {'google': Provider('google', 'Google', 'https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token',
                                'https://www.googleapis.com/oauth2/v3/certs', ('https://accounts.google.com', 'accounts.google.com'), 'GOOGLE_OAUTH')}
SCOPES = 'openid email profile'    # Identity only: no access to Gmail, Drive or contacts.

def credentials(provider):
    return os.getenv(provider.env + '_CLIENT_ID', '').strip(), os.getenv(provider.env + '_CLIENT_SECRET', '').strip()
def redirect_uri(provider):
    return os.getenv(provider.env + '_REDIRECT_URI', '').strip() or f'{config.APP_PUBLIC_URL}/api/auth/{provider.name}/callback'
def enabled(provider): return all(credentials(provider))
def has_password(user): return bool(user.password_hash) and not user.password_hash.startswith('!')

# Talking to the provider ------------------------------------------------------------------------

def exchange_code(provider, code, verifier):
    client_id, secret = credentials(provider)
    with OAuth2Client(client_id, secret, redirect_uri=redirect_uri(provider), code_challenge_method='S256', timeout=10) as client:
        return client.fetch_token(provider.token_url, code=code, code_verifier=verifier, grant_type='authorization_code')

_keys, _keys_lock = {}, threading.Lock()
def fetch_jwks(provider, refresh=False):
    with _keys_lock:
        cached = _keys.get(provider.name)
        if cached and not refresh and time.monotonic() - cached[0] < 3600: return cached[1]
    response = httpx.get(provider.jwks_url, timeout=10); response.raise_for_status()
    keys = response.json()
    with _keys_lock: _keys[provider.name] = (time.monotonic(), keys)
    return keys

def verify_id_token(provider, id_token, nonce):
    """Signature (RS256 only), issuer, audience, expiry and nonce. Raises when any fails."""
    try: decoded = jwt.decode(id_token, KeySet.import_key_set(fetch_jwks(provider)), algorithms=['RS256'])
    except ValueError:    # the provider may have rotated its keys
        decoded = jwt.decode(id_token, KeySet.import_key_set(fetch_jwks(provider, refresh=True)), algorithms=['RS256'])
    jwt.JWTClaimsRegistry(iss={'essential': True, 'values': list(provider.issuers)}, aud={'essential': True, 'value': credentials(provider)[0]},
                          exp={'essential': True}, sub={'essential': True}, nonce={'essential': True, 'value': nonce}).validate(decoded.claims)
    return decoded.claims

# Starting -----------------------------------------------------------------------------------------

def begin_flow(db, provider, response, user_id=None):
    state, nonce, verifier, browser = (secrets.token_urlsafe(48) for _ in range(4))
    db.execute(delete(models.OAuthFlow).where(models.OAuthFlow.expires_at < datetime.now(timezone.utc)))
    db.add(models.OAuthFlow(state_hash=digest(state), provider=provider.name, nonce=nonce, code_verifier=verifier, browser_hash=digest(browser), user_id=user_id, expires_at=datetime.now(timezone.utc) + timedelta(minutes=FLOW_MINUTES)))
    db.commit()
    client = OAuth2Client(credentials(provider)[0], redirect_uri=redirect_uri(provider), scope=SCOPES, code_challenge_method='S256')
    url, _ = client.create_authorization_url(provider.authorize_url, state=state, nonce=nonce, code_verifier=verifier, prompt='select_account')
    # Ties the attempt to this browser: a link started elsewhere cannot sign this browser in (login CSRF).
    response.set_cookie(FLOW_COOKIE, browser, httponly=True, secure=config.SECURE_COOKIE, samesite='lax', max_age=FLOW_MINUTES * 60, path='/api/auth')
    return url

def provider_or_404(name):
    provider = PROVIDERS.get(name)
    if not provider or not enabled(provider): fail(404, 'This sign-in method is not available')
    return provider

@router.get('/auth/providers')
def providers(): return {name: enabled(p) for name, p in PROVIDERS.items()}

@router.get('/auth/{name}/start')
def start(name: str, request: Request, db: Session = Depends(get_db)):
    provider = provider_or_404(name)
    response = RedirectResponse('/', status_code=302)
    response.headers['location'] = begin_flow(db, provider, response)
    return response

# Returning ----------------------------------------------------------------------------------------

def finish(target, cookie=True):
    response = RedirectResponse('/#' + target, status_code=303)
    if cookie: response.delete_cookie(FLOW_COOKIE, path='/api/auth')
    return response
def refuse(code, cookie=True): return finish(f'account?auth_error={code}', cookie)

def unique_username(db, claims):
    base = re.sub(r'[^A-Za-z0-9_]+', '_', (claims.get('email') or '').partition('@')[0]).strip('_')[:24] or 'user'
    base = base if len(base) >= 3 else f'user_{base}'
    candidate = base
    while db.scalar(select(models.User.id).where(models.User.username == candidate)) is not None: candidate = f'{base}_{secrets.token_hex(3)}'
    return candidate

def landing(user): return 'admin' if user.role == 'admin' else 'host' if user.role == 'host' else 'catalogue'

def notify_change(db, user, what):
    email_service.enqueue(db, 'sign_in_method_changed', user.email, user.id, {'what': what})

def link_identity(db, provider, claims, auth, flow_user):
    if not auth or auth[0].id != flow_user: return refuse('link_session')
    user = auth[0]
    owner = db.scalar(select(models.UserIdentity).where(models.UserIdentity.provider == provider.name, models.UserIdentity.subject == claims['sub']))
    if owner: return refuse('identity_in_use' if owner.user_id != user.id else 'already_connected')
    if db.scalar(select(models.UserIdentity.id).where(models.UserIdentity.user_id == user.id, models.UserIdentity.provider == provider.name)): return refuse('already_connected')
    db.add(models.UserIdentity(user_id=user.id, provider=provider.name, subject=claims['sub'], email=(claims.get('email') or '').lower()))
    # The provider vouches for this very address, so it counts as confirmed. Any other address is left as it is.
    if claims.get('email_verified') is True and (claims.get('email') or '').lower() == user.email and not user.email_verified:
        user.email_verified, user.email_verified_at, user.legacy_email_access = True, datetime.now(timezone.utc), False
    db.add(models.Activity(actor_id=user.id, action='identity.connected', subject=f'user:{user.id}', detail=provider.name))
    notify_change(db, user, f'{provider.label} sign-in was connected')
    try: db.commit()
    except IntegrityError: db.rollback(); return refuse('identity_in_use')
    email_service.wake()
    return finish(f'account?auth_notice={provider.name}_connected')

@router.get('/auth/{name}/callback')
def callback(name: str, request: Request, state: str = '', code: str = '', error: str = '', auth=Depends(current), db: Session = Depends(get_db)):
    provider = PROVIDERS.get(name)
    if not provider or not enabled(provider) or not state: return refuse('sign_in_failed')
    # Single use: whatever happens next, this attempt cannot be replayed.
    flow = db.scalar(select(models.OAuthFlow).where(models.OAuthFlow.state_hash == digest(state), models.OAuthFlow.provider == name, models.OAuthFlow.expires_at > datetime.now(timezone.utc)))
    browser = request.cookies.get(FLOW_COOKIE, '')
    if flow is None or not browser or not secrets.compare_digest(flow.browser_hash, digest(browser)):
        # Leaves the cookie: a forged link must not be able to break a genuine attempt in progress.
        db.rollback(); return refuse('sign_in_failed', cookie=False)
    nonce, verifier, flow_user = flow.nonce, flow.code_verifier, flow.user_id
    db.delete(flow); db.commit()
    if error or not code: return refuse('sign_in_cancelled')
    try:
        claims = verify_id_token(provider, exchange_code(provider, code, verifier)['id_token'], nonce)
    except Exception as e:
        log.warning('%s sign-in refused: %s', name, type(e).__name__)
        return refuse('sign_in_failed')
    if flow_user is not None: return link_identity(db, provider, claims, auth, flow_user)
    identity = db.scalar(select(models.UserIdentity).where(models.UserIdentity.provider == name, models.UserIdentity.subject == claims['sub']))
    if identity:
        user = db.get(models.User, identity.user_id)
        if not user.active or not may_sign_in(user): return refuse('account_unavailable')
        identity.email, identity.last_login_at = (claims.get('email') or identity.email).lower(), datetime.now(timezone.utc)
    else:
        email = (claims.get('email') or '').lower()
        if not email or claims.get('email_verified') is not True: return refuse('email_not_verified')
        # A matching address proves nothing about who owns the account here: never merged or signed in.
        if db.scalar(select(models.User.id).where(models.User.email == email)) is not None: return refuse('email_exists')
        username = unique_username(db, claims)
        user = models.User(email=email, username=username, display_name=username, password_hash=UNUSABLE_PASSWORD, role='buyer', email_verified=True, email_verified_at=datetime.now(timezone.utc),
                           first_name=(claims.get('given_name') or '')[:100], last_name=(claims.get('family_name') or '')[:100])
        db.add(user)
        try:
            db.flush()
            db.add(models.UserIdentity(user_id=user.id, provider=name, subject=claims['sub'], email=email, last_login_at=datetime.now(timezone.utc)))
            db.add(models.Activity(actor_id=user.id, action='user.registered', subject=f'user:{user.id}', detail=name))
            db.flush()
        except IntegrityError:    # two tabs at once: the other one created it
            db.rollback(); return refuse('try_again')
    response = finish(landing(user))
    new_session(user, response, db, request)
    return response

# Managing, from Account settings ------------------------------------------------------------------

class PasswordConfirm(BaseModel):
    password: str = Field(max_length=128)

def confirm_password(user, password):
    if not password_matches(user.password_hash, password): fail(401, 'Incorrect password')

@router.get('/auth/sign-in-methods')
def sign_in_methods(auth=Depends(current), db: Session = Depends(get_db)):
    if not auth: fail(401, 'Please sign in')
    user = auth[0]
    identities = {i.provider: i for i in db.scalars(select(models.UserIdentity).where(models.UserIdentity.user_id == user.id))}
    return {'email': user.email, 'email_verified': user.email_verified, 'password': has_password(user),
            'sessions': db.scalar(select(func.count()).select_from(models.LoginSession).where(models.LoginSession.user_id == user.id, models.LoginSession.expires_at > datetime.now(timezone.utc))),
            'providers': [{'name': p.name, 'label': p.label, 'available': enabled(p), 'connected': p.name in identities, 'email': identities[p.name].email if p.name in identities else ''} for p in PROVIDERS.values()]}

@router.post('/auth/{name}/connect')
def connect(name: str, body: PasswordConfirm, request: Request, response: Response, auth=Depends(mutate), db: Session = Depends(get_db)):
    """Recent authentication: the password again. The account is the one signed in, never one found by address."""
    session_limit(request, 'connect-identity', auth[0].id)
    provider = provider_or_404(name)
    confirm_password(auth[0], body.password)
    return {'url': begin_flow(db, provider, response, auth[0].id)}

@router.post('/auth/{name}/disconnect')
def disconnect(name: str, body: PasswordConfirm, request: Request, auth=Depends(mutate), db: Session = Depends(get_db)):
    session_limit(request, 'disconnect-identity', auth[0].id)
    provider = PROVIDERS.get(name)
    if not provider: fail(404, 'This sign-in method is not available')
    identity = db.scalar(select(models.UserIdentity).where(models.UserIdentity.user_id == auth[0].id, models.UserIdentity.provider == name))
    if not identity: fail(404, 'This sign-in method is not connected')
    others = db.scalar(select(func.count()).select_from(models.UserIdentity).where(models.UserIdentity.user_id == auth[0].id, models.UserIdentity.id != identity.id))
    if not has_password(auth[0]) and not others: fail(409, 'Set a password first: this is your only way to sign in.')
    if has_password(auth[0]): confirm_password(auth[0], body.password)
    else: fail(409, 'Confirm with a password: set one first.')
    db.delete(identity)
    db.add(models.Activity(actor_id=auth[0].id, action='identity.disconnected', subject=f'user:{auth[0].id}', detail=name))
    notify_change(db, auth[0], f'{provider.label} sign-in was disconnected')
    db.commit(); email_service.wake()
    return {'message': f'{provider.label} is disconnected.'}

@router.post('/auth/password-link')
def password_link(request: Request, auth=Depends(mutate), db: Session = Depends(get_db)):
    """Setting a first password goes through the verified inbox, the same proof as a password reset."""
    session_limit(request, 'password-link', auth[0].id)
    queued = email_service.enqueue_limited(db, 'password_reset', auth[0].email, auth[0].id); db.commit(); email_service.wake()
    return {'message': f'A link to choose a password is on its way to {auth[0].email}.' if queued else 'We sent you one a moment ago. Check your inbox, or try again in a minute.', **email_service.capture_info()}

@router.post('/auth/sessions/sign-out-others')
def sign_out_others(auth=Depends(mutate), db: Session = Depends(get_db)):
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id == auth[0].id, models.LoginSession.token_hash != auth[1].token_hash)); db.commit()
    return {'message': 'Your other sessions have been signed out.'}
