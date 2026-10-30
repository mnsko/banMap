# Web za Cloudflare proxy, SSH honeypot přímo na IP

Tato volitelná varianta vrstvi `docker-compose.cloudflare.yml` až za základní a produkční Compose. Cloudflare zajišťuje veřejný HTTP/HTTPS vstup, nikoli běžné SSH porty. Správní SSH používá přímo IP VPS a port 22022, honeypot přímo IP VPS a port 22. Nepřidávej zatím AAAA originu; Compose publikuje IPv4. IPv6 návštěvníci mohou nadále přicházet přes Cloudflare edge.

## DNS, TLS a cache v Cloudflare

- A záznam `ssh` směřuje na IPv4 VPS, **Proxied / oranžový mrak**.
- SSL/TLS režim **Full (strict)** nastav pouze pro tento hostname: Rules → Overview → Create rule → Configuration Rule, výraz `(http.host eq "ssh.mnsk.me")`, nastavení SSL → Strict / Full (strict). To ponechá ostatní hostname zóny beze změny. Cloudflare toto nastavení dokumentuje v [Configuration Rules settings](https://developers.cloudflare.com/rules/configuration-rules/settings/#ssl). Caddy získává veřejně důvěryhodný certifikát i pro spojení Cloudflare → origin. Není potřeba Cloudflare API token ani DNS challenge plugin.
- HTTP → HTTPS přesměrovává Caddy. Port 80 musí přenést HTTP ACME challenge přes Cloudflare na origin, včetně obnovování certifikátu. Pokud je Always Use HTTPS pro celou zónu již zapnuté, nevypínej ho bez posouzení ostatních webů; před zveřejněním je potřeba ověřit skutečnou ACME cestu a případně zvolit odpovídající způsob vydání certifikátu. TLS-ALPN challenge je v této variantě vypnutá, protože veřejné TLS ukončuje Cloudflare.
- V Cache Rules nastav **Bypass cache** pro následující výraz. Pokud máš obecné cache pravidlo, ujisti se, že výsledné vyhodnocení těchto cest opravdu vede na bypass:

```text
(http.host eq "ssh.mnsk.me" and (
  starts_with(http.request.uri.path, "/api/") or
  http.request.uri.path eq "/healthz" or
  starts_with(http.request.uri.path, "/.well-known/acme-challenge/")
))
```

API/SSE navíc dostává `Cache-Control: no-store` z Caddy. Nepoužívej pro tyto cesty Cache Everything ani interaktivní WAF challenge. Pokud ACME validace selže na WAF pravidle, povol pouze příslušnou challenge cestu; nevypínej ochrany celé zóny. Web Analytics a Rocket Loader nejsou pro aplikaci potřeba; aplikace má vlastní CSP a nemá analytické skripty.

## Aktuální důvěryhodné rozsahy

```sh
cd /opt/banmap
git pull --ff-only
sudo python3 scripts/cloudflare-policy.py fetch
```

Skript stahuje veřejný seznam z pevné oficiální HTTPS adresy `https://api.cloudflare.com/client/v4/ips`, ověřuje strukturu, rodiny adres, veřejné a kanonické CIDR a odmítá příliš široké prefixy. Nepotřebuje účet, token ani heslo. Při chybě nepřepíše poslední úspěšný soubor. Výsledný `runtime/cloudflare/proxy.env` je ignorovaný Gitem a obsahuje pouze veřejné rozsahy. Nepoužívej sem ručně zkopírované testovací rozsahy.

Caddy z tohoto seznamu současně odvozuje důvěru v `CF-Connecting-IP` i povolené skutečné TCP protistrany. Přímý návštěvník originu dostane 403 i se zfalšovanými hlavičkami; ochrana funguje také před obnovením hostitelských firewallových pravidel po rebootu. Aplikaci se předává ověřené `{client_ip}` jako X-Forwarded-For, aby rate limit a SSE limity fungovaly pro jednotlivé návštěvníky.

## Hostitelské guardy a startup

Nejdřív dokonči SSH/fail2ban a produkční přípravu z `deployment.md`. Ověř, že na originu neprobíhá jiný web na 80/443; pravidla jsou určena pro tento vyhrazený VPS. Pak nainstaluj honeypot guard a Cloudflare guard:

```sh
sudo install -Dm755 scripts/install-egress-guard.sh /usr/local/lib/banmap/install-egress-guard.sh
sudo install -m644 deploy/banmap-egress.service /etc/systemd/system/banmap-egress.service
sudo install -m644 deploy/banmap-cloudflare.service /etc/systemd/system/banmap-cloudflare.service
sudo systemctl daemon-reload
sudo systemctl enable --now banmap-egress.service banmap-cloudflare.service
```

Cloudflare guard používá stejný validovaný soubor jako Caddy. Omezuje příchozí TCP 80/443 na výchozím rozhraní přes INPUT a DOCKER-USER, IPv4 i IPv6; portů 22/22022 se netýká. Zachovává ostatní firewallová pravidla. Při více síťových rozhraních je potřeba explicitně nastavit `WEB_INGRESS_INTERFACE` pro službu a ověřit každou skutečnou vstupní cestu. Návod pro jeden default interface odpovídá aktuálnímu VPS.

Po přípravě soukromého `.env` a ověření DNS/TLS/cache spusť:

```sh
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloudflare.yml config --quiet
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloudflare.yml up -d --build --wait --wait-timeout 120
```

Vyžaduje existující policy soubor. Běžný dvousouborový produkční postup bez Cloudflare override zůstává přímým nasazením a tuto ochranu nemá; nemíchej oba způsoby správy stejného projektu.

## Ověření a provoz

- `sudo systemctl status banmap-egress banmap-cloudflare --no-pager` a skutečné pravidlo v DOCKER-USER.
- `sudo docker compose ... exec -T app python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/healthz").read().decode())'` ověří aplikaci přímo uvnitř kontejneru; Cloudflare-only Caddy úmyslně nepřijímá lokální klienty jako veřejnou proxy.
- Z běžného externího klienta ověř HTTPS domény, `Cache-Control: no-store` pro API, živé SSE a skutečný webový klientský rate limit. Přímé HTTPS originu se SNI/Host domény musí vracet 403 (nebo být zahozené firewallem), i při podvržené CF hlavičce.
- SSH do honeypotu testuj na IP VPS, ne na proxied doméně. Zdrojem Cowrie událostí je IP SSH klienta, nezávislá na Cloudflare HTTP hlavičkách.
- Pravidelně obnovuj seznam: `sudo python3 scripts/cloudflare-policy.py fetch`, potom `sudo systemctl restart banmap-cloudflare` a `sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloudflare.yml up -d caddy`. Compose promítne aktualizovaný env_file do kontejneru. Při neúspěšném downloadu ponech platný předchozí seznam a zjisti příčinu.
- Po úpravě frontendových souborů případně vyčisti jejich Cloudflare cache. Zálohy a monitoring originu zůstávají potřeba; veřejný honeypot znamená, že IP stroje není skrytá.

Konfigurace je validována lokálně. `scripts/check-cloudflare.py` ověřuje skutečný Caddy v oddělené Docker síti, s interní testovací CA a plným ověřením TLS: správné IP z důvěryhodné proxy, ignorování podvrženého XFF, no-store a odmítnutí nedůvěryhodné protistrany. Produkční Cloudflare/ACME cestu a hostitelské guardy je nutné ověřit na skutečném VPS. Cloudové prostředí samotné nyní nemá povolený přístup k veřejnému Cloudflare API (403); tuto síťovou operaci provádí přípravný příkaz na VPS, není nahrazena testovacími daty.
