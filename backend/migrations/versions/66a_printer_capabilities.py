"""Separate approved printer capabilities from host-managed material stock.
Existing approved materials become the printer's capabilities, so no host loses availability."""
from alembic import op
import sqlalchemy as sa
revision='66a_printer_capabilities'
down_revision='65a_equipment_revisions'
branch_labels=depends_on=None

def upgrade():
    op.add_column('host_printers',sa.Column('capabilities',sa.Text(),nullable=False,server_default='[]'))
    op.execute('UPDATE host_printers SET capabilities=materials')

def downgrade():
    with op.batch_alter_table('host_printers') as batch:batch.drop_column('capabilities')
