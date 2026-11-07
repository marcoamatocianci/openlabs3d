"""Where the tubes go. Deterministic: the same types, counts and limits always give the same layout.

Automatic layouts flow tubes into rows (tall ones at the back, so caps stay reachable) and let each row settle as far
forward as the real distance rules allow, so rows of different tubes nest instead of sitting on a uniform grid. Several
widths and arrangements are evaluated and the best one that fits a printer wins. Manual layouts are only checked.
"""
import math
from dataclasses import dataclass
from functools import lru_cache
from .profiles import OVERRIDE_LIMITS, PROFILES
from .rules import MAX_FOOTPRINT_MM, RULES
from .structure import body_profile, terrace_profile, top_inset

@dataclass(frozen=True, eq=False)     # compared by identity: the layout search hashes these thousands of times per plan
class TubeType:
    """A profile with this configuration's clearance and overrides applied, placed in this design style."""
    profile_id: str
    label: str
    body_d: float
    bore_d: float
    cap_d: float
    length: float
    cone: float
    tip_d: float
    separation: float
    floor_z: float
    natural_deck: float       # floor plus the held share of the length
    depth_low: float = 0.0    # how deep this tube may be held at the lowest rack, recommended, and highest
    depth_recommended: float = 0.0
    depth_high: float = 0.0
    deck: float = 0.0         # after similar heights are merged
    base_deck: float = 0.0    # the lowest deck in this rack: the body's own height

def _round(value, step=.1): return round(round(value / step) * step, 4)

def held_depth(profile, values):
    """How deep a Premium rack holds a tube: its cone, then enough straight wall to keep it upright, and never so deep that
    fingers cannot reach it. Depth beyond that is only height and plastic, so this is what makes a Premium rack low."""
    length, body = values['overall_length_mm'], values['body_diameter_mm']
    return min(profile.cone_length_mm + max(RULES.grip_share * body, RULES.grip_min_mm), length * (1 - RULES.exposed_share))

def depth_limits(profile, values, style):
    """(lowest, recommended, highest) depth at which this tube may be held. At the lowest, its cone is seated and a real length
    of straight wall holds it upright; a tube too short to have that is at least held to the top of its cone, where it reaches
    its full width. At the highest, there is still enough tube above the rack to take hold of."""
    length, body, cone = values['overall_length_mm'], values['body_diameter_mm'], profile.cone_length_mm
    recommended = held_depth(profile, values) if style == 'premium' else profile.insertion_fraction * length
    low = cone + max(RULES.low_grip_share * body, RULES.low_grip_min_mm)
    if low > length * (1 - RULES.exposed_share): low = cone
    high = length - max(RULES.high_exposed_share * length, RULES.high_exposed_min_mm)
    return min(low, recommended), recommended, max(high, recommended)

def _depth_at(limits, s):
    low, recommended, high = limits
    return recommended + (recommended - low) * s if s < 0 else recommended + (high - recommended) * s

def _support_for(height, floor, limits):
    """The one setting, from -1 (lowest) through 0 (recommended) to 1 (highest), that makes the tallest tube reach this height.
    Every tube moves together within its own limits, so a mixed rack keeps its proportions."""
    tallest = lambda s: max(floor + _depth_at(l, s) for l in limits)
    if height <= tallest(-1): return -1.0
    if height >= tallest(1): return 1.0
    low, high = -1.0, 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if tallest(middle) < height: low = middle
        else: high = middle
    return (low + high) / 2

def height_range(types):
    """(lowest, recommended, highest) height this set of tubes allows, as the rack's decks will round to."""
    if not types: return None
    floor = next(iter(types.values())).floor_z
    recommended = _round(max(floor + t.depth_recommended for t in types.values()), .5)
    low = math.ceil(max(floor + t.depth_low for t in types.values()) * 2) / 2
    high = math.floor(max(floor + t.depth_high for t in types.values()) * 2) / 2
    return min(low, recommended), recommended, max(high, recommended)

def resolve_types(config, issues):
    """{profile id: TubeType} for every profile used; bad overrides become issues."""
    used = {t.profile_id for t in config.tubes if t.quantity > 0} if config.layout.mode == 'auto' else {p.profile_id for p in config.layout.positions}
    floor = RULES.base_mm if config.style == 'lightweight' else RULES.floor_mm
    resolved, limits = {}, {}
    for pid in sorted(used):
        profile = PROFILES.get(pid)
        if profile is None:
            issues.append(dict(level='error', code='unknown_tube', message=f'"{pid}" is not a tube this configurator supports.', fix='Choose a tube from the list.')); continue
        override = config.overrides.get(pid)
        values = {'body_diameter_mm': profile.body_diameter_mm, 'cap_diameter_mm': profile.cap_diameter_mm, 'overall_length_mm': profile.overall_length_mm}
        for key, (low, high) in OVERRIDE_LIMITS.items():
            wanted = getattr(override, key, None) if override else None
            if wanted is None: continue
            base = values[key]
            if not low * base <= wanted <= high * base:
                issues.append(dict(level='error', code='invalid_dimension', message=f'{profile.label}: {key.replace("_mm", "").replace("_", " ")} must be between {low * base:.1f} and {high * base:.1f} mm.', fix='Enter a size within this range, or choose another tube.'))
            else: values[key] = wanted
        if values['cap_diameter_mm'] < values['body_diameter_mm']:
            issues.append(dict(level='error', code='invalid_dimension', message=f'{profile.label}: the cap cannot be narrower than the body.', fix='Check the cap diameter.'))
        limits[pid] = depth_limits(profile, values, config.style)
        resolved[pid] = (profile, values)
    # With no height asked for, every tube sits at its recommended depth; asked for, all of them move together. Out of range is
    # reported by the planner, and the rack is still drawn at the nearest height it can have.
    support = _support_for(config.height_mm, floor, list(limits.values())) if config.height_mm is not None and limits else 0.0
    result = {}
    for pid, (profile, values) in resolved.items():
        clearance = max(.3, profile.recommended_clearance_mm + config.clearance_adjust_mm)
        low, recommended, high = limits[pid]
        result[pid] = TubeType(pid, profile.label, values['body_diameter_mm'], _round(values['body_diameter_mm'] + clearance, .01), values['cap_diameter_mm'],
                               values['overall_length_mm'], profile.cone_length_mm, profile.tip_diameter_mm, profile.minimum_separation_mm, floor, floor + _depth_at(limits[pid], support),
                               depth_low=low, depth_recommended=recommended, depth_high=high)
    return _merge_decks(result, 8.0 if config.style == 'premium' else 4.0)

def _merge_decks(types, within):
    """Heights this close become one deck: a 3 mm step between 15 and 50 mL decks looks like a mistake."""
    ordered = sorted(types.values(), key=lambda t: -t.natural_deck)
    result, group_top = {}, None
    for t in ordered:
        if group_top is None or group_top - t.natural_deck > within: group_top = _round(t.natural_deck, .5)
        result[t.profile_id] = TubeType(**{**t.__dict__, 'deck': group_top})
    lowest = min((t.deck for t in result.values()), default=0.0)
    return {k: TubeType(**{**t.__dict__, 'base_deck': lowest}) for k, t in result.items()}

MAX_WIDTHS = 40
MAX_SPREAD = 1.55       # how much a row of smaller tubes may open up to line up with the rows beside it

def _gap(a, b, spacing):
    gap = max(a.separation, b.separation)
    return {'compact': max(1.5, gap - 1.5), 'standard': gap, 'roomy': gap + 3}[spacing]

def _structure_wall(style, tall=None):
    if style == 'lightweight': return RULES.sleeve_wall_mm
    return RULES.outer_wall_mm + (top_inset(terrace_profile(tall.deck, tall.base_deck)) if tall and tall.deck > tall.base_deck else 0.0)

@lru_cache(maxsize=512)
def pitch(a, b, spacing, style):
    """Centre distance two tubes need, from their bores, their caps and any step between their decks."""
    required = max((a.bore_d + b.bore_d) / 2 + RULES.bore_web_mm, (a.cap_d + b.cap_d) / 2 + _gap(a, b, spacing))
    if a.deck != b.deck:
        tall, short = (a, b) if a.deck > b.deck else (b, a)
        required = max(required, tall.bore_d / 2 + _structure_wall(style, tall) + short.cap_d / 2 + _gap(a, b, spacing))
    return math.ceil(required * 2) / 2      # half millimetres keep drawings and rows tidy

@lru_cache(maxsize=256)
def _premium_reach(t):
    """A Premium tube's distance to the outline of what holds it: flat deck, then the curve of the wall."""
    if t.deck > t.base_deck:      # on a raised level, which itself stands on the deck, inside the body's curve
        return RULES.outer_wall_mm + top_inset(terrace_profile(t.deck, t.base_deck)) + top_inset(body_profile(t.base_deck)) + 1.0
    return RULES.outer_wall_mm + top_inset(body_profile(t.deck))

def edge_margin(t, style, extra=0.0):
    """Distance from a tube's centre to the edge of the rack at its widest."""
    wall = _premium_reach(t) if style == 'premium' else RULES.sleeve_wall_mm + 1.5
    return max(t.bore_d / 2 + wall, t.cap_d / 2) + extra

def footprint(tubes, style, extra=0.0):
    """(x0, y0, x1, y1) around placed tubes [(TubeType, x, y)]."""
    return (min(x - edge_margin(t, style, extra) for t, x, y in tubes), min(y - edge_margin(t, style, extra) for t, x, y in tubes),
            max(x + edge_margin(t, style, extra) for t, x, y in tubes), max(y + edge_margin(t, style, extra) for t, x, y in tubes))

def _rows(sequence, width, mode, spacing, style, extra):
    """Flow a tube sequence into rows no wider than width; 'grouped' keeps each type on its own rows."""
    rows, current, used = [], [], 0.0
    for t in sequence:
        if current:
            step = pitch(current[-1], t, spacing, style)
            over = used + step + edge_margin(t, style, extra) + edge_margin(current[0], style, extra) > width
            if over or (mode == 'grouped' and t.profile_id != current[-1].profile_id):
                rows.append(current); current, used = [t], 0.0
            else: current.append(t); used += step
        else: current, used = [t], 0.0
    if current: rows.append(current)
    return rows

def _settle(row, placed, y, spacing, style):
    """The rearmost y at which this row keeps its distance from what is already placed: rows only move forward, so only
    the nearest ones can set it."""
    recent = placed[-(3 * len(row) + 16):]
    for t, x in row:
        for other, px, py in recent:
            need = pitch(t, other, spacing, style)
            if need > abs(x - px): y = min(y, py - math.sqrt(need * need - (x - px) ** 2))
    return math.floor(y * 2) / 2

def _align(row, positions, placed, rows, index, mode):
    """Rows read as a grid. A short row of the same tube keeps to the columns of the row behind it; a row of a different
    tube spreads to the width of the rack if that needs only a little more spacing, so both edges line up."""
    if not index or mode == 'staggered' or len(row) < 1: return positions
    previous = [(x, t) for t, x, _ in placed[-len(rows[index - 1]):]]
    columns = [x for x, _ in previous]
    if len(row) < len(columns) and {t.profile_id for t in row} == {t.profile_id for _, t in previous}:
        # The middle columns, leaning to the left when the row cannot be exactly centred.
        start = (len(columns) - len(row)) // 2
        return columns[start:start + len(row)]
    if len(row) > 1 and len({t.profile_id for t in row}) == 1:
        low, high = min(x for t, x, _ in placed), max(x for t, x, _ in placed)
        now = positions[-1] - positions[0]
        if now < high - low and (high - low) / now <= MAX_SPREAD:
            step = (high - low) / (len(row) - 1)
            return [low + k * step for k in range(len(row))]
    return positions

def _place(rows, mode, spacing, style):
    """Centre each row and bring it forward until the nearest tube of any earlier row sets the distance."""
    placed, y, shifted = [], 0.0, False
    for index, row in enumerate(rows):
        xs = [0.0]
        for a, b in zip(row, row[1:]): xs.append(xs[-1] + pitch(a, b, spacing, style))
        shift = 0.0
        # Staggered: every other row of one type moves half a pitch and tucks into the row behind it.
        if mode == 'staggered' and index and not shifted and len({t.profile_id for t in row}) == 1 and row[0].profile_id == rows[index - 1][-1].profile_id:
            shift = pitch(row[0], row[0], spacing, style) / 2
        shifted = shift != 0.0
        positions = [x - xs[-1] / 2 + shift for x in xs]
        positions = _align(row, positions, placed, rows, index, mode)
        if placed: y = _settle(list(zip(row, positions)), placed, y, spacing, style)
        placed.extend((t, x, y) for t, x in zip(row, positions))
    return placed

def fits_upright(width, depth, height, volumes):
    """Whether the rack prints upright on any of these (x, y, z) volumes, turned about Z if needed."""
    m, mz = RULES.printer_margin_mm * 2, RULES.printer_margin_z_mm
    return any(height + mz <= z and ((width + m <= x and depth + m <= y) or (depth + m <= x and width + m <= y)) for x, y, z in volumes)

def _layout_cost(rows, placed, w, d, aspect, preference='balanced'):
    """Layout quality in one number, lower is better: the area of the rack, made dearer by what looks or works badly.
    Empty space beside short rows and mixing tubes within a row make it hard to read; a long thin rack is awkward and
    tips more easily; and between equals wider than deep gives a longer front for a name and an easier reach to the back."""
    widths = {}
    for t, x, y in placed: widths.setdefault(y, []).append(x)
    spans = [max(xs) - min(xs) for xs in widths.values()]
    widest = max(spans) or 1.0
    ragged = sum(1 - s / widest for s in spans) / len(spans) if len(spans) > 1 else 0.0
    mixed = sum(1 for row in rows if len({t.profile_id for t in row}) > 1) / len(rows)
    if preference == 'compact': return round(w * d * (1 + max(0.0, aspect - 2.0) * .5) * (1.1 if d > w else 1), 1)
    if preference == 'wide': return round(w * d * (1 + ragged * .45) * (1 + mixed * .35) * (1 + max(0.0, 1.8 - w / d) * .9) * (1 + max(0.0, w / d - 3.2) * .5), 1)
    return round(w * d * (1 + ragged * .45) * (1 + mixed * .35) * (1 + max(0.0, aspect - 1.7) * .6) * (1.1 if d > w else 1), 1)

def automatic(types, counts, layout, style, volumes, min_size=(0.0, 0.0), reserve=(0.0, 0.0)):
    """The best layout of the requested tubes: [(TubeType, x, y)], centred."""
    extra = layout.outer_margin_mm
    preference = layout.preference
    # "Compact" may use the tightest spacing that still clears caps and fingers, unless the buyer set a spacing themselves.
    spacing = 'compact' if preference == 'compact' and layout.spacing == 'standard' else layout.spacing
    sequence = [t for t in sorted(types.values(), key=lambda t: (-t.deck, -t.bore_d, t.profile_id)) for _ in range(counts.get(t.profile_id, 0))]
    if not sequence: return []
    widths = set()
    n = len(sequence)
    limit = math.ceil(math.sqrt(n) * 3) + 1
    for t in types.values():
        step = pitch(t, t, spacing, style)
        for k in range(1, min(limit, counts.get(t.profile_id, 1)) + 1):
            widths.add(_round(2 * edge_margin(t, style, extra) + (k - 1) * step + .01, .01))
    # Rows as wide as the printers allow, so a tall stack of tubes can still find a layout that fits.
    for x, y, _ in (volumes or [])[:6]:
        for side in (x, y):
            room = side - 2 * RULES.printer_margin_mm - reserve[0]
            if room > 0: widths.add(_round(room, .01))
    if layout.columns:
        lead = sequence[0]
        widths = {_round(2 * edge_margin(lead, style, extra) + (layout.columns - 1) * pitch(lead, lead, spacing, style) + .01, .01)}
    # The search is repeated on every change, so a large rack samples its row widths: neighbouring ones give nearly the same rack.
    if len(widths) > MAX_WIDTHS:
        ordered = sorted(widths)
        widths = {ordered[round(k * (len(ordered) - 1) / (MAX_WIDTHS - 1))] for k in range(MAX_WIDTHS)}
    # Straight rows by default. A staggered layout is a little smaller, but tubes in rows are what a bench expects: they can be
    # counted and addressed, and the structure between them opens up. It stays available as an explicit choice.
    modes = {'auto': ('grouped', 'flow', 'staggered') if preference == 'compact' else ('grouped', 'flow'), 'grid': ('flow',), 'grouped': ('grouped',), 'staggered': ('staggered',)}[layout.arrangement]
    best, best_score = None, None
    height = max(t.deck for t in types.values())
    for width in sorted(widths):
        for mode_index, mode in enumerate(modes):
            rows = _rows(sequence, width, mode, spacing, style, extra)
            placed = _place(rows, mode, spacing, style)
            x0, y0, x1, y1 = footprint(placed, style, extra)
            w, d = max(x1 - x0 + reserve[0], min_size[0]), max(y1 - y0 + reserve[1], min_size[1])
            # The same rows can also run front to back, with groups side by side. Rows stay rows either way.
            for turned in (False, True):
                if turned:
                    w, d = max(y1 - y0 + reserve[0], min_size[0]), max(x1 - x0 + reserve[1], min_size[1])
                if layout.orientation == 'landscape' and w < d: continue
                if layout.orientation == 'portrait' and d < w: continue
                aspect = max(w / d, d / w)
                fits = fits_upright(w, d, height, volumes) if volumes else w <= MAX_FOOTPRINT_MM and d <= MAX_FOOTPRINT_MM
                # Tubes of different heights read best with the tall ones along the back and a long low deck in front.
                cost = _layout_cost(rows, placed, w, d, aspect, preference)
                if preference != 'compact' and style == 'premium' and len({t.deck for t in types.values()}) > 1:
                    # And a raised level that runs the width of the rack, not a block standing on a tray.
                    top = max(t.deck for t in types.values())
                    tall = [(x, y) for t, x, y in placed if t.deck == top]
                    run = max(y for _, y in tall) - min(y for _, y in tall) if turned else max(x for x, _ in tall) - min(x for x, _ in tall)
                    cost *= (1.3 if turned else 1) * (1 + .6 * max(0.0, 1 - (run + 40) / max(w, 1)))
                score = (not fits, round(cost, 1), mode_index, turned, -width)
                if best_score is None or score < best_score:
                    best, best_score = ([(t, -y, x) for t, x, y in placed] if turned else placed), score
    if best is None:   # the requested orientation is impossible for these tubes (for example one tube): ignore it
        return automatic(types, counts, layout.model_copy(update={'orientation': 'auto'}), style, volumes, min_size, reserve)
    x0, y0, x1, y1 = footprint(best, style, extra)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [(t, _round(x - cx), _round(y - cy)) for t, x, y in best]

def check_positions(placed, spacing, style):
    """Problems between placed tubes, worst first per pair: overlap, too little wall, touching caps, tight for fingers."""
    issues = []
    for i, (a, ax, ay) in enumerate(placed):
        for j in range(i + 1, len(placed)):
            b, bx, by = placed[j]
            distance = math.hypot(ax - bx, ay - by)
            bores, caps = (a.bore_d + b.bore_d) / 2, (a.cap_d + b.cap_d) / 2
            if distance > max(bores, caps) + 40: continue
            if distance < bores:
                issues.append(dict(level='error', code='overlap', tubes=[i, j], message=f'Positions {i + 1} and {j + 1} overlap: they are {distance:.1f} mm apart and need at least {bores + RULES.bore_web_mm:.1f} mm.', fix='Move one of them, or use Auto-arrange.'))
            elif distance < bores + RULES.bore_web_mm:
                issues.append(dict(level='error', code='thin_wall', tubes=[i, j], message=f'Positions {i + 1} and {j + 1} leave only {distance - bores:.1f} mm of wall; at least {RULES.bore_web_mm:.1f} mm is needed.', fix='Move them further apart.'))
            elif distance < caps + .5:
                issues.append(dict(level='error', code='cap_interference', tubes=[i, j], message=f'The caps at positions {i + 1} and {j + 1} would touch: they are {distance:.1f} mm apart and need at least {caps + .5:.1f} mm.', fix='Move them further apart.'))
            elif distance < pitch(a, b, 'compact', style) - .5:
                issues.append(dict(level='warning', code='finger_access', tubes=[i, j], message=f'Positions {i + 1} and {j + 1} are tight for fingers ({distance:.1f} mm apart; {pitch(a, b, "standard", style):.1f} mm is comfortable).', fix='Allow more room if you remove these tubes often.'))
    return issues
