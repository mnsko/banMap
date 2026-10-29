#!/usr/bin/env python3
"""Verify effective runtime hardening, not only the source YAML."""
import json
import subprocess
for service in ['cowrie','gateway','app','caddy']:
    container=subprocess.check_output(['docker','compose','ps','-q',service],text=True).strip()
    assert container, f'{service} is not running'
    info=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
    assert info['State']['Running'],service
    assert info['Config']['User'].split(':')[0] not in {'','0','root'},service
    host=info['HostConfig']
    assert host['ReadonlyRootfs'],service
    assert 'ALL' in host['CapDrop'],service
    assert any(option.startswith('no-new-privileges') for option in host['SecurityOpt']),service
    assert host['PidsLimit']>0 and host['Memory']>0 and host['NanoCpus']>0,service
    if service=='app':
        assert not host['PortBindings']
        assert {m['Destination'] for m in info['Mounts'] if m['RW']}=={'/data'}
    if service=='cowrie':
        assert not host['PortBindings']
        assert len(info['NetworkSettings']['Networks'])==1
        assert any(option.startswith('seccomp=') and 'unconfined' not in option for option in host['SecurityOpt'])
    print('PASS runtime hardening:',service)
