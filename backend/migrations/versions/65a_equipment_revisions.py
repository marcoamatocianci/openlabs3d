"""Add independent equipment proposals; preserve all existing account/equipment rows."""
from alembic import op
import sqlalchemy as sa
revision='65a_equipment_revisions'
down_revision='64a_material_colors'
branch_labels=depends_on=None

def upgrade():
    op.create_table('equipment_revisions',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('proposal',sa.Text(),nullable=False),sa.Column('before',sa.Text(),nullable=False),
        sa.Column('rejection_reason',sa.String(1000),nullable=False),
        sa.Column('reviewed_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('reviewed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("status IN ('draft','pending','approved','rejected')"))
    op.create_index('ix_equipment_revisions_user_id','equipment_revisions',['user_id'])
    op.create_index('ix_equipment_revisions_status','equipment_revisions',['status'])
    op.create_index('uq_equipment_open_revision','equipment_revisions',['user_id'],unique=True,sqlite_where=sa.text("status IN ('draft','pending')"))
    op.add_column('order_items',sa.Column('manufacturing_dimensions',sa.Text(),nullable=False,server_default='[]'))

def downgrade():
    op.drop_column('order_items','manufacturing_dimensions')
    op.drop_table('equipment_revisions')
