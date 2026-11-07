"""The physical test set: python scripts/rack_validation_prints.py OUTPUT_DIR   (needs requirements-cad.txt)

Six ordinary configurations through the same planner and CAD engine customers use, to print and measure. Writes each
rack's STL and 3MF, and manifest.json with what to expect and what to measure. Printing them is the only way to learn
whether the tube fit, clearances and text work: nothing here has been printed yet.
"""
import json, os, sys, tempfile
from pathlib import Path
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + tempfile.mkdtemp() + '/unused.db')
os.environ.setdefault('UPLOAD_DIR', tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.rack.build import run
from app.rack.planner import plan
from app.rack.schema import RackConfiguration

P50, P15, P15M, P05 = 'conical-50-generic', 'conical-15-generic', 'micro-1.5-generic', 'micro-0.5-generic'
ROUND = 'Bore diameter, with a pin gauge or calipers, across two directions, at the deck and 5 mm below. Compare with the planned diameter.'
SET = [
    ('1-microtube-single', 'Fit of one 1.5 mL tube', {P15M: 1}, 'premium', {}, ['Insert a real 1.5 mL tube from each brand in use: it should drop in without force and not rattle.', 'The tube stands on its seat, not on its cap flange.', ROUND]),
    ('2-conical-50-single', 'Fit and stability of one 50 mL tube', {P50: 1}, 'premium', {}, ['Insert a capped 50 mL tube, empty and then full: no binding, and the rack does not tip when nudged.', 'Tilt the loaded rack on the bench: note the angle at which it tips (the design target is 20 degrees).', ROUND]),
    ('3-mixed-small', 'All four tube types in one rack', {P50: 2, P15: 2, P15M: 4, P05: 4}, 'premium', {}, ['Every tube type seats at its own depth.', 'Caps do not touch their neighbours, with all positions filled.', 'Remove a microtube with gloves on while its neighbours are in place.', ROUND]),
    ('4-lightweight-structure', 'Open frame strength and printability', {P50: 6}, 'lightweight', {}, ['Prints with no supports. Inspect window roofs and sleeve tops for sagging.', 'Fill every position with full 50 mL tubes: lift by the frame, and look for cracks at webs and windows.', 'Weigh it, and compare with the estimated mass.', ROUND]),
    ('5-premium-edges', 'Fillets, chamfers and terraces', {P15: 4, P15M: 8}, 'premium', {'edge': 'rounded'}, ['Rounded top edges print without visible stair-stepping problems.', 'The bottom chamfer offsets elephant foot, so the outline measures as planned at the base.', 'The terrace step is clean and adds no overhang.', ROUND]),
    ('6-text-engraved', 'Engraved lettering', {P50: 6}, 'premium', {'label': {'text': 'Proserpio Lab 03', 'style': 'engraved'}}, ['Letters are legible, counters (the holes in e, a, o) stay open, and depth measures about 0.8 mm.']),
    ('6-text-embossed', 'Embossed lettering', {P50: 6}, 'lightweight', {'label': {'text': 'Proserpio Lab 03', 'style': 'embossed'}}, ['Letters stay attached, are legible, and stand about 0.6 mm proud.', 'The label wall stays stiff when pressed with a thumb.']),
    ('6-text-engraved-light', 'Engraved lettering on a Lightweight nameplate', {P50: 6}, 'lightweight', {'label': {'text': 'Proserpio Lab 03', 'style': 'engraved'}}, ['Letters stay attached, are legible, and stand about 0.6 mm proud.', 'The label wall stays stiff when pressed with a thumb.']),
    ('7-rack-24-microtubes', 'Small rack of 1.5 mL tubes', {P15M: 24}, 'lightweight', {}, ['Every position takes a tube, and the base does not lift at the corners.', ROUND]),
    ('8-rack-20-conical-50', 'Large rack of 50 mL tubes', {P50: 20}, 'lightweight', {}, ['Fits the bed with its margin. Lift it full of tubes by the frame, and look for flex or cracks.', ROUND]),
    ('10-premium-lowest', 'The lowest rack the height control allows for 50 mL tubes', {P50: 6}, 'premium', {'height_mm': 31.5}, ['A full tube stands steady when the rack is moved. Note any wobble: this height is a design rule, not a measurement.']),
    ('11-microtubes-lowest', 'The lowest rack for 1.5 mL tubes', {P15M: 24}, 'premium', {'height_mm': 22.5}, ['Tubes seat and can be lifted out with one hand.']),
    ('9-mixed-50-15-labelled', 'Mixed 50 and 15 mL rack with a label', {P50: 15, P15: 5}, 'premium', {'label': {'text': 'Proserpio Lab', 'style': 'engraved'}}, ['Both tube sizes seat at their own depth, and the label is legible.', ROUND]),
]

def main(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    manifest = {'status': 'NOT YET PRINTED. Record measurements here; do not treat any of this as validated until then.',
                'print': {'orientation': 'upright, base on the bed, no supports', 'material': 'PETG or PLA from one known spool', 'layer_mm': .2, 'nozzle_mm': .4, 'perimeters': 3, 'infill': '15 %'}, 'prints': []}
    for name, purpose, tubes, style, extra, checks in SET:
        result = plan(RackConfiguration(tubes=[{'profile_id': p, 'quantity': n} for p, n in tubes.items()], style=style, **extra), [(256, 256, 256)])
        assert result['ok'], (name, result['issues'])
        built = run(result['spec'], output / name)
        for preview in ('preview.glb', 'render.webp', 'thumb.webp'): (output / name / preview).unlink(missing_ok=True)
        bores = sorted({(t['profile_id'], t['bore_d']) for t in result['tubes']})
        manifest['prints'].append({'name': name, 'purpose': purpose, 'style': style, 'dimensions_mm': built['metrics']['dims_mm'], 'volume_mm3': built['metrics']['volume_mm3'], 'area_mm2': built['metrics']['area_mm2'], 'planned_bores_mm': [{'tube': p, 'diameter': b} for p, b in bores],
                                   'estimated_grams_petg': result['estimates']['materials']['PETG']['grams'], 'geometry_checks_passed': len(built['report']['geometry_checked']), 'check_after_printing': checks, 'measured': None})
        print(f'{name}: {built["metrics"]["dims_mm"]}, {built["metrics"]["total_seconds"]} s', flush=True)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print('wrote', output / 'manifest.json')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'rack-validation-prints')
