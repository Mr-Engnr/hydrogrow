# Results

On-device latency benchmarks are not yet recorded (tracked in the Roadmap).
Every table below regenerates from scripts once model files are recovered.

Regeneration commands (once files exist):
- Nutrient: run ml/nutrient-prediction/src/pipeline.py -> reports/metrics.json + confusion_matrix.png
- Disease: run ml/disease-detection/src/evaluate.py with a VERIFIED clean split
- Latency: run ml/benchmarks/latency_pi.py on the Pi, 100 iterations, median + p95

Lost with the Azure subscription (do not fake):
- Historical telemetry (1,758+ records)
- Uptime percentage
- EC trajectory from live deployment
