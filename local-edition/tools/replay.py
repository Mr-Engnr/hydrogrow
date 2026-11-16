#!/usr/bin/env python3
"""
replay.py: demo mode. Re-publishes recorded Pi telemetry to the broker so the
dashboard / twins / analytics show real historical readings when the live rig
is unavailable. Every frame is tagged source: "replay" so the badge shows
"Demo Mode", never "Live".

Input formats (auto-detected):
  * a directory of Azure blob dumps:  YYYYMMDD_HHMMSS_us.json  (one payload each)
  * a .jsonl file: one payload per line
  * a .json file holding a list of payloads
  * a .json file holding a single payload (looped)

Usage:
  python replay.py recordings/          # all frames, 5 s apart, loop forever
  python replay.py pi_logs.jsonl --interval 2 --once
  python replay.py recordings/ --keep-timestamps   # don't rewrite "timestamp"

Env (same as every other component): MQTT_HOST (127.0.0.1), MQTT_PORT (1883),
MQTT_TOPIC (hydrogrow/telemetry), MQTT_USER, MQTT_PASS, REPLAY_INTERVAL_S (5).
"""
import argparse
import json
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

BLOB_RE = re.compile(r"^\d{8}_\d{6}_\d+\.json$")


def load_frames(src: Path):
    frames = []
    if src.is_dir():
        files = sorted(p for p in src.iterdir() if BLOB_RE.match(p.name)) or sorted(src.glob("*.json"))
        for p in files:
            try:
                frames.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"replay: skipping {p.name}: {e}", file=sys.stderr)
    elif src.suffix == ".jsonl":
        for i, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                frames.append(json.loads(line))
            except Exception as e:
                print(f"replay: skipping line {i}: {e}", file=sys.stderr)
    else:
        data = json.loads(src.read_text(encoding="utf-8"))
        frames = data if isinstance(data, list) else [data]
    return [f for f in frames if isinstance(f, dict)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="directory of *.json blobs, a .jsonl file, or a .json file")
    ap.add_argument("--host", default=os.getenv("MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    ap.add_argument("--topic", default=os.getenv("MQTT_TOPIC", "hydrogrow/telemetry"))
    ap.add_argument("--user", default=os.getenv("MQTT_USER") or None)
    ap.add_argument("--password", default=os.getenv("MQTT_PASS") or None)
    ap.add_argument("--interval", type=float, default=float(os.getenv("REPLAY_INTERVAL_S", "5")),
                    help="seconds between frames (default 5, or REPLAY_INTERVAL_S)")
    ap.add_argument("--once", action="store_true", help="play the set once instead of looping")
    ap.add_argument("--keep-timestamps", action="store_true",
                    help="leave the recorded 'timestamp' alone (default: rewrite to now so charts look live)")
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args()

    src = Path(a.source)
    if not src.exists():
        print(f"replay: {src} does not exist", file=sys.stderr)
        return 2
    frames = load_frames(src)
    if not frames:
        print(f"replay: no usable JSON payloads found in {src}", file=sys.stderr)
        return 2

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"replay-{os.getpid()}")
    if a.user:
        client.username_pw_set(a.user, a.password)
    client.reconnect_delay_set(1, 10)
    connected = threading.Event()
    client.on_connect = lambda c, u, flags, rc, props=None: connected.set() if rc == 0 else None
    try:
        client.connect(a.host, a.port, keepalive=30)
    except (OSError, socket.gaierror, ConnectionRefusedError, TimeoutError) as e:
        print(f"replay: cannot reach MQTT broker at {a.host}:{a.port} ({e.__class__.__name__}: {e})",
              file=sys.stderr)
        print("replay: is the broker running? Override with --host/--port or MQTT_HOST/MQTT_PORT.",
              file=sys.stderr)
        return 2
    client.loop_start()
    if not connected.wait(timeout=10):
        client.loop_stop()
        print(f"replay: broker at {a.host}:{a.port} did not answer CONNECT within 10 s", file=sys.stderr)
        return 2
    mode = "once" if a.once else "looping"
    print(f"replay -> mqtt://{a.host}:{a.port} {a.topic} {len(frames)} frames every {a.interval}s {mode}",
          flush=True)

    n = 0
    try:
        while True:
            for frame in frames:
                n += 1
                payload = dict(frame)
                payload["source"] = "replay"
                if not a.keep_timestamps:
                    payload["recorded_timestamp"] = payload.get("timestamp")
                    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
                body = json.dumps(payload)
                info = client.publish(a.topic, body, qos=1)
                info.wait_for_publish(timeout=10)
                print(f"[{n}] pH={payload.get('pH', payload.get('ph'))} ec={payload.get('ec')} "
                      f"temp={payload.get('temperature')} status={payload.get('status')} "
                      f"published={info.is_published()}", flush=True)
                if a.print:
                    print(body, flush=True)
                time.sleep(a.interval)
            if a.once:
                break
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
