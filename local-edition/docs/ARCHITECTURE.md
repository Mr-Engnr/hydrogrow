# Local Edition architecture

The Local Edition runs the whole HydroGrow stack on one Raspberry Pi, or on a laptop with a
simulated Pi. No cloud account and no internet are needed after installation. It replaces the
Azure services of the cloud edition (IoT Hub, Functions, Blob Storage, Digital Twins, App
Service) with four local processes, and it serves the same API shapes, so the dashboard
and the Unity twin client need no logic changes.

```
 firmware/main.py ──MQTT QoS 1──▶ Mosquitto ──▶ ingest/ingest.py ──▶ SQLite ◀── backend (Express :8080) ──▶ browser dashboard
 (sensors, camera,   hydrogrow/    :1883 /      (port of the Azure    data/        /api/pidata, /api/analytics,      Unity twin client
  ML, dosing)        telemetry     ws :9001      Function)            hydrogrow.db  /twins/:id, /health, React build
        ▲
 tools/fake_pi.py   (simulated frames, source "fake")
 tools/replay.py    (recorded frames,  source "replay")
```

## Components

| Component | Path | Runs as (Pi) | Replaces (cloud edition) |
|---|---|---|---|
| Firmware | `firmware/main.py` + `firmware/mqtt_publisher.py` | `hydrogrow-firmware` | same loop; IoT Hub client swapped for MQTT via `HYDROGROW_TRANSPORT=mqtt` |
| Broker | `broker/mosquitto.conf` (Pi), `tools/dev_broker.js` (laptop) | `mosquitto` | Azure IoT Hub |
| Ingest | `ingest/ingest.py`, `ingest/schema.sql` | `hydrogrow-ingest` | Function `processTelemetry`, Blob Storage, Digital Twins writes |
| Backend | `backend/` (Express 5, better-sqlite3) | `hydrogrow-backend` | App Service backend + Function `analytics` + Function `get_twin` |
| Dashboard | `local-edition/dashboard/src` overrides on top of the repo's `dashboard/` | built into `backend/build`, served by the backend | Static Web App / App Service build |

There is one firmware. `firmware/main.py` imports `IoTHubDeviceClient` and `Message` from
`azure.iot.device` when `HYDROGROW_TRANSPORT=azure`, and from `mqtt_publisher` when it is
`mqtt` (the default). The rest of the loop is identical in both editions.

## Data flow

1. **Publish.** Every `SENSOR_INTERVAL_S` the firmware builds the payload in
   [PAYLOAD_CONTRACT.md](PAYLOAD_CONTRACT.md) section 1 and hands it to `mqtt_publisher`. The
   publisher writes it to `$HYDROGROW_DATA_DIR/mqtt_queue/` first, publishes with QoS 1, and
   deletes the file only after the broker acknowledges it. Broker restarts, network drops and
   reboots do not lose readings.
2. **Ingest.** `ingest.py` subscribes with a fixed client id and a persistent session, so the
   broker queues messages while ingest is down. Each message is decoded like the Azure
   Function did, stored in `telemetry` under an Azure-style blob name
   (`YYYYMMDD_HHMMSS_microseconds.json`), and the twin properties are updated with the
   Function's rules (contract section 3). A heartbeat goes to `service_state` every 5 s.
3. **Serve.** The backend reads the same SQLite file (WAL mode, one writer, many readers). It
   picks the latest reading by greatest blob name, exactly like the old Blob listing, and
   rebuilds the analytics and twin documents from the stored rows.

## Storage (`ingest/schema.sql`)

| Table | Holds |
|---|---|
| `telemetry` | raw payload JSON plus extracted columns (pH normalised from `pH`/`ph`, EC, temperature, humidity, water level, source, status), `ingested_at`, `pi_timestamp`, `blob_name`, `ingest_day` |
| `twins`, `twin_state` | the five twins (`plant1..3`, `watertank1`, `environment1`) and their properties with per-property update times |
| `users` | email, bcrypt hash, opaque bearer token (one per user), created time |
| `service_state` | ingest heartbeat and counters for `/health` |

About 1.5 KB per reading: at a 30 s sensor interval that is roughly 4 MB per day.

## HTTP API (backend, port 8080)

| Route | Auth | Purpose |
|---|---|---|
| `GET /api/pidata` | none | latest reading, remapped for the dashboard (contract section 4) |
| `GET /api/pidata/source` | none | `source` of the latest reading (`pi`, `fake`, `replay`), age, stale threshold, dry-run flag |
| `GET /api/analytics?days=N` | none | daily averages, a port of the Azure Function (contract section 5) |
| `GET /twins`, `GET /twins/:id` (also under `/api`) | none, CORS `*` | twin documents in Azure Digital Twins shape for Unity |
| `GET /health` (also `/api/health`) | none | broker reachable, ingest heartbeat, database, last-reading age; 200 or 503 |
| `POST /api/auth/register`, `/login`, `/logout`, `GET /api/auth/me` | bearer token on `/me` | opaque random tokens stored in SQLite, not JWT |
| `POST /api/chat` | none | optional Hugging Face chat; disabled without `HF_API_KEY`, 15 s timeout |
| `GET /*` | none | the React build; unknown `/api/*` paths return a JSON 404 |

`backend/test/contract.test.js` checks these shapes against the cloud edition's behaviour,
including the exact parsers the Unity scripts use on the twin documents.

## Data-source labels (Demo Mode honesty)

Every stored reading carries a `source`. The real firmware sends none, so it is stored as
`pi`. `tools/fake_pi.py` tags its frames `fake` and `tools/replay.py` tags its frames `replay`.
The dashboard badge is driven only by the source of the latest stored reading:

| Source | Badge |
|---|---|
| `pi` | **Live** (amber "stale" after 2 x `SENSOR_INTERVAL_S` with no new reading) |
| `replay` | **Demo Mode** |
| `fake` | **Simulated** |
| none, unknown, or backend unreachable | never "Live" |

There is no config flag that can make simulated or replayed data show as Live. Sensors that
return nothing are shown as `--` with a "not responding" warning, not as 0.

## Timing

The firmware's defaults keep the original single 30-minute cycle. On the Pi, `setup.sh`
writes `SENSOR_INTERVAL_S=30`, `CAMERA_INTERVAL_S=300` and `DOSING_COOLDOWN_S=1800`, so the
dashboard updates every 30 s while dosing still happens at most every 30 minutes. The dosing
cooldown is persisted, so a reboot cannot trigger an extra dose. `PUMPS_DRY_RUN=1` (the
default after setup) makes every dosing and water decision and publishes it with
`"dry_run": true`, but never drives a relay.

## Boot and failure behaviour

- No unit waits for the network or NTP. Without internet the firmware starts right after
  Mosquitto and publishes `status: "clock_unsynced"` until the clock syncs (the Pi has no RTC).
- All three HydroGrow units use `Restart=always`. Mosquitto keeps queued QoS 1 messages on disk.
- `/health` turns 200 once the firmware's first reading is stored: TensorFlow loads in 30 to
  60 s, so expect green about 60 to 90 s after power-on.

## Security model

The Pi is meant for an isolated LAN (a travel router or hotspot). The broker accepts anonymous
clients and the read endpoints are public, as they were in the cloud edition. To lock it down,
set `allow_anonymous false` with a password file in `broker/mosquitto.conf` and set
`MQTT_USER` / `MQTT_PASS`. Secrets live only in `/etc/hydrogrow/hydrogrow.env` (mode 640) and
`/etc/hydrogrow/cloudflared.env` (mode 600); the repo ships `.env.example` with placeholders.
