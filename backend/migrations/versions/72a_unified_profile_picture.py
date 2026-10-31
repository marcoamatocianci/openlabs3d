"""One active profile picture. Legacy columns and uploaded files are preserved for recovery."""
import json
import re
from alembic import op
import sqlalchemy as sa

revision = '72a_unified_profile_picture'
down_revision = '71a_lab_avatars'
branch_labels = depends_on = None

# Frozen historical catalogue; migration behavior must not change with application releases.
LEGACY = {'erlenmeyer': ('angular', 'rounded', 'liquid', 'abstract'), 'beaker': ('classic', 'filled', 'wide'), 'test-tube': ('single', 'trio', 'tilted'), 'pipette': ('classic', 'drop', 'minimal'), 'dna': ('helix', 'ladder', 'beads'), 'molecule': ('triad', 'ring', 'chain'), 'microscope': ('classic', 'compact'), 'petri-dish': ('colonies', 'agar', 'stacked'), 'cell': ('nucleus', 'dividing', 'membrane'), 'bacterium': ('rod', 'cocci', 'spiral'), 'centrifuge-tube': ('conical', 'filled', 'pair'), 'microplate': ('grid', 'filled', 'strip')}

def selection(row):
    try:
        style = json.loads(row['avatar_style'])
        valid = (isinstance(style, dict) and set(style) == {'type', 'variant', 'foreground', 'background'}
                 and all(isinstance(v, str) for v in style.values())
                 and style['variant'] in LEGACY.get(style['type'], ())
                 and all(re.fullmatch(r'#[0-9a-fA-F]{6}', style[k]) for k in ('foreground', 'background')))
    except (ValueError, TypeError):
        style, valid = None, False
    photo = row['avatar'] and re.fullmatch(r'[a-f0-9]{48}\.webp', row['avatar'])
    if valid and (row['avatar_mode'] == 'custom' or not photo):
        return {'kind': 'avatar', 'style': style}
    if photo:
        return {'kind': 'photo', 'file': row['avatar']}
    return {'kind': 'initials'}

def upgrade():
    op.add_column('users', sa.Column('profile_picture', sa.Text(), nullable=False, server_default='{"kind":"initials"}'))
    db = op.get_bind()
    rows = db.execute(sa.text('SELECT id, avatar, avatar_mode, avatar_style FROM users')).mappings().all()
    for row in rows:
        db.execute(sa.text('UPDATE users SET profile_picture=:picture WHERE id=:id'),
                   {'picture': json.dumps(selection(row), separators=(',', ':')), 'id': row['id']})

def downgrade():
    db = op.get_bind()
    for row in db.execute(sa.text('SELECT id, profile_picture FROM users')).mappings().all():
        picture = json.loads(row['profile_picture'])
        # Translate the latest choice back for older versions; keep migration archives otherwise.
        if picture['kind'] == 'photo':
            db.execute(sa.text("UPDATE users SET avatar=:file, avatar_mode='photo' WHERE id=:id"), {'file':picture['file'], 'id':row['id']})
        elif picture['kind'] == 'avatar':
            db.execute(sa.text("UPDATE users SET avatar_mode='custom', avatar_style=:style WHERE id=:id"), {'style':json.dumps(picture['style']), 'id':row['id']})
        else:
            db.execute(sa.text("UPDATE users SET avatar='', avatar_mode='photo', avatar_style='' WHERE id=:id"), {'id':row['id']})
    with op.batch_alter_table('users') as batch:
        batch.drop_column('profile_picture')
