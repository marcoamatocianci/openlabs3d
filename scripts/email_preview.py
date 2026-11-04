"""Isolated email verification fixture: a temporary database, and real SMTP to the local Mailpit.
    docker compose up -d mailpit
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/email_preview.py
Serves http://127.0.0.1:18103 (EMAIL_QA_PORT). EMAIL_QA_DIR sets the data folder, so a test can reach the database.
Accounts (password TestPassword2026): verified@example.org, and legacy@example.org, which predates verification."""
import os, runpy, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]; temp = os.environ.get('EMAIL_QA_DIR') or tempfile.mkdtemp(prefix='ol3d-email-'); port = int(os.getenv('EMAIL_QA_PORT', '18103'))
settings = dict(MAIL_TRANSPORT='smtp', SMTP_HOST='127.0.0.1', SMTP_PORT=os.getenv('EMAIL_QA_SMTP_PORT', '1025'), SMTP_USE_STARTTLS='false', SMTP_FROM_EMAIL='noreply@openlabs3d.local', SMTP_FROM_NAME='OpenLabs3D',
                APP_PUBLIC_URL=f'http://127.0.0.1:{port}', MAIL_CAPTURE_URL=os.getenv('MAILPIT_URL', 'http://127.0.0.1:8025'), EMAIL_RESEND_COOLDOWN_SECONDS=os.getenv('EMAIL_RESEND_COOLDOWN_SECONDS', '3'))
os.environ.update(DATABASE_URL='sqlite:///' + temp + '/qa.db', UPLOAD_DIR=temp + '/uploads', APP_ENV='development', SEED_OFFICIAL_COLLECTION='false', **settings)
namespace = runpy.run_path(str(root / 'scripts/account_preview.py'))
os.environ.update(settings)   # the shared preview selects file mail
from app import models
from app.database import SessionLocal
from app.main import hasher
with SessionLocal() as db:
    for name, values in (('verified', {'email_verified': True}), ('legacy', {'legacy_email_access': True})):
        if not db.query(models.User).filter_by(username=name).first():
            db.add(models.User(email=name + '@example.org', username=name, display_name=name, password_hash=hasher.hash('TestPassword2026'), role='buyer', **values))
    db.commit()
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(namespace['app'], host='127.0.0.1', port=port)
