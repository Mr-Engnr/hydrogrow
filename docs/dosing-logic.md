# Dosing logic

How HydroGrow decides when and how much to feed.

## Two independent dosing paths

**Nutrient A (macro / NPK)** is model-driven. The GradientBoosting classifier maps
live sensor state to a deficiency class. Dosing fires only when:

1. The model predicts a deficiency with confidence >= 70%
2. EC is below the safety cutoff (dosing into an already-concentrated reservoir
   burns roots, so high EC always vetoes)
3. The current growth phase permits macro dosing

**Nutrient B (micro + CalMag)** is schedule-driven on a 24h interval. Micronutrient
demand is steady and low; a model adds nothing here, so a schedule is the honest
design.

## Why CalMag lives in the B bottle

Three bottles, two available pump lines. CalMag merges into Nutrient B, never A:
calcium in the CalMag reacts with phosphate in the macro bottle and precipitates,
which both wastes nutrient and clogs lines. The combined bottle is a 4:1 B+CalMag
blend, so every B dose target carries a 1.25x multiplier to deliver full B strength.

## Growth phases

Five phases over a 60-day model calendar:

| Phase | Model days |
|---|---|
| Germination | 1-7 |
| Seedling | 8-14 |
| Vegetative | 15-35 |
| Mature | 36-52 |
| Harvest Ready | 53-60 |

The physical cycle runs ~40 days, mapped onto the 60-day model calendar:

```
model_day = clamp(round(actual_day * 1.5), 1, 60)
```

Harvest flush (water only, no nutrients) begins at real day 37.

## Execution order matters

Within each control cycle: **nutrients dose before water top-up.** Reversing this
pushes the water level past max before nutrients go in, and the added nutrient
volume then overflows the reservoir. Order is enforced in the control loop, not
left to chance.

## From dose volume to pump runtime

Doses are computed in mL against a 16L reservoir. Converting mL to pump seconds
requires the measured flow rate of each pump:

```
runtime_sec = dose_mL / flow_rate_mL_per_sec
```

Flow rate comes from a 10-second calibration: run the pump into a measuring
container for 10s, divide collected mL by 10.

Measured flow rates per pump are not yet recorded.

## Safety behavior observed in production

During integration, EC read 2.415 mS/cm (above cutoff) while the model signal was
unavailable due to a DHT22 fault. The controller correctly held Nutrient A dosing
on both grounds independently - the EC veto and the missing-model-input veto each
sufficed. Defense in depth on actuation is deliberate.
