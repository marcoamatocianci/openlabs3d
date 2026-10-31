"""Unified profile picture: persistence, catalogue, validation, migration and authorized rendering."""
import io
import json
import re
import secrets
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, create_engine, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_marketplace import app, register, headers, SessionLocal
from app import models, config
from app.avatars import VARIANTS, FOREGROUNDS, BACKGROUNDS, contrast, picture_data
from app.main import digest

STYLE = {'type':'erlenmeyer', 'variant':'angular', 'foreground':'#386641', 'background':'#fcfaf5'}

def photo():
    data = io.BytesIO()
    Image.new('RGB', (64, 64), (200, 80, 60)).save(data, format='PNG')
    return data.getvalue()

def owner():
    client = TestClient(app)
    email = 'picture_' + secrets.token_hex(5) + '@example.org'
    return client, headers(register(client, email)), email

def picture(client):
    return client.get('/api/auth/me').json()['user']['profile_picture']

def save(client, h, style=STYLE):
    return client.put('/api/profile/avatar-style', json={'kind':'avatar', 'style':style}, headers=h)

def staff_client():
    with SessionLocal() as db:
        admin = models.User(email=secrets.token_hex(5)+'@example.org', display_name='Admin', password_hash='x', role='admin', email_verified=True)
        db.add(admin); db.flush()
        session = secrets.token_urlsafe(16)
        db.add(models.LoginSession(token_hash=digest(session), user_id=admin.id, csrf='c', expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        db.commit()
    staff = TestClient(app); staff.cookies.set('ol3d_session', session)
    return staff

def test_catalogue_and_palettes_match_browser():
    script = (Path(__file__).resolve().parents[2]/'assets/lab-avatars.js').read_text()
    browser = json.loads(re.search(r'const AVATAR_VARIANTS = (\{.*?\});', script).group(1))
    assert browser == {k:list(v) for k,v in VARIANTS.items()}
    assert len(VARIANTS) == 6 and VARIANTS['dna'] == ('helix',)
    assert VARIANTS['molecule'] == ('triad', 'ring', 'chain')
    assert all(len(v) == 1 for k,v in VARIANTS.items() if k != 'molecule')
    for name, colors in (('FOREGROUNDS', FOREGROUNDS), ('BACKGROUNDS', BACKGROUNDS)):
        browser_colors = json.loads(re.search(r'const AVATAR_'+name+r' = (\[.*?\]);',script).group(1).replace("'", '"'))
        assert browser_colors == list(colors) and len(colors) == 5

def test_new_user_initials_and_atomic_replacements_persist_after_login():
    client, h, email = owner()
    user = client.get('/api/auth/me').json()['user']
    assert user['profile_picture'] == {'kind':'initials'}
    assert not {'avatar', 'avatar_mode', 'avatar_style'} & user.keys()
    for _ in range(2):
        saved = save(client, h)
        assert saved.status_code == 200, saved.text
        assert picture(client) == {'kind':'avatar','style':{**STYLE, 'foreground':'#386641'}}
        uploaded = client.post('/api/profile/avatar',files={'file':('me.png',photo(),'image/png')},headers=h)
        assert uploaded.status_code == 200
        assert set(picture(client)) == {'kind','file'} and picture(client)['kind'] == 'photo'
        assert client.get('/api/profile/avatar').status_code == 200
    saved_photo = picture(client)
    assert client.post('/api/auth/logout',headers=h).status_code == 200
    login = client.post('/api/auth/login',json={'email':email,'password':'LongPasswordForTest2026'})
    assert login.status_code == 200 and picture(client) == saved_photo
    h = headers(login.json()['csrf_token'])
    assert save(client,h).status_code == 200
    assert client.get('/api/profile/avatar').status_code == 404, 'no inactive photo can be served'
    with SessionLocal() as db:
        u = db.scalar(select(models.User).where(models.User.email==email))
        assert u.avatar == u.avatar_style == ''
        assert json.loads(u.profile_picture)['kind'] == 'avatar'
    assert client.delete('/api/profile/avatar',headers=h).json()['profile_picture'] == {'kind':'initials'}

@pytest.mark.parametrize('type,variant', [(t,v) for t,vs in VARIANTS.items() for v in vs])
def test_every_curated_motif_can_be_saved(type, variant):
    client,h,_ = owner()
    assert save(client,h,{**STYLE,'type':type,'variant':variant}).status_code == 200

def test_invalid_choices_and_uploads_preserve_previous_picture():
    client,h,_ = owner(); save(client,h)
    before = picture(client)
    for bad in ({**STYLE,'type':'skull'}, {**STYLE,'type':'beaker','variant':'classic'}, {**STYLE,'type':'dna','variant':'beads'},
                {**STYLE,'foreground':'#fff'}, {**STYLE,'foreground':'#123456'}, {**STYLE,'background':'#ffffff'},
                {**STYLE,'extra':'x'},
                {**STYLE,'type':['dna']}, {**STYLE,'background':'#000000"/><script>alert(1)</script>'}):
        assert save(client,h,bad).status_code == 422, bad
        assert picture(client) == before
    for choice in ({'kind':'avatar'}, {'kind':'photo','file':'../x'}, {'kind':'initials','style':STYLE}, {'mode':'custom','style':STYLE}):
        assert client.put('/api/profile/avatar-style',json=choice,headers=h).status_code == 422
    assert client.post('/api/profile/avatar',files={'file':('fake.png',b'not image','image/png')},headers=h).status_code == 422
    assert client.post('/api/profile/avatar',files={'file':('huge.png',b'x'*(2*1024*1024+1),'image/png')},headers=h).status_code == 413
    assert picture(client) == before
    assert save(client,{}).status_code == 403
    assert save(TestClient(app),{}).status_code == 401


def test_all_curated_palette_pairs_are_allowed():
    from app.avatars import AvatarStyle
    for f in FOREGROUNDS:
        for b in BACKGROUNDS:
            assert AvatarStyle(**{**STYLE,'foreground':f,'background':b}).foreground == f


def test_administrators_see_the_same_active_picture_and_photos_are_authorized():
    client,h,email = owner(); stranger,_,_ = owner(); staff = staff_client()
    user = client.get('/api/auth/me').json()['user']; url = f"/api/profile/avatar?user_id={user['id']}"
    def row(): return next(u for u in staff.get('/api/admin/users').json() if u['email']==email)
    assert row()['profile_picture'] == {'kind':'initials'}
    client.post('/api/profile/avatar',files={'file':('me.png',photo(),'image/png')},headers=h)
    assert row()['profile_picture'] == picture(client)
    assert staff.get(url).content == client.get(url).content
    assert stranger.get(url).status_code == 403
    assert TestClient(app).get(url).status_code == 401
    save(client,h)
    assert row()['profile_picture'] == picture(client)
    assert staff.get(url).status_code == 404
    with SessionLocal() as db:
        u=db.get(models.User,user['id']);u.profile_picture='{"kind":"avatar","style":{"type":"<svg>"}}';db.commit()
    assert row()['profile_picture'] == {'kind':'initials'}

@pytest.mark.parametrize('raw', ['null','[]','"x"','{"kind":"photo","file":"../../etc/passwd"}', '{"kind":"avatar","style":{"type":[]}}'])
def test_malformed_stored_data_is_safe(raw):
    assert picture_data(raw) == {'kind':'initials'}


def test_migration_preserves_active_legacy_pictures_and_archives(tmp_path):
    path=Path(__file__).resolve().parents[1]/'migrations/versions/72a_unified_profile_picture.py'
    spec=importlib.util.spec_from_file_location('picture_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    legacy={'type':'dna','variant':'beads','foreground':'#f4a261','background':'#2b2d42'}
    filename='a'*48+'.webp'
    cases=[('', 'photo', ''), (filename,'photo',json.dumps(legacy)), (filename,'custom',json.dumps(legacy)),
           (filename,'unknown',json.dumps(legacy)), ('','custom',json.dumps(legacy)), (filename,'custom','broken')]
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    with engine.begin() as db:
        db.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, avatar TEXT, avatar_mode TEXT, avatar_style TEXT)'))
        for i,(photo_file,mode,style) in enumerate(cases):
            db.execute(text('INSERT INTO users VALUES (:id,:photo,:mode,:style)'),{'id':i,'photo':photo_file,'mode':mode,'style':style})
        with Operations.context(MigrationContext.configure(db)): migration.upgrade()
        rows=db.execute(text('SELECT * FROM users ORDER BY id')).mappings().all()
        assert [picture_data(r['profile_picture'])['kind'] for r in rows] == ['initials','photo','avatar','photo','avatar','photo']
        for row,original in zip(rows,cases):
            assert (row['avatar'],row['avatar_mode'],row['avatar_style']) == original
        assert picture_data(rows[2]['profile_picture'])['style'] == legacy
        with Operations.context(MigrationContext.configure(db)): migration.downgrade()
        assert 'profile_picture' not in db.execute(text('SELECT * FROM users')).keys()


def test_upload_commit_failure_preserves_selection_and_removes_staged_file(monkeypatch):
    from sqlalchemy.orm import Session
    client,h,_ = owner()
    client.post('/api/profile/avatar',files={'file':('me.png',photo(),'image/png')},headers=h)
    before=picture(client)
    directory=config.UPLOAD_DIR.parent/'avatars'
    files_before=set(directory.iterdir())
    def failed_commit(self): raise RuntimeError('Simulated database failure')
    with monkeypatch.context() as patch:
        patch.setattr(Session,'commit',failed_commit)
        with pytest.raises(RuntimeError,match='Simulated database failure'):
            client.post('/api/profile/avatar',files={'file':('replacement.png',photo(),'image/png')},headers=h)
    assert picture(client)==before
    assert set(directory.iterdir())==files_before
    assert client.get('/api/profile/avatar').status_code==200
