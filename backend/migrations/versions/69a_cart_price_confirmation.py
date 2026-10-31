"""Remember the unit price a buyer saw and accepted for each basket line.

Existing lines get NULL: nobody can know which price their owner saw, so the basket asks the
buyer to review the current price once before checkout."""
from alembic import op
import sqlalchemy as sa
revision='69a_cart_price_confirmation'
down_revision='68a_order_color_snapshot'
branch_labels=depends_on=None

def upgrade():
    op.add_column('cart_items',sa.Column('confirmed_unit_price_cents',sa.Integer(),nullable=True))

def downgrade():
    with op.batch_alter_table('cart_items') as batch:
        batch.drop_column('confirmed_unit_price_cents')
