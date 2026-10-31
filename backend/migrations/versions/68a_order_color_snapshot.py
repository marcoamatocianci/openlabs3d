"""Snapshot the display colour of each purchased configuration.

Earlier lines keep an empty value: their exact colour was never stored, so the buyer
interface shows the recorded colour name instead of guessing one from current stock."""
from alembic import op
import sqlalchemy as sa
revision='68a_order_color_snapshot'
down_revision='67a_custom_requests'
branch_labels=depends_on=None

def upgrade():
    op.add_column('order_items',sa.Column('color_hex',sa.String(7),nullable=False,server_default=''))

def downgrade():
    with op.batch_alter_table('order_items') as batch:
        batch.drop_column('color_hex')
