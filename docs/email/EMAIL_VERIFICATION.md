# Email verification and transactional email

A new account opens only after its owner clicks a link sent to its address:

**Register → Receive email → Click the link → Account active → Sign in**

No DNS record, provider account or production setting has been changed. This document lists what you need to do before going live.

## Before going live

1. Choose a provider and verify your sending domain ([Provider setup](#provider-setup)).
2. Add the SPF, DKIM and DMARC records it gives you ([DNS records](#dns-records)).
3. Set the [environment variables](#environment-variables) in the server's `.env`, which git ignores. Never commit it.
4. Deploy: `docker compose -f compose.yaml -f compose.production.yaml up -d --build`. It refuses to start without `APP_PUBLIC_URL`, `SMTP_HOST` and `SMTP_FROM_EMAIL`.
5. Check for configuration problems in the log, then send a test:
   ```bash
   docker compose -f compose.yaml -f compose.production.yaml logs backend | grep -i "email is not configured"
   docker compose -f compose.yaml -f compose.production.yaml exec backend python -m app.email_service send-test you@yourdomain.com
   ```
6. Register a real test account, then check the message headers in the inbox: SPF, DKIM and DMARC should each say `pass`.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `APP_PUBLIC_URL` | `http://localhost:8080` | Public address used in every link. Must be `https://` in production. Request headers are never used for this. `PUBLIC_BASE_URL` still works as the older name |
| `MAIL_TRANSPORT` | `smtp` in production | `smtp`, or `file` (development only, writes `.eml` files) |
| `SMTP_HOST` | | Your provider's SMTP server |
| `SMTP_PORT` | `587` | |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | | From your provider. Only ever read by the backend, never sent to the browser |
| `SMTP_FROM_EMAIL` | | Sender address on your verified domain |
| `SMTP_FROM_NAME` | `OpenLabs3D` | Sender name |
| `SMTP_REPLY_TO` | | Optional reply address |
| `SMTP_USE_STARTTLS` | `true` | Encrypt on port 587. Older name: `SMTP_STARTTLS` |
| `SMTP_USE_SSL` | `false` | Encrypt from the start, usually port 465. Set `SMTP_USE_STARTTLS=false` with it |
| `SMTP_TIMEOUT_SECONDS` | `10` | Connection and response timeout |
| `EMAIL_VERIFICATION_EXPIRY_HOURS` | `24` | Lifetime of verification and email-change links |
| `PASSWORD_RESET_EXPIRY_MINUTES` | `60` | Lifetime of password reset links |
| `EMAIL_RESEND_COOLDOWN_SECONDS` | `60` | Minimum time between messages of one kind to one address |
| `EMAIL_RESEND_HOURLY_LIMIT` | `5` | Maximum per hour of one kind to one address |
| `UNVERIFIED_ACCOUNT_RETENTION_DAYS` | `7` | A sign-up never confirmed is removed after this long, releasing its username and address |
| `EMAIL_WORKER` | `true` | `false` stops this process from sending |
| `MAIL_ALLOW_REAL_DELIVERY` | `false` | Lets a non-production environment reach a real server, for example staging |

If mail is misconfigured, the site keeps running. The problem is logged at startup, without any values, and messages wait in the queue for up to 72 hours. Production refuses to send without encryption or with a non-https `APP_PUBLIC_URL`.

## Provider setup

Any SMTP provider works. These need an account and domain verification, which only you can do. Check the details with the provider, because they can change.

**Brevo is the preferred provider.**

| Provider | `SMTP_HOST` | `SMTP_PORT` | `SMTP_USERNAME` | `SMTP_PASSWORD` | Note |
|---|---|---|---|---|---|
| [Resend](https://resend.com/docs/send-with-smtp) | `smtp.resend.com` | `587` | `resend` | An API key | |
| [Brevo](https://developers.brevo.com/docs/smtp-integration) | `smtp-relay.brevo.com` | `587` | The login on the SMTP tab | An SMTP key, not an API key | Can restrict keys to your server's IP |
| [Amazon SES](https://docs.aws.amazon.com/ses/latest/dg/send-email-smtp.html) | `email-smtp.<region>.amazonaws.com` | `587` | SES SMTP username | SES SMTP password | SMTP credentials are per region and differ from AWS access keys. New accounts start in a sandbox: request production access first |

## DNS records

Add these at your DNS host. **Take the exact values from your provider;** the ones below only show the form.

| Record | Name | Type | Example value | Purpose |
|---|---|---|---|---|
| SPF | `yourdomain.com`, or the subdomain your provider names | TXT | `v=spf1 include:<provider's domain> ~all` | Which servers may send for the domain. **Only one SPF record per name:** merge with any existing one |
| DKIM | Given by the provider, such as `<selector>._domainkey.yourdomain.com` | TXT or CNAME | Given by the provider | Signs each message, proving it is unaltered and authorized |
| DMARC | `_dmarc.yourdomain.com` | TXT | `v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com` | What receivers do when SPF and DKIM fail, and where to send reports |

Start DMARC at `p=none` and read the reports. Move to `p=quarantine`, then `p=reject`, once all your legitimate mail passes. Sender verification means proving to the provider that you own the domain, usually through these same records.

## Common delivery errors

`last_error` holds the error class and SMTP code, never the address, link or server text. To see it:

```bash
docker compose -f compose.yaml -f compose.production.yaml exec backend python -c "
import sqlite3; d=sqlite3.connect('file:/app/data/openlabs3d.db?mode=ro',uri=True)
print(*d.execute('select id,kind,status,attempts,last_error,created_at from email_jobs order by id desc limit 20'),sep='\n')"
```

| `last_error` or symptom | Likely cause | What to do |
|---|---|---|
| `SMTPAuthenticationError 535` | Wrong username or key. On Brevo or SES, using an API or AWS key instead of the SMTP credential | Fix the credential; the message retries |
| `SMTPNotSupportedError` | The server does not offer STARTTLS, so nothing was sent | Check host and port, or use port 465 with `SMTP_USE_SSL=true` |
| `SSLCertVerificationError` | The host name does not match the certificate, or something intercepts the connection | Use the exact host name from your provider |
| `TimeoutError`, `ConnectionRefusedError`, `gaierror` | Outbound port blocked (many hosting companies block 25, some block 587), or the host is wrong | Try port 587 or 465 from the server. Retries are automatic |
| `SMTPSenderRefused 553` or `550` | The sender address or domain is not verified | Verify it with the provider, and match `SMTP_FROM_EMAIL` to it |
| `SMTPRecipientsRefused 550` | The address does not exist. Status `failed`, not retried | Nothing; the user can register or resend with the right address |
| `SMTPRecipientsRefused 450` or `451`, `SMTPDataError 451` | Temporary refusal or greylisting | Retries are automatic |
| `SMTPDataError 554` | Rejected as spam or by policy. Not retried | Check SPF, DKIM and DMARC, and the provider's activity log |
| Status `sent`, but nothing in the inbox | The server accepted it, which does not prove delivery | Check spam, the provider's log and suppression list, and the authentication results |
| Status stays `pending`, 0 attempts | Mail is misconfigured, or the worker is off | See the startup log |

## How it works

**Sending.** A request only records what to send, in its own transaction (`email_jobs`). A worker thread in the backend sends it, so a slow provider never delays a request and a crash never loses a message. Failures retry after 1 minute, 5 minutes, 30 minutes, 2 hours and 6 hours. A permanent refusal stops at once. Finished messages are deleted after 30 days.

**To add a message** such as an order confirmation: write a builder in `backend/app/email_service.py` that returns `content(...)`, add it to `BUILDERS`, then call `enqueue(db, kind, recipient, user_id, context)` before the request commits and `wake()` after.

**Links.** 256 random bits. Only the SHA-256 hash is stored, and the link is created at send time, so neither the database nor the queue holds a usable one. The token is in the address fragment (`/#verify-email?token=…`), which browsers do not send to servers, so it stays out of Caddy and backend logs. The page removes it from the address bar as soon as it reads it. This differs from a `/verify-email?token=` path for that reason.

## Security

| Threat | Protection |
|---|---|
| Invalid, expired or reused links | Refused with a specific reason. A conditional update lets exactly one of several simultaneous attempts through |
| Learning which addresses are registered | A taken username is refused the same way whoever the address belongs to. Registering a taken address, resending and asking for a password reset all answer as for any other address, in about the same time. Sign-in reveals "not verified" only after the right password. Sign-in with an unknown address still checks a password hash |
| Excessive email | Per address: one per minute, five per hour. Per IP, over 15 minutes: 30 register, resend, forgot or reset requests, 60 verifications, 50 failed sign-ins. These are generous because a lab shares one address. Per account: 5 failed sign-ins, and 10 sensitive actions |
| Someone registering your address first | A second registration with a different password makes both passwords stop working. Whoever holds the inbox gets a link to choose a new one |
| Link pointing at another site | Links use only `APP_PUBLIC_URL`. No redirect target is accepted from a link |
| Bypassing the frontend | Enforced in the backend: at sign-in, on every signed-in request, and on each protected action |
| Taking over an account by changing its email | Needs the current password. The old address keeps working until the new one is confirmed, then is told, with the new address partly hidden. Other sessions and links sent to the old address stop working |
| Probing mailboxes | Never done. Only clicking the link verifies an address |

**Usernames.** A username is held from registration, including while the email is unconfirmed, and it is released when the account is deleted. A sign-up that is never confirmed is removed after `UNVERIFIED_ACCOUNT_RETENTION_DAYS`, once no link of it is still valid, which frees its name and address. Verified and grandfathered accounts are never removed this way. Registering again on an unconfirmed address, with a free username, replaces the name chosen earlier.

**Restricted until verified:** ordering, custom requests, applying as a host, creating and publishing listings, accepting printing jobs, CAD uploads. A new unverified account cannot sign in at all.

## Existing accounts

The migration `76a_email_verification` changes who can sign in as follows. It sends no email.

| State at migration | After it | Can sign in | Protected actions |
|---|---|---|---|
| `email_verified = 1` | Unchanged. `email_verified_at` stays empty: the date was never recorded and is not invented | Yes | Yes |
| `email_verified = 0` | **Grandfathered:** `legacy_email_access = 1`, still `email_verified = 0` | Yes | No, as before, until they verify |

Grandfathered accounts are never shown as verified. Account settings shows "Not verified" and a button to get a link. Verifying records the date and clears the flag. To list them:

```sql
SELECT id, role, email FROM users WHERE legacy_email_access = 1;
```

**On this development database:** account 14 (a buyer on gmail.com) is grandfathered. Accounts 10–13 were already verified, by the development seed rather than by a link. The backup from just before the migration is `backups/pre-email-verification-20261102-234411.db`.

## Local development

`docker compose up` also loads `compose.override.yaml`, which production does not. Every message goes to Mailpit, whatever `.env` says, so nothing real can be sent. No production credentials are needed.

**Nothing reaches a real inbox in this setup, even for a real address such as a Gmail one.** The "Check your inbox" page says so in development, with a link to Mailpit.

- **Read captured mail:** http://127.0.0.1:8025. It listens on this computer only, and it has no password, so do not expose it.
- **Test sending:** `docker compose exec backend python -m app.email_service send-test someone@example.org`
- **Safety net:** outside production, the backend refuses any SMTP server that is not local, unless `MAIL_ALLOW_REAL_DELIVERY=true`.

### Trying a real inbox from this computer

Use your Brevo account ([Provider setup](#provider-setup)). Fill in the prepared `.env`, add `COMPOSE_FILE=compose.yaml` to it, then:

```bash
docker compose up -d --build backend
docker compose exec backend python -m app.email_service send-test you@yourdomain.com
```

Every message then really goes out, so use only your own addresses. Remove that line and rebuild to return to Mailpit. A personal Gmail account is not used as a sender.

**Tests:**

```bash
# Backend, with a fake mail server
cd backend && uv run --no-project --python 3.12 --with-requirements requirements.txt --with httpx --with pytest python -m pytest tests/test_email_verification.py

# Whole experience through real SMTP to Mailpit, with an isolated database
docker compose up -d mailpit
EMAIL_QA_DIR=/some/empty/folder uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/email_preview.py
EMAIL_QA_DIR=/some/empty/folder uv run --no-project --python 3.12 --with playwright python tests/email_verification_browser.py OUTPUT_DIR
```

## Limitations

- **Accepted is not delivered.** Bounces and spam complaints are not processed. Addresses that bounce after acceptance need the provider's log or webhooks, which are not connected.
- **Link scanners.** A mail security scanner that runs JavaScript could open a link and verify the address without the person doing so. Opening the page without JavaScript changes nothing, because verifying needs a POST from the page. A confirmation button would close this, at the cost of an extra click.
- **Rate limits per IP are in memory.** They reset when the backend restarts, and they assume a single backend process, as deployed. Per-address limits are in the database and survive restarts. People behind one shared address share the per-IP limit.
- **The worker runs inside the backend process.** Messages wait while it is down, and continue after it restarts.
- **A newer link replaces an older one.** Only the newest verification email works. The page says so.
- **Reloading the result page** after a link was used shows the invalid-link page, because the token has been removed from the address.
- **Delivery failures are not shown in the admin interface.** See `email_jobs` as above.
- **`tests/browser_workflow.py`** (Selenium) expects registering to sign in, and was not updated or run.
