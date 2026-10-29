import io,zipfile,json
from pathlib import Path
import pytest
from app.mesh import inspect_mesh

def test_official_stl_and_3mf_dimensions_match():
    root=Path(__file__).resolve().parents[2]/'official_products'
    for name,dims in [('microtube_rack_24',[118,82,32]),('centrifuge_rack_15ml_12',[110,85,52]),('centrifuge_rack_50ml_6',[124,86,62])]:
        for extension in ['.stl','.3mf']:
            dimensions,triangles=inspect_mesh((root/name/(name+extension)).read_bytes(),extension,True)
            assert dimensions==dims
            assert len(triangles)>100

def test_3mf_components_transform_and_units():
    xml='''<model unit="centimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="2" z="3"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object><object id="2"><components><component objectid="1" transform="2 0 0 0 2 0 0 0 2 10 0 0"/></components></object></resources><build><item objectid="2"/></build></model>'''
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as z:z.writestr('3D/model.model',xml)
    dimensions,triangles=inspect_mesh(data.getvalue(),'.3mf',True)
    assert dimensions==[20,40,60]
    assert triangles[0][0]==(100,0,0)

def test_render_pipeline_outputs_and_preserves_source(tmp_path,monkeypatch):
    from app import render_product
    from PIL import Image
    source=Path(__file__).resolve().parents[2]/'official_products/microtube_rack_24/microtube_rack_24.stl'
    before=source.read_bytes()
    def run(command,**kwargs):
        payload=json.loads(Path(command[-1]).read_text());folder=Path(payload['output'])
        Image.new('RGBA',(1200,1200),(200,200,200,0)).save(folder/'render.png')
        (folder/'model.glb').write_bytes(b'fixture')
    monkeypatch.setattr(render_product.subprocess,'run',run)
    assert render_product.render_asset(source,tmp_path/'visual')
    assert source.read_bytes()==before
    assert Image.open(tmp_path/'visual/thumb.webp').size==(640,640)
    assert json.loads((tmp_path/'visual/status.json').read_text())['dimensions_mm']==[118,82,32]


def test_render_failure_is_reported(tmp_path,monkeypatch):
    from app import render_product
    source=tmp_path/'invalid.stl';source.write_bytes(b'invalid')
    assert render_product.render_asset(source,tmp_path/'out') is False
    assert json.loads((tmp_path/'out/status.json').read_text())['status']=='failed'
