from datetime import datetime, timezone
import ipaddress
import re
from .cowrie_parser import timestamp

LINE = re.compile(r'^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,.]\d+)?(?:Z|[+-]\d\d:\d\d)?)\s+.*?\[sshd\]\s+(Found|Ban|Unban)\s+([\da-fA-F:.]+)(?:\s|$)')


def parse(line):
    if not isinstance(line, str):
        return None
    match = LINE.search(line[:65536])
    if not match:
        return None
    try:
        ts, action, ip = match.groups()
        # Host fail2ban must log UTC; see deployment instructions.
        return {'ts': timestamp(ts.replace(',', '.')), 'source': 'fail2ban',
                'type': 'f2b_' + action.lower(), 'ip': str(ipaddress.ip_address(ip)), 'session': ''}
    except (ValueError, TypeError):
        return None
