"""Create a consistent database and image archive while the application is stopped."""
import argparse
import sqlite3
import tarfile
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('archive', type=Path)
args = parser.parse_args()
data = Path('/app/data')
source = data / 'openlabs3d.db'
if not source.is_file(): raise SystemExit('Database does not exist; start the application first.')
if args.archive.exists(): raise SystemExit('Backup already exists; choose a new filename.')
with tempfile.TemporaryDirectory() as temp:
    snapshot = Path(temp) / 'openlabs3d.db'
    with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as src, sqlite3.connect(snapshot) as dst:
        src.backup(dst)
    with tarfile.open(args.archive, 'x:gz') as archive:
        archive.add(snapshot, arcname='openlabs3d.db')
        uploads = data / 'uploads'
        if uploads.exists(): archive.add(uploads, arcname='uploads')
print('Backup created:', args.archive)
