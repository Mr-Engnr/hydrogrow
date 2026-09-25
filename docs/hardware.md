# Hardware

Complete pinout, wiring notes, and bill of materials for the HydroGrow rig.

## Bill of materials

| Component | Part | Interface | Notes |
|---|---|---|---|
| Compute | Raspberry Pi 4B | Host | Runs full control loop + on-device ML |
| ADC | ADS1115 16-bit | I2C 0x48 | 4-channel, reads analog probes |
| Display | SH1106 1.3" OLED | I2C 0x3C | Live status readout. NOT an SSD1306 - needs raw I2C commands via smbus2 |
| pH probe | PH4502C | ADS1115 A3, 5V supply | Single-point calibrated (see calibration.md) |
| EC / TDS | DFRobot Gravity TDS V1.0 | ADS1115 A1, 3.3V output | EC is the working unit; TDS derived by formula, never measured directly |
| Air temp + RH | DHT22 | GPIO4, 10k pull-up, 3.3V | Retried up to 15 attempts across two phases with a 2s cooldown |
| Water level | HC-SR04 ultrasonic | GPIO23 TRIG / GPIO24 ECHO | ECHO stepped down through a 1k + 2k divider (5V to ~3.3V) |
| Camera | Pi Camera (IMX219) | CSI | Disease detection, single frame cropped to 3 plant regions |
| Relays | 4-channel SRD-05VDC | GPIO17 / GPIO27 / GPIO22 | Active-low board |
| Pumps | 12V DC peristaltic x3 | Via relays | A: macro nutrients, B: micro + CalMag blend, C: water |
| Board | Custom perfboard | - | All sensor and relay wiring soldered |

## Pump mapping

| Pump | GPIO | Line | Trigger |
|---|---|---|---|
| A | 17 | Nutrient A (Growth Booster, macro NPK) | Model-driven, EC-safety-gated |
| B | 27 | Nutrient B + CalMag blend (4:1) | Schedule-driven, 24h interval |
| C | 22 | Water top-up | Level-driven |

## Wiring gotchas learned in the build

**Relay drive current.** Pi GPIO sources roughly 8 mA. The relay board optocouplers
want 15 to 20 mA. Marginal drive shows up as relays that click intermittently or
not at all. Fix: a BC547 or 2N2222 buffer per channel with a 1k base resistor.

**Ultrasonic inversion.** HC-SR04 measures the distance from sensor to water
surface. Small distance means a FULL tank. Every threshold in the level logic is
inverted from intuition; a "high" raw reading is a low tank.

**ECHO divider.** ECHO outputs 5V; Pi GPIO is 3.3V tolerant. The 1k + 2k divider
brings it to ~3.3V. If HC-SR04 reads time out ("end" never arrives), check this
divider's joints first - it was the root cause of a full 0/10 failure during
integration.

**DHT22 flakiness.** Borderline pull-up strength or a loose DATA wire shows as
intermittent "buffer not returned" with occasional successes. The firmware retries
15 times across two phases (with a 2s sensor-recovery cooldown between phases)
before reporting None. Persistent failure blocks the nutrient model, which needs
temp and humidity as features.

**I2C intermittency.** If a device detected in one scan disappears in the next,
suspect a solder joint, not software. This exact symptom appeared after repeated
rewiring sessions on the perfboard.

## Diagrams

A wiring schematic (Fritzing/KiCad, covering the ECHO divider and the relay
transistor buffer) has not been drawn yet. See
[media/hardware/wiring-detail.jpg](../media/hardware/wiring-detail.jpg) for a
photo of the actual perfboard wiring in the meantime.
