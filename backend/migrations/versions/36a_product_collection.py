"""Product collection, publication attribution and order colors."""
from alembic import op
import sqlalchemy as sa
revision = '36a_product_collection'
down_revision = '239b6b0a175f'
branch_labels = depends_on = None

def upgrade():
    op.add_column('listings',sa.Column('featured',sa.Boolean(),nullable=False,server_default='0'))
    op.add_column('listings',sa.Column('collection_key',sa.String(80),nullable=True))
    op.create_index('ix_listing_collection','listings',['collection_key'],unique=True)
    op.add_column('listings',sa.Column('approved_by',sa.Integer(),nullable=True))
    op.add_column('order_items',sa.Column('color',sa.String(40),nullable=False,server_default=''))

def downgrade():
    op.drop_column('order_items','color')
    op.drop_column('listings','approved_by')
    op.drop_index('ix_listing_collection',table_name='listings')
    op.drop_column('listings','collection_key')
    op.drop_column('listings','featured')
