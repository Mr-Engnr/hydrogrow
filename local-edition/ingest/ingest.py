#!/usr/bin/env python3
"""
HydroGrow Local Edition ingest: MQTT -> SQLite.

Local replacement for the Azure Function `processTelemetry`. For every message
on hydrogrow/telemetry it:
  1. decodes / unwraps exactly like the Function (strip, skip empty, [0] of arrays)
  2. stores the raw payload plus extracted columns in the telemetry table,
     under an Azure-style blob_name YYYYMMDD_HHMMSS_microseconds.json
  3. updates twin_state with the same property names and rules the Function
     wrote to Azure Digital Twins (watertank1, environment1, plant1..3)

Differences from the Function:
  - "pH" and "ph" are both accepted; a normalised ph column is stored
  - nutrient_status: null is treated as {} instead of raising
  - the raw JSON is stored as received; the Pi's own timestamp is kept in a
    column, and ingested_at holds the naive-UTC value the Function used to
    overwrite "timestamp" with (both values are available)

Config comes from the environment (see .env.example):
  MQTT_HOST, MQTT_PORT, MQTT_TOPIC, MQTT_USER, MQTT_PASS, HYDROGROW_DB
"""

import json
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

# ------------------------------------------------------------------ config
MQTT_HOST  = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT  = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "hydrogrow/telemetry")
MQTT_USER  = os.getenv("MQTT_USER") or None
MQTT_PASS  = os.getenv("MQTT_PASS") or None
CLIENT_ID  = os.getenv("INGEST_CLIENT_ID", "hydrogrow-ingest")
# Same default as the backend (backend/src/config/env.config.js): local-edition/data/hydrogrow.db
DB_PATH    = Path(os.getenv("HYDROGROW_DB") or str(Path(__file__).resolve().parent.parent / "data" / "hydrogrow.db"))
SCHEMA_SQL = Path(__file__).with_name("schema.sql")
HEARTBEAT_S = 5

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s ingest %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("ingest")


# ------------------------------------------------------------------ helpers (rules from function_app.py)
# Local Edition change: the water alert is judged on water_level_pct with the
# dashboard thresholds (<=20 % critical, <=40 % warning). The Function compared the
# raw cm distance against 20, which fired on a full tank. waterLevel (cm) is still
# written to the twin unchanged; waterLevelPct is written alongside it.
def get_alert_status(key, value):
    if key == "ph":
        if value < 6.0: return "Low pH: Use pH Up Nutrient"
        if value > 8.0: return "High pH: Use pH Down Nutrient"
    elif key == "waterLevelPct":
        if value <= 20: return "Critical: Low Water Level"
        if value <= 40: return "Warning: Low Water Level"
    elif key == "temperature" and (value < 18 or value > 30):
        return "Warning: Temperature out of range"
    return "Normal"


def utc_naive_now():
    """Function used datetime.utcnow(); reproduce a naive UTC datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_int_flag(v):
    if v is None:
        return None
    return 1 if v else 0


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ------------------------------------------------------------------ storage
class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self.conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        self.conn.commit()
        self.lock = threading.Lock()
        log.info("db ready at %s", path)

    # -- telemetry ---------------------------------------------------------
    def insert_telemetry(self, data: dict, raw_text: str) -> str:
        now = utc_naive_now()
        blob_name = now.strftime("%Y%m%d_%H%M%S_%f") + ".json"
        ingest_day = now.strftime("%Y-%m-%d")

        ph = num(data.get("pH", data.get("ph")))
        ns = data.get("nutrient_status") or {}
        dp = data.get("disease_predictions") or {}
        dosing = data.get("dosing") or {}

        def plant(pid):
            p = dp.get(pid) or {}
            return p.get("label"), num(p.get("confidence"))

        p1l, p1c = plant("plant1")
        p2l, p2c = plant("plant2")
        p3l, p3c = plant("plant3")

        row = (
            blob_name, now.isoformat(), ingest_day, data.get("timestamp"),
            data.get("source") or "pi",
            ph, num(data.get("ec")), num(data.get("tds")),
            num(data.get("temperature")), num(data.get("humidity")),
            num(data.get("water_level", data.get("waterLevel"))),
            num(data.get("water_level_cm")), num(data.get("water_level_pct")),
            to_int_flag(data.get("water_low")),
            data.get("growth_day_actual"), data.get("growth_day_model"),
            data.get("growth_phase"), to_int_flag(data.get("harvest_flush")),
            data.get("status"), data.get("image"),
            ns.get("label"), num(ns.get("confidence")),
            p1l, p1c, p2l, p2c, p3l, p3c,
            to_int_flag((dosing.get("nutrient_a") or {}).get("dosed")),
            to_int_flag((dosing.get("nutrient_b") or {}).get("dosed")),
            raw_text,
        )
        sql = """INSERT INTO telemetry (
            blob_name, ingested_at, ingest_day, pi_timestamp, source,
            ph, ec, tds, temperature, humidity,
            water_level, water_level_cm, water_level_pct, water_low,
            growth_day_actual, growth_day_model, growth_phase, harvest_flush,
            status, image, nutrient_label, nutrient_confidence,
            plant1_label, plant1_confidence, plant2_label, plant2_confidence,
            plant3_label, plant3_confidence, dosing_a_dosed, dosing_b_dosed, raw_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        with self.lock:
            for attempt in range(3):
                try:
                    self.conn.execute(sql, row)
                    self.conn.commit()
                    return blob_name
                except sqlite3.IntegrityError:
                    # same microsecond twice: nudge the name like a retry would
                    now = utc_naive_now()
                    blob_name = now.strftime("%Y%m%d_%H%M%S_%f") + ".json"
                    row = (blob_name,) + row[1:]
            raise

    # -- twins -------------------------------------------------------------
    def patch_twin(self, twin_id: str, patch: list):
        """patch = [{"op":"add","path":"/prop","value":v}, ...] like ADT JSON-Patch."""
        ts = utc_naive_now().isoformat()
        with self.lock:
            for op in patch:
                prop = op["path"].lstrip("/")
                self.conn.execute(
                    "INSERT INTO twin_state (twin_id, property, value_json, updated_at) "
                    "VALUES (?,?,?,?) ON CONFLICT(twin_id, property) DO UPDATE SET "
                    "value_json=excluded.value_json, updated_at=excluded.updated_at",
                    (twin_id, prop, json.dumps(op["value"]), ts),
                )
            self.conn.commit()

    # -- liveness ----------------------------------------------------------
    def heartbeat(self, state: dict):
        ts = utc_naive_now().isoformat()
        with self.lock:
            self.conn.execute(
                "INSERT INTO service_state (service, state_json, updated_at) VALUES ('ingest',?,?) "
                "ON CONFLICT(service) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
                (json.dumps(state), ts),
            )
            self.conn.commit()


# ------------------------------------------------------------------ twin update (mirrors processTelemetry)
def update_twins(store: Store, data: dict):
    normalized = dict(data)
    normalized["ph"] = data.get("pH", data.get("ph"))
    normalized["waterLevel"] = data.get("water_level", data.get("waterLevel"))
    normalized["waterLevelPct"] = data.get("water_level_pct")

    mapping = {
        "ph": "watertank1", "ec": "watertank1", "waterLevel": "watertank1", "waterLevelPct": "watertank1",
        "temperature": "environment1", "humidity": "environment1",
    }
    for key, value in normalized.items():
        if key in mapping and value is not None:
            twin_id = mapping[key]
            patch = [{"op": "add", "path": f"/{key}", "value": value}]
            if key in ["ph", "waterLevelPct", "temperature"]:
                patch.append({"op": "add", "path": "/alertStatus", "value": get_alert_status(key, value)})
            store.patch_twin(twin_id, patch)

    disease_predictions = data.get("disease_predictions") or {}
    nutrient_data = data.get("nutrient_status") or {}          # null -> {}
    nutrient_label = nutrient_data.get("label")
    nutrient_conf = nutrient_data.get("confidence")

    planted_plants = ["plant1", "plant2"]
    for plant_id in ["plant1", "plant2", "plant3"]:
        plant_patch = []
        if plant_id in disease_predictions and disease_predictions[plant_id]:
            plant_data = disease_predictions[plant_id]
            disease_status = plant_data.get("label", "Unknown")
            disease_confidence = float(plant_data.get("confidence", 0.0)) * 100   # 0-1 -> 0-100 for Unity
            plant_patch.append({"op": "add", "path": "/disease_status", "value": disease_status})
            plant_patch.append({"op": "add", "path": "/disease_confidence", "value": disease_confidence})
            plant_patch.append({"op": "add", "path": "/diseased", "value": disease_status != "Healthy"})
        if plant_id in planted_plants and nutrient_label is not None:
            plant_patch.append({"op": "add", "path": "/nutrient_status", "value": nutrient_label})
            plant_patch.append({"op": "add", "path": "/nutrient_confidence", "value": float(nutrient_conf or 0.0)})
        if plant_patch:
            store.patch_twin(plant_id, plant_patch)


# ------------------------------------------------------------------ message handling
class Ingest:
    def __init__(self):
        self.store = Store(DB_PATH)
        self.connected = False
        self.count = 0
        self.last_blob = None
        self.last_source = None
        self.stop = threading.Event()

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=CLIENT_ID,
            clean_session=False,          # broker queues QoS1 while we are down
            protocol=mqtt.MQTTv311,
        )
        if MQTT_USER:
            self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    # paho callbacks ----------------------------------------------------------
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.error("connect failed: %s", reason_code)
            return
        self.connected = True
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info("connected to %s:%s, subscribed %s (session_present=%s)",
                 MQTT_HOST, MQTT_PORT, MQTT_TOPIC, getattr(flags, "session_present", flags))
        self.write_heartbeat()

    def on_disconnect(self, client, userdata, flags, reason_code=None, properties=None):
        self.connected = False
        log.warning("disconnected (%s); paho will reconnect", reason_code)

    def on_message(self, client, userdata, msg):
        try:
            message = msg.payload.decode("utf-8").strip()
            if not message:
                log.warning("empty message received")
                return
            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                log.error("invalid JSON: %s", e)
                return
            if isinstance(data, list):              # batch unwrap, as the Function did
                data = data[0]
            if not isinstance(data, dict):
                log.error("payload is not an object: %r", type(data))
                return

            blob_name = self.store.insert_telemetry(data, json.dumps(data))
            self.count += 1
            self.last_blob = blob_name
            self.last_source = data.get("source") or "pi"
            try:
                update_twins(self.store, data)
            except Exception as e:                   # twin failure never blocks storage
                log.error("twin update failed: %s", e)
            log.info("stored %s source=%s pH=%s ec=%s", blob_name, self.last_source,
                     data.get("pH", data.get("ph")), data.get("ec"))
        except Exception as e:
            log.exception("message handling error: %s", e)

    # lifecycle ---------------------------------------------------------------
    def write_heartbeat(self):
        try:
            self.store.heartbeat({
                "broker_connected": self.connected,
                "messages_stored": self.count,
                "last_blob_name": self.last_blob,
                "last_source": self.last_source,
                "pid": os.getpid(),
            })
        except Exception as e:
            log.error("heartbeat failed: %s", e)

    def heartbeat_loop(self):
        while not self.stop.is_set():
            self.write_heartbeat()
            self.stop.wait(HEARTBEAT_S)

    def run(self):
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: self.shutdown())
        signal.signal(signal.SIGINT, lambda *_: self.shutdown())
        # connect_async + loop_forever keeps retrying if the broker is not up yet
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        log.info("starting; broker %s:%s db %s", MQTT_HOST, MQTT_PORT, DB_PATH)
        self.client.loop_forever(retry_first_connection=True)

    def shutdown(self):
        if self.stop.is_set():
            return
        log.info("shutting down")
        self.stop.set()
        try:
            self.store.heartbeat({"broker_connected": False, "messages_stored": self.count,
                                  "last_blob_name": self.last_blob, "last_source": self.last_source,
                                  "pid": os.getpid(), "stopped": True})
        except Exception:
            pass
        self.client.disconnect()


if __name__ == "__main__":
    Ingest().run()
