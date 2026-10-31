"""Three-part pipette holder (official_products/pipette_holder): printable parts, the kit hosts download, and
attaching the kit to an existing official listing in place of its single-part model."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_z_collection import collection
import test_z_collection
from app.main import app
from app.mesh import inspect_mesh
from app.models import Listing, User

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'official_products/pipette_holder'
REPORT = json.loads((FOLDER / 'validation.json').read_text())


def test_three_parts_fit_the_smallest_printer_and_form_the_kit():
    bed = sorted(REPORT['assumed_bed_mm'])
    assert bed == [180.0, 180.0, 180.0]
    assert [p['part'] for p in REPORT['parts']] == ['base', 'column', 'head']
    triangles = 0
    for part in REPORT['parts']:
        dims, mesh = inspect_mesh((FOLDER / 'parts' / (part['part'] + '.stl')).read_bytes(), '.stl', True)
        assert all(a <= b for a, b in zip(sorted(dims), bed)), part['part']
        assert part['mesh']['watertight'] and part['mesh']['single_body'] and part['floating_layers_0_2mm'] == 0
        assert part['overhang_area_over_limit_plus_tessellation_tolerance_mm2'] < 1.0
        triangles += len(mesh)
    _, kit = inspect_mesh((FOLDER / 'pipette_holder.3mf').read_bytes(), '.3mf', True)
    assert len(kit) == triangles
    assert all(j['spigot_core_clears_socket'] and j['other_overlap_mm3'] < 1e-3 for j in REPORT['joints'])
    fit = REPORT['fit_checks_against_stand_in_pipette']
    assert fit['envelope_intersection_mm3'] == 0 and fit['fitted_tip_end_above_plinth_mm'] >= 10
    assert REPORT['assembled_dimensions_mm'][2] == 280


def test_kit_replaces_the_model_of_an_existing_official_listing(collection):
    from app import attach_official_cad
    with test_z_collection.SessionLocal() as db:
        admin = db.scalar(select(User).where(User.role == 'admin'))
        listing = Listing(owner_id=admin.id, title='Pipette Holder Tree', description='A fantastic pipette holder', category='Pipette holders',
                          price_cents=1500, material='PETG', dimensions='164.11 × 144 × 212 mm', compatibility='pipettes',
                          listing_type='official', status='approved', featured=True, approved_by=admin.id,
                          cad_path='a' * 48 + '.stl', cad_dimensions='[164.1067, 144.0, 212.0]',
                          configuration='{"materials": {"PETG": 10000, "PLA": 10000}}')
        db.add(listing); db.commit()
        listing_id, version = listing.id, listing.version
        product = attach_official_cad.attach_kit_files(db, listing, FOLDER, describe=True)
        assert product.cad_path.endswith('.3mf') and product.version > version
        assert json.loads(product.cad_dimensions) == REPORT['host_cad_dimensions_mm']
        assert product.dimensions == '164 × 144 × 280 mm (assembled, 3 printed parts)'
        # Only the model changed: the owner's wording, price and publication stay as they were.
        assert (product.title, product.description, product.price_cents, product.status) == ('Pipette Holder Tree', 'A fantastic pipette holder', 1500, 'approved')
    public = TestClient(app)
    p = public.get(f'/api/listings/{listing_id}').json()
    assert p['has_cad'] and p['cad_format'] == '3MF'
    visual = p['configurator']['visual']
    assert visual['status'] == 'ready' and p['configurator']['model_url'] == visual['model']
    assert public.get(visual['model']).content[:4] == b'glTF' and public.get(visual['image']).status_code == 200
    # The kit itself stays restricted to the owner and administrators.
    assert public.get(f'/api/listings/{listing_id}/cad').status_code == 401
    assert collection.get(f'/api/listings/{listing_id}/cad').content == (FOLDER / 'pipette_holder.3mf').read_bytes()
