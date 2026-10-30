# Stav projektu

Aktualizováno: 2026-10-30. Tento dokument se aktualizuje s ověřenými milníky; neověřené produkční kroky zůstávají výslovně otevřené.

## Příprava skutečného VPS (2026-10-30)

Následující stav je ověřen výstupy příkazů a přihlášení, které uživatel provedl na svém VPS; cloudový agent na server nemá přímé SSH připojení.

- [x] Hicoria VPS: Ubuntu 26.04 LTS, x86_64, přibližně 1,6 GiB RAM, 1,6 GiB swap a 40 GB disk.
- [x] Funkční webová záchranná konzole potvrzena uživatelem.
- [x] Správní účet `mnsk`, přihlášení SSH klíčem a funkční sudo.
- [x] Bezpečný přechod přes souběžné porty 22/22022 na výhradní správní port 22022; ověřeno z nové relace i po rebootu.
- [x] Efektivní sshd konfigurace: `PermitRootLogin no`, `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `AuthenticationMethods publickey`, `AllowUsers mnsk`.
- [x] Ověřena socket activation a explicitní původní `Port 22` v hlavním souboru; odstraněn pouze tento konflikt. `Port` je vícehodnotová volba, takže přidání 22022 samo neodebere 22.
- [x] Systémové aktualizace a restart na jádro `7.0.0-42-generic`; po restartu žádná selhaná systemd služba, UTC a aktivní synchronizovaný NTP.
- [x] Blok pro automatické bezpečnostní aktualizace s vypnutým automatickým rebootem dokončen podle potvrzení uživatele.
- [x] UFW aktivní: povoleny pouze TCP 22/22022/80/443, ostatní příchozí provoz zakázán; výstup potvrzuje IPv4 i IPv6 pravidla.
- [x] Fail2ban konfigurační test prošel, server odpovídá pong, aktivní jail `sshd` se systemd backendem a akcí omezenou na TCP 22022 podle aplikované konfigurace.
- [x] Vyhrazený log `/var/log/banmap/fail2ban/fail2ban.log`: root / banmap-logs, GID 10001, adresář 0750 a soubor 0640; nainstalována konfigurace rotace, její skutečný běh je ještě potřeba ověřit.
- [x] Připraven a v cloudu spuštěn produkční build helper s připnutým Pythonem 3.12 v Dockeru; nevyžaduje změnu výchozího Pythonu Ubuntu 26.04. Cold-cache síťové stažení helperem zbývá ověřit na VPS.
- [ ] Docker, produkční honeypot, hostitelský egress guard, geolokace a veřejné HTTPS zatím nenasazeny.

## Hotovo a ověřeno v lokálním cloudu

- [x] První milník pushnutý na GitHub `main`: commit `34479b1`.
- [x] Cowrie 3.1.4 připnuté na digest, vlastní UserDB, emulovaný shell, vypnutý telnet/SFTP/tunelování, limity zdrojů/session/artefaktů. Konfigurace ověřena v aktuálním upstreamu i v běžícím kontejneru.
- [x] Skutečné lokální SSH přihlášení a `uname -a`; anonymizovaná testovací fixture pochází ze skutečného Cowrie JSONL.
- [x] Oddělená interní síť, HAProxy s PROXY protokolem a seccomp bez nových TCP/UDP/DNS spojení. Ověřena blokace internetu i aktivního listeneru na hostiteli; příchozí SSH zůstává funkční.
- [x] FastAPI, SQLite/WAL, Cowrie/fail2ban parsery, atomické offsety, deduplikace i s NULL, částečné/poškozené/dlouhé řádky, rename/copytruncate a pozdní zápisy do rotace.
- [x] Sanitizace, token masking, prahy různých IP pro jména/hesla/páry, výslovně bezpečná veřejná projekce. Hesla, příkazy ani syrové URL nejsou ve feedu/SSE.
- [x] Read-only API, whitelist rozsahů, cache, rate limit, globální i klientské limity SSE, IP masking, HIDE_IPS, retence syrových dat a denní souhrny.
- [x] GeoLite2 City a ASN, samostatné lookupy i při chybějícím záznamu v druhé DB, ochrana proti poškozené DB, bez souřadnic pro neveřejné IP. Ověřeno skutečnými veřejnými testovacími MMDB; nejsou vydávány za produkční GeoLite2.
- [x] Volitelné PTR s timeoutem a Tor seznam mimo hlavní ingest smyčku; bezpečné předání MaxMind konfigurace oficiálnímu updateru ověřují integrační testy s nahrazeným upstreamem.
- [x] Dashboard: mapa, všechny žebříčky, graf 24 h, heatmapa, přepínání rozsahu, feed, SSE, dialog o soukromí, uptime a počty dnes/celkem.
- [x] Desktop 1440 px a mobil 390 px: bez JavaScript chyb a vodorovného přetékání; přepínače a dialog fungují. Testovaný HTML/XSS řetězec zůstává textem bez elementu/odkazu a bez spuštění.
- [x] Lokální Natural Earth obrys světa zůstává dostupný při blokovaných externích CARTO dlaždicích. Chybějící produkční geolokace je v UI jasně označena.
- [x] End-to-end SSH → skutečný log → SQLite → SSE opakovaně přibližně 1,5 s; unikátní testovací heslo se ve veřejných odpovědích neobjevuje.
- [x] Restart aplikace zachovává historii bez duplicit.
- [x] Runtime inspekce všech čtyř kontejnerů: non-root, read-only root, cap_drop ALL, no-new-privileges, limity CPU/RAM/PID. Aplikace nemá publikovaný port a zapisuje pouze do `/data`.
- [x] 52 backend testů prošlo. Skripty pro browser, SSH/SSE, restart a izolaci jsou samostatně opakovatelné.
- [x] `scripts/install.sh` byl skutečně spuštěn a prošel; ověřené wheelhouse a frontend artefakty, offline Docker build, oba Compose soubory validní, lokální i produkční Caddy konfigurace validní.
- [x] README, původní plán, dokumentace Cowrie/izolace, bezpečný návod nasazení a provozní skripty.
- [x] GitHub Actions workflow pro stejné kontroly; jeho vzdálený výsledek je samostatná věc, není nahrazován lokálními výsledky.
- [x] Do cloudového draftu uloženy `install_script`, `start_skill` a přístup k `*.basemaps.cartocdn.com`. Draft není aplikace síťové změny ani publikace snapshotu.

## Stav fází původního plánu

| Fáze | Stav |
|---|---|
| 1. Host a honeypot | Lokální honeypot a izolace ověřeny; na VPS ověřeny správní SSH, aktualizace a reboot. Fail2ban a produkční honeypot zbývají. |
| 2. Aplikace a parsery | Hotovo a testováno. |
| 3. Sanitizace | Hotovo, testy API i skutečného browser DOM. |
| 4. Geolokace | Implementace a MMDB testy hotové; produkční databáze je potřeba dodat. |
| 5. API | Hotovo a testováno. |
| 6. Frontend | Hotovo, desktop/mobil ověřeny. |
| 7. Živý režim | Hotovo, skutečná lokální SSH/SSE cesta ověřena. |
| 8. Veřejné nasazení | Konfigurace a návod připraveny; skutečné HTTPS/VPS není nasazeno. |
| 9. Volitelná rozšíření | Mimo v1. |

## Co zbývá pro skutečné veřejné nasazení

- [ ] Poskytovatel dovoluje honeypot; snapshot a otestovaná záchranná konzole.
- [ ] DNS `ssh.mnsk.me` ukazuje na VPS. Produkční override nyní publikuje IPv4; AAAA přidat až s navrženou a ověřenou IPv6 cestou.
- [x] Správní SSH 22022, pouze klíče, ne root, ověřeno z druhé relace před uvolněním 22 a znovu po rebootu VPS.
- [x] Na skutečném Ubuntu 26.04 ověřeny `ssh.socket`/`ssh.service` a efektivní `sshd -T`; změny provedl uživatel podle vedeného postupu.
- [x] Aktivní fail2ban pro správní SSH a čitelný vyhrazený UTC log adresář.
- [ ] Ověřit skutečnou rotaci fail2ban logu a zachování oprávnění.
- [ ] Nainstalovat a ověřit hostitelský DOCKER-USER/INPUT guard včetně persistence po restartu Dockeru a rebootu. Zde ověřena syntaxe skriptů a seccomp; hostitelská systemd/iptables konfigurace VPS nebyla aplikována.
- [ ] Dodat licencované GeoLite2 City + ASN a nastavit aktualizace. Živé stažení pomocí vlastního MaxMind účtu nebylo bez přihlašovacích údajů provedeno.
- [ ] Veřejné HTTPS/Caddy/ACME, HSTS, správné příchozí porty a end-to-end test z internetu včetně původní veřejné IP.
- [ ] Zálohy, monitoring místa, pravidelné promazávání rotací a obnovení po rebootu VPS.
- [ ] V cloudovém nastavení zkontrolovat a uložit draft, potom prostředí publikovat. Obnovení snapshotu v novém tasku dosud nebylo ověřeno.

## Důležité hranice

Lokální cloud není připojen ke skutečnému VPS. Výchozí telnet je vypnutý, login používá UserDB a volitelné RDNS/Tor jsou vypnuté. Plné IP odpovídají zadání; `MASK_IPS` je volitelné. `range=all` u mapy a žebříčků znamená dostupné retenční okno; celoživotní souhrnné počty přetrvávají. HMAC identifikátory jsou pseudonymní, proto se DB, sůl, logy i zálohy musí chránit. Žádné externí nasazení ani nová cloudová snapshot verze nejsou tímto dokumentem prohlášeny za publikované.
