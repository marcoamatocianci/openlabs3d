"""Exact printer capabilities shared by quoting and job assignment.

Stock: each host keeps one material inventory (HostMaterial: {material: {name: hex}}); a printer
offers the materials that are both in that inventory and among its approved capabilities.

Colour identity: hosts stock colours as {material: {name: hex}}. A name is not a colour on its own,
because two printers may stock "orange" in different shades. When every eligible printer offers a
name in one shade, the purchasable key is the plain name ("orange"), exactly as before. When the
shades differ, each one becomes its own option keyed "name~rrggbb" ("orange~e66a3c"), so the
buyer chooses a shade, and only hosts stocking that exact shade can take the job.
"""
import json
import math
from sqlalchemy import event, select
from sqlalchemy.orm import Session, object_session
from . import models

SHADE_SEPARATOR = '~'
_CACHE, _INVENTORY = 'approved_printers', 'host_inventory'

def _approved_printers(db):
    """Printers of active, approved hosts, loaded once per request (database session)."""
    # Mirror autoflush: pending changes must be visible, and flushing clears the cache below.
    if db.new or db.dirty or db.deleted: db.flush()
    printers = db.info.get(_CACHE)
    if printers is None:
        query = select(models.HostPrinter).join(models.HostApplication, models.HostApplication.user_id == models.HostPrinter.user_id).join(models.User, models.User.id == models.HostPrinter.user_id).where(models.HostApplication.status == 'approved', models.User.active.is_(True), models.User.role == 'host').order_by(models.HostPrinter.id)
        printers = db.info[_CACHE] = list(db.scalars(query))
    return printers

def _inventory(db):
    """{host id: {material: {name: hex}}}, loaded once per request like the printers."""
    if db.new or db.dirty or db.deleted: db.flush()
    inventory = db.info.get(_INVENTORY)
    if inventory is None:
        inventory = {}
        for row in db.scalars(select(models.HostMaterial).order_by(models.HostMaterial.id)):
            inventory.setdefault(row.user_id, {})[row.material] = json.loads(row.colors or '{}')
        db.info[_INVENTORY] = inventory
    return inventory

def host_inventory(db, user_id):
    return _inventory(db).get(user_id, {})

def printer_stock(printer, db=None):
    """What this printer can offer: the host's inventory limited to the printer's approved materials."""
    db = db or object_session(printer)
    capabilities = set(json.loads(printer.capabilities or '[]'))
    return {m: colors for m, colors in host_inventory(db, printer.user_id).items() if m in capabilities} if db else {}

def set_host_inventory(db, user_id, material_colors):
    """Replace a host's inventory: {material: {name: hex}} (an empty dict keeps the material)."""
    from sqlalchemy import delete
    db.execute(delete(models.HostMaterial).where(models.HostMaterial.user_id == user_id))
    db.add_all(models.HostMaterial(user_id=user_id, material=m, colors=json.dumps({n: h.lower() for n, h in c.items()})) for m, c in material_colors.items())
    db.flush()

def _forget(session, *_):
    session.info.pop(_CACHE, None); session.info.pop(_INVENTORY, None)
for _name in ('after_flush', 'after_commit', 'after_rollback', 'after_soft_rollback'):
    event.listen(Session, _name, _forget)
@event.listens_for(Session, 'do_orm_execute')
def _forget_on_write(state):
    # Bulk UPDATE/DELETE statements (host decisions, suspensions) bypass the flush.
    if not state.is_select: _forget(state.session)

def compatible_printers(product, host_id=None):
    db = object_session(product) if product is not None else None
    if db is None:
        return []
    try:
        dimensions = json.loads(product.cad_dimensions)
        if not isinstance(dimensions, list) or len(dimensions) != 3 or any(isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d) or d <= 0 for d in dimensions):
            return []
    except (ValueError, TypeError):
        return []
    return [p for p in _approved_printers(db) if (host_id is None or p.user_id == host_id) and p.quantity > 0 and all(a <= b for a, b in zip(sorted(dimensions), sorted([p.x, p.y, p.z])))]

def offers(product, host_id=None):
    """Every stocked shade that can make this product: (material, colour name, hex, host id)."""
    result, seen = [], set()
    for printer in compatible_printers(product, host_id):
        # In the host's inventory and within this printer's administrator-approved capabilities.
        for material, colors in printer_stock(printer).items():
            for name, value in colors.items():
                shade = (material, name, value.lower(), printer.user_id)
                if shade not in seen: seen.add(shade); result.append(shade)
    return result

def split_color(key):
    """'orange~e66a3c' -> ('orange', '#e66a3c'); 'orange' -> ('orange', '')."""
    name, _, shade = (key or '').partition(SHADE_SEPARATOR)
    return name, '#' + shade.lower() if shade else ''

def combinations(product, host_id=None):
    """{material: {colour key: hex}} for buyers; with host_id, only that host's shades (same keys)."""
    shades = offers(product)
    distinct = {}
    for material, name, value, _ in shades:
        distinct.setdefault((material, name), set()).add(value)
    result = {}
    for material, name, value, owner in shades:
        if host_id is not None and owner != host_id: continue
        key = name if len(distinct[(material, name)]) == 1 else f'{name}{SHADE_SEPARATOR}{value[1:]}'
        result.setdefault(material, {})[key] = value
    return result

def host_shades(product, host_id):
    """The (material, name, hex) shades one host can make this product in."""
    return {(material, name, value) for material, name, value, _ in offers(product, host_id)}

def matches(shades, material, color, color_hex=''):
    """Whether a line can be made from these shades. Lines with a recorded shade (orders placed
    since colour snapshots) need that exact shade; older lines match on material and name."""
    name, key_shade = split_color(color)
    wanted = (color_hex or key_shade).lower()
    return any(m == material and n == name and (not wanted or v == wanted) for m, n, v in shades)

def supports(product, material, color, host_id=None, color_hex=''):
    return matches(host_shades(product, host_id), material, color, color_hex)
