"""Content-addressed CAD assets, stored files and the CAD processing queue; order snapshots become Text.

Runs on SQLite and PostgreSQL. Creates no rows: the CAD worker registers existing files and adopts their
existing previews on start (cad_assets.reconcile), so nothing is rendered again. orders.contact and
orders.address were VARCHAR(200)/VARCHAR(1000) while checkout accepts and stores up to 1000/3000
characters; SQLite never enforced the lengths, PostgreSQL does.
"""
import sqlalchemy as sa
from alembic import op

revision = '78a_cad_assets'
down_revision = '77a_external_identities'
branch_labels = depends_on = None

def upgrade():
    op.create_table('cad_assets',
        sa.Column('sha256', sa.String(64), primary_key=True),
        sa.Column('format', sa.String(4), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('analysis', sa.Text(), nullable=True),
        sa.Column('analysis_version', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("format IN ('stl','3mf')"), sa.CheckConstraint('size_bytes >= 0'))
    op.create_table('cad_files',
        sa.Column('name', sa.String(80), primary_key=True),
        sa.Column('sha256', sa.String(64), sa.ForeignKey('cad_assets.sha256', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_cad_files_sha256', 'cad_files', ['sha256'])
    op.create_table('cad_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sha256', sa.String(64), sa.ForeignKey('cad_assets.sha256', ondelete='RESTRICT'), nullable=False),
        sa.Column('kind', sa.String(12), nullable=False),
        sa.Column('cache_key', sa.String(40), nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default='queued'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('claimed_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('output_dir', sa.String(64), nullable=False, server_default=''),
        sa.Column('result', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('last_error', sa.String(500), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('sha256', 'kind', 'cache_key', name='uq_cad_job_stage'),
        sa.CheckConstraint("kind IN ('analyze','render')"),
        sa.CheckConstraint("status IN ('queued','processing','ready','failed')"))
    op.create_index('ix_cad_jobs_due', 'cad_jobs', ['status', 'next_attempt_at'])
    # PostgreSQL only. SQLite ignores VARCHAR lengths (both are TEXT affinity), and changing the declared type
    # there would rebuild the orders table, dropping its unnamed CHECK constraints.
    if op.get_bind().dialect.name != 'sqlite':
        op.alter_column('orders', 'contact', type_=sa.Text(), existing_type=sa.String(200), existing_nullable=False)
        op.alter_column('orders', 'address', type_=sa.Text(), existing_type=sa.String(1000), existing_nullable=False)

def downgrade():
    # Refuses on PostgreSQL if a stored snapshot no longer fits, rather than truncating it.
    if op.get_bind().dialect.name != 'sqlite':
        op.alter_column('orders', 'address', type_=sa.String(1000), existing_type=sa.Text(), existing_nullable=False)
        op.alter_column('orders', 'contact', type_=sa.String(200), existing_type=sa.Text(), existing_nullable=False)
    op.drop_index('ix_cad_jobs_due', 'cad_jobs')
    op.drop_table('cad_jobs')
    op.drop_index('ix_cad_files_sha256', 'cad_files')
    op.drop_table('cad_files')
    op.drop_table('cad_assets')
