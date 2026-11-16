#!/usr/bin/env bash
# setup.sh: the one command on the Pi (Local Edition).
#
#   git clone https://github.com/Mr-Engnr/hydrogrow.git && cd hydrogrow
#   sudo bash local-edition/setup.sh                   # as your normal user via sudo
#   sudo bash local-edition/setup.sh --force           # redo every step even if stamped done
#   bash local-edition/setup.sh --dry-run              # laptop: non-hardware checks only, no root needed
#
# Chains: ask PLANTING_DATE / demo password / optional tunnel token
#         -> deploy/bootstrap.sh -> (reboot + auto-resume if I2C/camera were just enabled)
#         -> deploy/hwtest.py -> deploy/install.sh -> optional Cloudflare tunnel -> tools/healthcheck.sh
# Every step writes a stamp in <app>/.setup/ and is skipped on rerun when done; a failed step is
# retried from that point. Final PASS/FAIL table is printed and saved to <app>/.setup/REPORT.txt.
set -uo pipefail

MODE=run; FORCE=0; RESUME=0
for a in "$@"; do case "$a" in --dry-run) MODE=dry ;; --force) FORCE=1 ;; --resume) RESUME=1 ;; esac; done

APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"   # .../local-edition
REPO_DIR="$(cd "$APP_DIR/.." && pwd)"
if [ "$MODE" = "dry" ]; then
  APP_USER="$(id -un)"
  HOME_DIR="$APP_DIR/.setup/fakehome"; ETC_DIR="$APP_DIR/.setup/fake-etc"
else
  [ "$(id -u)" -eq 0 ] || { echo "run with sudo: sudo bash $0"; exit 1; }
  APP_USER="${APP_USER:-${SUDO_USER:-}}"
  if [ -z "$APP_USER" ] || [ "$APP_USER" = "root" ]; then
    echo "run as your normal user via sudo (or set APP_USER=<user>): the services run as that user"; exit 1
  fi
  HOME_DIR="$(getent passwd "$APP_USER" | cut -d: -f6)"; [ -n "$HOME_DIR" ] || { echo "user $APP_USER not found"; exit 1; }
  ETC_DIR=/etc/hydrogrow
fi
STATE="$APP_DIR/.setup"
ENV_FILE="$ETC_DIR/hydrogrow.env"; TUN_FILE="$ETC_DIR/cloudflared.env"
export APP_USER   # bootstrap.sh / install.sh run the services as this user
RESUME_UNIT=/etc/systemd/system/hydrogrow-setup-resume.service
LOG="$STATE/setup.log"
declare -a REPORT=()

c_g=$'\033[32m'; c_r=$'\033[31m'; c_y=$'\033[33m'; c_b=$'\033[1m'; c_0=$'\033[0m'
say()  { printf '%s[setup]%s %s\n' "$c_b" "$c_0" "$*" | tee -a "$LOG" 2>/dev/null || printf '[setup] %s\n' "$*"; }
head_() { printf '\n%s==== %s ====%s\n' "$c_b" "$*" "$c_0" | tee -a "$LOG" 2>/dev/null; }
stamp()  { touch "$STATE/done.$1"; }
done_()  { [ "$FORCE" -eq 0 ] && [ -f "$STATE/done.$1" ]; }
rec()    { REPORT+=("$1|$2|$3"); }   # name|PASS/FAIL/SKIP/WARN|detail
as_user(){ if [ "$MODE" = "dry" ]; then "$@"; else runuser -u "$APP_USER" -- "$@"; fi; }

step_run() {  # name  fn   -> runs fn unless stamped; records PASS/FAIL; returns fn status
  local name="$1" fn="$2"
  if done_ "$name"; then rec "$name" SKIP "already done (use --force to redo)"; say "$name: already done"; return 0; fi
  head_ "$name"
  if "$fn"; then stamp "$name"; return 0; else return 1; fi
}

# ================================================================== steps
valid_date() { [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && date -d "$1" >/dev/null 2>&1; }

s_env() {
  mkdir -p "$ETC_DIR"
  if [ ! -f "$ENV_FILE" ]; then
    bash "$APP_DIR/deploy/render-env.sh" "$HOME_DIR" > "$ENV_FILE"
    [ "$MODE" = "dry" ] || { chmod 640 "$ENV_FILE"; chown "root:$APP_USER" "$ENV_FILE"; }
    say "created $ENV_FILE"
  fi
  # current values
  local cur_date cur_pw
  cur_date="$(grep -E '^PLANTING_DATE=' "$ENV_FILE" | cut -d= -f2-)"; cur_pw="$(grep -E '^DEMO_USER_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
  local pd="${PLANTING_DATE:-}" pw="${DEMO_USER_PASSWORD:-}" tok="${CLOUDFLARE_TUNNEL_TOKEN:-}" thost="${TUNNEL_HOSTNAME:-}"
  if [ "$MODE" = "dry" ]; then pd="${pd:-2026-10-20}"; pw="${pw:-dry-run-password}"; fi
  if [ -z "$pd" ] && [ -n "$cur_date" ] && [ "$FORCE" -eq 0 ]; then pd="$cur_date"; fi
  if [ -z "$pw" ] && [ -n "$cur_pw" ] && [ "$FORCE" -eq 0 ]; then pw="$cur_pw"; fi
  if [ -t 0 ]; then
    while ! valid_date "$pd"; do
      read -r -p "  Planting date (day 1 of the grow, YYYY-MM-DD) [${cur_date:-none}]: " pd </dev/tty
      [ -z "$pd" ] && [ -n "$cur_date" ] && pd="$cur_date"
      valid_date "$pd" || echo "  not a valid date"
    done
    while [ -z "$pw" ]; do
      read -r -s -p "  Dashboard demo password (user $(grep -E '^DEMO_USER_EMAIL=' "$ENV_FILE" | cut -d= -f2-)): " pw </dev/tty; echo
      local pw2; read -r -s -p "  Repeat: " pw2 </dev/tty; echo
      [ "$pw" = "$pw2" ] || { echo "  passwords differ"; pw=""; }
    done
    if [ ! -f "$TUN_FILE" ] && [ -z "$tok" ]; then
      read -r -p "  Cloudflare tunnel token (optional public URL; Enter to skip, see docs/EXPO_RUNBOOK.md): " tok </dev/tty
      if [ -n "$tok" ] && [ -z "$thost" ]; then read -r -p "  Public hostname routed to this tunnel (e.g. hydrogrow.example.com): " thost </dev/tty; fi
    fi
  else
    valid_date "$pd" || { rec env FAIL "no TTY and PLANTING_DATE not set/invalid (export PLANTING_DATE=YYYY-MM-DD)"; return 1; }
    [ -n "$pw" ] || { rec env FAIL "no TTY and DEMO_USER_PASSWORD not set"; return 1; }
  fi
  sed -i -E "s#^\#?PLANTING_DATE=.*#PLANTING_DATE=$pd#" "$ENV_FILE"
  grep -q '^PLANTING_DATE=' "$ENV_FILE" || echo "PLANTING_DATE=$pd" >> "$ENV_FILE"
  pw_esc="$(printf '%s' "$pw" | sed -e 's/[&#\\]/\\&/g')"
  sed -i -E "s#^DEMO_USER_PASSWORD=.*#DEMO_USER_PASSWORD=$pw_esc#" "$ENV_FILE"
  if [ -n "$tok" ]; then
    printf 'TUNNEL_TOKEN=%s\nTUNNEL_HOSTNAME=%s\n' "$tok" "$thost" > "$TUN_FILE"
    [ "$MODE" = "dry" ] || chmod 600 "$TUN_FILE"
    say "tunnel token stored in $TUN_FILE"
  fi
  rec env PASS "PLANTING_DATE=$pd, demo password set$([ -f "$TUN_FILE" ] && echo ', tunnel token present' || echo ', no tunnel')"
  return 0
}

s_bootstrap() {
  if [ "$MODE" = "dry" ]; then
    local bad=0 f
    for f in setup.sh deploy/bootstrap.sh deploy/install.sh deploy/detect.sh deploy/render-env.sh deploy/install-tunnel.sh tools/healthcheck.sh; do bash -n "$APP_DIR/$f" || { say "syntax error: $f"; bad=1; }; done
    for f in local-edition/deploy/hwtest.py local-edition/ingest/ingest.py local-edition/tools/fake_pi.py local-edition/tools/replay.py firmware/main.py firmware/mqtt_publisher.py; do python -m py_compile "$REPO_DIR/$f" 2>/dev/null || python3 -m py_compile "$REPO_DIR/$f" || { say "py compile error: $f"; bad=1; }; done
    for f in local-edition/deploy/requirements-pi.lock local-edition/deploy/requirements-pi.resolved.txt local-edition/broker/mosquitto.conf ml/nutrient-prediction/models/nutrient_model.pkl dashboard/src/index.js; do [ -f "$REPO_DIR/$f" ] || { say "missing: $f"; bad=1; }; done
    [ $bad -eq 0 ] && { rec bootstrap PASS "dry-run: scripts parse, Python compiles, lock + nutrient model + shared dashboard present"; return 0; }
    rec bootstrap FAIL "dry-run checks failed (see above)"; return 1
  fi
  if bash "$APP_DIR/deploy/bootstrap.sh" 2>&1 | tee -a "$LOG"; then rec bootstrap PASS "venv, pins, models, apt, I2C/camera"; return 0; fi
  rec bootstrap FAIL "see $LOG"; return 1
}

s_reboot_if_needed() {
  [ "$MODE" = "dry" ] && { rec reboot SKIP "dry-run"; return 0; }
  if [ -e /dev/i2c-1 ] && [ -n "$(id -nG "$APP_USER" | grep -ow gpio)" ]; then rec reboot SKIP "I2C already live, no reboot needed"; return 0; fi
  say "I2C/camera were just enabled: rebooting once. Setup resumes automatically after boot."
  cat > "$RESUME_UNIT" <<EOF
[Unit]
Description=HydroGrow setup resume (one-shot after the bootstrap reboot)
After=network-online.target multi-user.target
Wants=network-online.target
[Service]
Type=oneshot
Environment=APP_USER=$APP_USER
ExecStart=/bin/bash $APP_DIR/setup.sh --resume
StandardOutput=journal+console
StandardError=journal+console
TimeoutStartSec=0
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload && systemctl enable hydrogrow-setup-resume.service >/dev/null 2>&1
  rec reboot PASS "rebooting; resume unit armed"
  print_report "(rebooting now; after ~90 s: ssh back in and run  sudo bash $APP_DIR/setup.sh  to watch/confirm)"
  sleep 3; systemctl reboot; exit 0
}

s_hwtest() {
  if [ "$MODE" = "dry" ]; then rec hwtest SKIP "dry-run (no hardware)"; return 0; fi
  local out="$STATE/hwtest.json"
  as_user env HYDROGROW_DATA_DIR="$HOME_DIR" "$HOME_DIR/iot-env/bin/python" "$APP_DIR/deploy/hwtest.py" --json "$out" 2>&1 | tee -a "$LOG"
  local fails; fails="$(python3 -c "import json;print(json.load(open('$out'))['summary']['FAIL'])" 2>/dev/null || echo "?")"
  if [ "$fails" = "0" ]; then rec hwtest PASS "all sensor/camera/model checks pass"; return 0; fi
  rec hwtest WARN "$fails check(s) failed: wiring/sensor issue, software continues ($out)"; return 0   # software-side goal: don't block
}

s_install() {
  if [ "$MODE" = "dry" ]; then
    local nodebin; nodebin="$(command -v node || true)"; [ -n "$nodebin" ] || { rec install FAIL "node not found on this machine"; return 1; }
    (cd "$APP_DIR/backend" && npm ci --omit=dev --no-audit --no-fund >/dev/null 2>&1 && node -e 'require("better-sqlite3")(":memory:")' ) || { rec install FAIL "backend npm ci / better-sqlite3"; return 1; }
    (cd "$APP_DIR/backend" && npm ci --no-audit --no-fund >/dev/null 2>&1 && npm test 2>&1 | grep -E "^# (pass|fail)" | tee -a "$LOG" | grep -q "^# fail 0") || { rec install FAIL "backend contract tests"; return 1; }
    local u r; for u in hydrogrow-ingest hydrogrow-backend hydrogrow-firmware hydrogrow-tunnel; do
      r="$(sed -e "s#@APP_DIR@#$APP_DIR#g" -e "s#@FIRMWARE_DIR@#$REPO_DIR/firmware#g" -e "s#@APP_USER@#$APP_USER#g" -e "s#@VENV@#$HOME_DIR/iot-env#g" -e "s#@NODE@#$nodebin#g" "$APP_DIR/deploy/systemd/$u.service")"
      echo "$r" | grep -q '@' && { rec install FAIL "unrendered placeholder in $u.service"; return 1; }
    done
    rec install PASS "dry-run: backend deps + better-sqlite3 load + contract tests pass, 4 units render"; return 0
  fi
  if bash "$APP_DIR/deploy/install.sh" 2>&1 | tee -a "$LOG"; then rec install PASS "mosquitto, node, backend, units enabled"; return 0; fi
  rec install FAIL "see $LOG"; return 1
}

s_tunnel() {
  if [ ! -f "$TUN_FILE" ]; then rec tunnel SKIP "no token (optional; docs/EXPO_RUNBOOK.md, Public link)"; return 0; fi
  if [ "$MODE" = "dry" ]; then rec tunnel PASS "dry-run: token file present, unit renders"; return 0; fi
  if bash "$APP_DIR/deploy/install-tunnel.sh" 2>&1 | tee -a "$LOG"; then rec tunnel PASS "hydrogrow-tunnel.service enabled (waits for internet, never blocks)"; return 0; fi
  rec tunnel WARN "tunnel install failed (local stack unaffected); see $LOG"; return 0
}

s_health() {
  if [ "$MODE" = "dry" ]; then rec health SKIP "dry-run (no services)"; return 0; fi
  local port; port="$(grep -E '^PORT=' "$ENV_FILE" | cut -d= -f2)"; port="${port:-8080}"
  local deadline=$((SECONDS+150)) code=000
  while [ $SECONDS -lt $deadline ]; do code="$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health" || true)"; [ "$code" = 200 ] && break; sleep 5; done
  HOST=127.0.0.1 PORT="$port" bash "$APP_DIR/tools/healthcheck.sh" 2>&1 | tee -a "$LOG"
  if [ "$code" = 200 ]; then rec health PASS "GET /health 200, all checks green"; return 0; fi
  rec health FAIL "/health is $code after 150 s (journalctl -u hydrogrow-firmware -n 50)"; return 1
}

print_report() {
  local note="${1:-}" ip; ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  {
    printf '\n%s================ HydroGrow setup report  %s ================%s\n' "$c_b" "$(date '+%Y-%m-%d %H:%M')" "$c_0"
    printf '%-13s %-5s %s\n' STEP RESULT DETAIL
    local overall=PASS line n s d col
    for line in "${REPORT[@]}"; do
      IFS='|' read -r n s d <<<"$line"
      case "$s" in PASS) col=$c_g;; FAIL) col=$c_r; overall=FAIL;; WARN) col=$c_y;; *) col="";; esac
      printf '%-13s %s%-5s%s %s\n' "$n" "$col" "$s" "$c_0" "$d"
    done
    printf '%s\nOVERALL: %s%s%s\n' "$note" "$([ $overall = PASS ] && echo "$c_g" || echo "$c_r")" "$overall" "$c_0"
    if [ "$MODE" != "dry" ]; then
      printf 'Dashboard : http://%s.local:8080/   or   http://%s:8080/\n' "$(hostname)" "${ip:-<ip>}"
      printf 'Unity base: http://%s:8080   (twins at /twins/plant2)\n' "${ip:-<ip>}"
      [ -f "$TUN_FILE" ] && printf 'Public    : https://%s  (when the tunnel is up: systemctl status hydrogrow-tunnel)\n' "$(sed -n 's/^TUNNEL_HOSTNAME=//p' "$TUN_FILE")"
      printf 'Rerun any time: sudo bash %s/setup.sh    (add --force to redo all steps)\n' "$APP_DIR"
    fi
  } | tee "$STATE/REPORT.txt" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' >/dev/null
  cat "$STATE/REPORT.txt" 2>/dev/null
  sed -i 's/\x1b\[[0-9;]*m//g' "$STATE/REPORT.txt" 2>/dev/null
}

# ================================================================== main
mkdir -p "$STATE" "$HOME_DIR" 2>/dev/null; : >> "$LOG" 2>/dev/null
say "mode=$MODE user=$APP_USER app=$APP_DIR $( [ $FORCE -eq 1 ] && echo '(force)' ) $( [ $RESUME -eq 1 ] && echo '(resume after reboot)' )"

if [ "$MODE" != "dry" ] && [ "$RESUME" -eq 0 ] && systemctl is-active --quiet hydrogrow-setup-resume.service 2>/dev/null; then
  say "post-reboot resume is running; following its log (Ctrl-C only detaches)"; journalctl -fu hydrogrow-setup-resume.service; exit 0
fi
if [ "$RESUME" -eq 1 ]; then systemctl disable hydrogrow-setup-resume.service >/dev/null 2>&1; rm -f "$RESUME_UNIT"; systemctl daemon-reload; fi

FAILED=0
step_run env          s_env          || FAILED=1
[ $FAILED -eq 0 ] && { step_run bootstrap    s_bootstrap    || FAILED=1; }
[ $FAILED -eq 0 ] && { step_run reboot       s_reboot_if_needed || FAILED=1; }
[ $FAILED -eq 0 ] && { step_run hwtest       s_hwtest       || FAILED=1; }
[ $FAILED -eq 0 ] && { step_run install      s_install      || FAILED=1; }
[ $FAILED -eq 0 ] && { step_run tunnel       s_tunnel       || FAILED=1; }
[ $FAILED -eq 0 ] && { s_health || FAILED=1; }     # health is never stamped: always re-checked
print_report
exit $FAILED
