# Firmware

The Raspberry Pi control loop: sensor acquisition, on-device inference, dosing
decisions, OLED status, and telemetry publishing.

## Layout

| Path | Purpose |
|---|---|
| `main.py` | Full control loop. Contains `SensorReader`, `PumpController`, `Display`, `HydroController` |
| `inference/nutrient.py` | Loads the GradientBoosting model, derives NPK estimates, returns label + confidence |
| `config/settings.example.yaml` | Pins, thresholds, calibration, growth phases |
| `config/crop_boxes.yaml` | Per-plant camera ROI boxes for the 3-plant single-camera setup |
| `tests/test_hardware_basic.py` | Quick relay + pH + TDS sanity check |
| `tests/test_hardware_full.py` | 10-stage interactive bring-up: I2C scan, OLED, ADS1115, pH, TDS, DHT22, HC-SR04, all three pumps |

## Control loop timing

| Task | Interval |
|---|---|
| Sensor read | 15 s |
| Control decision | 120 s |
| OLED refresh | 5 s |
| JSON log write | 60 s |

Decisions run on a slower cadence than reads deliberately. Dosing changes take
time to mix and register; acting on every 15-second sample would chase noise and
overshoot.

## Dosing safety rails

Defined in the `DOSE` config block:

| Rail | Value | Why |
|---|---|---|
| `min_gap_sec` | 300 | No pump fires twice within 5 minutes |
| `max_per_hour` | 4 | Hard ceiling per pump per hour |
| `post_wait_sec` | 90 | Wait after dosing before trusting a new reading |
| `ab_gap_sec` | 5 | Separate A and B doses so they mix rather than react in the line |

`post_wait_sec` is the one that matters most. Reading EC immediately after a dose
gives a reading from unmixed solution near the sensor, which drives a second dose,
which drives a third. The wait breaks that runaway loop.

## Lettuce targets

pH 5.5 to 6.5 (ideal 6.0), EC 0.8 to 2.0 mS/cm (ideal 1.4), air 15 to 26 C,
humidity 40 to 80%.

Water level uses HC-SR04 distance from sensor down to the water surface, so
**smaller distance means more water**: 3 cm is full, 12 cm triggers top-up, 20 cm
is critical, 30 cm is an empty tank. Every threshold reads inverted from intuition.

## Running

On the Pi:

```bash
source ~/iot-env/bin/activate
pip install -r firmware/requirements.txt
python firmware/main.py
```

Paths default to the home directory and are overridable:

```bash
export HYDROGROW_DATA_DIR=/var/lib/hydrogrow
export NUTRIENT_MODEL_PATH=/opt/models/nutrient_model.pkl
export IOTHUB_CONNECTION_STRING="HostName=...;DeviceId=...;SharedAccessKey=..."
```

Hardware bring-up before first run:

```bash
python firmware/tests/test_hardware_full.py
```

## Known issues

- DHT22 reads are intermittent when the 10k pull-up is marginal. The loop retries
  15 times across two phases with a 2 s recovery cooldown; persistent `None`
  blocks the nutrient model, which needs temperature and humidity as features.
- EC is uncalibrated against a reference solution. Readings are directionally
  useful but absolute values should not be trusted for reporting.
- pH uses single-point calibration: offset is corrected, slope is not.

<!-- PENDING: camera/disease inference module and the IoT Hub publisher are not
     yet in this folder. See ../MISSING.md. -->
