"""Reset a local development database to four test accounts.

Run only against disposable development data. Listings and orders are retained,
with ownership reassigned; host assignments and account-specific data are reset.
"""
import os
import uuid

# Refuse defaults, remote databases and production before importing application code.
if os.environ.get('APP_ENV') != 'development' or os.environ.get('DATABASE_URL') != 'sqlite:////app/data/openlabs3d.db' or os.environ.get('OPENLABS3D_DEV_RESET') != 'yes':
    raise SystemExit('Requires APP_ENV=development, the local development SQLite path and OPENLABS3D_DEV_RESET=yes')

from sqlalchemy import delete, update, text
from .database import SessionLocal
from .main import hasher
from . import models

ACCOUNTS = [
    ('admin@example.org', 'admin_test', 'AdminTest2026!', 'admin'),
    ('buyer@example.org', 'buyer_test', 'BuyerTest2026!', 'buyer'),
    ('host@example.org', 'host_test', 'HostTest2026!', 'host'),
    ('pending@example.org', 'pending_test', 'PendingTest2026!', 'buyer'),
]

def reset():
    with SessionLocal.begin() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        # Temporary unique identities allow repeat runs before old users are deleted.
        users=[]
        for email, username, password, role in ACCOUNTS:
            temporary=uuid.uuid4().hex
            user=models.User(email=temporary+'@invalid.local', username='tmp_'+temporary[:20], display_name=username,
                             password_hash=hasher.hash(password), role=role, active=True, email_verified=True)
            db.add(user); users.append(user)
        db.flush()
        admin,buyer,host,pending=users
        new_ids=[u.id for u in users]
        db.execute(update(models.Listing).values(owner_id=admin.id,approved_by=None))
        db.execute(update(models.Order).values(buyer_id=buyer.id))
        db.execute(update(models.PrintingJob).values(host_id=None))
        db.execute(update(models.Activity).values(actor_id=None))
        db.execute(delete(models.HostApplication))
        db.execute(delete(models.User).where(models.User.id.not_in(new_ids)))
        db.flush()
        for user,(email,username,_,_) in zip(users,ACCOUNTS):
            user.email=email;user.username=username
        db.add_all([models.HostApplication(user_id=host.id,status='approved',name='host_test',contact='host@example.org'),
                    models.HostApplication(user_id=pending.id,status='pending',name='pending_test',contact='pending@example.org',submitted_at=models.now())])
        db.flush()
        violations=db.execute(text('PRAGMA foreign_key_check')).fetchall()
        if violations: raise RuntimeError(f'Foreign key violations: {violations}')
    print('Development accounts reset successfully.')

if __name__ == '__main__': reset()
