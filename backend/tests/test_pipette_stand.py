import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_z_collection import collection
import test_z_collection
from app.main import app
from app.mesh import inspect_mesh
from app.models import Listing, Category

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'official_products/dna_pipette_stand_6'
KEY = 'dna-pipette-stand'


def stand(client):
    items = client.get('/api/listings?category=Pipette holders').json()['items']
    return next(p for p in items if p['collection_key'] == KEY)


def test_seeded_once_with_category(collection):
    # The fixture seeds twice; the product and its category must exist exactly once.
    with test_z_collection.SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Listing).where(Listing.collection_key == KEY)) == 1
        assert db.scalar(select(func.count()).select_from(Category).where(Category.name == 'Pipette holders')) == 1


def test_appears_in_collection(collection):
    public = TestClient(app)
    p = stand(public)
    assert p['status'] == 'approved' and p['listing_type'] == 'official' and p['category'] == 'Pipette holders'
    assert 'pixel on Printables' in p['description'] and 'printables.com/model/1332410' in p['description']
    assert KEY in [i['collection_key'] for i in public.get('/api/listings?per_page=50').json()['items']]
    assert set(p['color_images']) == {'aqua-blue', 'signal-red', 'cream'}
    for url in p['color_images'].values(): assert (ROOT / url.lstrip('/')).is_file()


def test_server_quotes_each_material(collection):
    public = TestClient(app); p = stand(public)
    assert set(p['configurator']['materials']) == {'PLA', 'PETG', 'ABS'}
    for material in ('PLA', 'PETG', 'ABS'):
        q = public.post(f"/api/listings/{p['id']}/quote", json={'material': material, 'color': 'cream', 'quantity': 2}).json()
        assert q['material'] == material and q['unit_price_cents'] == p['price_cents'] and q['total_cents'] == 2 * p['price_cents']
    # A client-supplied price is never accepted as an input to the quote.
    assert public.post(f"/api/listings/{p['id']}/quote", json={'material': 'PETG', 'color': 'cream', 'quantity': 1, 'price_cents': 1}).status_code == 422


def test_configurator_model_fallback_and_attached_kit(collection, tmp_path, monkeypatch):
    public = TestClient(app); p = stand(public)
    # Before CAD is attached the configurator loads the bundled GLB.
    model_url = p['configurator']['model_url']
    assert model_url == f'/assets/models/{KEY}.glb' and (ROOT / model_url.lstrip('/')).read_bytes()[:4] == b'glTF'
    from app import attach_official_cad, config
    monkeypatch.setattr(config, 'UPLOAD_DIR', tmp_path / 'uploads')
    with test_z_collection.SessionLocal() as db:
        product = attach_official_cad.attach_kit(db, KEY)
        assert product.cad_path.endswith('.3mf')
        assert json.loads(product.cad_dimensions) == json.loads((FOLDER / 'validation.json').read_text())['host_cad_dimensions_mm']
    p = stand(public)
    visual = p['configurator']['visual']
    assert visual['status'] == 'ready' and p['configurator']['model_url'] == visual['model']
    glb = public.get(visual['model']); assert glb.status_code == 200 and glb.content[:4] == b'glTF'
    assert public.get(visual['image']).status_code == 200


def test_printable_parts_and_kit():
    report = json.loads((FOLDER / 'validation.json').read_text())
    bed = sorted(report['assumed_bed_mm'])
    names = {part['part'] for part in report['parts']}
    assert names == {'foot', 'tower_lower', 'tower_upper', 'crown'}
    for part in report['parts']:
        dims, _ = inspect_mesh((FOLDER / 'parts' / (part['part'] + '.stl')).read_bytes(), '.stl', True)
        assert all(a <= b for a, b in zip(sorted(dims), bed)), part['part']
        assert part['watertight'] and part['single_solid'] and part['floating_layers'] == 0
        assert part['overhang_area_over_limit_mm2'] < 2.0
    assert all(v for v in report['checks'].values() if isinstance(v, bool))
    kit_dims, triangles = inspect_mesh((FOLDER / 'dna_pipette_stand_6.3mf').read_bytes(), '.3mf', True)
    assert len(triangles) == sum(p['triangles'] for p in report['parts'])
    assembled, _ = inspect_mesh((FOLDER / 'assembly/dna_pipette_stand_6_assembled.stl').read_bytes(), '.stl', True)
    assert assembled == [round(v, 4) for v in report['assembled_dimensions_mm']] or max(abs(a - b) for a, b in zip(assembled, report['assembled_dimensions_mm'])) < .01
