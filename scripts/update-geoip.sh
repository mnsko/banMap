#!/usr/bin/env bash
set -euo pipefail
umask 022
cd "$(dirname "$0")/.."
python3 scripts/update-geoip.py
