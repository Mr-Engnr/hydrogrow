# ML

PENDING: model files and training notebooks. Both models were trained in Google
Colab - check Colab/Drive for notebooks and downloadable weights before
declaring anything lost.

- disease-detection/    - MobileNetV2, 3 classes (Bacterial, Healthy, Septoria)
- nutrient-prediction/  - GradientBoosting on 7 sensor features, LOGO CV
- benchmarks/           - on-Pi latency measurement (needs Pi + models)

CRITICAL before publishing any accuracy number: verify the disease model's
train/test split. If the split can't be confirmed clean, re-split and re-evaluate.
