#!/usr/bin/env bash
# bootstrap.sh: rebuild the Pi's Python/hardware environment on a FRESH Raspberry Pi OS card.
# Idempotent; run with sudo from local-edition/ in a clone of the repo (setup.sh calls it):
#   sudo bash deploy/bootstrap.sh            # everything below
#   sudo bash deploy/bootstrap.sh --pumps    # also pulse the relays during the hardware test
#
# Reconstructs the environment found in the backup of the old card (Python 3.13.5, TensorFlow
# 2.21.0, aarch64):
#   1. sanity: 64-bit userland, Python 3.13 (Raspberry Pi OS Trixie)
#   2. apt: i2c-tools, python3-picamera2 (+libcamera, kms++, pidng, piexif, simplejpeg, prctl),
#           python3-venv, libcap-dev, libatlas/openblas, libgpiod, mosquitto deps, build tools
#   3. raspi-config nonint: enable I2C and the camera, keep SSH on
#   4. ~/iot-env: python3 -m venv --system-site-packages (picamera2 visible without symlink hacks)
#   5. pip install -r deploy/requirements-pi.lock (exact versions from the backup; paho -> 2.1.0)
#   6. models into ~/models, SHA-256 verified: the .h5 from the v1.0.0 GitHub release asset,
#      the .pkl from ml/nutrient-prediction/models/ in this repo (weights are never committed here)
#   7. hardware test: deploy/hwtest.py with a pass/fail table (relays only with --pumps)
# Then run deploy/install.sh for Mosquitto, Node, systemd units.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${APP_USER:-$(stat -c %U "$APP_DIR")}"
HOME_DIR="$(getent passwd "$APP_USER" | cut -d: -f6)"
VENV="${VENV:-$HOME_DIR/iot-env}"
REPO_DIR="$(cd "$APP_DIR/.." && pwd)"
LOCK="$APP_DIR/deploy/requirements-pi.lock"
H5_URL="https://github.com/Mr-Engnr/hydrogrow/releases/download/v1.0.0/lettuce_mobilenetv2.h5"
H5_SHA="c2947b489e242a3f77b7586e68f517a5df835a225991b140f5acdaafb28e1b6f"
PKL_SHA="3cc057b25a4b6c9c1237a16fbbc839dd64798c8b2781fab288fc6f712238cee1"
PUMPS=""; [ "${1:-}" = "--pumps" ] && PUMPS="--pumps"
say()  { printf '[bootstrap] %s\n' "$*"; }
step() { printf '\n[bootstrap] ---- %s\n' "$*"; }
die()  { printf '[bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }
as_user() { runuser -u "$APP_USER" -- "$@"; }
[ "$(id -u)" -eq 0 ] || die "run with sudo"

step "1/7 sanity"
. /etc/os-release
PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
say "OS: $PRETTY_NAME  userland: $(dpkg --print-architecture)  python3: $(python3 --version 2>&1)"
[ "$(dpkg --print-architecture)" = "arm64" ] || die "64-bit (arm64) Raspberry Pi OS required: the backup venv is aarch64 and TensorFlow has no 32-bit wheel"
if [ "$PYV" != "3.13" ]; then
  say "WARNING: python3 is $PYV, the backup used 3.13.5 (Raspberry Pi OS Trixie). The pinned wheels (TensorFlow 2.21, numpy 2.4.4) target cp313."
  say "         Re-image with 'Raspberry Pi OS (64-bit)' based on Debian 13 trixie, or set ALLOW_PY_MISMATCH=1 to continue anyway."
  [ "${ALLOW_PY_MISMATCH:-0}" = "1" ] || exit 1
fi
[ -f "$LOCK" ] || die "$LOCK missing"

step "2/7 apt packages"
export DEBIAN_FRONTEND=noninteractive
PKGS=(python3-venv python3-pip python3-dev i2c-tools python3-smbus libgpiod2
      python3-picamera2 python3-libcamera python3-kms++ python3-prctl libcamera-apps rpicam-apps
      libcap-dev libatlas-base-dev libopenblas0 libhdf5-dev libjpeg-dev zlib1g-dev libfreetype6-dev
      build-essential pkg-config git curl xz-utils ca-certificates avahi-daemon mosquitto mosquitto-clients)
need=()
for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || need+=("$p"); done
if [ "${#need[@]}" -gt 0 ]; then
  say "installing: ${need[*]}"
  apt-get update -qq
  # some names differ between Bookworm and Trixie (libcamera-apps vs rpicam-apps, libatlas); install what exists
  for p in "${need[@]}"; do apt-get install -y -qq "$p" 2>/dev/null || say "  (skipped unavailable package $p)"; done
else
  say "all present"
fi

step "3/7 raspi-config: I2C + camera + SSH (nonint, idempotent)"
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_i2c 0      && say "I2C enabled"
  raspi-config nonint do_ssh 0      && say "SSH enabled"
  raspi-config nonint do_camera 0 2>/dev/null && say "legacy camera flag set (ignored on libcamera systems)" || true
  # Trixie/Bookworm: camera is auto-detected via libcamera; make sure it is not disabled
  CFG=/boot/firmware/config.txt; [ -f "$CFG" ] || CFG=/boot/config.txt
  grep -q '^camera_auto_detect=1' "$CFG" || { sed -i '/^camera_auto_detect=/d' "$CFG"; echo 'camera_auto_detect=1' >> "$CFG"; say "camera_auto_detect=1 written to $CFG (reboot needed)"; }
  grep -q '^dtparam=i2c_arm=on' "$CFG" || say "note: dtparam=i2c_arm=on not found in $CFG; raspi-config should have added it"
else
  say "raspi-config not found; enable I2C and camera manually"
fi
for g in gpio i2c video spi dialout; do getent group "$g" >/dev/null && usermod -aG "$g" "$APP_USER"; done
say "$APP_USER groups: $(id -nG "$APP_USER")"

step "4/7 venv $VENV (--system-site-packages)"
if [ -x "$VENV/bin/python" ]; then
  if grep -q 'include-system-site-packages = true' "$VENV/pyvenv.cfg"; then
    say "exists with system-site-packages; reused"
  else
    say "exists but WITHOUT system-site-packages (old symlink-hack style)."
    say "Not touching it. To rebuild: mv ~/iot-env ~/iot-env.old && re-run bootstrap."
  fi
else
  as_user python3 -m venv --system-site-packages "$VENV"
  say "created"
fi
as_user "$VENV/bin/python" -c 'import picamera2, libcamera; print("[bootstrap] picamera2 visible from venv:", picamera2.__file__)' || die "picamera2 not importable from the venv; is python3-picamera2 installed?"

step "5/7 pip install -r requirements-pi.lock (exact versions from the backup)"
as_user "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "pip<26" >/dev/null 2>&1 || true
# dry check first so a missing wheel is reported clearly instead of a 20-minute compile surprise
if as_user "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --only-binary=:all: --dry-run -r "$LOCK" >/dev/null 2>&1; then
  say "all pins available as wheels for this Python/arch"
else
  say "some pins have no wheel for $(python3 --version 2>&1) aarch64; pip will build them from source (RPi.GPIO, rpi_ws281x, sysv_ipc are small; TensorFlow/numpy/scipy MUST be wheels)"
fi
as_user "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$LOCK"
as_user "$VENV/bin/python" - <<'EOF'
import importlib, sys
want = {"tensorflow": "2.21.0", "numpy": "2.4.4", "sklearn": "1.8.0", "keras": "3.14.0", "paho.mqtt": None}
bad = []
for m, v in want.items():
    mod = importlib.import_module(m)
    got = getattr(mod, "__version__", None)
    if m == "paho.mqtt":
        import paho.mqtt.client as c; got = "v2 API" if hasattr(c, "CallbackAPIVersion") else "v1 API"; ok = got == "v2 API"
    else:
        ok = got == v
    print(f"[bootstrap]   {m:12s} {got}  {'OK' if ok else 'MISMATCH, wanted ' + str(v)}")
    if not ok: bad.append(m)
sys.exit(1 if bad else 0)
EOF

step "6/7 models -> $HOME_DIR/models"
as_user install -d "$HOME_DIR/models" "$HOME_DIR/captures"
place_model() {  # name sha source(url|path)
  local dst="$HOME_DIR/models/$1"
  if [ -f "$dst" ] && echo "$2  $dst" | sha256sum -c --quiet - 2>/dev/null; then say "$1 already in place (sha ok)"; return; fi
  case "$3" in
    http*) say "downloading $1 (v1.0.0 release asset)"; as_user curl -fsSL "$3" -o "$dst.tmp" && as_user mv "$dst.tmp" "$dst" ;;
    *)     [ -f "$3" ] || die "$3 missing; is this a full clone of the repo?"; as_user cp "$3" "$dst"; say "copied $1 from the repo" ;;
  esac
  echo "$2  $dst" | sha256sum -c --quiet - || die "$1 SHA-256 mismatch"
  say "$1 sha256 verified"
}
place_model lettuce_mobilenetv2.h5 "$H5_SHA" "$H5_URL"
place_model nutrient_model.pkl "$PKL_SHA" "$REPO_DIR/ml/nutrient-prediction/models/nutrient_model.pkl"

step "7/7 hardware test"
if [ ! -e /dev/i2c-1 ]; then
  say "/dev/i2c-1 not present yet (I2C was just enabled). REBOOT, then run:"
  say "   $VENV/bin/python $APP_DIR/deploy/hwtest.py $PUMPS"
else
  as_user env HYDROGROW_DATA_DIR="$HOME_DIR" "$VENV/bin/python" "$APP_DIR/deploy/hwtest.py" $PUMPS --json "$HOME_DIR/hwtest_last.json" || say "hardware test reported failures (see table above; $HOME_DIR/hwtest_last.json)"
fi
printf '\n[bootstrap] done. Next: sudo bash deploy/install.sh   (Mosquitto config, Node 22, systemd units, health)\n'
