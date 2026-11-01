"""Exact printer capabilities shared by quoting and job assignment.

Stock: each host keeps one material inventory (HostMaterial: {material: {name: hex}}); a printer
offers the materials that are both in that inventory and among its approved capabilities.

Colour identity: hosts stock colours as {material: {name: hex}}. A name is not a colour on its own,
because two printers may stock "orange" in different shades. When every eligible printer offers a
name in one shade, the purchasable key is the plain name ("orange"), exactly as before. When the
shades differ, each one becomes its own option keyed "name~rrggbb" ("orange~e66a3c"), so the
buyer chooses a shade, and only hosts stocking that exact shade can take the job.

Independence: nobody manufactures their own order. A buyer is never offered capacity only their own
printers have, and job_ineligibility() never lets a host see or take a job from their own order.
"""
import json
import math
import re
from sqlalchemy import event, select
from sqlalchemy.orm import Session, object_session
from . import models

SHADE_SEPARATOR = '~'
_CACHE, _INVENTORY, _HOSTS, _SHADES = 'approved_printers', 'host_inventory', 'approved_hosts', 'sized_shades'

def _approved_host_ids(db):
    """Active, approved hosts, whether or not they have printers; loaded once per request."""
    if db.new or db.dirty or db.deleted: db.flush()
    hosts = db.info.get(_HOSTS)
    if hosts is None:
        query = select(models.HostApplication.user_id).join(models.User, models.User.id == models.HostApplication.user_id).where(models.HostApplication.status == 'approved', models.User.active.is_(True), models.User.role == 'host')
        hosts = db.info[_HOSTS] = set(db.scalars(query))
    return hosts

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
    for key in (_CACHE, _INVENTORY, _HOSTS, _SHADES): session.info.pop(key, None)
for _name in ('after_flush', 'after_commit', 'after_rollback', 'after_soft_rollback'):
    event.listen(Session, _name, _forget)
@event.listens_for(Session, 'do_orm_execute')
def _forget_on_write(state):
    # Bulk UPDATE/DELETE statements (host decisions, suspensions) bypass the flush.
    if not state.is_select: _forget(state.session)

def valid_dimensions(value):
    """Three finite, positive sizes in mm (a list or its JSON text), else None."""
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return None
    if not isinstance(value, list) or len(value) != 3 or any(isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d) or d <= 0 for d in value):
        return None
    return value

_SIZE = r'(\d+(?:\.\d+)?)\s*(?:mm)?'
_TEXT_SIZE = re.compile(r'\s*' + _SIZE + r'\s*[x×*]\s*' + _SIZE + r'\s*[x×*]\s*' + _SIZE + r'\s*', re.IGNORECASE)

def line_dimensions(item):
    """Build size of an order line as sold: the CAD dimensions pinned at checkout or, for lines
    ordered before they were pinned, a 'W × D × H mm' size recorded with the line. None if unknown."""
    try:
        pinned = json.loads(item.manufacturing_dimensions)
    except (ValueError, TypeError):
        return None
    if pinned:
        return valid_dimensions(pinned)
    match = _TEXT_SIZE.fullmatch(item.dimensions or '')
    return valid_dimensions([float(v) for v in match.groups()]) if match else None

def fits(printer, dimensions):
    return printer.quantity > 0 and all(a <= b for a, b in zip(sorted(dimensions), sorted([printer.x, printer.y, printer.z])))

def compatible_printers(product, host_id=None):
    db = object_session(product) if product is not None else None
    dimensions = valid_dimensions(product.cad_dimensions) if db is not None else None
    if dimensions is None:
        return []
    return [p for p in _approved_printers(db) if (host_id is None or p.user_id == host_id) and fits(p, dimensions)]

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

def combinations(product, host_id=None, exclude_host=None):
    """{material: {colour key: hex}} for buyers; with host_id, only that host's shades (same keys).
    exclude_host drops shades only that host stocks: a buyer's own printers cannot take their order.
    Keys are worked out over every host, so a shade has the same key whoever is looking."""
    shades = offers(product)
    distinct = {}
    for material, name, value, _ in shades:
        distinct.setdefault((material, name), set()).add(value)
    result = {}
    for material, name, value, owner in shades:
        if host_id is not None and owner != host_id: continue
        if exclude_host is not None and owner == exclude_host: continue
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

def _sized_shades(db, host_id, dimensions):
    """(material, name, hex) a host offers on approved printers that fit this size, or None when
    none fits. Each shade comes from one printer's own stock. Worked out once per request for each
    host and size, so a long job list costs one evaluation per product, not one per job."""
    printers = _approved_printers(db)          # flushes pending changes first, resetting the caches
    cache = db.info.setdefault(_SHADES, {})
    key = (host_id, tuple(dimensions))
    if key not in cache:
        fitting = [p for p in printers if p.user_id == host_id and fits(p, dimensions)]
        cache[key] = {(m, n, v.lower()) for p in fitting for m, colors in printer_stock(p, db).items() for n, v in colors.items()} if fitting else None
    return cache[key]

def job_ineligibility(job, host_id):
    """Why this host cannot take this job now, or None when it can. The one rule behind Available
    Jobs, acceptance and the administrator's view. Each job is one order line, and needs a single
    approved printer that fits the line as sold and offers its exact material and shade.

    Reasons: unavailable (taken, cancelled), own_order (the host is the buyer), host (not an active
    approved host), printer (none fits), material (no fitting printer offers it), color (not that shade).
    Reads current equipment and stock, so changes made after a job was listed are honoured."""
    db = object_session(job)
    order = db.get(models.Order, job.order_id)
    if job.status != 'available' or job.host_id is not None or order is None or order.status == 'cancelled':
        return 'unavailable'
    if order.buyer_id == host_id:
        return 'own_order'
    if host_id not in _approved_host_ids(db):
        return 'host'
    item = job.item
    dimensions = line_dimensions(item)
    if dimensions is None:
        # Lines that recorded no size at all keep using the product's current model.
        listing = db.get(models.Listing, item.listing_id)
        dimensions = valid_dimensions(listing.cad_dimensions) if listing else None
    shades = _sized_shades(db, host_id, dimensions) if dimensions else None
    if shades is None:
        return 'printer'
    if not any(m == item.material for m, _, _ in shades):
        return 'material'
    if not matches(shades, item.material, item.color, item.color_hex):
        return 'color'
    return None
