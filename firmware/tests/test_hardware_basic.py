import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import time

# ─── SETUP ───────────────────────────────────────────
GPIO.setmode(GPIO.BCM)

# Relay pins (active LOW)
PUMP1 = 17
PUMP2 = 27
PUMP3 = 22
GPIO.setup([PUMP1, PUMP2, PUMP3], GPIO.OUT, initial=GPIO.HIGH)

# I2C + ADS1115
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
ads.gain = 1  # ±4.096V range

# Analog channels
ph_channel  = AnalogIn(ads, ADS.P3)   # pH on A3
tds_channel = AnalogIn(ads, ADS.P1)   # TDS/EC on A1

# ─── HELPER FUNCTIONS ────────────────────────────────
def voltage_to_ph(voltage):
    # PH4502C: 7pH = ~2.5V, slope ~0.18V/pH
    return 7 + (2.5 - voltage) / 0.18

def voltage_to_tds(voltage):
    # Gravity TDS V1.0 formula (3.3V ref)
    compensation = 1.0  # temperature compensation factor (assume 25°C)
    voltage_comp = voltage / compensation
    tds = (133.42 * voltage_comp**3 
           - 255.86 * voltage_comp**2 
           + 857.39 * voltage_comp) * 0.5
    return tds

def test_pump(pin, name, duration=2):
    print(f"\n>>> Testing {name}...")
    GPIO.output(pin, GPIO.LOW)   # ON
    time.sleep(duration)
    GPIO.output(pin, GPIO.HIGH)  # OFF
    print(f"    {name} done.")

# ─── TESTS ───────────────────────────────────────────

print("=" * 40)
print("   HYDROGROW HARDWARE TEST")
print("=" * 40)

# 1. RELAY / PUMP TEST
print("\n[1] RELAY TEST")
input("    Press Enter to test Pump 1...")
test_pump(PUMP1, "Pump 1")

input("    Press Enter to test Pump 2...")
test_pump(PUMP2, "Pump 2")

input("    Press Enter to test Pump 3...")
test_pump(PUMP3, "Pump 3")

# 2. pH SENSOR TEST
print("\n[2] pH SENSOR TEST (10 readings)")
for i in range(10):
    v = ph_channel.voltage
    ph = voltage_to_ph(v)
    print(f"    Raw: {v:.3f}V  →  pH: {ph:.2f}")
    time.sleep(1)

# 3. TDS/EC SENSOR TEST
print("\n[3] TDS/EC SENSOR TEST (10 readings)")
for i in range(10):
    v = tds_channel.voltage
    tds = voltage_to_tds(v)
    print(f"    Raw: {v:.3f}V  →  TDS: {tds:.1f} ppm")
    time.sleep(1)

# ─── CLEANUP ─────────────────────────────────────────
GPIO.cleanup()
print("\n✅ All tests complete.")