"""Geometric layer continuity check, not a replacement for slicer/physical trials."""
import json
from pathlib import Path
import numpy as np
import trimesh
from shapely.ops import unary_union
from build_redesign import NAMES, ROOT

reports=[]
for name in NAMES:
    mesh=trimesh.load(ROOT/'redesign'/name/(name+'.stl'),force='mesh')
    heights=np.arange(.1,mesh.extents[2],.2)
    layers=mesh.section_multiplane([0,0,0],[0,0,1],heights)
    previous=None; islands=[]
    for height,section in zip(heights,layers):
        assert section is not None
        polygons=list(section.polygons_full)
        current=unary_union(polygons)
        if previous is not None:
            for polygon in polygons:
                if polygon.area>.01 and polygon.intersection(previous).area<1e-6:
                    islands.append(float(height))
        previous=current
    assert not islands, (name,islands)
    reports.append(dict(product=name,layer_height_mm=.2,layers=len(layers),floating_components=0))
(ROOT/'redesign/layer_validation.json').write_text(json.dumps(reports,indent=2))
print(json.dumps(reports,indent=2))
