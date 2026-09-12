import RPi.GPIO as GPIO
import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_dht

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

def header(title):
    print("\n" + "="*45)
    print(f"  TEST: {title}")
    print("="*45)

def ok(msg):   print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ {msg}")
def info(msg): print(f"  ℹ  {msg}")
def wait():    input("\n  Press Enter to continue...\n")

# ─────────────────────────────────────────
# TEST 1: I2C BUS
# ─────────────────────────────────────────
header("I2C BUS — detect devices")
import subprocess
result = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True)
print(result.stdout)
if "3c" in result.stdout:
    ok("OLED found at 0x3C")
else:
    fail("OLED NOT found at 0x3C — check wiring")
if "48" in result.stdout:
    ok("ADS1115 found at 0x48")
else:
    fail("ADS1115 NOT found at 0x48 — check wiring")
wait()

# ─────────────────────────────────────────
# TEST 2: OLED
# ─────────────────────────────────────────
header("OLED SSD1106")
try:
    from luma.core.interface.serial import i2c as luma_i2c
    from luma.oled.device import sh1106
    from luma.core.render import canvas
    serial = luma_i2c(port=1, address=0x3C)
    oled = sh1106(serial)
    with canvas(oled) as d:
        d.text((0, 0),  "HydroGrow Test", fill="white")
        d.text((0, 16), "OLED OK!",        fill="white")
        d.text((0, 32), time.strftime("%H:%M:%S"), fill="white")
    ok("OLED displaying — check screen")
except ImportError:
    fail("luma.oled not installed — run: pip install luma.oled")
except Exception as e:
    fail(f"OLED error: {e}")
wait()

# ─────────────────────────────────────────
# TEST 3: ADS1115 RAW
# ─────────────────────────────────────────
header("ADS1115 — raw channel voltages")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1
    for ch_num in [0, 1, 2, 3]:
        ch = AnalogIn(ads, ch_num)
        print(f"  A{ch_num}: {ch.voltage:.4f} V  (raw {ch.value})")
    ok("ADS1115 reading all 4 channels")
except Exception as e:
    fail(f"ADS1115 error: {e}")
wait()

# ─────────────────────────────────────────
# TEST 4: pH SENSOR
# ─────────────────────────────────────────
header("pH Sensor — A3 (PH4502C)")
info("Place probe in water. Reading 10 samples...")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1
    ph_ch = AnalogIn(ads, 3)
    readings = []
    for i in range(10):
        v = ph_ch.voltage
        ph = 7.0 + (2.5 - v) / 0.18
        ph = max(0, min(14, ph))
        readings.append(ph)
        print(f"  [{i+1:02d}] {v:.3f}V → pH {ph:.2f}")
        time.sleep(0.5)
    avg = sum(readings) / len(readings)
    print(f"\n  Average pH: {avg:.2f}")
    if 3 <= avg <= 11:
        ok(f"pH sensor working — reading {avg:.2f}")
    else:
        fail(f"pH reading {avg:.2f} out of expected range — check 5V power")
except Exception as e:
    fail(f"pH error: {e}")
wait()

# ─────────────────────────────────────────
# TEST 5: TDS / EC SENSOR
# ─────────────────────────────────────────
header("TDS Sensor — A1 (Gravity V1.0)")
info("Place probe in water. Reading 10 samples...")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1
    tds_ch = AnalogIn(ads, 1)
    readings = []
    for i in range(10):
        v = tds_ch.voltage
        tds = (133.42*v**3 - 255.86*v**2 + 857.39*v) * 0.5
        tds = max(0, tds)
        ec  = round(tds / 500.0, 2)
        readings.append(tds)
        print(f"  [{i+1:02d}] {v:.3f}V → TDS {tds:.0f}ppm  EC {ec:.2f}mS/cm")
        time.sleep(0.5)
    avg = sum(readings) / len(readings)
    print(f"\n  Average TDS: {avg:.0f} ppm")
    if v > 0.01:
        ok(f"TDS sensor working — {avg:.0f} ppm")
    else:
        fail("TDS reading 0V — check wiring or probe in water?")
except Exception as e:
    fail(f"TDS error: {e}")
wait()

# ─────────────────────────────────────────
# TEST 6: DHT22
# ─────────────────────────────────────────
header("DHT22 — Temperature & Humidity (GPIO4)")
info("Reading 5 samples with 2s gap...")
try:
    dht = adafruit_dht.DHT22(board.D4, use_pulseio=False)
    success = 0
    for i in range(5):
        try:
            t = dht.temperature
            h = dht.humidity
            if t is not None and h is not None:
                print(f"  [{i+1}] Temp: {t:.1f}°C  Humidity: {h:.1f}%")
                success += 1
            else:
                print(f"  [{i+1}] None returned")
        except RuntimeError as e:
            print(f"  [{i+1}] Runtime error: {e}")
        time.sleep(2.5)
    if success >= 3:
        ok(f"DHT22 working ({success}/5 reads succeeded)")
    elif success >= 1:
        info(f"DHT22 partially working ({success}/5) — check pull-up resistor 10kΩ")
    else:
        fail("DHT22 not responding — check GPIO4 wiring and 10kΩ pull-up")
except Exception as e:
    fail(f"DHT22 error: {e}")
wait()

# ─────────────────────────────────────────
# TEST 7: HC-SR04
# ─────────────────────────────────────────
header("HC-SR04 — Ultrasonic Distance (GPIO23/24)")
info("Make sure 1kΩ+2kΩ voltage divider is on ECHO pin.")
info("Reading 10 distance samples...")
TRIG = 23
ECHO = 24
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.output(TRIG, GPIO.LOW)
time.sleep(0.5)
try:
    success = 0
    for i in range(10):
        try:
            GPIO.output(TRIG, GPIO.HIGH)
            time.sleep(0.00001)
            GPIO.output(TRIG, GPIO.LOW)

            timeout = time.time() + 0.05
            start = time.time()
            while GPIO.input(ECHO) == 0:
                start = time.time()
                if time.time() > timeout:
                    raise TimeoutError("No echo start")

            end = time.time()
            while GPIO.input(ECHO) == 1:
                end = time.time()
                if time.time() > timeout + 0.05:
                    raise TimeoutError("No echo end")

            dist = (end - start) * 34300 / 2.0
            if 2 <= dist <= 400:
                print(f"  [{i+1:02d}] Distance: {dist:.1f} cm")
                success += 1
            else:
                print(f"  [{i+1:02d}] Out of range: {dist:.1f} cm")
        except TimeoutError as e:
            print(f"  [{i+1:02d}] Timeout: {e}")
        time.sleep(0.1)

    if success >= 7:
        ok(f"HC-SR04 working ({success}/10 valid readings)")
    elif success >= 3:
        info(f"HC-SR04 partially working ({success}/10) — check voltage divider")
    else:
        fail("HC-SR04 not responding — check VCC 5V, TRIG GPIO23, ECHO divider GPIO24")
except Exception as e:
    fail(f"HC-SR04 error: {e}")
wait()

# ─────────────────────────────────────────
# TEST 8: RELAY — Pump A (Nutrient A)
# ─────────────────────────────────────────
header("RELAY — Pump A / Nutrient A (GPIO17 → IN1)")
info("Pump A will run for 2 seconds. Watch for relay click.")
PUMP_A = 17
GPIO.setup(PUMP_A, GPIO.OUT, initial=GPIO.HIGH)
input("  Press Enter to fire Pump A...")
GPIO.output(PUMP_A, GPIO.LOW)
time.sleep(2)
GPIO.output(PUMP_A, GPIO.HIGH)
result = input("  Did you hear a click and pump ran? (y/n): ")
if result.lower() == 'y':
    ok("Pump A (Nutrient A) working")
else:
    fail("Pump A — check GPIO17 → IN1 wiring and relay VCC/GND")
wait()

# ─────────────────────────────────────────
# TEST 9: RELAY — Pump B (Nutrient B)
# ─────────────────────────────────────────
header("RELAY — Pump B / Nutrient B (GPIO27 → IN2)")
PUMP_B = 27
GPIO.setup(PUMP_B, GPIO.OUT, initial=GPIO.HIGH)
input("  Press Enter to fire Pump B...")
GPIO.output(PUMP_B, GPIO.LOW)
time.sleep(2)
GPIO.output(PUMP_B, GPIO.HIGH)
result = input("  Did you hear a click and pump ran? (y/n): ")
if result.lower() == 'y':
    ok("Pump B (Nutrient B) working")
else:
    fail("Pump B — check GPIO27 → IN2 wiring")
wait()

# ─────────────────────────────────────────
# TEST 10: RELAY — Pump C (Water)
# ─────────────────────────────────────────
header("RELAY — Pump C / Water (GPIO22 → IN3)")
PUMP_C = 22
GPIO.setup(PUMP_C, GPIO.OUT, initial=GPIO.HIGH)
input("  Press Enter to fire Pump C...")
GPIO.output(PUMP_C, GPIO.LOW)
time.sleep(2)
GPIO.output(PUMP_C, GPIO.HIGH)
result = input("  Did you hear a click and pump ran? (y/n): ")
if result.lower() == 'y':
    ok("Pump C (Water) working")
else:
    fail("Pump C — check GPIO22 → IN3 wiring")
wait()

# ─────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────
print("\n" + "="*45)
print("  ALL TESTS COMPLETE")
print("  Check ✅/❌ above for any failures")
print("="*45)

GPIO.cleanup()
