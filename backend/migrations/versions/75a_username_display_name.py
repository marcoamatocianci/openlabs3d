"""One public name: every account's display_name becomes its username (the column is kept for older code)."""
from alembic import op

revision = '75a_username_display_name'
down_revision = '74a_host_material_inventory'
branch_labels = depends_on = None

def upgrade():
    op.execute("UPDATE users SET display_name = username WHERE username IS NOT NULL AND username != ''")

def downgrade():
    pass  # Previous display names are not kept; the username remains a valid display name.
