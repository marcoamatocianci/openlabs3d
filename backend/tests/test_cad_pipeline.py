"""CAD pipeline: content-addressed storage, one analysis and one preview per content, the durable worker queue,
adoption of earlier previews, safe parsing and the geometry analysis itself."""
import io, json, secrets, struct, zipfile
from datetime import datetime, timedelta, timezone
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_marketplace import app
from test_marketplace_integrity import login, printer, user
import test_marketplace_integrity as integrity
from db_fixtures import isolate
from app import cad_assets, cad_worker, config, models
from app.mesh import analyze, load_mesh

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    engine, factory, cleanup = isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(integrity, 'SessionLocal', factory)   # its login() helper writes sessions
    monkeypatch.setattr(config, 'UPLOAD_DIR', tmp_path / 'uploads' / 'products')
    yield factory
    cleanup()

def binary_stl(triangles):
    triangles = np.asarray(triangles, dtype='<f4').reshape(-1, 3, 3)
    body = b''.join(struct.pack('<3f', 0, 0, 0) + t.tobytes() + b'\0\0' for t in triangles)
    return b'solid-ish binary'.ljust(80, b'\0') + struct.pack('<I', len(triangles)) + body

def cube(size=10, offset=(0, 0, 0), inverted=False):
    """12 outward-facing triangles."""
    o = np.array(offset, float); s = size
    v = [o + np.array(p) * s for p in [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]]
    quads = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(2,3,7,6),(1,2,6,5),(0,4,7,3)]
    tris = [t for a,b,c,d in quads for t in ((v[a],v[b],v[c]),(v[a],v[c],v[d]))]
    return [t[::-1] for t in tris] if inverted else tris

def fake_render(calls):
    def render(path, output, metrics=None, image='render.png'):
        from PIL import Image
        calls.append(path); output.mkdir(parents=True, exist_ok=True)
        Image.new('RGBA', (32, 32), (128, 128, 128, 255)).save(output / image, lossless=True)
        Image.new('RGBA', (16, 16)).save(output / 'thumb.webp'); (output / 'model.glb').write_bytes(b'glTF')
        if metrics is not None: metrics.update(image=image, bytes={})
        return True
    return render

def market(factory):
    with factory() as db:
        host, buyer = user(db, 'host'), user(db, 'buyer'); printer(db, host, {'PLA': {'black': '#000000'}})
        listings = [models.Listing(owner_id=host.id, title=f'Rack {i}', description='', category='Tube racks', price_cents=1000, material='PLA',
                                   dimensions='', compatibility='', status='approved', configuration='{"materials":{"PLA":10000}}') for i in range(2)]
        db.add_all(listings); db.commit()
        return host.id, buyer.id, [p.id for p in listings]

def upload(client, listing_id, data, name='model.stl'):
    return client.post(f'/api/listings/{listing_id}/cad', files={'file': (name, data)})

def counts(factory):
    with factory() as db:
        return {m.__tablename__: db.scalar(select(func.count()).select_from(m)) for m in (models.CadAsset, models.CadFile, models.CadJob)}

def test_identical_uploads_are_stored_analysed_and_rendered_once(isolated, monkeypatch):
    host, buyer, (a, b) = market(isolated); client = login(host); calls = []
    monkeypatch.setattr('app.render_product.render_asset', fake_render(calls))
    data = binary_stl(cube(20))
    first = upload(client, a, data); assert first.status_code == 200, first.text
    assert first.json()['dimensions_mm'] == [20, 20, 20] and first.json()['processing'] == {'analysis': 'queued', 'preview': 'queued'}
    assert first.json()['listing']['configurator']['visual']['status'] == 'pending'
    assert upload(client, b, data).status_code == 200
    assert counts(isolated) == {'cad_assets': 1, 'cad_files': 1, 'cad_jobs': 2}
    assert len(list((config.UPLOAD_DIR.parent / 'cad').iterdir())) == 1
    while cad_worker.work_once(isolated): pass
    assert len(calls) == 1, 'one Blender run for two listings'
    # A third listing, a re-upload and a title change process nothing more.
    assert upload(client, a, data).json()['processing'] == {'analysis': 'ready', 'preview': 'ready'}
    assert client.patch(f'/api/listings/{a}', json={'title': 'Renamed rack'}).status_code == 200
    assert not cad_worker.work_once(isolated) and len(calls) == 1
    visual = client.get(f'/api/listings/{b}').json()['configurator']['visual']
    assert visual['status'] == 'ready' and visual['image'].endswith('/render.webp')
    # Edits send a host's listing back to review, so only its owner sees it (and its previews) now.
    served = client.get(visual['model'])
    assert served.status_code == 200 and 'immutable' in served.headers['cache-control'] and served.headers['cache-control'].startswith('private')
    assert served.headers['content-type'] == 'model/gltf-binary' and client.get(visual['image']).headers['content-type'] == 'image/webp'
    assert client.get(visual['image'].replace('render.webp', 'render.png')).status_code == 404
    assert login(buyer).get(visual['model']).status_code == 404

def test_failed_renders_retry_then_fail_and_can_be_requeued(isolated, monkeypatch):
    host, _, (a, _) = market(isolated); client = login(host)
    monkeypatch.setattr('app.render_product.render_asset', lambda *args, **kwargs: False)
    assert upload(client, a, binary_stl(cube(5))).status_code == 200
    for attempt in range(cad_worker.MAX_ATTEMPTS):
        with isolated() as db:   # skip the backoff wait
            for job in db.scalars(select(models.CadJob)): job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        while cad_worker.work_once(isolated): pass
    with isolated() as db:
        render = db.scalar(select(models.CadJob).where(models.CadJob.kind == 'render'))
        assert render.status == 'failed' and render.attempts == cad_worker.MAX_ATTEMPTS and 'Rendering failed' in render.last_error
        assert db.scalar(select(models.CadJob).where(models.CadJob.kind == 'analyze')).status == 'ready'
    assert client.get(f'/api/listings/{a}').json()['configurator']['visual']['status'] == 'failed'
    again = client.post(f'/api/listings/{a}/render')
    assert again.json() == {'status': 'queued', 'requeued': 1}
    monkeypatch.setattr('app.render_product.render_asset', fake_render([]))
    assert cad_worker.work_once(isolated)
    assert client.get(f'/api/listings/{a}').json()['configurator']['visual']['status'] == 'ready'

def test_a_job_abandoned_by_a_stopped_worker_is_taken_again(isolated, monkeypatch):
    host, _, (a, _) = market(isolated); monkeypatch.setattr('app.render_product.render_asset', fake_render([]))
    assert upload(login(host), a, binary_stl(cube(5))).status_code == 200
    claimed = cad_worker.claim(isolated)            # a worker takes the job, then dies
    assert claimed and cad_worker.claim(isolated)[0] != claimed[0], 'a claimed job is not handed out twice'
    with isolated() as db:
        db.get(models.CadJob, claimed[0]).claimed_until = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
    again = cad_worker.claim(isolated)
    assert again[0] == claimed[0] and again[3] == 2, 'reclaimed once its claim expired, as a second attempt'

def test_existing_previews_are_adopted_not_rendered_again(isolated, monkeypatch):
    host, buyer, (a, _) = market(isolated); calls = []
    monkeypatch.setattr('app.render_product.render_asset', fake_render(calls))
    name = secrets.token_hex(24) + '.stl'; cad = config.UPLOAD_DIR.parent / 'cad'; cad.mkdir(parents=True)
    (cad / name).write_bytes(binary_stl(cube(8)))
    legacy = config.UPLOAD_DIR.parent / 'renders' / name[:-4]; legacy.mkdir(parents=True)
    for f in cad_assets.PREVIEW_FILES: (legacy / f).write_bytes(b'x')
    (legacy / 'status.json').write_text('{"status":"ready"}')
    with isolated() as db: db.get(models.Listing, a).cad_path = name; db.commit()
    before = login(buyer).get(f'/api/listings/{a}').json()['configurator']['visual']
    with isolated() as db: assert cad_assets.reconcile(db) == 1
    while cad_worker.work_once(isolated): pass
    assert calls == [], 'the existing preview is kept'
    after = login(buyer).get(f'/api/listings/{a}').json()['configurator']['visual']
    assert before == after and after['image'].endswith(f'/{name[:-4]}/render.png')
    with isolated() as db:
        assert db.scalar(select(models.CadAsset)).analysis_version == 1, 'analysis still runs once'
        assert cad_assets.reconcile(db) == 0

def test_content_decides_the_format_not_the_extension(isolated):
    host, _, (a, _) = market(isolated); client = login(host)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z: z.writestr('3D/3dmodel.model', '<model/>')
    assert upload(client, a, archive.getvalue(), 'model.stl').status_code == 422
    assert upload(client, a, binary_stl(cube(5)), 'model.3mf').status_code == 422
    assert upload(client, a, binary_stl(cube(5)), 'model.exe').status_code == 422
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, 'w', zipfile.ZIP_DEFLATED) as z: z.writestr('3D/3dmodel.model', b'<' + b' ' * 5_000_000 + b'>')
    assert upload(client, a, bomb.getvalue(), 'model.3mf').status_code == 422, 'compression ratio over 200 refused'
    entity = io.BytesIO()
    with zipfile.ZipFile(entity, 'w') as z: z.writestr('3D/3dmodel.model', '<!DOCTYPE m [<!ENTITY e "x">]><model>&e;</model>')
    assert upload(client, a, entity.getvalue(), 'model.3mf').status_code == 422
    assert counts(isolated)['cad_files'] == 0, 'nothing invalid is stored'

def test_analysis_is_private_to_the_owner_and_reports_findings(isolated, monkeypatch):
    host, buyer, (a, _) = market(isolated); client = login(host)
    monkeypatch.setattr('app.render_product.render_asset', fake_render([]))
    open_box = cube(10)[2:]   # bottom face missing
    assert upload(client, a, binary_stl(open_box)).status_code == 200
    assert client.get(f'/api/listings/{a}/cad/analysis').json()['status'] == 'queued'
    while cad_worker.work_once(isolated): pass
    report = client.get(f'/api/listings/{a}/cad/analysis').json()
    assert report['status'] == 'ready' and not report['analysis']['watertight']
    assert 'open_mesh' in {f['code'] for f in report['analysis']['findings'] if f['level'] == 'error'}
    assert report['printers'] and report['printers'][0]['fits'] is True
    assert login(buyer).get(f'/api/listings/{a}/cad/analysis').status_code == 403

def test_geometry_analysis_on_known_solids():
    solid = analyze(load_mesh(binary_stl(cube(10)), '.stl'))
    assert solid['watertight'] and solid['winding_consistent'] and not solid['inverted_normals']
    assert solid['volume_mm3'] == pytest.approx(1000) and solid['surface_area_mm2'] == pytest.approx(600)
    assert solid['components'] == 1 and solid['vertices'] == 8 and solid['boundary_edges'] == 0
    assert not [f for f in solid['findings'] if f['level'] == 'error']
    inverted = analyze(load_mesh(binary_stl(cube(10, inverted=True)), '.stl'))
    assert inverted['inverted_normals'] and 'inverted_normals' in {f['code'] for f in inverted['findings']}
    two = analyze(load_mesh(binary_stl(cube(10) + cube(5, offset=(30, 0, 0))), '.stl'))
    assert two['components'] == 2 and two['volume_mm3'] == pytest.approx(1125)
    flipped = cube(10); flipped[0] = flipped[0][::-1]
    assert not analyze(load_mesh(binary_stl(flipped), '.stl'))['winding_consistent']
    tiny = analyze(load_mesh(binary_stl(cube(1.5)), '.stl'))
    assert 'units_small' in {f['code'] for f in tiny['findings']}
    # A 3MF in centimetres with two build items keeps its parts and its unit.
    xml = ('<model unit="centimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
           '<object id="1" name="Foot"><mesh><vertices>' + ''.join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in
           [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]) + '</vertices><triangles>' +
           ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in
           [(0,3,2),(0,2,1),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(2,3,7),(2,7,6),(1,2,6),(1,6,5),(0,4,7),(0,7,3)]) +
           '</triangles></mesh></object></resources><build><item objectid="1"/><item objectid="1" transform="1 0 0 0 1 0 0 0 1 3 0 0"/></build></model>')
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z: z.writestr('3D/3dmodel.model', xml)
    kit = analyze(load_mesh(data.getvalue(), '.3mf'))
    assert kit['unit'] == 'centimeter' and kit['dimensions_mm'] == [40, 10, 10] and kit['components'] == 2
    assert [p['name'] for p in kit['parts']] == ['Foot', 'Foot'] and kit['volume_mm3'] == pytest.approx(2000)
