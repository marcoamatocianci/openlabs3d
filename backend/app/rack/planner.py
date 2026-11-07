"""From a RackConfiguration to a plan: layout, structure, label placement, checks and estimates, in milliseconds.

The plan's spec is the only input to the CAD generator, and its hash is the identity of the rack. Runs in the web
process; contains no CAD.
"""
import math
from shapely.geometry import Point
from . import estimate, labels
from .layout import automatic, check_positions, edge_margin, fits_upright, footprint, height_range, resolve_types
from .profiles import FAMILIES, DEFAULT_PROFILE, LIBRARY_VERSION, OVERRIDE_LIMITS, PROFILES
from .rules import MAX_FOOTPRINT_MM, MAX_TUBES, RULES
from .schema import spec_hash
from .structure import Tube, body_profile, bored, corner_rect, drain_d, inset_at, lightweight, polygons, premium, rings, seat_volume, top_inset

GEOMETRY_VERSION = 4          # the newest design. Each family says which version made it: orders keep what they were built from.
LIGHTWEIGHT_VERSION = 3       # unchanged since version 3, so a Lightweight rack keeps its identity and its cached build
# How far the Premium body goes: (corner radius, softness of the wall).
EDGES = {'sharp': (.55, .45), 'soft': (1.0, 1.0), 'rounded': (1.0, 1.25)}
MAX_NAME_GROWTH = 1.5    # beyond this a longer name is refused, with a suggestion, rather than changing the rack's shape
PLATE_WALL = 2.4        # the Lightweight nameplate's thickness, across its face
PLATE_INSET = .8        # its foot stands this far in from the edge of the frame
PRESETS = [
    {'id': 'microtube', 'name': 'Microtube rack', 'summary': '24 × 1.5 mL', 'tubes': {'micro-1.5-generic': 24}, 'style': 'lightweight'},
    {'id': 'falcon-50', 'name': 'Falcon rack', 'summary': '12 × 50 mL', 'tubes': {'conical-50-generic': 12}, 'style': 'lightweight'},
    {'id': 'mixed-falcon', 'name': 'Mixed rack', 'summary': '15 × 50 mL + 5 × 15 mL', 'tubes': {'conical-50-generic': 15, 'conical-15-generic': 5}, 'style': 'premium'},
]

def catalog():
    return {'schema_version': 1, 'library_version': LIBRARY_VERSION, 'geometry_version': GEOMETRY_VERSION, 'max_tubes': MAX_TUBES,
            'profiles': [p.public() for p in PROFILES.values()], 'families': [{'id': f, 'label': l, 'default': DEFAULT_PROFILE[f]} for f, l in FAMILIES],
            'override_limits': OVERRIDE_LIMITS, 'presets': PRESETS,
            'fonts': [{'id': k, 'label': v['label']} for k, v in labels.FONTS.items()],
            'text': {'min_size_mm': RULES.min_text_size_mm, 'max_size_mm': RULES.max_text_size_mm, 'default_size_mm': labels.DEFAULT_SIZE_MM, 'max_chars': 40},
            'materials': {m: {'density_g_cm3': d} for m, d in estimate.DENSITY_G_CM3.items()}}

def _issue(level, code, message, fix='', **extra): return dict(level=level, code=code, message=message, fix=fix, **extra)

def _cog_height(types): return max(t.floor_z + t.length / 2 for t in types.values())

def plan(config, volumes=None, rates=None):
    """volumes: nominal printers as [(x, y, z)] mm able to take this finish, or None when unknown (then only the absolute
    size limit applies). A chosen layout.envelope narrows the search and the check to that one printer size."""
    issues = []
    envelope = config.layout.envelope
    chosen = [(envelope.x, envelope.y, envelope.z)] if envelope else None
    label_text = (config.label.text if config.label else '').strip()
    labelled = bool(label_text)
    style = config.style
    types = resolve_types(config, issues)
    if config.layout.mode == 'auto': counts = {t.profile_id: t.quantity for t in config.tubes if t.quantity > 0 and t.profile_id in types}
    else:
        counts = {}
        for p in config.layout.positions: counts[p.profile_id] = counts.get(p.profile_id, 0) + 1
    total = sum(counts.values())
    if total == 0 and not any(i['level'] == 'error' for i in issues):
        issues.append(_issue('error', 'empty', 'This rack holds no tubes yet.', 'Add at least one tube.'))
    if total > MAX_TUBES:
        issues.append(_issue('error', 'too_many', f'A rack can hold up to {MAX_TUBES} tubes; this one asks for {total}.', 'Reduce the quantities, or order two racks.'))
    if any(i['level'] == 'error' for i in issues):
        return {'ok': False, 'issues': issues, 'spec': None, 'hash': None, 'tubes': [], 'bands': [], 'dims': None, 'metrics': None, 'fit': None, 'summary': _summary(counts), 'height': None, 'layouts': []}

    limits = height_range(types)
    if config.height_mm is not None:
        low, _, high = limits
        if config.height_mm < low - .01:
            issues.append(_issue('error', 'height_too_low', f'This rack needs at least {low:g} mm of height to hold the selected tubes securely.', f'Use {low:g} mm or more.', action={'kind': 'height', 'value': low, 'label': f'Use {low:g} mm'}))
        elif config.height_mm > high + .01:
            issues.append(_issue('error', 'height_too_high', f'This rack can be at most {high:g} mm tall: any taller and the selected tubes would sit too deep to take hold of.', f'Use {high:g} mm or less.', action={'kind': 'height', 'value': high, 'label': f'Use {high:g} mm'}))
    # Reserve room the layout must leave for a label, then find the tubes' positions.
    label_position = config.label.position if labelled else None
    cap_guess = labels.text_size('H', config.label.font, config.label.size_mm or labels.DEFAULT_SIZE_MM)[1] if labelled else 0
    reserve = {'front': 0.0, 'back': 0.0, 'left': 0.0, 'right': 0.0}
    if labelled and style == 'lightweight' and label_position != 'top': reserve[label_position] = _plate_depth(cap_guess)
    if labelled and style == 'premium' and label_position == 'top': reserve['front'] = cap_guess + 6
    cog = _cog_height(types)
    stable = 2 * math.tan(math.radians(RULES.tip_angle_deg)) * cog
    reserve_xy = (reserve['left'] + reserve['right'], reserve['front'] + reserve['back'])
    margin = config.layout.outer_margin_mm
    options, compact_fits = [], False
    # A name should not be refused for a few millimetres: the rack may grow a little to carry it, on the side it sits on.
    name_w = _name_width(label_text, config.label.font, style) if labelled and label_position != 'top' else 0.0
    if config.layout.mode == 'auto':
        wanted = (max(stable, name_w if label_position in ('front', 'back') else 0), max(stable, name_w if label_position in ('left', 'right') else 0))
        placed = automatic(types, counts, config.layout, style, chosen or volumes, wanted, reserve_xy)
        fitting = _layouts_that_fit(config, types, counts, style, chosen or volumes, wanted, reserve_xy, placed)
        options = fitting if len(fitting) >= 2 else []
        compact_fits = any(o['id'] == 'compact' for o in fitting)
    else:
        placed = [(types[p.profile_id], p.x, p.y) for p in config.layout.positions]
    issues.extend(check_positions(placed, config.layout.spacing, style))
    x0, y0, x1, y1 = footprint(placed, style, margin)
    x0 -= reserve['left']; x1 += reserve['right']; y0 -= reserve['front']; y1 += reserve['back']
    along_name = 'x' if label_position in ('front', 'back') else 'y'
    for low, high, name in ((x0, x1, 'x'), (y0, y1, 'y')):
        need = stable
        if name_w and name == along_name and name_w <= (high - low) * MAX_NAME_GROWTH: need = max(need, name_w)
        short = need - (high - low)
        if short > 0:
            if name == 'x': x0, x1 = x0 - short / 2, x1 + short / 2
            else: y0, y1 = y0 - short / 2, y1 + short / 2
    # Everything from here on is centred on the rack; the offset maps it back to a manual layout's coordinates.
    cx, cy = round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)
    rect = tuple(round(v, 2) for v in (x0 - cx, y0 - cy, x1 - cx, y1 - cy))
    tubes = [Tube(t.profile_id, round(x - cx, 2), round(y - cy, 2), t.bore_d, t.cap_d, t.deck, t.deck - (t.natural_deck - t.floor_z) if style == 'premium' else t.floor_z, t.cone, t.tip_d, t.length) for t, x, y in placed]

    if style == 'premium' and config.corner_radius_mm is not None:
        allowed = _corner_limit(tubes, rect)
        if config.corner_radius_mm > allowed:
            issues.append(_issue('warning', 'fillet_clamped', f'A corner radius of {config.corner_radius_mm:g} mm would cut into the tube walls; using {allowed:g} mm.', 'This is applied automatically.'))
    # Short-tube handling can change decks, so the structure comes before the label that sits on it.
    if style == 'premium':
        structure = premium(tubes, rect, EDGES[config.edge], config.corner_radius_mm, margin=margin)
    else:
        plate = _plate(config, label_text, rect, tubes, issues) if labelled else None
        structure = lightweight(tubes, rect, plate)
    height = max([z1 for _, z1, _ in structure.filled] + [t.deck for t in structure.tubes])
    label = _place_label(config, label_text, structure, reserve, issues) if labelled else None

    # Checks
    dims = [round(rect[2] - rect[0], 2), round(rect[3] - rect[1], 2), round(height, 2)]
    if label and label.get('flat'):      # the flat for a name takes that much off the rack's depth on its side
        dims[0 if label['position'] in ('left', 'right') else 1] = round(dims[0 if label['position'] in ('left', 'right') else 1] - label['flat'], 2)
    fit = _fit(dims, volumes, issues, chosen)
    if fit['state'] == 'too_large':
        # Not only what is wrong, but the one change most likely to put it right.
        for issue in issues:
            if issue['code'] == 'too_large' and compact_fits and config.layout.preference != 'compact':
                issue['action'] = {'kind': 'layout', 'value': 'compact', 'label': 'Try a more compact layout'}
    base = structure.filled[0][2]
    if len(polygons(base)) != 1:
        issues.append(_issue('error', 'disconnected', 'The base would print as separate pieces.', 'Move the tubes closer together, or use Auto-arrange.'))
    if style == 'premium':
        # Below its belly the wall leans out, within the printable limit by construction; above it every band sits inside the one below.
        belly = structure.terraces[0]['profile']['belly']
        for (z0, _, lower), (z1, _, upper) in zip(structure.filled, structure.filled[1:]):
            if z0 >= belly and bored(structure, z1, upper).difference(lower.buffer(.01)).area > 1.0:
                issues.append(_issue('error', 'floating', f'Material at {z0:.0f} mm would have nothing under it.', 'Use Auto-arrange.'))
        walls = []
        for t in structure.tubes:
            plan_there = next(p for z0, z1, p in structure.filled if z0 <= t.deck - .01 < z1)
            walls.append(plan_there.boundary.distance(Point(t.x, t.y)) - t.radius)
    else:
        walls = structure.walls
    min_wall = round(min(walls), 2) if walls else None
    if min_wall is not None and min_wall < RULES.min_wall_mm - .01:
        issues.append(_issue('error', 'thin_wall', f'The thinnest outer wall would be {min_wall:.1f} mm; at least {RULES.min_wall_mm:.1f} mm is needed.', 'Move the tube inward or add margin.'))
    contact = base.area
    if contact < RULES.min_bed_contact_mm2:
        issues.append(_issue('warning', 'bed_contact', f'Only {contact:.0f} mm² touches the bed; the print may need a brim.', 'A larger footprint improves adhesion.'))
    half = min(dims[0], dims[1]) / 2
    tip_angle = round(math.degrees(math.atan2(half, cog)), 1)

    spec = _spec(config, structure, label, dims)
    volume, area = _volume_area(structure, label)
    metrics = {'volume_mm3': round(volume), 'area_mm2': round(area), 'bed_contact_mm2': round(contact), 'tip_angle_deg': tip_angle, 'min_wall_mm': min_wall,
               'holes': len(tubes), 'basis': 'plan'}
    bands = [{'z0': z0, 'z1': z1, 'polys': rings(bored(structure, z0, poly))} for z0, z1, poly in structure.filled]
    funnels = [{'at': f['at'], 'bands': [{'z0': z0, 'z1': z1, 'polys': rings(poly)} for z0, z1, poly in f['bands']]} for f in structure.funnels]
    margins = {pid: round(edge_margin(t, style, margin), 2) for pid, t in types.items()}
    tube_data = [{'i': i, 'profile_id': t.profile_id, 'x': t.x, 'y': t.y, 'bore_d': t.bore_d, 'cap_d': t.cap_d, 'deck': t.deck, 'floor': t.floor, 'length': t.length} for i, t in enumerate(structure.tubes)]
    ok = not any(i['level'] == 'error' for i in issues)
    return {'ok': ok, 'issues': issues, 'spec': spec, 'hash': spec_hash(spec) if ok else None, 'dims': dims, 'tubes': tube_data, 'bands': bands, 'funnels': funnels, 'offset': [cx, cy],
            'footprint': list(rect), 'label': label, 'metrics': metrics, 'estimates': estimates(volume, area, len(tubes), labelled, style, rates), 'fit': fit, 'summary': _summary(counts),
            'terraces': [{'rect': t['rect'], 'z': t['z'], 'corners': t['corners']} for t in structure.terraces], 'corner_r': structure.corner_r, 'top_fillet': structure.top_fillet,
            'height': {'min': limits[0], 'recommended': limits[1], 'max': limits[2], 'value': dims[2], 'custom': config.height_mm is not None}, 'layouts': options, 'margins': margins}

def _layouts_that_fit(config, types, counts, style, volumes, wanted, reserve, placed):
    """Each preference that gives a rack which fits and differs from the others in a way a person would notice. Nothing is
    offered once the buyer has fixed the layout's shape or rows themselves."""
    layout = config.layout
    if layout.columns or layout.orientation != 'auto' or layout.arrangement != 'auto' or sum(counts.values()) < 2: return []
    height = max(t.deck for t in types.values())
    found = []
    for preference in ('balanced', 'compact', 'wide'):
        tubes = placed if preference == layout.preference else automatic(types, counts, layout.model_copy(update={'preference': preference}), style, volumes, wanted, reserve)
        x0, y0, x1, y1 = footprint(tubes, style, layout.outer_margin_mm)
        w, d = max(x1 - x0 + reserve[0], wanted[0]), max(y1 - y0 + reserve[1], wanted[1])
        fits = fits_upright(w, d, height, volumes) if volumes else w <= MAX_FOOTPRINT_MM and d <= MAX_FOOTPRINT_MM
        if not fits: continue
        if any(abs(w - o['dims'][0]) < .05 * o['dims'][0] and abs(d - o['dims'][1]) < .05 * o['dims'][1] for o in found): continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        found.append({'id': preference, 'dims': [round(w, 1), round(d, 1)], 'tubes': [[round(x - cx, 1), round(y - cy, 1), t.bore_d] for t, x, y in tubes]})
    for option in found: option['selected'] = option['id'] == layout.preference
    if found and not any(o['selected'] for o in found): found[0]['selected'] = True
    return found

def _name_width(text, font, style):
    """The side a name needs at the smallest printable letters. Corners are estimated: their radius depends on the rack."""
    width = labels.text_size(text, font, labels.min_size(font))[0]
    return round(width + (18 if style == 'lightweight' else 2 * 24), 1)

def _plate_depth(cap):
    """How much depth a leaning nameplate adds to the footprint, for letters of this height."""
    return round(PLATE_INSET + _plate_height(cap) * math.tan(math.radians(RULES.label_rake_deg)) + PLATE_WALL / math.cos(math.radians(RULES.label_rake_deg)) + .6, 2)

def _plate_height(cap): return round(max(RULES.base_mm + 11.0, RULES.base_mm + (cap + 7) * math.cos(math.radians(RULES.label_rake_deg))), 2)

def estimates(volume, area, holes, labelled, style, rates=None):
    rates = rates or estimate.DEFAULT_RATES
    base, factors = estimate.price_rules(volume, area, holes, labelled, style, rates)
    return {'pricing_status': 'validated' if rates.commercially_validated else 'prototype', 'base_cents': base, 'materials': {m: {'grams': round(estimate.grams(volume, area, m), 1), 'unit_price_cents': estimate.material_price(base, f), 'factor_bps': f} for m, f in factors.items()}}

def _summary(counts):
    order = {f: n for n, (f, _) in enumerate(FAMILIES)}
    parts = sorted(counts.items(), key=lambda kv: order.get(PROFILES[kv[0]].family, 9) if kv[0] in PROFILES else 9)
    return [{'profile_id': pid, 'quantity': n, 'label': PROFILES[pid].label if pid in PROFILES else pid, 'nominal_ml': PROFILES[pid].nominal_capacity_ml if pid in PROFILES else None} for pid, n in parts]

def summary_text(plan_summary):
    return ' + '.join(f"{p['quantity']} × {p['nominal_ml']:g} mL" for p in plan_summary)

def _corner_limit(tubes, rect):
    """Largest outer corner radius that keeps the wall around every bore."""
    best = 40.0
    x0, y0, x1, y1 = rect
    for t in tubes:
        dx = min(t.x - x0, x1 - t.x); dy = min(t.y - y0, y1 - t.y)
        reach = t.radius + RULES.min_wall_mm + .5 + top_inset(body_profile(t.deck))
        if dx >= reach and dy >= reach:
            # From the corner circle: R - sqrt((R-dx)^2 + (R-dy)^2) >= reach, solved for R by scanning.
            limit = 0.0
            for tenth in range(0, 401):
                r = tenth / 10
                inside = dx >= r or dy >= r
                if inside or r - math.hypot(r - dx, r - dy) >= reach: limit = r
                else: break
            best = min(best, limit)
    return round(best, 1)

def _plate(config, text, rect, tubes, issues):
    """A Lightweight rack has no solid face, so a label gets a slim nameplate along one edge: it leans back to read from
    above, carries only its own letters, and stands on the frame. It is never wider than the name needs."""
    label = config.label
    if label.position == 'top': return None
    x0, y0, x1, y1 = rect
    along_x = label.position in ('front', 'back')
    length = (x1 - x0) if along_x else (y1 - y0)
    room = length - 18
    size, status = labels.fit(text, label.font, label.size_mm, room, 22)
    width, cap = labels.text_size(text, label.font, size)
    half = min((width + 12) / 2, length / 2 - 3)
    height = _plate_height(cap)
    rake = math.radians(RULES.label_rake_deg)
    run = height * math.tan(rake)
    thick = round(PLATE_WALL / math.cos(rake), 2)
    outer = {'front': y0, 'back': y1, 'left': x0, 'right': x1}[label.position]
    sign = -1 if label.position in ('front', 'left') else 1
    face = round(outer - sign * PLATE_INSET, 2)
    foot_low, foot_high = sorted((outer, face - sign * (thick + 1.0)))
    foot = (-half, foot_low, half, foot_high) if along_x else (foot_low, -half, foot_high, half)
    return {'position': label.position, 's0': round(-half, 2), 's1': round(half, 2), 'face': face, 'sign': sign, 'along': 'x' if along_x else 'y', 'height': height, 'run': round(run, 2), 'thick': thick,
            'foot': tuple(round(v, 2) for v in foot), 'size': size, 'status': status}

def _place_label(config, text, structure, reserve, issues):
    label = config.label
    x0, y0, x1, y1 = structure.rect
    position = label.position
    alternatives = [p for p in ('front', 'back', 'left', 'right') if p != position]
    def refuse(code, message, fix): issues.append(_issue('error', code, message, fix)); return None
    rake, panel = 0.0, None
    if structure.style == 'lightweight':
        if position == 'top':
            return refuse('label_position', 'A Lightweight rack has no top surface to carry a label.', 'Choose the front, back or a side, or switch to Premium.')
        plate = structure.plate
        size, status = plate['size'], plate['status']
        along = (x1 - x0) if position in ('front', 'back') else (y1 - y0)
        room = along - 18
        rake = RULES.label_rake_deg
        cz = (RULES.base_mm + plate['height']) / 2
        face = plate['face'] - plate['sign'] * cz * math.tan(math.radians(rake))
    else:
        body = structure.terraces[0]
        lowest, profile = body['z'], body['profile']
        along = (x1 - x0) if position in ('front', 'back', 'top') else (y1 - y0)
        # The name goes across the straight part of that side, and a little way into the corners, where the flat fades out.
        pair = {'front': (0, 1), 'back': (2, 3), 'left': (0, 3), 'right': (1, 2), 'top': (0, 1)}[position]
        room = along - body['corners'][pair[0]] - body['corners'][pair[1]] + 6 if position != 'top' else along - 2 * max(body['corners']) - 6
        if position == 'top':
            height_room = reserve['front'] - 2
            cz = lowest
        else:
            cz = profile['belly']
            # The tallest band of wall around the belly that a flat of the deepest allowed depth reaches.
            reach_up = reach_down = 0.0
            while cz + reach_up < lowest and inset_at(profile, cz + reach_up) < RULES.label_flat_max_mm: reach_up += .25
            while cz - reach_down > 0 and inset_at(profile, cz - reach_down) < RULES.label_flat_max_mm: reach_down += .25
            height_room = 2 * min(reach_up, reach_down) - 4
        size, status = labels.fit(text, label.font, label.size_mm, room, height_room)
    width, cap = labels.text_size(text, label.font, size)
    if status == 'too_long':
        keep = labels.characters_that_fit(text, label.font, size, room)
        return refuse('label_too_long', f'"{text}" is too long for this side of the rack: {keep} of {len(text)} characters fit at the smallest printable size.', f'Shorten the name to {keep} characters, place it on another side ({", ".join(alternatives[:2])}), or add tubes to widen the rack.')
    if status == 'too_short':
        return refuse('label_too_tall', 'This side of the rack is not tall enough for the smallest printable letters.', 'Place the name on another side.')
    if status == 'reduced':
        issues.append(_issue('warning', 'label_resized', f'The name was reduced to {size:g} mm to fit this side of the rack.', 'Shorten it to keep the larger size.'))
    stroke = labels.FONTS[label.font]['stroke'] * size
    if stroke < RULES.min_text_stroke_mm - .01:
        issues.append(_issue('warning', 'label_strokes', f'The thinnest strokes of this font at {size:g} mm are about {stroke:.1f} mm, under the {RULES.min_text_stroke_mm} mm a 0.4 mm nozzle draws reliably.', 'Use a larger size or the Sans font.'))
    depth = RULES.engrave_depth_mm if label.style == 'engraved' else RULES.emboss_height_mm
    out = {'text': text, 'font': label.font, 'size': size, 'style': label.style, 'position': position, 'depth': depth, 'width': round(width, 2), 'cap': round(cap, 2), 'rake': rake}
    if structure.style == 'premium' and position != 'top':
        # A soft flat, just deep enough to take the letters: the plane meets the convex wall in a curve, so the area for the
        # name is part of the body's shape, not a plate set into it. Its depth follows the size of the letters.
        half = cap / 2 + 2.0
        flat = round(max(.5, inset_at(profile, min(cz + half, lowest)), inset_at(profile, max(cz - half, 0.0))), 2)
        out['flat'] = flat
        if position == 'front': out.update(anchor=[0.0, round(y0 + flat, 3), round(cz, 2)])
        elif position == 'back': out.update(anchor=[0.0, round(y1 - flat, 3), round(cz, 2)])
        elif position == 'left': out.update(anchor=[round(x0 + flat, 3), 0.0, round(cz, 2)])
        else: out.update(anchor=[round(x1 - flat, 3), 0.0, round(cz, 2)])
    elif structure.style == 'lightweight':
        if position in ('front', 'back'): out.update(anchor=[0.0, round(face, 3), round(cz, 2)])
        else: out.update(anchor=[round(face, 3), 0.0, round(cz, 2)])
    else: out.update(anchor=[0.0, round(y0 + reserve['front'] / 2 + 1, 2), lowest])
    return out

def _fit(dims, volumes, issues, chosen=None):
    """Whether a printer can hold this rack upright. The state says which limit applied, and exceeded names the sides."""
    width, depth, height = dims
    if width > MAX_FOOTPRINT_MM or depth > MAX_FOOTPRINT_MM:
        issues.append(_issue('error', 'too_large', f'This rack would measure {width:.0f} × {depth:.0f} mm, beyond the {MAX_FOOTPRINT_MM:.0f} mm the configurator generates.', 'Reduce the number of tubes.'))
    if volumes is None and not chosen: return {'state': 'unknown', 'exceeded': []}
    if not volumes and not chosen:
        return {'state': 'no_printers', 'exceeded': [], 'limit': None}
    within = chosen or volumes
    if fits_upright(width, depth, height, within):
        state = {'state': 'fits', 'exceeded': [], 'printers': sum(1 for v in within if fits_upright(width, depth, height, [v])), 'of': len(within)}
        if chosen: state['limit'] = _usable(chosen[0], width, depth)[:3]
        return state
    largest = max(within, key=lambda v: (v[0] * v[1], v[2]))
    limit_w, limit_d, limit_h = _usable(largest, width, depth)
    exceeded = [name for name, value, limit in (('width', width, limit_w), ('depth', depth, limit_d), ('height', height, limit_h)) if value > limit]
    adjective = {'width': 'wide', 'depth': 'deep', 'height': 'tall'}
    too = f'too {adjective[exceeded[0]]}' if len(exceeded) == 1 else 'too large'
    where = 'the printing area you chose' if chosen else 'the currently available printers'
    measure = ', '.join(f'{value:.0f} mm {name} against {limit:.0f} mm available' for name, value, limit in (('width', width, limit_w), ('depth', depth, limit_d), ('height', height, limit_h)) if name in exceeded)
    issues.append(_issue('error', 'too_large', f'This rack is {too} for {where}.', ('Try a larger printing area, fewer tubes or a more compact arrangement.' if chosen else 'Try reducing the number of tubes or using a more compact arrangement.') + (f' ({measure}.)' if measure else '')))
    return {'state': 'too_large', 'exceeded': exceeded, 'limit': [limit_w, limit_d, limit_h]}

def _usable(volume, width, depth):
    """A build volume less its margins, turned the way this rack sits best."""
    x, y, z = volume[0] - RULES.printer_margin_mm * 2, volume[1] - RULES.printer_margin_mm * 2, volume[2] - RULES.printer_margin_z_mm
    if (width > depth) != (x > y): x, y = y, x
    return [round(x, 1), round(y, 1), round(z, 1)]

def _lead_in(t, structure):
    """A soft entry to each bore, as generous as the wall to its nearest neighbour allows, and always ending on flat deck: if
    it ran into the curve at the edge of the deck, the two surfaces would meet in a sliver no mesher can close."""
    gap = min((math.hypot(t.x - o.x, t.y - o.y) - t.radius - o.radius for o in structure.tubes if o is not t), default=20.0)
    lead = max(.5, min(2.2, t.radius * .22, (gap - 1.0) / 2))
    if structure.style == 'premium':
        level = next((l for l in structure.terraces if abs(l['z'] - t.deck) < 1e-6), structure.terraces[0])
        deck = corner_rect(tuple(level['rect']), level['corners'], top_inset(level['profile']))
        flat = deck.boundary.distance(Point(t.x, t.y)) - t.radius
        lead = max(.4, min(lead, flat - .6))
    return round(lead, 2)

def _spec(config, structure, label, dims):
    """Everything the CAD generator needs and nothing else. Stored with orders, so an order can always be rebuilt."""
    lightweight_style = structure.style == 'lightweight'
    tubes = []
    for t in sorted(structure.tubes, key=lambda t: (-t.y, t.x, t.profile_id)):
        tubes.append({'profile_id': t.profile_id, 'x': t.x, 'y': t.y, 'bore_d': t.bore_d, 'deck': t.deck, 'floor': round(t.floor, 2), 'tip_d': t.tip_d, 'cone': round(min(t.cone, t.deck - t.floor - 3), 2),
                      'seat': 'tapered', 'drain_d': drain_d(t), 'lead': _lead_in(t, structure)})
    keys = ('text', 'font', 'size', 'style', 'position', 'depth', 'anchor', 'rake', 'flat')
    spec = {'geometry_version': LIGHTWEIGHT_VERSION if lightweight_style else GEOMETRY_VERSION, 'style': structure.style, 'footprint': list(structure.rect), 'dims': dims, 'tubes': tubes, 'label': {k: label.get(k) for k in keys} if label else None,
            'entry_chamfer': RULES.entry_chamfer_mm}
    if lightweight_style:
        spec['base'] = {'z1': RULES.base_mm, 'polys': rings(structure.base, .03)}
        spec['funnels'] = [{'shape': f['shape'], 'at': f['at']} for f in structure.funnels]
        spec['links'] = [{k: l[k] for k in ('kind', 'x', 'y', 'angle', 'thick', 'profile')} if l.get('kind') == 'bridge' else {'kind': 'wall', 'z0': l['z0'], 'z1': l['z1'], 'polys': rings(l['shape'], .03), 'window': l['window']} for l in structure.links]
        plate = structure.plate
        spec['plate'] = {k: plate[k] for k in ('position', 's0', 's1', 'face', 'sign', 'height', 'run', 'thick')} if plate else None
    else:
        spec['terraces'] = [{'rect': t['rect'], 'z': t['z'], 'corners': t['corners'], 'profile': t['profile']} for t in structure.terraces]
    return spec

def _volume_area(structure, label):
    """Plan-level volume and surface from the bands, plus what tapered seats leave. Refined by the CAD build."""
    volume = area = 0.0
    previous = None
    for z0, z1, poly in structure.filled:
        section = bored(structure, z0, poly, 16)
        height = z1 - z0
        volume += section.area * height
        area += section.length * height
        area += section.area if previous is None else abs(previous - section.area)
        previous = section.area
    area += previous or 0.0
    if structure.style == 'premium':
        for t in structure.tubes: volume += seat_volume(t)
        return max(volume, 1.0), area
    # Lightweight: separate pieces, each counted on its own. Their faces where they meet are not surface, which about cancels
    # the funnels' bottoms and tops counted below.
    volume = area = 0.0
    for z0, z1, poly in structure.filled:
        volume += poly.area * (z1 - z0); area += poly.length * (z1 - z0)
    area += 2 * structure.filled[0][2].area
    volume -= sum(l.get('embedded', 0) for l in structure.links)
    for funnel in structure.funnels:
        one_volume = sum(poly.area * (z1 - z0) for z0, z1, poly in funnel['bands'])
        one_area = sum(poly.length * (z1 - z0) for z0, z1, poly in funnel['bands'])
        volume += one_volume * len(funnel['at']); area += one_area * len(funnel['at'])
    return max(volume, 1.0), area
