#!/usr/bin/env python3
"""Fetch only pinned frontend artifacts and verify npm's SHA-512 integrity."""
from pathlib import Path
import base64
import hashlib
import io
import json
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
manifest_path = ROOT/'app/static/vendor-manifest.json'
manifest = json.loads(manifest_path.read_text())
target = ROOT/'app/static/vendor'
target.mkdir(parents=True, exist_ok=True)
for package in manifest:
    with urllib.request.urlopen(package['url'],timeout=60) as response:
        blob = response.read(10_000_000)
    digest = 'sha512-'+base64.b64encode(hashlib.sha512(blob).digest()).decode()
    if digest != package['integrity']:
        raise SystemExit('Integrity mismatch: '+package['name'])
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
        for source,dest in package['files'].items():
            member=archive.getmember(source)
            if not member.isfile():
                raise SystemExit('Unexpected archive member')
            path=target/dest
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
            path.chmod(0o644)
    print('Verified',package['name'])
