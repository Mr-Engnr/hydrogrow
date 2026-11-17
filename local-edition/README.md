# HydroGrow Local Edition

The whole HydroGrow stack on one Raspberry Pi, or on a laptop with a simulated Pi: MQTT
broker, ingest to SQLite, Express backend, React dashboard and the Unity twin endpoint. No
cloud account, and no internet after installation.

- [docs/START_HERE.md](docs/START_HERE.md): Demo Mode on a laptop, then setup on a Pi
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, data flow, API, data-source labels
- [docs/PAYLOAD_CONTRACT.md](docs/PAYLOAD_CONTRACT.md): telemetry fields and API shapes
- [docs/EXPO_RUNBOOK.md](docs/EXPO_RUNBOOK.md): running it at a show, Demo Mode fallback, troubleshooting

| Folder | Contents |
|---|---|
| `broker/` | Mosquitto config for the Pi |
| `ingest/` | MQTT to SQLite service and the shared schema |
| `backend/` | Express API, serves the dashboard build; `npm test` runs the contract tests |
| `dashboard/` | only the files that differ from the repo's `dashboard/`; `npm run build` merges them |
| `tools/` | `fake_pi.py`, `replay.py`, `dev_broker.js` (laptop broker), `healthcheck.sh` |
| `deploy/` | Pi bootstrap, installer, hardware test, pinned Python versions, systemd units |
| `setup.sh` | the one command on the Pi |

The firmware is shared with the cloud edition: `firmware/main.py` with
`HYDROGROW_TRANSPORT=mqtt` publishes through `firmware/mqtt_publisher.py`. Model weights are
not stored here; setup downloads the disease model from the v1.0.0 release and copies the
nutrient model from `ml/`.
