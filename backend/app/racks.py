"""Design Your Rack: the API between the configurator and the marketplace.

  catalog   tube profiles, presets and fonts
  plan      layout, structure, checks, estimates and what can be bought, in milliseconds, no CAD
  builds    the authoritative CAD model, made once per geometry by the worker
  designs   a buyer's saved drafts
  listing   turns a finished design into a product the existing cart, checkout and job system can sell

A rack is sold as a private, immutable listing: one per buyer and geometry. pricing.quote(), the cart's price
confirmation, checkout, availability.job_ineligibility() and the host's download route all work on it unchanged, so
there is no second ordering system. The client never supplies a price or a position that is not checked again here.
"""
import json, os, secrets, shutil
from functools import lru_cache
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from . import availability, cad_assets, database, models
from .database import get_db
from .main import admin, admin_mutate, current, fail, get_listing, mutate, require, same_origin, throttle
from .manufacturing import MANUFACTURING_STATES
from .mesh import ANALYSIS_VERSION
from .pricing import UNAVAILABLE, quote
from .rack import estimate, planner
from .rack.profiles import PROFILES
from .rack.rules import RULES
from .rack.queue import build_path, request_build
from .rack.schema import RackConfiguration

router = APIRouter(prefix='/api', tags=['racks'])
HASH = Annotated[str, Path(pattern=r'^[a-f0-9]{64}$')]
MAX_DESIGNS = 200
MAX_QUEUE = 40
RACK_PREVIEW_KEY = 'rack-1'

def _client(request): return request.headers.get('x-real-ip', request.client.host if request.client else 'unknown')

@lru_cache(maxsize=256)
def _cached_plan(config_json, volumes):
    """Undo, switching back and forth, and several people starting from one preset all ask for the same plan.
    Results are shared between requests: never change one in place."""
    return planner.plan(RackConfiguration.model_validate_json(config_json), list(volumes))

def _plan(db, config, viewer_id=None):
    """Plan against the printers that can take this viewer's chosen finish, with what the rack could be bought in."""
    every = availability.rack_envelopes(db, exclude_host=viewer_id)
    able = availability.rack_envelopes(db, config.material, config.color, viewer_id) if config.material else every
    # A finish no printer has still gets a layout, for any printer; the selection below says it cannot be bought yet.
    volumes = tuple((e['x'], e['y'], e['z']) for e in (able or every))
    geometry = config.model_copy(update={'material': '', 'color': ''})
    result = _cached_plan(geometry.model_dump_json(), volumes)
    rates = estimate.load_rates(db)
    if result.get('metrics') and result.get('spec'):
        m = result['metrics']
        result = {**result, 'estimates': planner.estimates(m['volume_mm3'], m['area_mm2'], m['holes'], bool(result['spec'].get('label')), result['spec']['style'], rates)}
    return {**result, 'availability': _availability(db, result, config, viewer_id, able)}

NO_HOST = 'No Printing Host currently supports this combination of dimensions, material, and color. Try choosing a smaller rack or another material.'

def _availability(db, result, config, viewer_id, able):
    """What this rack can be bought in, which printing areas are on offer, and whether the chosen finish can be made."""
    usable = lambda e: {**e, 'usable': [e['x'] - 2 * RULES.printer_margin_mm, e['y'] - 2 * RULES.printer_margin_mm, e['z'] - RULES.printer_margin_z_mm]}
    data = {'materials': {}, 'own_printers_only': False, 'envelopes': [usable(e) for e in able], 'selection': None}
    if not result.get('dims') or not result.get('estimates'): return data
    offered = availability.rack_combinations(db, result['dims'], exclude_host=viewer_id)
    data['materials'] = {m: {'colors': colors, **result['estimates']['materials'][m]} for m, colors in offered.items() if m in result['estimates']['materials']}
    data['own_printers_only'] = bool(viewer_id) and not data['materials'] and bool(availability.rack_combinations(db, result['dims']))
    if config.material and config.color:
        hosts = availability.rack_hosts(db, result['dims'], config.material, config.color, viewer_id)
        data['selection'] = {'material': config.material, 'color': config.color, 'hosts': hosts, 'ok': hosts > 0, 'message': '' if hosts else NO_HOST}
    return data

def _public(result):
    return {k: v for k, v in result.items() if k != 'spec'}

def _require_buildable(result):
    if not result['ok']:
        first = next(i for i in result['issues'] if i['level'] == 'error')
        fail(422, {'code': 'invalid_rack', 'message': first['message'], 'issues': result['issues']})

@router.get('/racks/catalog')
def rack_catalog(response: Response):
    response.headers['Cache-Control'] = 'public, max-age=300'
    return planner.catalog()

@router.post('/racks/plan')
def rack_plan(body: RackConfiguration, request: Request, response: Response):
    """No write lock (it writes nothing, and it runs on every change the buyer makes), so it opens its own session."""
    same_origin(request)
    throttle(('rack-plan', _client(request)), 1800, 900)
    response.headers['Cache-Control'] = 'no-store'
    with database.SessionLocal() as db:
        viewer = current(request, db)
        return _public(_plan(db, body, viewer[0].id if viewer else None))

def build_data(db, row):
    data = {'hash': row.config_hash, 'status': row.status}
    if row.status in ('queued', 'processing'): return data
    if row.status in ('failed', 'abandoned'):
        return {**data, 'error': 'This rack could not be generated. Change the design or try again.' if row.status == 'failed' else '', 'detail': row.last_error[:300] if row.status == 'failed' else ''}
    stored = json.loads(row.result or '{}')
    spec = json.loads(row.spec)
    metrics = stored.get('metrics', {})
    labelled = bool(spec.get('label'))
    return {**data, 'metrics': {**metrics, 'basis': 'cad'}, 'report': stored.get('report', {}), 'notes': stored.get('notes', []),
            'estimates': planner.estimates(metrics['volume_mm3'], metrics['area_mm2'], metrics['holes'], labelled, spec['style'], estimate.load_rates(db)),
            'preview_url': f'/api/racks/builds/{row.config_hash}/preview.glb', 'thumbnail_url': f'/api/racks/builds/{row.config_hash}/thumb.webp'}

@router.post('/racks/builds', status_code=202)
def create_build(body: RackConfiguration, request: Request, db: Session = Depends(get_db)):
    """Ask for the exact CAD model of a configuration. Identical geometry is built once, for everyone."""
    same_origin(request)
    viewer = current(request, db)
    result = _plan(db, body, viewer[0].id if viewer else None)
    _require_buildable(result)
    if not db.get(models.RackBuild, result['hash']):
        # Only new geometry costs CPU, so only that is limited.
        if viewer: throttle(('rack-build-account', viewer[0].id), 120, 900)
        else: throttle(('rack-build-ip', _client(request)), 40, 900)
        waiting = db.scalar(select(func.count()).select_from(models.RackBuild).where(models.RackBuild.status.in_(('queued', 'processing'))))
        if waiting >= MAX_QUEUE: fail(503, 'The rack generator is busy. Try again in a minute.')
    row = request_build(db, result['hash'], result['spec'])
    db.commit()
    return build_data(db, row)

@router.get('/racks/builds/{digest}')
def read_build(digest: HASH, response: Response, db: Session = Depends(get_db)):
    """Polling also tells the worker somebody is still waiting; builds nobody waits for are dropped."""
    row = db.get(models.RackBuild, digest)
    if row is None: fail(404, 'Build not found')
    now = cad_assets.utcnow()
    seen = row.last_requested_at if row.last_requested_at.tzinfo else row.last_requested_at.replace(tzinfo=now.tzinfo)
    if (now - seen).total_seconds() > 15:
        row.last_requested_at = now; db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return build_data(db, row)

def _preview_file(digest, name, media):
    path = build_path(digest) / name
    if not path.is_file(): fail(404, 'Preview unavailable')
    # A hash names one geometry for good, and previews are coarser than the manufacturing file. Only someone who
    # already knows the configuration can name them; there is no listing of builds.
    return FileResponse(path, media_type=media, headers={'Cache-Control': 'public, max-age=31536000, immutable', 'X-Content-Type-Options': 'nosniff'})

@router.get('/racks/builds/{digest}/preview.glb')
def build_preview(digest: HASH): return _preview_file(digest, 'preview.glb', 'model/gltf-binary')

@router.get('/racks/builds/{digest}/thumb.webp')
def build_thumbnail(digest: HASH): return _preview_file(digest, 'thumb.webp', 'image/webp')

# Saved designs ---------------------------------------------------------------------------------------------------
class DesignInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(default='', max_length=80)
    config: RackConfiguration

class DesignRename(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)

def _design(db, design_id, auth):
    row = db.get(models.RackDesign, design_id)
    # Somebody else's design looks the same as one that does not exist.
    if row is None or row.user_id != auth[0].id: fail(404, 'Design not found')
    return row

def _default_name(db, user_id, result):
    parts = [p for p in result.get('summary', [])]
    if len(parts) == 1: stem = f"{parts[0]['nominal_ml']:g} mL Rack"
    elif len(parts) == 2: stem = ' / '.join(f"{p['nominal_ml']:g} mL" for p in parts) + ' Mixed Rack'
    else: stem = 'My Custom Rack'
    taken = set(db.scalars(select(models.RackDesign.name).where(models.RackDesign.user_id == user_id)))
    if stem not in taken and parts: return stem
    n = 1
    while f'{stem} {n:02d}' in taken: n += 1
    return f'{stem} {n:02d}'

def _purchased(db, design):
    rows = db.execute(select(models.OrderItem, models.Order).join(models.Order, models.Order.id == models.OrderItem.order_id).join(models.Listing, models.Listing.id == models.OrderItem.listing_id)
                      .where(models.Listing.rack_design_id == design.id, models.Order.buyer_id == design.user_id).order_by(models.Order.created_at.desc()).limit(20)).all()
    return [{'item_id': i.id, 'order_reference': o.reference, 'order_id': o.id, 'status': o.status, 'material': i.material, 'color': i.color, 'color_hex': i.color_hex, 'quantity': i.quantity, 'price_cents': i.price_cents, 'dimensions': i.dimensions, 'created_at': o.created_at} for i, o in rows]

def design_data(db, row, full=True):
    data = {'id': row.id, 'name': row.name, 'hash': row.config_hash, 'config': json.loads(row.config), 'created_at': row.created_at, 'updated_at': row.updated_at,
            'thumbnail_url': f'/api/racks/builds/{row.config_hash}/thumb.webp' if row.config_hash and (build_path(row.config_hash) / 'thumb.webp').is_file() else ''}
    if full: data['purchased'] = _purchased(db, row)
    return data

@router.get('/racks/designs')
def list_designs(auth=Depends(require), db: Session = Depends(get_db)):
    rows = db.scalars(select(models.RackDesign).where(models.RackDesign.user_id == auth[0].id).order_by(models.RackDesign.updated_at.desc(), models.RackDesign.id.desc())).all()
    return [design_data(db, row) for row in rows]

def _save_new(db, auth, config, name):
    count = db.scalar(select(func.count()).select_from(models.RackDesign).where(models.RackDesign.user_id == auth[0].id))
    if count >= MAX_DESIGNS: fail(409, f'You can keep up to {MAX_DESIGNS} designs. Delete one you no longer need.')
    result = _plan(db, config, auth[0].id)
    row = models.RackDesign(user_id=auth[0].id, name=name or _default_name(db, auth[0].id, result), config=config.model_dump_json(), config_hash=result['hash'] or '')
    db.add(row); db.commit()
    return row

@router.post('/racks/designs', status_code=201)
def create_design(body: DesignInput, auth=Depends(mutate), db: Session = Depends(get_db)):
    return design_data(db, _save_new(db, auth, body.config, body.name))

@router.get('/racks/designs/{design_id}')
def read_design(design_id: int, auth=Depends(require), db: Session = Depends(get_db)):
    return design_data(db, _design(db, design_id, auth))

@router.put('/racks/designs/{design_id}')
def update_design(design_id: int, body: DesignInput, auth=Depends(mutate), db: Session = Depends(get_db)):
    """Editing a design changes this draft only. What was ordered lives in its own immutable listing and order line."""
    row = _design(db, design_id, auth)
    row.config = body.config.model_dump_json()
    row.config_hash = _plan(db, body.config, auth[0].id)['hash'] or ''
    if body.name: row.name = body.name
    db.commit()
    return design_data(db, row)

@router.patch('/racks/designs/{design_id}')
def rename_design(design_id: int, body: DesignRename, auth=Depends(mutate), db: Session = Depends(get_db)):
    row = _design(db, design_id, auth); row.name = body.name; db.commit()
    return design_data(db, row)

@router.post('/racks/designs/{design_id}/duplicate', status_code=201)
def duplicate_design(design_id: int, auth=Depends(mutate), db: Session = Depends(get_db)):
    row = _design(db, design_id, auth)
    return design_data(db, _save_new(db, auth, RackConfiguration.model_validate_json(row.config), f'{row.name[:70]} copy'))

@router.delete('/racks/designs/{design_id}')
def delete_design(design_id: int, auth=Depends(mutate), db: Session = Depends(get_db)):
    """Removes the draft; orders made from it keep everything they need."""
    row = _design(db, design_id, auth)
    db.execute(update(models.Listing).where(models.Listing.rack_design_id == row.id, models.Listing.owner_id == auth[0].id).values(rack_design_id=None, version=models.Listing.version + 1))
    db.delete(row); db.commit()
    return {'ok': True}

def _ordered_item(db, item_id, auth):
    item = db.get(models.OrderItem, item_id)
    order = db.get(models.Order, item.order_id) if item else None
    if item is None or order.buyer_id != auth[0].id or not item.rack_snapshot: fail(404, 'Rack order not found')
    return item

@router.post('/racks/orders/{item_id}/design', status_code=201)
def design_from_order(item_id: int, auth=Depends(mutate), db: Session = Depends(get_db)):
    """Start a new draft from a purchased rack, leaving the order untouched."""
    item = _ordered_item(db, item_id, auth)
    config = RackConfiguration.model_validate(json.loads(item.rack_snapshot)['config'])
    return design_data(db, _save_new(db, auth, config, f'{item.title[:62]} (reorder)'))

@router.post('/racks/orders/{item_id}/reorder')
def reorder_line(item_id: int, auth=Depends(mutate), db: Session = Depends(get_db)):
    """What the cart needs to order the same rack again: the same geometry, material and colour, at today's price."""
    item = _ordered_item(db, item_id, auth)
    listing = get_listing(db, item.listing_id)
    _reprice(db, listing)
    q = quote(listing, item.material, item.color, 1, auth[0].id)
    db.commit()
    return {'listing_id': listing.id, 'title': listing.title, **q}

# Selling a finished design ---------------------------------------------------------------------------------------
class ListingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    config: RackConfiguration
    design_id: int | None = None
    name: str = Field(default='', max_length=80)
    material: str = Field(max_length=200)
    color: str = Field(max_length=48)
    quantity: int = Field(default=1, ge=1, le=50, strict=True)

STYLE_NAMES = {'lightweight': 'Lightweight', 'premium': 'Premium'}

def _pin_preview(db, digest, source):
    """Previews a basket and a job show, under the same immutable renders/ store as other products."""
    existing = db.scalar(select(models.CadJob).where(models.CadJob.sha256 == digest, models.CadJob.kind == 'render', models.CadJob.status == 'ready').limit(1))
    if existing: return
    name = secrets.token_hex(16)
    work = cad_assets.renders_dir() / f'.work-{name}'
    work.mkdir(parents=True)
    try:
        for source_name, target in (('render.webp', 'render.webp'), ('thumb.webp', 'thumb.webp'), ('preview.glb', 'model.glb')): shutil.copyfile(source / source_name, work / target)
        os.rename(work, cad_assets.renders_dir() / name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    db.add(models.CadJob(sha256=digest, kind='render', cache_key=RACK_PREVIEW_KEY, status='ready', output_dir=name, result=json.dumps({'image': 'render.webp', 'rack': True}), next_attempt_at=cad_assets.utcnow(), finished_at=cad_assets.utcnow()))

def _store_manufacturing_files(db, digest, analysis):
    """Copy a build to the immutable CAD store: from here on it no longer depends on the build cache."""
    source = build_path(digest)
    files = {}
    for suffix, fmt in (('rack.stl', 'stl'), ('rack.3mf', '3mf')):
        data = (source / suffix).read_bytes()
        name, sha, _ = cad_assets.store(data, fmt)
        asset = cad_assets.register(db, name, sha, fmt, len(data))
        files[fmt] = {'name': name, 'sha256': sha, 'bytes': len(data)}
        if fmt == 'stl' and asset.analysis_version != ANALYSIS_VERSION:
            asset.analysis, asset.analysis_version = json.dumps(analysis, separators=(',', ':')), ANALYSIS_VERSION
    db.flush()
    _pin_preview(db, files['stl']['sha256'], source)
    return files

def _pricing(db, metrics, spec):
    base, factors = estimate.price_rules(metrics['volume_mm3'], metrics['area_mm2'], metrics['holes'], bool(spec.get('label')), spec['style'], estimate.load_rates(db))
    return base, json.dumps({'materials': factors, 'discounts': {}, 'max_quantity': 20}, sort_keys=True)

def _reprice(db, listing):
    """Bring a rack's listing to today's rates. The geometry never moves; the basket's price review shows any change."""
    snapshot = json.loads(listing.rack_snapshot)
    base, rules = _pricing(db, snapshot['metrics'], snapshot['spec'])
    if listing.price_cents != base or listing.configuration != rules: listing.price_cents, listing.configuration = base, rules

def private_listing(db, user, config, result, build, design_id, name=''):
    """The buyer's internal record for this exact geometry, created once. Its size and price come from the measured solid.
    It exists so the cart, checkout and job system can sell the rack; no page presents it as a product."""
    stored = json.loads(build.result)
    metrics = stored['metrics']
    spec = result['spec']
    base, rules = _pricing(db, metrics, spec)
    listing = db.scalar(select(models.Listing).where(models.Listing.owner_id == user.id, models.Listing.rack_hash == result['hash']))
    if listing is not None:
        if listing.removed or listing.status != 'approved': fail(409, 'This rack is no longer available.')
        _reprice(db, listing)
        snapshot = json.loads(listing.rack_snapshot)
        if name and snapshot.get('name') != name or (design_id and snapshot.get('design_id') != design_id):
            # Only labels for later orders: lines already ordered hold their own copy.
            snapshot.update(name=name or snapshot.get('name', ''), design_id=design_id or snapshot.get('design_id'))
            listing.rack_snapshot = json.dumps(snapshot, separators=(',', ':'))
            if design_id: listing.rack_design_id = design_id
        return listing
    files = _store_manufacturing_files(db, result['hash'], stored['analysis'])
    text = planner.summary_text(result['summary'])
    title = f'Custom rack: {text} ({STYLE_NAMES[spec["style"]]})'[:160]
    w, d, h = metrics.get('dims_mm') or result['dims']       # the solid decides, not the plan: embossed letters add depth
    factors = json.loads(rules)['materials']
    snapshot = {'schema_version': 1, 'name': name, 'hash': result['hash'], 'geometry_version': result['spec']['geometry_version'], 'library_version': planner.LIBRARY_VERSION, 'design_id': design_id,
                'config': config.model_dump(mode='json'), 'spec': spec, 'summary': result['summary'], 'profiles': {p['profile_id']: PROFILES[p['profile_id']].public() for p in result['summary']},
                'metrics': metrics, 'report': stored['report'], 'files': files, 'pricing': {'base_cents': base, 'factors': factors, 'status': 'validated' if estimate.load_rates(db).commercially_validated else 'prototype'}}
    listing = models.Listing(owner_id=user.id, title=title, description=f'A custom rack designed in Design Your Rack: {text}.', category='Tube racks', price_cents=base, material=next(iter(factors)),
                             dimensions=f'{w:g} × {d:g} × {h:g} mm', compatibility=text[:300], listing_type='official', status='approved', configuration=rules, cad_path=files['stl']['name'], cad_dimensions=json.dumps([w, d, h]),
                             published_at=cad_assets.utcnow(), rack_hash=result['hash'], rack_snapshot=json.dumps(snapshot, separators=(',', ':')), rack_design_id=design_id)
    db.add(listing); db.flush()
    db.add(models.Activity(actor_id=user.id, action='rack.listed', subject=f'listing:{listing.id}', detail=result['hash'][:16]))
    return listing

@router.post('/racks/listing')
def create_listing(body: ListingRequest, auth=Depends(mutate), db: Session = Depends(get_db)):
    """Everything the basket needs, for a design whose CAD model is ready and has passed its checks. The price comes back
    from the existing quote; the browser then adds this listing to the basket like any other product."""
    if auth[0].role == 'admin': fail(403, 'Administrators use marketplace order management')
    design_id = _design(db, body.design_id, auth).id if body.design_id else None
    result = _plan(db, body.config, auth[0].id)
    _require_buildable(result)
    if result['fit']['state'] != 'fits':
        fail(422, {'code': 'no_printer', 'message': NO_HOST, 'issues': result['issues']})
    build = db.get(models.RackBuild, result['hash'])
    if build is None or build.status != 'ready' or not (build_path(result['hash']) / 'rack.stl').is_file():
        fail(409, {'code': 'build_pending', 'message': 'The exact model is still being generated.', 'status': build.status if build else 'missing'})
    listing = private_listing(db, auth[0], body.config, result, build, design_id, body.name)
    db.flush()
    # Measured dimensions, this exact finish and today's hosts, by the rule checkout and job acceptance will use again.
    try: q = quote(listing, body.material, body.color, body.quantity, auth[0].id)
    except HTTPException as exc:
        db.rollback()
        fail(422, {'code': 'no_host', 'message': NO_HOST if exc.detail == UNAVAILABLE else exc.detail})
    db.commit()
    return {'listing_id': listing.id, 'hash': result['hash'], 'title': listing.title, **q}

# For hosts ---------------------------------------------------------------------------------------------------------
@router.get('/jobs/{job_id}/rack')
def job_rack(job_id: int, auth=Depends(require), db: Session = Depends(get_db)):
    """The specification of a custom rack as sold, under the same rule as its manufacturing files."""
    job = db.get(models.PrintingJob, job_id)
    user = auth[0]
    if not job or (user.role != 'admin' and job.host_id != user.id) or not job.item.rack_snapshot: fail(404, 'Rack specification not found')
    if user.role != 'admin':
        from .operations import active_host
        active_host(auth, db)
        if job.status not in MANUFACTURING_STATES: fail(403, 'The specification is available only while your job is accepted, printing or ready for delivery')
    rack = json.loads(job.item.rack_snapshot)
    return {k: rack[k] for k in ('hash', 'geometry_version', 'summary', 'profiles', 'metrics', 'report')} | {'style': rack['spec']['style'], 'dims_mm': rack['spec']['dims'], 'label': rack['spec'].get('label'), 'tubes': rack['spec']['tubes'], 'orientation': 'upright, base on the bed'}

# For administrators -------------------------------------------------------------------------------------------------
@router.get('/admin/rack-pricing')
def read_rack_pricing(auth=Depends(admin), db: Session = Depends(get_db)):
    return estimate.load_rates(db).model_dump()

@router.put('/admin/rack-pricing')
def save_rack_pricing(body: estimate.Rates, auth=Depends(admin_mutate), db: Session = Depends(get_db)):
    """New rates reach racks the next time they are added to a basket; orders keep the price they were placed at."""
    if set(body.material_eur_per_kg) != set(estimate.MATERIALS) or any(not 0 <= v <= 1000 for v in body.material_eur_per_kg.values()):
        fail(422, 'Give a cost between 0 and 1000 EUR/kg for each of: ' + ', '.join(estimate.MATERIALS))
    row = db.get(models.MarketplaceSetting, estimate.SETTING_KEY)
    if row is None: row = models.MarketplaceSetting(key=estimate.SETTING_KEY, value=''); db.add(row)
    row.value = body.model_dump_json()
    db.add(models.Activity(actor_id=auth[0].id, action='rack.pricing_saved', subject='marketplace'))
    db.commit()
    return body.model_dump()
