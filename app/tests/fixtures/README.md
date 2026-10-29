# Test data provenance

`cowrie.sample.jsonl` was captured from the pinned Cowrie 3.1.4 container using a local SSH session. Source addresses and session IDs were replaced with documentation values; the weak credentials are synthetic. No production log data is included.

`GeoIP2-City-Test.mmdb` and `GeoLite2-ASN-Test.mmdb` are small public **test databases**, not production GeoLite2 data. Source: https://github.com/maxmind/MaxMind-DB/tree/d1551916cff0712d12ff602c309234471b0402a2/test-data . They were compared byte-for-byte with that checkout. MaxMind's MIT and Apache-2.0 licenses are included alongside them. Used only in tests; never installed as the production databases.
