"""Offline MaxMind lookups; optional public-IP-only PTR/Tor enrichment."""
from datetime import timedelta
import asyncio
import ipaddress
import logging
import dns.asyncresolver
import dns.exception
import geoip2.database
import geoip2.errors
import httpx
from .db import utcnow
from .sanitize import clean

logger = logging.getLogger(__name__)


class Geo:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.city = self.open('GeoLite2-City.mmdb')
        self.asn = self.open('GeoLite2-ASN.mmdb')
        self.tor_ips = set()
        self.tor_checked = None

    def open(self, name):
        try:
            return geoip2.database.Reader(str(self.settings.geo_dir / name))
        except (OSError, ValueError):
            logger.warning('%s unavailable; coordinates/ASN may be absent', name)
            return None

    def lookup(self, ip):
        result = {'country_code':None,'country':None,'city':None,'lat':None,'lon':None,'asn':None,'asn_org':None}
        if not ipaddress.ip_address(ip).is_global:
            return result
        try:
            if self.city:
                city = self.city.city(ip)
                result.update(country_code=city.country.iso_code, country=clean(city.country.name,128), city=clean(city.city.name,128), lat=city.location.latitude, lon=city.location.longitude)
            if self.asn:
                asn = self.asn.asn(ip)
                result.update(asn=asn.autonomous_system_number, asn_org=clean(asn.autonomous_system_organization,256))
        except geoip2.errors.GeoIP2Error:
            pass
        return result

    async def enrich(self):
        cutoff = (utcnow() - timedelta(days=1)).isoformat()
        ips = self.db.query('SELECT ip FROM ip_info WHERE resolved_at IS NULL OR resolved_at < ? LIMIT 50', (cutoff,))
        for row in ips:
            ip = row['ip']
            info = self.lookup(ip)
            rdns = None
            if self.settings.rdns and ipaddress.ip_address(ip).is_global:
                try:
                    answer = await dns.asyncresolver.resolve_address(ip, lifetime=2)
                    rdns = clean(str(answer[0]).rstrip('.'),253)
                except (OSError, TimeoutError, dns.exception.DNSException):
                    pass
            with self.db.transaction() as c:
                c.execute('UPDATE ip_info SET country_code=?,country=?,city=?,lat=?,lon=?,asn=?,asn_org=?,rdns=?,is_tor=?,resolved_at=? WHERE ip=?', (*info.values(),rdns,int(ip in self.tor_ips),utcnow().isoformat(),ip))

    async def refresh_tor(self):
        if not self.settings.tor or (self.tor_checked and utcnow()-self.tor_checked < timedelta(days=1)):
            return
        self.tor_checked = utcnow()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                async with client.stream('GET','https://check.torproject.org/torbulkexitlist') as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 2_000_000:
                            raise ValueError('Tor list too large')
            ips = set()
            for line in data.decode().splitlines():
                try:
                    address = ipaddress.ip_address(line)
                    if address.is_global:
                        ips.add(str(address))
                except ValueError:
                    continue
            self.tor_ips = ips
            with self.db.transaction() as c:
                c.execute('UPDATE ip_info SET is_tor=0')
                c.executemany('UPDATE ip_info SET is_tor=1 WHERE ip=?', [(ip,) for ip in ips])
        except (httpx.HTTPError, ValueError, UnicodeError):
            logger.warning('Tor exit list unavailable; retaining last successful list')

    def close(self):
        for reader in (self.city,self.asn):
            if reader:
                reader.close()
