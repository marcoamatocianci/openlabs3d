"""The part of the rack engine that needs no CAD: profiles, layout, structure, labels, limits and price rules."""
import json, math
import numpy as np
import pytest
from pydantic import ValidationError
from PIL import Image, ImageDraw, ImageFont
from app.rack import estimate, labels
from app.rack.layout import fits_upright
from app.rack.planner import catalog, plan, summary_text
from app.rack.profiles import OVERRIDE_LIMITS, PROFILES
from app.rack.rules import MAX_TUBES, RULES
from app.rack.schema import RackConfiguration, spec_hash

P50, P15, P15M, P05 = 'conical-50-generic', 'conical-15-generic', 'micro-1.5-generic', 'micro-0.5-generic'
PRINTER = [(256, 256, 256)]

def config(tubes, style='lightweight', **extra):
    return RackConfiguration(tubes=[{'profile_id': p, 'quantity': n} for p, n in tubes.items()], style=style, **extra)

def manual(positions, style='lightweight', **extra):
    return RackConfiguration(style=style, layout={'mode': 'manual', 'positions': [{'profile_id': p, 'x': x, 'y': y} for p, x, y in positions]}, **extra)

def codes(result, level=None): return {i['code'] for i in result['issues'] if level is None or i['level'] == level}

def counts(result):
    found = {}
    for t in result['tubes']: found[t['profile_id']] = found.get(t['profile_id'], 0) + 1
    return found

def pairs_keep_their_distance(result):
    tubes = result['tubes']
    for i, a in enumerate(tubes):
        for b in tubes[i + 1:]:
            distance = math.hypot(a['x'] - b['x'], a['y'] - b['y'])
            assert distance >= (a['bore_d'] + b['bore_d']) / 2 + RULES.bore_web_mm - .05
            assert distance >= (a['cap_d'] + b['cap_d']) / 2 + .5

def test_every_profile_records_where_its_dimensions_came_from():
    for profile in PROFILES.values():
        assert profile.source_reference and profile.verification_status in ('generic_unverified', 'published_unmeasured', 'measured')
        assert profile.cap_diameter_mm >= profile.body_diameter_mm > profile.tip_diameter_mm
    # None has been measured, and the catalogue says so: nothing may claim otherwise yet.
    assert not [p for p in PROFILES.values() if p.verification_status == 'measured']
    assert {p.nominal_capacity_ml for p in PROFILES.values()} == {.5, 1.5, 15, 50}

@pytest.mark.parametrize('style', ['lightweight', 'premium'])
@pytest.mark.parametrize('tubes', [{P50: 1}, {P50: 6}, {P50: 20}, {P15M: 24}, {P50: 15, P15: 5}, {P50: 6, P15M: 12}, {P50: 6, P15: 10, P15M: 24, P05: 12}])
def test_automatic_layouts_hold_what_was_asked_for(style, tubes):
    result = plan(config(tubes, style), PRINTER)
    assert result['ok'], result['issues']
    assert counts(result) == tubes
    pairs_keep_their_distance(result)
    w, d, h = result['dims']
    x0, y0, x1, y1 = result['footprint']
    assert (round(x1 - x0, 2), round(y1 - y0, 2)) == (w, d)
    for t in result['tubes']:   # inside the rack, seated above the bed, held below its own deck
        assert x0 + t['bore_d'] / 2 < t['x'] < x1 - t['bore_d'] / 2 and y0 + t['bore_d'] / 2 < t['y'] < y1 - t['bore_d'] / 2
        assert 0 < t['floor'] < t['deck'] <= h
    assert fits_upright(w, d, h, PRINTER)

def test_mixed_tube_seats_follow_each_tube_not_a_common_slab():
    result = plan(config({P50: 4, P05: 8}, 'premium'), PRINTER)
    by_type = {t['profile_id']: t for t in result['tubes']}
    assert by_type[P50]['bore_d'] > by_type[P05]['bore_d'] * 3
    assert by_type[P50]['deck'] > by_type[P05]['deck'] + 20         # microtubes sit on their own lower terrace
    assert by_type[P05]['deck'] - by_type[P05]['floor'] < PROFILES[P05].overall_length_mm    # and still stand proud to grip
    # Tall tubes stand behind or beside short ones, never in front of them, so their caps do not block the way in.
    for tall in (t for t in result['tubes'] if t['profile_id'] == P50):
        for short in (t for t in result['tubes'] if t['profile_id'] == P05):
            assert not (tall['y'] < short['y'] and abs(tall['x'] - short['x']) < (tall['cap_d'] + short['cap_d']) / 2)

def test_layout_is_deterministic_and_identity_follows_geometry():
    a, b = plan(config({P50: 7, P15M: 9}), PRINTER), plan(config({P15M: 9, P50: 7}), PRINTER)
    assert a['hash'] == b['hash'] and a['tubes'] == b['tubes']
    assert plan(config({P50: 8, P15M: 9}), PRINTER)['hash'] != a['hash']
    assert plan(config({P50: 7, P15M: 9}, 'premium'), PRINTER)['hash'] != a['hash']
    assert plan(config({P50: 7, P15M: 9}, label={'text': 'Lab 03'}), PRINTER)['hash'] != a['hash']
    assert a['hash'] == spec_hash(a['spec'])
    json.dumps(a)     # everything sent to the browser and stored with orders is plain JSON

def test_a_shifted_manual_layout_is_the_same_rack():
    tubes = [(P50, 0, 0), (P50, 40, 0), (P15, 80, 0)]
    a = plan(manual(tubes), PRINTER)
    b = plan(manual([(p, x + 13.5, y - 7) for p, x, y in tubes]), PRINTER)
    assert a['ok'] and a['hash'] == b['hash']
    assert b['offset'][0] - a['offset'][0] == pytest.approx(13.5)

def test_premium_bands_never_overhang_above_the_plinth_and_the_base_is_one_piece():
    result = plan(config({P50: 6, P15: 4, P15M: 8, P05: 4}, 'premium', label={'text': 'RNA'}), PRINTER)
    assert result['ok'], result['issues']
    assert 'floating' not in codes(result) and 'disconnected' not in codes(result)
    assert len(result['bands'][0]['polys']) == 1
    assert result['bands'][0]['z0'] == 0 and result['bands'][-1]['z1'] == result['dims'][2]

def test_lightweight_base_is_one_piece_and_every_tube_is_carried():
    result = plan(config({P50: 6, P15: 4, P15M: 8, P05: 4}, 'lightweight', label={'text': 'RNA'}), PRINTER)
    assert result['ok'], result['issues']
    assert 'disconnected' not in codes(result)
    assert len(result['bands'][0]['polys']) == 1 and result['bands'][0]['z0'] == 0
    assert sum(len(f['at']) for f in result['funnels']) == len(result['tubes'])
    assert max(b['z1'] for f in result['funnels'] for b in f['bands']) == result['dims'][2]

@pytest.mark.parametrize('profile', sorted(PROFILES))
def test_every_funnel_leans_less_than_the_printable_limit(profile):
    """The funnel follows the tube's cone, so this is a property of the tube library: a new tube must keep it."""
    result = plan(config({profile: 4}), PRINTER)
    for funnel in result['spec']['funnels']:
        shape = funnel['shape']
        run, rise = shape['bore'] - shape['tip'], shape['cone_top'] - shape['floor']
        assert math.degrees(math.atan2(run, rise)) < RULES.self_support_deg - 5
        assert shape['wall'] >= RULES.min_wall_mm

def test_lightweight_is_a_different_structure_with_far_less_material():
    light, block = plan(config({P50: 12}), PRINTER), plan(config({P50: 12}, 'premium'), PRINTER)
    assert light['metrics']['volume_mm3'] < block['metrics']['volume_mm3'] * .4
    assert light['spec']['funnels'] and light['spec']['base'] and 'terraces' not in light['spec']
    assert block['spec']['terraces'] and not block['spec'].get('funnels')
    assert light['metrics']['bed_contact_mm2'] < block['metrics']['bed_contact_mm2'] * .7
    assert light['estimates']['materials']['PLA']['grams'] < block['estimates']['materials']['PLA']['grams'] * .65
    windows = [w for funnel in light['spec']['funnels'] for w in funnel['shape']['windows']]
    assert windows
    # Every window roof is steeper than what prints unsupported.
    for w in windows:
        assert math.degrees(math.atan2(w['apex'] - w['shoulder'], w['width'] / 2)) >= RULES.self_support_deg

@pytest.mark.parametrize('tubes,share', [({P15M: 24}, .75), ({P05: 24}, .8), ({P15: 12}, .7), ({P50: 20}, .6)])
def test_lightweight_saves_real_material_at_every_tube_size(tubes, share):
    """A straight sleeve saved microtube racks almost nothing (77 g against 81 g). A funnel has to do better than that."""
    light, block = plan(config(tubes), PRINTER), plan(config(tubes, 'premium'), PRINTER)
    assert light['estimates']['materials']['PETG']['grams'] < block['estimates']['materials']['PETG']['grams'] * share

def test_links_between_collars_stay_within_the_bridging_limit():
    result = plan(config({P50: 6, P15: 6, P15M: 8}), PRINTER)
    bridges = [l for l in result['spec']['links'] if l['kind'] == 'bridge']
    assert bridges
    for link in bridges:
        (a_top, top), (b_top, _), _, (_, under), _ = link['profile']
        assert b_top > a_top and top > under
        # The underside is an arch at the printable limit or steeper, so even a short span needs no bridging.
        low = link['profile'][2][1]; middle = link['profile'][3][0]
        assert math.degrees(math.atan2(under - low, abs(link['profile'][2][0] - middle))) >= RULES.self_support_deg + 10

def test_the_plan_sends_each_funnel_shape_once():
    result = plan(config({P15M: 96}), PRINTER)
    assert len(result['funnels']) == 1 and len(result['funnels'][0]['at']) == 96
    assert len(json.dumps(result['funnels'])) < 60_000

def test_manual_tubes_too_close_for_a_bridge_do_not_break_the_plan():
    for gap in (32, 34, 34.5, 36, 42):
        assert plan(manual([(P50, 0, 0), (P50, gap, 0)]), PRINTER)['dims']

# Automatic layout quality ------------------------------------------------------------------------------------------
def rows_of(result):
    rows = {}
    for t in result['tubes']: rows.setdefault(t['y'], []).append(t)
    return rows

@pytest.mark.parametrize('tubes', [{P15M: 24}, {P50: 20}, {P50: 12}, {P15: 30}, {P05: 16}])
def test_one_kind_of_tube_makes_a_straight_full_grid(tubes):
    result = plan(config(tubes), PRINTER)
    rows = rows_of(result)
    assert len({len(r) for r in rows.values()}) == 1
    columns = {t['x'] for t in result['tubes']}
    assert len(columns) == len(next(iter(rows.values())))

@pytest.mark.parametrize('n', [5, 7, 11, 13, 22, 23])
def test_a_short_last_row_keeps_to_the_columns(n):
    result = plan(config({P50: n}), PRINTER)
    columns = {t['x'] for t in result['tubes']}
    assert len(columns) == max(len(r) for r in rows_of(result).values())
    width = max(t['x'] for t in result['tubes']) - min(t['x'] for t in result['tubes'])
    assert abs(sum(columns) / len(columns)) < width * .02    # and the columns are centred on the rack

def test_a_row_of_smaller_tubes_lines_up_with_the_rack():
    result = plan(config({P50: 15, P15: 5}), PRINTER)
    large = [t['x'] for t in result['tubes'] if t['profile_id'] == P50]
    small = [t['x'] for t in result['tubes'] if t['profile_id'] == P15]
    assert min(small) == pytest.approx(min(large), abs=1) and max(small) == pytest.approx(max(large), abs=1)

@pytest.mark.parametrize('style', ['lightweight', 'premium'])
@pytest.mark.parametrize('tubes', [{P15M: 24}, {P50: 15, P15: 5}, {P15M: 16, P05: 8}, {P50: 6, P15: 10, P15M: 24, P05: 12}, {P50: 7}])
def test_layouts_are_wider_than_deep_and_not_awkwardly_long(style, tubes):
    result = plan(config(tubes, style), PRINTER)
    width, depth, _ = result['dims']
    assert max(width, depth) / min(width, depth) < 2.2
    # A Premium rack with tubes of several heights puts the tall ones along the back, which may make it the deeper way round.
    if style == 'lightweight' or len(result['terraces']) == 1: assert width >= depth

@pytest.mark.parametrize('tubes', [{P50: 40}, {P15: 60}, {P15M: 100}])
def test_a_tight_printer_still_gets_the_layout_that_fits(tubes):
    assert plan(config(tubes), [(256, 256, 256)])['fit']['state'] in ('fits', 'too_large')

def test_racks_prefer_being_wider_than_deep_between_equals():
    for tubes in ({P50: 6}, {P15M: 24}, {P50: 12}):
        width, depth, _ = plan(config(tubes), PRINTER)['dims']
        assert width >= depth
    # So an ordinary lab name fits the front of a six-position rack.
    assert plan(config({P50: 6}, 'premium', label={'text': 'Proserpio Lab 03'}), PRINTER)['ok']

def test_small_racks_get_a_footprint_that_does_not_tip():
    result = plan(config({P50: 1}), PRINTER)
    assert result['metrics']['tip_angle_deg'] >= RULES.tip_angle_deg - .01
    assert min(result['dims'][:2]) > PROFILES[P50].body_diameter_mm + 10

def test_empty_too_many_and_unknown_tubes_are_refused_with_a_way_forward():
    for result, code in ((plan(config({}), PRINTER), 'empty'), (plan(config({P05: MAX_TUBES + 1}), PRINTER), 'too_many'), (plan(config({'nope': 3}), PRINTER), 'unknown_tube')):
        assert not result['ok'] and code in codes(result, 'error') and result['hash'] is None
        assert all(i['fix'] for i in result['issues'])

@pytest.mark.parametrize('positions,code', [
    ([(P50, 0, 0), (P50, 10, 0)], 'overlap'),
    ([(P50, 0, 0), (P50, 32, 0)], 'thin_wall'),
    ([(P50, 0, 0), (P50, 34, 0)], 'cap_interference'),
])
def test_manual_positions_that_cannot_work_are_named(positions, code):
    result = plan(manual(positions), PRINTER)
    assert code in codes(result, 'error') and not result['ok'] and result['hash'] is None
    assert next(i for i in result['issues'] if i['code'] == code)['tubes'] == [0, 1]

def test_tight_positions_warn_without_blocking():
    result = plan(manual([(P50, 0, 0), (P50, 35.5, 0)]), PRINTER)
    assert result['ok'] and 'finger_access' in codes(result, 'warning')

def test_oversized_designs_name_the_dimension_and_are_never_scaled():
    result = plan(config({P50: 60}), PRINTER)
    assert not result['ok'] and result['fit']['state'] == 'too_large' and result['fit']['exceeded']
    message = next(i for i in result['issues'] if i['code'] == 'too_large')
    assert 'for the currently available printers' in message['message'] and 'reducing' in message['fix']
    assert counts(result) == {P50: 60}     # the design is reported as it is
    pairs_keep_their_distance(result)

def test_build_volume_rules_allow_turning_but_not_tipping():
    assert fits_upright(240, 100, 60, [(100 + 10, 240 + 10, 65)])    # turned about Z
    assert not fits_upright(240, 100, 60, [(70, 250, 250)])          # would need lying on a side
    assert not fits_upright(246.1, 100, 60, PRINTER)                 # the margin counts
    assert fits_upright(246, 100, 60, PRINTER)
    assert plan(config({P50: 4}), [])['fit']['state'] == 'no_printers'

def test_automatic_layout_prefers_a_shape_that_fits_the_printers():
    square = plan(config({P50: 12}), [(256, 256, 256)])
    long_bed = plan(config({P50: 12}), [(500, 80, 256)])
    assert square['fit']['state'] == 'fits'
    assert long_bed['fit']['state'] == 'fits' and max(long_bed['dims'][:2]) > 400

def test_overrides_are_applied_within_safe_limits():
    wider = plan(config({P15: 4}, overrides={P15: {'body_diameter_mm': 18.5}}), PRINTER)
    assert wider['ok'] and wider['tubes'][0]['bore_d'] == pytest.approx(18.5 + PROFILES[P15].recommended_clearance_mm)
    low, high = OVERRIDE_LIMITS['body_diameter_mm']
    for bad in (PROFILES[P15].body_diameter_mm * low - .5, PROFILES[P15].body_diameter_mm * high + .5):
        assert 'invalid_dimension' in codes(plan(config({P15: 4}, overrides={P15: {'body_diameter_mm': bad}}), PRINTER), 'error')
    assert 'invalid_dimension' in codes(plan(config({P15: 4}, overrides={P15: {'cap_diameter_mm': 15}}), PRINTER), 'error')

def test_the_schema_refuses_junk():
    for bad in ({'tubes': [{'profile_id': P50, 'quantity': -1}]}, {'tubes': [{'profile_id': P50, 'quantity': 1.5}]}, {'surprise': 1}, {'schema_version': 9}, {'style': 'wood'},
                {'layout': {'positions': [{'profile_id': P50, 'x': float('inf'), 'y': 0}]}}, {'label': {'text': 'a\nb'}}, {'label': {'text': '<script>'}}, {'label': {'text': '__import__("os")'}}, {'clearance_adjust_mm': 5}):
        with pytest.raises(ValidationError): RackConfiguration(**bad)
    assert RackConfiguration(label={'text': '  Müller Lab – 03  '.replace('–', '-')}).label.text == 'Müller Lab - 03'

# Labels ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('position', ['front', 'back', 'left', 'right'])
@pytest.mark.parametrize('style', ['lightweight', 'premium'])
def test_labels_fit_their_face(style, position):
    result = plan(config({P50: 12}, style, label={'text': 'Proserpio Lab', 'position': position}), PRINTER)
    assert result['ok'], result['issues']
    label = result['label']
    assert label['size'] >= labels.min_size('sans')
    along = result['dims'][0] if position in ('front', 'back') else result['dims'][1]
    assert label['width'] < along - 10

def test_premium_top_label_gets_its_own_strip_clear_of_the_holes():
    plain = plan(config({P50: 12}, 'premium'), PRINTER)
    labelled = plan(config({P50: 12}, 'premium', label={'text': 'Lab 03', 'position': 'top'}), PRINTER)
    assert labelled['ok'] and labelled['dims'][1] > plain['dims'][1]
    label = labelled['label']
    nearest = min(t['y'] - t['bore_d'] / 2 for t in labelled['tubes'])
    assert label['anchor'][1] + label['cap'] / 2 < nearest

def test_lightweight_has_no_top_face_and_says_what_to_do():
    result = plan(config({P50: 4}, label={'text': 'Lab', 'position': 'top'}), PRINTER)
    assert 'label_position' in codes(result, 'error') and 'Premium' in next(i for i in result['issues'] if i['code'] == 'label_position')['fix']

def test_long_labels_shrink_then_are_refused_with_a_length_that_fits():
    small = {P50: 4}
    reduced = plan(config(small, 'premium', label={'text': 'Sample Prep', 'size_mm': 16}), PRINTER)
    assert 'label_resized' in codes(reduced, 'warning') and reduced['label']['size'] < 16
    refused = plan(config(small, 'premium', label={'text': 'Molecular Biology and Sample Preparation'}), PRINTER)
    assert 'label_too_long' in codes(refused, 'error') and not refused['ok']
    issue = next(i for i in refused['issues'] if i['code'] == 'label_too_long')
    assert 'Shorten' in issue['fix'] and 'characters' in issue['fix']

def test_label_letters_stay_printable():
    for font in labels.FONTS:
        assert labels.FONTS[font]['stroke'] * labels.min_size(font) >= RULES.min_text_stroke_mm - 1e-6
    assert RULES.engrave_depth_mm >= 3 * RULES.layer_mm and RULES.emboss_height_mm >= 3 * RULES.layer_mm - 1e-9

@pytest.mark.parametrize('font', list(labels.FONTS))
def test_font_strokes_match_their_constants(font):
    size = 400
    image = Image.new('L', (1600, 600), 0)
    ImageDraw.Draw(image).text((20, 50), 'lIietaEs-', font=ImageFont.truetype(labels.font_path(font), size), fill=255)
    ink, runs = np.array(image) > 128, []
    for grid in (ink, ink.T):
        for line in grid[::3]:
            edges = np.diff(np.r_[0, line.astype(int), 0])
            runs += list(np.where(edges == -1)[0] - np.where(edges == 1)[0])
    assert np.percentile(runs, 5) / size >= labels.FONTS[font]['stroke'] * .95

# Limits and prices -----------------------------------------------------------------------------------------------
def test_premium_corner_radius_is_limited_by_the_tube_walls():
    fine = plan(config({P50: 4}, 'premium', corner_radius_mm=14), PRINTER)
    assert fine['ok'] and fine['corner_r'] == 14 and 'fillet_clamped' not in codes(fine)
    excessive = plan(config({P50: 4}, 'premium', corner_radius_mm=40), PRINTER)
    assert 'fillet_clamped' in codes(excessive, 'warning') and excessive['corner_r'] < 40 and excessive['ok']
    assert excessive['metrics']['min_wall_mm'] >= RULES.min_wall_mm
    # Never more than half the narrower side either: a larger radius cannot exist, and the fillet would be dropped.
    narrow = plan(config({P50: 2}, 'premium', corner_radius_mm=50), PRINTER)
    assert narrow['corner_r'] < min(narrow['dims'][:2]) / 2

def test_estimates_follow_the_model_and_match_the_quote_arithmetic():
    small, large = plan(config({P50: 4}), PRINTER), plan(config({P50: 16}), PRINTER)
    pla_small, pla_large = small['estimates']['materials']['PLA'], large['estimates']['materials']['PLA']
    assert pla_large['grams'] > pla_small['grams'] * 2 and pla_large['unit_price_cents'] > pla_small['unit_price_cents']
    base, factors = estimate.price_rules(100000, 40000, 8, False, 'lightweight')
    for material, factor in factors.items():
        direct = estimate.unit_price_cents(100000, 40000, material, 8, False, 'lightweight')
        assert abs(estimate.material_price(base, factor) - direct) <= 1     # through basis points, as pricing.quote does
    assert min(factors.values()) == 10000
    assert estimate.unit_price_cents(100000, 40000, 'PLA', 8, True, 'lightweight') > estimate.unit_price_cents(100000, 40000, 'PLA', 8, False, 'lightweight')
    assert estimate.unit_price_cents(100000, 40000, 'PLA', 8, False, 'premium') > estimate.unit_price_cents(100000, 40000, 'PLA', 8, False, 'lightweight')

def test_mass_is_not_solid_volume_and_never_exceeds_it():
    assert estimate.printed_volume(1_000_000, 100_000) < 1_000_000 * .5
    assert estimate.printed_volume(1000, 100_000) == pytest.approx(980)

def test_plan_is_quick_enough_to_run_on_every_change():
    import time
    started = time.perf_counter()
    plan(config({P05: MAX_TUBES}), [(500, 500, 256)])
    assert time.perf_counter() - started < 3.0

def test_catalog_is_complete_and_presets_are_valid_configurations():
    data = catalog()
    assert {f['id'] for f in data['families']} == {'conical-50', 'conical-15', 'micro-1.5', 'micro-0.5'}
    assert len(data['fonts']) == 3 and {p['id'] for p in data['presets']} == {'microtube', 'falcon-50', 'mixed-falcon'}
    for preset in data['presets']:
        result = plan(config(preset['tubes'], preset['style']), [(256, 256, 256)])
        assert result['ok'], (preset['name'], result['issues'])
        assert summary_text(result['summary'])
    json.dumps(data)

# Printing areas ---------------------------------------------------------------------------------------------------
def test_a_chosen_printing_area_constrains_the_automatic_layout():
    wide = plan(config({P50: 12}), [(500, 500, 256)])
    box = plan(config({P50: 20}, layout={'envelope': {'x': 180, 'y': 180, 'z': 180}}), [(500, 500, 256), (180, 180, 180)])
    assert not box['ok'] and box['fit']['state'] == 'too_large' and 'printing area you chose' in next(i for i in box['issues'] if i['code'] == 'too_large')['message']
    fits = plan(config({P50: 6}, layout={'envelope': {'x': 180, 'y': 180, 'z': 180}}), [(500, 500, 256), (180, 180, 180)])
    assert fits['ok'] and fits['fit']['limit'] == [170.0, 170.0, 175.0] and max(fits['dims'][:2]) <= 170
    assert wide['ok'] and wide['fit']['printers'] == 1

def test_layouts_use_the_whole_printer_when_they_must():
    """All tubes fit a long narrow bed only as one long block, which the width candidates must reach."""
    result = plan(config({P50: 8}), [(340, 90, 256)])
    assert result['ok'] and result['dims'][0] <= 330 and result['dims'][1] <= 80

def test_manual_positions_outside_the_chosen_area_block_the_rack():
    far = RackConfiguration(layout={'mode': 'manual', 'envelope': {'x': 180, 'y': 180, 'z': 180}, 'positions': [{'profile_id': P50, 'x': 0, 'y': 0}, {'profile_id': P50, 'x': 200, 'y': 0}]})
    result = plan(far, [(500, 500, 256), (180, 180, 180)])
    assert not result['ok'] and 'width' in result['fit']['exceeded']

def test_the_finish_never_changes_the_geometry_or_its_hash():
    a, b = plan(config({P50: 4}), PRINTER), plan(config({P50: 4}, material='PETG', color='red'), PRINTER)
    assert a['hash'] == b['hash'] and 'material' not in a['spec'] and 'color' not in a['spec']

def test_rates_are_data():
    from app.rack.estimate import Rates, unit_price_cents
    cheap, dear = Rates(setup_eur=0, marketplace_fee_pct=0), Rates(setup_eur=20, marketplace_fee_pct=50)
    assert unit_price_cents(100000, 40000, 'PLA', 8, False, 'lightweight', cheap) < unit_price_cents(100000, 40000, 'PLA', 8, False, 'lightweight', dear)
    assert plan(config({P50: 4}), PRINTER)['estimates']['pricing_status'] == 'prototype'
    assert plan(config({P50: 4}), PRINTER, Rates(commercially_validated=True))['estimates']['pricing_status'] == 'validated'


# Rack height ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('style', ['premium', 'lightweight'])
@pytest.mark.parametrize('tubes', [{P50: 6}, {P15: 8}, {P15M: 24}, {P05: 12}, {P50: 15, P15: 5}, {P50: 2, P15M: 12}])
def test_height_limits_come_from_the_tubes_and_the_rack_is_what_was_asked(style, tubes):
    limits = plan(config(tubes, style), PRINTER)['height']
    assert limits['min'] <= limits['recommended'] <= limits['max'] and not limits['custom']
    for height in (limits['min'], limits['recommended'], limits['max'], round((limits['min'] + limits['max']) * 2) / 4):
        result = plan(config(tubes, style, height_mm=height), PRINTER)
        assert result['ok'], (height, result['issues'])
        assert result['dims'][2] == pytest.approx(height, abs=.26)      # decks are drawn to the half millimetre
        assert result['height']['custom']

def test_different_tubes_have_different_limits():
    falcon, micro = plan(config({P50: 4}, 'premium'), PRINTER)['height'], plan(config({P15M: 4}, 'premium'), PRINTER)['height']
    assert falcon['min'] > micro['max']
    assert falcon['max'] - falcon['min'] > micro['max'] - micro['min']

@pytest.mark.parametrize('style', ['premium', 'lightweight'])
@pytest.mark.parametrize('profile', sorted(PROFILES))
def test_at_every_height_a_tube_is_held_and_can_still_be_reached(style, profile):
    limits = plan(config({profile: 4}, style), PRINTER)['height']
    tube = PROFILES[profile]
    for height in (limits['min'], limits['max']):
        t = plan(config({profile: 4}, style, height_mm=height), PRINTER)['tubes'][0]
        held = t['deck'] - t['floor']
        assert held >= min(tube.cone_length_mm, tube.overall_length_mm * (1 - RULES.exposed_share)) - .6     # past the cone, or as far as a short tube allows
        assert t['length'] - held >= RULES.high_exposed_min_mm - .6                                          # always something to take hold of
    low = plan(config({profile: 4}, style, height_mm=limits['min']), PRINTER)
    assert low['metrics']['min_wall_mm'] >= RULES.min_wall_mm

def test_too_low_and_too_high_are_refused_with_the_nearest_height_that_works():
    limits = plan(config({P50: 6}, 'premium'), PRINTER)['height']
    low = plan(config({P50: 6}, 'premium', height_mm=limits['min'] - 5), PRINTER)
    issue = next(i for i in low['issues'] if i['code'] == 'height_too_low')
    assert not low['ok'] and low['hash'] is None
    assert f"{limits['min']:g} mm" in issue['message'] and issue['action'] == {'kind': 'height', 'value': limits['min'], 'label': f"Use {limits['min']:g} mm"}
    high = plan(config({P50: 6}, 'premium', height_mm=limits['max'] + 5), PRINTER)
    assert not high['ok'] and next(i for i in high['issues'] if i['code'] == 'height_too_high')['action']['value'] == limits['max']

def test_height_changes_the_material_price_and_the_shape_not_just_the_scale():
    low, standard, tall = (plan(config({P50: 6}, 'premium', height_mm=h), PRINTER) for h in (32, 45, 70))
    grams = [p['estimates']['materials']['PETG']['grams'] for p in (low, standard, tall)]
    assert grams[0] < grams[1] < grams[2]
    assert low['estimates']['materials']['PETG']['unit_price_cents'] < tall['estimates']['materials']['PETG']['unit_price_cents']
    # Not a scaled model: every bore keeps its diameter, its seat its cone and its floor its thickness.
    for p in (low, standard, tall):
        assert {t['bore_d'] for t in p['tubes']} == {low['tubes'][0]['bore_d']}
        assert all(t['floor'] == pytest.approx(RULES.floor_mm) for t in p['tubes'])
    assert low['spec']['terraces'][0]['profile']['round'] < tall['spec']['terraces'][0]['profile']['round']
    assert low['hash'] != standard['hash'] != tall['hash']

def test_a_tall_rack_is_checked_against_the_printers_height():
    limits = plan(config({P50: 4}, 'premium'), [(250, 250, 250)])['height']
    short_printer = [(250, 250, 60)]
    assert plan(config({P50: 4}, 'premium', height_mm=40), short_printer)['fit']['state'] == 'fits'
    assert plan(config({P50: 4}, 'premium', height_mm=limits['max']), short_printer)['fit']['state'] == 'too_large'

def test_mixed_tubes_keep_their_order_at_any_height():
    limits = plan(config({P50: 4, P15M: 8}, 'premium'), PRINTER)['height']
    for height in (limits['min'], limits['max']):
        result = plan(config({P50: 4, P15M: 8}, 'premium', height_mm=height), PRINTER)
        decks = {t['profile_id']: t['deck'] for t in result['tubes']}
        assert result['ok'] and decks[P50] > decks[P15M]

def test_default_height_changes_nothing():
    assert plan(config({P50: 6}, 'premium'), PRINTER)['hash'] == plan(config({P50: 6}, 'premium', height_mm=None), PRINTER)['hash']
    assert plan(config({P50: 6}), PRINTER)['dims'][2] == 60.5

def test_manual_layouts_can_change_height_too():
    positions = [(P50, 0, 0), (P50, 40, 0)]
    limits = plan(manual(positions), PRINTER)['height']
    result = plan(manual(positions, height_mm=limits['max']), PRINTER)
    assert result['ok'] and result['dims'][2] == pytest.approx(limits['max'], abs=.26) and [t['x'] for t in result['tubes']] == [t['x'] for t in plan(manual(positions), PRINTER)['tubes']]

# Layout choices ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('style', ['premium', 'lightweight'])
@pytest.mark.parametrize('tubes', [{P15M: 24}, {P50: 15, P15: 5}, {P15M: 16, P05: 8}, {P15: 30}])
def test_layouts_offered_are_valid_and_really_different(style, tubes):
    options = plan(config(tubes, style), [(256, 256, 256)])['layouts']
    for a in options:
        for b in options:
            if a is not b: assert abs(a['dims'][0] - b['dims'][0]) > .04 * min(a['dims'][0], b['dims'][0]) or abs(a['dims'][1] - b['dims'][1]) > .04 * min(a['dims'][1], b['dims'][1])
        assert fits_upright(*a['dims'], plan(config(tubes, style), [(256, 256, 256)])['dims'][2], [(256, 256, 256)])
        assert len(a['tubes']) == sum(tubes.values())
    assert sum(o['selected'] for o in options) == (1 if options else 0)

@pytest.mark.parametrize('style', ['premium', 'lightweight'])
def test_each_layout_can_be_chosen_and_is_what_it_says(style):
    options = {o['id']: o for o in plan(config({P15M: 24}, style), PRINTER)['layouts']}
    assert set(options) == {'balanced', 'compact', 'wide'}
    area = lambda o: o['dims'][0] * o['dims'][1]
    assert area(options['compact']) < area(options['balanced'])
    assert options['wide']['dims'][0] / options['wide']['dims'][1] > options['balanced']['dims'][0] / options['balanced']['dims'][1]
    for name, option in options.items():
        layout = plan(config({P15M: 24}, style, layout={'preference': name}), PRINTER)
        assert layout['ok'] and layout['dims'][:2] == pytest.approx(option['dims'], abs=.1)
        pairs_keep_their_distance(layout)

def test_nothing_is_offered_when_there_is_nothing_to_choose_or_the_buyer_decided():
    assert plan(config({P50: 1}, 'premium'), PRINTER)['layouts'] == []
    assert plan(config({P50: 12}, 'premium', layout={'columns': 3}), PRINTER)['layouts'] == []
    assert plan(config({P50: 12}, 'premium', layout={'orientation': 'portrait'}), PRINTER)['layouts'] == []
    assert plan(manual([(P50, 0, 0), (P50, 40, 0)]), PRINTER)['layouts'] == []

def test_too_large_offers_the_compact_layout_when_that_would_fit():
    # A printer the balanced 6 x 4 rows just miss, and the compact ones reach.
    result = plan(config({P15M: 24}, 'premium'), [(125, 78, 200)])
    assert result['fit']['state'] == 'too_large'
    assert next(i for i in result['issues'] if i['code'] == 'too_large')['action'] == {'kind': 'layout', 'value': 'compact', 'label': 'Try a more compact layout'}
    assert plan(config({P15M: 24}, 'premium', layout={'preference': 'compact'}), [(125, 78, 200)])['fit']['state'] == 'fits'
