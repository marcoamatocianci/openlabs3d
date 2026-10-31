"""Pin each order line to the exact CAD file and listing revision it was sold with.

New orders record these at checkout (cad_status 'pinned'). Earlier lines never stored them, so
the purchased version cannot be established: they are frozen to the model the listing referenced
when this migration ran, with its checksum, and marked 'unverified' so hosts and administrators
see that the original version is unknown. Later model uploads no longer affect any of them."""
import hashlib, re
from alembic import op
import sqlalchemy as sa
revision='70a_order_manufacturing_snapshot'
down_revision='69a_cart_price_confirmation'
branch_labels=depends_on=None
COLUMNS=('listing_version','cad_path','cad_sha256','cad_status')

def upgrade():
    op.add_column('order_items',sa.Column('listing_version',sa.Integer(),nullable=True))
    op.add_column('order_items',sa.Column('cad_path',sa.String(80),nullable=False,server_default=''))
    op.add_column('order_items',sa.Column('cad_sha256',sa.String(64),nullable=False,server_default=''))
    op.add_column('order_items',sa.Column('cad_status',sa.String(12),nullable=False,server_default=''))
    bind=op.get_bind()
    from app import config
    cad=config.UPLOAD_DIR.parent/'cad'   # same location as app.manufacturing.cad_file
    digests={}
    rows=bind.execute(sa.text('SELECT order_items.id, listings.cad_path FROM order_items JOIN listings ON listings.id=order_items.listing_id')).all()
    for item_id,path in rows:
        path=path or ''
        if not re.fullmatch(r'[a-f0-9]{48}\.(stl|3mf)',path):status,path,digest='none','',''
        elif (cad/path).is_file():
            if path not in digests:digests[path]=hashlib.sha256((cad/path).read_bytes()).hexdigest()
            status,digest='unverified',digests[path]
        else:status,digest='unverified',''
        bind.execute(sa.text('UPDATE order_items SET cad_path=:path, cad_sha256=:digest, cad_status=:status WHERE id=:id'),{'path':path,'digest':digest,'status':status,'id':item_id})

def downgrade():
    with op.batch_alter_table('order_items') as batch:
        for column in reversed(COLUMNS):batch.drop_column(column)
