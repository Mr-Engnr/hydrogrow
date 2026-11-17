# Exhibition runbook (Local Edition on a Raspberry Pi)

For running HydroGrow at a show: bench setup, go/no-go, show-day operation, Demo Mode
fallback and recovery. First-time install is in [START_HERE.md](START_HERE.md), section B.
Paths below are relative to the repo clone on the Pi (`~/hydrogrow` if you cloned into home).

Target hardware: Raspberry Pi 4B (4 GB), Raspberry Pi OS 64-bit trixie, the HydroGrow rig
wired as in `firmware/README.md`.

## 1. What runs

| Unit | Runs | Starts after |
|---|---|---|
| `mosquitto` (stock unit + `/etc/mosquitto/conf.d/hydrogrow.conf`) | broker on 1883, WebSocket 9001 | boot |
| `hydrogrow-ingest` | `~/iot-env/bin/python local-edition/ingest/ingest.py` | mosquitto |
| `hydrogrow-backend` | `node local-edition/backend/src/server.js` on :8080 | ingest |
| `hydrogrow-firmware` | `~/iot-env/bin/python -u firmware/main.py` | mosquitto, time-sync (ordering only) |
| `hydrogrow-tunnel` (optional) | `cloudflared` public URL | network-online; skipped without a token |

All read `/etc/hydrogrow/hydrogrow.env` and restart on failure. Logs go to journald:
`journalctl -fu hydrogrow-firmware`.

## 2. Bench checklist (the day before)

| # | Step | Expect |
|---|---|---|
| 1 | `sudo bash local-edition/setup.sh` finished with OVERALL PASS | report saved in `local-edition/.setup/REPORT.txt` |
| 2 | `~/iot-env/bin/python local-edition/deploy/hwtest.py --pumps` while watching the relays | every sensor PASS, three relay clicks |
| 3 | `bash local-edition/tools/healthcheck.sh` | `0 failed`, mode `live` |
| 4 | Dashboard from a laptop on the same Wi-Fi | badge **Live**, readings change every 30 s |
| 5 | `sudo reboot`, then poll `/health` from the laptop | HTTP 200 within 2 minutes, no keyboard needed |
| 6 | Pull the power, wait 10 s, plug back in, poll again | 200 within 2 minutes; `journalctl -b -u hydrogrow-firmware` shows no dosing on boot (cooldown persisted) |
| 7 | DHCP reservation for the Pi on the show router (section 5) | fixed IP written down |
| 8 | Image the SD card (section 9) | spare card ready |

PowerShell poll from a Windows laptop:

```powershell
1..24 | % { try { (iwr -UseBasicParsing http://<pi-ip>:8080/health).StatusCode; break } catch { "waiting"; sleep 5 } }
```

## 3. Go/no-go before leaving the bench

- `healthcheck.sh` shows `0 failed` and the browser badge says **Live**.
- `/etc/hydrogrow/hydrogrow.env`: `PLANTING_DATE` set, demo password set, `PUMPS_DRY_RUN` as
  intended (keep `1` until the tank is filled and the pumps are verified).
- The Pi's fixed IP is written down and given to whoever runs the Unity twin.
- Spare SD card imaged and labelled with the date.
- A laptop with this repo, Node 22 and Python ready for Demo Mode (section 4).

## 4. Demo Mode fallback

If the rig or a sensor fails at the show, keep the demo honest and running:

- **Pi still up, sensor fault:** leave it. The dashboard shows the failed sensor as `--`
  with a "not responding" warning; the other readings stay live.
- **Rig unusable:** stop the firmware and feed recorded or simulated data into the same stack.

  ```bash
  sudo systemctl stop hydrogrow-firmware
  ~/iot-env/bin/python local-edition/tools/replay.py <recordings>     # badge: Demo Mode
  # or
  ~/iot-env/bin/python local-edition/tools/fake_pi.py                 # badge: Simulated
  ```

  `replay.py` accepts a folder of `YYYYMMDD_HHMMSS_us.json` payloads, a `.jsonl` file, or a
  `.json` list. Each frame is re-tagged `source: "replay"`.
- **Pi dead:** run the laptop stack from [START_HERE.md](START_HERE.md) section A.

The badge is driven only by the stored `source` of the latest reading. Simulated or replayed
data can never show as **Live**. Tell visitors which mode they are looking at.

Back to live: stop the simulator, `sudo systemctl start hydrogrow-firmware`. The badge
returns to **Live** with the first real reading.

## 5. Name resolution

`avahi-daemon` makes the Pi answer as `<hostname>.local`. Windows laptops and some phones do
not resolve `.local`, so give the Pi a fixed address. Pick one:

- **Router (preferred):** a DHCP reservation for the Pi's MAC address (`ip link` shows it).
- **Pi with NetworkManager:**
  ```bash
  nmcli con show                       # find the connection name
  sudo nmcli con mod "<name>" ipv4.addresses <ip>/24 ipv4.gateway <router-ip> ipv4.dns <router-ip> ipv4.method manual
  sudo nmcli con up "<name>"
  ```

Unity and other clients should try `http://<hostname>.local:8080`, then `http://<ip>:8080`,
using `GET /health` with a 3 s timeout to pick one. Twin documents are at `/twins/<id>`.

## 6. Public link (optional, Cloudflare Tunnel)

Lets people outside the LAN open the dashboard. It needs a domain on Cloudflare and internet
at the venue. Nothing depends on it: without internet the unit waits quietly and the local
stack is unaffected.

1. Cloudflare Zero Trust, Networks, Tunnels: create a tunnel, choose "Debian, arm64", copy the
   token. Add a public hostname (for example `hydrogrow.<your-domain>`) of type HTTP pointing
   to `localhost:8080`.
2. On the Pi, either answer the token prompt in `setup.sh`, or:
   ```bash
   sudo install -d -m 755 /etc/hydrogrow
   printf 'TUNNEL_TOKEN=%s\nTUNNEL_HOSTNAME=%s\n' '<token>' '<public-hostname>' | sudo tee /etc/hydrogrow/cloudflared.env >/dev/null
   sudo chmod 600 /etc/hydrogrow/cloudflared.env
   sudo bash local-edition/deploy/install-tunnel.sh
   ```
3. `systemctl status hydrogrow-tunnel` shows `activating` while it waits for internet and
   `active (running)` once connected.

The token is the only secret. It lives in `/etc/hydrogrow/cloudflared.env`; never commit it,
and rotate it in the Zero Trust dashboard if it leaks. The read endpoints are public through
the tunnel just as on the LAN; add a Cloudflare Access policy if that is not acceptable.
Removal: `sudo systemctl disable --now hydrogrow-tunnel && sudo rm /etc/hydrogrow/cloudflared.env`.

## 7. Resource expectations (estimates, not yet measured on a Pi)

| Service | Memory | CPU |
|---|---|---|
| mosquitto | ~5 MB | idle |
| hydrogrow-ingest | ~25 MB | brief spikes per message |
| hydrogrow-backend | ~70 MB | a few % while a browser polls every 5 s |
| hydrogrow-firmware | 400 to 900 MB (TensorFlow + MobileNetV2) | one core for a few seconds per camera cycle |

`healthcheck.sh` prints the live numbers. The database grows about 4 MB per day at a 30 s
sensor interval.

## 8. Troubleshooting

| Symptom | Look at |
|---|---|
| setup: "64-bit required" or Python not 3.13 | wrong image; reflash with 64-bit trixie |
| setup: pip conflict | `local-edition/deploy/requirements-pi.resolved.txt` is the known-good set |
| hwtest: I2C 0x3C / 0x48 missing | wiring; `raspi-config nonint get_i2c` (0 = enabled); was the reboot done? |
| hwtest: camera error | ribbon seating; `rpicam-hello --list-cameras`; `camera_auto_detect=1` in `/boot/firmware/config.txt` |
| install: better-sqlite3 will not load | needs internet once: `sudo apt-get install build-essential python3`, rerun setup |
| install: dashboard build fails | free memory (close the desktop session), then `FORCE_DASHBOARD_BUILD=1 sudo -E bash local-edition/deploy/install.sh` |
| `/health` 503 `last_reading` | `journalctl -u hydrogrow-firmware -n 50`; TensorFlow takes 30 to 60 s after boot |
| `/health` 503 `broker` | `systemctl status mosquitto`; `/etc/mosquitto/conf.d/hydrogrow.conf` present |
| readings show `status: clock_unsynced` | no NTP yet; connect the Pi to internet once, or set the date by hand |
| `.local` does not resolve on Windows | use the fixed IP (section 5) |

## 9. Spare card and rollback

**Image the card:** `sudo shutdown -h now`, then read the card on another machine
(Win32DiskImager "Read", or `sudo dd if=/dev/sdX of=hydrogrow-pi-YYYYMMDD.img bs=4M status=progress`
on Linux) and compress with `xz -T0`. Restore with Raspberry Pi Imager, "Use custom".

**Rollback:** `sudo systemctl disable --now hydrogrow-firmware hydrogrow-ingest hydrogrow-backend`
stops the stack; Mosquitto, the venv, models and data stay. Files the installer created
outside the clone: `/etc/hydrogrow/`, `/etc/systemd/system/hydrogrow-*.service`,
`/etc/mosquitto/conf.d/hydrogrow.conf`, `/usr/local/lib/nodejs`.
