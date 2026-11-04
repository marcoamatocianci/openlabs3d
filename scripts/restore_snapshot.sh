#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Restore only into an empty application volume; never overwrite an existing site.
docker compose build backend
docker compose run --rm --no-deps -T --entrypoint python backend -c '
import sys,tarfile
from pathlib import Path
root=Path("/app/data")
if any(root.iterdir()):
    raise SystemExit("Application volume is not empty. Restore refused to preserve existing data.")
with tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as archive:
    archive.extractall(root,filter="data")
print("Site snapshot restored.")
' < snapshot/app-data.tar.gz
docker compose up -d
