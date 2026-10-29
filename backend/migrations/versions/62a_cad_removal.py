"""CAD asset metadata and non-destructive product removal."""
from alembic import op
import sqlalchemy as sa
revision='62a_cad_removal'
down_revision='61a_equipment'
branch_labels=depends_on=None
def upgrade():
    op.add_column('listings',sa.Column('cad_path',sa.String(80),nullable=False,server_default=''))
    op.add_column('listings',sa.Column('cad_dimensions',sa.Text(),nullable=False,server_default='[]'))
    op.add_column('listings',sa.Column('removed',sa.Boolean(),nullable=False,server_default='0'))
def downgrade():raise RuntimeError('Restore a backup to preserve model references.')
