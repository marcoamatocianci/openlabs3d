"""Slice rack files with a real slicer: python scripts/rack_slicer_check.py VALIDATION_DIR [OUTPUT.json]

VALIDATION_DIR comes from scripts/rack_validation_prints.py. PrusaSlicer runs in a disposable container, with a generic 256 mm
FDM profile at 0.4 mm nozzle, 0.2 mm layers, 3 perimeters and 15% infill. That is one reproducible profile, not every host's printer.

For each rack, STL and 3MF: does it load, is it manifold and one part, does it slice without warnings, do the toolpaths have the
model's size. Then it slices again with automatic supports turned on: support-free is a claim the slicer gets to test.
"""
import json, re, subprocess, sys, tempfile
from pathlib import Path

IMAGE = 'ol3d-slicer-test'
PROFILE = """bed_shape = 0x0,256x0,256x256,0x256
max_print_height = 256
nozzle_diameter = 0.4
filament_diameter = 1.75
filament_density = 1.27
filament_type = PETG
layer_height = 0.2
first_layer_height = 0.2
perimeters = 3
top_solid_layers = 4
bottom_solid_layers = 4
fill_density = 15%
fill_pattern = gyroid
support_material = 0
skirts = 1
gcode_flavor = marlin2
"""

def slicer(directory, *arguments):
    return subprocess.run(['docker', 'run', '--rm', '--network', 'none', '-v', f'{directory}:/work', IMAGE, 'prusa-slicer', *arguments], capture_output=True, text=True, timeout=900)

def gcode_facts(path):
    facts = {'layers': 0, 'support_mm': 0.0, 'types': {}}
    kind, x0, y0, x1, y1, z1, last, e_total = '', 1e9, 1e9, -1e9, -1e9, 0.0, (0.0, 0.0), 0.0
    for line in open(path, errors='replace'):
        if line.startswith(';LAYER_CHANGE'): facts['layers'] += 1
        elif line.startswith(';TYPE:'): kind = line[6:].strip()
        elif line.startswith('G1 ') and kind and 'E' in line and kind not in ('Skirt/Brim', 'Skirt'):
            x, y = re.search(r'X(-?[\d.]+)', line), re.search(r'Y(-?[\d.]+)', line)
            if x and y:
                point = (float(x.group(1)), float(y.group(1)))
                length = ((point[0] - last[0]) ** 2 + (point[1] - last[1]) ** 2) ** .5
                facts['types'][kind] = facts['types'].get(kind, 0) + length
                x0, y0, x1, y1 = min(x0, point[0]), min(y0, point[1]), max(x1, point[0]), max(y1, point[1])
                last = point
        elif line.startswith('G1 ') and ('X' in line and 'Y' in line):
            x, y = re.search(r'X(-?[\d.]+)', line), re.search(r'Y(-?[\d.]+)', line)
            if x and y: last = (float(x.group(1)), float(y.group(1)))
        elif line.startswith('; filament used [g]'): facts['grams'] = float(line.split('=')[1])
        elif line.startswith('; estimated printing time (normal mode)'): facts['time'] = line.split('=')[1].strip()
    facts['toolpath_size'] = [round(x1 - x0, 1), round(y1 - y0, 1)]
    facts['types'] = {k: round(v) for k, v in sorted(facts['types'].items())}
    return facts

def check(directory, name, manifest):
    results = {'name': name, 'dimensions_mm': manifest['dimensions_mm'], 'estimated_grams_petg': manifest['estimated_grams_petg']}
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary); work.chmod(0o777)
        (work / 'profile.ini').write_text(PROFILE)
        for ext in ('stl', '3mf'): (work / f'rack.{ext}').write_bytes((directory / name / f'rack.{ext}').read_bytes())
        for ext in ('stl', '3mf'):
            info = slicer(work, '--info', f'/work/rack.{ext}')
            parts = dict(re.findall(r'^(\w+)\s*=\s*(.+)$', info.stdout, re.M))
            sliced = slicer(work, '--load', '/work/profile.ini', '--export-gcode', '--output', f'/work/{ext}.gcode', f'/work/rack.{ext}')
            ok = sliced.returncode == 0 and (work / f'{ext}.gcode').is_file()
            noise = [l for l in (sliced.stdout + sliced.stderr).splitlines() if re.search(r'warn|error|empty|fail|non-manifold|not manifold|open edge', l, re.I)]
            results[ext] = {'loaded': info.returncode == 0, 'manifold': parts.get('manifold'), 'parts': parts.get('number_of_parts'), 'open_edges': parts.get('open_edges'), 'size': [parts.get('size_x'), parts.get('size_y'), parts.get('size_z')], 'sliced': ok, 'messages': noise[:6]}
            if ok: results[ext].update(gcode_facts(work / f'{ext}.gcode'))
        supported = slicer(work, '--load', '/work/profile.ini', '--support-material', '--support-material-auto', '--export-gcode', '--output', '/work/s.gcode', '/work/rack.stl')
        results['auto_support_mm'] = gcode_facts(work / 's.gcode')['types'].get('Support material', 0) if supported.returncode == 0 else None
    return results

def main(directory, output=None):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    reports = []
    for entry in manifest['prints']:
        r = check(directory, entry['name'], entry); reports.append(r)
        s = r['stl']
        print(f"{r['name']:26s} stl:{s['sliced']} 3mf:{r['3mf']['sliced']} manifold:{s['manifold']} parts:{s['parts']} size:{s['size']} layers:{s.get('layers')} toolpath:{s.get('toolpath_size')} g:{s.get('grams')} (est {r['estimated_grams_petg']}) time:{s.get('time')} auto-support mm:{r['auto_support_mm']} bridges mm:{s.get('types', {}).get('Bridge infill', 0)} overhang mm:{s.get('types', {}).get('Overhang perimeter', 0)} msgs:{len(s['messages'])}/{len(r['3mf']['messages'])}", flush=True)
    if output: Path(output).write_text(json.dumps(reports, indent=1))

if __name__ == '__main__':
    main(*sys.argv[1:])
