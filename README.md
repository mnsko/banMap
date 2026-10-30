# SSH Observatory / banMap

Veřejný, read-only dashboard nad izolovaným SSH honeypotem Cowrie. FastAPI, SQLite/WAL, SSE, Leaflet, Chart.js a Docker Compose. Původní zadání je v [plan.md](plan.md); průběžný stav a zbývající práce v [PROGRESS.md](PROGRESS.md).

## Lokální spuštění

Potřebuješ Linux, Python 3.12 a Docker Engine s Compose ≥ 2.24.4.

```sh
./scripts/install.sh
# .env je volitelný; bez něj platí bezpečné lokální výchozí hodnoty.
docker compose up -d --build
.venv/bin/python -m pytest -q
./scripts/check-egress.sh
python3 scripts/check-containers.py
.venv/bin/python scripts/smoke.py --restart
```

Web poslouchá lokálně na portu 8080, honeypot na portu 2222. Aplikace samotná žádný hostitelský port nepublikuje. Pro úpravy backendu spusť po změně `docker compose up -d --build app`. V cloudu s read-only domovským adresářem nastav před buildem `export DOCKER_CONFIG="$PWD/runtime/docker"`.

GeoLite2 databáze nejsou součástí repozitáře. Bez nich fungují logy, API, žebříčky a SSE, ale mapa nemá souřadnice. Doplň legálně získané `geoip/GeoLite2-City.mmdb` a `geoip/GeoLite2-ASN.mmdb`, nastav jim práva 644 a restartuj aplikaci. Viz [nasazení](docs/deployment.md).

Volitelný test UI v Chromium (desktop, mobil a neaktivní XSS vstup):

```sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/browser-smoke.py
```

GitHub Actions spouští backend testy, Compose, izolaci, restart i tyto prohlížečové testy. Skripty byly ověřeny lokálně; výsledek vzdáleného CI je potřeba kontrolovat samostatně.

## Co je uvnitř

- Čtení Cowrie JSONL a pouze bezpečnostních událostí fail2ban jailu `sshd`; žádné čtení úspěšných přihlášení skutečného SSH.
- Atomické ukládání offsetů, identifikace inode, čtení rotovaných logů a deduplikace v DB.
- Veřejná hesla, páry i jména až od nejméně tří různých IP. Podezřelé tokeny a dlouhé hodnoty se maskují již při ingestu.
- Feed/SSE používají explicitní seznam bezpečných polí a neobsahují hesla, příkazy ani syrové URL.
- Whitelist rozsahů, limity API/SSE, cache agregací, CSP, inertní text z nedůvěryhodných dat.
- Výchozí retence syrových událostí 90 dní. Anonymní denní počty a HMAC identifikátory pro souhrnné statistiky přetrvávají; žebříčky a mapa pracují s událostmi v retenčním okně.
- `MASK_IPS=true` maskuje IPv4 na /24 a IPv6 na /48. `HIDE_IPS` přijímá čárkami oddělené IP/CIDR a vylučuje je ze syrových dat; loopback sondy se ignorují automaticky.

## Izolace a produkce

Cowrie je na vlastní interní síti. Malá HAProxy brána přijímá SSH a předává původní IP pomocí PROXY protokolu; poslouchá jen na vnější straně. Seccomp profil Cowrie blokuje vytváření odchozích spojení včetně DNS a přístupu k hostiteli. Všechny služby běží jako non-root, s read-only kořenem, bez capabilities a s limity zdrojů. Podrobnosti a původ profilu: [docs/cowrie.md](docs/cowrie.md).

**Produkční override nespouštěj před bezpečným přesunem správního SSH a kontrolou konzole poskytovatele.** Postup, DNS, HTTPS, fail2ban, hostitelská firewallová ochrana a rotace: [docs/deployment.md](docs/deployment.md).

```sh
# Až na připraveném VPS; hostitelský Python 3.12 není potřeba:
sudo ./scripts/prepare-production.sh
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

`docker compose down` data nemaže. `down -v` smaže databázi, logy i klíče honeypotu. Zálohuj pojmenované volumes a chraň zálohy stejně jako původní syrová data. Nepřidávej `.env`, databáze, skutečné logy ani MaxMind databáze do Gitu.
