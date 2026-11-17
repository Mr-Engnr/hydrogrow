#!/usr/bin/env bash
# healthcheck.sh: one-screen status of the expo stack. Safe to run any time.
#   bash tools/healthcheck.sh            # on the Pi
#   HOST=<pi-hostname>.local bash tools/healthcheck.sh   # from another machine (service/RAM rows need the Pi)
set -u
HOST="${HOST:-127.0.0.1}"; PORT="${PORT:-8080}"
URL="http://$HOST:$PORT/health"
ok=0; fail=0
pass() { printf '  \033[32mOK\033[0m   %s\n' "$1"; ok=$((ok+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail+1)); }

echo "HydroGrow healthcheck  $(date -u +%Y-%m-%dT%H:%M:%SZ)  target $URL"
if command -v systemctl >/dev/null 2>&1 && [ "$HOST" = "127.0.0.1" ]; then
  echo "services (RSS MB / %CPU since start):"
  for u in mosquitto hydrogrow-ingest hydrogrow-backend hydrogrow-firmware; do
    st=$(systemctl is-active "$u" 2>/dev/null); pid=$(systemctl show -p MainPID --value "$u" 2>/dev/null)
    if [ "$st" = "active" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
      rss=$(awk '/VmRSS/ {printf "%d", $2/1024}' "/proc/$pid/status" 2>/dev/null)
      cpu=$(ps -o %cpu= -p "$pid" 2>/dev/null | tr -d ' ')
      pass "$(printf '%-20s active  pid %-6s %4s MB  %5s%%' "$u" "$pid" "${rss:-?}" "${cpu:-?}")"
    else
      bad "$(printf '%-20s %s' "$u" "$st")"
    fi
  done
  if [ -f /etc/hydrogrow/cloudflared.env ]; then
    st=$(systemctl is-active hydrogrow-tunnel 2>/dev/null)
    case "$st" in
      active)     pass "$(printf '%-20s %s  https://%s' hydrogrow-tunnel "$st" "$(sed -n 's/^TUNNEL_HOSTNAME=//p' /etc/hydrogrow/cloudflared.env 2>/dev/null)")" ;;
      activating) printf '  [33mWAIT[0m %-20s waiting for internet (optional)
' hydrogrow-tunnel ;;
      *)          printf '  [33mWARN[0m %-20s %s (optional, local stack unaffected)
' hydrogrow-tunnel "$st" ;;
    esac
  fi
  echo "system: $(free -m | awk '/Mem:/ {printf "RAM %d/%d MB used", $3, $2}'), load $(cut -d' ' -f1-3 /proc/loadavg), temp $(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 || echo '?'), disk $(df -h / | awk 'NR==2 {print $4 " free"}')"
fi

echo "backend /health:"
body=$(curl -s -m 5 -w '\n%{http_code}' "$URL" 2>/dev/null) || body="connection failed
000"
code=$(printf '%s' "$body" | tail -n1); json=$(printf '%s' "$body" | sed '$d')
if [ "$code" = "200" ] || [ "$code" = "503" ]; then
  python3 - "$json" <<'EOF' || echo "$json"
import json, sys
h = json.loads(sys.argv[1])
print(f"  mode={h.get('mode')}  ok={h.get('ok')}  uptime={h.get('uptime_s')}s")
for k, v in h.get("checks", {}).items():
    flag = "OK  " if v.get("ok") else "FAIL"
    detail = {kk: vv for kk, vv in v.items() if kk not in ("ok",)}
    print(f"  [{flag}] {k:13s} {json.dumps(detail)[:150]}")
EOF
  [ "$code" = "200" ] && pass "HTTP 200: all checks green" || bad "HTTP 503: see checks above"
else
  bad "backend unreachable ($code): $json"
fi

echo "dashboard: $(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://$HOST:$PORT/" 2>/dev/null) (200 = served)"
echo "twins:     $(curl -s -m 5 "http://$HOST:$PORT/twins" 2>/dev/null | head -c 120)"
echo "source:    $(curl -s -m 5 "http://$HOST:$PORT/api/pidata/source" 2>/dev/null | head -c 160)"
printf '\n%d ok, %d failed\n' "$ok" "$fail"
[ "$fail" -eq 0 ]
