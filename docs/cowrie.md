# Cowrie a izolace

Konfigurační klíče i pole událostí byly ověřeny proti oficiálnímu repozitáři Cowrie, tag `v3.1.4`, commit `085ed091a84ae1cee7f15b6e8aa549d11826a0f7`:

- [výchozí konfigurace](https://github.com/cowrie/cowrie/blob/v3.1.4/src/cowrie/data/etc/cowrie.cfg.dist)
- [Dockerfile](https://github.com/cowrie/cowrie/blob/v3.1.4/docker/Dockerfile)
- [JSON output](https://github.com/cowrie/cowrie/blob/v3.1.4/src/cowrie/output/jsonlog.py)
- [UserDB](https://github.com/cowrie/cowrie/blob/v3.1.4/src/cowrie/core/auth.py)
- [SSH transport / HASSH / PROXY protocol](https://github.com/cowrie/cowrie/blob/v3.1.4/src/cowrie/ssh/transport.py)

Image je distroless, UID/GID 999; nemá shell ani wget. Testy proto používají jeho Python. Fixture JSONL vznikla skutečným lokálním SSH připojením; IP je nahrazena dokumentační adresou, přihlašovací údaje jsou záměrně syntetické.

## Síť

Docker na `internal: true` síti nepublikuje SSH port. HAProxy proto má dvě rozhraní; poslouchá výhradně na vstupní adrese `172.30.78.2:2222` a spojení předává na Cowrie `172.30.77.2:2222` s PROXY hlavičkou. Cowrie důvěřuje PROXY protokolu jen na své oddělené síti; nejsou na ní další aplikace. Skutečná veřejná IP se ověřuje také testem z internetu na VPS; lokální NAT přirozeně ukazuje adresu lokální brány.

Samotná interní síť nedokáže zablokovat hostitele ani všechny cesty přes Docker DNS. Proto má Cowrie navíc seccomp profil, který zakazuje `connect`, `sendmsg`, `sendmmsg`, multiplexovaný `socketcall` a io_uring. `sendto` je povolen jen s nulovým cílovým ukazatelem pro zápis do již přijatých TCP spojení. Sockety se mohou vytvářet/přijímat, takže emulované SSH funguje; Cowrie nemůže zahájit TCP/UDP/DNS spojení. Test zahrnuje aktivní listener na hostiteli, nejen zavřený port. Profil neaplikovat na aplikaci, Caddy ani HAProxy.

Profil vychází z Docker/Moby default seccomp profilu [moby/profiles](https://github.com/moby/profiles/blob/4b8214fc4971e06172938a1f1554ccff6647ee80/seccomp/default.json), commit `4b8214fc4971e06172938a1f1554ccff6647ee80`, licence Apache-2.0 v `cowrie/SECCOMP-LICENSE`. Původní default-deny a ostatní pravidla zůstávají zachovány. Upraveny jsou jen výše uvedené síťové syscall položky. Testováno na Linux amd64 s Docker Engine 28.4.0; jiné architektury a upgrady obrazů vyžadují znovu spustit integrační a egress testy.

Hostitelský firewall z návodu je další vrstva. Nepřipojuj Cowrie na běžnou Docker síť, neměň shell backend na proxy a nepřidávej capabilities, Docker socket ani mounty hostitelských citlivých adresářů.
