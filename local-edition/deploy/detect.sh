#!/usr/bin/env bash
# detect.sh: REPORT ONLY. Prints what install.sh would have to work with on this Pi.
# Changes nothing. Run as the normal user:   bash deploy/detect.sh
set -u
APP_USER="${APP_USER:-$(id -un)}"
HOME_DIR="$(getent passwd "$APP_USER" | cut -d: -f6)"
VENV="${VENV:-$HOME_DIR/iot-env}"
hr() { printf '\n== %s\n' "$1"; }

hr "OS"
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME (VERSION_CODENAME=${VERSION_CODENAME:-?})"
echo "kernel: $(uname -r)  machine: $(uname -m)  userland: $(dpkg --print-architecture 2>/dev/null || echo '?')"
echo "model: $(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null || echo '?')"
echo "hostname: $(hostname)   user: $APP_USER   home: $HOME_DIR"
echo "groups of $APP_USER: $(id -nG "$APP_USER" 2>/dev/null)"

hr "Clock"
date -u +"now UTC: %Y-%m-%dT%H:%M:%SZ"
timedatectl 2>/dev/null | grep -E "synchronized|NTP service" || echo "timedatectl unavailable"

hr "Resources"
free -m | sed -n '1,3p'
df -h / "$HOME_DIR" 2>/dev/null | awk 'NR==1 || !seen[$1]++'
echo "cpu temp: $(vcgencmd measure_temp 2>/dev/null || echo '?')  throttled: $(vcgencmd get_throttled 2>/dev/null || echo '?')"

hr "Python"
echo "system python3: $(python3 --version 2>&1)  at $(command -v python3)"
if [ -x "$VENV/bin/python" ]; then
  echo "venv $VENV: $("$VENV/bin/python" --version 2>&1)"
  echo "venv base: $(grep -E '^(home|version)' "$VENV/pyvenv.cfg" 2>/dev/null | tr '\n' ' ')"
  echo "system-site-packages: $(grep -i include-system-site-packages "$VENV/pyvenv.cfg" 2>/dev/null)"
  echo "key packages:"
  "$VENV/bin/python" - <<'EOF'
import importlib, sys
for m in ["tensorflow", "keras", "numpy", "sklearn", "joblib", "picamera2", "paho.mqtt", "RPi.GPIO", "board",
          "adafruit_dht", "adafruit_ads1x15", "luma.oled", "PIL", "yaml", "sqlite3", "azure.iot.device"]:
    try:
        mod = importlib.import_module(m)
        v = getattr(mod, "__version__", "") or getattr(mod, "version", "")
        print(f"  OK   {m:22s} {v}  ({getattr(mod, '__file__', '')})")
    except Exception as e:
        print(f"  --   {m:22s} missing ({e.__class__.__name__})")
EOF
  echo "symlinks in site-packages:"
  find "$VENV/lib" -maxdepth 3 -type l -printf '  %p -> %l\n' 2>/dev/null | head -20
else
  echo "venv $VENV NOT FOUND (install.sh will refuse to create one; run: sudo bash deploy/bootstrap.sh)"
fi

hr "Firmware data (HYDROGROW_DATA_DIR default = $HOME_DIR)"
for f in models/lettuce_mobilenetv2.h5 models/nutrient_model.pkl nutrient_b_state.json dosing_state.json captures buffer mqtt_queue hydrogrow/hydrogrow.db; do
  p="$HOME_DIR/$f"; [ -e "$p" ] && echo "  present  $p ($(du -sh "$p" 2>/dev/null | cut -f1))" || echo "  absent   $p"
done

hr "Existing services and timers (nothing here is changed by install.sh)"
systemctl list-unit-files --type=service --state=enabled --no-legend 2>/dev/null | grep -vE '^(getty|systemd-|dbus|ssh|cron|rsyslog|avahi|bluetooth|hciuart|triggerhappy|dphys|rpi-|raspberrypi-|console-|e2scrub|fake-hwclock|keyboard|ModemManager|NetworkManager|wpa_|networking|udisks|polkit|rng-|apparmor|dhcpcd|serial-|pigpiod|nfs|rpcbind|ifup|alsa|sshswitch|userconfig|cups|colord|lightdm|x11|pulseaudio|wayvnc|labwc)' | sed 's/^/  /'
echo "  units mentioning main.py / hydrogrow:"
grep -lsE 'main\.py|hydrogrow' /etc/systemd/system/*.service /lib/systemd/system/*.service /home/*/.config/systemd/user/*.service 2>/dev/null | sed 's/^/    /' || true
echo "  hydrogrow-* / mosquitto state:"
for u in mosquitto hydrogrow-ingest hydrogrow-backend hydrogrow-firmware avahi-daemon cloudflared systemd-timesyncd systemd-time-wait-sync; do
  printf '    %-20s enabled=%-9s active=%s\n' "$u" "$(systemctl is-enabled "$u" 2>/dev/null || echo n/a)" "$(systemctl is-active "$u" 2>/dev/null || echo n/a)"
done
echo "  processes running main.py:"
pgrep -af 'main\.py' | sed 's/^/    /' || echo "    none"

hr "Cron"
echo "  crontab ($APP_USER):"; crontab -l -u "$APP_USER" 2>/dev/null | grep -v '^#' | sed 's/^/    /' || echo "    (none)"
echo "  crontab (root):"; sudo -n crontab -l 2>/dev/null | grep -v '^#' | sed 's/^/    /' || echo "    (none or no sudo)"
echo "  /etc/cron.d:"; ls /etc/cron.d 2>/dev/null | sed 's/^/    /'

hr "Node / Mosquitto / avahi"
echo "node: $(command -v node 2>/dev/null && node --version 2>/dev/null || echo 'not installed')"
echo "npm:  $(command -v npm 2>/dev/null && npm --version 2>/dev/null || echo 'not installed')"
echo "mosquitto: $(dpkg -s mosquitto 2>/dev/null | grep '^Version' || echo 'not installed')"
echo "avahi-daemon: $(dpkg -s avahi-daemon 2>/dev/null | grep '^Version' || echo 'not installed')"
echo "/etc/mosquitto/conf.d: $(ls /etc/mosquitto/conf.d 2>/dev/null | tr '\n' ' ')"
echo "/etc/hydrogrow/hydrogrow.env: $([ -f /etc/hydrogrow/hydrogrow.env ] && echo present || echo absent)"

hr "Network"
ip -4 -o addr show scope global 2>/dev/null | awk '{print "  " $2 ": " $4}'
echo "  default route: $(ip route show default 2>/dev/null | head -1)"
echo "  listening on 1883/8080/9001: $(ss -ltn 2>/dev/null | awk '$4 ~ /:(1883|8080|9001)$/ {print $4}' | tr '\n' ' ')"
echo "  internet: $(curl -fsI -m 5 https://deb.debian.org >/dev/null 2>&1 && echo yes || echo no)"

printf '\nDone. Nothing was changed.\n'
