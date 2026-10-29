#!/usr/bin/env bash
# Read-only preflight; SSH and firewall changes must follow docs/deployment.md.
set -euo pipefail
printf 'Host preflight (no changes are applied)\n'
if [ -r /etc/os-release ]; then
  . /etc/os-release
  printf 'OS: %s\n' "$PRETTY_NAME"
fi
for tool in docker sshd fail2ban-client ufw iptables logrotate; do
  if command -v "$tool" >/dev/null; then printf 'Available: %s\n' "$tool"; else printf 'MISSING: %s\n' "$tool"; fi
done
if command -v systemctl >/dev/null; then
  systemctl is-active ssh.socket ssh.service || true
  systemctl cat ssh.socket || true
fi
if command -v ss >/dev/null; then ss -lnt; fi
printf '\nBefore production: test provider console and SSH key login on 22022 from a second terminal.\nRead docs/deployment.md; this script does not relocate SSH or change firewall policy.\n'
