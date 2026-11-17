#!/usr/bin/env bash
# install.sh: idempotent Local Edition installer for the Raspberry Pi. Re-run as often as you like.
#
#   sudo bash deploy/install.sh            # full install / update
#   sudo bash deploy/install.sh --check    # only print the final health summary
#
# What it does (each step skips itself when already done):
#   1. apt: mosquitto, mosquitto-clients, avahi-daemon, curl, xz-utils (+ build tools only if needed)
#   2. Mosquitto: drops broker/mosquitto.conf into /etc/mosquitto/conf.d/hydrogrow.conf, start-checks
#      the full config (rolls back to the previous hydrogrow.conf if the broker rejects it), then restarts
#   3. Node 22 LTS from the official nodejs.org tarball for this CPU (skipped if node >= 22 exists)
#   4. backend: npm ci --omit=dev, verifies better-sqlite3 loads (rebuilds from source if not);
#      builds the dashboard into backend/build when it is missing (FORCE_DASHBOARD_BUILD=1 to redo)
#   5. ~/iot-env: REUSED as-is; only installs paho-mqtt into it when missing
#   6. /etc/hydrogrow/hydrogrow.env from .env.example via deploy/render-env.sh (never overwritten)
#   7. systemd units hydrogrow-ingest / -backend / -firmware (Restart=always), enabled + (re)started
#   8. waits for /health and prints the summary
# What it never does: touch other services, cron jobs, the venv's existing packages,
# the hostname, or the network configuration (those are printed as suggestions only).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$APP_DIR/.." && pwd)"
FIRMWARE_DIR="$REPO_DIR/firmware"
APP_USER="${APP_USER:-$(stat -c %U "$APP_DIR")}"
HOME_DIR="$(getent passwd "$APP_USER" | cut -d: -f6)"
VENV="${VENV:-$HOME_DIR/iot-env}"
ENV_FILE=/etc/hydrogrow/hydrogrow.env
NODE_MAJOR_WANTED=22
NODE_PREFIX=/usr/local/lib/nodejs
LOG_PREFIX="[install]"
CHECK_ONLY=0; [ "${1:-}" = "--check" ] && CHECK_ONLY=1

say()  { printf '%s %s\n' "$LOG_PREFIX" "$*"; }
step() { printf '\n%s ---- %s\n' "$LOG_PREFIX" "$*"; }
die()  { printf '%s ERROR: %s\n' "$LOG_PREFIX" "$*" >&2; exit 1; }
as_user() { runuser -u "$APP_USER" -- "$@"; }

[ "$(id -u)" -eq 0 ] || die "run with sudo: sudo bash deploy/install.sh"
[ -d "$APP_DIR/backend" ] && [ -d "$APP_DIR/ingest" ] && [ -f "$FIRMWARE_DIR/main.py" ] && [ -d "$REPO_DIR/dashboard/src" ] || die "unexpected layout: run from local-edition/ in a full clone of the repo"

if [ "$CHECK_ONLY" -eq 0 ]; then
say "app dir   : $APP_DIR"
say "user      : $APP_USER (home $HOME_DIR)"
say "venv      : $VENV"
say "arch      : $(uname -m) kernel, $(dpkg --print-architecture) userland"

# ------------------------------------------------------------------ 0. preconditions
step "0/8 preconditions"
[ -x "$VENV/bin/python" ] || die "$VENV not found. On a fresh card run: sudo bash deploy/bootstrap.sh first (creates ~/iot-env from deploy/requirements-pi.lock). Set VENV=/path/to/venv if it lives elsewhere."
say "venv python: $("$VENV/bin/python" --version 2>&1)"
for f in models/lettuce_mobilenetv2.h5 models/nutrient_model.pkl; do
  [ -f "$HOME_DIR/$f" ] && say "model ok   : $HOME_DIR/$f" || say "WARNING    : $HOME_DIR/$f missing; the firmware will run but disease/nutrient inference will be skipped"
done

# ------------------------------------------------------------------ 1. apt
step "1/8 apt packages"
export DEBIAN_FRONTEND=noninteractive
need=()
for p in mosquitto mosquitto-clients avahi-daemon curl xz-utils ca-certificates; do
  dpkg -s "$p" >/dev/null 2>&1 || need+=("$p")
done
if [ "${#need[@]}" -gt 0 ]; then
  say "installing: ${need[*]}"
  apt-get update -qq
  apt-get install -y -qq "${need[@]}"
else
  say "all present"
fi

# ------------------------------------------------------------------ 2. mosquitto
step "2/8 mosquitto config"
MOSQ_MAIN=/etc/mosquitto/mosquitto.conf
MOSQ_CONF=/etc/mosquitto/conf.d/hydrogrow.conf
MOSQ_PREV=/etc/mosquitto/hydrogrow.conf.prev   # outside conf.d so the broker never includes it
install -d -m 755 /etc/mosquitto/conf.d
if ! cmp -s "$APP_DIR/broker/mosquitto.conf" "$MOSQ_CONF"; then
  rm -f "$MOSQ_PREV"; [ -f "$MOSQ_CONF" ] && cp -p "$MOSQ_CONF" "$MOSQ_PREV"
  install -m 644 "$APP_DIR/broker/mosquitto.conf" "$MOSQ_CONF"
  say "wrote $MOSQ_CONF"
  MOSQ_CHANGED=1
else
  say "config unchanged"; MOSQ_CHANGED=0
fi

# Start check. mosquitto has no config-test flag (-t does not exist), so run the broker exactly as the
# stock unit does (same binary, same -c $MOSQ_MAIN, so conf.d + stock settings are all parsed) for 3 s.
# Still running after 3 s (timeout exit 124) = config accepted; any earlier exit = rejected.
# The service is stopped first because the probe needs ports 1883/9001. Wants= in our units does not
# propagate a stop, and step 7 restarts them anyway.
mosq_probe() {
  local rc=0
  # same ExecStartPre as the stock unit (log file / pid dir must exist for the broker to start)
  mkdir -m 740 -p /var/log/mosquitto /run/mosquitto
  chown mosquitto:mosquitto /var/log/mosquitto /run/mosquitto
  timeout -k 5 3 /usr/sbin/mosquitto -c "$MOSQ_MAIN" >"$MOSQ_PROBE_OUT" 2>&1 || rc=$?
  [ "$rc" -eq 124 ]
}
# the stock Debian unit is used as-is; just make sure it is enabled
systemctl enable mosquitto >/dev/null 2>&1 || true
if [ "$MOSQ_CHANGED" -eq 1 ] || ! systemctl is-active --quiet mosquitto; then
  MOSQ_PROBE_OUT="$(mktemp)"
  systemctl stop mosquitto
  if mosq_probe; then
    say "start check: broker ran 3 s with $MOSQ_MAIN (+ conf.d) -> OK"
    rm -f "$MOSQ_PROBE_OUT"
  else
    say "start check FAILED: mosquitto -c $MOSQ_MAIN exited early:"
    sed 's/^/      /' "$MOSQ_PROBE_OUT" >&2; rm -f "$MOSQ_PROBE_OUT"
    if [ "$MOSQ_CHANGED" -eq 1 ]; then
      if [ -f "$MOSQ_PREV" ]; then cp -p "$MOSQ_PREV" "$MOSQ_CONF"; say "restored the previous $MOSQ_CONF"
      else rm -f "$MOSQ_CONF"; say "removed the new $MOSQ_CONF (there was no previous one)"; fi
      systemctl start mosquitto || true
      say "mosquitto (previous config): $(systemctl is-active mosquitto)"
    fi
    die "mosquitto will not start with this config; fix broker/mosquitto.conf (or the error above) and re-run"
  fi
  systemctl restart mosquitto
fi
systemctl is-active --quiet mosquitto || { journalctl -u mosquitto -n 20 --no-pager >&2 || true; die "mosquitto is not active after start (see above and /var/log/mosquitto/mosquitto.log)"; }
say "mosquitto: $(systemctl is-active mosquitto)"

# ------------------------------------------------------------------ 3. node
step "3/8 Node.js $NODE_MAJOR_WANTED"
node_ok() { command -v "$1" >/dev/null 2>&1 && [ "$("$1" -p 'process.versions.node.split(".")[0]' 2>/dev/null)" -ge "$NODE_MAJOR_WANTED" ]; }
if node_ok node; then
  NODE_BIN="$(command -v node)"; say "found $("$NODE_BIN" --version) at $NODE_BIN (kept)"
else
  case "$(dpkg --print-architecture)" in
    arm64) NARCH=arm64 ;;
    armhf) NARCH=armv7l ;;
    amd64) NARCH=x64 ;;
    *) die "unsupported userland arch $(dpkg --print-architecture)" ;;
  esac
  say "downloading latest v${NODE_MAJOR_WANTED}.x for linux-$NARCH from nodejs.org"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "https://nodejs.org/dist/latest-v${NODE_MAJOR_WANTED}.x/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"
  TARBALL="$(awk -v a="linux-$NARCH.tar.xz" '$2 ~ a"$" {print $2}' "$tmp/SHASUMS256.txt" | head -1)"
  [ -n "$TARBALL" ] || die "no linux-$NARCH tarball in latest-v${NODE_MAJOR_WANTED}.x"
  curl -fsSL "https://nodejs.org/dist/latest-v${NODE_MAJOR_WANTED}.x/$TARBALL" -o "$tmp/$TARBALL"
  (cd "$tmp" && grep " $TARBALL\$" SHASUMS256.txt | sha256sum -c -) || die "sha256 mismatch for $TARBALL"
  install -d "$NODE_PREFIX"
  tar -xJf "$tmp/$TARBALL" -C "$NODE_PREFIX"
  NODE_DIR="$NODE_PREFIX/${TARBALL%.tar.xz}"
  for b in node npm npx; do ln -sfn "$NODE_DIR/bin/$b" "/usr/local/bin/$b"; done
  NODE_BIN=/usr/local/bin/node
  say "installed $("$NODE_BIN" --version) -> $NODE_DIR"
fi
NPM_BIN="$(dirname "$NODE_BIN")/npm"; [ -x "$NPM_BIN" ] || NPM_BIN="$(command -v npm)"

# ------------------------------------------------------------------ 4. backend deps
step "4/8 backend dependencies (better-sqlite3 native module)"
cd "$APP_DIR/backend"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules/.package-lock.json ]; then
  say "npm ci --omit=dev (as $APP_USER)"
  as_user env PATH="$(dirname "$NODE_BIN"):$PATH" HOME="$HOME_DIR" "$NPM_BIN" ci --omit=dev --no-audit --no-fund
else
  say "node_modules up to date"
fi
if as_user "$NODE_BIN" -e 'require("better-sqlite3")(":memory:").prepare("select sqlite_version() v").get()' >/dev/null 2>&1; then
  say "better-sqlite3 loads on $(dpkg --print-architecture) (prebuilt binary)"
else
  say "no prebuilt better-sqlite3 for this arch; building from source (needs build-essential, python3)"
  apt-get install -y -qq build-essential python3 python3-setuptools
  as_user env PATH="$(dirname "$NODE_BIN"):$PATH" HOME="$HOME_DIR" "$NPM_BIN" rebuild better-sqlite3 --build-from-source
  as_user "$NODE_BIN" -e 'require("better-sqlite3")(":memory:")' || die "better-sqlite3 still does not load"
  say "better-sqlite3 built from source OK"
fi
if [ ! -f "$APP_DIR/backend/build/index.html" ] || [ "${FORCE_DASHBOARD_BUILD:-0}" = "1" ]; then
  say "building the dashboard into backend/build (npm ci + react-scripts build; a few minutes on a Pi 4)"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR/dashboard"
  (cd "$APP_DIR/dashboard" && as_user env PATH="$(dirname "$NODE_BIN"):$PATH" HOME="$HOME_DIR" "$NPM_BIN" ci --no-audit --no-fund      && as_user env PATH="$(dirname "$NODE_BIN"):$PATH" HOME="$HOME_DIR" "$NPM_BIN" run build) || die "dashboard build failed"
else
  say "dashboard build present (FORCE_DASHBOARD_BUILD=1 to rebuild)"
fi
cd "$APP_DIR"

# ------------------------------------------------------------------ 5. venv: paho only
step "5/8 ~/iot-env: add paho-mqtt only"
if as_user "$VENV/bin/python" -c 'import paho.mqtt.client as m; v=m.__version__ if hasattr(m,"__version__") else __import__("paho.mqtt").mqtt.__version__; assert v.split(".")[0]=="2", v' 2>/dev/null; then
  say "paho-mqtt 2.x already present; venv untouched"
else
  say "pip install paho-mqtt (no --upgrade of anything else, no deps beyond paho)"
  as_user "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check "paho-mqtt>=2.1.0,<3"
fi
as_user "$VENV/bin/python" -c 'import paho.mqtt.client, sqlite3, json' || die "venv cannot import paho/sqlite3"

# ------------------------------------------------------------------ 6. env + dirs
step "6/8 $ENV_FILE and data dirs"
install -d -m 755 /etc/hydrogrow
if [ ! -f "$ENV_FILE" ]; then
  bash "$APP_DIR/deploy/render-env.sh" "$HOME_DIR" > "$ENV_FILE"
  chmod 640 "$ENV_FILE"; chown "root:$APP_USER" "$ENV_FILE"
  say "created $ENV_FILE from .env.example  <-- set PLANTING_DATE and DEMO_USER_PASSWORD (setup.sh asks for both)"
else
  say "$ENV_FILE exists; left untouched"
fi
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
DB_DIR="$(dirname "${HYDROGROW_DB:-$HOME_DIR/hydrogrow/hydrogrow.db}")"
as_user install -d "$DB_DIR" "${HYDROGROW_DATA_DIR:-$HOME_DIR}/mqtt_queue" "${HYDROGROW_DATA_DIR:-$HOME_DIR}/captures"
say "db dir $DB_DIR, data dir ${HYDROGROW_DATA_DIR:-$HOME_DIR}"

# ------------------------------------------------------------------ 7. systemd units
step "7/8 systemd units"
CHANGED_UNITS=0
for u in hydrogrow-ingest hydrogrow-backend hydrogrow-firmware; do
  rendered="$(sed -e "s#@APP_DIR@#$APP_DIR#g" -e "s#@FIRMWARE_DIR@#$FIRMWARE_DIR#g" -e "s#@APP_USER@#$APP_USER#g" -e "s#@VENV@#$VENV#g" -e "s#@NODE@#$NODE_BIN#g" "$APP_DIR/deploy/systemd/$u.service")"
  if [ ! -f "/etc/systemd/system/$u.service" ] || [ "$rendered" != "$(cat "/etc/systemd/system/$u.service")" ]; then
    printf '%s\n' "$rendered" > "/etc/systemd/system/$u.service"; CHANGED_UNITS=1; say "wrote $u.service"
  fi
done
[ "$CHANGED_UNITS" -eq 1 ] && systemctl daemon-reload
for u in hydrogrow-ingest hydrogrow-backend hydrogrow-firmware; do
  systemctl enable "$u" >/dev/null 2>&1
  systemctl restart "$u"
  say "$u: $(systemctl is-active "$u")"
done

# ------------------------------------------------------------------ suggestions (not applied)
step "suggestions (NOT applied automatically)"
say "this Pi answers as $(hostname).local (avahi). Windows laptops often cannot resolve .local:"
say "give the Pi a DHCP reservation on the router; see docs/EXPO_RUNBOOK.md, \"Name resolution\" (not changed here)"
fi  # CHECK_ONLY

# ------------------------------------------------------------------ 8. health summary
step "8/8 health summary (waiting up to 120 s for the firmware's first reading)"
PORT_="$(grep -E '^PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2)"; PORT_="${PORT_:-8080}"
deadline=$((SECONDS + 120)); code=000
while [ "$SECONDS" -lt "$deadline" ]; do
  code="$(curl -s -m 3 -o /tmp/hg_health.json -w '%{http_code}' "http://127.0.0.1:$PORT_/health" || true)"
  [ "$code" = "200" ] && break
  sleep 5
done
printf '\n'
HOST=127.0.0.1 PORT="$PORT_" bash "$APP_DIR/tools/healthcheck.sh" || true
printf '\n'
if [ "$code" = "200" ]; then
  say "ALL GREEN. Dashboard: http://$(hostname).local:$PORT_/  (or http://$(hostname -I | awk '{print $1}'):$PORT_/)"
else
  say "not fully green yet (HTTP $code). Usual causes: firmware still loading TensorFlow (wait 1-2 min),"
  say "or no reading stored yet. Inspect: journalctl -u hydrogrow-firmware -n 50 --no-pager ; journalctl -u hydrogrow-ingest -n 20 --no-pager"
fi
say "logs: journalctl -fu hydrogrow-firmware   |   re-run this script any time; it is idempotent"
