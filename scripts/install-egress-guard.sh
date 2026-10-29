#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" != 0 ]; then
  echo 'Run this host firewall installer as root on the target VPS.' >&2
  exit 1
fi
command -v iptables >/dev/null
iptables -w -S DOCKER-USER >/dev/null || { echo 'Docker iptables DOCKER-USER chain is unavailable; do not expose the honeypot.' >&2; exit 1; }
# Preserve all unrelated host and Docker rules. Update our own chains atomically.
for chain in BANMAP-EGRESS BANMAP-HOST; do
  if ! iptables -w -S "$chain" >/dev/null 2>&1; then iptables -w -N "$chain"; fi
done
iptables-restore --wait --noflush <<'RULES'
*filter
-F BANMAP-EGRESS
-A BANMAP-EGRESS -s 172.30.77.0/24 -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
-A BANMAP-EGRESS -s 172.30.77.3/32 -d 172.30.77.2/32 -p tcp --dport 2222 -j RETURN
-A BANMAP-EGRESS -s 172.30.77.0/24 -j DROP
-A BANMAP-EGRESS -j RETURN
-F BANMAP-HOST
-A BANMAP-HOST -i br-banmap-hp -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
-A BANMAP-HOST -i br-banmap-hp -j DROP
-A BANMAP-HOST -j RETURN
COMMIT
RULES
iptables -w -C DOCKER-USER -j BANMAP-EGRESS 2>/dev/null || iptables -w -I DOCKER-USER 1 -j BANMAP-EGRESS
iptables -w -C INPUT -j BANMAP-HOST 2>/dev/null || iptables -w -I INPUT 1 -j BANMAP-HOST
iptables -w -S BANMAP-EGRESS
iptables -w -S BANMAP-HOST
