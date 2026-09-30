# Firmware

The Raspberry Pi control loop: sensor acquisition, on-device inference, dosing
decisions, OLED status, and telemetry publishing.

## Layout

| Path | Purpose |
|---|---|
| `main.py` | v2.0 control loop, 30-min supervisory cycle: sensors + camera, water-level control, Nutrient A dosing (Random Forest), scheduled Nutrient B, MobileNetV2 disease check, IoT Hub publish with disk buffer, OLED status |
| `inference/nutrient.py` | Loads the Random Forest model, derives NPK estimates, returns label + confidence |
| `config/settings.example.yaml` | Pins, thresholds, calibration, growth phases |
| `config/crop_boxes.yaml` | Per-plant camera ROI boxes for the 3-plant single-camera setup |
| `tests/test_hardware_basic.py` | Quick relay + pH + TDS sanity check |
| `tests/test_hardware_full.py` | 11-stage interactive bring-up: I2C scan, OLED, ADS1115, pH, TDS, DHT22, HC-SR04, all three pumps, Pi Camera capture |
| `tests/test_sensors.py` | pH + EC readout mirrored to the OLED |
| `tests/camera_test.py` | Pi Camera capture + MobileNetV2 disease prediction |

## Control loop timing

| Task | Interval |
|---|---|
| Supervisory cycle (sensors, camera, ML, dosing, water, publish, OLED) | 30 min (`LOOP_INTERVAL = 1800`) |
| Water pump poll while filling | 1 s |
| Water pump continuous-run cap | 300 s (`PUMP_TIMEOUT`) |
| OLED status rotation (pH, temp/humidity, water) | ~12.5 s, once per cycle |

Each cycle runs in a fixed order: acquire, validate, growth-day mapping, disease
check, nutrient prediction, Nutrient A, Nutrient B, water top-up, publish, OLED.
Nutrients are dosed before water so the top-up absorbs the added volume instead of
overfilling. Failed IoT Hub publishes are buffered to `$HYDROGROW_DATA_DIR/buffer/`.

## Dosing rules

**Nutrient A (macros, Pump B)** is model-driven. It fires only when all hold:

- EC < 1.2 mS/cm
- the Random Forest predicts a deficiency (label is not `Healthy`)
- model confidence >= 70% (`DOSE_MIN_CONFIDENCE`)

EC >= 1.8 is a hard cutoff and never doses. Burst length scales with how low EC is:
2 s (1.1 to 1.2), 3 s (0.8 to 1.1), 4 s (below 0.8, hard ceiling).

**Nutrient B (micros + CalMag blend, Pump C)** is schedule-driven, since the model
only detects N/P/K deficiencies. Every 24 h it tops up 10% of the remaining gap
toward a per-phase target for the 16 L reservoir, capped at 30 s per burst:

| Phase | Target (mL) |
|---|---|
| Germination | 0 |
| Seedling | 50 |
| Vegetative | 100 |
| Mature | 140 |
| Harvest Ready | 0 |

The bottle is 400 mL pure B + 100 mL CalMag, so targets are scaled x1.25 versus
pure-B values. Dosed volume is persisted in `nutrient_b_state.json` and resets when
the phase changes. `PUMP_FLOW_ML_S` (1.0 mL/s) is a placeholder: measure your pump.

**Harvest flush:** from real day 37 onward, all nutrient dosing stops.

## Growth-day mapping (40 to 60 days)

Real lettuce reaches harvest in about 40 days, but the nutrient model was trained
on a 60-day lifecycle. The loop tracks the real day from `PLANTING_DATE` (set this
to your sow date in `main.py`) and scales it for the model:
`model_day = round(actual_day * 1.5)`, clamped to 1..60. Phases on the model scale:
Germination 1-7, Seedling 8-14, Vegetative 15-35, Mature 36-52, Harvest Ready 53-60.

## Lettuce targets

pH 5.5 to 6.5, EC 1.2 to 1.8 mS/cm (below 1.2 is depletion, above 1.8 is burn risk).

Water level uses HC-SR04 distance from sensor down to the water surface, so
**smaller distance means more water**:

| Distance | Meaning |
|---|---|
| >= 3.0 cm | Water low, pump ON |
| 2.0 cm | Fill target, pump OFF |
| < 1.5 cm | Overfill fault |

Empty-box baseline is 11.8 cm (`TOTAL_BOX_DEPTH`); level % is derived from it.

## Running

On the Pi:

```bash
source ~/iot-env/bin/activate
pip install -r firmware/requirements.txt
python firmware/main.py
```

Environment variables:

| Variable | Required | Purpose |
|---|---|---|
| `IOTHUB_CONNECTION_STRING` | Yes | Azure IoT Hub device connection string. Startup fails without it. |
| `HYDROGROW_DATA_DIR` | No (default `~`) | Root for `models/`, `captures/`, `buffer/` and `nutrient_b_state.json` |

```bash
export IOTHUB_CONNECTION_STRING="<device connection string from Azure portal>"
export HYDROGROW_DATA_DIR=/var/lib/hydrogrow
```

Models are loaded from `$HYDROGROW_DATA_DIR/models/`: `nutrient_model.pkl` and
`lettuce_mobilenetv2.h5`. If either fails to load, that prediction is disabled and
the loop keeps running. The disease model ships as a release asset; the nutrient
model is in the repo:

```bash
mkdir -p "$HYDROGROW_DATA_DIR/models"
curl -L -o "$HYDROGROW_DATA_DIR/models/lettuce_mobilenetv2.h5" \
  https://github.com/Mr-Engnr/hydrogrow/releases/download/v1.0.0/lettuce_mobilenetv2.h5
cp ml/nutrient-prediction/models/nutrient_model.pkl "$HYDROGROW_DATA_DIR/models/"
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
