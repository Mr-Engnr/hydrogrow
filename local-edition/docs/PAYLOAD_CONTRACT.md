# HydroGrow Payload Contract

Extracted from `firmware/main.py` (v2.0), `cloud/functions/function_app.py`,
`backend/src/routes/pidata.routes.js` and `dashboard/src/pages/Dashboard.jsx`
in the cloud edition of this repo. This is the contract the Local Edition honours
field for field. Nothing here changes sensor, dosing, growth-day, ML or pump logic.

---

## 1. Pi -> broker: telemetry message

**Producer:** `publish()` in `firmware/main.py`
**Transport (Azure):** one IoT Hub `Message(json.dumps(payload))`, `content_type=application/json`, `content_encoding=utf-8`
**Transport (local):** MQTT topic `hydrogrow/telemetry`, QoS 1, same JSON body
**Cadence:** once per supervisory cycle, `LOOP_INTERVAL = 1800 s` (30 min)

### 1.1 Field table

Casing is exact. Note `pH` (capital H); everything else is snake_case.

| Field | Type | Unit / range | Source | Notes |
|---|---|---|---|---|
| `temperature` | number or null | degC, validated 0..60 | DHT22 | null when DHT read fails (tolerated by `validate()`) |
| `humidity` | number or null | % RH, validated 0..100 | DHT22 | null when DHT read fails |
| `pH` | number | pH, validated 2.0..11.0 | ADS1115 A3 | **capital H**. Never null in a published frame |
| `ec` | number | mS/cm, validated 0..5, 3 dp | ADS1115 A1 | temp-compensated |
| `tds` | number | ppm, 1 dp | derived from EC | |
| `water_level` | number | **cm distance from sensor to water surface**, validated 0.5..20.0 | HC-SR04 | smaller = more water. Raw distance kept "for compatibility". NOT a percentage |
| `water_level_cm` | number or null | cm of water in box, 2 dp | `TOTAL_BOX_DEPTH - water_level` | |
| `water_level_pct` | number or null | 0..100 %, 1 dp | `water_level_cm / TOTAL_BOX_DEPTH * 100` | what the dashboard card shows |
| `water_low` | boolean or null | | `water_level >= LEVEL_LOW_DISTANCE (3.0)` | |
| `timestamp` | string | ISO-8601 **with** `+00:00` | `datetime.now(timezone.utc).isoformat()` | **Overwritten by the cloud** (see section 2) |
| `growth_day_actual` | integer | days since `PLANTING_DATE`, >= 1 | calendar | absent in error frames published from `enter_error()` |
| `growth_day_model` | integer | 1..60 | `round(actual * 1.5)` clamped | absent in error frames |
| `growth_phase` | string | `Germination`, `Seedling`, `Vegetative`, `Mature`, `Harvest Ready` | | absent in error frames |
| `harvest_flush` | boolean | | `actual_day >= 37` | absent in error frames |
| `image` | string or null | basename of capture, e.g. `20260604_140001.jpg` | picamera2 | null if camera unavailable |
| `status` | string | `"ok"`, `"validation failed"`, or `"water_warning: <info>"` | | error string doubles as status |
| `disease_predictions` | object | keys `plant1`, `plant2`, `plant3` always present | MobileNetV2 on Pi | each value is `{label, confidence}` or `null` |
| `disease_predictions.<plant>.label` | string | `Bacterial`, `Healthy`, `Septoria_blight_on_lettuce` | | |
| `disease_predictions.<plant>.confidence` | number | **0.0..1.0**, 4 dp | softmax max | 0-1 scale, unlike nutrient |
| `disease_predictions.plant3` | null | always | `ACTIVE_PLANTS.plant3 = False` | empty hole |
| `nutrient_status` | object or null | | Random Forest on Pi | null when model missing or any of pH/ec/temp/humidity/water_level is None |
| `nutrient_status.label` | string | `Healthy`, `Nitrogen_Deficient`, `Phosphorus_Deficient`, `Potassium_Deficient` | | |
| `nutrient_status.confidence` | number | **0.0..100.0**, 1 dp | `predict_proba max * 100` | 0-100 scale, unlike disease |
| `dosing` | object or null | | | null in error frames from `enter_error()` |
| `dosing.nutrient_a` | object | | `dose_nutrient_a()` | see 1.2 |
| `dosing.nutrient_b` | object | | `dose_nutrient_b()` | see 1.2 |

### 1.2 Dosing sub-objects

`dosing.nutrient_a` (model-driven macros, Pump B):

| Field | Type | Notes |
|---|---|---|
| `dosed` | boolean | |
| `reason` | string or null | e.g. `"EC 1.45 in range (>= 1.2); no dose needed"` |
| `burst_s` | number | seconds, 0 when not dosed |
| `ec` | number or null | EC used for the decision |
| `label` | string or null | nutrient label used |
| `confidence` | number or null | 0-100 |

`dosing.nutrient_b` (schedule-driven micros, Pump C):

| Field | Type | Notes |
|---|---|---|
| `dosed` | boolean | |
| `reason` | string or null | e.g. `"next Nutrient B in 18.2h"` |
| `burst_s` | number | seconds |
| `phase` | string | growth phase |
| `target_ml` | number | per-phase target, 1 dp |
| `dosed_ml` | number | cumulative this phase, 1 dp |

During harvest flush (`growth_day_actual >= 37`) both sub-objects collapse to
`{"dosed": false, "reason": "harvest flush (day N)"}` with no other keys.

### 1.2a Local Edition additions

Present only when the corresponding feature is active; with default settings the payload is byte-identical to the original.

| Field / value | When | Meaning |
|---|---|---|
| `dosing.nutrient_a` / `nutrient_b` = `{"dosed": false, "reason": "dosing cooldown (Ns remaining)"}` | `SENSOR_INTERVAL_S < DOSING_COOLDOWN_S` and a tick falls inside the cooldown | same shape as the harvest-flush branch |
| `dry_run: true` | `PUMPS_DRY_RUN=1` | decisions were made and logged but no relay was driven |
| `water_regulation: {"dry_run": true, "action": "would_top_up" \| "no_action"}` | `PUMPS_DRY_RUN=1`, on ticks where the water pass ran | `regulate_water()` decides from one level read and returns immediately (no 300 s fill loop); live mode is unchanged |
| `status: "clock_unsynced"` | system year < 2026 and no other error | Pi clock has not synced; growth day and timestamps unreliable |
| `source: "fake"` / `"replay"` | tools/fake_pi.py / tools/replay.py | never sent by the real Pi; drives the dashboard badge |

### 1.3 Example payload (normal cycle)

```json
{
  "temperature": 24.3,
  "humidity": 61.2,
  "pH": 6.12,
  "ec": 1.456,
  "tds": 728.0,
  "water_level": 2.4,
  "water_level_cm": 9.4,
  "water_level_pct": 79.7,
  "water_low": false,
  "timestamp": "2026-06-18T09:00:12.481233+00:00",
  "growth_day_actual": 18,
  "growth_day_model": 27,
  "growth_phase": "Vegetative",
  "harvest_flush": false,
  "image": "20260618_090010.jpg",
  "status": "ok",
  "disease_predictions": {
    "plant1": { "label": "Healthy", "confidence": 0.9731 },
    "plant2": { "label": "Bacterial", "confidence": 0.8812 },
    "plant3": null
  },
  "nutrient_status": { "label": "Healthy", "confidence": 96.4 },
  "dosing": {
    "nutrient_a": {
      "dosed": false,
      "reason": "EC 1.456 in range (>= 1.2); no dose needed",
      "burst_s": 0,
      "ec": 1.456,
      "label": null,
      "confidence": null
    },
    "nutrient_b": {
      "dosed": false,
      "reason": "next Nutrient B in 17.9h",
      "burst_s": 0,
      "phase": "Vegetative",
      "target_ml": 100.0,
      "dosed_ml": 41.0
    }
  }
}
```

### 1.4 Example payload (error frame from `enter_error()`)

Published when `validate()` rejects the frame. Growth-day keys are absent.

```json
{
  "temperature": null,
  "humidity": null,
  "pH": 6.05,
  "ec": 1.401,
  "tds": 700.5,
  "water_level": 25.1,
  "water_level_cm": 0.0,
  "water_level_pct": 0.0,
  "water_low": true,
  "timestamp": "2026-06-18T09:30:11.002911+00:00",
  "image": "20260618_093009.jpg",
  "status": "validation failed",
  "disease_predictions": { "plant1": null, "plant2": null, "plant3": null },
  "nutrient_status": null,
  "dosing": null
}
```

---

## 2. Cloud ingest (`processTelemetry`): what local `ingest.py` must replicate

1. Decode body as UTF-8, strip, skip if empty, skip if invalid JSON.
2. If the body is a JSON **array**, use element `[0]`.
3. **Overwrite** `data["timestamp"]` with `datetime.utcnow().isoformat()`: naive UTC, **no** `+00:00` suffix, microseconds included (e.g. `2026-06-18T09:00:13.104552`). The Pi's own tz-aware timestamp is lost in the stored record.
4. Store the full JSON. Azure blob name: `datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f') + ".json"` giving `YYYYMMDD_HHMMSS_microseconds.json`, e.g. `20260618_090013_104552.json`. Backend `/pidata` filters names with `^\d{8}_\d{6}_\d+\.json$` and picks the lexicographically greatest. Local SQLite keeps this same `blob_name` column so "latest" selection is identical.
5. Update twin state (section 3). Twin failures are swallowed; storage is never blocked by twin errors.

---

## 3. Twin state (Azure Digital Twins properties written by `processTelemetry`)

Key normalisation first: `ph = data.pH ?? data.ph`, `waterLevel = data.water_level ?? data.waterLevel`.
Only non-null values are written. `water_level_pct` is **not** written to any twin.

### `watertank1`

| Property | Source | Alert rule (`alertStatus`) |
|---|---|---|
| `ph` | `pH` | `< 6.0` -> `"Low pH: Use pH Up Nutrient"`, `> 8.0` -> `"High pH: Use pH Down Nutrient"`, else `"Normal"` |
| `ec` | `ec` | no alert written for ec |
| `waterLevel` | `water_level` (**raw cm distance**) | none (Local Edition change: the Function compared cm `< 20`, which fired on a full tank) |
| `waterLevelPct` | `water_level_pct` (Local Edition addition) | `<= 20` -> `"Critical: Low Water Level"`, `<= 40` -> `"Warning: Low Water Level"`, else `"Normal"` (same thresholds as the dashboard) |
| `alertStatus` | last rule applied in dict iteration order | the `waterLevelPct` rule is evaluated last and wins; absent when the sender has no `water_level_pct` |

### `environment1`

| Property | Source | Alert rule |
|---|---|---|
| `temperature` | `temperature` | `< 18 or > 30` -> `"Warning: Temperature out of range"`, else `"Normal"` |
| `humidity` | `humidity` | none |
| `alertStatus` | temperature rule | |

### `plant1`, `plant2`, `plant3` (DTDL `dtmi:hydroponic:plant;2`)

| Property | Schema | Source | Scale |
|---|---|---|---|
| `disease_status` | string | `disease_predictions.<id>.label` (default `"Unknown"`) | |
| `disease_confidence` | double | `disease_predictions.<id>.confidence` **x 100** | 0-100 |
| `diseased` | boolean | `disease_status != "Healthy"` | |
| `nutrient_status` | string | `nutrient_status.label` | plant1 and plant2 only |
| `nutrient_confidence` | double | `float(nutrient_status.confidence or 0.0)` as-is | 0-100 |

Disease props are written only when `disease_predictions[<id>]` is truthy, so `plant3` never gets them.
Nutrient props are written only to `plant1`/`plant2` and only when `nutrient_status.label` is not None.

### `/twins/{twinId}` response shape (what Unity parsed)

ADT returns the twin document. The local endpoint returns the same shape:

```json
{
  "$dtId": "watertank1",
  "$etag": "W/\"<opaque>\"",
  "$metadata": { "$model": "dtmi:hydroponic:watertank;1" },
  "ph": 6.12,
  "ec": 1.456,
  "waterLevel": 2.4,
  "alertStatus": "Critical: Low Water Level"
}
```

```json
{
  "$dtId": "plant2",
  "$etag": "W/\"<opaque>\"",
  "$metadata": { "$model": "dtmi:hydroponic:plant;2" },
  "disease_status": "Bacterial",
  "disease_confidence": 88.12,
  "diseased": true,
  "nutrient_status": "Healthy",
  "nutrient_confidence": 96.4
}
```

Errors: `{"error": "<message>"}` with HTTP 500, `Access-Control-Allow-Origin: *`.

---

## 4. Backend `/api/pidata` response (consumed by the dashboard)

**Auth:** none. The route is mounted before `authMiddleware`; the dashboard still sends a Bearer header, which is ignored.
**Shape:** a one-element array `[remapped]`.

| Response key | Source expression | Notes |
|---|---|---|
| `ph` | `data.pH ?? data.ph ?? null` | |
| `ec` | `data.ec` | |
| `waterTemp` | `data.temperature` | labelled "Water Temp" in the UI but is DHT22 air temp |
| `humidity` | `data.humidity` | |
| `waterLevel` | `data.waterLevel ?? data.water_level ?? null` | **raw cm distance** |
| `waterLevelPct` | `data.water_level_pct ?? null` | |
| `waterLow` | `data.water_low ?? null` | |
| `health_status` | `data.nutrient_status?.label OR data.nutrient_status OR "Unknown"` | string |
| `nutrient_confidence` | `data.nutrient_confidence` | **always `undefined`** (key does not exist in the payload), so omitted from JSON |
| `plant1` | `data.plant1 OR null` | always `null` (top-level key never sent) |
| `plant2` | `data.plant2 OR null` | always `null` |
| `plant3` | `data.plant3 OR null` | always `null` |
| `disease_predictions` | `data.disease_predictions OR null` | passed through untouched, confidence still 0-1 |

404 `{"error": "No data found"}` when no matching blob. 500 `{"error": "<message>"}` on failure.

Example:

```json
[{
  "ph": 6.12,
  "ec": 1.456,
  "waterTemp": 24.3,
  "humidity": 61.2,
  "waterLevel": 2.4,
  "waterLevelPct": 79.7,
  "waterLow": false,
  "health_status": "Healthy",
  "plant1": null,
  "plant2": null,
  "plant3": null,
  "disease_predictions": {
    "plant1": { "label": "Healthy", "confidence": 0.9731 },
    "plant2": { "label": "Bacterial", "confidence": 0.8812 },
    "plant3": null
  }
}]
```

### Dashboard fields read from `/pidata`

`Dashboard.jsx` takes `data[data.length - 1]` and reads: `ph`, `ec`, `waterTemp`, `humidity`, `waterLevel`, `waterLevelPct`, `health_status`, `disease_predictions.{plant1,plant2,plant3}.{label,confidence}`. Falsy numeric values become `0` (`latest.ph || 0`). Disease confidence is multiplied by 100 in the UI; "Disease Detected" needs `confidence >= 0.7`.

---

## 5. Backend `/api/analytics?days=N` response (proxied from the Azure Function)

**Auth:** none. `days` parsed as int, default 7, non-positive becomes 7.

Function logic:
- `cutoff = utcnow - timedelta(days=N)`
- For each blob whose name parses as `YYYYMMDD_*`: `blob_date = strptime(first segment, "%Y%m%d")`; include if `blob_date >= cutoff`. Day key = `blob_date.strftime("%Y-%m-%d")` (UTC ingest date, **not** the payload timestamp).
- Collect `data["ph"]`, `data["ec"]`, `data["temperature"]`, `data["humidity"]` only when the key is present.
- `labels = sorted(daily_ph.keys())`: the label axis is driven by **ph** days only.
- `avg(lst) = round(sum/len, 2)` or `0` if empty.

```json
{
  "labels": ["2026-06-12", "2026-06-13", "2026-06-14"],
  "daily_avg_ph": [6.1, 6.08, 6.15],
  "daily_avg_ec": [1.44, 1.47, 1.5],
  "daily_avg_temp": [24.1, 24.6, 23.9],
  "daily_avg_humidity": [60.2, 62.8, 59.4],
  "overall_week_avg_ph": 6.11
}
```

Dashboard reads `labels`, `daily_avg_ph`, `daily_avg_ec`, `daily_avg_temp`, `daily_avg_humidity`, `overall_week_avg_ph`. Renders charts only when `analyticsData.labels` is truthy.

---

## 6. Auth routes (`/api/auth/*`)

Mechanism is **opaque random bearer tokens** (`crypto.randomBytes(32).hex`) stored on the user record. Not JWT. The cloud edition kept users in `backend/src/data/users.json`; the Local Edition keeps the same records in the SQLite `users` table and seeds one demo user from `DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD`.

| Route | Method | Auth | Request | Response |
|---|---|---|---|---|
| `/api/auth/register` | POST | no | `{email, password, name}` | 201 `{success, message, user:{id,email,name}}`; 400 `{success:false, message}` |
| `/api/auth/login` | POST | no | `{email, password}` | 200 `{success, message, token, user:{id,email,name}}`; 401 on bad creds |
| `/api/auth/logout` | POST | Bearer (optional) | | `{success:true, message}` |
| `/api/auth/me` | GET | **authMiddleware** | | `{success:true, user:{id,email,name}}`; 401 `{success:false, message}` |

User record: `{id: uuid, email: lowercase, password: bcrypt(10), name, token: string|null, createdAt: ISO}`. One active token per user; login rotates it, logout nulls it.

## 7. Other routes

| Route | Method | Auth | Status in the Local Edition |
|---|---|---|---|
| `/api/chat` | POST `{input}` -> `{reply}` | no | keep; HuggingFace router; fails with 500 `{reply: "The AI is currently busy...", details}` offline |
| `/api/esp32data` | GET | **authMiddleware** (the only protected data route) | **removed**; it proxied a dead Azure-hosted URL and no dashboard code called it. Unknown `/api/*` paths return a JSON 404 |
| `/{*path}` | GET | no | serves `backend/build/index.html` (React SPA) |

Dashboard API base: the cloud edition used `process.env.NODE_ENV === 'production' ? "/api" : <dev host>/api`. The Local Edition always uses the relative `/api` (override with `REACT_APP_API_BASE` for development), so no host is baked into the bundle.

## 8. Publisher swap surface (`firmware/mqtt_publisher.py`)

`main.py` touches the Azure SDK in exactly these places:

```python
from azure.iot.device import IoTHubDeviceClient, Message      # line 45
IOTHUB_CONN = os.getenv("IOTHUB_CONNECTION_STRING")           # line 183
iot = IoTHubDeviceClient.create_from_connection_string(IOTHUB_CONN)   # line 269
iot.connect()                                                 # line 270
msg = Message(json.dumps(payload)); msg.content_type = ...; msg.content_encoding = ...
iot.send_message(msg)                                         # line 798-801
```

A drop-in module exposing `IoTHubDeviceClient` (with `create_from_connection_string`, `connect`, `send_message`) and `Message` (with settable `content_type` / `content_encoding`) lets the swap be a single import. `firmware/main.py` picks the module from `HYDROGROW_TRANSPORT` (`mqtt` default, `azure` for the cloud edition). The connection-string argument is ignored by the MQTT transport; the broker host comes from the environment.
