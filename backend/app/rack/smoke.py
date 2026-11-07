"""python -m app.rack.smoke: one real rack of each style through the whole generator, label included.

Runs while the worker image is built, so an image whose CAD libraries were pruned too far fails to build instead of failing
for the first buyer. Pure geometry: it needs no database, and writes only to a temporary directory.
"""
import json, tempfile
from .build import run

def spec(style):
    tube = {'profile_id': 'smoke', 'x': 0.0, 'y': 0.0, 'bore_d': 11.7, 'deck': 27.0, 'floor': 3.2 if style == 'lightweight' else 3.0, 'tip_d': 3.4, 'cone': 15.0, 'seat': 'dimple' if style == 'lightweight' else 'tapered', 'drain_d': 2.4}
    data = {'geometry_version': 0, 'style': style, 'footprint': [-20, -20, 20, 20], 'dims': [40, 40, 27.0], 'tubes': [tube], 'entry_chamfer': .8,
            'label': {'text': 'Lab', 'font': 'sans', 'size': 8.0, 'style': 'engraved', 'position': 'front', 'depth': .8, 'anchor': [0.0, -20.0, 12.0]}}
    square = lambda half: [[-half, -half], [half, -half], [half, half], [-half, half]]
    if style == 'lightweight':
        data['bands'] = [{'z0': 0.0, 'z1': 3.2, 'polys': [{'outer': square(20), 'holes': []}]}, {'z0': 3.2, 'z1': 27.0, 'polys': [{'outer': square(20), 'holes': []}]}]
        data['windows'] = []
    else:
        data.update(terraces=[{'rect': [-20, -20, 20, 20], 'z': 27.0}], corner_r=5.0, top_fillet=1.2, bottom_chamfer=.6)
    return data

def main():
    for style in ('premium', 'lightweight'):
        with tempfile.TemporaryDirectory() as directory:
            result = run(spec(style), directory)
        print(style, json.dumps({k: result['metrics'][k] for k in ('volume_mm3', 'triangles', 'total_seconds')}))

if __name__ == '__main__':
    main()
