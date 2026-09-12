#!/usr/bin/env python3
"""
HydroGrow — Smart Lettuce Hydroponic System Controller

Hardware map:
  ADS1115  (I2C 0x48)  — pH on A3, TDS on A1
  OLED     (I2C 0x3C)  — SSD1106/SH1106 128x64
  pH       PH4502C     — 5V, analog Po → A3
  TDS      Gravity V1  — 3.3V, analog A → A1
  DHT22                — GPIO4 (Pin 7), 10kΩ pull-up
  HC-SR04              — TRIG GPIO23, ECHO GPIO24 (1kΩ+2kΩ divider)
  Relay    4-CH active LOW:
    IN1 GPIO17 (Pin 11) → Pump A — Nutrient A
    IN2 GPIO27 (Pin 13) → Pump B — Nutrient B
    IN3 GPIO22 (Pin 15) → Pump C — Water
"""

import os
import sys
import json
import time
import logging
import math
from datetime import datetime
from typing import Optional, Tuple

import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_dht

# ── Optional: OLED via luma.oled ─────────────────────────
try:
    from luma.core.interface.serial import i2c as luma_i2c
    from luma.oled.device import sh1106
    from luma.core.render import canvas as luma_canvas
    OLED_OK = True
except ImportError:
    OLED_OK = False

# ── Optional: Azure IoT Hub ───────────────────────────────
try:
    from azure.iot.device import IoTHubDeviceClient, Message
    AZURE_OK = True
except ImportError:
    AZURE_OK = False

# ── Optional: ML models (existing pipeline) ───────────────
try:
    from models.pi_inference import predict_nutrient_status
    ML_OK = True
except ImportError:
    ML_OK = False

# ── Optional: Pi Camera ───────────────────────────────────
try:
    from picamera2 import Picamera2
    CAM_OK = True
except ImportError:
    CAM_OK = False


# ═══════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════

# GPIO
PIN_PUMP_A  = 17    # Nutrient A
PIN_PUMP_B  = 27    # Nutrient B
PIN_PUMP_C  = 22    # Water
PIN_TRIG    = 23    # HC-SR04 trigger
PIN_ECHO    = 24    # HC-SR04 echo (via voltage divider)
PIN_DHT22   = 4     # DHT22 data

# ADS1115 channels
CH_PH  = 3          # A3
CH_TDS = 1          # A1

# ── Lettuce optimal parameters ────────────────────────────
# Source: standard NFT/DWC lettuce cultivation guidelines
LETTUCE = dict(
    ph_min        = 5.5,
    ph_max        = 6.5,
    ph_ideal      = 6.0,
    ec_min        = 0.8,    # mS/cm  (~400 ppm)
    ec_max        = 2.0,    # mS/cm  (~1000 ppm)
    ec_ideal      = 1.4,    # mS/cm  (~700 ppm)
    temp_air_min  = 15.0,   # °C
    temp_air_max  = 26.0,
    humid_min     = 40.0,   # %
    humid_max     = 80.0,
    # HC-SR04: distance from sensor DOWN to water surface
    # smaller = more water (sensor closer to water)
    wl_full_cm    = 3.0,    # cm when tank is full
    wl_low_cm     = 12.0,   # cm — start topping up
    wl_critical_cm= 20.0,   # cm — emergency fill
    wl_max_cm     = 30.0,   # cm — sensor distance to empty tank bottom
)

# ── Pump dosing ───────────────────────────────────────────
DOSE = dict(
    nutrient_a_sec = 3,     # seconds per dose of Nutrient A
    nutrient_b_sec = 3,     # seconds per dose of Nutrient B
    water_sec      = 8,     # seconds per dose of water
    ab_gap_sec     = 5,     # gap between A and B doses
    post_wait_sec  = 90,    # wait after dosing before re-reading
    min_gap_sec    = 300,   # minimum 5 min between doses of same pump
    max_per_hour   = 4,     # safety: max doses per pump per hour
)

# ── System timing ─────────────────────────────────────────
T_READ    = 15      # sensor read every N seconds
T_CONTROL = 120     # control decision every N seconds
T_OLED    = 5       # OLED refresh every N seconds
T_LOG     = 60      # write JSON log every N seconds

# ── Azure (uses env var if set) ───────────────────────────
IOTHUB_CONN = os.getenv("IOTHUB_CONNECTION_STRING", "")

# ── File paths ────────────────────────────────────────────
DATA_DIR     = os.getenv("HYDROGROW_DATA_DIR", os.path.expanduser("~"))
LOG_FILE     = os.path.join(DATA_DIR, "hydrogrow.log")
DATA_FILE    = os.path.join(DATA_DIR, "hydrogrow_data.json")
ACTIONS_FILE = os.path.join(DATA_DIR, "hydrogrow_actions.json")
CAM_PATH     = os.path.join(DATA_DIR, "cam_{}.jpg")


# ═══════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("HydroGrow")


# ═══════════════════════════════════════════════════════════
#  SENSOR READER
# ═══════════════════════════════════════════════════════════

class SensorReader:
    """Reads pH, TDS/EC, DHT22, HC-SR04 with validation."""

    def __init__(self):
        # I2C bus
        self.i2c = busio.I2C(board.SCL, board.SDA)

        # ADS1115
        self.ads = ADS.ADS1115(self.i2c)
        self.ads.gain = 1           # ±4.096 V range
        self.ph_ch  = AnalogIn(self.ads, CH_PH)
        self.tds_ch = AnalogIn(self.ads, CH_TDS)

        # DHT22
        self.dht = adafruit_dht.DHT22(board.D4, use_pulseio=False)

        # HC-SR04
        GPIO.setup(PIN_TRIG, GPIO.OUT)
        GPIO.setup(PIN_ECHO, GPIO.IN)
        GPIO.output(PIN_TRIG, GPIO.LOW)
        time.sleep(0.3)

        log.info("SensorReader ready")

    # ── pH ────────────────────────────────────────────────
    def read_ph(self, n: int = 10) -> Optional[float]:
        """
        Average n samples from PH4502C.
        PH4502C calibration: 7 pH → 2.5 V, slope 0.18 V/pH.
        Returns None on error.
        """
        try:
            voltages = []
            for _ in range(n):
                voltages.append(self.ph_ch.voltage)
                time.sleep(0.05)

            # Discard outliers (min/max of n≥5)
            if len(voltages) >= 5:
                voltages = sorted(voltages)[1:-1]

            avg_v = sum(voltages) / len(voltages)
            ph = 7.0 + (2.5 - avg_v) / 0.18
            ph = round(max(0.0, min(14.0, ph)), 2)
            return ph

        except Exception as e:
            log.error(f"pH read error: {e}")
            return None

    # ── TDS / EC ──────────────────────────────────────────
    def read_tds(self, water_temp: float = 25.0,
                 n: int = 10) -> Tuple[Optional[float], Optional[float]]:
        """
        Returns (tds_ppm, ec_mScm) with temperature compensation.
        Gravity TDS V1.0 formula, 3.3 V reference.
        Returns (None, None) on error.
        """
        try:
            voltages = []
            for _ in range(n):
                voltages.append(self.tds_ch.voltage)
                time.sleep(0.05)

            if len(voltages) >= 5:
                voltages = sorted(voltages)[1:-1]

            avg_v = sum(voltages) / len(voltages)

            # Temperature compensation (NTC, 2% per °C deviation from 25°C)
            comp = 1.0 + 0.02 * (water_temp - 25.0)
            v_comp = avg_v / comp

            # Gravity V1.0 polynomial
            tds_ppm = (
                133.42 * v_comp**3
                - 255.86 * v_comp**2
                + 857.39 * v_comp
            ) * 0.5
            tds_ppm = max(0.0, round(tds_ppm, 1))

            # EC: TDS(ppm) / 500 → mS/cm (KCl equivalent)
            ec = round(tds_ppm / 500.0, 2)
            return tds_ppm, ec

        except Exception as e:
            log.error(f"TDS read error: {e}")
            return None, None

    # ── DHT22 ─────────────────────────────────────────────
    def read_dht22(self, retries: int = 3) -> Tuple[Optional[float], Optional[float]]:
        """
        Returns (temperature_C, humidity_%) with retry.
        DHT22 sometimes gives RuntimeError on first read — handled.
        """
        for attempt in range(retries):
            try:
                temp = self.dht.temperature
                hum  = self.dht.humidity
                if temp is not None and hum is not None:
                    if -10.0 <= temp <= 60.0 and 0.0 <= hum <= 100.0:
                        return round(temp, 1), round(hum, 1)
                    else:
                        log.warning(f"DHT22 out-of-range: T={temp} H={hum}")
            except RuntimeError as e:
                log.debug(f"DHT22 attempt {attempt+1}: {e}")
                time.sleep(2.0)   # DHT22 needs 2s between reads
            except Exception as e:
                log.error(f"DHT22 fatal: {e}")
                return None, None
        return None, None

    # ── HC-SR04 ───────────────────────────────────────────
    def read_distance(self, retries: int = 3) -> Optional[float]:
        """
        Returns distance in cm from sensor to water surface.
        Lower value = more water.
        5 cm burst average is taken for stability.
        """
        readings = []
        for attempt in range(retries + 2):   # extra attempts for averaging
            try:
                # Trigger pulse (10 µs)
                GPIO.output(PIN_TRIG, GPIO.HIGH)
                time.sleep(0.00001)
                GPIO.output(PIN_TRIG, GPIO.LOW)

                t_out = time.time() + 0.05   # 50 ms timeout

                # Wait for echo start
                t_start = time.time()
                while GPIO.input(PIN_ECHO) == 0:
                    t_start = time.time()
                    if time.time() > t_out:
                        raise TimeoutError("ECHO start")

                # Wait for echo end
                t_end = time.time()
                while GPIO.input(PIN_ECHO) == 1:
                    t_end = time.time()
                    if time.time() > t_out + 0.05:
                        raise TimeoutError("ECHO end")

                duration = t_end - t_start
                dist = (duration * 34300) / 2.0   # speed of sound 343 m/s

                if 2.0 <= dist <= 400.0:
                    readings.append(dist)
                    if len(readings) >= 3:
                        break

            except TimeoutError as e:
                log.debug(f"HC-SR04 timeout: {e}")
            except Exception as e:
                log.warning(f"HC-SR04 attempt {attempt+1}: {e}")

            time.sleep(0.06)

        if readings:
            # Return median of collected readings
            readings.sort()
            return round(readings[len(readings) // 2], 1)
        return None

    # ── Water level as percentage ─────────────────────────
    def distance_to_level_pct(self, dist_cm: Optional[float]) -> Optional[float]:
        """Convert HC-SR04 distance → water level 0-100%."""
        if dist_cm is None:
            return None
        full  = LETTUCE["wl_full_cm"]
        empty = LETTUCE["wl_max_cm"]
        pct = (empty - dist_cm) / (empty - full) * 100.0
        return round(max(0.0, min(100.0, pct)), 1)

    # ── Read all ──────────────────────────────────────────
    def read_all(self) -> dict:
        """Single call to read every sensor. Returns unified dict."""
        air_temp, humidity = self.read_dht22()
        wtemp = air_temp if air_temp else 25.0   # use air temp as proxy

        tds_ppm, ec = self.read_tds(water_temp=wtemp)
        dist = self.read_distance()

        return {
            "timestamp":      datetime.utcnow().isoformat() + "Z",
            "ph":             self.read_ph(),
            "ec":             ec,
            "tds_ppm":        tds_ppm,
            "air_temp":       air_temp,
            "humidity":       humidity,
            "water_level_cm": dist,
            "water_level_pct": self.distance_to_level_pct(dist),
        }


# ═══════════════════════════════════════════════════════════
#  PUMP CONTROLLER
# ═══════════════════════════════════════════════════════════

class PumpController:
    """
    Controls 3 pumps via 4-channel relay.
    Relay is ACTIVE LOW: GPIO.LOW = pump ON, GPIO.HIGH = pump OFF.
    Safety: min gap between doses, max doses/hour, no simultaneous run.
    """

    PUMPS = {
        "A": PIN_PUMP_A,
        "B": PIN_PUMP_B,
        "C": PIN_PUMP_C,
    }
    LABELS = {
        PIN_PUMP_A: "Nutrient-A",
        PIN_PUMP_B: "Nutrient-B",
        PIN_PUMP_C: "Water",
    }

    def __init__(self):
        pins = list(self.PUMPS.values())
        GPIO.setup(pins, GPIO.OUT, initial=GPIO.HIGH)   # all OFF at start
        self._last_time  = {p: 0.0  for p in pins}
        self._dose_count = {p: 0    for p in pins}
        self._running    = False
        self._hourly_reset = time.time()
        log.info("PumpController ready — all pumps OFF")

    # ── Safety gate ───────────────────────────────────────
    def _safe(self, pin: int) -> bool:
        if self._running:
            log.warning("Pump blocked — another pump is running")
            return False

        elapsed = time.time() - self._last_time[pin]
        if elapsed < DOSE["min_gap_sec"]:
            rem = int(DOSE["min_gap_sec"] - elapsed)
            log.warning(f"{self.LABELS[pin]} cooldown: {rem}s remaining")
            return False

        if self._dose_count[pin] >= DOSE["max_per_hour"]:
            log.error(
                f"{self.LABELS[pin]} reached max {DOSE['max_per_hour']} doses/hr — "
                "check system manually!"
            )
            return False

        return True

    # ── Core run ─────────────────────────────────────────
    def _run(self, pin: int, seconds: float) -> bool:
        if not self._safe(pin):
            return False
        try:
            self._running = True
            label = self.LABELS[pin]
            log.info(f"[PUMP] {label} ON for {seconds}s")
            GPIO.output(pin, GPIO.LOW)          # ON (active LOW)
            time.sleep(seconds)
            GPIO.output(pin, GPIO.HIGH)         # OFF
            log.info(f"[PUMP] {label} OFF")
            self._last_time[pin]  = time.time()
            self._dose_count[pin] += 1
            return True
        except Exception as e:
            GPIO.output(pin, GPIO.HIGH)         # Safety OFF
            log.error(f"Pump error ({self.LABELS[pin]}): {e}")
            return False
        finally:
            self._running = False

    # ── Public pump methods ───────────────────────────────
    def nutrient_a(self) -> bool:
        return self._run(PIN_PUMP_A, DOSE["nutrient_a_sec"])

    def nutrient_b(self) -> bool:
        return self._run(PIN_PUMP_B, DOSE["nutrient_b_sec"])

    def water(self) -> bool:
        return self._run(PIN_PUMP_C, DOSE["water_sec"])

    def nutrients_ab(self) -> bool:
        """Dose A then wait briefly then dose B."""
        ok_a = self.nutrient_a()
        if ok_a:
            time.sleep(DOSE["ab_gap_sec"])
            ok_b = self.nutrient_b()
            return ok_a and ok_b
        return False

    # ── Hourly reset ──────────────────────────────────────
    def tick_reset(self):
        if time.time() - self._hourly_reset >= 3600:
            for p in self._dose_count:
                self._dose_count[p] = 0
            self._hourly_reset = time.time()
            log.info("Dose counters reset (1-hour cycle)")

    # ── Emergency stop ────────────────────────────────────
    def all_off(self):
        GPIO.output(list(self.PUMPS.values()), GPIO.HIGH)
        self._running = False
        log.warning("ALL PUMPS OFF (emergency stop)")

    # ── Status ────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "doses_this_hour": dict(zip(
                ["nutrient_a", "nutrient_b", "water"],
                [self._dose_count[PIN_PUMP_A],
                 self._dose_count[PIN_PUMP_B],
                 self._dose_count[PIN_PUMP_C]]
            )),
            "pump_running": self._running,
        }


# ═══════════════════════════════════════════════════════════
#  OLED DISPLAY
# ═══════════════════════════════════════════════════════════

class Display:
    """SH1106/SSD1106 128×64 OLED via luma.oled. Fails gracefully."""

    def __init__(self):
        self.dev = None
        if not OLED_OK:
            log.warning("luma.oled not installed — OLED disabled")
            return
        try:
            serial = luma_i2c(port=1, address=0x3C)
            self.dev = sh1106(serial)
            log.info("OLED ready (SH1106 128×64)")
        except Exception as e:
            log.error(f"OLED init failed: {e}")

    def _draw(self, fn):
        if not self.dev:
            return
        try:
            with luma_canvas(self.dev) as d:
                fn(d)
        except Exception as e:
            log.debug(f"OLED draw error: {e}")

    def sensors(self, data: dict, action: str = ""):
        """Show live sensor values."""
        def _fn(d):
            # Header
            d.text((0, 0),  "── HydroGrow ──", fill="white")
            # Values
            ph  = f"{data['ph']:.2f}"  if data.get("ph")  is not None else "---"
            ec  = f"{data['ec']:.2f}"  if data.get("ec")  is not None else "---"
            tmp = f"{data['air_temp']:.1f}" if data.get("air_temp") is not None else "---"
            hum = f"{data['humidity']:.0f}" if data.get("humidity") is not None else "---"
            wlp = f"{data['water_level_pct']:.0f}%" if data.get("water_level_pct") is not None else "---"

            d.text((0, 12), f"pH:{ph:>6}  EC:{ec:>5}mS", fill="white")
            d.text((0, 24), f"T :{tmp:>5}C  H:{hum:>4}%", fill="white")
            d.text((0, 36), f"Water level: {wlp:>5}", fill="white")
            d.text((0, 48), f"{datetime.now():%H:%M:%S}", fill="white")
            if action:
                d.text((70, 48), action[:10], fill="white")
        self._draw(_fn)

    def message(self, lines: list):
        def _fn(d):
            for i, line in enumerate(lines[:5]):
                d.text((0, i * 12), str(line)[:21], fill="white")
        self._draw(_fn)

    def alert(self, title: str, body: str):
        def _fn(d):
            d.rectangle([(0, 0), (127, 63)], outline="white")
            d.text((4, 4),  f"! {title} !", fill="white")
            d.text((4, 20), body[:20],       fill="white")
            d.text((4, 36), datetime.now().strftime("%H:%M:%S"), fill="white")
        self._draw(_fn)


# ═══════════════════════════════════════════════════════════
#  HYDROPONIC DECISION ENGINE
# ═══════════════════════════════════════════════════════════

class HydroController:
    """
    Reads sensors, decides actions, controls pumps, displays status.
    Control priority for lettuce:
      1. Water level  — critical first
      2. EC level     — nutrients if low, dilute if high
      3. pH level     — small nutrient dose if high, dilute if low
      4. Alerts only  — temperature, humidity
    """

    def __init__(self):
        self.sensors  = SensorReader()
        self.pumps    = PumpController()
        self.display  = Display()

        self._last_read    = 0.0
        self._last_control = 0.0
        self._last_oled    = 0.0
        self._last_log     = 0.0
        self._latest       = {}
        self._actions      = []        # rolling 20-entry action log
        self._errors       = 0
        self._MAX_ERRORS   = 10

        # Azure IoT Hub
        self._iot = None
        if AZURE_OK and IOTHUB_CONN:
            try:
                self._iot = IoTHubDeviceClient.create_from_connection_string(IOTHUB_CONN)
                self._iot.connect()
                log.info("Azure IoT Hub connected")
            except Exception as e:
                log.error(f"Azure IoT: {e}")

        # Announce startup
        log.info("=" * 52)
        log.info("  HydroGrow Controller v1.0 — LETTUCE MODE")
        log.info(f"  pH  target : {LETTUCE['ph_min']} – {LETTUCE['ph_max']}")
        log.info(f"  EC  target : {LETTUCE['ec_min']} – {LETTUCE['ec_max']} mS/cm")
        log.info(f"  Temp target: {LETTUCE['temp_air_min']} – {LETTUCE['temp_air_max']} °C")
        log.info("=" * 52)
        self.display.message(["HydroGrow v1.0", "Crop: Lettuce", "Booting up...", ""])

    # ── Sensor stage ──────────────────────────────────────
    def _read(self) -> dict:
        try:
            data = self.sensors.read_all()
            self._latest = data
            self._errors = 0
            return data
        except Exception as e:
            self._errors += 1
            log.error(f"Sensor error #{self._errors}: {e}")
            if self._errors >= self._MAX_ERRORS:
                log.critical("Sensor errors exceeded limit — safe shutdown")
                self.shutdown()
            return self._latest   # last known good data

    # ── Validate readings ─────────────────────────────────
    @staticmethod
    def _valid(value, lo, hi) -> bool:
        return value is not None and lo <= value <= hi

    # ── Decision engine ───────────────────────────────────
    def _decide(self, d: dict) -> str:
        ph  = d.get("ph")
        ec  = d.get("ec")
        wl  = d.get("water_level_cm")    # cm from sensor to water surface
        tmp = d.get("air_temp")
        hum = d.get("humidity")

        # ── PRIORITY 1: Water level ───────────────────────
        if wl is not None:

            if wl >= LETTUCE["wl_critical_cm"]:
                # Tank critically low
                self.display.alert("WATER LOW", f"Level: {wl}cm — filling")
                log.warning(f"CRITICAL water level {wl}cm — filling")
                if self.pumps.water():
                    return self._act(f"FILL_WATER critical={wl}cm")
                return self._act("FILL_WATER failed (cooldown?)")

            if wl >= LETTUCE["wl_low_cm"]:
                # Water level getting low — top up
                log.info(f"Low water level {wl}cm — topping up")
                if self.pumps.water():
                    time.sleep(DOSE["post_wait_sec"])
                    return self._act(f"TOP_UP_WATER wl={wl}cm")

        # ── PRIORITY 2: EC / Nutrient concentration ───────
        if ec is not None:

            if ec < LETTUCE["ec_min"]:
                # Solution too weak — add nutrients A and B
                deficit = round(LETTUCE["ec_ideal"] - ec, 2)
                log.info(f"Low EC={ec} mS/cm (target {LETTUCE['ec_min']}-{LETTUCE['ec_max']}) — dosing A+B, deficit={deficit}")
                self.display.message([
                    "EC TOO LOW",
                    f"EC: {ec} mS/cm",
                    "Dosing A+B...",
                    f"Target: {LETTUCE['ec_ideal']}",
                ])
                if self.pumps.nutrients_ab():
                    time.sleep(DOSE["post_wait_sec"])
                    return self._act(f"DOSE_NUTRIENTS_AB ec={ec}")

            elif ec > LETTUCE["ec_max"]:
                # Solution too concentrated — dilute with water
                log.info(f"High EC={ec} mS/cm — diluting with water")
                self.display.message([
                    "EC TOO HIGH",
                    f"EC: {ec} mS/cm",
                    "Diluting...",
                ])
                if self.pumps.water():
                    time.sleep(DOSE["post_wait_sec"])
                    return self._act(f"DILUTE_EC ec={ec}")

        # ── PRIORITY 3: pH adjustment ─────────────────────
        if ph is not None:

            if ph > LETTUCE["ph_max"]:
                # pH too alkaline — nutrient solutions are slightly acidic
                # A small dose of Nutrient A helps bring pH down
                log.info(f"pH={ph} too high (>{LETTUCE['ph_max']}) — dosing Nutrient A to lower")
                self.display.message([
                    f"pH HIGH: {ph}",
                    "Target: 5.5–6.5",
                    "Dosing A (acidic)",
                ])
                if self.pumps.nutrient_a():
                    return self._act(f"PH_CORRECT_HIGH ph={ph}")

            elif ph < LETTUCE["ph_min"]:
                # pH too acidic — dilute with plain water
                log.info(f"pH={ph} too low (<{LETTUCE['ph_min']}) — diluting with water")
                self.display.message([
                    f"pH LOW: {ph}",
                    "Target: 5.5–6.5",
                    "Diluting with H2O",
                ])
                if self.pumps.water():
                    return self._act(f"PH_CORRECT_LOW ph={ph}")

        # ── Temperature / humidity alerts (no pump action) ─
        alerts = []
        if tmp is not None:
            if tmp > LETTUCE["temp_air_max"]:
                alerts.append(f"TEMP_HIGH:{tmp}C — lettuce may bolt")
            elif tmp < LETTUCE["temp_air_min"]:
                alerts.append(f"TEMP_LOW:{tmp}C — growth slowing")

        if hum is not None:
            if hum > LETTUCE["humid_max"]:
                alerts.append(f"HUM_HIGH:{hum}% — disease risk")
            elif hum < LETTUCE["humid_min"]:
                alerts.append(f"HUM_LOW:{hum}%")

        for a in alerts:
            log.warning(f"[ALERT] {a}")

        return "MONITOR_OK" if not alerts else " | ".join(alerts)

    # ── ML nutrient inference (optional) ──────────────────
    def _ml_prediction(self, data: dict) -> Optional[str]:
        if not ML_OK:
            return None
        try:
            status = predict_nutrient_status(
                ph=data.get("ph", 6.0),
                ec=data.get("ec", 1.4),
                air_temp=data.get("air_temp", 22.0),
                humidity=data.get("humidity", 60.0),
                water_level=data.get("water_level_pct", 80.0),
            )
            return status
        except Exception as e:
            log.debug(f"ML prediction error: {e}")
            return None

    # ── Camera capture (optional) ─────────────────────────
    def _capture_images(self) -> list:
        if not CAM_OK:
            return []
        paths = []
        try:
            cam = Picamera2()
            cam.start()
            time.sleep(2)
            for i in range(3):
                path = CAM_PATH.format(i + 1)
                cam.capture_file(path)
                paths.append(path)
                log.info(f"Captured {path}")
            cam.stop()
        except Exception as e:
            log.error(f"Camera error: {e}")
        return paths

    # ── Send to Azure ──────────────────────────────────────
    def _send_azure(self, data: dict, action: str, ml_status: Optional[str]):
        if not self._iot:
            return
        try:
            payload = {
                **data,
                "device_id":    "raspberrypi",
                "action":       action,
                "nutrient_status": ml_status or "N/A",
                # Field aliases for dashboard compatibility
                "waterTemp":    data.get("air_temp"),
                "health_status": ml_status or "Healthy",
                "temperature":  data.get("air_temp"),
            }
            msg = Message(json.dumps(payload))
            msg.content_type = "application/json"
            msg.content_encoding = "utf-8"
            self._iot.send_message(msg)
            log.info("Sent → Azure IoT Hub")
        except Exception as e:
            log.error(f"Azure send failed: {e}")

    # ── Write JSON log ────────────────────────────────────
    def _save_local(self, data: dict, action: str):
        try:
            with open(DATA_FILE, "w") as f:
                json.dump({**data, "latest_action": action}, f, indent=2)
        except Exception:
            pass
        try:
            with open(ACTIONS_FILE, "w") as f:
                json.dump(self._actions[-20:], f, indent=2)
        except Exception:
            pass

    # ── Action logger ─────────────────────────────────────
    def _act(self, action: str) -> str:
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
        }
        self._actions.append(entry)
        log.info(f"[ACTION] {action}")
        return action

    # ── Safe shutdown ─────────────────────────────────────
    def shutdown(self):
        log.info("Shutting down HydroGrow safely...")
        self.pumps.all_off()
        self.display.message(["HydroGrow", "SHUTDOWN", "All pumps OFF"])
        if self._iot:
            try:
                self._iot.disconnect()
            except Exception:
                pass
        GPIO.cleanup()
        sys.exit(0)

    # ── Main loop ─────────────────────────────────────────
    def run(self):
        """Continuous control loop."""
        try:
            while True:
                now = time.time()
                self.pumps.tick_reset()

                # ── Read sensors ──────────────────────────
                if now - self._last_read >= T_READ:
                    data = self._read()
                    self._last_read = now

                    # ── OLED update ───────────────────────
                    if now - self._last_oled >= T_OLED:
                        action_label = self._actions[-1]["action"] if self._actions else ""
                        self.display.sensors(data, action_label[:8])
                        self._last_oled = now

                    # ── Control decision ──────────────────
                    if now - self._last_control >= T_CONTROL:
                        ml_status = self._ml_prediction(data)
                        action    = self._decide(data)
                        self._last_control = now

                        self._send_azure(data, action, ml_status)

                        if now - self._last_log >= T_LOG:
                            self._save_local(data, action)
                            self._last_log = now

                        log.info(
                            f"[STATUS] pH={data.get('ph')} EC={data.get('ec')}mS "
                            f"WL={data.get('water_level_cm')}cm T={data.get('air_temp')}C "
                            f"→ {action}"
                        )

                time.sleep(1)

        except KeyboardInterrupt:
            log.info("Ctrl-C received")
            self.shutdown()
        except Exception as e:
            log.critical(f"Fatal: {e}", exc_info=True)
            self.shutdown()


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    ctrl = HydroController()
    ctrl.run()