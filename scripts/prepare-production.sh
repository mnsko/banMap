#!/usr/bin/env bash
# Prepare deployable images using Python 3.12 inside Docker, independent of host Python.
set -euo pipefail
umask 022
cd "$(dirname "$0")/.."
command -v docker >/dev/null
command -v python3 >/dev/null
mkdir -p wheels runtime/docker runtime/fail2ban geoip
export DOCKER_CONFIG="${DOCKER_CONFIG:-$PWD/runtime/docker}"
docker info >/dev/null
docker compose config --quiet
python_image='python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
if ! docker image inspect "$python_image" >/dev/null 2>&1; then
    docker pull "$python_image"
fi
runner=(docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges:true
    --user "$(id -u):$(id -g)" --pids-limit 64 --memory 256m --cpus 1
    --tmpfs /tmp:size=128m,mode=1777,noexec,nosuid
    --env HOME=/tmp --env PIP_NO_CACHE_DIR=1 --env PIP_DISABLE_PIP_VERSION_CHECK=1
    --mount "type=bind,src=$PWD,dst=/work" --workdir /work "$python_image")
# A complete, verified wheelhouse works without registry/DNS access in the helper.
# If it is incomplete, fetch the missing artifacts normally with TLS and locked hashes.
if ! "${runner[@]}" python -m pip download --no-index --find-links=/work/wheels \
    --only-binary=:all: --require-hashes --dest /work/wheels \
    -r /work/app/requirements.lock >runtime/wheelhouse-check.log 2>&1; then
    echo 'Fetching pinned Python 3.12 wheels using the trusted Docker helper...'
    "${runner[@]}" python -m pip download --only-binary=:all: --require-hashes \
        --dest /work/wheels -r /work/app/requirements.lock
fi
python3 scripts/vendor-assets.py
chmod 644 cowrie/cowrie.cfg cowrie/userdb.txt cowrie/seccomp.json gateway/haproxy.cfg Caddyfile deploy/Caddyfile
chmod 755 runtime runtime/fail2ban geoip
docker compose build
echo 'Images prepared. No application services or public ports were started.'
