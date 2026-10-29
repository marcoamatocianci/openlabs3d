"""Structured equipment and controlled materials."""
from alembic import op
import sqlalchemy as sa
revision='61a_equipment'
down_revision='60a_carts'
branch_labels=depends_on=None
def upgrade():
    op.create_table('materials',sa.Column('name',sa.String(60),primary_key=True),sa.Column('technology',sa.String(10),nullable=False))
    op.create_table('printer_models',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('manufacturer',sa.String(100),nullable=False),sa.Column('model',sa.String(100),nullable=False),sa.Column('technology',sa.String(10),nullable=False),*[sa.Column(a,sa.Float(),nullable=True) for a in ('x','y','z')],sa.Column('source',sa.String(1000),nullable=False),sa.Column('verified',sa.Boolean(),nullable=False),sa.Column('materials',sa.Text(),nullable=False),sa.Column('limitations',sa.Text(),nullable=False),sa.UniqueConstraint('manufacturer','model'),sa.CheckConstraint("technology IN ('FDM','RESIN')"))
    op.create_table('host_printers',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('model_id',sa.Integer(),sa.ForeignKey('printer_models.id'),nullable=True),sa.Column('manufacturer',sa.String(100),nullable=False),sa.Column('model',sa.String(100),nullable=False),sa.Column('technology',sa.String(10),nullable=False),*[sa.Column(a,sa.Float(),nullable=False) for a in ('x','y','z')],sa.Column('quantity',sa.Integer(),nullable=False),sa.Column('materials',sa.Text(),nullable=False),sa.CheckConstraint("technology IN ('FDM','RESIN')"),sa.CheckConstraint('quantity BETWEEN 1 AND 100'),sa.CheckConstraint('x>0 AND y>0 AND z>0'))
    op.create_index('ix_host_printers_user_id','host_printers',['user_id'])
def downgrade():raise RuntimeError('Restore a backup to preserve equipment.')
