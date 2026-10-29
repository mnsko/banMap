# Nasazení na VPS (Ubuntu 26.04)

Lokální cloudová validace nezajišťuje přístup na VPS ani změnu DNS. Veřejné nasazení vyžaduje následující kroky na cílovém stroji. Výchozí produkční override publikuje pouze IPv4 TCP 22, 80 a 443; správní SSH na 22022 spravuje hostitel. Pro IPv6 je potřeba zvlášť navrhnout a otestovat firewall i publikování; do té doby nepřidávej AAAA.

## 1. Předpoklady a bezpečné přesunutí SSH

1. Ověř podmínky poskytovatele, vytvoř snapshot a skutečně vyzkoušej jeho záchrannou konzoli. Nezavírej stávající SSH relaci.
2. Připrav ne-root účet s klíčem a sudo. Ze druhého terminálu otestuj přihlášení tímto klíčem.
3. Prozkoumej `systemctl status ssh.socket ssh.service`, `systemctl cat ssh.socket` a `ss -lntp`. Moderní Ubuntu může používat socket activation a generator z konfigurace sshd; nepředpokládej, že samotné restartování `ssh.service` změní posluchač socketu.
4. Povol 22022/TCP v cloudovém i hostitelském firewallu **před** změnou posluchače. Správní SSH lze omezit na vlastní pevnou IP; honeypot 22 neomezuj pomocí fail2ban.
5. Nejdřív nastav oba porty 22 a 22022; pro socket activation použij drop-in s vyprázdněním `ListenStream=` a následně oběma `ListenStream=22` a `ListenStream=22022`. Pro klasickou service použij oba `Port` v sshd konfiguraci. Před reloadem vždy `sshd -t`, potom `systemctl daemon-reload` a restart skutečně používané jednotky.
6. Ze druhého terminálu se **skutečně přihlas na 22022 klíčem**, zkontroluj sudo a konzoli. Pak teprve odeber 22 ze sshd i případného socket drop-inu. Znovu `sshd -t` a restart příslušné jednotky; `ss -lntp` musí potvrdit, že hostitelský sshd už na 22 neposlouchá.
7. Vynucuj `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin no` a `AllowUsers tvuj-ucet`. OpenSSH u většiny voleb bere první nalezenou hodnotu; pouhé přidání `99-hardening.conf` nemusí přebít dřívější cloud-init konfiguraci. Použij vhodný pořádek a výsledek ověř pomocí `sshd -T -C user=tvuj-ucet,host=ssh.mnsk.me,addr=TVA_IP`.

Konkrétní stav jednotek Ubuntu 26.04 musí být ověřen na VPS; tento cloud běží v jiném prostředí. Žádný skript tohoto projektu nepřesouvá SSH bez operátora.

## 2. Docker, konfigurace a soubory

Nainstaluj Docker Engine a Compose plugin ≥2.24.4 z důvěryhodného podepsaného zdroje, Python 3.12, fail2ban, ufw, logrotate a unattended-upgrades. Ubuntu 26.04 může mít jiné výchozí Python; explicitně zajisti 3.12 nebo si připrav wheelhouse na Linuxu s odpovídající architekturou a Pythonem 3.12.

Naklonuj repo, spusť `./scripts/install.sh`, vytvoř neveřejný `.env` podle `.env.example`, nastav `DOMAIN=ssh.mnsk.me`, případně `MASK_IPS=true` a `HIDE_IPS=TVA_IP`. Nezadávej produkční klíče do chatu ani do Gitu. Instalace `.env` automaticky nečte ani nepřepisuje.

Vytvoř `/var/log/banmap/fail2ban` (root, skupina s GID 10001, adresář 0750, logy 0640). Tento vyhrazený adresář se mountuje read-only. Nemountuj celé `/var/log`, Docker socket ani SSH klíče. Číselné GID musí odpovídat aplikaci i po rotaci.

## 3. fail2ban a čas

Nastav UTC pro hostitelské logy. Do `/etc/fail2ban/fail2ban.local` patří:

```ini
[Definition]
logtarget = /var/log/banmap/fail2ban/fail2ban.log
```

Do `/etc/fail2ban/jail.d/banmap.local`:

```ini
[DEFAULT]
backend = systemd
bantime = 1h
findtime = 10m
maxretry = 5
ignoreip = 127.0.0.1/8 ::1 TVOJE_IP

[sshd]
enabled = true
port = 22022
```

Ověř `fail2ban-client -t`, restart, `fail2ban-client status sshd`, vznik a oprávnění logu. Parser sbírá pouze `Found`, `Ban` a `Unban` z jailu `sshd`, ne úspěšná přihlášení. Vlastní IP vyluč také přes `HIDE_IPS`.

## 4. Firewall a izolace

Povol 22, 80, 443, 22022/TCP a případné služby poskytovatele, pak teprve aktivuj UFW. Docker publikované porty mohou obejít UFW. Aplikace nemá publikovaný port, telnet je vypnutý. Nepřipojuj interní sítě k jiným aplikacím.

Cowrie seccomp a interní síť jsou první vrstvy. Další hostitelská pravidla nainstaluj přes `scripts/install-egress-guard.sh` (root). Pravidla chrání `br-banmap-hp` i adresu/subnet `172.30.77.0/24`, blokují nové odchozí spojení do dalších sítí a přístup k hostiteli. Skript odmítne pokračovat, pokud Docker nemá iptables řetězec `DOCKER-USER`; nftables backend potřebuje odpovídající samostatné pravidlo, ne slepé předstírání úspěchu.

Nainstaluj soubory a aktivuj jednotku:

```sh
sudo install -Dm755 scripts/install-egress-guard.sh /usr/local/lib/banmap/install-egress-guard.sh
sudo install -m644 deploy/banmap-egress.service /etc/systemd/system/banmap-egress.service
sudo systemctl daemon-reload
sudo systemctl enable --now banmap-egress.service
```

Systemd jednotka `deploy/banmap-egress.service` se spouští po Dockeru a znovu po jeho restartu. Ověř běžící pravidla po restartu Dockeru i po rebootu. Seccomp zůstává účinný i v době obnovování hostitelských pravidel.

Spusť `scripts/check-egress.sh`. Potom skutečně otestuj nový příchozí SSH pokus a kontroluj, že PROXY protokol přenáší původní veřejnou IP. Při změně seccomp nebo obrazů opakuj všechny testy.

## 5. GeoLite2

GeoLite2 City/ASN vyžadují vlastní oprávněný přístup od MaxMind. Databáze vlož do `geoip/` pod názvy `GeoLite2-City.mmdb` a `GeoLite2-ASN.mmdb` (0644). Aplikace při startu ověřuje čitelnost; chybná/chybějící DB se nesmí prezentovat jako funkční geolokace. `/healthz` uvádí oba stavy.

Pro automatické aktualizace doporučujeme oficiální [geoipupdate](https://github.com/maxmind/geoipupdate). Nastav jeho AccountID, LicenseKey a EditionIDs `GeoLite2-City GeoLite2-ASN` v souboru s právy 0600 mimo Git a `DatabaseDirectory` na absolutní cestu `geoip/` tohoto projektu. Spouštěj pravidelně; wrapper `scripts/update-geoip.sh` po úspěchu ověří obě DB a restartuje pouze aplikaci. Klíče nejsou předávány veřejnému webovému procesu. Kontrola hashů/TLS náleží oficiálnímu updateru, nezakazuj ji.

Volitelné `ENABLE_RDNS=true` provádí pouze PTR lookup veřejných IP s timeoutem. `ENABLE_TOR=true` denně stahuje pevnou adresu `https://check.torproject.org/torbulkexitlist`; případnou síťovou politiku nastav jen na tento host. Selhání enrichmentu neblokuje příjem událostí.

## 6. Spuštění HTTPS a ověření

A záznam `ssh.mnsk.me` musí ukazovat na VPS, porty 80/443 být dostupné z internetu. Ověř efektivní složený Compose před startem:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
./scripts/check-egress.sh
```

Caddy s produkční konfigurací používá automatické HTTPS a HSTS; certifikáty jsou v persistentních volumes. CSP dodává aplikace. Klientská IP pro API/SSE vychází z Caddy, protože aplikační port není publikovaný. Nepřidávej další nedůvěryhodné služby na backend síť a nevystavuj uvicorn přímo.

Ověř z internetu TLS a hlavičky, SSH log i jeho původní IP, mapu se souřadnicemi, SSE do přibližně 2 s, prahy hesel, rate limit, návrat po restartu a fungování správního SSH. `scripts/smoke.py` je **lokální** test vývojové konfigurace a nepředstírá tento veřejný test.

## 7. Retence a provoz

- Aplikační retence se provádí při startu a každou hodinu; syrové události a staré IP cache se mažou. Denní souhrny a HMAC unikátních IP zůstávají. Žebříčky mimo retenční okno nejsou k dispozici.
- Cowrie rotuje JSON log každý den. `scripts/prune-cowrie-logs.sh` odstraňuje pouze dost staré uzavřené rotace, nikdy aktivní `cowrie.json`; plánuj denně a sleduj disk. TTY je vypnuté, artefakty ve zvláštním state volume s limitem velikosti na soubor; nová síťová stažení blokuje seccomp.
- fail2ban log rotuj pomocí `deploy/fail2ban.logrotate`, po přejmenování použij `fail2ban-client flushlogs`; ověř správná práva nového souboru. Aplikace zvládá změnu inode i pozdní zápisy.
- Rotující Docker stdout logy mají 10 MB × 3 na službu; obsahují i Cowrie diagnostiku, proto jsou neveřejné a podléhají stejnému účelu zpracování a omezenému přístupu.
- Chraň DB, logy, HMAC sůl a zálohy; nastav vlastní retenční politiku snapshotů a záloh. Mazání v SQLite není záruka vymazání historických snapshotů. `PRAGMA secure_delete` a WAL checkpoint pomáhají s aktuální databází, nikoli se zálohami.
- Monitoruj zdraví, chyby čtení logů, zaplnění disku, stáří GeoLite2 a expiraci certifikátů. Při zahlcení omez příchozí spojení na firewallu/proxy a zkontroluj CPU/IO; limity API nejsou náhradou ochrany VPS proti DDoS.
