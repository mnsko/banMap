#!/usr/bin/env python3
"""Fetch public Cloudflare prefixes over verified HTTPS; render narrowly scoped guards."""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT/'runtime/cloudflare/proxy.env'
KEY = 'CLOUDFLARE_PROXY_RANGES'
URL = 'https://api.cloudflare.com/client/v4/ips'


def validate(values):
    if not isinstance(values,list) or not 2 <= len(values) <= 200:
        raise ValueError('Invalid Cloudflare prefix list')
    networks=[]
    for value in values:
        if not isinstance(value,str):
            raise ValueError('Invalid prefix type')
        network=ipaddress.ip_network(value,strict=True)
        if not network.is_global or network.prefixlen < (8 if network.version==4 else 16):
            raise ValueError('Refusing private or overly broad proxy prefix')
        if network in networks:
            raise ValueError('Duplicate proxy prefix')
        networks.append(network)
    if {n.version for n in networks}!={4,6}:
        raise ValueError('Both IPv4 and IPv6 prefix lists are required')
    return networks


def parse_response(payload):
    if not isinstance(payload,dict) or payload.get('success') is not True:
        raise ValueError('Cloudflare API did not report success')
    result=payload.get('result')
    if not isinstance(result,dict) or not isinstance(result.get('ipv4_cidrs'),list) or not isinstance(result.get('ipv6_cidrs'),list):
        raise ValueError('Incomplete Cloudflare API response')
    v4=result['ipv4_cidrs'];v6=result['ipv6_cidrs']
    networks=validate(v4+v6)
    if any(n.version!=4 for n in networks[:len(v4)]) or any(n.version!=6 for n in networks[len(v4):]):
        raise ValueError('Incorrect address family in Cloudflare response')
    return networks


def read_policy(path):
    text=path.read_text()
    lines=[line for line in text.splitlines() if line and not line.startswith('#')]
    if len(text)>65536 or len(lines)!=1 or not lines[0].startswith(KEY+'='):
        raise ValueError('Invalid proxy policy file')
    return validate(lines[0].split('=',1)[1].split())


def save_policy(path,networks):
    path.parent.mkdir(parents=True,exist_ok=True)
    content=f'# Source: {URL}\n# Updated UTC: {datetime.now(timezone.utc).isoformat()}\n{KEY}='+ ' '.join(str(n) for n in networks)+'\n'
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name); stream.write(content); stream.flush(); os.fsync(stream.fileno())
            os.fchmod(stream.fileno(),0o644)
        os.replace(temporary,path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Unexpected redirect from the fixed Cloudflare API endpoint')


def fetch_policy(path):
    opener=urllib.request.build_opener(NoRedirect())
    with opener.open(URL,timeout=30) as response:
        blob=response.read(1_000_001)
    if len(blob)>1_000_000:
        raise ValueError('Cloudflare API response too large')
    networks=parse_response(json.loads(blob))
    save_policy(path,networks)
    return networks


def render_rules(networks,interface,family):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}',interface):
        raise ValueError('Invalid ingress interface')
    lines=['*filter','-F BANMAP-CF-WEB']
    for network in networks:
        if network.version==family:
            lines.append(f'-A BANMAP-CF-WEB -i {interface} -p tcp -m multiport --dports 80,443 -s {network} -j RETURN')
    lines.extend([f'-A BANMAP-CF-WEB -i {interface} -p tcp -m multiport --dports 80,443 -j DROP','-A BANMAP-CF-WEB -j RETURN','COMMIT'])
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['fetch','show','rules'])
    parser.add_argument('--policy',type=Path,default=POLICY)
    parser.add_argument('--interface')
    parser.add_argument('--family',type=int,choices=[4,6],default=4)
    args=parser.parse_args()
    try:
        networks=fetch_policy(args.policy) if args.action=='fetch' else read_policy(args.policy)
        if args.action=='rules':
            print(render_rules(networks,args.interface or '',args.family),end='')
        else:
            print(f'Validated proxy policy: {sum(n.version==4 for n in networks)} IPv4, {sum(n.version==6 for n in networks)} IPv6 prefixes')
    except (OSError,ValueError,TypeError) as error:
        raise SystemExit(f'Cloudflare policy unavailable: {error}; existing policy was not replaced')

if __name__=='__main__':
    main()
