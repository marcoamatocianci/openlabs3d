"""Account identities and saved contact information; preserve existing records."""
from alembic import op
import sqlalchemy as sa
import re
revision = '58a_accounts'
down_revision = '47b_configurator'
branch_labels = depends_on = None

def upgrade():
    op.add_column('users', sa.Column('username', sa.String(32, collation='NOCASE'), nullable=False, server_default=''))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='0'))
    for name, length in [('first_name',100),('last_name',100),('phone',40),('country',2),('city',150),('region',150),('postal_code',30),('street',200),('additional',200)]:
        op.add_column('users', sa.Column(name,sa.String(length),nullable=False,server_default=''))
    conn = op.get_bind()
    used = set()
    for uid, name in conn.execute(sa.text('SELECT id, display_name FROM users ORDER BY id')).all():
        base = re.sub('[^A-Za-z0-9_]', '_', name).strip('_')[:24] or 'user'
        if len(base)<3: base='user_'+base
        candidate=base
        while candidate.lower() in used: candidate=base+'_'+str(uid); base=candidate[:24]
        used.add(candidate.lower())
        conn.execute(sa.text('UPDATE users SET username=:name WHERE id=:id'), {'name':candidate,'id':uid})
    op.create_index('uq_users_username','users',['username'],unique=True)
    op.create_table('account_tokens',sa.Column('token_hash',sa.String(64),primary_key=True),sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('purpose',sa.String(20),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_account_tokens_user_id','account_tokens',['user_id'])
    op.create_table('user_addresses',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),*[sa.Column(n,sa.String(l),nullable=False) for n,l in [('label',40),('first_name',100),('last_name',100),('phone',40),('country',2),('city',150),('region',150),('postal_code',30),('street',200),('additional',200)]],sa.Column('is_default',sa.Boolean(),nullable=False))
    op.create_index('ix_user_addresses_user_id','user_addresses',['user_id'])
    op.create_index('uq_default_address','user_addresses',['user_id'],unique=True,sqlite_where=sa.text('is_default = 1'))

def downgrade():
    raise RuntimeError('Account migration contains user data. Restore a verified backup instead of dropping account records.')
