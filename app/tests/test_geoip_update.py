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
    monkeypatch.setattr(updater.subprocess,'run',run)
    updater.main()
    assert payload==calls[0][1]['env']['GEOIPUPDATE_LICENSE_KEY']
    assert payload not in str(calls[0][0])
    assert calls[0][0][1:3]==['-f','/dev/null']
    assert calls[1][0][:6]==['docker','compose','exec','-T','app','python']
    for key in ['MAXMIND_ACCOUNT_ID','MAXMIND_LICENSE_KEY','GEOIPUPDATE_LICENSE_KEY']:
        if key in calls[1][1]['env'] or key in calls[2][1]['env']:
            pytest.fail('Updater credentials leaked into a Docker subprocess environment')
    assert payload not in str(calls[1][0])
    assert calls[2][0]==['docker','compose','restart','app']
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


def test_failed_validation_does_not_restart_app(updater,monkeypatch):
    monkeypatch.setenv('MAXMIND_ACCOUNT_ID','123')
    monkeypatch.setenv('MAXMIND_LICENSE_KEY','private-marker')
    geo=updater.ROOT/'geoip';geo.mkdir()
    for name in ['GeoLite2-City.mmdb','GeoLite2-ASN.mmdb']:(geo/name).touch()
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0 if len(calls)==1 else 1)
    monkeypatch.setattr(updater.subprocess,'run',run)
    with pytest.raises(SystemExit,match='could not be validated'):updater.main()
    assert len(calls)==2
    assert all('private-marker' not in str(args) for args in calls)


def test_missing_download_cannot_restart_app(updater,monkeypatch):
    monkeypatch.setenv('MAXMIND_ACCOUNT_ID','123')
    monkeypatch.setenv('MAXMIND_LICENSE_KEY','private-marker')
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(updater.subprocess,'run',run)
    with pytest.raises(SystemExit,match='database is missing'):updater.main()
    assert len(calls)==1
