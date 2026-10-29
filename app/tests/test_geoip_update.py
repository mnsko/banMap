import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture
def updater(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('geoip_update',Path(__file__).parents[2]/'scripts/update-geoip.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(module.shutil,'which',lambda name:'/usr/bin/geoipupdate')
    monkeypatch.delenv('MAXMIND_ACCOUNT_ID',raising=False)
    monkeypatch.delenv('MAXMIND_LICENSE_KEY',raising=False)
    return module


def test_literal_env_and_no_credentials_in_arguments(updater,monkeypatch):
    payload='$(touch should-never-exist)'
    (updater.ROOT/'.env').write_text(f'MAXMIND_ACCOUNT_ID=123\nMAXMIND_LICENSE_KEY="{payload}"\nUNRELATED=ignored\n')
    geo=updater.ROOT/'geoip';geo.mkdir()
    for name in ['GeoLite2-City.mmdb','GeoLite2-ASN.mmdb']: (geo/name).touch()
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0)
    class Reader:
        def __init__(self,path): self.path=path
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def metadata(self): return SimpleNamespace(database_type=Path(self.path).stem)
    monkeypatch.setattr(updater.subprocess,'run',run)
    monkeypatch.setattr(updater.geoip2.database,'Reader',Reader)
    updater.main()
    assert payload==calls[0][1]['env']['GEOIPUPDATE_LICENSE_KEY']
    assert payload not in str(calls[0][0])
    assert calls[0][0][1:3]==['-f','/dev/null']
    assert calls[1][0]==['docker','compose','restart','app']
    assert not (updater.ROOT/'should-never-exist').exists()


def test_update_failure_never_exposes_upstream_output(updater,monkeypatch):
    monkeypatch.setenv('MAXMIND_ACCOUNT_ID','123')
    monkeypatch.setenv('MAXMIND_LICENSE_KEY','sensitive-marker')
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1,stderr=b'sensitive-marker')
    monkeypatch.setattr(updater.subprocess,'run',run)
    with pytest.raises(SystemExit) as error: updater.main()
    assert 'sensitive-marker' not in str(error.value)
    assert len(calls)==1


def test_update_requires_actual_credentials(updater):
    with pytest.raises(SystemExit,match='MAXMIND_ACCOUNT_ID is missing'): updater.main()
