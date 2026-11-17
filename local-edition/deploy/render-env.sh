#!/usr/bin/env bash
# render-env.sh HOME_DIR: print local-edition/.env.example with Raspberry Pi values.
# Used by setup.sh and install.sh to create /etc/hydrogrow/hydrogrow.env once (never overwritten).
#   bash deploy/render-env.sh /home/<user> | sudo tee /etc/hydrogrow/hydrogrow.env
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
H="${1:?usage: render-env.sh HOME_DIR}"
echo "# /etc/hydrogrow/hydrogrow.env, rendered by local-edition/deploy/render-env.sh. Edit here, then"
echo "# sudo systemctl restart hydrogrow-firmware hydrogrow-ingest hydrogrow-backend"
sed -E \
  -e "s#^\#?HYDROGROW_DB=.*#HYDROGROW_DB=$H/hydrogrow/hydrogrow.db#" \
  -e "s#^\#?HYDROGROW_DATA_DIR=.*#HYDROGROW_DATA_DIR=$H#" \
  -e "s#^SENSOR_INTERVAL_S=.*#SENSOR_INTERVAL_S=30#" \
  -e "s#^CAMERA_INTERVAL_S=.*#CAMERA_INTERVAL_S=300#" \
  -e "s#^PUMPS_DRY_RUN=.*#PUMPS_DRY_RUN=1#" \
  "$APP_DIR/.env.example"
