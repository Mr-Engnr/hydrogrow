import os
import time
import subprocess
import numpy as np
import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_dht

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

oled = None

def header(title):
    print("\n" + "=" * 55)
    print(f"  TEST: {title}")
    print("=" * 55)

def ok(msg):   print(f"  OK    {msg}")
def fail(msg): print(f"  FAIL  {msg}")
def info(msg): print(f"  INFO  {msg}")
def wait():    input("\n  Press Enter to continue to next test...\n")

# =========================================================
# TEST 1: I2C BUS
# =========================================================
header("1/11 - I2C BUS - detect OLED (0x3C) and ADS1115 (0x48)")
result = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True)
print(result.stdout)
if "3c" in result.stdout:
    ok("OLED found at 0x3C")
else:
    fail("OLED NOT found - check SDA/SCL wiring")
if "48" in result.stdout:
    ok("ADS1115 found at 0x48")
else:
    fail("ADS1115 NOT found - check SDA/SCL wiring")
wait()

# =========================================================
# TEST 2: OLED DISPLAY
# =========================================================
header("2/11 - OLED Display (SH1106)")
try:
    from luma.core.interface.serial import i2c as luma_i2c
    from luma.oled.device import sh1106
    from luma.core.render import canvas

    serial = luma_i2c(port=1, address=0x3C)
    oled = sh1106(serial)
    with canvas(oled) as d:
        d.text((0, 0),  "-- HydroGrow --", fill="white")
        d.text((0, 14), "OLED Test OK",     fill="white")
        d.text((0, 28), "Full System Test", fill="white")
        d.text((0, 56), time.strftime("%H:%M:%S"), fill="white")
    ok("OLED showing - check screen now")
    time.sleep(4)
except ImportError:
    fail("luma.oled not installed - pip install luma.oled pillow")
except Exception as e:
    fail(f"OLED error: {e}")
wait()

# =========================================================
# TEST 3: ADS1115 RAW CHANNELS
# =========================================================
header("3/11 - ADS1115 - all 4 channels raw voltage")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1
    for ch_num in [0, 1, 2, 3]:
        ch = AnalogIn(ads, ch_num)
        print(f"  A{ch_num}: {ch.voltage:.4f} V")
    ok("ADS1115 reading all channels")
except Exception as e:
    fail(f"ADS1115 error: {e}")
wait()

# =========================================================
# TEST 4: pH SENSOR
# =========================================================
header("4/11 - pH Sensor - A3 (PH4502C @ 5V)")
info("Place probe in water...")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1
    ph_ch = AnalogIn(ads, 3)
    readings = []
    for i in range(10):
        v = ph_ch.voltage
        ph = round(max(0.0, min(14.0, 7.0 + (2.5 - v) / 0.18)), 2)
        readings.append(ph)
        print(f"  [{i+1:02d}] {v:.3f}V -> pH {ph:.2f}")
        if oled:
            from luma.core.render import canvas
            with canvas(oled) as d:
                d.text((0, 0),  "-- pH Sensor --", fill="white")
                d.text((0, 14), f"V: {v:.3f}V",     fill="white")
                d.text((0, 28), f"pH: {ph:.2f}",    fill="white")
        time.sleep(0.5)
    avg = round(sum(readings) / len(readings), 2)
    if 3.0 <= avg <= 11.0:
        ok(f"pH sensor working - avg pH {avg}")
    else:
        fail(f"pH {avg} out of range - check 5V power")
except Exception as e:
    fail(f"pH error: {e}")
wait()

# =========================================================
# TEST 5: TDS/EC SENSOR
# =========================================================
header("5/11 - TDS/EC Sensor - A1 (Gravity V1.0)")
info("Place probe in water...")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1
    tds_ch = AnalogIn(ads, 1)
    readings = []
    for i in range(10):
        v = tds_ch.voltage
        tds = max(0.0, round((133.42*v**3 - 255.86*v**2 + 857.39*v)*0.5, 1))
        ec = round(tds / 500.0, 2)
        readings.append(tds)
        print(f"  [{i+1:02d}] {v:.3f}V -> TDS {tds:.0f}ppm EC {ec:.2f}mS/cm")
        if oled:
            from luma.core.render import canvas
            with canvas(oled) as d:
                d.text((0, 0),  "-- TDS Sensor --", fill="white")
                d.text((0, 14), f"V: {v:.3f}V",      fill="white")
                d.text((0, 28), f"TDS: {tds:.0f}ppm", fill="white")
                d.text((0, 42), f"EC: {ec:.2f}mS",    fill="white")
        time.sleep(0.5)
    avg = round(sum(readings) / len(readings), 1)
    ok(f"TDS sensor done - avg {avg}ppm")
except Exception as e:
    fail(f"TDS error: {e}")
wait()

# =========================================================
# TEST 6: DHT22
# =========================================================
header("6/11 - DHT22 - Temperature & Humidity (GPIO4 @ 3.3V)")
info("Needs 10k pull-up between DATA and 3.3V")
try:
    dht = adafruit_dht.DHT22(board.D4, use_pulseio=False)
    success = 0
    for i in range(5):
        try:
            t = dht.temperature
            h = dht.humidity
            if t is not None and h is not None:
                print(f"  [{i+1}] Temp: {t:.1f}C  Humidity: {h:.1f}%")
                success += 1
                if oled:
                    from luma.core.render import canvas
                    with canvas(oled) as d:
                        d.text((0, 0),  "-- DHT22 --",       fill="white")
                        d.text((0, 14), f"Temp: {t:.1f}C",   fill="white")
                        d.text((0, 28), f"Hum:  {h:.1f}%",   fill="white")
            else:
                print(f"  [{i+1}] None returned")
        except RuntimeError as e:
            print(f"  [{i+1}] RuntimeError: {e}")
        time.sleep(2.5)
    if success >= 3:
        ok(f"DHT22 working ({success}/5)")
    else:
        fail(f"DHT22 unstable ({success}/5) - check 10k pull-up")
except Exception as e:
    fail(f"DHT22 error: {e}")
wait()

# =========================================================
# TEST 7: HC-SR04
# =========================================================
header("7/11 - HC-SR04 - Ultrasonic Distance (GPIO23/24 @ 5V)")
info("ECHO must have voltage divider to safe 3.3V level")
TRIG = 23
ECHO = 24
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.output(TRIG, GPIO.LOW)
time.sleep(0.5)
success = 0
for i in range(10):
    try:
        GPIO.output(TRIG, GPIO.HIGH)
        time.sleep(0.00001)
        GPIO.output(TRIG, GPIO.LOW)
        t_out = time.time() + 0.05
        start = time.time()
        while GPIO.input(ECHO) == 0:
            start = time.time()
            if time.time() > t_out:
                raise TimeoutError("start")
        end = time.time()
        while GPIO.input(ECHO) == 1:
            end = time.time()
            if time.time() > t_out + 0.05:
                raise TimeoutError("end")
        dist = round((end - start) * 34300 / 2.0, 1)
        if 2.0 <= dist <= 400.0:
            print(f"  [{i+1:02d}] Distance: {dist} cm")
            success += 1
            if oled:
                from luma.core.render import canvas
                with canvas(oled) as d:
                    d.text((0, 0),  "-- HC-SR04 --",     fill="white")
                    d.text((0, 14), f"Dist: {dist} cm",  fill="white")
        else:
            print(f"  [{i+1:02d}] Out of range: {dist} cm")
    except Exception as e:
        print(f"  [{i+1:02d}] {e}")
    time.sleep(0.1)
if success >= 7:
    ok(f"HC-SR04 working ({success}/10)")
else:
    fail(f"HC-SR04 issues ({success}/10) - check 5V VCC, TRIG, ECHO divider")
wait()

# =========================================================
# TEST 8: RELAY - PUMP A
# =========================================================
header("8/11 - Relay K1 - Pump A / Nutrient A (GPIO17 -> IN1)")
PUMP_A = 17
GPIO.setup(PUMP_A, GPIO.OUT, initial=GPIO.HIGH)
input("  Press Enter to fire Pump A (5s)...")
GPIO.output(PUMP_A, GPIO.LOW)
print("  Pump A ON - check NO terminal for 12V now")
time.sleep(5)
GPIO.output(PUMP_A, GPIO.HIGH)
print("  Pump A OFF")
r = input("  Did pump actually run? (y/n): ")
if r.lower() == 'y':
    ok("Pump A (Nutrient A) working")
else:
    fail("Pump A failed - check relay/transistor driver wiring")
wait()

# =========================================================
# TEST 9: RELAY - PUMP B
# =========================================================
header("9/11 - Relay K2 - Pump B / Nutrient B (GPIO27 -> IN2)")
PUMP_B = 27
GPIO.setup(PUMP_B, GPIO.OUT, initial=GPIO.HIGH)
input("  Press Enter to fire Pump B (5s)...")
GPIO.output(PUMP_B, GPIO.LOW)
print("  Pump B ON - check NO terminal for 12V now")
time.sleep(5)
GPIO.output(PUMP_B, GPIO.HIGH)
print("  Pump B OFF")
r = input("  Did pump actually run? (y/n): ")
if r.lower() == 'y':
    ok("Pump B (Nutrient B) working")
else:
    fail("Pump B failed - check relay/transistor driver wiring")
wait()

# =========================================================
# TEST 10: RELAY - PUMP C
# =========================================================
header("10/11 - Relay K3 - Pump C / Water (GPIO22 -> IN3)")
PUMP_C = 22
GPIO.setup(PUMP_C, GPIO.OUT, initial=GPIO.HIGH)
input("  Press Enter to fire Pump C (5s)...")
GPIO.output(PUMP_C, GPIO.LOW)
print("  Pump C ON - check NO terminal for 12V now")
time.sleep(5)
GPIO.output(PUMP_C, GPIO.HIGH)
print("  Pump C OFF")
r = input("  Did pump actually run? (y/n): ")
if r.lower() == 'y':
    ok("Pump C (Water) working")
else:
    fail("Pump C failed - check relay/transistor driver wiring")
wait()

# =========================================================
# TEST 11: CAMERA
# =========================================================
header("11/11 - Pi Camera - capture test")
try:
    from picamera2 import Picamera2
    from datetime import datetime

    cam = Picamera2()
    config = cam.create_still_configuration(main={"size": (1280, 720)})
    cam.configure(config)
    cam.start()
    time.sleep(2)

    save_dir = os.path.join(os.getenv("HYDROGROW_DATA_DIR", os.path.expanduser("~")), "captures")
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(save_dir, f"systest_{ts}.jpg")
    cam.capture_file(filepath)
    cam.stop()

    if os.path.exists(filepath):
        size_kb = os.path.getsize(filepath) / 1024
        ok(f"Camera working - image saved {filepath} ({size_kb:.0f} KB)")
    else:
        fail("Camera capture failed - no file created")
except Exception as e:
    fail(f"Camera error: {e}")

# =========================================================
# SUMMARY
# =========================================================
print("\n" + "=" * 55)
print("  FULL SYSTEM TEST COMPLETE")
print("  Review OK / FAIL above for any issues")
print("=" * 55)

if oled:
    from luma.core.render import canvas
    with canvas(oled) as d:
        d.text((0, 0),  "-- HydroGrow --",   fill="white")
        d.text((0, 14), "Full Test Done",    fill="white")
        d.text((0, 28), "Check terminal",    fill="white")

GPIO.cleanup()
