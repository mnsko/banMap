#!/usr/bin/env python3
"""Use the official updater; only whitelisted .env values, never source shell code."""
import os
from pathlib import Path
import shutil
import subprocess
import geoip2.database

ROOT=Path(__file__).resolve().parent.parent

def main():
    if not shutil.which('geoipupdate'):
        raise SystemExit('Install the official geoipupdate first; see docs/deployment.md')
    values={}
    env_file=ROOT/'.env'
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key,separator,value=line.partition('=')
            if separator and key.strip() in {'MAXMIND_ACCOUNT_ID','MAXMIND_LICENSE_KEY'}:
                values[key.strip()]=value.strip().strip('\"\'')
    env=os.environ.copy()
    for name in ['MAXMIND_ACCOUNT_ID','MAXMIND_LICENSE_KEY']:
        value=env.get(name) or values.get(name)
        if not value:
            raise SystemExit(f'{name} is missing; configure it securely in .env or the process environment')
        env['GEOIPUPDATE_'+name.removeprefix('MAXMIND_')]=value
    env['GEOIPUPDATE_EDITION_IDS']='GeoLite2-City GeoLite2-ASN'
    # Empty config; actual credentials are only in the updater process environment.
    result=subprocess.run(['geoipupdate','-f','/dev/null','-d',str(ROOT/'geoip')],env=env,capture_output=True)
    if result.returncode:
        # Upstream diagnostics may contain a request URL; never copy them into public logs.
        raise SystemExit('GeoLite2 update failed; check account access, license and network configuration')
    for name,kind in [('GeoLite2-City.mmdb','GeoLite2-City'),('GeoLite2-ASN.mmdb','GeoLite2-ASN')]:
        path=ROOT/'geoip'/name
        with geoip2.database.Reader(str(path)) as reader:
            if reader.metadata().database_type!=kind:
                raise SystemExit('Unexpected MaxMind database type')
        path.chmod(0o644)
    # COMPOSE_FILE can select the active production override; credentials are not forwarded to containers.
    subprocess.run(['docker','compose','restart','app'],cwd=ROOT,check=True)
    print('Both GeoLite2 databases verified; application restarted')

if __name__=='__main__':
    main()
