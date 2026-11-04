"""Preview URLs for a listing, from the database (cad_assets.preview); no file is read for registered CAD.

URLs name the preview's own directory, which never changes once written, so browsers may cache them for good
(cad.visual_asset). A CAD file the worker has not registered yet (seeded, attached or from before
cad_assets) falls back to its legacy renders/<cad stem>/ folder until the worker's next reconcile.
"""
import json, re
from pathlib import PurePosixPath
from . import config
from .cad_assets import preview, preview_state

def urls(p, revision, image='render.png'):
    base = f'/api/listings/{p.id}/visuals/{revision}/'
    return {'status': 'ready', 'image': base + image, 'thumbnail': base + 'thumb.webp', 'model': base + 'model.glb'}

def visual_revision(p):
    """(preview directory, still image file name) a listing currently serves, or None."""
    if not re.fullmatch(r'[a-f0-9]{48}\.(stl|3mf)', p.cad_path or ''): return None
    if p.cad_file is not None:
        job = preview(p)
        if not job: return None
        try: image = json.loads(job.result or '{}').get('image') or 'render.png'
        except ValueError: image = 'render.png'
        return job.output_dir, image
    stem = PurePosixPath(p.cad_path).stem
    try: ready = json.loads((config.UPLOAD_DIR.parent / 'renders' / stem / 'status.json').read_text())['status'] == 'ready'
    except (OSError, ValueError, KeyError): ready = False
    return (stem, 'render.png') if ready else None

def visual_data(p):
    if not re.fullmatch(r'[a-f0-9]{48}\.(stl|3mf)', p.cad_path or ''): return {'status': 'none'}
    revision = visual_revision(p)
    if revision: return urls(p, *revision)
    if p.cad_file is not None: return {'status': preview_state(p) or 'pending'}
    stem = PurePosixPath(p.cad_path).stem
    try: status = json.loads((config.UPLOAD_DIR.parent / 'renders' / stem / 'status.json').read_text())['status']
    except (OSError, ValueError, KeyError): status = 'pending'
    return {'status': status}
