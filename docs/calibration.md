# Sensor calibration

## pH (PH4502C)

Current state: single-point calibration. This corrects offset only, not slope,
so error grows the further the reading sits from the calibration point. Physical
probe contamination amplifies the drift.

Symptoms of a probe needing attention: readings pinned high (e.g. 9+ in a
solution known to be ~6), slow settling, drift within a single session.

Procedure (single-point):
1. Rinse probe in distilled water, blot dry
2. Immerse in pH 7.0 buffer, wait 60s for stable reading
3. Record raw voltage from ADS1115 A3
4. Set `calibration.ph_offset` in settings.yaml so computed pH reads 7.0

Roadmap: two-point calibration (pH 4.0 + 7.0 buffers) to correct slope as well,
on a scheduled cadence with drift logged as telemetry.

## EC (Gravity TDS V1.0)

The probe outputs a voltage read on ADS1115 A1. EC in mS/cm is the working unit
everywhere in the system; TDS in ppm is derived by formula only and never used
for decisions, because conversion-factor inconsistencies between scales (0.5 vs
0.7) breed silent bugs.

Temperature compensation: readings normalize to 25 C using a 2%/degree
coefficient (`calibration.ec_temp_coefficient`).

Status: not yet calibrated against a reference solution (1.413 mS/cm standard).
Still needed: record raw voltage vs reference, set the scale factor.

## DHT22

No calibration needed, but read reliability depends on the 10k pull-up and solid
DATA wiring. The firmware retries up to 15 attempts across two phases with a 2s
cooldown; persistent None readings indicate hardware, not code.

## HC-SR04 water level

Calibrate the empty-tank and full-tank distances once:
1. Measure sensor-to-water-surface distance at full: `dist_full_cm`
2. Measure at empty: `dist_empty_cm`
3. Level % = (dist_empty - reading) / (dist_empty - dist_full) * 100

Remember the inversion: smaller distance = fuller tank.
