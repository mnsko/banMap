# SSH Attack Map + Honeypot – plán projektu

Veřejná webová aplikace na `ssh.mnsk.me`, která zobrazuje útočníky na živé mapě světa a statistiky z **SSH honeypotu (Cowrie)** na portu 22: jaké uživatelské jméno a heslo zkoušejí, odkud přicházejí, jaké příkazy spouštějí po (falešném) přihlášení, jaké klienty používají. Skutečný SSH běží na jiném portu a je chráněný fail2ban.

> Pokyny pro AI agenta: pracuj po fázích, po každé fázi ověř, že aplikace běží (`docker compose up`) a že testy procházejí. Nepřeskakuj bezpečnostní požadavky v sekci 10 – UI je veřejné, stroj je na VPS a vstupní data pocházejí od útočníků. U konkrétních voleb Cowrie (názvy konfiguračních klíčů, formát logu) ověř aktuální dokumentaci a skutečný log, nespoléhej na paměť.

---

## 1. Rozhodnutí (zadání)

- Jeden stroj: **VPS, Ubuntu 26.04**, veřejná doména **`ssh.mnsk.me`**.
- Port **22 = Cowrie honeypot** (sbírá hesla, příkazy, klienty).
- **Skutečný SSH na jiném portu** (např. 22022), jen klíče, `fail2ban`.
- Web veřejný bez přihlášení, klidně vše veřejné (s výjimkami v kapitole 6.4 a 10, které chrání soukromí).
- Sbírat uživatelská jména, hesla a další zajímavosti.

### Cíle
- Živá mapa světa s body útočníků.
- Žebříčky: **nejčastější hesla**, uživatelská jména, páry jméno:heslo, země, ASN, IP, SSH klienti, HASSH otisky, příkazy po přihlášení, domény v odkazech na stažení malwaru.
- Časové vzorce (graf 24 h, heatmapa hodina × den), čas do prvního útoku, podíl opakovaných útočníků.
- Historie v SQLite, přežije restart.
- Nasazení přes Docker Compose.

### Mimo rozsah (v1)
- Ovládání čehokoli z webu (UI je read-only).
- Více serverů (možné rozšíření).

---

## 2. Volba nástrojů

| Úloha | Volba | Poznámka |
|---|---|---|
| Honeypot SSH | **Cowrie** (středně interaktivní, emuluje shell, loguje hesla/příkazy/stažení, JSON log) | Alternativy: Endlessh (tarpit, hesla nesbírá), OpenCanary. Cowrie je pro tento cíl nejvhodnější. |
| Ochrana skutečného SSH | **fail2ban** (jail `sshd` na novém portu) | Zůstává; bany se zobrazí na mapě jako samostatný typ události. |
| Telnet (volitelné) | Cowrie telnet na portu 23 | Hodně botů, hodně dat. |

fail2ban na portu 22 nedává smysl (honeypot musí útočníky přijímat), proto chrání jen skutečný SSH. Čtení SSH logu z journald **odpadá** – detaily přináší rovnou Cowrie.

---

## 3. Technologie aplikace

| Vrstva | Volba | Důvod |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** | Parsování logů, SSE |
| Zdroje dat | Tail `cowrie.json` (JSON lines) + tail `fail2ban.log` | Viz sekce 6 |
| Geolokace | **MaxMind GeoLite2-City + ASN** (offline `.mmdb`, `geoip2`) | Bez limitů; potřeba bezplatný účet a licenční klíč |
| DB | **SQLite** (WAL) | Bez další služby |
| Živé aktualizace | **Server-Sent Events** | Jednodušší než WebSocket |
| Frontend | **Vanilla JS + Leaflet + Chart.js** | Bez build kroku |
| Dlaždice | CARTO dark / OSM | Dodržet attribution |
| Reverzní proxy | **Caddy** | Auto HTTPS pro `ssh.mnsk.me` |
| Nasazení | **Docker Compose** | |

---

## 4. Architektura

```
 Internet ─> :22   ─> Cowrie (kontejner, vnitřně :2222, žádný výstup do sítě)
                          │  zapisuje cowrie.json (sdílený volume)
 Internet ─> :22022 ─> skutečný sshd (hostitel) ─> fail2ban ─> /var/log/fail2ban.log
 Internet ─> :80/443 ─> Caddy ─> app (FastAPI, non-root)
                                   │ čte cowrie.json a fail2ban.log (ro)
                                   v
                         SQLite (volume) + GeoLite2
```

Docker poznámka: publikované porty kontejnerů **obcházejí `ufw`** (Docker vkládá vlastní iptables pravidla). Do světa mají jít jen porty 22, 80, 443 (a případně 23) – aplikace samotná se nepublikuje, je dostupná jen přes Caddy v interní síti.

---

## 5. Příprava VPS

### 5.1 Doména a DNS
- A (a případně AAAA) záznam `ssh.mnsk.me` → IP VPS.
- Caddy získá certifikát přes Let's Encrypt (potřebuje porty 80/443 dostupné z internetu).

### 5.2 Přesun skutečného SSH – **opatrně, ať se nezamkneš**
1. Před změnou ověř, že máš funkční přístup přes **konzoli poskytovatele VPS** (záchranná cesta).
2. Nahraj svůj SSH klíč, ověř přihlášení klíčem.
3. Nejdřív **přidej** nový port (např. 22022) a otestuj přihlášení z druhého terminálu **při otevřené původní relaci**.
4. Teprve potom odstraň port 22 ze skutečného sshd.
   - Pozor: na Ubuntu může SSH běžet přes `ssh.socket` (socket activation). Port se pak mění přes override socketu (`systemctl edit ssh.socket`, `ListenStream=`), nebo se socket vypne a použije se `ssh.service` s `Port` v `sshd_config.d`. Ověř, co používá Ubuntu 26.04.
5. `/etc/ssh/sshd_config.d/99-hardening.conf`:
   ```
   Port 22022
   PasswordAuthentication no
   PermitRootLogin no
   AllowUsers <tvuj-ucet>
   ```
6. Pokud máš stálou IP, omez port 22022 ve firewallu jen na ni (volitelně).

### 5.3 fail2ban
```ini
# /etc/fail2ban/jail.local
[DEFAULT]
backend = systemd
bantime = 1h
findtime = 10m
maxretry = 5
logtarget = /var/log/fail2ban.log
ignoreip = 127.0.0.1/8 ::1 <tvoje-IP>

[sshd]
enabled = true
port = 22022
```
Ověř `fail2ban-client status sshd` a že vzniká `/var/log/fail2ban.log`.

### 5.4 Firewall
- `ufw`: povolit 22, 80, 443, 22022 (a 23 pokud telnet), vše ostatní zakázat.
- **Blokování odchozího provozu honeypotu** (viz 5.6).

### 5.5 Cowrie (Docker)
- Oficiální image `cowrie/cowrie`, vnitřní SSH port 2222 mapovat `22:2222` (telnet `23:2223` volitelně).
- Běží jako non-root (v image), `read_only: true` kde to jde, `cap_drop: [ALL]`, `no-new-privileges`, limity zdrojů, `pids_limit`.
- Log do sdíleného volume `cowrie-log` (`cowrie.json`), aplikace ho čte read-only.
- Konfigurace (`cowrie.cfg`, ověř aktuální názvy voleb):
  - `hostname` a fingerprint věrohodné (např. běžný Ubuntu/Debian server), ne výchozí.
  - **Přihlášení**: aby se boti "dostali dovnitř" a ukázali příkazy, použít `AuthRandom` (úspěch po několika pokusech) nebo vlastní `userdb.txt` (např. povolit `root`/`admin` s běžnými slabými hesly). Cílem je sbírat jak hesla, tak chování po přihlášení.
  - Limity: velikost stahovaných souborů, délka session, retence TTY logů (nebo je vypnout, ať neroste disk).
  - JSON výstup zapnutý (`output_jsonlog`).

### 5.6 Izolace honeypotu (povinné)
Cowrie emuluje `wget`/`curl` a může skutečně stahovat soubory z internetu. VPS nesmí být výchozím bodem útoků ani hostitelem malwaru:
- Kontejner Cowrie dostane vlastní Docker síť a **veškerý nový odchozí provoz se zahazuje** (pravidla v řetězci `DOCKER-USER`, např. DROP pro `conntrack --ctstate NEW` ze subnetu sítě honeypotu; odpovědi na příchozí spojení fungují dál). Pravidla musí přežít restart (skript při startu / systemd unit / `iptables-persistent`).
- URL z příkazů se přesto zalogují (jsou v příkazu), jen se reálně nestáhnou.
- Ověřit testem: z kontejneru `wget http://example.com` musí selhat.
- Zkontrolovat podmínky VPS poskytovatele (některé zakazují provoz honeypotů) a mít zálohu/snapshot.

### 5.7 Další
- `unattended-upgrades`, pravidelná aktualizace image Cowrie.
- `logrotate` pro `cowrie.json` (aplikace musí rotaci zvládnout).
- Monitoring disku (honeypot může generovat hodně dat).

---

## 6. Parsování

### 6.1 Cowrie JSON log
Každý řádek je JSON objekt. Klíčová pole: `eventid`, `timestamp`, `src_ip`, `session`, plus podle události. Mapování (ověř na skutečném logu):

| `eventid` | Uložit jako | Pole |
|---|---|---|
| `cowrie.session.connect` | `connect` | IP, `src_port`, `dst_port` |
| `cowrie.client.version` | `client_version` | řetězec verze SSH klienta |
| `cowrie.client.kex` | `kex` | `hassh`, algoritmy |
| `cowrie.login.failed` | `login_failed` | `username`, `password` |
| `cowrie.login.success` | `login_success` | `username`, `password` |
| `cowrie.command.input` | `command` | `input` |
| `cowrie.session.file_download` | `download` | `url`, `shasum`, `outfile` |
| `cowrie.session.file_upload` | `upload` | `shasum`, `filename` |
| `cowrie.direct-tcpip.request` | `tcp_forward` | cíl `dst_ip`, `dst_port` (pokus o zneužití jako proxy) |
| `cowrie.session.closed` | `closed` | `duration` |

Ostatní `eventid` ignorovat.

### 6.2 fail2ban log
```
... [sshd] Found 203.0.113.5 - 2026-10-29 14:03:11
... [sshd] Ban 203.0.113.5
... [sshd] Unban 203.0.113.5
```
Uložit jako `f2b_found`, `f2b_ban`, `f2b_unban`. Slouží hlavně k zobrazení pokusů o skutečný SSH (málo časté, ale zajímavé).

### 6.3 Požadavky na parsery
- Nevalidní/oříznutý řádek nesmí shodit aplikaci (ošetřit i neplatný JSON a chybějící pole).
- Sledování souborů přežije rotaci (změna inode / zmenšení souboru), persistovat offset.
- Při startu načíst historii a **deduplikovat**.
- Veškeré hodnoty jsou nedůvěryhodný vstup: oříznout délku, odstranit řídicí/ANSI znaky, ukládat jako text.

### 6.4 Citlivost hesel a jmen (veřejné zobrazení)
Hesla ukládáme, aby šlo dělat statistiky, ale **veřejně zobrazujeme jen agregáty**:
- **Heslo se zobrazí jen tehdy, když ho použilo ≥ 3 různých IP** (boti používají sdílené slovníky; unikátní heslo jedné osoby, třeba překlep skutečného uživatele, se tak nikdy nezveřejní). Práh je konfigurovatelný.
- Hesla a jména delší než 64 znaků, nebo vypadající jako klíče/tokeny (vysoká entropie), se maskují (`[masked]`).
- **Nikdy nezobrazovat dvojici IP + heslo** (ani v živém feedu). Živý feed ukazuje čas, zemi, uživatelské jméno (agregovaně filtrované) a typ události, ne heslo.
- Páry `jméno:heslo` jen agregovaně a se stejným prahem.
- Příkazy a URL se zobrazují jako **text** (nikdy odkazy), URL "defanged" (`hxxp://`, `[.]`), ideálně jen doména + počet.
- Neukládat ani nezobrazovat nic z vlastního SSH (tvoje přihlášení na 22022 nepatří do dat). Tvoje IP lze skrýt přes `HIDE_IPS`.

---

## 7. Datový model (SQLite)

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,                -- ISO 8601 UTC
  source TEXT NOT NULL,            -- 'cowrie' | 'fail2ban'
  type TEXT NOT NULL,              -- viz mapování v 6.1/6.2
  ip TEXT NOT NULL,
  session TEXT,                    -- Cowrie session ID
  src_port INTEGER, dst_port INTEGER,
  username TEXT, password TEXT,    -- oříznuté; password jen interně
  command TEXT,
  client_version TEXT, hassh TEXT,
  url TEXT, shasum TEXT,
  tcp_dst TEXT,
  duration REAL,
  UNIQUE (ts, source, type, ip, session, username, password, command)
);
CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_events_ip ON events(ip);
CREATE INDEX idx_events_type ON events(type);

CREATE TABLE ip_info (
  ip TEXT PRIMARY KEY,
  country_code TEXT, country TEXT, city TEXT,
  lat REAL, lon REAL,
  asn INTEGER, asn_org TEXT,
  rdns TEXT,
  is_tor INTEGER DEFAULT 0,
  first_seen TEXT, last_seen TEXT, resolved_at TEXT
);
```

- Geolokace/ASN při prvním výskytu IP, rDNS asynchronně s timeoutem, Tor seznam denně (`check.torproject.org/torbulkexitlist`).
- **Retence**: syrové události (hesla, příkazy) mazat po např. 90 dnech, agregáty a počítadla ponechat. IP adresy jsou osobní údaje (EU), proto zdokumentovat účel a retenci a mít v konfiguraci volbu maskování IP (např. poslední oktet) pro veřejné UI.

---

## 8. API (vše GET, read-only)

| Endpoint | Popis |
|---|---|
| `GET /api/map?range=24h` | Agregace po IP: počet pokusů, poslední výskyt, souřadnice, stav banu |
| `GET /api/stats?range=24h` | Počty podle typů, časová řada, heatmapa hodina × den |
| `GET /api/top/passwords?range=` | Hesla s počtem pokusů a počtem různých IP (jen přes práh z 6.4) |
| `GET /api/top/usernames?range=` | Uživatelská jména |
| `GET /api/top/credentials?range=` | Páry jméno:heslo (jen přes práh) |
| `GET /api/top/{countries,asns,clients,hassh,commands,download-domains,tcp-targets}?range=` | Ostatní žebříčky |
| `GET /api/events?limit=50` | Posledních N událostí (jen bezpečná pole, bez hesla a bez IP+heslo) |
| `GET /api/stream` | SSE – nové události |
| `GET /healthz` | Health check |

Pravidla: `range`/`limit` z whitelistu a s horním limitem, cache agregací 5–10 s, limit souběžných SSE spojení (celkem i na IP), generické chybové odpovědi.

---

## 9. Frontend

- Tmavá celostránková mapa (Leaflet + CARTO dark), body podle počtu pokusů, barva podle stavu (aktivní / zabanováno / historie).
- Pulzující animace u nových událostí ze SSE + živý feed.
- Panely: **top hesla** (s počtem různých IP), top jména, top páry, top země/ASN, top příkazy, top klienti/HASSH, domény stahovaného malwaru, graf 24 h, heatmapa, počítadla (pokusy dnes/celkem, unikátní IP, hesla vyzkoušená, uptime).
- Přepínač rozsahu 1 h / 24 h / 7 dní / vše.
- Klik na bod: IP, země/město, ASN, rDNS, počet pokusů, první/poslední výskyt, nejčastější jména (hesla ne).
- Responzivní, bez frameworku.
- **Vše z DB přes `textContent`, nikdy `innerHTML`** (XSS z hesel, jmen a příkazů útočníků).
- Poznámka v UI: poloha je přibližná (VPN, proxy, hosting); stránka "O projektu" vysvětlí, že jde o honeypot a že hesla jsou zobrazena jen agregovaně.

---

## 10. Bezpečnost (povinné)

**Honeypot a stroj**
- Cowrie v kontejneru: non-root, `cap_drop ALL`, read-only FS (mimo volume), limity zdrojů, **žádný odchozí provoz** (5.6).
- Honeypot neběží na hostiteli a nesdílí s ním nic kromě log volume (aplikace čte read-only).
- Skutečný SSH: pouze klíče, `AllowUsers`, `PermitRootLogin no`, jiný port, fail2ban.
- Na stroji nesmí být nic cenného; pravidelné snapshoty VPS.
- Aplikace a Cowrie jsou v oddělených Docker sítích; Caddy je jediný vstup k aplikaci.

**Aplikace**
- Non-root, `read_only`, `cap_drop ALL`, `no-new-privileges`, zápis jen do `/data`.
- Žádný Docker socket, žádný přístup k `fail2ban-client`, žádné spouštění příkazů ze vstupu.
- Pouze GET endpointy; žádné cookies ani trackery.

**Veřejný web**
- Caddy: HTTPS, HSTS, `Content-Security-Policy` (jen vlastní skripty + zvolené CDN/dlaždice), `X-Content-Type-Options`, `Referrer-Policy`, rate limiting (plugin `caddy-ratelimit`) a/nebo `slowapi`.
- Cache agregací, limity SSE.
- Nezobrazovat verze serveru ani interní chyby.

**Soukromí a legalita**
- Ukládat jen to, co sbírá honeypot (cizí útočníci, ne uživatelé vaší služby); žádná úspěšná přihlášení do skutečného SSH.
- Retence a práh zobrazení hesel dle 6.4 a 7.
- Licenční klíč MaxMind jen v `.env` (v `.gitignore`).

---

## 11. Struktura repozitáře

```
ssh-attack-map/
├── plan.md
├── docker-compose.yml          # cowrie, app, caddy
├── .env.example
├── Caddyfile                   # ssh.mnsk.me
├── cowrie/
│   ├── cowrie.cfg
│   └── userdb.txt
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # FastAPI, routes, SSE
│   ├── cowrie_parser.py
│   ├── f2b_parser.py
│   ├── sanitize.py             # ořezání, maskování, prahy
│   ├── geo.py                  # GeoLite2, rDNS, Tor seznam
│   ├── db.py
│   ├── static/ (index.html, app.js, style.css)
│   └── tests/
│       ├── fixtures/cowrie.sample.json
│       ├── fixtures/fail2ban.sample.log
│       ├── test_cowrie_parser.py
│       ├── test_f2b_parser.py
│       ├── test_sanitize.py     # XSS, dlouhé řetězce, práh hesel
│       └── test_api.py
├── geoip/                      # GeoLite2-*.mmdb (mimo git)
└── scripts/
    ├── setup-host.sh           # fail2ban, sshd port, ufw, DOCKER-USER pravidla
    ├── check-egress.sh         # test, že honeypot nemá odchozí síť
    └── update-geoip.sh
```

---

## 12. Fáze implementace

**Fáze 1 – Host a honeypot**: DNS, přesun skutečného SSH (5.2, bezpečný postup), fail2ban, Cowrie v Dockeru na portu 22, blokace odchozího provozu, ověření logu `cowrie.json` na skutečných datech.

**Fáze 2 – Aplikace a parsery**: FastAPI, SQLite, parser Cowrie a fail2ban, testy nad vzorovými logy, deduplikace, rotace.

**Fáze 3 – Sanitizace**: ořezání, maskování, prahy pro hesla, testy XSS a dlouhých vstupů.

**Fáze 4 – Geolokace**: GeoLite2 City + ASN, cache, rDNS, Tor seznam, privátní IP bez souřadnic.

**Fáze 5 – API**: endpointy z kapitoly 8, cache, validace, testy.

**Fáze 6 – Frontend**: mapa, žebříčky (hesla!), grafy, heatmapa.

**Fáze 7 – Živý režim**: SSE, animace, reconnect, limity.

**Fáze 8 – Veřejné nasazení**: Caddy + HTTPS + hlavičky + rate limit, hardening kontejnerů, retence dat, README.

**Fáze 9 – Volitelná rozšíření**: Cowrie telnet (port 23), AbuseIPDB (API klíč, limity), export otevřených dat (CSV/JSON), týdenní souhrn, statistika malwaru podle SHA256 (odkaz na VirusTotal jako text), více serverů.

---

## 13. Akceptační kritéria

- Pokus o přihlášení na `ssh.mnsk.me:22` se do ~2 s objeví na mapě a ve feedu.
- Skutečný SSH funguje jen na novém portu, klíčem; port 22 u něj už neběží.
- `check-egress.sh` potvrdí, že z kontejneru Cowrie nejde navázat žádné odchozí spojení.
- Po restartu kontejnerů nezmizí historie a nevzniknou duplicity; po rotaci logu pokračuje sledování.
- Heslo použité jen jednou IP se ve veřejném UI ani API nikdy neobjeví; `top/passwords` ukazuje jen hesla nad prahem.
- Žádná IP + heslo kombinace není ve veřejných odpovědích ani ve feedu.
- Jméno/heslo/příkaz typu `<script>alert(1)</script>` ani 500znakový řetězec nic nerozbije (testy).
- URL z příkazů se zobrazují jako defanged text, ne jako odkazy.
- Kontejnery neběží jako root; web nelze použít k ovládání hostitele.
- Veřejný web přežije jednoduché zahlcení (cache + rate limit).

---

## 14. Zbývající otázky

- Jaký port pro skutečný SSH (návrh 22022)? Má se omezit na tvou IP?
- Jak "vstřícný" má být honeypot (AuthRandom po několika pokusech vs. vlastní `userdb.txt`)?
- Zveřejňovat IP v plném tvaru, nebo maskované (/24)? Výchozí návrh: plné IP útočníků v mapě, volba `MASK_IPS` v konfiguraci.
- Povolit i telnet (port 23)?