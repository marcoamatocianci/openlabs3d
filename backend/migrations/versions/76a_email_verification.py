"""Mandatory email verification: hashed single-use links, an email queue, and a pending address for changes.

Legacy strategy: every account that exists unverified at this point keeps the ability to sign in
(legacy_email_access) and stays unverified. It is not marked verified, because nothing shows it controls
its address. Accounts already verified stay so; their email_verified_at stays NULL, because the date was
never recorded and is not invented here."""
import sqlalchemy as sa
from alembic import op

revision = '76a_email_verification'
down_revision = '75a_username_display_name'
branch_labels = depends_on = None

def upgrade():
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('legacy_email_access', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('pending_email', sa.String(254), nullable=True))
    op.add_column('account_tokens', sa.Column('new_email', sa.String(254), nullable=True))
    op.add_column('account_tokens', sa.Column('used_at', sa.DateTime(timezone=True), nullable=True))
    op.execute('UPDATE users SET legacy_email_access = 1 WHERE email_verified = 0')
    op.create_table('email_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('recipient', sa.String(254), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('context', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(12), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('claimed_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(200), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_email_jobs_user_id', 'email_jobs', ['user_id'])
    op.create_index('ix_email_jobs_due', 'email_jobs', ['status', 'next_attempt_at'])
    op.create_index('ix_email_jobs_recipient', 'email_jobs', ['recipient', 'kind', 'created_at'])

def downgrade():
    op.drop_table('email_jobs')
    with op.batch_alter_table('account_tokens') as batch:
        batch.drop_column('used_at'); batch.drop_column('new_email')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('pending_email'); batch.drop_column('legacy_email_access'); batch.drop_column('email_verified_at')
