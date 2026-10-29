from dataclasses import dataclass, field
from pathlib import Path
import ipaddress
import os


def flag(name, default=False):
    return os.getenv(name, str(default)).lower() in {'1', 'true', 'yes'}


@dataclass
class Settings:
    data: Path = field(default_factory=lambda: Path(os.getenv('DATA_DIR', '/data')))
    cowrie_log: Path = field(default_factory=lambda: Path(os.getenv('COWRIE_LOG', '/logs/cowrie/cowrie.json')))
    f2b_log: Path = field(default_factory=lambda: Path(os.getenv('F2B_LOG', '/logs/fail2ban/fail2ban.log')))
    geo_dir: Path = field(default_factory=lambda: Path(os.getenv('GEOIP_DIR', '/geoip')))
    threshold: int = field(default_factory=lambda: int(os.getenv('PASSWORD_MIN_IPS', '3')))
    retention_days: int = field(default_factory=lambda: int(os.getenv('RETENTION_DAYS', '90')))
    mask_ips: bool = field(default_factory=lambda: flag('MASK_IPS'))
    hide_ips: str = field(default_factory=lambda: os.getenv('HIDE_IPS', ''))
    rdns: bool = field(default_factory=lambda: flag('ENABLE_RDNS'))
    tor: bool = field(default_factory=lambda: flag('ENABLE_TOR'))
    sse_total: int = 100
    sse_per_ip: int = 3
    rate_per_minute: int = 180

    def __post_init__(self):
        if self.threshold < 3 or self.retention_days < 1:
            raise ValueError('PASSWORD_MIN_IPS must be >=3 and RETENTION_DAYS >=1')
        self.hidden = [ipaddress.ip_network(x.strip(), strict=False) for x in self.hide_ips.split(',') if x.strip()]

    def hidden_ip(self, ip):
        address = ipaddress.ip_address(ip)
        return address.is_loopback or any(address in network for network in self.hidden)
