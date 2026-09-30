#!/usr/bin/env python3
"""
HydroGrow - Production Control Loop (v2.0)
==========================================
30-minute supervisory loop:
  acquire sensors + camera -> validate -> closed-loop water control
  -> publish to Azure IoT Hub -> rotate OLED status -> sleep

Hardware (validated wiring):
  ADS1115  I2C 0x48 : pH=A3 (5V probe), EC/TDS=A1 (3.3V probe)
  OLED     I2C 0x3C : SH1106 128x64
  DHT22    GPIO4    : temp/humidity (10k pull-up)
  HC-SR04  GPIO23 TRIG / GPIO24 ECHO (ECHO via 1k+2k divider)
  Relay1   GPIO22 -> IN3 : water pump   (active)
  Relay2   GPIO17 -> IN1 : nutrient A   (reserved/off)
  Relay3   GPIO27 -> IN2 : nutrient B   (reserved/off)
  Pi Camera (imx219) via picamera2

Run inside venv:  source ~/iot-env/bin/activate && python main.py
Stop cleanly:     Ctrl+C   (relays are forced OFF on exit)
"""

import os
import time
import json
import statistics
from datetime import datetime, timezone

import board
import busio
import RPi.GPIO as GPIO
import adafruit_dht
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# OLED
from luma.core.interface.serial import i2c as luma_i2c
from luma.oled.device import sh1106
from PIL import ImageDraw, ImageFont

# Camera
from picamera2 import Picamera2

# Azure IoT
from azure.iot.device import IoTHubDeviceClient, Message

# ============================================================
# CONFIG
# ============================================================
LOOP_INTERVAL        = 1800     # s  (30 min)
PUMP_POLL_INTERVAL   = 1.0      # s
# --- Water level band (distance to water surface; filling LOWERS the distance) ---
LEVEL_LOW_DISTANCE   = 3.0      # cm  -> at/above this = water too LOW  -> pump ON
LEVEL_TARGET_DISTANCE = 2.0     # cm  -> fill until distance drops to here -> pump OFF
LEVEL_HIGH_DISTANCE  = 1.5      # cm  -> below this = water too HIGH (overfill fault)
PUMP_TIMEOUT         = 300      # s   safety cap on continuous run (5 min - tune after observing real fill time)
DATA_DIR             = os.getenv("HYDROGROW_DATA_DIR", os.path.expanduser("~"))
CAPTURE_DIR          = os.path.join(DATA_DIR, "captures")

# --- Water level geometry (sensor at top, distance = gap to water surface) ---
TOTAL_BOX_DEPTH = 11.8    # cm  empty-box baseline distance (confirmed)
#   water_level_cm = TOTAL_BOX_DEPTH - distance ; pct = level_cm / depth * 100

# --- Nutrient dosing (Pumps B & C) ---
# Optimal lettuce hydroponics (UF/IFAS HS1422; vegetative stage):
#   pH 5.5-6.5, EC 1.2-1.8 mS/cm. Below 1.2 = depletion; above 1.8 = burn risk.
EC_OPTIMAL_LOW   = 1.2    # below this = under-fertilized -> candidate for dosing
EC_OPTIMAL_HIGH  = 1.8    # at/above this = SAFETY CUTOFF, never dose (burn risk)
PH_OPTIMAL_LOW   = 5.5
PH_OPTIMAL_HIGH  = 6.5
DOSE_MIN_CONFIDENCE = 70.0  # % - ignore model predictions below this confidence
# EC-scaled dose tiers: the lower the EC, the bigger the burst (per pump, seconds)
#   1.1 - 1.2  -> 2s   (just under range)
#   0.8 - 1.1  -> 3s   (moderately low)
#   < 0.8      -> 4s   (very weak)  -- hard ceiling, never more
def _dose_seconds(ec):
    if ec >= 1.1:  return 2.0
    if ec >= 0.8:  return 3.0
    return 4.0
DOSE_MIX_PAUSE   = 30     # s  wait between A and B so they don't mix concentrated
# Pump A (Nutrient A, macros N/P/K) dosing requires:
#   EC < 1.2 AND model predicts deficiency AND confidence >= 70%.

# --- Nutrient B (micronutrients + CalMag blend) - SCHEDULE-driven ---
# Pump C bottle is a fixed blend: 400 mL pure-B + 100 mL CalMag (4:1).
# Because it's 80% B-strength, doses scale x1.25 vs pure-B targets to hit
# the same micronutrient concentration. The ML model only detects macro
# (N/P/K) deficiencies, never micros, so Nutrient B runs on a schedule.
TANK_VOLUME_L   = 16.0    # reservoir capacity (litres)
PUMP_FLOW_ML_S  = 1.0     # <-- PLACEHOLDER: 1.0 mL/s (60 mL/min). MEASURE YOURS:
                          #     run Pump C 10s into a cup, mL/10 = real value.
# Per-stage TOTAL Nutrient-B-blend target for the whole 16 L reservoir (mL).
# = (pure-B mL/L * 1.25 blend factor) * 16 L, from the grow table.
NUT_B_TARGET_ML = {
    "Germination":     0.0,   # no nutrients during germination
    "Seedling":       50.0,   # 2.5 mL/L B x1.25 x16L
    "Vegetative":    100.0,   # 5.0 mL/L B x1.25 x16L
    "Mature":        140.0,   # 7.0 mL/L B x1.25 x16L
    "Harvest Ready":   0.0,   # flush window - hold/taper nutrients for clean taste
}
NUT_B_DOSE_INTERVAL_HOURS = 24    # how often Nutrient B is topped up
NUT_B_TOPUP_FRACTION      = 0.10  # add 10% of the remaining gap each scheduled dose
NUT_B_MAX_BURST_S         = 30    # hard ceiling on any single Nutrient B burst (s)
# Harvest flush: stop nutrients in the final days for cleaner-tasting leaves.
# Keyed off REAL calendar day (the model only sees "Mature" past day 35).
HARVEST_FLUSH_START_DAY   = 37    # real day to begin flush (stop dosing)

# --- Disease detection (MobileNetV2) ---
MODEL_PATH    = os.path.join(DATA_DIR, "models", "lettuce_mobilenetv2.h5")
DISEASE_CLASSES = ["Bacterial", "Healthy", "Septoria_blight_on_lettuce"]  # alphabetical
MODEL_INPUT   = (224, 224)        # MobileNetV2 input size
# Which plant holes are actually planted. 3 holes -> A (left), B (right), C (empty)
ACTIVE_PLANTS = {"plant1": True, "plant2": True, "plant3": False}

# --- Nutrient deficiency model (Random Forest, scikit-learn) ---
NUTRIENT_MODEL_PATH = os.path.join(DATA_DIR, "models", "nutrient_model.pkl")
NUTRIENT_FEATURE_ORDER = [
    'pH', 'EC', 'N_Concentration', 'P_Concentration', 'K_Concentration',
    'Air_Temp', 'Humidity', 'Water_Level', 'Growth_Day', 'Treatment_%'
]
TREATMENT_PCT = 100.0   # nutrient solution strength %

# ============================================================
# GROWTH-DAY TRACKING + 40->60 DAY MODEL MAPPING (Task 2)
# ============================================================
# Physical crop: real lettuce reaches harvest in ~40 days.
# ML model: trained on a fixed 60-day lifecycle (immutable, cannot retrain).
# We bridge the two in software so the model always receives the "Growth_Day"
# it expects, while the system tracks true calendar days from a planting date.
import datetime as _dt
PLANTING_DATE = _dt.date(2026, 6, 1)   # <-- Day 1. Change to your real sow date.
REAL_CYCLE_DAYS  = 40                  # physical crop lifecycle
MODEL_CYCLE_DAYS = 60                  # lifecycle the ML model was trained on

def get_actual_day(today=None):
    """Real calendar day of the grow cycle (1-based) from PLANTING_DATE."""
    today = today or _dt.date.today()
    d = (today - PLANTING_DATE).days + 1     # day of planting = day 1
    return max(1, d)                          # never below 1

def get_model_day(actual_day):
    """
    Linear-scale a real day (1..40) into the model's expected day (1..60).
        model_day = actual_day * (60/40) = actual_day * 1.5
    Clamped to the model's valid 1..60 range so it never receives an
    out-of-range day (e.g. if the crop is held past day 40).
    """
    scaled = round(actual_day * (MODEL_CYCLE_DAYS / REAL_CYCLE_DAYS))
    return max(1, min(scaled, MODEL_CYCLE_DAYS))

def get_growth_phase(model_day):
    """
    Model's fixed phase architecture on its 60-day scale (matches training data).
    5 phases: Germination, Seedling, Vegetative, Mature, Harvest Ready.
    """
    if model_day <= 7:   return "Germination"   # 1-7
    if model_day <= 14:  return "Seedling"      # 8-14
    if model_day <= 35:  return "Vegetative"    # 15-35
    if model_day <= 52:  return "Mature"        # 36-52
    return "Harvest Ready"                      # 53-60

# --- Pin map (BCM) ---
RELAY_WATER = 22   # IN3  Relay 1
RELAY_NUT_A = 17   # IN1  Relay 2 (reserved)
RELAY_NUT_B = 27   # IN2  Relay 3 (reserved)
DHT_PIN     = board.D4
TRIG_PIN    = 23
ECHO_PIN    = 24

# --- Relay polarity ---  most SRD boards are ACTIVE-LOW
RELAY_ACTIVE_LOW = True

# --- ADS1115 channels ---
ADS_PH_CH = 3   # A3
ADS_EC_CH = 1   # A1

# --- Calibration constants (REPLACE after 2-point calibration) ---
PH_SLOPE  = -5.70
PH_OFFSET = 21.34
EC_TEMP_COMP = 0.02   # 2% per degC

# --- Azure IoT Hub device connection string ---
IOTHUB_CONN = os.getenv("IOTHUB_CONNECTION_STRING")

# ============================================================
# GLOBALS (hardware handles, set in init)
# ============================================================
dht       = None
ads       = None
ph_in     = None
ec_in     = None
oled      = None
oled_font = None
camera    = None
iot       = None
disease_model = None              # lazy-loaded MobileNetV2 (TensorFlow)
nutrient_model = None              # lazy-loaded Random Forest (joblib)


# ============================================================
# HAL  -  low-level primitives
# ============================================================
def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

def utc_now_compact():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def gpio_write(pin, logical_on):
    """Set relay logical ON/OFF, handling active-low boards."""
    if RELAY_ACTIVE_LOW:
        GPIO.output(pin, GPIO.LOW if logical_on else GPIO.HIGH)
    else:
        GPIO.output(pin, GPIO.HIGH if logical_on else GPIO.LOW)

def relay_all_off():
    for pin in (RELAY_WATER, RELAY_NUT_A, RELAY_NUT_B):
        gpio_write(pin, False)


# ============================================================
# INIT
# ============================================================
def init_system():
    global dht, ads, ph_in, ec_in, oled, oled_font, camera, iot

    # --- GPIO ---
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in (RELAY_WATER, RELAY_NUT_A, RELAY_NUT_B):
        GPIO.setup(pin, GPIO.OUT)
    # SAFETY INVARIANT: relays off before anything else
    relay_all_off()
    GPIO.setup(TRIG_PIN, GPIO.OUT)
    GPIO.setup(ECHO_PIN, GPIO.IN)
    GPIO.output(TRIG_PIN, False)

    # --- I2C / ADS1115 ---
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1                      # +/-4.096 V
    ph_in = AnalogIn(ads, ADS_PH_CH)
    ec_in = AnalogIn(ads, ADS_EC_CH)

    # --- DHT22 ---
    dht = adafruit_dht.DHT22(DHT_PIN, use_pulseio=False)

    # --- OLED ---
    serial = luma_i2c(port=1, address=0x3C)
    oled = sh1106(serial)
    oled_font = ImageFont.load_default()

    # --- Camera (optional - never let it kill the loop) ---
    try:
        camera = Picamera2()
        try:
            cfg = camera.create_still_configuration()
        except Exception:
            cfg = camera.create_preview_configuration()
        camera.configure(cfg)
        camera.start()
        time.sleep(2)                 # sensor warm-up
        log("camera ready")
    except Exception as e:
        camera = None
        log(f"camera init failed ({e}) - continuing without camera")

    # --- Azure IoT Hub ---
    iot = IoTHubDeviceClient.create_from_connection_string(IOTHUB_CONN)
    iot.connect()

    # --- Disease model (optional - never let it kill the loop) ---
    global disease_model
    try:
        from tensorflow.keras.models import load_model
        disease_model = load_model(MODEL_PATH)
        log("disease model loaded")
    except Exception as e:
        disease_model = None
        log(f"disease model load failed ({e}) - disease detection disabled")

    # --- Nutrient model (optional - never let it kill the loop) ---
    global nutrient_model
    try:
        import joblib
        nutrient_model = joblib.load(NUTRIENT_MODEL_PATH)
        log("nutrient model loaded")
    except Exception as e:
        nutrient_model = None
        log(f"nutrient model load failed ({e}) - nutrient prediction disabled")

    os.makedirs(CAPTURE_DIR, exist_ok=True)
    log("init complete")


# ============================================================
# SENSOR SERVICE
# ============================================================
def read_distance_once():
    """Single HC-SR04 measurement in cm, or None on timeout/bad echo."""
    # ensure a clean low before triggering
    GPIO.output(TRIG_PIN, False)
    time.sleep(0.002)
    GPIO.output(TRIG_PIN, True)
    time.sleep(0.00001)               # 10 us trigger pulse
    GPIO.output(TRIG_PIN, False)

    # wait for echo to RISE (start of pulse)
    deadline = time.perf_counter() + 0.03
    while GPIO.input(ECHO_PIN) == 0:
        if time.perf_counter() > deadline:
            return None
    pulse_start = time.perf_counter()

    # wait for echo to FALL (end of pulse)
    deadline = time.perf_counter() + 0.03
    while GPIO.input(ECHO_PIN) == 1:
        if time.perf_counter() > deadline:
            return None
    pulse_end = time.perf_counter()

    elapsed = pulse_end - pulse_start
    distance = (elapsed * 34300) / 2  # cm
    # reject implausibly short echoes (timing glitch, not a real surface)
    if distance < 1.0:
        return None
    return distance

def read_distance_median(n=5):
    """
    Median-of-n with outlier rejection. Tank geometry never legitimately
    exceeds ~20 cm, so anything beyond that is a glitch, not real water level.
    """
    PLAUSIBLE_MIN, PLAUSIBLE_MAX = 0.5, 20.0
    samples = []
    for _ in range(n):
        d = read_distance_once()
        if d is not None and PLAUSIBLE_MIN <= d <= PLAUSIBLE_MAX:
            samples.append(d)
        time.sleep(0.05)
    if not samples:
        return None
    med = statistics.median(samples)
    # second pass: drop any sample that's wildly off the median (glitch reject)
    clean = [s for s in samples if abs(s - med) <= 3.0]
    return round(statistics.median(clean), 2) if clean else round(med, 2)

def read_dht():
    """
    DHT22 is flaky. Strategy:
      - Phase 1: up to 10 quick attempts; return the FIRST read where
        both temp and humidity are valid.
      - If all 10 fail: sleep 2 s, then Phase 2: up to 5 more attempts.
      - If still nothing: give up, return (None, None).
    """
    # Phase 1: 10 quick attempts
    for _ in range(10):
        try:
            t = dht.temperature
            h = dht.humidity
            if t is not None and h is not None:
                return round(t, 1), round(h, 1)
        except RuntimeError:
            pass                       # transient DHT error, keep trying
        time.sleep(0.5)

    # cooldown, then Phase 2: 5 more attempts
    log("DHT22 phase 1 failed, retrying after 2s")
    time.sleep(2)
    for _ in range(5):
        try:
            t = dht.temperature
            h = dht.humidity
            if t is not None and h is not None:
                return round(t, 1), round(h, 1)
        except RuntimeError:
            pass
        time.sleep(0.5)

    log("DHT22 read failed after all retries")
    return None, None

def read_adc_median(channel_in, n=5):
    """Median-of-n ADC voltage read to reject single-sample noise spikes."""
    samples = []
    for _ in range(n):
        try:
            samples.append(channel_in.voltage)
        except Exception:
            pass
        time.sleep(0.02)
    return statistics.median(samples) if samples else None

def convert_ph(voltage):
    if voltage is None:
        return None
    ph = round(PH_SLOPE * voltage + PH_OFFSET, 2)
    # reject chemically implausible readings (sensor noise, not real water)
    if not (2.0 <= ph <= 11.0):
        return None
    return ph

def convert_ec(voltage, temp_c):
    comp = 1.0 + EC_TEMP_COMP * ((temp_c if temp_c else 25.0) - 25.0)
    v = voltage / comp if comp else voltage
    tds = (133.42 * v**3 - 255.86 * v**2 + 857.39 * v) * 0.5
    tds = max(tds, 0.0)
    ec  = tds / 500.0                  # approx mS/cm
    return round(ec, 3), round(tds, 1)

def acquire_all():
    temp, hum = read_dht()
    v_ph = read_adc_median(ph_in)
    v_ec = read_adc_median(ec_in)
    ec, tds = convert_ec(v_ec, temp) if v_ec is not None else (None, None)
    distance = read_distance_median()

    # convert raw distance -> absolute level (cm) and percentage
    if distance is not None:
        level_cm  = max(TOTAL_BOX_DEPTH - distance, 0.0)
        level_pct = round((level_cm / TOTAL_BOX_DEPTH) * 100, 1)
        water_low = distance >= LEVEL_LOW_DISTANCE      # gap too big = low water
    else:
        level_cm = level_pct = None
        water_low = None

    return {
        "temperature":    temp,
        "humidity":       hum,
        "pH":             convert_ph(v_ph),
        "ec":             ec,
        "tds":            tds,
        "water_level":    distance,           # raw distance (cm) - kept for compatibility
        "water_level_cm": round(level_cm, 2) if level_cm is not None else None,
        "water_level_pct": level_pct,         # 0-100 % for dashboard
        "water_low":      water_low,          # bool status flag
        "timestamp":      utc_now_iso(),
    }

def validate(f):
    """
    Frame is valid if the core sensors (pH, EC, water level) are in range.
    DHT22 temp/humidity are allowed to be None (flaky sensor) - if present
    they must be in range, but a missing DHT reading does NOT reject the frame.
    """
    try:
        # DHT fields: only checked when present (None is tolerated)
        if f["temperature"] is not None and not (0 <= f["temperature"] <= 60):
            return False
        if f["humidity"] is not None and not (0 <= f["humidity"] <= 100):
            return False
        # core fields: must be present and in a chemically plausible range
        return all([
            f["pH"] is not None and 2.0 <= f["pH"] <= 11.0,
            f["ec"] is not None and 0 <= f["ec"] <= 5,
            f["water_level"] is not None and 0.5 <= f["water_level"] <= 20.0,
        ])
    except (KeyError, TypeError):
        return False


# ============================================================
# RELAY CONTROL  -  closed-loop water regulation
# ============================================================
class PumpFault(Exception):
    pass

def regulate_water():
    """
    Fill control. Distance to water surface; filling LOWERS the distance.
      distance >= 3.0      -> water too low  -> pump ON
      distance 2.0 - 3.0   -> safe band      -> do nothing
      distance < 1.5       -> water too high -> overfill fault
    While filling, pump until distance drops to LEVEL_TARGET_DISTANCE (2.0).
    Returns ('ok'|'error', info). Pump always OFF on exit.
    Returns ('ok'|'error', info). Pump always OFF on exit.
    """
    level = read_distance_median()
    if level is None:
        return "error", "level sensor fault"

    # below the low threshold -> either safe band or overfilled (no pump)
    if level < LEVEL_LOW_DISTANCE:
        if level < LEVEL_HIGH_DISTANCE:
            return "error", f"water too high ({level} cm) - overfill"
        return "ok", level                       # in safe band

    # level >= 3.0 -> water too low -> fill
    log(f"water low ({level} cm) -> pump ON")
    start = time.time()
    baseline = level          # level when pump started
    rising_strikes = 0        # consecutive "not making progress" reads
    GRACE_PERIOD = 20         # s before fault-checking (slow tank needs time)
    PUMP_RUN     = 15         # s to run the pump before each measurement
    SETTLE_PAUSE = 3          # s pump OFF before reading (let surface settle -
                              #   pump inflow churns the surface & corrupts echo)
    try:
        while True:
            # --- pump a burst ---
            gpio_write(RELAY_WATER, True)
            time.sleep(PUMP_RUN)

            # --- pause and let the water surface settle, THEN measure ---
            gpio_write(RELAY_WATER, False)
            time.sleep(SETTLE_PAUSE)
            level = read_distance_median(n=5)        # still water -> clean read
            if level is None:
                raise PumpFault("echo lost during fill")

            # success: reached target depth (check this first, always)
            if level <= LEVEL_TARGET_DISTANCE:
                log(f"target reached ({level} cm) -> pump OFF")
                return "ok", level

            # overfill fault: dropped below safe band
            if level < LEVEL_HIGH_DISTANCE:
                raise PumpFault(f"overfill ({level} cm)")

            elapsed = time.time() - start
            log(f"filling... {level} cm (baseline {baseline} cm, {int(elapsed)}s elapsed)")

            # only fault-check after grace period (water needs time to move)
            if elapsed > GRACE_PERIOD:
                # not making progress = level not meaningfully below baseline
                # tolerate sensor noise (0.5 cm); require 3 consecutive strikes
                if level > baseline - 0.5:
                    rising_strikes += 1
                    if rising_strikes >= 3:
                        raise PumpFault("no fill progress (pump dry/blocked)")
                else:
                    rising_strikes = 0
                    baseline = level      # progress made, advance baseline

            # safety: hard cap on total run time
            if elapsed > PUMP_TIMEOUT:
                raise PumpFault("fill timeout")
    except PumpFault as e:
        return "error", str(e)
    finally:
        gpio_write(RELAY_WATER, False)           # ALWAYS off

def dose_nutrient_a(frame, nutrient_status):
    """
    Pump B -> Nutrient A (MACROS, N/P/K). MODEL-DRIVEN.
    Fires when ALL hold:
      1. EC < EC_OPTIMAL_LOW (1.2)            - solution genuinely under-range
      2. model predicts a deficiency (any N/P/K, label != 'Healthy')
      3. model confidence >= DOSE_MIN_CONFIDENCE (70%)
    Hard cutoff: EC >= EC_OPTIMAL_HIGH (1.8) never doses.
    Burst size scales with how low EC is (2s/3s/4s).
    """
    result = {"dosed": False, "reason": None, "burst_s": 0,
              "ec": frame.get("ec"), "label": None, "confidence": None}

    ec = frame.get("ec")
    if ec is None:
        result["reason"] = "no EC reading"
        return result
    if ec >= EC_OPTIMAL_HIGH:
        result["reason"] = f"EC {ec} >= safety cutoff {EC_OPTIMAL_HIGH}; holding"
        return result
    if ec >= EC_OPTIMAL_LOW:
        result["reason"] = f"EC {ec} in range (>= {EC_OPTIMAL_LOW}); no dose needed"
        return result

    label = conf = None
    if nutrient_status and isinstance(nutrient_status, dict):
        label = nutrient_status.get("label")
        conf  = nutrient_status.get("confidence")
    result["label"], result["confidence"] = label, conf

    if not label or label == "Healthy":
        result["reason"] = f"model says '{label}' (not deficient); holding"
        return result
    if conf is None or conf < DOSE_MIN_CONFIDENCE:
        result["reason"] = f"confidence {conf} < {DOSE_MIN_CONFIDENCE}%; holding"
        return result

    burst = _dose_seconds(ec)
    result["burst_s"] = burst
    log(f"Nutrient A: EC {ec} low + model '{label}' @ {conf}% -> Pump B {burst}s")
    try:
        gpio_write(RELAY_NUT_A, True)
        time.sleep(burst)
        gpio_write(RELAY_NUT_A, False)
        result.update({"dosed": True,
                       "reason": f"dosed {burst}s (EC {ec}, {label} @ {conf}%)"})
    except Exception as e:
        log(f"Nutrient A dosing error: {e}")
        result["reason"] = f"error: {e}"
    finally:
        gpio_write(RELAY_NUT_A, False)     # SAFETY: always off
    return result


def dose_nutrient_b(phase, last_dose_iso, dosed_ml_so_far):
    """
    Pump C -> Nutrient B (MICROS). SCHEDULE-DRIVEN (model can't detect micros).
    Every NUT_B_DOSE_INTERVAL_HOURS, top up toward the per-stage target:
        target_ml  = NUT_B_ML_PER_L[phase] * TANK_VOLUME_L
        gap        = target_ml - dosed_ml_so_far
        this_dose  = gap * NUT_B_TOPUP_FRACTION       (gradual convergence)
        burst_s    = this_dose / PUMP_FLOW_ML_S        (capped)
    Returns (result_dict, new_last_dose_iso, new_dosed_ml).
    """
    result = {"dosed": False, "reason": None, "burst_s": 0,
              "phase": phase, "target_ml": 0, "dosed_ml": dosed_ml_so_far}

    target_ml = NUT_B_TARGET_ML.get(phase, 0.0)
    result["target_ml"] = round(target_ml, 1)

    if target_ml <= 0:
        result["reason"] = f"{phase}: no Nutrient B needed"
        return result, last_dose_iso, dosed_ml_so_far

    # schedule check: enough time elapsed since last dose?
    now = _dt.datetime.utcnow()
    if last_dose_iso:
        try:
            last = _dt.datetime.fromisoformat(last_dose_iso)
            hrs = (now - last).total_seconds() / 3600.0
            if hrs < NUT_B_DOSE_INTERVAL_HOURS:
                result["reason"] = (f"next Nutrient B in "
                                    f"{NUT_B_DOSE_INTERVAL_HOURS - hrs:.1f}h")
                return result, last_dose_iso, dosed_ml_so_far
        except ValueError:
            pass   # malformed timestamp -> treat as due

    gap = target_ml - dosed_ml_so_far
    if gap <= 0.5:                         # close enough to target
        result["reason"] = f"at target ({dosed_ml_so_far:.1f}/{target_ml:.1f} mL)"
        return result, now.isoformat(), dosed_ml_so_far   # reset timer

    this_dose_ml = gap * NUT_B_TOPUP_FRACTION
    burst = min(this_dose_ml / PUMP_FLOW_ML_S, NUT_B_MAX_BURST_S)
    burst = round(burst, 1)

    log(f"Nutrient B ({phase}): target {target_ml:.1f} mL, "
        f"have {dosed_ml_so_far:.1f} mL -> Pump C {burst}s ({this_dose_ml:.1f} mL)")
    try:
        gpio_write(RELAY_NUT_B, True)
        time.sleep(burst)
        gpio_write(RELAY_NUT_B, False)
        new_total = dosed_ml_so_far + (burst * PUMP_FLOW_ML_S)
        result.update({"dosed": True, "burst_s": burst,
                       "dosed_ml": round(new_total, 1),
                       "reason": f"topped up {burst}s ({this_dose_ml:.1f} mL)"})
        return result, now.isoformat(), new_total
    except Exception as e:
        log(f"Nutrient B dosing error: {e}")
        result["reason"] = f"error: {e}"
    finally:
        gpio_write(RELAY_NUT_B, False)     # SAFETY: always off
    return result, last_dose_iso, dosed_ml_so_far


# ============================================================
# CAMERA SERVICE
# ============================================================
def capture_and_store():
    if camera is None:
        return None
    name = f"capture_{utc_now_compact()}.jpg"
    path = os.path.join(CAPTURE_DIR, name)
    camera.capture_file(path)
    log(f"image saved {path}")
    return path

def run_inference(pil_crop):
    """Run MobileNetV2 on a single PIL crop -> (label, confidence) or None."""
    if disease_model is None:
        return None
    try:
        import numpy as np
        img = pil_crop.convert("RGB").resize(MODEL_INPUT)
        arr = np.asarray(img, dtype="float32") / 255.0      # normalize 0-1
        arr = np.expand_dims(arr, axis=0)                   # (1,224,224,3)
        preds = disease_model.predict(arr, verbose=0)[0]
        idx = int(np.argmax(preds))
        return DISEASE_CLASSES[idx], round(float(preds[idx]), 4)
    except Exception as e:
        log(f"inference error: {e}")
        return None

def analyze_plants(path):
    """
    Split the capture by WIDTH into left (plant1/A) and right (plant2/B).
    Run disease inference on each planted hole. Plant3 (C) is empty -> None.
    Returns a dict keyed by plant id, e.g.:
      {'plant1': {'label': 'Healthy', 'confidence': 0.97},
       'plant2': {'label': 'Bacterial', 'confidence': 0.88},
       'plant3': None}
    """
    result = {"plant1": None, "plant2": None, "plant3": None}
    if path is None:
        return result
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
        mid = w // 2
        left  = img.crop((0,   0, mid, h))   # plant1 / A
        right = img.crop((mid, 0, w,   h))   # plant2 / B

        # optionally save crops for debugging / dataset building
        base = os.path.splitext(path)[0]
        left.save(f"{base}_plant1.jpg")
        right.save(f"{base}_plant2.jpg")

        if ACTIVE_PLANTS.get("plant1"):
            log("  plant1: running inference...")
            r = run_inference(left)
            if r:
                result["plant1"] = {"label": r[0], "confidence": r[1]}
                log(f"  plant1: {r[0]} ({r[1]})")
        if ACTIVE_PLANTS.get("plant2"):
            log("  plant2: running inference...")
            r = run_inference(right)
            if r:
                result["plant2"] = {"label": r[0], "confidence": r[1]}
                log(f"  plant2: {r[0]} ({r[1]})")
        # plant3 stays None (empty hole)

    except Exception as e:
        log(f"analyze_plants error: {e}")
    return result


def estimate_npk(ph, ec):
    """
    Estimate N, P, K concentrations from pH and EC.
    EC (mS/cm) scales total nutrient load; pH shifts availability.
    Think of EC as total budget, pH as how that budget is split.
    (Matches pi_inference.py exactly.)
    """
    n = ec * 40.0   # N is the biggest consumer of EC
    p = ec * 10.0
    k = ec * 20.0

    if ph < 5.5:
        p *= 0.6
        k *= 0.7
    elif ph > 7.0:
        n *= 0.7

    return round(n, 2), round(p, 2), round(k, 2)


def predict_nutrient_status(frame, model_day):
    """
    Predict nutrient deficiency from the current sensor frame.
    `model_day` is the 40->60 mapped day the model expects (Task 2).
    Returns {'label': ..., 'confidence': ...} or None if model/data unavailable.
    """
    if nutrient_model is None:
        return None
    try:
        import numpy as np
        ph = frame.get("pH")
        ec = frame.get("ec")
        air_temp = frame.get("temperature")
        humidity = frame.get("humidity")
        water_level = frame.get("water_level")

        # nutrient model needs pH/EC/temp/humidity; skip cleanly if DHT is down
        if None in (ph, ec, air_temp, humidity, water_level):
            return None

        n, p, k = estimate_npk(ph, ec)
        input_values = [
            ph, ec, n, p, k,
            air_temp, humidity, water_level,
            model_day, TREATMENT_PCT          # mapped model day, not raw calendar day
        ]
        input_array = np.array(input_values).reshape(1, -1)

        label = nutrient_model.predict(input_array)[0]
        confidence = round(nutrient_model.predict_proba(input_array)[0].max() * 100, 1)
        return {"label": str(label), "confidence": confidence}
    except Exception as e:
        log(f"nutrient prediction error: {e}")
        return None


# ============================================================
# CLOUD CLIENT
# ============================================================
def publish(frame, image_path, error=None, disease=None, nutrient=None, dosing=None):
    payload = dict(frame)
    payload["image"]  = os.path.basename(image_path) if image_path else None
    payload["status"] = error if error else "ok"
    payload["disease_predictions"] = disease if disease else {
        "plant1": None, "plant2": None, "plant3": None
    }
    payload["nutrient_status"] = nutrient   # {'label':..., 'confidence':...} or None
    payload["dosing"] = dosing              # {'dosed':bool, 'reason':..., ...} or None
    try:
        msg = Message(json.dumps(payload))
        msg.content_type = "application/json"
        msg.content_encoding = "utf-8"
        iot.send_message(msg)
        log("published to IoT Hub")
    except Exception as e:
        log(f"publish failed: {e}")
        _buffer_to_disk(payload)

def _buffer_to_disk(payload):
    try:
        buffer_dir = os.path.join(DATA_DIR, "buffer")
        os.makedirs(buffer_dir, exist_ok=True)
        fn = os.path.join(buffer_dir, f"{utc_now_compact()}.json")
        with open(fn, "w") as fp:
            json.dump(payload, fp)
        log(f"buffered to {fn}")
    except Exception as e:
        log(f"buffer failed: {e}")


# ============================================================
# OLED DISPLAY
# ============================================================
def oled_show(line1, line2=""):
    from PIL import Image
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.text((4, 16), line1, font=oled_font, fill=255)
    if line2:
        draw.text((4, 36), line2, font=oled_font, fill=255)
    oled.display(image)

def oled_cycle(f):
    oled_show(f"pH: {f['pH']}")
    time.sleep(4.0)
    t = f['temperature'] if f['temperature'] is not None else "--"
    h = f['humidity'] if f['humidity'] is not None else "--"
    oled_show(f"T: {t}C", f"H: {h}%")
    time.sleep(4.5)
    pct = f.get('water_level_pct')
    pct_str = f"{pct}%" if pct is not None else "--"
    oled_show(f"Water: {pct_str}")
    time.sleep(4.0)

def oled_error(reason):
    oled_show("ERROR", reason[:18])


# ============================================================
# ORCHESTRATOR  -  main FSM loop
# ============================================================
def log(msg):
    print(f"[{utc_now_iso()}] {msg}", flush=True)

# --- Nutrient B schedule state (persisted so it survives restarts) ---
import json as _json
NUT_B_STATE_FILE = os.path.join(DATA_DIR, "nutrient_b_state.json")

def load_nut_b_state():
    """Return (last_dose_iso, dosed_ml, last_phase). Defaults if no file."""
    try:
        with open(NUT_B_STATE_FILE) as f:
            s = _json.load(f)
        return s.get("last_dose_iso"), float(s.get("dosed_ml", 0.0)), s.get("phase")
    except Exception:
        return None, 0.0, None

def save_nut_b_state(last_dose_iso, dosed_ml, phase):
    try:
        with open(NUT_B_STATE_FILE, "w") as f:
            _json.dump({"last_dose_iso": last_dose_iso,
                        "dosed_ml": dosed_ml, "phase": phase}, f)
    except Exception as e:
        log(f"could not save Nutrient B state: {e}")

def enter_error(reason, frame, img_path):
    relay_all_off()
    log(f"ERROR: {reason}")
    oled_error(reason)
    publish(frame, img_path, error=reason)

def run_forever():
    init_system()
    while True:
        # ---- S2: ACQUIRE (camera + sensors) ----
        try:
            img_path = capture_and_store()
        except Exception as e:
            img_path = None
            log(f"camera error: {e}")
        frame = acquire_all()
        log(f"frame: {frame}")

        # ---- S3: VALIDATE ----
        if not validate(frame):
            enter_error("validation failed", frame, img_path)
            _sleep_to_next_tick()
            continue

        # ---- Growth-day tracking + 40->60 model-day mapping (Task 2) ----
        actual_day = get_actual_day()
        model_day  = get_model_day(actual_day)
        phase      = get_growth_phase(model_day)
        frame["growth_day_actual"] = actual_day
        frame["growth_day_model"]  = model_day
        frame["growth_phase"]      = phase
        frame["harvest_flush"]     = (actual_day >= HARVEST_FLUSH_START_DAY)
        log(f"day: actual {actual_day} -> model {model_day} ({phase})")

        # ---- ML: per-plant disease detection ----
        log("running disease detection on captured image...")
        disease = analyze_plants(img_path)
        log(f"disease detection complete: {disease}")

        # ---- ML: nutrient deficiency prediction (uses model_day) ----
        log("running nutrient deficiency prediction...")
        nutrient_status = predict_nutrient_status(frame, model_day)
        log(f"nutrient prediction complete: {nutrient_status}")

        # ============================================================
        # TASK 1 ORDERING: NUTRIENTS FIRST, WATER LAST
        # Dosing nutrients raises the liquid level; if we topped up water
        # first then dosed, we could exceed max water level. So we dose
        # nutrients, then top up water last to absorb any remaining gap.
        # ============================================================

        # Harvest flush: in the final days, stop ALL nutrient dosing so the
        # plant flushes stored nutrients -> cleaner-tasting leaves. Keyed off
        # the REAL calendar day (model only sees "Mature" past day 35).
        flushing = actual_day >= HARVEST_FLUSH_START_DAY

        if flushing:
            log(f"HARVEST FLUSH (day {actual_day}): nutrient dosing paused")
            dose_a = {"dosed": False, "reason": f"harvest flush (day {actual_day})"}
            dose_b = {"dosed": False, "reason": f"harvest flush (day {actual_day})"}
        else:
            # ---- S4a: NUTRIENT A (macros) - model-driven, EC-scaled ----
            dose_a = dose_nutrient_a(frame, nutrient_status)
            log(f"Nutrient A: {dose_a}")

            # ---- S4b: NUTRIENT B (micros+CalMag) - scheduled top-up ----
            last_iso, dosed_ml, last_phase = load_nut_b_state()
            if last_phase != phase:           # phase changed -> reset accumulator
                dosed_ml = 0.0
            dose_b, last_iso, dosed_ml = dose_nutrient_b(phase, last_iso, dosed_ml)
            save_nut_b_state(last_iso, dosed_ml, phase)
            log(f"Nutrient B: {dose_b}")

        # ---- S4c: WATER REGULATION (LAST, after dosing) ----
        # Non-fatal: a fill fault (empty reservoir / weak pump) is warned and
        # the cycle still completes - dosing & ML already ran above.
        status, info = regulate_water()
        water_status = "ok"
        if status == "error":
            water_status = f"water_warning: {info}"
            log(f"WARNING water regulation: {info} (continuing cycle anyway)")

        # ---- S5: PUBLISH (sensors + disease + nutrient + dosing) ----
        dosing = {"nutrient_a": dose_a, "nutrient_b": dose_b}
        publish(frame, img_path, disease=disease,
                nutrient=nutrient_status, dosing=dosing,
                error=(water_status if water_status != "ok" else None))

        # ---- S6: DISPLAY ----
        oled_cycle(frame)

        # ---- S1: WAIT next tick ----
        _sleep_to_next_tick()

def _sleep_to_next_tick():
    """Sleep the remainder of the 30-min cycle (OLED cycle already consumed ~12.5s)."""
    log(f"sleeping until next cycle (~{LOOP_INTERVAL//60} min)")
    time.sleep(LOOP_INTERVAL)


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        run_forever()
    except KeyboardInterrupt:
        log("interrupted by user")
    except Exception as e:
        log(f"fatal: {e}")
    finally:
        # SAFETY on every exit path
        try:
            relay_all_off()
        except Exception:
            pass
        try:
            if camera:
                camera.stop()
        except Exception:
            pass
        try:
            if iot:
                iot.disconnect()
        except Exception:
            pass
        GPIO.cleanup()
        log("shutdown complete - relays OFF")
