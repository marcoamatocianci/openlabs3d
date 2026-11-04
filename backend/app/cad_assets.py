"""Content-addressed CAD storage, the processing queue, and the previews pages show.

Each unique content (SHA-256 of the bytes) is analysed and rendered at most once per stage version:

* analysis  (cache_key ANALYSIS_KEY)   geometry facts and findings, stored on cad_assets;
* render    (cache_key RENDER_PRESET)  neutral studio still, thumbnail and browser GLB under uploads/renders.

Changing a listing's title, price or colours never touches these rows; colours are applied in the browser
(assets/product-visuals.js). Previews that existed before this module (renders/<cad stem>/, including the
assembled renders of official kits) are adopted as they are, under cache_key ADOPTED, and never redone.
Bump RENDER_PRESET only when studio_scene.py or the derived images change; existing previews stay in use
until `python -m app.cad_worker --rerender` is run for them.
"""
import hashlib, json, logging, os, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from . import config, models
from .manufacturing import CAD_NAME, cad_file
from .mesh import ANALYSIS_VERSION

log = logging.getLogger(__name__)
RENDER_PRESET = 'studio-1'
ANALYSIS_KEY = f'geometry-{ANALYSIS_VERSION}'
ADOPTED = 'adopted'
PREVIEW_FILES = ('render.png', 'thumb.webp', 'model.glb')

def utcnow(): return datetime.now(timezone.utc)
def cad_dir(): return config.UPLOAD_DIR.parent / 'cad'
def renders_dir(): return config.UPLOAD_DIR.parent / 'renders'

def file_digest(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while block := stream.read(chunk): digest.update(block)
    return digest.hexdigest()

def store(data: bytes, fmt: str):
    """Write CAD bytes once under a content-derived immutable name. Returns (name, sha256, created)."""
    digest = hashlib.sha256(data).hexdigest()
    name = f'{digest[:48]}.{fmt}'
    directory = cad_dir(); directory.mkdir(parents=True, exist_ok=True)
    final = directory / name
    if final.exists(): return name, digest, False
    temporary = directory / f'.{secrets.token_hex(8)}.part'
    with open(temporary, 'xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    try: os.link(temporary, final)          # never replaces an existing file, even under a race
    except FileExistsError: pass
    finally: temporary.unlink(missing_ok=True)
    return name, digest, True

def register(db, name, digest, fmt, size):
    """The asset and file rows for a stored CAD file (idempotent). Returns the CadAsset."""
    asset = db.get(models.CadAsset, digest)
    if asset is None:
        asset = models.CadAsset(sha256=digest, format=fmt, size_bytes=size)
        if not _insert(db, asset): asset = db.get(models.CadAsset, digest)
    if db.get(models.CadFile, name) is None:
        _insert(db, models.CadFile(name=name, sha256=digest))
    return asset

def _insert(db, row):
    """Insert unless another transaction already did; True when this one did."""
    try:
        with db.begin_nested(): db.add(row)
        return True
    except IntegrityError:
        return False

def job(asset, kind, key=None):
    return next((j for j in asset.jobs if j.kind == kind and (key is None or j.cache_key == key)), None)

def enqueue(db, digest, kind, key):
    existing = db.scalar(select(models.CadJob).where(models.CadJob.sha256 == digest, models.CadJob.kind == kind, models.CadJob.cache_key == key))
    if existing: return existing
    row = models.CadJob(sha256=digest, kind=kind, cache_key=key, status='queued', next_attempt_at=utcnow())
    return row if _insert(db, row) else db.scalar(select(models.CadJob).where(models.CadJob.sha256 == digest, models.CadJob.kind == kind, models.CadJob.cache_key == key))

def has_preview(db, digest):
    return db.scalar(select(models.CadJob.id).where(models.CadJob.sha256 == digest, models.CadJob.kind == 'render', models.CadJob.status == 'ready').limit(1)) is not None

def schedule(db, digest):
    """Queue what this content still lacks. A content analysed or rendered before (for any file, listing or
    user) is not processed again."""
    asset = db.get(models.CadAsset, digest)
    if asset.analysis_version != ANALYSIS_VERSION: enqueue(db, digest, 'analyze', ANALYSIS_KEY)
    if not has_preview(db, digest): enqueue(db, digest, 'render', RENDER_PRESET)

def requeue_failed(db, digest):
    """Owner's "try again": failed stages run once more; ready and queued ones are left alone."""
    rows = db.scalars(select(models.CadJob).where(models.CadJob.sha256 == digest, models.CadJob.status == 'failed')).all()
    for row in rows:
        row.status, row.attempts, row.next_attempt_at, row.last_error = 'queued', 0, utcnow(), ''
    return len(rows)

def preview(listing):
    """The render job a listing shows, or None: the current preset, else an adopted or older ready one."""
    asset = listing.cad_file.asset if listing.cad_file else None
    if asset is None: return None
    ready = [j for j in asset.jobs if j.kind == 'render' and j.status == 'ready' and j.output_dir]
    if not ready: return None
    return next((j for j in ready if j.cache_key == RENDER_PRESET), None) or max(ready, key=lambda j: (j.finished_at or j.created_at, j.id))

def preview_state(listing):
    """'ready', 'pending', 'processing', 'failed' or None (no CAD record yet), without touching the disk."""
    asset = listing.cad_file.asset if listing.cad_file else None
    if asset is None: return None
    if preview(listing): return 'ready'
    current = job(asset, 'render', RENDER_PRESET)
    if current is None: return 'pending'
    return {'queued': 'pending'}.get(current.status, current.status)

def _legacy_status(stem):
    folder = renders_dir() / stem
    try: status = json.loads((folder / 'status.json').read_text()).get('status')
    except (OSError, ValueError): return None
    return status if status == 'ready' and all((folder / f).is_file() for f in PREVIEW_FILES) else None

def adopt(db, name, digest):
    """Record a preview that already exists for this file (renders/<stem>/) as this content's ready render."""
    stem = Path(name).stem
    if _legacy_status(stem) != 'ready': return False
    existing = db.scalar(select(models.CadJob).where(models.CadJob.sha256 == digest, models.CadJob.kind == 'render', models.CadJob.cache_key == ADOPTED))
    if existing: return False
    sizes = {f: (renders_dir() / stem / f).stat().st_size for f in PREVIEW_FILES}
    return _insert(db, models.CadJob(sha256=digest, kind='render', cache_key=ADOPTED, status='ready', output_dir=stem,
                                     result=json.dumps({'bytes': sizes, 'adopted': True}), next_attempt_at=utcnow(), finished_at=utcnow()))

def reconcile(db, limit=200):
    """Register CAD files that listings and order lines reference but that have no row yet (files from before
    this module, seeded or attached official products), adopt their previews and queue what is missing.
    Reads each such file once. Returns how many files were registered."""
    known = select(models.CadFile.name)
    names = set(db.scalars(select(models.Listing.cad_path).where(models.Listing.cad_path != '', models.Listing.cad_path.not_in(known)).limit(limit)))
    names |= set(db.scalars(select(models.OrderItem.cad_path).where(models.OrderItem.cad_path != '', models.OrderItem.cad_path.not_in(known)).limit(limit)))
    registered = 0
    for name in sorted(n for n in names if CAD_NAME.fullmatch(n)):
        path = cad_file(name)
        if not path.is_file():
            log.warning('CAD file %s is referenced but missing', name); continue
        digest = file_digest(path)
        register(db, name, digest, path.suffix[1:].lower(), path.stat().st_size)
        adopt(db, name, digest)
        schedule(db, digest)
        registered += 1
    db.commit()
    return registered
