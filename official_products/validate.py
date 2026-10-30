"""Reopen both exports and verify topology, bounds and equivalent volume (mm)."""
import json
from pathlib import Path
import numpy as np
import trimesh
results=[]
for directory in sorted(Path(__file__).parent.iterdir()):
    if not directory.is_dir() or not (directory/(directory.name+'.stl')).is_file():continue
    meshes=[trimesh.load(directory/(directory.name+ext),force='mesh') for ext in ('.stl','.3mf')]
    for mesh in meshes:
        assert mesh.is_watertight and mesh.is_winding_consistent and mesh.is_volume
        assert len(mesh.split())==1
        assert np.all(mesh.area_faces>0)
    assert np.allclose(meshes[0].bounds,meshes[1].bounds,atol=1e-4)
    assert np.isclose(meshes[0].volume,meshes[1].volume,rtol=1e-5)
    results.append(dict(product=directory.name,dimensions_mm=meshes[0].extents.tolist(),volume_mm3=meshes[0].volume,watertight=True,consistent_winding=True,single_solid=True,equivalent_exports=True))
Path(__file__).with_name('validation.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
