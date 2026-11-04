"""External sign-in identities (Google first), and short-lived sign-in attempts. Changes no existing account."""
import sqlalchemy as sa
from alembic import op

revision = '77a_external_identities'
down_revision = '76a_email_verification'
branch_labels = depends_on = None

def upgrade():
    op.create_table('user_identities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(30), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('email', sa.String(254), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('provider', 'subject', name='uq_identity_subject'),
        sa.UniqueConstraint('user_id', 'provider', name='uq_identity_user_provider'))
    op.create_table('oauth_flows',
        sa.Column('state_hash', sa.String(64), primary_key=True),
        sa.Column('provider', sa.String(30), nullable=False),
        sa.Column('nonce', sa.String(100), nullable=False),
        sa.Column('code_verifier', sa.String(128), nullable=False),
        sa.Column('browser_hash', sa.String(64), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table('oauth_flows'); op.drop_table('user_identities')
