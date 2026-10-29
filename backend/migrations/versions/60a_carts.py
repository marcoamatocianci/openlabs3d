"""Per-user persistent cart lines; prices are never persisted in carts."""
from alembic import op
import sqlalchemy as sa
revision='60a_carts'
down_revision='59a_preferences'
branch_labels=depends_on=None
def upgrade():
    op.create_table('cart_items',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('listing_id',sa.Integer(),sa.ForeignKey('listings.id',ondelete='CASCADE'),nullable=False),sa.Column('material',sa.String(200),nullable=False),sa.Column('color',sa.String(40),nullable=False),sa.Column('quantity',sa.Integer(),nullable=False),sa.UniqueConstraint('user_id','listing_id','material','color'),sa.CheckConstraint('quantity BETWEEN 1 AND 50'))
    op.create_index('ix_cart_items_user_id','cart_items',['user_id'])
def downgrade():raise RuntimeError('Restore a backup to preserve carts.')
