"""Shipped status for orders and printing jobs, shipment details on the job, buyer-confirmed completion."""
from alembic import op
import sqlalchemy as sa

revision = '73a_shipped_status'
down_revision = '72a_unified_profile_picture'
branch_labels = depends_on = None

ORDER_OLD = "status IN ('pending','accepted','printing','ready','completed','cancelled')"
ORDER_NEW = "status IN ('pending','accepted','printing','ready','shipped','completed','cancelled')"
JOB_OLD = "status IN ('available','accepted','printing','ready','completed','cancelled')"
JOB_NEW = "status IN ('available','accepted','printing','ready','shipped','completed','cancelled')"

def checks(table, keep_out):
    """Reflected CHECK constraints of a table, without the status rule being replaced."""
    found = sa.inspect(op.get_bind()).get_check_constraints(table)
    return [sa.CheckConstraint(c['sqltext']) for c in found if ' '.join(c['sqltext'].split()) != keep_out]

def rebuild(table, old, new, columns=()):
    # SQLite cannot alter a CHECK constraint: rebuild the table with the new rule and every other one kept.
    with op.batch_alter_table(table, recreate='always', table_args=[*checks(table, old), sa.CheckConstraint(new)]) as batch:
        for column in columns: batch.add_column(column)

def upgrade():
    rebuild('orders', ORDER_OLD, ORDER_NEW)
    rebuild('printing_jobs', JOB_OLD, JOB_NEW, [
        sa.Column('carrier', sa.String(80), nullable=False, server_default=''),
        sa.Column('tracking_number', sa.String(80), nullable=False, server_default=''),
        sa.Column('tracking_url', sa.String(500), nullable=False, server_default=''),
        sa.Column('shipping_note', sa.String(500), nullable=False, server_default=''),
        sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True)])

def downgrade():
    # Older releases know no shipped state: a shipped job goes back to ready, and its order follows.
    op.execute("UPDATE printing_jobs SET status='ready' WHERE status='shipped'")
    op.execute("UPDATE orders SET status='ready' WHERE status='shipped'")
    with op.batch_alter_table('printing_jobs', recreate='always', table_args=[*checks('printing_jobs', JOB_NEW), sa.CheckConstraint(JOB_OLD)]) as batch:
        for name in ('shipped_at', 'shipping_note', 'tracking_url', 'tracking_number', 'carrier'): batch.drop_column(name)
    with op.batch_alter_table('orders', recreate='always', table_args=[*checks('orders', ORDER_NEW), sa.CheckConstraint(ORDER_OLD)]):
        pass
