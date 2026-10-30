#!/usr/bin/env python3
"""Use the official updater; only whitelisted .env values, never source shell code."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent.parent
VERIFY_DATABASES = """
from pathlib import Path
import geoip2.database
for name, kind in [('GeoLite2-City.mmdb','GeoLite2-City'), ('GeoLite2-ASN.mmdb','GeoLite2-ASN')]:
    with geoip2.database.Reader(str(Path('/geoip') / name)) as reader:
        if reader.metadata().database_type != kind:
            raise SystemExit('Unexpected MaxMind database type')
print('GeoLite2 database types verified')
"""

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
    (ROOT/'geoip').mkdir(parents=True,exist_ok=True)
    # Empty config; actual credentials are only in the updater process environment.
    result=subprocess.run(['geoipupdate','-f','/dev/null','-d',str(ROOT/'geoip')],env=env,capture_output=True)
    if result.returncode:
        # Upstream diagnostics may contain a request URL; never copy them into public logs.
        raise SystemExit('GeoLite2 update failed; check account access, license and network configuration')
    for name in ['GeoLite2-City.mmdb','GeoLite2-ASN.mmdb']:
        path=ROOT/'geoip'/name
        if not path.is_file():
            raise SystemExit('Expected GeoLite2 database is missing after update')
        path.chmod(0o644)
    # Use the installed reader inside the app; the host needs only standard Python 3.
    # Strip credentials even from the Docker client's environment, not just container arguments.
    docker_env={key:value for key,value in os.environ.items() if key not in {
        'MAXMIND_ACCOUNT_ID','MAXMIND_LICENSE_KEY','GEOIPUPDATE_ACCOUNT_ID','GEOIPUPDATE_LICENSE_KEY',
        'GEOIPUPDATE_ACCOUNT_ID_FILE','GEOIPUPDATE_LICENSE_KEY_FILE',
    }}
    validation=subprocess.run(['docker','compose','exec','-T','app','python','-c',VERIFY_DATABASES],cwd=ROOT,env=docker_env,capture_output=True)
    if validation.returncode:
        raise SystemExit('Downloaded databases could not be validated in the running app container; application was not restarted')
    # COMPOSE_FILE can select the active production override; credentials are not forwarded to containers.
    subprocess.run(['docker','compose','restart','app'],cwd=ROOT,env=docker_env,check=True)
    print('Both GeoLite2 databases verified; application restarted')

if __name__=='__main__':
    main()
