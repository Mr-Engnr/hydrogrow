# Start here: HydroGrow Local Edition

Two ways in. Try Demo Mode on a laptop first; it needs no hardware.

## A. Demo Mode on a laptop (about 10 minutes)

Needs Node.js 22 and Python 3.10 or newer. Windows, macOS and Linux all work. Run each
long-lived process in its own terminal, from the repo root. On Windows, use Git Bash or
PowerShell 7: Windows PowerShell 5.1 (the built-in `powershell.exe`) rejects `&&`, so there
run each `&&`-joined part as its own line, in order.

```bash
cd local-edition
cp .env.example .env          # then set DEMO_USER_PASSWORD in .env
python -m pip install -r ingest/requirements.txt    # paho-mqtt, for ingest and the simulators
```

| Terminal | Command | What it is |
|---|---|---|
| 1 | `cd local-edition/tools && npm ci && npm run broker` | MQTT broker stand-in (Aedes) on 1883 and ws 9001 |
| 2 | `python local-edition/ingest/ingest.py` | MQTT to SQLite (`local-edition/data/hydrogrow.db`) |
| 3 | `cd local-edition/dashboard && npm ci && npm run build`, then `cd ../backend && npm ci && npm start` | builds the dashboard once, then serves it and the API on :8080 |
| 4 | `python local-edition/tools/fake_pi.py` | simulated Pi, one frame every 5 s |

Open http://localhost:8080/, log in as `demo@hydrogrow.local` with the password you set.
The badge says **Simulated**.

Things to try:

- `python local-edition/tools/fake_pi.py --scenario low_ec` (also `high_ph`, `low_water`,
  `diseased`, `flaky_dht`) to see the alerts change.
- `python local-edition/tools/replay.py <folder-or-jsonl>` (stop `fake_pi.py` first) to
  re-publish recorded readings; the badge says **Demo Mode**. No recordings ship with the
  repo; use your own, for example the `raw_json` column of `telemetry` in a Pi's database.
- Stop `fake_pi.py` and watch "Last updated" turn amber.
- `curl http://localhost:8080/health` and `curl http://localhost:8080/twins/watertank1`.

If port 1883 is taken, set `MQTT_PORT=1884` and `MQTT_WS_PORT=9002` in every terminal (and
in `.env`).

## B. On a Raspberry Pi with the real rig (30 to 45 minutes, internet once)

1. **Flash** Raspberry Pi OS (64-bit), Debian 13 "trixie", with Raspberry Pi Imager. In
   "Edit settings" choose a hostname (for example `hydrogrow-pi`), your user, Wi-Fi and
   **SSH on**. The pinned TensorFlow wheels need 64-bit and Python 3.13.
2. **Boot** and `ssh <user>@<hostname>.local` (or use the IP from the router).
3. **Clone and run setup:**

   ```bash
   git clone https://github.com/Mr-Engnr/hydrogrow.git
   cd hydrogrow
   sudo bash local-edition/setup.sh
   ```

   It asks for the planting date (`YYYY-MM-DD`), a dashboard password, and optionally a
   Cloudflare tunnel token (Enter skips it). Then it runs unattended: apt packages, I2C and
   camera, a Python venv with the exact pinned versions, the models (SHA-256 checked),
   **one automatic reboot**, a hardware test, Mosquitto, Node 22, the dashboard build,
   systemd units and a health check. It ends with a PASS/FAIL table. After the reboot,
   ssh back in and run the same command to watch it finish. Rerun it after any failure; it
   resumes where it stopped.
4. **Open** `http://<hostname>.local:8080/` (or `http://<pi-ip>:8080/`) and log in. The badge
   must say **Live**.

Pumps start in dry run: every dosing decision is made and logged, no relay moves. When the
tank is ready:

```bash
sudo sed -i 's/^PUMPS_DRY_RUN=1/PUMPS_DRY_RUN=0/' /etc/hydrogrow/hydrogrow.env
sudo systemctl restart hydrogrow-firmware
```

Something wrong? `bash local-edition/tools/healthcheck.sh`, then
[EXPO_RUNBOOK.md](EXPO_RUNBOOK.md). How it fits together: [ARCHITECTURE.md](ARCHITECTURE.md).
Message and API shapes: [PAYLOAD_CONTRACT.md](PAYLOAD_CONTRACT.md).
