"""Per-host material inventory, chosen once for all printers (host_materials).

Existing per-printer stock (host_printers.materials / material_colors) is merged per host: every
stocked material, with the union of its colours. If two printers listed the same colour name in
different shades, the later shade is kept under "name-2", "name-3"… so no shade is lost. The printer
columns are left untouched (no longer read), so a downgrade restores the previous behaviour.
"""
import json
from alembic import op
import sqlalchemy as sa

revision = '74a_host_material_inventory'
down_revision = '73a_shipped_status'
branch_labels = depends_on = None

def merged_inventory(rows):
    """rows: (user_id, materials JSON, material_colors JSON) in printer order -> {user: {material: {name: hex}}}."""
    inventory = {}
    for user_id, materials, colors in rows:
        try: stocked, shades = json.loads(materials or '[]'), json.loads(colors or '{}')
        except ValueError: continue
        host = inventory.setdefault(user_id, {})
        for material in stocked:
            current = host.setdefault(material, {})
            for name, value in (shades.get(material) or {}).items():
                value = value.lower()
                if value in current.values(): continue
                key, n = name, 2
                while key in current: key, n = f'{name}-{n}', n + 1
                current[key] = value
    return inventory

def upgrade():
    op.create_table('host_materials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('material', sa.String(40), nullable=False),
        sa.Column('colors', sa.Text(), nullable=False, server_default='{}'),
        sa.UniqueConstraint('user_id', 'material'))
    op.create_index('ix_host_materials_user_id', 'host_materials', ['user_id'])
    db = op.get_bind()
    rows = db.execute(sa.text('SELECT user_id, materials, material_colors FROM host_printers ORDER BY id')).all()
    table = sa.table('host_materials', sa.column('user_id'), sa.column('material'), sa.column('colors'))
    values = [{'user_id': user, 'material': material, 'colors': json.dumps(colors)} for user, stock in merged_inventory(rows).items() for material, colors in stock.items()]
    if values: op.bulk_insert(table, values)

def downgrade():
    op.drop_index('ix_host_materials_user_id', 'host_materials')
    op.drop_table('host_materials')
