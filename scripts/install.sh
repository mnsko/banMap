#!/usr/bin/env bash
set -euo pipefail
umask 022
cd "$(dirname "$0")/.."
python3 -c 'import sys; assert sys.version_info[:2] == (3,12), "Use Python 3.12"'
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements-dev.lock
mkdir -p wheels runtime/docker runtime/fail2ban geoip
.venv/bin/python -m pip download --disable-pip-version-check --only-binary=:all: --require-hashes --dest wheels -r app/requirements.lock
.venv/bin/python scripts/vendor-assets.py
chmod 644 cowrie/cowrie.cfg cowrie/userdb.txt cowrie/seccomp.json gateway/haproxy.cfg Caddyfile deploy/Caddyfile
chmod 755 runtime runtime/fail2ban geoip
# Support environments with a read-only home; preserve any explicit Docker config.
export DOCKER_CONFIG="${DOCKER_CONFIG:-$PWD/runtime/docker}"
docker compose config --quiet
docker compose build
