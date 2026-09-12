# Cloud

Azure serverless layer: telemetry persistence, Digital Twin sync, and the
analytics API the dashboard charts read from.

## Functions (`functions/function_app.py`)

| Function | Trigger | Job |
|---|---|---|
| `processTelemetry` | Event Hub (IoT Hub built-in endpoint) | Writes each reading to blob, then patches the Digital Twin graph |
| `get_twin` | HTTP GET `/twins/{twinId}` | Reads a single twin, CORS-open for the Unity client |
| `analytics` | HTTP GET `/analytics?days=N` | Aggregates blobs into daily averages for pH, EC, temp, humidity |
| `predict_disease` | HTTP POST `/predict-disease` | TFLite inference on an uploaded image, also patches plant1 |

### Design notes

**Batch unwrapping.** IoT Hub sometimes delivers a JSON array rather than a
single object. `processTelemetry` unwraps `data[0]` before any field access.

**Key normalization at the boundary.** The Pi sends `pH` and `water_level`;
legacy senders and the twin schema use `ph` and `waterLevel`. Both are mapped in
one place rather than patched at every consumer. Field-name drift across Pi,
Function, twin, backend, and dashboard caused more production bugs than any model.

**Confidence scale mismatch, handled explicitly.** The disease model outputs 0-1
and Unity expects 0-100, so disease confidence is multiplied by 100. The nutrient
model already emits 0-100 and is written through unchanged. Both are commented
inline because this is exactly the kind of thing that breaks silently.

**Empty plant slots.** `plant3` has no live nutrient reading and arrives as
`None` when the grow hole is empty. A truthiness check runs before any `.get()`
so an empty slot skips cleanly instead of throwing.

**Blob date parsing.** Blob names are `YYYYMMDD_HHMMSS_microseconds.json`.
Analytics splits on underscore and parses the first segment; anything unparseable
is skipped rather than aborting the whole aggregation.

**Digital Twin failures are non-fatal.** The DT update sits in its own try/except
inside `processTelemetry`, so a twin outage never blocks blob persistence.
Telemetry durability outranks visualization.

## Digital Twin models (`digital-twin/`)

`plant_model_v2.json` defines the plant interface (`dtmi:hydroponic:plant;2`):

| Property | Schema |
|---|---|
| `disease_status` | string |
| `disease_confidence` | double (0-100) |
| `diseased` | boolean |
| `nutrient_status` | string |
| `nutrient_confidence` | double (0-100) |

Twin instances: `watertank1` (ph, ec, waterLevel, alertStatus), `environment1`
(temperature, humidity, alertStatus), and `plant1` / `plant2` / `plant3`.

<!-- PENDING: watertank and environment DTDL JSON not recovered. plant_model_v2.json
     is the only interface definition on hand. -->

## Local development

```bash
cd cloud/functions
cp local.settings.example.json local.settings.json   # fill in real values
pip install -r requirements.txt
func start
```

Deploy:

```bash
func azure functionapp publish <function-app-name> --python
```

## Configuration

All secrets live in Azure app settings, never in code. `local.settings.json` is
gitignored and never deployed.

| Setting | Purpose |
|---|---|
| `AzureWebJobsStorage` | Blob persistence and function state |
| `IotHubConnection` | Event Hub-compatible connection string |
| `IOTHUB_EVENTHUB_NAME` | Event Hub-compatible name from IoT Hub built-in endpoints |
| `ADT_URL` | Digital Twins instance endpoint |
| `FUNCTIONS_WORKER_RUNTIME` | `python` |

## Known limits

- `predict_disease` expects `models/disease_model.tflite` and
  `models/disease_classes.json` alongside the function. Weights ship via release.
- Digital Twins auth uses `DefaultAzureCredential`, requiring the Function App's
  managed identity to hold the Azure Digital Twins Data Owner role.
