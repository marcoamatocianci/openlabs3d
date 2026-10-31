"""Custom tool requests and their reference files."""
from alembic import op
import sqlalchemy as sa
revision='67a_custom_requests'
down_revision='66a_printer_capabilities'
branch_labels=depends_on=None

def upgrade():
    op.create_table('custom_requests',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('idempotency_key',sa.String(80),nullable=False),
        sa.Column('title',sa.String(120),nullable=False),
        sa.Column('application',sa.Text(),nullable=False),
        sa.Column('dimensions',sa.Text(),nullable=False),
        sa.Column('compatibility',sa.Text(),nullable=False,server_default=''),
        sa.Column('quantity',sa.Integer(),nullable=False),
        sa.Column('material',sa.String(60),nullable=False,server_default=''),
        sa.Column('conditions',sa.Text(),nullable=False,server_default='[]'),
        sa.Column('requirements',sa.Text(),nullable=False,server_default=''),
        sa.Column('status',sa.String(20),nullable=False,server_default='submitted'),
        sa.Column('admin_notes',sa.Text(),nullable=False,server_default=''),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('user_id','idempotency_key'),
        sa.CheckConstraint('quantity BETWEEN 1 AND 10000'),
        sa.CheckConstraint("status IN ('submitted','under_review','quoted','closed')"))
    op.create_index('ix_custom_requests_user_id','custom_requests',['user_id'])
    op.create_index('ix_custom_requests_status','custom_requests',['status'])
    op.create_index('ix_custom_requests_created_at','custom_requests',['created_at'])
    op.create_table('custom_request_files',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('request_id',sa.Integer(),sa.ForeignKey('custom_requests.id',ondelete='CASCADE'),nullable=False),
        sa.Column('filename',sa.String(255),nullable=False),
        sa.Column('storage_path',sa.String(80),nullable=False,unique=True),
        sa.Column('kind',sa.String(10),nullable=False),
        sa.Column('size',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("kind IN ('model','image','document')"))
    op.create_index('ix_custom_request_files_request_id','custom_request_files',['request_id'])

def downgrade():
    op.drop_table('custom_request_files')
    op.drop_table('custom_requests')
