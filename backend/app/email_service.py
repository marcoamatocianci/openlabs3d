"""Transactional email. A request only records what to send, in its own transaction (email_jobs). A worker thread
sends it and retries with growing delays, so a slow or failing provider neither holds up a request nor loses a message.

Links are created when a message is sent, and only their hash is stored, so the queue never holds a usable link.

To add a message (order confirmation, host notification): write a builder that returns content(...), add it to
BUILDERS, and call enqueue(db, kind, recipient, user_id, context) before the request commits, then wake() after."""
import hashlib, html, json, logging, os, secrets, smtplib, ssl, sys, threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from pathlib import Path
from sqlalchemy import delete, func, select, text, update
from . import config, database, models

log = logging.getLogger('openlabs3d.email')
RETRY_DELAYS = (60, 300, 1800, 7200, 21600)     # seconds; a message gets one more attempt than delays, over about 8.5 hours
CLAIM_SECONDS = 300                             # a message whose sender died is tried again after this
MAX_AGE_HOURS = 72                              # never deliver a stale link or notice after an outage longer than this
POLL_SECONDS = 15
LOCAL_SMTP_HOSTS = {'mailpit', 'localhost', '127.0.0.1', '::1'}

def utcnow(): return datetime.now(timezone.utc)

# Configuration ----------------------------------------------------------------------------------

def flag(name, default=''): return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes')

@dataclass(frozen=True)
class SmtpSettings:
    host: str; port: int; username: str; password: str; from_email: str; from_name: str; reply_to: str
    starttls: bool; use_ssl: bool; timeout: float

def smtp_settings():
    """Read when sending. SMTP_STARTTLS and SMTP_FROM are the older names."""
    name, address = parseaddr(os.getenv('SMTP_FROM', ''))
    return SmtpSettings(host=os.getenv('SMTP_HOST', '').strip(), port=int(os.getenv('SMTP_PORT') or 587),
        username=os.getenv('SMTP_USERNAME', ''), password=os.getenv('SMTP_PASSWORD', ''),
        from_email=os.getenv('SMTP_FROM_EMAIL', '').strip() or address, from_name=os.getenv('SMTP_FROM_NAME', '').strip() or name or 'OpenLabs3D',
        reply_to=os.getenv('SMTP_REPLY_TO', '').strip(), starttls=flag('SMTP_USE_STARTTLS', os.getenv('SMTP_STARTTLS', 'true')),
        use_ssl=flag('SMTP_USE_SSL'), timeout=float(os.getenv('SMTP_TIMEOUT_SECONDS') or 10))

def capture_info():
    """In development, where the page can point to the mail capture: mail sent there never reaches a real inbox,
    and a message saying "check your inbox" would otherwise send a developer to the wrong place."""
    url = os.getenv('MAIL_CAPTURE_URL', '').strip()
    return {'mail_capture_url': url} if url and config.APP_ENV != 'production' else {}

def mail_transport(): return os.getenv('MAIL_TRANSPORT', 'file' if config.APP_ENV == 'development' else 'smtp')

def configuration_problems():
    """Why mail cannot go out, naming settings and never their values. Messages wait in the queue meanwhile."""
    transport = mail_transport()
    if transport == 'file': return [] if config.APP_ENV == 'development' else ['MAIL_TRANSPORT=file is only for development']
    if transport != 'smtp': return ['MAIL_TRANSPORT must be smtp or file']
    s, problems = smtp_settings(), []
    if not s.host: problems.append('SMTP_HOST is not set')
    if not s.from_email: problems.append('SMTP_FROM_EMAIL is not set')
    if s.username and not s.password: problems.append('SMTP_USERNAME is set without SMTP_PASSWORD')
    if s.starttls and s.use_ssl: problems.append('Use either SMTP_USE_STARTTLS or SMTP_USE_SSL, not both')
    if config.APP_ENV == 'production':
        if not (s.starttls or s.use_ssl): problems.append('Production needs SMTP_USE_STARTTLS or SMTP_USE_SSL')
        if not config.APP_PUBLIC_URL.startswith('https://'): problems.append('APP_PUBLIC_URL must start with https:// in production')
    elif s.host not in LOCAL_SMTP_HOSTS and not flag('MAIL_ALLOW_REAL_DELIVERY'):
        problems.append('Outside production, SMTP only goes to a local capture service unless MAIL_ALLOW_REAL_DELIVERY=true')
    if s.username and not (s.starttls or s.use_ssl) and s.host not in LOCAL_SMTP_HOSTS: problems.append('SMTP credentials need an encrypted connection')
    return problems

# Queue ------------------------------------------------------------------------------------------

def enqueue(db, kind, recipient, user_id=None, context=None):
    """Adds a message to the caller's transaction: it exists only if the request commits. Call wake() after the commit."""
    if kind not in BUILDERS: raise ValueError('Unknown email kind')
    job = models.EmailJob(kind=kind, recipient=recipient.lower(), user_id=user_id, context=json.dumps(context or {}))
    db.add(job); db.flush()
    return job

def recently_queued(db, kind, recipient):
    since = utcnow() - timedelta(seconds=config.EMAIL_RESEND_COOLDOWN_SECONDS)
    return bool(db.scalar(select(func.count()).select_from(models.EmailJob).where(models.EmailJob.recipient == recipient.lower(), models.EmailJob.kind == kind, models.EmailJob.status != 'cancelled', models.EmailJob.created_at > since)))

def enqueue_limited(db, kind, recipient, user_id=None, context=None):
    """As enqueue, within the cooldown and hourly limit per address. Cancelled messages were never sent and do not count."""
    if recently_queued(db, kind, recipient): return False
    hour = db.scalar(select(func.count()).select_from(models.EmailJob).where(models.EmailJob.recipient == recipient.lower(), models.EmailJob.kind == kind, models.EmailJob.status != 'cancelled', models.EmailJob.created_at > utcnow() - timedelta(hours=1)))
    if hour >= config.EMAIL_RESEND_HOURLY_LIMIT: return False
    return enqueue(db, kind, recipient, user_id, context) is not None

def cancel_pending(db, user_id, kinds):
    db.execute(update(models.EmailJob).where(models.EmailJob.user_id == user_id, models.EmailJob.kind.in_(kinds), models.EmailJob.status == 'pending').values(status='cancelled'))

# Links ------------------------------------------------------------------------------------------

def issue_token(db, user, purpose, lifetime, new_email=None):
    """A new single-use link token, replacing earlier ones of this purpose. Only the hash is stored."""
    token = secrets.token_urlsafe(32)
    db.execute(delete(models.AccountToken).where(models.AccountToken.user_id == user.id, models.AccountToken.purpose == purpose))
    db.add(models.AccountToken(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id, purpose=purpose, new_email=new_email, expires_at=utcnow() + lifetime))
    return token

def link(route, token=None): return f"{config.APP_PUBLIC_URL}/#{route}" + (f'?token={token}' if token else '')

def mask_address(address):
    name, _, domain = address.partition('@')
    return f'{name[:1]}***@{domain}'

# Content ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Content:
    subject: str; text: str; html: str

INK, TEAL, PAPER, LINE, MUTED = '#1d3557', '#396d8e', '#edf4fa', '#d6e1eb', '#52677e'
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

def content(subject, heading, paragraphs, button=None, url=None, note=''):
    """Table layout and inline styles, the form every major client renders. All values are escaped."""
    e = html.escape
    body = ''.join(f'<p style="margin:0 0 16px;font:16px/1.55 {FONT};color:{INK}">{e(p)}</p>' for p in paragraphs)
    action = plain = ''
    if button:
        action = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 24px"><tr><td style="border-radius:7px;background:{INK}">'
                  f'<a href="{e(url, quote=True)}" style="display:inline-block;padding:13px 26px;font:600 16px/1.2 {FONT};color:#ffffff;text-decoration:none;border-radius:7px">{e(button)}</a></td></tr></table>'
                  f'<p style="margin:0 0 16px;font:13px/1.5 {FONT};color:{MUTED}">If the button does not work, copy this address into your browser:<br><a href="{e(url, quote=True)}" style="color:{TEAL};word-break:break-all">{e(url)}</a></p>')
        plain = f'{button}:\n{url}\n\n'
    footnote = f'<p style="margin:0;font:13px/1.5 {FONT};color:{MUTED}">{e(note)}</p>' if note else ''
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{e(subject)}</title></head>'
            f'<body style="margin:0;padding:0;background:{PAPER}"><div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(paragraphs[0])}</div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}"><tr><td align="center" style="padding:32px 16px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px"><tr><td style="padding:0 4px 18px">'
            f'<img src="{e(config.APP_PUBLIC_URL, quote=True)}/assets/brand/favicon-192.png" width="32" height="32" alt="" style="vertical-align:middle;border:0;border-radius:7px"> '
            f'<span style="vertical-align:middle;font:700 18px {FONT};color:{INK}">OpenLabs3D</span></td></tr>'
            f'<tr><td style="padding:32px 32px 28px;background:#ffffff;border:1px solid {LINE};border-radius:12px">'
            f'<h1 style="margin:0 0 16px;font:600 24px/1.25 {FONT};color:{INK}">{e(heading)}</h1>{body}{action}{footnote}</td></tr>'
            f'<tr><td style="padding:18px 4px 0;font:12px/1.5 {FONT};color:{MUTED}">OpenLabs3D · Laboratory tools, printed on demand. This is an automated message.</td></tr>'
            f'</table></td></tr></table></body></html>')
    words = '\n\n'.join(paragraphs)
    return Content(subject, f'{heading}\n\n{words}\n\n{plain}{note}\n\n-- \nOpenLabs3D. This is an automated message.\n', page)

def account_of(db, job):
    user = db.get(models.User, job.user_id) if job.user_id else None
    return user if user and user.active else None

def hours_text(): return f'{config.EMAIL_VERIFICATION_EXPIRY_HOURS} hours'

def verify_email(db, job, context):
    user = account_of(db, job)
    if not user or user.email_verified or user.email != job.recipient: return None
    token = issue_token(db, user, 'verify', timedelta(hours=config.EMAIL_VERIFICATION_EXPIRY_HOURS))
    return content('Verify your OpenLabs3D email address', 'Welcome to OpenLabs3D', ['Thanks for creating your account. Please confirm your email address to get started.'],
                   'Verify Email Address', link('verify-email', token), f"This verification link expires in {hours_text()}. If you didn't create an account, you can safely ignore this message.")

def email_change(db, job, context):
    user = account_of(db, job)
    if not user or user.pending_email != job.recipient: return None
    token = issue_token(db, user, 'email_change', timedelta(hours=config.EMAIL_VERIFICATION_EXPIRY_HOURS), new_email=job.recipient)
    return content('Confirm your new OpenLabs3D email address', 'Confirm your new email address', ['You asked to use this address for your OpenLabs3D account. Your current address stays active until you confirm this one.'],
                   'Confirm New Address', link('verify-email', token), f"This link expires in {hours_text()}. If you didn't ask for this, you can safely ignore this message.")

def password_reset(db, job, context):
    user = account_of(db, job)
    if not user or user.email != job.recipient: return None
    token = issue_token(db, user, 'reset', timedelta(minutes=config.PASSWORD_RESET_EXPIRY_MINUTES))
    if user.password_hash.startswith('!') and db.scalar(select(models.UserIdentity.id).where(models.UserIdentity.user_id == user.id).limit(1)):
        return content('Your OpenLabs3D sign-in', 'You sign in with Google', ['Your OpenLabs3D account uses Google to sign in, and Google manages that password. Use Continue with Google on the sign-in page.', 'If you would also like an OpenLabs3D password, you can choose one here.'],
                       'Choose a Password', link('reset', token), f"This link expires in {config.PASSWORD_RESET_EXPIRY_MINUTES} minutes. If you didn't ask for this, you can safely ignore this message.")
    return content('Reset your OpenLabs3D password', 'Reset your password', ['We received a request to reset the password of your OpenLabs3D account.'],
                   'Reset Password', link('reset', token), f"This link expires in {config.PASSWORD_RESET_EXPIRY_MINUTES} minutes. If you didn't ask for this, you can safely ignore this message; your password has not changed.")

def finish_registration(db, job, context):
    user = account_of(db, job)
    if not user or user.email_verified or user.email != job.recipient: return None
    token = issue_token(db, user, 'reset', timedelta(hours=config.EMAIL_VERIFICATION_EXPIRY_HOURS))
    return content('Finish setting up your OpenLabs3D account', 'Finish setting up your account',
                   ['Someone, possibly you, tried to create an account with this address while an earlier registration was waiting for confirmation.', 'To keep the account safe, no earlier password works any more. Choose a password to confirm this address and finish.'],
                   'Choose a Password', link('reset', token), f"This link expires in {hours_text()}. If this wasn't you, you can safely ignore this message: without a new password, nobody can sign in.")

def account_exists(db, job, context):
    return content('Someone tried to use your email on OpenLabs3D', 'This address already has an account', ['Someone tried to use this email address for a new or existing OpenLabs3D account, but it already belongs to an account. Nothing has changed.', 'If it was you, sign in instead, or reset your password from the sign-in page.'],
                   'Sign In', link('account'), "If it wasn't you, no action is needed.")

def email_changed_notice(db, job, context):
    setting = db.get(models.MarketplaceSetting, 'contact')
    contact = f' Please contact {setting.value} right away.' if setting and setting.value else ' Please contact the OpenLabs3D administrators right away.'
    return content('Your OpenLabs3D email address was changed', 'Your email address was changed', [f"The email address of your OpenLabs3D account was changed to {context.get('new_address', 'a new address')}. This address no longer signs in to it.", f"If you didn't make this change, your account may be at risk.{contact}"])

def password_changed(db, job, context):
    return content('Your OpenLabs3D password was changed', 'Your password was changed', ['The password of your OpenLabs3D account was just changed. Other sessions have been signed out.', "If this wasn't you, reset your password now from the sign-in page."], 'Sign In', link('account'))

def sign_in_method_changed(db, job, context):
    return content('A sign-in method of your OpenLabs3D account changed', 'Your sign-in methods changed', [f"{context.get('what', 'A sign-in method was changed')} on your OpenLabs3D account.", "If this wasn't you, reset your password now from the sign-in page."], 'Review Account', link('account'))

def test_message(db, job, context):
    return content('OpenLabs3D email test', 'Email delivery works', ['This test message confirms that OpenLabs3D can send through the configured mail server.'], 'Open OpenLabs3D', link('home'))

BUILDERS = {'verify_email': verify_email, 'email_change': email_change, 'password_reset': password_reset, 'finish_registration': finish_registration,
            'account_exists': account_exists, 'email_changed_notice': email_changed_notice, 'password_changed': password_changed, 'sign_in_method_changed': sign_in_method_changed, 'test_message': test_message}

def compose(recipient, item):
    s, message = smtp_settings(), EmailMessage()
    from_email = s.from_email or 'noreply@localhost'
    message['Subject'] = item.subject; message['To'] = recipient; message['From'] = formataddr((s.from_name, from_email))
    message['Date'] = formatdate(localtime=False); message['Message-ID'] = make_msgid(domain=from_email.rpartition('@')[2] or 'localhost')
    message['Auto-Submitted'] = 'auto-generated'
    if s.reply_to: message['Reply-To'] = s.reply_to
    message.set_content(item.text); message.add_alternative(item.html, subtype='html')
    return message

# Delivery ---------------------------------------------------------------------------------------

class DeliveryError(Exception):
    def __init__(self, reason, permanent=False):
        super().__init__(reason); self.reason, self.permanent = reason, permanent

def send_smtp(message, s):
    context = ssl.create_default_context()
    try:
        client = smtplib.SMTP_SSL(s.host, s.port, timeout=s.timeout, context=context) if s.use_ssl else smtplib.SMTP(s.host, s.port, timeout=s.timeout)
        with client:
            client.ehlo()
            # Refuses to continue (and so to send credentials) when the server does not offer encryption.
            if s.starttls: client.starttls(context=context); client.ehlo()
            if s.username: client.login(s.username, s.password)
            client.send_message(message)
    except smtplib.SMTPRecipientsRefused as e:
        codes = [code for code, _ in e.recipients.values()]
        raise DeliveryError(f'SMTPRecipientsRefused {codes[0] if codes else ""}'.strip(), permanent=bool(codes) and all(500 <= c < 600 for c in codes)) from None
    except smtplib.SMTPDataError as e: raise DeliveryError(f'SMTPDataError {e.smtp_code}', permanent=500 <= e.smtp_code < 600) from None
    # Credentials or a refused sender are this site's configuration: they can be fixed, so keep the message.
    except smtplib.SMTPResponseException as e: raise DeliveryError(f'{type(e).__name__} {e.smtp_code}') from None
    except (smtplib.SMTPException, OSError) as e: raise DeliveryError(type(e).__name__) from None

def send_file(message):
    directory = Path(os.getenv('MAIL_OUTBOX', str(config.UPLOAD_DIR.parent / 'mail')))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(directory / (secrets.token_hex(16) + '.eml'), 'xb', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream: stream.write(message.as_bytes())

def deliver(message):
    if mail_transport() == 'file': return send_file(message)
    send_smtp(message, smtp_settings())

def begin(db):
    database.write_lock(db)

def prepare_next(factory):
    """Claims the next due message and builds it, in one short transaction: nothing stays locked while sending.
    Returns (job id, kind, attempt, message); message is None when it no longer applies. None when nothing is due."""
    with factory() as db:
        begin(db)
        now = utcnow()
        job = db.scalars(select(models.EmailJob).where(((models.EmailJob.status == 'pending') & (models.EmailJob.next_attempt_at <= now)) | ((models.EmailJob.status == 'sending') & (models.EmailJob.claimed_until < now))).order_by(models.EmailJob.next_attempt_at, models.EmailJob.id).limit(1)).first()
        if job is None: db.rollback(); return None
        job.attempts += 1; job.status = 'sending'; job.claimed_until = now + timedelta(seconds=CLAIM_SECONDS)
        reference = (job.id, job.kind, job.attempts)
        if job.created_at.replace(tzinfo=timezone.utc) < now - timedelta(hours=MAX_AGE_HOURS):
            job.status = 'failed'; job.last_error = 'too old'; db.commit(); return (*reference, None)
        try: item = BUILDERS[job.kind](db, job, json.loads(job.context or '{}'))
        except Exception as e:
            db.rollback(); job = db.get(models.EmailJob, reference[0]); job.status = 'failed'; job.last_error = type(e).__name__; db.commit()
            log.error('email job %s (%s) could not be built: %s', reference[0], reference[1], type(e).__name__)
            return (*reference, None)
        if item is None: job.status = 'cancelled'; db.commit(); return (*reference, None)
        message = compose(job.recipient, item)
        db.commit()
        return (*reference, message)

def record_sent(factory, job_id):
    with factory() as db:
        job = db.get(models.EmailJob, job_id); job.status = 'sent'; job.sent_at = utcnow(); job.claimed_until = None; job.last_error = ''; db.commit()

def record_failure(factory, job_id, error):
    with factory() as db:
        job = db.get(models.EmailJob, job_id); job.last_error = error.reason[:200]; job.claimed_until = None
        if error.permanent or job.attempts > len(RETRY_DELAYS): job.status = 'failed'
        else: job.status = 'pending'; job.next_attempt_at = utcnow() + timedelta(seconds=RETRY_DELAYS[job.attempts - 1])
        db.commit()
        # Identifies the message without its address or link.
        log.warning('email job %s (%s) attempt %s: %s, now %s', job.id, job.kind, job.attempts, job.last_error, job.status)

def process_due(factory=None, limit=50):
    """Sends what is due and returns how many went out. Nothing is attempted, or used up, while mail is misconfigured."""
    factory = factory or database.SessionLocal
    if configuration_problems(): return 0
    sent = 0
    for _ in range(limit):
        prepared = prepare_next(factory)
        if prepared is None: break
        job_id, _kind, _attempt, message = prepared
        if message is None: continue
        try: deliver(message)
        except DeliveryError as e: record_failure(factory, job_id, e)
        except Exception as e: record_failure(factory, job_id, DeliveryError(type(e).__name__))
        else: record_sent(factory, job_id); sent += 1
    return sent

def remove_abandoned_signups(factory):
    """A sign-up never confirmed gives up its username and address. Such an account has never been able to sign in.
    Verified accounts and those from before verification was required (legacy_email_access) are never touched."""
    from fastapi import HTTPException
    from .operations import delete_account
    now, cutoff = utcnow(), utcnow() - timedelta(days=config.UNVERIFIED_ACCOUNT_RETENTION_DAYS)
    abandoned = (models.User.email_verified.is_(False), models.User.legacy_email_access.is_(False), models.User.created_at < cutoff)
    with factory() as db: ids = list(db.scalars(select(models.User.id).where(*abandoned)))
    for user_id in ids:
        with factory() as db:
            begin(db)
            user = db.scalar(select(models.User).where(models.User.id == user_id, *abandoned))
            # A link still valid may yet be clicked.
            if user is None or db.scalar(select(models.AccountToken.token_hash).where(models.AccountToken.user_id == user_id, models.AccountToken.used_at.is_(None), models.AccountToken.expires_at > now).limit(1)): db.rollback(); continue
            try: delete_account(user, user, db)
            except HTTPException: db.rollback(); log.warning('abandoned sign-up %s kept: it has linked records', user_id)

def purge(factory=None):
    """Addresses are personal data: finished messages, old links and abandoned sign-ups are not kept longer than useful."""
    factory = factory or database.SessionLocal
    remove_abandoned_signups(factory)
    with factory() as db:
        begin(db)
        db.execute(delete(models.EmailJob).where(models.EmailJob.status.in_(('sent', 'failed', 'cancelled')), models.EmailJob.created_at < utcnow() - timedelta(days=30)))
        db.execute(delete(models.AccountToken).where(models.AccountToken.expires_at < utcnow() - timedelta(days=7)))
        db.commit()

# Worker -----------------------------------------------------------------------------------------

wake_event, stop_event = threading.Event(), threading.Event()
worker = None

def wake(): wake_event.set()

def run_worker():
    last_purge = 0
    while not stop_event.is_set():
        wake_event.wait(POLL_SECONDS); wake_event.clear()
        if stop_event.is_set(): return
        try:
            process_due()
            now = datetime.now().timestamp()
            if now - last_purge > 3600: purge(); last_purge = now
        except Exception as e: log.error('email worker: %s', type(e).__name__)

def start_worker():
    global worker
    problems = configuration_problems()
    if problems: log.error('Email is not configured, messages will wait in the queue: %s', '; '.join(problems))
    if worker is None and not (os.getenv('EMAIL_WORKER') or 'true').lower() == 'false':
        stop_event.clear(); worker = threading.Thread(target=run_worker, name='email-worker', daemon=True); worker.start()

def stop_worker():
    global worker
    stop_event.set(); wake_event.set()
    if worker: worker.join(timeout=15)
    worker = None

if __name__ == '__main__':
    # Checks delivery from the server: python -m app.email_service send-test someone@example.org
    if len(sys.argv) != 3 or sys.argv[1] != 'send-test': sys.exit('Usage: python -m app.email_service send-test someone@example.org')
    problems = configuration_problems()
    if problems: sys.exit('Not configured: ' + '; '.join(problems))
    try: deliver(compose(sys.argv[2], test_message(None, None, {})))
    except DeliveryError as e: sys.exit('Not sent: ' + e.reason)
    print('Accepted by the mail server. That does not yet prove it reached the inbox.')
