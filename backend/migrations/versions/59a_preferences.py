"""Account appearance and safe avatar reference."""
from alembic import op
import sqlalchemy as sa
revision='59a_preferences'
down_revision='58a_accounts'
branch_labels=depends_on=None
def upgrade():
    op.add_column('users',sa.Column('theme',sa.String(10),nullable=False,server_default='system'))
    op.add_column('users',sa.Column('avatar',sa.String(80),nullable=False,server_default=''))
def downgrade():
    raise RuntimeError('Restore a backup to preserve user preferences.')
