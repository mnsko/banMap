#!/usr/bin/env python3
"""Exercise actual Caddy proxy trust, forged headers and cache headers in an isolated network.

Uses a disposable local CA with full TLS verification. No public services or host firewall changes.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parent.parent
PYTHON='python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
prefix='banmap-cf-test-'+uuid.uuid4().hex[:8]
network=prefix+'-net'
containers=[]

def command(*args,check=True):
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return (result.stdout+result.stderr).strip() if len(args)>1 and args[1]=='logs' else result.stdout.strip()


def start(name,*args):
    containers.append(name)
    return command('docker','run','-d','--name',name,*args)

with tempfile.TemporaryDirectory(prefix='banmap-cf-test-') as directory:
    temp=Path(directory)
    source=(ROOT/'deploy/Caddyfile.cloudflare').read_text()
    issuer='''    tls {
        issuer acme {
            disable_tlsalpn_challenge
        }
    }'''
    assert issuer in source
    config=source.replace(issuer,'    tls internal').replace('    admin off','    admin off\n    skip_install_trust',1)
    config_path=temp/'Caddyfile';config_path.write_text(config);config_path.chmod(0o644)
    backend=temp/'backend.py'
    backend.write_text('''from http.server import BaseHTTPRequestHandler,HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  body=json.dumps({'forwarded_for':self.headers.get('X-Forwarded-For'),'cf_header':self.headers.get('CF-Connecting-IP')}).encode()
  self.send_response(200); self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
''');backend.chmod(0o644)
    created_network=False
    try:
        command('docker','network','create','--internal','--subnet','172.29.188.0/24',network)
        created_network=True
        start(prefix+'-backend','--network',network,'--ip','172.29.188.3','--network-alias','app','--read-only','--cap-drop','ALL','--user','65532:65532','--mount',f'type=bind,src={backend},dst=/backend.py,readonly',PYTHON,'python','-B','/backend.py')
        start(prefix+'-caddy','--network',network,'--ip','172.29.188.2','--network-alias','cf-test.local','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--user','10001:10001','--tmpfs','/data:uid=10001,gid=10001,mode=0700,size=16m','--tmpfs','/config:uid=10001,gid=10001,mode=0700,size=16m','--env','HTTP_PROXY=','--env','HTTPS_PROXY=','--env','ALL_PROXY=','--env','http_proxy=','--env','https_proxy=','--env','all_proxy=','--env','NO_PROXY=*','--env','no_proxy=*','--env','DOMAIN=cf-test.local:8443','--env','CLOUDFLARE_PROXY_RANGES=172.29.188.4/32','--mount',f'type=bind,src={config_path},dst=/etc/caddy/Caddyfile,readonly','banmap-caddy')
        certificate=temp/'root.crt'
        for attempt in range(50):
            # Export only the public test CA via its owner; do not read any private keys.
            result=subprocess.run(['docker','exec','--user','10001:10001',prefix+'-caddy','cat','/data/caddy/pki/authorities/local/root.crt'],capture_output=True,text=True)
            if result.returncode==0 and '-----BEGIN CERTIFICATE-----' in result.stdout:
                certificate.write_text(result.stdout)
                break
            time.sleep(.2)
        else:
            raise RuntimeError('Test Caddy did not initialize its local CA: '+command('docker','logs',prefix+'-caddy',check=False)+'; data directories: '+command('docker','exec',prefix+'-caddy','find','/data','/config','-maxdepth','5',check=False))
        certificate.chmod(0o644)
        client_code='''import json,ssl,urllib.request,urllib.error,time
context=ssl.create_default_context(cafile='/test-root.crt')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
request=urllib.request.Request('https://cf-test.local:8443/api/test',headers={'CF-Connecting-IP':'203.0.113.45','X-Forwarded-For':'1.1.1.1'})
for attempt in range(20):
 try:
  response=opener.open(request,timeout=3)
  body=json.load(response)
  assert body['forwarded_for']=='203.0.113.45',body
  assert body['cf_header'] is None,body
  assert response.headers['Cache-Control']=='no-store'
  print('PASS trusted proxy: actual visitor IP, forged XFF ignored, upstream header removed, API no-store')
  break
 except urllib.error.HTTPError:raise
 except urllib.error.URLError:
  if attempt==19:raise
  time.sleep(.2)
'''
        command('docker','run','--rm','--network',network,'--ip','172.29.188.4','--read-only','--cap-drop','ALL','--user','65532:65532','--mount',f'type=bind,src={certificate},dst=/test-root.crt,readonly',PYTHON,'python','-c',client_code)
        print('PASS trusted proxy: verified TLS, real client IP, forged XFF ignored, API no-store')
        untrusted='''import ssl,urllib.request,urllib.error
context=ssl.create_default_context(cafile='/test-root.crt')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
request=urllib.request.Request('https://cf-test.local:8443/api/test',headers={'CF-Connecting-IP':'203.0.113.45','X-Forwarded-For':'172.29.188.4'})
try:
 opener.open(request,timeout=3)
except urllib.error.HTTPError as error:
 assert error.code==403,error.code
else:raise AssertionError('Untrusted direct origin access was allowed')
'''
        command('docker','run','--rm','--network',network,'--ip','172.29.188.5','--read-only','--cap-drop','ALL','--user','65532:65532','--mount',f'type=bind,src={certificate},dst=/test-root.crt,readonly',PYTHON,'python','-c',untrusted)
        print('PASS untrusted source: spoofed Cloudflare/XFF headers cannot bypass origin 403')
    except Exception:
        for container in containers:
            print(command('docker','logs',container,check=False))
        raise
    finally:
        for container in reversed(containers):
            command('docker','rm','-f',container,check=False)
        if created_network:command('docker','network','rm',network,check=False)
