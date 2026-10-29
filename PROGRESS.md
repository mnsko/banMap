# Stav projektu

Aktualizováno: 2026-10-29. Tento dokument se aktualizuje společně s ověřenými milníky.

## Hotovo a ověřeno lokálně

- [x] Založení projektu podle `plan.md`, připnuté verze obrazů a Python závislosti s kontrolou hashů.
- [x] Cowrie 3.1.4, emulovaný shell, vlastní UserDB, vypnutý telnet/SFTP/tunelování, limity session a stahovaných artefaktů.
- [x] Skutečné lokální SSH přihlášení a emulovaný `uname -a`; testovací fixture pochází ze skutečného Cowrie logu s nahrazenou IP.
- [x] Samostatná interní síť, HAProxy s původní IP, seccomp blokující nové odchozí TCP/UDP/DNS spojení.
- [x] Kontrolní test potvrdil i blokaci spojení k živému listeneru na hostiteli; příchozí SSH nadále funguje.
- [x] FastAPI, SQLite/WAL, Cowrie/fail2ban parsery, deduplikace, persistované offsety, částečné řádky, rename/copytruncate rotace a pozdní zápisy.
- [x] Sanitizace, maskování tokenů, prahy různých IP pro jména/hesla/páry, explicitní veřejná projekce bez hesel.
- [x] API s validací, cache, rate limitem, SSE a limity souběhu, IP masking, HIDE_IPS, retence a anonymní denní souhrny.
- [x] Offline GeoLite2 integrace, volitelné PTR/Tor obohacení mimo hlavní ingest smyčku; testy chybějících DB a mockovaného City/ASN lookupu.
- [x] 45 unit/integration testů parserů, úložiště, soukromí, API a bezpečnostních limitů prošlo.

## Rozpracováno v aktuálním milníku

- [ ] Dokončení a ověření dashboardu v desktopovém i mobilním prohlížeči.
- [x] End-to-end smoke: SSH → skutečný log → SQLite → veřejný feed/SSE za 1,532 s; tajné testovací heslo není ve veřejných odpovědích.
- [ ] Samostatné ověření restartu bez duplicit.
- [ ] Opakovatelné instalační/startovací skripty, produkční návod, CI a uložená cloudová konfigurace.
- [ ] První push ověřeného základu na GitHub (připraven tento commit).

## Vyžaduje skutečné VPS / vlastní konfiguraci

- [ ] Poskytovatel dovoluje honeypot; snapshot a funkční záchranná konzole.
- [ ] DNS `ssh.mnsk.me` ukazuje na VPS. Ověřit i AAAA; nenechat nefunkční IPv6 záznam.
- [ ] Správní SSH na 22022, pouze klíče, ne root, ověřeno z druhé relace před uvolněním 22.
- [ ] Ověřit na Ubuntu 26.04 aktivní `ssh.socket`/`ssh.service` a efektivní konfiguraci sshd.
- [ ] Aktivní fail2ban pouze pro správní SSH, čitelné UTC logy a retence na hostiteli.
- [ ] Hostitelský DOCKER-USER/INPUT guard, persistence po restartu Dockeru a rebootu.
- [ ] Licencované produkční GeoLite2 City + ASN a aktualizace. Bez nich nejsou mapové souřadnice.
- [ ] Veřejné HTTPS/Caddy/ACME, HSTS, příchozí porty a end-to-end test z internetu.
- [ ] Zálohy, monitoring místa, retence Cowrie logů a kontrola obnovení po rebootu VPS.

## Omezení a rozhodnutí

- Lokální cloud není připojen ke skutečnému VPS. DNS, SSH/firewall VPS ani veřejné nasazení se zde nemění.
- Výchozí správní port 22022; telnet je vypnutý; emulovaný login přes UserDB.
- Plné IP dle zadání, volitelný `MASK_IPS`; hesla nikdy nejsou v feedu/SSE.
- `range=all` u mapy a žebříčků znamená dostupné retenční okno; celoživotní souhrnné počty zůstávají zvlášť.
- Doplňky fáze 9 (AbuseIPDB, export, více senzorů, týdenní přehledy) zůstávají mimo v1.
- Žádné vnější nasazení ani nová cloudová snapshot verze zatím nebyly publikovány.
