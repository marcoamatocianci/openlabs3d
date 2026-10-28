"""Persistent model references and opt-in pricing rules."""
from alembic import op
import sqlalchemy as sa
revision='47b_configurator'
down_revision='36a_product_collection'
branch_labels=depends_on=None

def upgrade():
    op.add_column('listings',sa.Column('model_url',sa.String(300),nullable=False,server_default=''))
    op.add_column('listings',sa.Column('configuration',sa.Text(),nullable=False,server_default='{}'))
    for key in ('microtube-rack','15ml-rack','50ml-rack'):
        op.execute(sa.text('UPDATE listings SET model_url=:url WHERE collection_key=:key').bindparams(url='/assets/models/'+key+'.glb',key=key))
def downgrade():
    op.drop_column('listings','configuration');op.drop_column('listings','model_url')
