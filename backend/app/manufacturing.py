"""Immutable manufacturing files and who may download them.

CAD uploads are stored once under a random or content-derived name (cad/<48 hex>.stl|3mf) and are
never overwritten or deleted, so a name identifies one exact file forever. Each order line records
the name, its SHA-256 and the listing revision when the order is placed; hosts download that file,
never the listing's current one.
"""
import hashlib, re, threading
from . import config

CAD_NAME = re.compile(r'[a-f0-9]{48}\.(stl|3mf)')
# The job states in which the assigned host is making the part. Completed and cancelled jobs, and
# jobs returned to the pool or given to another host, no longer grant access.
MANUFACTURING_STATES = ('accepted', 'printing', 'ready')
_digests, _lock = {}, threading.Lock()

def cad_file(name):
    return config.UPLOAD_DIR.parent / 'cad' / name if CAD_NAME.fullmatch(name or '') else None

def sha256(path):
    """Digest of an immutable CAD file, computed once per file and process."""
    key = (str(path), path.stat().st_size)
    with _lock:
        if key in _digests: return _digests[key]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with _lock: _digests[key] = digest
    return digest

def snapshot(listing):
    """The manufacturing reference stored on an order line."""
    path = cad_file(listing.cad_path)
    if path is None:
        return {'listing_version': listing.version, 'cad_path': '', 'cad_sha256': '', 'cad_status': 'none'}
    if not path.is_file():
        return {'listing_version': listing.version, 'cad_path': listing.cad_path, 'cad_sha256': '', 'cad_status': 'missing'}
    return {'listing_version': listing.version, 'cad_path': listing.cad_path, 'cad_sha256': sha256(path), 'cad_status': 'pinned'}
