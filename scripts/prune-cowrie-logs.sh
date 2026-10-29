#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T -e RETENTION_DAYS="${RETENTION_DAYS:-90}" cowrie /cowrie/cowrie-env/bin/python3 - <<'PY'
import os, time
from pathlib import Path
retention=int(os.environ['RETENTION_DAYS'])
assert retention>=1
cutoff=time.time()-retention*86400
for directory,pattern in [('var/log/cowrie','cowrie.json.*'),('var/log/cowrie','cowrie.log.*'),('var/lib/cowrie/downloads','*')]:
    for path in Path(directory).glob(pattern):
        if (path.is_file() or path.is_symlink()) and path.lstat().st_mtime < cutoff:
            path.unlink()
            print('Removed expired',path.name)
PY
