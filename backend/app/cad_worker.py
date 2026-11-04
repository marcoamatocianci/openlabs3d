"""The CAD processing service: python -m app.cad_worker [--once] [--rerender] [--status]

Runs as its own container (compose service `worker`), never inside the web process. It claims one cad_jobs
row at a time (FOR UPDATE SKIP LOCKED on PostgreSQL, the writer lock on SQLite), so several workers never take
the same job, and works outside any database transaction. A worker that dies mid-job leaves its claim to expire;
the job is then retried. Failures retry with backoff up to MAX_ATTEMPTS and are then recorded as failed with the
reason, for the owner's "try again" (cad_assets.requeue_failed).

Stages: 'analyze' (mesh.analyze, about a second for 400k triangles) and 'render' (Blender, tens of seconds).
Renders are written to a temporary directory and moved into renders/<random id>/ only when complete, so a
preview directory, once referenced, never changes.
"""
import argparse, json, logging, os, secrets, shutil, signal, sys, time
from datetime import timedelta
from pathlib import Path
from sqlalchemy import and_, or_, select, func
from . import config, models
from .database import SessionLocal, write_lock
from .cad_assets import RENDER_PRESET, ADOPTED, cad_dir, enqueue, reconcile, renders_dir, utcnow
from .mesh import ANALYSIS_VERSION, analyze, load_mesh

log = logging.getLogger('openlabs3d.cad_worker')
MAX_ATTEMPTS = int(os.getenv('CAD_MAX_ATTEMPTS', '3'))
POLL_SECONDS = float(os.getenv('CAD_POLL_SECONDS', '2'))
RECONCILE_SECONDS = float(os.getenv('CAD_RECONCILE_SECONDS', '300'))
CLAIM_SECONDS = {'analyze': 120, 'render': int(os.getenv('CAD_RENDER_TIMEOUT_SECONDS', '300')) + 120}
stopping = False

def claim(factory=SessionLocal):
    """Take the next due job. Returns (id, kind, sha256, attempt) or None."""
    with factory() as db:
        if db.get_bind().dialect.name == 'sqlite': write_lock(db)
        now = utcnow()
        job = db.scalars(select(models.CadJob).where(or_(
                and_(models.CadJob.status == 'queued', models.CadJob.next_attempt_at <= now),
                and_(models.CadJob.status == 'processing', models.CadJob.claimed_until < now)))
            .order_by(models.CadJob.kind, models.CadJob.next_attempt_at, models.CadJob.id)   # 'analyze' first: it is quick
            .limit(1).with_for_update(skip_locked=True)).first()
        if job is None: db.rollback(); return None
        if job.attempts >= MAX_ATTEMPTS:
            # Its last attempt never reported back (the worker stopped or was killed): give up.
            job.status, job.claimed_until, job.finished_at = 'failed', None, now
            job.last_error = job.last_error or f'Stopped without finishing after {job.attempts} attempts'
            db.commit(); return claim(factory)
        job.status, job.attempts = 'processing', job.attempts + 1
        job.claimed_until, job.started_at = now + timedelta(seconds=CLAIM_SECONDS[job.kind]), now
        claimed = (job.id, job.kind, job.sha256, job.attempts)
        db.commit()
        return claimed

def finish(job_id, factory=SessionLocal, error=None, **values):
    with factory() as db:
        job = db.get(models.CadJob, job_id)
        if job is None: return
        job.claimed_until, job.finished_at = None, utcnow()
        if error is None:
            job.status, job.last_error = 'ready', ''
            for key, value in values.items(): setattr(job, key, value)
        else:
            job.last_error = error[:500]
            if job.attempts >= MAX_ATTEMPTS: job.status = 'failed'
            else: job.status, job.next_attempt_at = 'queued', utcnow() + timedelta(seconds=30 * 4 ** (job.attempts - 1))
        db.commit()

def source_path(db, digest):
    """Any stored file with this content (all are identical by definition)."""
    for name in db.scalars(select(models.CadFile.name).where(models.CadFile.sha256 == digest).order_by(models.CadFile.created_at)):
        path = cad_dir() / name
        if path.is_file(): return path
    raise FileNotFoundError(f'No stored file for content {digest[:12]}')

def run_analyze(digest, factory=SessionLocal):
    with factory() as db: path = source_path(db, digest)
    started = time.perf_counter()
    result = analyze(load_mesh(path.read_bytes(), path.suffix.lower()))
    seconds = round(time.perf_counter() - started, 3)
    with factory() as db:
        asset = db.get(models.CadAsset, digest)
        asset.analysis, asset.analysis_version = json.dumps(result, separators=(',', ':')), ANALYSIS_VERSION
        db.commit()
    return {'result': json.dumps({'seconds': seconds, 'triangles': result['triangles']})}

def run_render(digest, factory=SessionLocal):
    from .render_product import render_asset
    with factory() as db: path = source_path(db, digest)
    name = secrets.token_hex(16)
    work = renders_dir() / f'.work-{name}'
    metrics, started = {}, time.perf_counter()
    try:
        if not render_asset(path, work, metrics, image='render.webp'):
            raise RuntimeError(metrics.get('error') or 'Rendering failed')
        (work / 'status.json').unlink(missing_ok=True)
        os.rename(work, renders_dir() / name)          # complete, or not there at all
    finally:
        shutil.rmtree(work, ignore_errors=True)
    metrics['seconds'] = round(time.perf_counter() - started, 2)
    return {'output_dir': name, 'result': json.dumps(metrics)}

RUNNERS = {'analyze': run_analyze, 'render': run_render}

def work_once(factory=SessionLocal):
    """Process one job. True when there was one."""
    claimed = claim(factory)
    if claimed is None: return False
    job_id, kind, digest, attempt = claimed
    log.info('job %s: %s %s (attempt %s)', job_id, kind, digest[:12], attempt)
    try: values = RUNNERS[kind](digest, factory)
    except Exception as exc:
        log.warning('job %s: %s failed: %s', job_id, kind, exc)
        finish(job_id, factory, error=f'{type(exc).__name__}: {exc}')
    else:
        finish(job_id, factory, **values)
        log.info('job %s: %s ready %s', job_id, kind, values.get('result', ''))
    return True

def rerender(factory=SessionLocal):
    """Queue the current RENDER_PRESET for every content whose preview is older or adopted (after a look change)."""
    with factory() as db:
        write_lock(db)
        current = select(models.CadJob.sha256).where(models.CadJob.kind == 'render', models.CadJob.cache_key == RENDER_PRESET)
        digests = db.scalars(select(models.CadAsset.sha256).where(models.CadAsset.sha256.not_in(current))).all()
        for digest in digests: enqueue(db, digest, 'render', RENDER_PRESET)
        db.commit()
    return len(digests)

def status(factory=SessionLocal):
    with factory() as db:
        rows = db.execute(select(models.CadJob.kind, models.CadJob.status, func.count()).group_by(models.CadJob.kind, models.CadJob.status)).all()
        assets = db.scalar(select(func.count()).select_from(models.CadAsset))
    return {'assets': assets, 'jobs': {f'{k}:{s}': n for k, s, n in rows}}

def clean_work_dirs():
    """Unfinished render directories from a worker that was stopped mid-render."""
    for path in renders_dir().glob('.work-*'):
        if time.time() - path.stat().st_mtime > 3600: shutil.rmtree(path, ignore_errors=True)

def serve(factory=SessionLocal):
    def stop(*_):
        global stopping; stopping = True
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    renders_dir().mkdir(parents=True, exist_ok=True); cad_dir().mkdir(parents=True, exist_ok=True)
    heartbeat = Path(os.getenv('CAD_WORKER_HEARTBEAT', '/tmp/cad-worker-heartbeat'))
    last_reconcile = 0.0
    log.info('CAD worker started (preset %s, analysis v%s)', RENDER_PRESET, ANALYSIS_VERSION)
    while not stopping:
        heartbeat.touch()
        try:
            if time.monotonic() - last_reconcile > RECONCILE_SECONDS:
                with factory() as db: registered = reconcile(db)
                if registered: log.info('registered %s existing CAD files', registered)
                clean_work_dirs(); last_reconcile = time.monotonic()
            if not work_once(factory): time.sleep(POLL_SECONDS)
        except Exception:
            log.exception('CAD worker loop error'); time.sleep(10)
    log.info('CAD worker stopped')

def main(argv=None):
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--once', action='store_true', help='register files, process everything due, then exit')
    parser.add_argument('--rerender', action='store_true', help='queue the current preset for all older previews')
    parser.add_argument('--status', action='store_true', help='print queue counts as JSON')
    args = parser.parse_args(argv)
    if args.status: print(json.dumps(status())); return
    if args.rerender: print(f'queued {rerender()} renders'); return
    if args.once:
        with SessionLocal() as db: reconcile(db)
        while work_once(): pass
        print(json.dumps(status())); return
    serve()

if __name__ == '__main__':
    main()
