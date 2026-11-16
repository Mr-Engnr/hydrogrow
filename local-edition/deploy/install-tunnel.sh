#!/usr/bin/env bash
# install-tunnel.sh: optional Cloudflare named tunnel for a public demo URL (docs/EXPO_RUNBOOK.md, "Public link")
# Idempotent; run by setup.sh when /etc/hydrogrow/cloudflared.env exists, or by hand:
#   sudo bash deploy/install-tunnel.sh
# Needs: the token in /etc/hydrogrow/cloudflared.env (TUNNEL_TOKEN=...), internet for the one-time download.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TUN_FILE=/etc/hydrogrow/cloudflared.env
BIN=/usr/local/bin/cloudflared
say() { printf '[tunnel] %s\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$TUN_FILE" ] || { say "no $TUN_FILE; nothing to do (see docs/EXPO_RUNBOOK.md, "Public link")"; exit 0; }
grep -q '^TUNNEL_TOKEN=.\+' "$TUN_FILE" || { say "TUNNEL_TOKEN empty in $TUN_FILE"; exit 1; }
chmod 600 "$TUN_FILE"

case "$(dpkg --print-architecture)" in arm64) A=arm64 ;; armhf) A=arm ;; amd64) A=amd64 ;; *) say "unsupported arch"; exit 1 ;; esac
if [ ! -x "$BIN" ]; then
  say "downloading cloudflared ($A) from GitHub releases"
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$A" -o "$BIN.tmp"
  chmod 755 "$BIN.tmp"; mv "$BIN.tmp" "$BIN"
fi
say "cloudflared $("$BIN" --version 2>&1 | head -1)"

# never run as root: nobody only needs outbound HTTPS + localhost:8080
rendered="$(cat "$APP_DIR/deploy/systemd/hydrogrow-tunnel.service")"
if [ ! -f /etc/systemd/system/hydrogrow-tunnel.service ] || [ "$rendered" != "$(cat /etc/systemd/system/hydrogrow-tunnel.service)" ]; then
  printf '%s\n' "$rendered" > /etc/systemd/system/hydrogrow-tunnel.service
  systemctl daemon-reload
fi
systemctl enable hydrogrow-tunnel.service >/dev/null 2>&1
systemctl restart hydrogrow-tunnel.service || true
say "unit: $(systemctl is-active hydrogrow-tunnel.service) (it stays 'activating' until the internet is reachable; that is by design)"
HN="$(sed -n 's/^TUNNEL_HOSTNAME=//p' "$TUN_FILE")"
say "check later:  systemctl status hydrogrow-tunnel --no-pager ; curl -sI https://${HN:-<your-hostname>}/health"
