#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# No shell/wget exists in the distroless Cowrie image; use its Python.
# Test literal-IP TCP, host gateway, UDP DNS and hostname HTTP independently.
docker compose exec -T cowrie /cowrie/cowrie-env/bin/python3 - <<'PY'
import socket, urllib.request
failures = []
for host, port in [('1.1.1.1',443), ('93.184.216.34',80), ('172.30.77.1',22), ('172.30.77.1',8080)]:
    try:
        s = socket.create_connection((host, port), 2)
    except OSError:
        print(f'BLOCKED TCP {host}:{port}')
    else:
        s.close(); failures.append(f'TCP {host}:{port}')
try:
    urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://example.com', timeout=3)
except (OSError, ValueError):
    print('BLOCKED HTTP example.com')
else:
    failures.append('HTTP example.com')
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(2)
try:
    s.sendto(bytes.fromhex('123401000001000000000000076578616d706c6503636f6d0000010001'),('1.1.1.1',53))
    s.recv(512)
except OSError:
    print('BLOCKED external UDP DNS')
else:
    failures.append('UDP DNS')
finally:
    s.close()
if failures:
    raise SystemExit('EGRESS IS NOT ISOLATED: ' + ', '.join(failures))
PY
