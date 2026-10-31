"""Laboratory avatars: which picture an account shows, and its saved avatar design.

Existing accounts keep showing their uploaded photo ('photo'); accounts without one show a stable
generated laboratory avatar until they design their own."""
from alembic import op
import sqlalchemy as sa
revision='71a_lab_avatars'
down_revision='70a_order_manufacturing_snapshot'
branch_labels=depends_on=None

def upgrade():
    op.add_column('users',sa.Column('avatar_mode',sa.String(10),nullable=False,server_default='photo'))
    op.add_column('users',sa.Column('avatar_style',sa.Text(),nullable=False,server_default=''))

def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.drop_column('avatar_style')
        batch.drop_column('avatar_mode')
