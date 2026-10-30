"""Exact printer capabilities shared by quoting and job assignment."""
import json
import math
from sqlalchemy import select
from sqlalchemy.orm import object_session
from . import models

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
    query = select(models.HostPrinter).join(models.HostApplication, models.HostApplication.user_id == models.HostPrinter.user_id).join(models.User, models.User.id == models.HostPrinter.user_id).where(models.HostApplication.status == 'approved', models.User.active.is_(True), models.User.role == 'host')
    if host_id is not None:
        query = query.where(models.HostPrinter.user_id == host_id)
    return [p for p in db.scalars(query) if p.quantity > 0 and all(a <= b for a, b in zip(sorted(dimensions), sorted([p.x, p.y, p.z])))]

def combinations(product, host_id=None):
    result = {}
    for printer in compatible_printers(product, host_id):
        # Stocked by the host and within the printer's administrator-approved capabilities.
        materials = set(json.loads(printer.materials)) & set(json.loads(printer.capabilities or '[]'))
        for material, colors in json.loads(printer.material_colors or '{}').items():
            if material in materials:
                result.setdefault(material, {}).update(colors)
    return result

def supports(product, material, color, host_id=None):
    return color in combinations(product, host_id).get(material, {})
