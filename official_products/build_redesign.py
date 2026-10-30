"""Run in the CadQuery venv. Stage and validate all three models before promotion."""
import json, runpy, shutil
from pathlib import Path
import cadquery as cq
import numpy as np
import trimesh

ROOT=Path(__file__).resolve().parent
NAMES=('microtube_rack_24','centrifuge_rack_15ml_12','centrifuge_rack_50ml_6')

def build():
    reports=[]
    for name in NAMES:
        folder=ROOT/'redesign'/name
        model=runpy.run_path(str(folder/'source/model.py'))
        shape=model['result']; params=model['PARAMETERS']
        assert shape.val().isValid() and len(shape.solids().vals())==1
        cq.exporters.export(shape,str(folder/(name+'.stl')),tolerance=.025,angularTolerance=.1)
        mesh=trimesh.load(folder/(name+'.stl'),force='mesh')
        mesh.units='mm'
        (folder/(name+'.3mf')).write_bytes(trimesh.exchange.threemf.export_3MF(trimesh.Scene(mesh)))
        reopened=trimesh.load(folder/(name+'.3mf'),force='mesh')
        for m in (mesh,reopened):
            assert m.is_watertight and m.is_winding_consistent and m.is_volume
            assert len(m.split())==1 and np.all(m.area_faces>0)
            assert np.allclose(m.extents,params[:3],atol=.001)
        assert np.allclose(mesh.bounds,reopened.bounds,atol=1e-5)
        assert np.isclose(mesh.volume,reopened.volume,rtol=1e-7)
        assert np.isclose(mesh.volume,shape.val().Volume(),rtol=.002)
        old=trimesh.load(ROOT/'previous/block_v1'/name/(name+'.stl'),force='mesh')
        # Verify each tube clearance is empty throughout the upper bearing region.
        for i in range(params[3]):
            for j in range(params[4]):
                x=(i-(params[3]-1)/2)*params[5];y=(j-(params[4]-1)/2)*params[5]
                probe=cq.Workplane('XY').workplane(offset=4.01).center(x,y).circle(params[6]/2-.02).extrude(params[2])
                assert shape.intersect(probe).val().Volume()<1e-6
        reports.append(dict(product=name,dimensions_mm=mesh.extents.tolist(),bounds_mm=mesh.bounds.tolist(),volume_mm3=mesh.volume,brep_volume_mm3=shape.val().Volume(),reduction_percent=100*(1-mesh.volume/old.volume),watertight=True,consistent_winding=True,single_solid=True,equivalent_exports=True,clearance_check=True,triangles=len(mesh.faces)))
    (ROOT/'redesign/validation.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2))

def promote():
    reports=json.loads((ROOT/'redesign/validation.json').read_text())
    assert {r['product'] for r in reports}==set(NAMES)
    archive=ROOT/'previous/bridge_v2'
    for name in NAMES:
        assert not (archive/name).exists(), 'Rollback archive already exists; refusing overwrite'
    for name in NAMES:
        shutil.copytree(ROOT/name,archive/name)
    shutil.copy2(ROOT/'validation.json',archive/'validation.json')
    for name in NAMES:
        shutil.copytree(ROOT/'redesign'/name,ROOT/name,dirs_exist_ok=True)
    shutil.copy2(ROOT/'redesign/validation.json',ROOT/'validation.json')

if __name__=='__main__':
    import sys
    if '--promote' in sys.argv: promote()
    else: build()
