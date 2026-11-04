# Authentication and account management

One internal account, reached by email and password, by Google, or by both. Google handles Google authentication, OpenLabs3D handles its own users and permissions, and Brevo delivers email (`docs/email/EMAIL_VERIFICATION.md`).

## What you need to set up

No credential or external account has been created. Until the Google settings exist, the Google button stays hidden and everything else works.

**Google**

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project.
2. Under **Google Auth Platform**, configure the consent screen: app name, support email, and the scopes `openid`, `email` and `profile` only. While it is in Testing, add your own address as a test user.
3. Create an **OAuth client ID** of type **Web application**.
4. Add the **authorized redirect URI**, exactly:
   - development: `http://localhost:8080/api/auth/google/callback`
   - production: `https://yourdomain.com/api/auth/google/callback`
5. Put the values in `.env`, which git ignores, and run `docker compose up -d --build backend`:
   ```env
   GOOGLE_OAUTH_CLIENT_ID=
   GOOGLE_OAUTH_CLIENT_SECRET=
   GOOGLE_OAUTH_REDIRECT_URI=
   ```
   The redirect URI may stay empty: it defaults to `APP_PUBLIC_URL/api/auth/google/callback`.

**Brevo:** create the account, authenticate your domain (SPF, DKIM, DMARC), generate an SMTP key. The prepared `.env` lists the settings.

## How it works

| Piece | Where |
|---|---|
| Identities: `user_identities` (provider + Google `sub`, never the address) | `backend/app/models.py`, migration `77a_external_identities` |
| Attempts in progress: `oauth_flows` (hashed state, nonce, PKCE verifier) | same |
| Flow, linking, sign-in methods | `backend/app/identity.py` |
| Pages | `assets/accounts.js` |

**Adding a provider** such as Microsoft: add it to `PROVIDERS` with its endpoints, then add a button. Accounts, linking and sessions stay the same.

### Which account does a Google sign-in reach?

| Situation | Result |
|---|---|
| This Google `sub` is linked | That account, with its role unchanged |
| New `sub`, new address that Google has verified | A new Buyer, already verified, with a generated username and no password |
| New `sub`, address Google has not verified | Refused, nothing created |
| New `sub`, address already registered (even unconfirmed) | **Refused, nothing joined.** The user signs in the usual way, or resets the password, then connects Google in Account settings |

### Security

- **Flow:** authorization code with PKCE (S256), `state` single-use, stored hashed, tied to the browser by an HttpOnly cookie (prevents login CSRF), expiring in 10 minutes.
- **ID token:** RS256 signature against Google's keys, issuer, audience, expiry, `sub` and nonce are all checked.
- **Scopes:** `openid email profile` only.
- **Redirect URI:** from configuration, never from request headers. Behind Caddy it works through the normal `/api` route.
- **Linking and disconnecting** need the signed-in session and the password again. A Google identity links to one account only. The address on file is told by email.
- **The only way in** cannot be removed: Google-only users must set a password first.
- **Sessions:** server-side, HttpOnly, SameSite=Lax, Secure in production, 14 days, deleted on sign-out, new token on every sign-in.
- **Roles** are never touched by any sign-in method.
- **Passwords:** Argon2id. Google-only accounts hold an unusable marker, so no password matches them.

### Password recovery

Forgot password sends a single-use link stored as a hash (60 minutes, `PASSWORD_RESET_EXPIRY_MINUTES`), with the same answer for any address. A reset signs out all sessions and sends a notice. Google-only users receive an explanation that Google manages their password, with an option to add an OpenLabs3D one.

### Rate limits

Limits on an IP are generous, because a lab or campus shares one, and tight limits sit on the target instead.

| Limit | Value |
|---|---|
| Failed sign-ins per account | 5 per 15 minutes |
| Failed sign-ins per IP | 50 per 15 minutes |
| Register, resend, forgot, reset, per IP | 30 per 15 minutes |
| Verify links per IP | 60 per 15 minutes |
| Email per address | 1 per minute, 5 per hour |
| Password checks while signed in, per account | 10 per 15 minutes |

## Limitations

- **Real Google has not been tested.** Tests use mocked responses and a local fake Google, with really signed tokens. Try a real sign-in once credentials exist.
- **After a Google sign-in** the user lands on their workspace, not on the page they came from (such as a checkout in progress).
- **Google-only users** must set a password before changing their email or deleting their account.
- **"Recent authentication"** means entering the password again, not a session-age check. Setting a first password goes through the verified inbox instead.
- **Session management** is a count and "sign out others", not a device list.
