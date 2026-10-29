from datetime import datetime, timezone
import ipaddress
import json
import math
from .sanitize import clean, credential, URL, domain

EVENTS = {
    'cowrie.session.connect': 'connect', 'cowrie.client.version': 'client_version',
    'cowrie.client.kex': 'kex', 'cowrie.login.failed': 'login_failed',
    'cowrie.login.success': 'login_success', 'cowrie.command.input': 'command',
    'cowrie.session.file_download': 'download', 'cowrie.session.file_upload': 'upload',
    'cowrie.direct-tcpip.request': 'tcp_forward', 'cowrie.session.closed': 'closed',
}


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('invalid timestamp')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')


def port(value):
    if isinstance(value, int) and not isinstance(value, bool) and 0 < value < 65536:
        return value
    return None


def parse(line):
    try:
        obj = json.loads(line)
        if not isinstance(obj, dict) or obj.get('eventid') not in EVENTS:
            return None
        ip = str(ipaddress.ip_address(obj['src_ip']))
        event = {
            'ts': timestamp(obj['timestamp']), 'source': 'cowrie', 'type': EVENTS[obj['eventid']],
            'ip': ip, 'session': clean(obj.get('session'), 128),
            'src_port': port(obj.get('src_port')), 'dst_port': port(obj.get('dst_port')),
        }
        for key, src in [('username','username'), ('password','password')]:
            event[key] = credential(obj[src]) if isinstance(obj.get(src), str) else None
        for key, src in [('command','input'), ('client_version','version'), ('hassh','hassh'), ('url','url'), ('shasum','shasum')]:
            event[key] = clean(obj.get(src), 1024)
        if event['type'] == 'tcp_forward':
            event['tcp_dst'] = clean(obj.get('dst_ip'), 253) + ':' + str(port(obj.get('dst_port')) or '')
        if event['type'] == 'closed':
            duration = float(obj.get('duration', 0))
            event['duration'] = max(0, min(duration, 86400 * 7)) if math.isfinite(duration) else 0
        urls = ([event['url']] if event['url'] else []) + URL.findall(event['command'])[:10]
        event['domains'] = sorted({host for url in urls if (host := domain(url))})
        return event
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None
