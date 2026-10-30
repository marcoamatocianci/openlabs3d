"""Listing creation: CAD inspection, manual dimensions, multi-material pricing and draft/submit behaviour."""
import io
import json
import struct
import zipfile
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_marketplace import app, register, headers, SessionLocal, Category, upload_test_cad
from app.equipment import seed_equipment


def box_stl(x, y, z):
    """Binary STL of an axis-aligned box (12 triangles)."""
    v = [(a, b, c) for a in (0, x) for b in (0, y) for c in (0, z)]
    faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    body = b''.join(struct.pack('<12fH', 0, 0, 0, *v[i], *v[j], *v[k], 0) for i, j, k in faces)
    return b'box'.ljust(80, b'\0') + struct.pack('<I', len(faces)) + body


def box_3mf(x, y, z, unit='millimeter'):
    v = [(a, b, c) for a in (0, x) for b in (0, y) for c in (0, z)]
    faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    xml = ('<model unit="%s" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1" type="model"><mesh><vertices>' % unit
           + ''.join('<vertex x="%s" y="%s" z="%s"/>' % p for p in v) + '</vertices><triangles>'
           + ''.join('<triangle v1="%d" v2="%d" v3="%d"/>' % f for f in faces) + '</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('3D/3dmodel.model', xml)
    return data.getvalue()


def host(email):
    client = TestClient(app); token = register(client, email, host=True)
    with SessionLocal() as db:
        seed_equipment(db)
        if not db.scalar(select(Category).where(Category.name == 'Tube racks')): db.add(Category(name='Tube racks')); db.commit()
    return client, token


def test_cad_inspection_measures_stl_and_3mf_without_storing():
    client, token = host('inspect@example.org')
    r = client.post('/api/cad/inspect', files={'file': ('rack.stl', box_stl(120, 80, 40.5))}, headers=headers(token))
    assert r.status_code == 200, r.text
    assert r.json()['dimensions_mm'] == [120, 80, 40.5] and r.json()['format'] == 'STL' and 'assumed' in r.json()['units']
    assert r.json()['warnings'] == []
    # A model exported in metres is flagged rather than silently rescaled.
    assert r'metres' in client.post('/api/cad/inspect', files={'file': ('m.stl', box_stl(.12, .08, .04))}, headers=headers(token)).json()['warnings'][0]
    r = client.post('/api/cad/inspect', files={'file': ('rack.3mf', box_3mf(12, 8, 4, 'centimeter'))}, headers=headers(token))
    assert r.json()['dimensions_mm'] == [120, 80, 40] and r.json()['format'] == '3MF'
    assert client.post('/api/cad/inspect', files={'file': ('bad.stl', b'not a mesh')}, headers=headers(token)).status_code == 422
    assert client.post('/api/cad/inspect', files={'file': ('a.obj', box_stl(1, 1, 1))}, headers=headers(token)).status_code == 422
    buyer = TestClient(app); buyer_token = register(buyer, 'inspect-buyer@example.org')
    assert buyer.post('/api/cad/inspect', files={'file': ('rack.stl', box_stl(1, 1, 1))}, headers=headers(buyer_token)).status_code == 403
    assert client.get('/api/listings/mine').json() == []  # Inspection stores nothing.


def test_manual_dimensions_only_without_cad_and_validated():
    client, token = host('dims@example.org')
    p = client.post('/api/listings', json={'title': 'Rack', 'cad_dimensions': [100, 50, 20]}, headers=headers(token)).json()
    assert json.loads(p['cad_dimensions']) == [100, 50, 20]
    for bad in ([0, 1, 1], [-5, 1, 1], [1, 1], [1, 1, 1, 1], [1, 1, 6000]):
        assert client.patch(f"/api/listings/{p['id']}", json={'cad_dimensions': bad}, headers=headers(token)).status_code == 422
    assert client.patch(f"/api/listings/{p['id']}", content='{"cad_dimensions":[1,1,Infinity]}', headers={**headers(token), 'Content-Type': 'application/json'}).status_code == 422
    assert client.patch(f"/api/listings/{p['id']}", json={'cad_dimensions': [90, 45, 15]}, headers=headers(token)).status_code == 200
    r = client.post(f"/api/listings/{p['id']}/cad", files={'file': ('rack.stl', box_stl(120, 80, 40))}, headers=headers(token))
    assert r.status_code == 200 and r.json()['dimensions_mm'] == [120, 80, 40]
    # Geometry is authoritative once uploaded.
    assert client.patch(f"/api/listings/{p['id']}", json={'cad_dimensions': [1, 2, 3]}, headers=headers(token)).status_code == 409
    assert json.loads(client.get(f"/api/listings/{p['id']}").json()['cad_dimensions']) == [120, 80, 40]


def test_multiple_materials_persist_and_draft_does_not_submit():
    client, token = host('materials@example.org')
    p = client.post('/api/listings', json={'title': 'Rack', 'description': 'Rack', 'category': 'Tube racks', 'compatibility': '1.5 ml', 'dimensions': '120 × 80 × 40 mm', 'material': 'PLA', 'price_cents': 1000}, headers=headers(token)).json()
    upload_test_cad(client, p['id'], token)
    # PLA €10.00, PETG €12.50, TPU €18.00, as factors of the €10.00 base.
    rules = {'materials': {'PLA': 10000, 'PETG': 12500, 'TPU': 18000}, 'discounts': {}, 'max_quantity': 50}
    r = client.put(f"/api/listings/{p['id']}/pricing", json=rules, headers=headers(token))
    assert r.status_code == 200, r.text
    assert r.json()['configurator']['pricing_materials'] == {'PLA': 10000, 'PETG': 12500, 'TPU': 18000}
    assert r.json()['status'] == 'draft'
    assert client.put(f"/api/listings/{p['id']}/pricing", json={**rules, 'materials': {'Unobtainium': 10000}}, headers=headers(token)).status_code == 422
    reopened = client.get(f"/api/listings/{p['id']}").json()
    assert reopened['configurator']['pricing_materials'] == rules['materials'] and reopened['status'] == 'draft'
    admin_queue = [x for x in TestClient(app).get('/api/listings').json()['items'] if x['id'] == p['id']]
    assert admin_queue == []  # Drafts are private.
    submitted = client.post(f"/api/listings/{p['id']}/submit", headers=headers(token))
    assert submitted.status_code == 200 and submitted.json()['status'] == 'pending'
    assert submitted.json()['configurator']['pricing_materials'] == rules['materials']
