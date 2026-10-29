"""Copy complete profile postal addresses into saved addresses; profile columns are kept."""
from alembic import op
revision='63a_profile_addresses'
down_revision='62a_cad_removal'
branch_labels=depends_on=None
def upgrade():
    # Account Settings manages postal addresses only as saved addresses. Users who already
    # saved an address are left untouched; incomplete profile addresses are not copied.
    op.execute("""INSERT INTO user_addresses (user_id,label,first_name,last_name,phone,country,city,region,postal_code,street,additional,is_default)
        SELECT id,'',first_name,last_name,phone,country,city,region,postal_code,street,additional,1 FROM users
        WHERE first_name<>'' AND last_name<>'' AND phone<>'' AND country<>'' AND city<>'' AND street<>''
        AND NOT EXISTS (SELECT 1 FROM user_addresses a WHERE a.user_id=users.id)""")
def downgrade():
    # Data-only: the copied rows are ordinary saved addresses and remain valid.
    pass
