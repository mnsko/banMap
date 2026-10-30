import importlib.util
from pathlib import Path
import ipaddress
import pytest

spec=importlib.util.spec_from_file_location('cf_policy',Path(__file__).parents[2]/'scripts/cloudflare-policy.py')
policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)


def payload():
    # Public prefixes used only as test values, not a production Cloudflare allowlist.
    return {'success':True,'result':{'ipv4_cidrs':['8.8.8.0/24'],'ipv6_cidrs':['2606:4700::/32']}}


def test_validated_policy_round_trip_and_web_only_rules(tmp_path):
    networks=policy.parse_response(payload())
    path=tmp_path/'proxy.env';policy.save_policy(path,networks)
    assert policy.read_policy(path)==networks
    rules=policy.render_rules(networks,'eth0',4)
    assert '--dports 80,443 -s 8.8.8.0/24 -j RETURN' in rules
    assert '--dports 80,443 -j DROP' in rules
    assert '22022' not in rules and '--dports 22' not in rules
    assert '2606:4700' not in rules
    assert not any(line.startswith('-F ') and line!='-F BANMAP-CF-WEB' for line in rules.splitlines())


@pytest.mark.parametrize('prefix',['0.0.0.0/0','10.0.0.0/8','127.0.0.0/8','100.64.0.0/10','8.8.8.1/24','8.8.8.0/24\n-j ACCEPT','192.0.2.0/24'])
def test_refuses_broad_private_noncanonical_or_injected_prefix(prefix):
    data=payload();data['result']['ipv4_cidrs']=[prefix]
    with pytest.raises(ValueError):policy.parse_response(data)


@pytest.mark.parametrize('data',[{}, {'success':False,'result':{}}, {'success':True,'result':{'ipv4_cidrs':[],'ipv6_cidrs':[]}}, {'success':True,'result':{'ipv4_cidrs':['8.8.8.0/24'],'ipv6_cidrs':[]}}])
def test_incomplete_source_is_not_a_policy(data):
    with pytest.raises(ValueError):policy.parse_response(data)


def test_failed_refresh_preserves_existing_policy(tmp_path,monkeypatch):
    path=tmp_path/'proxy.env';policy.save_policy(path,policy.parse_response(payload()));before=path.read_bytes()
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size):return b'{"success":false}'
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(policy.urllib.request,'build_opener',lambda *args:Opener())
    with pytest.raises(ValueError):policy.fetch_policy(path)
    assert path.read_bytes()==before


def test_policy_file_cannot_inject_environment_or_firewall(tmp_path):
    path=tmp_path/'proxy.env';path.write_text('CLOUDFLARE_PROXY_RANGES=8.8.8.0/24 2606:4700::/32\nEVIL=value\n')
    with pytest.raises(ValueError):policy.read_policy(path)
    with pytest.raises(ValueError):policy.render_rules(policy.parse_response(payload()),'eth0\n-j ACCEPT',4)
