"""All Cowrie fields are hostile. Only explicit projections reach the API."""
from collections import Counter
import ipaddress
import math
import re
import unicodedata
from urllib.parse import urlsplit

ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))')
URL = re.compile(r'https?://[^\s<>\x00-\x20]+', re.I)
TOKEN = re.compile(r'(?:-----BEGIN|(?:sk|ghp|github_pat|AKIA|eyJ)[-_a-zA-Z0-9]{12,})')


def clean(value, limit=1024):
    if not isinstance(value, str):
        return ''
    value = ANSI.sub('', value[:65536])
    return ''.join(c for c in value if not unicodedata.category(c).startswith('C'))[:limit]


def credential(value):
    value = clean(value, 1024)
    if len(value) > 64 or TOKEN.search(value):
        return '[masked]'
    if len(value) >= 20:
        entropy = -sum((n / len(value)) * math.log2(n / len(value)) for n in Counter(value).values())
        if entropy >= 3.7:
            return '[masked]'
    return value


def defang(value):
    value = clean(value, 1024)
    return re.sub(r'https?://', lambda m: 'hxxps://' if m.group().lower().startswith('https') else 'hxxp://', value, flags=re.I).replace('.', '[.]')


def domain(value):
    try:
        host = urlsplit(value).hostname
        return clean(host.encode('idna').decode('ascii').lower(), 253) if host else ''
    except (ValueError, UnicodeError):
        return ''


def public_ip(value, mask):
    ip = ipaddress.ip_address(value)
    if mask:
        return str(ipaddress.ip_network(f'{ip}/{24 if ip.version == 4 else 48}', strict=False))
    return str(ip)
