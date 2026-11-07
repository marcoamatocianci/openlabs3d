"""Custom racks: saved designs, the build queue, and the private listing and order snapshot of a rack as sold.

Adds only: no existing row changes meaning. rack_hash stays NULL for every existing listing, and rack_snapshot empty
for every existing order line.
"""
import sqlalchemy as sa
from alembic import op

revision = '79a_parametric_racks'
down_revision = '78a_cad_assets'
branch_labels = depends_on = None

def upgrade():
    op.create_table('rack_designs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('config', sa.Text(), nullable=False),
        sa.Column('config_hash', sa.String(64), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_rack_designs_user_id', 'rack_designs', ['user_id'])
    op.create_table('rack_builds',
        sa.Column('config_hash', sa.String(64), primary_key=True),
        sa.Column('spec', sa.Text(), nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default='queued'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('claimed_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('result', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('last_error', sa.String(500), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued','processing','ready','failed','abandoned')"))
    op.create_index('ix_rack_builds_due', 'rack_builds', ['status', 'next_attempt_at'])
    # Plain ADD COLUMN on purpose: a batch recreate of these tables on SQLite would drop their unnamed CHECK constraints.
    op.add_column('listings', sa.Column('rack_hash', sa.String(64), nullable=True))
    op.add_column('listings', sa.Column('rack_snapshot', sa.Text(), nullable=False, server_default=''))
    op.add_column('listings', sa.Column('rack_design_id', sa.Integer(), nullable=True))
    op.create_index('uq_listing_rack', 'listings', ['owner_id', 'rack_hash'], unique=True, sqlite_where=sa.text('rack_hash IS NOT NULL'), postgresql_where=sa.text('rack_hash IS NOT NULL'))
    op.add_column('order_items', sa.Column('rack_snapshot', sa.Text(), nullable=False, server_default=''))

def downgrade():
    op.drop_column('order_items', 'rack_snapshot')
    op.drop_index('uq_listing_rack', table_name='listings')
    for column in ('rack_design_id', 'rack_snapshot', 'rack_hash'): op.drop_column('listings', column)
    op.drop_index('ix_rack_builds_due', table_name='rack_builds'); op.drop_table('rack_builds')
    op.drop_index('ix_rack_designs_user_id', table_name='rack_designs'); op.drop_table('rack_designs')
