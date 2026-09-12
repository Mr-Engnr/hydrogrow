# Results

PENDING: every table here regenerates from scripts once model files are
recovered. Placeholder markers [MEASURE] in the README map to this file.

Regeneration commands (once files exist):
- Nutrient: run ml/nutrient-prediction/src/pipeline.py -> reports/metrics.json + confusion_matrix.png
- Disease: run ml/disease-detection/src/evaluate.py with a VERIFIED clean split
- Latency: run ml/benchmarks/latency_pi.py on the Pi, 100 iterations, median + p95

Lost with the Azure subscription (do not fake):
- Historical telemetry (1,758+ records)
- Uptime percentage
- EC trajectory from live deployment
