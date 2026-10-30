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


def test_real_maxmind_databases_and_first_event_projection(db,settings,event):
    from pathlib import Path
    import shutil
    from app.queries import Queries
    fixtures=Path(__file__).parent/'fixtures'
    settings.geo_dir.mkdir()
    shutil.copyfile(fixtures/'GeoIP2-City-Test.mmdb',settings.geo_dir/'GeoLite2-City.mmdb')
    shutil.copyfile(fixtures/'GeoLite2-ASN-Test.mmdb',settings.geo_dir/'GeoLite2-ASN.mmdb')
    geo=Geo(db,settings)
    info=geo.lookup('81.2.69.160')
    assert info['country_code']=='GB'
    assert info['city']=='London'
    assert 50 < info['lat'] < 52 and -1 < info['lon'] < 1
    assert geo.lookup('1.0.0.1')['asn']==15169
    assert geo.lookup('10.0.0.1')['lat'] is None
    db.geo_lookup=geo.lookup
    db.insert(event(ip='81.2.69.160'))
    feed=Queries(db,settings).events()
    assert feed[0]['lat']==info['lat']
    assert feed[0]['lon']==info['lon']
    assert 'password' not in feed[0]
    geo.close()


def test_corrupt_database_does_not_crash_ingestion(db,settings):
    settings.geo_dir.mkdir()
    (settings.geo_dir/'GeoLite2-City.mmdb').write_bytes(b'not-a-database')
    geo=Geo(db,settings)
    assert geo.city is None
    assert geo.lookup('8.8.8.8')['lat'] is None
    geo.close()


def test_installing_database_reenriches_previously_seen_ips(db,settings,event):
    from pathlib import Path
    import shutil
    db.insert(event(ip='81.2.69.160'))
    before=Geo(db,settings)
    asyncio.run(before.enrich())
    cached=db.query('SELECT lat,resolved_at FROM ip_info')[0]
    assert cached['lat'] is None and cached['resolved_at'] is not None
    before.close()
    settings.geo_dir.mkdir()
    fixtures=Path(__file__).parent/'fixtures'
    shutil.copyfile(fixtures/'GeoIP2-City-Test.mmdb',settings.geo_dir/'GeoLite2-City.mmdb')
    shutil.copyfile(fixtures/'GeoLite2-ASN-Test.mmdb',settings.geo_dir/'GeoLite2-ASN.mmdb')
    after=Geo(db,settings)
    asyncio.run(after.enrich())
    assert db.query('SELECT lat FROM ip_info')[0]['lat']==51.5142
    assert db.query('SELECT count(*) n FROM events')[0]['n']==1
    after.close()


def test_wrong_database_edition_is_unavailable(db,settings):
    from pathlib import Path
    import shutil
    settings.geo_dir.mkdir()
    shutil.copyfile(Path(__file__).parent/'fixtures/GeoLite2-ASN-Test.mmdb',settings.geo_dir/'GeoLite2-City.mmdb')
    geo=Geo(db,settings)
    assert geo.city is None
    assert geo.lookup('1.0.0.1')['lat'] is None
    geo.close()
