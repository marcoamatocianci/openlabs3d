"""Email verification fixture plus a local fake Google, so the whole sign-in can be tested without real credentials.
Tokens are really signed, and the fake checks PKCE. Serves http://127.0.0.1:18104.
POST /fake-google/next {"sub","email","email_verified"} chooses who "signs in" next."""
import base64, hashlib, os, runpy, secrets, time
from pathlib import Path
os.environ['EMAIL_QA_PORT'] = '18104'
os.environ.update(GOOGLE_OAUTH_CLIENT_ID='fake-client', GOOGLE_OAUTH_CLIENT_SECRET='fake-secret')
root = Path(__file__).resolve().parents[1]
namespace = runpy.run_path(str(root / 'scripts/email_preview.py'))
app = namespace['namespace']['app']
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from app import identity
BASE = 'http://127.0.0.1:18104'; KEY = RSAKey.generate_key(2048, {'kid': 'fake'}); codes = {}; who = {}
google = identity.PROVIDERS['google']; google.authorize_url, google.token_url, google.jwks_url = BASE + '/fake-google/authorize', BASE + '/fake-google/token', BASE + '/fake-google/certs'
@app.post('/fake-google/next')
async def next_identity(request: Request): who.clear(); who.update(await request.json()); return {'ok': True}
@app.get('/fake-google/authorize')
def authorize(request: Request):
    q = request.query_params; code = secrets.token_urlsafe(16); codes[code] = (q['nonce'], q['code_challenge'], dict(who))
    return RedirectResponse(f"{q['redirect_uri']}?code={code}&state={q['state']}", status_code=302)
@app.post('/fake-google/token')
async def exchange(request: Request):
    form = await request.form(); nonce, challenge, person = codes.pop(form['code'])
    if base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest()).rstrip(b'=').decode() != challenge: return JSONResponse({'error': 'invalid_grant'}, 400)
    now = int(time.time())
    return {'access_token': 'x', 'token_type': 'Bearer', 'id_token': jwt.encode({'alg': 'RS256', 'kid': 'fake'}, {'iss': 'https://accounts.google.com', 'aud': 'fake-client', 'iat': now, 'exp': now + 600, 'nonce': nonce, **person}, KEY)}
@app.get('/fake-google/certs')
def certs(): return KeySet([KEY]).as_dict(private=False)
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=18104)
