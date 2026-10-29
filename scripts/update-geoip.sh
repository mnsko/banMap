#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GEOIPUPDATE_CONFIG:?Set GEOIPUPDATE_CONFIG to an existing private geoipupdate config file}"
# The config contains credentials, is never sourced or printed, and is outside Git.
command -v geoipupdate >/dev/null
geoipupdate -f "$GEOIPUPDATE_CONFIG" -d "$PWD/geoip"
.venv/bin/python - <<'PY'
from pathlib import Path
import geoip2.database
for name in ['GeoLite2-City.mmdb','GeoLite2-ASN.mmdb']:
    path=Path('geoip')/name
    with geoip2.database.Reader(str(path)) as reader:
        assert reader.metadata().database_type in {'GeoLite2-City','GeoLite2-ASN'}
    path.chmod(0o644)
print('Both GeoLite2 databases verified')
PY
# Caller chooses the actual active Compose project/configuration through COMPOSE_FILE.
docker compose restart app
