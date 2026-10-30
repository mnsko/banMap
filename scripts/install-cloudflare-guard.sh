#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo 'Run this host firewall installer as root.' >&2; exit 1; fi
cd "$(dirname "$0")/.."
policy_file="$PWD/runtime/cloudflare/proxy.env"
python3 scripts/cloudflare-policy.py show --policy "$policy_file"
ingress_iface="${WEB_INGRESS_INTERFACE:-$(ip -4 route show default | awk '{for(i=1;i<=NF;i++) if($i=="dev") {print $(i+1);exit}}')}"
[ -n "$ingress_iface" ] || { echo 'No default IPv4 interface; set WEB_INGRESS_INTERFACE.' >&2; exit 1; }
ip link show dev "$ingress_iface" >/dev/null
iptables -w -S DOCKER-USER >/dev/null
rules_dir=$(mktemp -d)
trap 'rm -rf "$rules_dir"' EXIT
python3 scripts/cloudflare-policy.py rules --interface "$ingress_iface" --family 4 > "$rules_dir/v4"
python3 scripts/cloudflare-policy.py rules --interface "$ingress_iface" --family 6 > "$rules_dir/v6"
# Validate everything before changing either family; never flush unrelated rules.
for tool in iptables ip6tables; do
    if ! "$tool" -w -S BANMAP-CF-WEB >/dev/null 2>&1; then "$tool" -w -N BANMAP-CF-WEB; fi
done
iptables-restore --wait --noflush < "$rules_dir/v4"
ip6tables-restore --wait --noflush < "$rules_dir/v6"
iptables -w -C DOCKER-USER -j BANMAP-CF-WEB 2>/dev/null || iptables -w -I DOCKER-USER 1 -j BANMAP-CF-WEB
iptables -w -C INPUT -j BANMAP-CF-WEB 2>/dev/null || iptables -w -I INPUT 1 -j BANMAP-CF-WEB
ip6tables -w -C INPUT -j BANMAP-CF-WEB 2>/dev/null || ip6tables -w -I INPUT 1 -j BANMAP-CF-WEB
if ip6tables -w -S DOCKER-USER >/dev/null 2>&1; then
    ip6tables -w -C DOCKER-USER -j BANMAP-CF-WEB 2>/dev/null || ip6tables -w -I DOCKER-USER 1 -j BANMAP-CF-WEB
fi
echo "Cloudflare-only web ingress applied on $ingress_iface for TCP 80/443; SSH ports are unaffected."
