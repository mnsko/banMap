from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.db import Database
from app.cowrie_parser import parse
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(data=tmp_path/'data',cowrie_log=tmp_path/'logs/cowrie.json',f2b_log=tmp_path/'f2b/fail2ban.log',geo_dir=tmp_path/'geo')


@pytest.fixture
def db(settings):
    settings.data.mkdir(parents=True)
    database=Database(settings.data/'test.sqlite',settings)
    yield database
    database.close()


@pytest.fixture
def event():
    def make(ip='203.0.113.1',password='password',username='root',eventid='cowrie.login.failed',**fields):
        import json
        obj={'timestamp':datetime.now(timezone.utc).isoformat(),'eventid':eventid,'src_ip':ip,'session':ip,'username':username,'password':password,**fields}
        return parse(json.dumps(obj))
    return make


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings,background=False)) as c:
        yield c
