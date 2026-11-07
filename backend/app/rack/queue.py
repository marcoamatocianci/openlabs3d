"""The durable queue and cache for rack builds. A build is keyed by the hash of its spec, so identical racks are built
once, whoever asks. The worker claims one at a time (FOR UPDATE SKIP LOCKED on PostgreSQL, the writer lock on SQLite)
and runs CAD in a subprocess with CPU, memory and wall-clock limits, so a bad build cannot take the worker down.

Builds nobody is waiting for are skipped or stopped: the browser's polling keeps last_requested_at fresh.
Build directories are caches. Anything sold is copied to the immutable CAD store at checkout, so old builds can go.
"""
import json, logging, os, resource, secrets, shutil, signal, subprocess, sys, time
from datetime import timedelta
from pathlib import Path
from sqlalchemy import and_, or_, select
from .. import config, models
from ..cad_assets import utcnow
from ..database import SessionLocal, write_lock

log = logging.getLogger('openlabs3d.rack')
MAX_ATTEMPTS = int(os.getenv('RACK_MAX_ATTEMPTS', '2'))
TIMEOUT = int(os.getenv('RACK_BUILD_TIMEOUT_SECONDS', '180'))
MEMORY_MB = int(os.getenv('RACK_BUILD_MEMORY_MB', '4096'))
ABANDON_SECONDS = int(os.getenv('RACK_ABANDON_SECONDS', '120'))
RETENTION_DAYS = int(os.getenv('RACK_BUILD_RETENTION_DAYS', '14'))
RETRY_FAILED_SECONDS = int(os.getenv('RACK_RETRY_FAILED_SECONDS', '600'))     # a failure may have been the machine's

def builds_dir(): return config.UPLOAD_DIR.parent / 'rack-builds'
def build_path(digest): return builds_dir() / digest

def _aware(moment):
    from datetime import timezone
    return moment if moment is None or moment.tzinfo else moment.replace(tzinfo=timezone.utc)

def request_build(db, digest, spec):
    """Ask for a build (idempotent): returns its row. A failed or abandoned build asked for again runs again."""
    row = db.get(models.RackBuild, digest)
    now = utcnow()
    if row is None:
        row = models.RackBuild(config_hash=digest, spec=json.dumps(spec, separators=(',', ':')), status='queued', next_attempt_at=now, last_requested_at=now)
        db.add(row); db.flush()
        return row
    row.last_requested_at = now
    retry = row.status == 'failed' and row.finished_at is not None and (now - _aware(row.finished_at)).total_seconds() > RETRY_FAILED_SECONDS
    if retry or row.status == 'abandoned' or (row.status == 'ready' and not (build_path(digest) / 'rack.stl').is_file()):
        row.status, row.attempts, row.next_attempt_at, row.last_error, row.result = 'queued', 0, now, '', '{}'
    return row

def claim(factory=SessionLocal):
    with factory() as db:
        if db.get_bind().dialect.name == 'sqlite': write_lock(db)
        now = utcnow()
        # Waited for too long by nobody: released without any CAD work.
        stale = now - timedelta(seconds=ABANDON_SECONDS)
        for row in db.scalars(select(models.RackBuild).where(models.RackBuild.status == 'queued', models.RackBuild.last_requested_at < stale).limit(50)):
            row.status = 'abandoned'
        job = db.scalars(select(models.RackBuild).where(or_(
                and_(models.RackBuild.status == 'queued', models.RackBuild.next_attempt_at <= now),
                and_(models.RackBuild.status == 'processing', models.RackBuild.claimed_until < now)))
            .order_by(models.RackBuild.last_requested_at.desc()).limit(1).with_for_update(skip_locked=True)).first()
        if job is None: db.commit(); return None
        if job.attempts >= MAX_ATTEMPTS:
            job.status, job.claimed_until = 'failed', None
            job.last_error = job.last_error or 'The build stopped without finishing'
            db.commit(); return claim(factory)
        job.status, job.attempts, job.claimed_until = 'processing', job.attempts + 1, now + timedelta(seconds=TIMEOUT + 60)
        claimed = (job.config_hash, job.spec)
        db.commit()
        return claimed

def _limits():
    os.nice(5)
    if MEMORY_MB: resource.setrlimit(resource.RLIMIT_AS, (MEMORY_MB << 20, MEMORY_MB << 20))
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT + 30, TIMEOUT + 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def _still_wanted(digest, factory):
    with factory() as db:
        row = db.get(models.RackBuild, digest)
        return row is not None and _aware(row.last_requested_at) >= utcnow() - timedelta(seconds=ABANDON_SECONDS)

def _run(digest, spec, work, factory):
    """Run the build subprocess. Returns (exit code, stdout, stderr), or None when it was stopped as abandoned."""
    spec_file = work / 'spec.json'; spec_file.write_text(spec)
    process = subprocess.Popen([sys.executable, '-m', 'app.rack.build', str(spec_file), str(work)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               cwd=str(Path(__file__).resolve().parents[2]), preexec_fn=_limits, start_new_session=True)
    started = time.monotonic()
    while True:
        try:
            out, err = process.communicate(timeout=2.0)
            return process.returncode, out, err
        except subprocess.TimeoutExpired:
            pass
        overdue = time.monotonic() - started > TIMEOUT
        if overdue or not _still_wanted(digest, factory):
            os.killpg(process.pid, signal.SIGKILL); process.wait()
            if overdue: raise TimeoutError(f'The build took longer than {TIMEOUT} s')
            return None

def _finish(digest, factory, **values):
    with factory() as db:
        row = db.get(models.RackBuild, digest)
        if row is None: return
        row.claimed_until = None
        for key, value in values.items(): setattr(row, key, value)
        db.commit()

def work_once(factory=SessionLocal):
    """Build one rack. True when there was one."""
    claimed = claim(factory)
    if claimed is None: return False
    digest, spec = claimed
    builds_dir().mkdir(parents=True, exist_ok=True)
    work = builds_dir() / f'.work-{secrets.token_hex(8)}'
    work.mkdir()
    log.info('rack %s: building', digest[:12])
    try:
        outcome = _run(digest, spec, work, factory)
        if outcome is None:
            _finish(digest, factory, status='abandoned'); log.info('rack %s: abandoned', digest[:12]); return True
        code, out, err = outcome
        if code == 3:   # the geometry was refused; retrying gives the same answer
            detail = json.loads(out.strip().splitlines()[-1])
            _finish(digest, factory, status='failed', last_error=detail['error'][:500], result=json.dumps({'checks': detail.get('checks', [])}), finished_at=utcnow())
            log.warning('rack %s: refused: %s', digest[:12], detail['error']); return True
        if code != 0: raise RuntimeError((err or f'exit code {code}').strip()[-400:])
        result = (work / 'result.json').read_text()
        final = build_path(digest)
        if final.exists(): shutil.rmtree(final)
        (work / 'spec.json').unlink(missing_ok=True); (work / 'result.json').unlink(missing_ok=True)
        os.rename(work, final)
        _finish(digest, factory, status='ready', result=result, last_error='', finished_at=utcnow())
        log.info('rack %s: ready', digest[:12])
    except Exception as exc:
        with factory() as db:
            row = db.get(models.RackBuild, digest)
            attempts = row.attempts if row else MAX_ATTEMPTS
        message = f'{type(exc).__name__}: {exc}'[:500]
        if attempts >= MAX_ATTEMPTS: _finish(digest, factory, status='failed', last_error=message, finished_at=utcnow())
        else: _finish(digest, factory, status='queued', last_error=message, next_attempt_at=utcnow() + timedelta(seconds=5))
        log.warning('rack %s: %s', digest[:12], message)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return True

def clean(factory=SessionLocal):
    """Remove leftovers of interrupted work and builds nobody has asked for in RETENTION_DAYS. Sold racks are safe:
    their files were copied to the CAD store when the rack was offered for sale."""
    if builds_dir().exists():
        for path in builds_dir().glob('.work-*'):
            if time.time() - path.stat().st_mtime > 3600: shutil.rmtree(path, ignore_errors=True)
    limit = utcnow() - timedelta(days=RETENTION_DAYS)
    with factory() as db:
        write_lock(db)
        rows = db.scalars(select(models.RackBuild).where(models.RackBuild.last_requested_at < limit, models.RackBuild.status != 'processing').limit(200)).all()
        for row in rows:
            shutil.rmtree(build_path(row.config_hash), ignore_errors=True)
            db.delete(row)
        db.commit()
    return len(rows)
