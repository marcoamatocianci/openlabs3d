"""Review server on a scratch copy of a database backup (the original file is never opened for writing).
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/review_server.py BACKUP.db [UPLOADS_DIR]
Migrates the copy to head, creates one browser session per role (first active user of each role) and
writes their cookies to $TMP/review-sessions.json. Serves http://127.0.0.1:18110 (REVIEW_PORT).
"""
import hashlib, json, os, secrets, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]; temp = Path(tempfile.mkdtemp(prefix='ol3d-review-'))
shutil.copy(sys.argv[1], temp / 'review.db')
uploads = temp / 'uploads'
if len(sys.argv) > 2: shutil.copytree(sys.argv[2], uploads)
os.environ.update(DATABASE_URL='sqlite:///' + str(temp / 'review.db'), UPLOAD_DIR=str(uploads), APP_ENV='development', MAIL_TRANSPORT='file', SEED_OFFICIAL_COLLECTION='false')
namespace = __import__('runpy').run_path(str(root / 'scripts/account_preview.py'))   # migrates and mounts the static files
from sqlalchemy import select
from app.database import SessionLocal
from app import models
sessions = {}
with SessionLocal() as db:
    for role in ('buyer', 'host', 'admin'):
        user = db.scalar(select(models.User).where(models.User.role == role, models.User.active.is_(True)).order_by(models.User.id))
        if not user: continue
        token = secrets.token_urlsafe(32)
        db.add(models.LoginSession(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), csrf='review-csrf', expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
        sessions[role] = {'token': token, 'csrf': 'review-csrf', 'user': user.username, 'id': user.id}
    db.commit()
(Path(tempfile.gettempdir()) / 'review-sessions.json').write_text(json.dumps(sessions))
print('REVIEW_DATABASE=' + str(temp / 'review.db'), flush=True)
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(namespace['app'], host='127.0.0.1', port=int(os.getenv('REVIEW_PORT', '18110')))
