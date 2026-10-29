import asyncio
from app.geo import Geo


def test_missing_database_and_private_addresses(db,settings):
    geo=Geo(db,settings)
    for ip in ['127.0.0.1','10.0.0.1','2001:db8::1','8.8.8.8']:
        assert geo.lookup(ip)['lat'] is None
    geo.close()


def test_city_asn_lookup_and_cache(db,settings,event):
    from types import SimpleNamespace as NS
    geo=Geo(db,settings)
    class City:
        def city(self,ip):
            return NS(country=NS(iso_code='CZ',name='Czechia'),city=NS(name='Prague'),location=NS(latitude=50.08,longitude=14.43))
        def close(self): pass
    class ASN:
        def asn(self,ip): return NS(autonomous_system_number=1234,autonomous_system_organization='Example')
        def close(self): pass
    geo.city=City(); geo.asn=ASN()
    db.insert(event(ip='8.8.8.8'))
    asyncio.run(geo.enrich())
    result=db.query('SELECT * FROM ip_info')[0]
    assert result['country_code']=='CZ' and result['lat']==50.08 and result['asn']==1234
    assert result['resolved_at']
    assert geo.lookup('10.0.0.1')['lat'] is None
    geo.close()
