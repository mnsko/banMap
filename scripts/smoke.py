#!/usr/bin/env python3
"""Local end-to-end readiness check. Does not administer or reconfigure a host."""
import argparse
import json
import subprocess
import threading
import time
import uuid
import httpx
import paramiko

parser=argparse.ArgumentParser()
parser.add_argument('--restart',action='store_true',help='Also restart only the app and verify history/deduplication')
args=parser.parse_args()
base='http://127.0.0.1:8080'
client=httpx.Client(base_url=base,timeout=5,trust_env=False)
assert client.get('/healthz').json()['status']=='ok'
latest=client.get('/api/events?limit=1').json()
cursor=latest[0]['id'] if latest else 0
received=[]; errors=[]; ready=threading.Event(); stop=threading.Event()
def consume():
    try:
        with client.stream('GET','/api/stream',headers={'Last-Event-ID':str(cursor)},timeout=8) as response:
            response.raise_for_status(); ready.set()
            for line in response.iter_lines():
                if stop.is_set(): break
                if line.startswith('data: '): received.append(json.loads(line[6:]))
    except Exception as exc:
        if not stop.is_set(): errors.append(type(exc).__name__)
thread=threading.Thread(target=consume,daemon=True); thread.start()
assert ready.wait(5),'SSE did not connect'

def ssh(password):
    c=paramiko.SSHClient()
    # Only this disposable, local honeypot. Never use AutoAddPolicy for VPS administration.
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect('127.0.0.1',2222,username='root',password=password,look_for_keys=False,allow_agent=False,timeout=5)
    return c
secret='rare-'+uuid.uuid4().hex[:8]
started=time.monotonic()
try:
    c=ssh(secret)
except paramiko.AuthenticationException:
    pass
else:
    c.close(); raise AssertionError('Unknown password unexpectedly accepted')
c=ssh('root')
channel=c.invoke_shell(); channel.settimeout(5); channel.recv(4096); channel.send('uname -a\n')
output=b''
while b'Linux' not in output:
    output+=channel.recv(4096)
channel.send('exit\n'); c.close()
deadline=time.monotonic()+5
while time.monotonic()<deadline and not any(e['type']=='command' for e in received):
    time.sleep(.05)
latency=time.monotonic()-started
stop.set()
assert not errors,errors
assert {'login_failed','login_success','command'}<={e['type'] for e in received},received
assert latency<2, f'SSH-to-SSE latency {latency:.3f}s exceeded 2 seconds'
for event in received:
    assert not ({'password','command','url','session'} & set(event)),event
for path in ['/api/events','/api/map','/api/stats','/api/top/passwords','/api/top/credentials','/api/top/commands']:
    response=client.get(path); response.raise_for_status(); assert secret not in response.text,path
assert 'Linux' in output.decode(errors='replace')
print(f'PASS SSH → Cowrie JSONL → SQLite → SSE in {latency:.3f}s; public projections do not leak test password')
if args.restart:
    # Allow final session-close line to be ingested before taking the baseline.
    time.sleep(1)
    before=client.get('/api/stats?range=1h').json()['lifetime_events']
    subprocess.run(['docker','compose','restart','app'],check=True)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        try:
            response=client.get('/healthz')
            if response.status_code==200 and response.json().get('last_ingest'): break
        except (httpx.HTTPError,ValueError): pass
        time.sleep(.25)
    else: raise AssertionError('App failed to restart')
    after=client.get('/api/stats?range=1h').json()['lifetime_events']
    assert before==after,(before,after)
    print(f'PASS app restart preserved all {after} events without duplicates')
client.close()
