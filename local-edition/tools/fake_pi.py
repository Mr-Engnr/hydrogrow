#!/usr/bin/env python3
"""
fake_pi.py: publishes realistic HydroGrow telemetry to the broker so the whole
stack can be tested without the Pi. Payloads follow docs/PAYLOAD_CONTRACT.md
exactly (same keys, casing, scales) with one extra field, source: "fake", so
the dashboard badge never shows synthetic data as Live.

Usage:
  python fake_pi.py                      # every 5 s forever to $MQTT_HOST:$MQTT_PORT (127.0.0.1:1883)
  python fake_pi.py --interval 2 --count 50
  python fake_pi.py --host <pi-hostname>.local --scenario low_ec
  python fake_pi.py --error-every 10     # every 10th frame is a validation-failed error frame

Scenarios: healthy (default), low_ec, high_ph, low_water, diseased, flaky_dht
"""

import argparse
import json
import math
import os
import random
import socket
import sys
import threading
import time
from datetime import datetime, timezone, date

import paho.mqtt.client as mqtt

TOTAL_BOX_DEPTH = 11.8          # from main.py
LEVEL_LOW_DISTANCE = 3.0
PLANTING_DATE = date(2026, 6, 1)
PHASE_TARGET_ML = {"Germination": 0.0, "Seedling": 50.0, "Vegetative": 100.0,
                   "Mature": 140.0, "Harvest Ready": 0.0}


def growth(today=None):
    today = today or date.today()
    actual = max(1, (today - PLANTING_DATE).days + 1)
    model = max(1, min(round(actual * 1.5), 60))
    if model <= 7: phase = "Germination"
    elif model <= 14: phase = "Seedling"
    elif model <= 35: phase = "Vegetative"
    elif model <= 52: phase = "Mature"
    else: phase = "Harvest Ready"
    return actual, model, phase


class Sim:
    """Slow random walk around a scenario's set-points."""

    def __init__(self, scenario, seed=None):
        self.rng = random.Random(seed)
        self.t = 0
        base = dict(ph=6.1, ec=1.45, temp=24.0, hum=61.0, dist=2.3)
        if scenario == "low_ec":     base.update(ec=0.95)
        if scenario == "high_ph":    base.update(ph=7.1)
        if scenario == "low_water":  base.update(dist=3.6)
        self.base = base
        self.scenario = scenario
        self.state = dict(base)
        self.nut_b_dosed_ml = 41.0

    def step(self):
        self.t += 1
        r = self.rng
        s = self.state
        for k, sigma, pull in (("ph", 0.02, 0.05), ("ec", 0.01, 0.05),
                               ("temp", 0.08, 0.05), ("hum", 0.4, 0.05), ("dist", 0.03, 0.05)):
            s[k] += r.gauss(0, sigma) + (self.base[k] - s[k]) * pull
        s["temp"] += 0.3 * math.sin(self.t / 40)        # gentle daily-ish swing
        return s

    def frame(self, error=False, flaky=False):
        s = self.step()
        ph = round(s["ph"], 2)
        ec = round(max(s["ec"], 0.0), 3)
        tds = round(ec * 500.0, 1)
        temp = None if flaky else round(s["temp"], 1)
        hum = None if flaky else round(s["hum"], 1)
        dist = round(max(s["dist"], 0.6), 2)
        level_cm = max(TOTAL_BOX_DEPTH - dist, 0.0)
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%d_%H%M%S")

        f = {
            "temperature": temp,
            "humidity": hum,
            "pH": ph,
            "ec": ec,
            "tds": tds,
            "water_level": dist,
            "water_level_cm": round(level_cm, 2),
            "water_level_pct": round(level_cm / TOTAL_BOX_DEPTH * 100, 1),
            "water_low": dist >= LEVEL_LOW_DISTANCE,
            "timestamp": now.isoformat(),
        }

        if error:
            f.update({
                "image": f"{stamp}.jpg",
                "status": "validation failed",
                "disease_predictions": {"plant1": None, "plant2": None, "plant3": None},
                "nutrient_status": None,
                "dosing": None,
                "source": "fake",
            })
            return f

        actual, model, phase = growth()
        f.update({
            "growth_day_actual": actual,
            "growth_day_model": model,
            "growth_phase": phase,
            "harvest_flush": actual >= 37,
            "image": f"{stamp}.jpg",
            "status": "ok",
        })

        # disease: 0-1 scale, plant3 always None
        if self.scenario == "diseased":
            p2 = {"label": "Bacterial", "confidence": round(self.rng.uniform(0.78, 0.93), 4)}
        else:
            p2 = {"label": "Healthy", "confidence": round(self.rng.uniform(0.90, 0.99), 4)}
        f["disease_predictions"] = {
            "plant1": {"label": "Healthy", "confidence": round(self.rng.uniform(0.93, 0.995), 4)},
            "plant2": p2,
            "plant3": None,
        }

        # nutrient: 0-100 scale, None when DHT is down (model needs temp/hum)
        if flaky:
            f["nutrient_status"] = None
            label, conf = None, None
        else:
            if ec < 1.2:
                label = self.rng.choice(["Nitrogen_Deficient", "Potassium_Deficient"])
                conf = round(self.rng.uniform(72.0, 91.0), 1)
            else:
                label, conf = "Healthy", round(self.rng.uniform(88.0, 99.0), 1)
            f["nutrient_status"] = {"label": label, "confidence": conf}

        # dosing, same shapes as dose_nutrient_a / dose_nutrient_b
        if f["harvest_flush"]:
            dose_a = {"dosed": False, "reason": f"harvest flush (day {actual})"}
            dose_b = {"dosed": False, "reason": f"harvest flush (day {actual})"}
        else:
            dose_a = {"dosed": False, "reason": None, "burst_s": 0, "ec": ec,
                      "label": None, "confidence": None}
            if ec >= 1.8:
                dose_a["reason"] = f"EC {ec} >= safety cutoff 1.8; holding"
            elif ec >= 1.2:
                dose_a["reason"] = f"EC {ec} in range (>= 1.2); no dose needed"
            else:
                dose_a.update(label=label, confidence=conf)
                if label and label != "Healthy" and conf is not None and conf >= 70:
                    burst = 2 if ec >= 1.1 else 3 if ec >= 0.8 else 4
                    dose_a.update(dosed=True, burst_s=burst,
                                  reason=f"dosed {burst}s (EC {ec}, {label} @ {conf}%)")
                else:
                    dose_a["reason"] = f"model says '{label}' (not deficient); holding"
            target = PHASE_TARGET_ML[phase]
            dose_b = {"dosed": False, "reason": None, "burst_s": 0, "phase": phase,
                      "target_ml": round(target, 1), "dosed_ml": round(self.nut_b_dosed_ml, 1)}
            if target <= 0:
                dose_b["reason"] = f"{phase}: no Nutrient B needed"
            else:
                dose_b["reason"] = f"next Nutrient B in {self.rng.uniform(1.0, 23.5):.1f}h"
        f["dosing"] = {"nutrient_a": dose_a, "nutrient_b": dose_b}
        f["source"] = "fake"
        return f


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.getenv("MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    ap.add_argument("--topic", default=os.getenv("MQTT_TOPIC", "hydrogrow/telemetry"))
    ap.add_argument("--user", default=os.getenv("MQTT_USER") or None)
    ap.add_argument("--password", default=os.getenv("MQTT_PASS") or None)
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between frames")
    ap.add_argument("--count", type=int, default=0, help="stop after N frames (0 = forever)")
    ap.add_argument("--scenario", default="healthy",
                    choices=["healthy", "low_ec", "high_ph", "low_water", "diseased", "flaky_dht"])
    ap.add_argument("--error-every", type=int, default=0, help="every Nth frame is an error frame")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--print", action="store_true", help="print each payload")
    a = ap.parse_args()

    sim = Sim(a.scenario, a.seed)
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"fake-pi-{os.getpid()}")
    if a.user:
        client.username_pw_set(a.user, a.password)
    client.reconnect_delay_set(1, 10)
    connected = threading.Event()
    client.on_connect = lambda c, u, flags, rc, props=None: connected.set() if rc == 0 else None
    try:
        client.connect(a.host, a.port, keepalive=30)
    except (OSError, socket.gaierror, ConnectionRefusedError, TimeoutError) as e:
        print(f"fake_pi: cannot reach MQTT broker at {a.host}:{a.port} ({e.__class__.__name__}: {e})",
              file=sys.stderr)
        print("fake_pi: is the broker running? On a laptop: `node tools/dev_broker.js`. "
              "Override with --host/--port or MQTT_HOST/MQTT_PORT.", file=sys.stderr)
        return 2
    client.loop_start()
    if not connected.wait(timeout=10):
        client.loop_stop()
        print(f"fake_pi: broker at {a.host}:{a.port} accepted the TCP connection but did not answer "
              "CONNECT within 10 s (wrong port, auth required, or not an MQTT broker?)", file=sys.stderr)
        return 2
    print(f"fake_pi -> mqtt://{a.host}:{a.port} {a.topic} every {a.interval}s scenario={a.scenario}", flush=True)

    n = 0
    try:
        while a.count == 0 or n < a.count:
            n += 1
            is_err = a.error_every and n % a.error_every == 0
            flaky = a.scenario == "flaky_dht" and n % 3 == 0
            payload = sim.frame(error=is_err, flaky=flaky)
            body = json.dumps(payload)
            info = client.publish(a.topic, body, qos=1)
            info.wait_for_publish(timeout=10)
            tag = "ERR " if is_err else ""
            print(f"[{n}] {tag}pH={payload['pH']} ec={payload['ec']} temp={payload['temperature']} "
                  f"lvl={payload['water_level_pct']}% published={info.is_published()}", flush=True)
            if a.print:
                print(body, flush=True)
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
