# Architecture

## Data flow

```
Raspberry Pi 4B (sensors + on-device ML + pump control)
    | MQTT over TLS :8883, every 15s
    v
Azure IoT Hub (device auth + ingestion)
    | Event Hub-compatible endpoint
    v
Azure Function: processTelemetry (Python, Consumption plan)
    | writes YYYYMMDD_HHMMSS_microseconds.json
    v
Azure Blob Storage (telemetry-data container)
    |                          \
    | latest blob               \ JSON-Patch updates
    v                            v
Express backend /pidata     Azure Digital Twins
    |                            (watertank1, environment1, plant1)
    v                            |
React dashboard              Unity 3D scene (live mirror)
```

Analytics path: Blob Storage -> Azure Function /api/analytics (HTTP, reads last N
days, computes daily averages) -> Express proxy /api/analytics -> dashboard charts.
The proxy exists because calling the Function directly from the browser hit CORS.

## Layer responsibilities

| Layer | Stack | Responsibility |
|---|---|---|
| Edge | Pi 4B, Python | Sensor sweep, nutrient + disease inference, dosing decisions, OLED status, telemetry publish |
| Transport | Azure IoT Hub | Device identity, MQTT ingestion, 8000 msg/day free tier |
| Processing | Azure Functions | Event-triggered blob persistence, HTTP analytics aggregation |
| Storage | Blob Storage | One timestamped JSON per reading |
| Twin | Azure Digital Twins | Live graph: water tank, environment, per-plant state |
| API | Node 20 + Express | Serves SPA, /pidata latest-reading endpoint, analytics proxy, JWT auth |
| UI | React | Live cards, trend charts, per-plant health with confidence bars |
| Visualization | Unity 3D | Reads Digital Twins graph, mirrors rig state in 3D |

## Design decisions worth knowing

**Blob selection by regex, not sort order.** The container also holds a 3D-scene
config file; naive alphabetical "latest blob" picked it up. The backend filters to
`^\d{8}_\d{6}_\d+\.json$` before selecting the newest.

**Field-name mapping at the API boundary.** Pi payload names (`temperature`,
`nutrient_status`) differ from dashboard expectations (`waterTemp`,
`health_status`). The remap lives in one place, `pidata.routes.js`, instead of
being patched at every layer. Field-name drift across four layers caused more
production bugs than any model.

**Single App Service for frontend + backend.** Express serves the compiled React
build for all non-API routes. One URL, one deploy, no CORS between UI and API.

**Frames, not video, for multi-plant vision.** One camera frame is cropped into
three fixed regions (per-plant ROI boxes in config) and each crop is scored
independently. One camera covers three plants with zero extra hardware.

## Deployment status

The original Azure deployment ran on a student subscription that has since been
disabled. All cloud components are reproducible from `cloud/infra/` against any
Azure subscription. Dashboard screenshots and the demo video in `media/` show the
system during its live deployment.

![Architecture diagram](../media/diagrams/architecture.png)
