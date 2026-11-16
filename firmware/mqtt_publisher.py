"""
mqtt_publisher.py: drop-in replacement for `azure.iot.device` used by main.py.

main.py only touches four things from the Azure SDK:
    from azure.iot.device import IoTHubDeviceClient, Message
    iot = IoTHubDeviceClient.create_from_connection_string(conn_str)
    iot.connect()
    msg = Message(json.dumps(payload)); msg.content_type = ...; msg.content_encoding = ...
    iot.send_message(msg)

This module exposes the same names with the same call shapes. main.py picks it
when HYDROGROW_TRANSPORT=mqtt (the default):
    from mqtt_publisher import IoTHubDeviceClient, Message

Behaviour:
  - publishes to MQTT_TOPIC (default hydrogrow/telemetry) with QoS 1
  - paho auto-reconnects with backoff; connect() never raises, it just starts
    the background loop (the Pi must keep running even if the broker is down)
  - every message is written to an on-disk queue BEFORE publishing and only
    deleted after the broker acknowledges it (PUBACK). A background flusher
    drains the queue in order whenever the connection is up. Readings are
    therefore never lost across broker restarts, Pi reboots or network drops.
  - send_message() returns within SEND_TIMEOUT_S; it logs instead of raising,
    matching main.py's existing try/except (which would otherwise double-buffer)

Config (env, see local-edition/.env.example):
  MQTT_HOST (default 127.0.0.1), MQTT_PORT (default 1883), MQTT_TOPIC, MQTT_USER, MQTT_PASS,
  MQTT_CLIENT_ID (hydrogrow-pi), HYDROGROW_DATA_DIR (~) -> <dir>/mqtt_queue/
"""

import glob
import logging
import os
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("mqtt_publisher")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "hydrogrow/telemetry")
MQTT_USER = os.getenv("MQTT_USER") or None
MQTT_PASS = os.getenv("MQTT_PASS") or None
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "hydrogrow-pi")
DATA_DIR = os.path.expanduser(os.getenv("HYDROGROW_DATA_DIR", "~"))
QUEUE_DIR = os.path.join(DATA_DIR, "mqtt_queue")
SEND_TIMEOUT_S = float(os.getenv("MQTT_SEND_TIMEOUT_S", "5"))
FLUSH_INTERVAL_S = 2.0


class Message:
    """Mirror of azure.iot.device.Message: data plus settable content metadata."""

    def __init__(self, data):
        self.data = data
        self.content_type = None
        self.content_encoding = None
        self.custom_properties = {}

    def __str__(self):
        return str(self.data)


class IoTHubDeviceClient:
    """Mirror of azure.iot.device.IoTHubDeviceClient backed by paho-mqtt."""

    def __init__(self):
        os.makedirs(QUEUE_DIR, exist_ok=True)
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._seq = 0
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        if MQTT_USER:
            self._client.username_pw_set(MQTT_USER, MQTT_PASS)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._flusher = threading.Thread(target=self._flush_loop, name="mqtt-flusher", daemon=True)

    # ---- Azure-compatible surface -------------------------------------------
    @classmethod
    def create_from_connection_string(cls, connection_string=None, **kwargs):
        # The Azure connection string is ignored; broker settings come from env.
        return cls()

    def connect(self):
        self._client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self._client.loop_start()
        self._flusher.start()
        if not self._connected.wait(timeout=5):
            log.warning("broker %s:%s not reachable yet; will keep retrying in background", MQTT_HOST, MQTT_PORT)
        else:
            log.info("connected to mqtt://%s:%s", MQTT_HOST, MQTT_PORT)

    def send_message(self, message):
        body = message.data if isinstance(message, Message) else message
        if isinstance(body, str):
            body = body.encode("utf-8")
        path = self._enqueue(body)
        # try to deliver right away so the caller's log line is truthful
        ok = self._publish_file(path, timeout=SEND_TIMEOUT_S)
        if not ok:
            log.warning("broker not acknowledging; reading kept in queue (%d pending)", self.pending())

    def disconnect(self):
        self._stop.set()
        self._client.loop_stop()
        self._client.disconnect()

    def shutdown(self):
        self.disconnect()

    # ---- queue ---------------------------------------------------------------
    def pending(self):
        return len(glob.glob(os.path.join(QUEUE_DIR, "*.json")))

    def _enqueue(self, body: bytes) -> str:
        with self._lock:
            self._seq += 1
            name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f") + f"_{self._seq:04d}.json"
        path = os.path.join(QUEUE_DIR, name)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fp:
            fp.write(body)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
        return path

    def _publish_file(self, path: str, timeout: float) -> bool:
        if not self._connected.is_set():
            return False
        try:
            with open(path, "rb") as fp:
                body = fp.read()
            info = self._client.publish(MQTT_TOPIC, body, qos=1)
            info.wait_for_publish(timeout=timeout)
            if info.is_published():
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
                return True
        except Exception as e:
            log.warning("publish failed for %s: %s", os.path.basename(path), e)
        return False

    def _flush_loop(self):
        while not self._stop.is_set():
            if self._connected.is_set():
                for path in sorted(glob.glob(os.path.join(QUEUE_DIR, "*.json"))):
                    if self._stop.is_set() or not self._connected.is_set():
                        break
                    if not self._publish_file(path, timeout=SEND_TIMEOUT_S):
                        break
            self._stop.wait(FLUSH_INTERVAL_S)

    # ---- paho callbacks ------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self._connected.set()
            n = self.pending()
            if n:
                log.info("connected; flushing %d queued readings", n)
        else:
            log.error("connect refused: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code=None, properties=None):
        self._connected.clear()
        log.warning("disconnected (%s); reconnecting", reason_code)


__all__ = ["IoTHubDeviceClient", "Message"]
