"""Preserve equipment; unknown colors remain an empty capability map."""
from alembic import op
import sqlalchemy as sa
revision = '64a_material_colors'
down_revision = '63a_profile_addresses'
branch_labels = depends_on = None
def upgrade():
    op.add_column('host_printers', sa.Column('material_colors', sa.Text(), nullable=False, server_default='{}'))
def downgrade():
    op.drop_column('host_printers', 'material_colors')
