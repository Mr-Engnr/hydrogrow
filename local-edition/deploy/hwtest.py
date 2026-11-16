#!/usr/bin/env python3
"""
hwtest.py: non-interactive hardware check with a pass/fail table.
Ported from the Pi's own send_data.py / test_all.py (11 manual steps) so bootstrap.sh can run
it unattended. Same pins, same conversions, same thresholds.

  ~/iot-env/bin/python deploy/hwtest.py              # sensors, I2C, OLED, camera, model files, imports
  ~/iot-env/bin/python deploy/hwtest.py --pumps      # ALSO fire each relay for 2 s (needs a human watching)
  ~/iot-env/bin/python deploy/hwtest.py --json out.json

Exit code 0 when every non-skipped test passes, 1 otherwise. Pump tests are SKIP unless --pumps.
Nothing here writes to the data dir except one camera frame in ~/captures/hwtest_*.jpg.
"""
import argparse, json, os, subprocess, sys, time, importlib

HOME = os.path.expanduser("~")
DATA_DIR = os.getenv("HYDROGROW_DATA_DIR", HOME)
MODEL_H5 = os.path.join(DATA_DIR, "models", "lettuce_mobilenetv2.h5")
MODEL_PKL = os.path.join(DATA_DIR, "models", "nutrient_model.pkl")
SHA_H5 = "c2947b489e242a3f77b7586e68f517a5df835a225991b140f5acdaafb28e1b6f"
SHA_PKL = "3cc057b25a4b6c9c1237a16fbbc839dd64798c8b2781fab288fc6f712238cee1"

results = []
def record(name, status, detail=""):
    results.append({"test": name, "status": status, "detail": str(detail)[:120]})
    print(f"  [{status:4s}] {name:34s} {detail}", flush=True)

def run(name, fn, skip=False):
    if skip:
        record(name, "SKIP", "use --pumps to enable"); return
    try:
        ok, detail = fn()
        record(name, "PASS" if ok else "FAIL", detail)
    except Exception as e:
        record(name, "FAIL", f"{e.__class__.__name__}: {e}")

# ---------------------------------------------------------------- tests
def t_imports():
    missing = []
    for m in ["RPi.GPIO", "board", "busio", "adafruit_ads1x15.ads1115", "adafruit_dht", "luma.oled.device",
              "picamera2", "numpy", "sklearn", "joblib", "paho.mqtt.client", "PIL", "smbus2", "yaml"]:
        try: importlib.import_module(m)
        except Exception as e: missing.append(f"{m}({e.__class__.__name__})")
    return (not missing, "all firmware imports resolve" if not missing else "missing: " + ", ".join(missing))

def t_tensorflow():
    import tensorflow as tf
    return True, f"tensorflow {tf.__version__}, numpy {importlib.import_module('numpy').__version__}"

def t_paho_v2():
    import paho.mqtt.client as m
    return hasattr(m, "CallbackAPIVersion"), f"paho-mqtt {getattr(m, '__version__', '?')} (v2 API {'present' if hasattr(m, 'CallbackAPIVersion') else 'MISSING'})"

def t_models():
    import hashlib
    out = []
    for p, want in ((MODEL_H5, SHA_H5), (MODEL_PKL, SHA_PKL)):
        if not os.path.isfile(p): return False, f"missing {p}"
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if h != want: return False, f"sha256 mismatch {os.path.basename(p)}"
        out.append(os.path.basename(p))
    return True, "present + SHA-256 verified: " + ", ".join(out)

def t_nutrient_model():
    import joblib, numpy as np, warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        m = joblib.load(MODEL_PKL)
        label = m.predict(np.array([[6.1, 1.4, 56.0, 14.0, 28.0, 24.0, 60.0, 2.4, 27, 100.0]]))[0]
    ver_warn = [str(x.message)[:60] for x in w if "version" in str(x.message).lower()]
    return (not ver_warn, f"predict -> {label}" + (f"; sklearn version warning: {ver_warn[0]}" if ver_warn else "; no version warning"))

def t_disease_model():
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    from tensorflow.keras.models import load_model
    import numpy as np
    t = time.time(); m = load_model(MODEL_H5)
    p = m.predict(np.zeros((1, 224, 224, 3), dtype="float32"), verbose=0)[0]
    return p.shape[0] == 3, f"loaded in {time.time()-t:.1f}s, 3 classes, probs sum {p.sum():.2f}"

def t_i2c():
    r = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0: return False, r.stderr.strip() or "i2cdetect failed (is I2C enabled? i2c-tools installed?)"
    found = [a for a in ("3c", "48") if a in r.stdout]
    return len(found) == 2, f"found {found} (need 3c=OLED, 48=ADS1115)"

def t_ads1115():
    import board, busio, adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    i2c = busio.I2C(board.SCL, board.SDA); ads = ADS.ADS1115(i2c); ads.gain = 1
    v = {c: round(AnalogIn(ads, c).voltage, 3) for c in range(4)}
    return True, f"A0..A3 volts {v}"

def t_ph():
    import board, busio, adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ads = ADS.ADS1115(busio.I2C(board.SCL, board.SDA)); ads.gain = 1; ch = AnalogIn(ads, 3)
    vals = []
    for _ in range(10):
        v = ch.voltage; vals.append(max(0.0, min(14.0, 7.0 + (2.5 - v) / 0.18))); time.sleep(0.2)
    avg = sum(vals) / len(vals)
    return 3.0 <= avg <= 11.0, f"avg pH {avg:.2f} from A3 (3..11 expected with probe in water)"

def t_tds():
    import board, busio, adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ads = ADS.ADS1115(busio.I2C(board.SCL, board.SDA)); ads.gain = 1; ch = AnalogIn(ads, 1)
    vals = []
    for _ in range(10):
        v = ch.voltage; vals.append(max(0.0, (133.42*v**3 - 255.86*v**2 + 857.39*v) * 0.5)); time.sleep(0.2)
    avg = sum(vals) / len(vals)
    return True, f"avg TDS {avg:.0f} ppm, EC {avg/500:.2f} mS/cm from A1"

def t_dht22():
    import board, adafruit_dht
    d = adafruit_dht.DHT22(board.D4, use_pulseio=False); good = 0; last = ""
    for _ in range(5):
        try:
            t, h = d.temperature, d.humidity
            if t is not None and h is not None: good += 1; last = f"{t:.1f}C {h:.1f}%"
        except RuntimeError as e: last = str(e)[:40]
        time.sleep(2.2)
    return good >= 3, f"{good}/5 reads ok, last {last}"

def t_hcsr04():
    import RPi.GPIO as GPIO
    TRIG, ECHO = 23, 24
    GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
    GPIO.setup(TRIG, GPIO.OUT); GPIO.setup(ECHO, GPIO.IN); GPIO.output(TRIG, 0); time.sleep(0.3)
    good, dists = 0, []
    for _ in range(10):
        try:
            GPIO.output(TRIG, 1); time.sleep(0.00001); GPIO.output(TRIG, 0)
            t0 = time.time(); start = end = t0
            while GPIO.input(ECHO) == 0:
                start = time.time()
                if start - t0 > 0.05: raise TimeoutError("no echo start")
            while GPIO.input(ECHO) == 1:
                end = time.time()
                if end - start > 0.05: raise TimeoutError("echo stuck high")
            d = (end - start) * 34300 / 2
            if 2 <= d <= 400: good += 1; dists.append(round(d, 1))
        except Exception: pass
        time.sleep(0.1)
    return good >= 7, f"{good}/10 valid, distances {dists[:5]} cm"

def t_oled():
    from luma.core.interface.serial import i2c as luma_i2c
    from luma.oled.device import sh1106
    from luma.core.render import canvas
    dev = sh1106(luma_i2c(port=1, address=0x3C))
    with canvas(dev) as d:
        d.text((0, 0), "-- HydroGrow --", fill="white"); d.text((0, 14), "hwtest OK", fill="white")
        d.text((0, 28), time.strftime("%H:%M:%S"), fill="white")
    return True, "text drawn on SH1106 (look at the display)"

def t_camera():
    from picamera2 import Picamera2
    cam = Picamera2(); cam.configure(cam.create_still_configuration(main={"size": (1280, 720)})); cam.start(); time.sleep(2)
    os.makedirs(os.path.join(DATA_DIR, "captures"), exist_ok=True)
    p = os.path.join(DATA_DIR, "captures", time.strftime("hwtest_%Y%m%d_%H%M%S.jpg"))
    cam.capture_file(p); cam.stop(); cam.close()
    return os.path.getsize(p) > 10_000, f"{p} ({os.path.getsize(p)//1024} KB)"

def pump(pin, name):
    def f():
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)   # active LOW: HIGH = off
        GPIO.output(pin, GPIO.LOW); time.sleep(2); GPIO.output(pin, GPIO.HIGH)
        return True, f"{name} GPIO{pin} pulsed 2 s (verify by ear/eye; relay click + 12 V on NO)"
    return f

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pumps", action="store_true", help="also pulse the three relays for 2 s each")
    ap.add_argument("--json", help="write results to this file")
    ap.add_argument("--no-ml", action="store_true", help="skip TensorFlow/model load (fast run)")
    a = ap.parse_args()
    print(f"HydroGrow hardware test  {time.strftime('%Y-%m-%d %H:%M:%S')}  python {sys.version.split()[0]}  data dir {DATA_DIR}")
    run("python imports", t_imports)
    run("paho-mqtt v2 API", t_paho_v2)
    run("model files + SHA-256", t_models)
    if not a.no_ml:
        run("tensorflow import", t_tensorflow)
        run("nutrient model predict", t_nutrient_model)
        run("disease model load+predict", t_disease_model)
    run("I2C bus (0x3C, 0x48)", t_i2c)
    run("ADS1115 4 channels", t_ads1115)
    run("pH probe A3", t_ph)
    run("TDS/EC probe A1", t_tds)
    run("DHT22 GPIO4", t_dht22)
    run("HC-SR04 GPIO23/24", t_hcsr04)
    run("OLED SH1106", t_oled)
    run("Pi camera capture", t_camera)
    run("relay K1 pump A GPIO17", pump(17, "Nutrient A"), skip=not a.pumps)
    run("relay K2 pump B GPIO27", pump(27, "Nutrient B"), skip=not a.pumps)
    run("relay K3 water  GPIO22", pump(22, "Water"), skip=not a.pumps)
    try:
        import RPi.GPIO as GPIO
        for pin in (17, 27, 22):
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)   # leave all relays OFF
        GPIO.cleanup()
    except Exception:
        pass
    n = {s: sum(1 for r in results if r["status"] == s) for s in ("PASS", "FAIL", "SKIP")}
    print(f"\n{n['PASS']} pass, {n['FAIL']} fail, {n['SKIP']} skipped")
    if a.json:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": n, "results": results}, open(a.json, "w"), indent=1)
    return 0 if n["FAIL"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
