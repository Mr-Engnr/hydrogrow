# MISSING.md - internal tracker, delete before making repo public

Status: RECOVERED / BLOCKED (needs external access) / TODO / LOST

## RECOVERED this session
- Backend (Express) source -> backend/
- Dashboard (React) source -> dashboard/
- Azure Function source -> cloud/functions/ (function_app.py, host.json, requirements.txt)
- Digital Twin plant model -> cloud/digital-twin/plant_model_v2.json
- Pi firmware main.py (842 lines: SensorReader, PumpController, Display, HydroController)
- pi_inference.py -> firmware/inference/nutrient.py
- Two hardware bring-up test scripts -> firmware/tests/
- nutrient_model.pkl (920 KB) -> ml/nutrient-prediction/models/ (small enough to commit)
- Disease training notebook -> ml/disease-detection/notebooks/train_mobilenetv2.ipynb
- Nutrient training notebook -> ml/nutrient-prediction/notebooks/train_nutrient_model.ipynb
- Disease metrics: 95.25% acc, macro F1 0.9501, per-class table (569 test images)
- Nutrient metrics: GB/RF/SVM 97.92%, DT 95.83%, KNN 89.58% (48 test samples)

## Still needed
| Item | Target | Status | Lead |
|---|---|---|---|
| Camera/disease inference module | firmware/inference/disease.py | BLOCKED | Pi SD card |
| IoT Hub publisher (send_data.py) | firmware/cloud/iot_client.py | BLOCKED | Pi SD card |
| firmware refactor into sensors/ control/ | firmware/ | TODO | main.py is monolithic but well-structured; split is optional polish |
| mock/replay.py hardware-free mode | firmware/mock/ | TODO | Needs a telemetry sample; none survived |
| lettuce_mobilenetv2.keras weights | GitHub Release | BLOCKED | Colab runtime output, or Pi |
| hydrogrow_final_v6.xlsx | ml/nutrient-prediction/data/ | TODO | Was read from /content/ in Colab - re-download from Drive |
| watertank/environment DTDL JSON | cloud/digital-twin/ | BLOCKED | Ask collaborator (plant_model_v2.json recovered) |
| disease_model.tflite + disease_classes.json | cloud/functions/models/ | BLOCKED | Referenced by predict_disease endpoint |
| Telemetry history (1,758 records) | data/samples/ | LOST | Azure storage disabled |
| On-Pi latency benchmarks | docs/results.md | BLOCKED | Needs Pi + weights |

## Notebook cleanup before publishing
1. model_disease.ipynb has a STALE hardcoded summary cell near the bottom
   ("COPY THIS INTO YOUR THESIS") printing Bacterial F1 0.11 / Septoria F1 0.25
   with 4 and 3 samples. These contradict the real sklearn report in the same
   notebook (0.92 / 0.95, 172 and 173 samples). DELETE that cell.
   If those numbers reached the paper draft, correct them there too.
2. Export confusion_matrix.png and training_curves.png from both notebooks into
   ml/*/reports/ - the notebooks already save them, just need the files.
3. Strip Colab-specific paths (/content/) or document them.

## Media (from Cowork manifest)
| Item | Status |
|---|---|
| Dashboard plant-health screenshot | TODO - run dashboard locally, screenshot |
| Dashboard live-view screenshot | TODO - same session |
| Perfboard top-down macro | BLOCKED - needs rig |
| Pumps dosing clip | BLOCKED - needs rig |
| Growth cycle strip | DEFERRED - roadmap item |
| Hero demo GIF (IMG_5325.MOV 00:04-00:20) | TODO - Cowork pass 2 |
| Unity twin GIF (IMG_5325.MOV 00:12-00:20) | TODO - Cowork pass 2 |
| rig-annotated (Labeled.png) | TODO - crop caption |
| architecture.png redraw | TODO |
| wiring-schematic.png | TODO - Fritzing |

## Code fixes applied this session
- function_app.py line 204-205: `_file_` -> `__file__`. This was a real NameError
  that would have 500'd the predict-disease endpoint on every call.
- function_app.py line 125: hardcoded Digital Twins hostname -> os.getenv("ADT_URL"),
  matching how the other two DT clients in the same file already read it.
- function_app.py line 28: hardcoded event hub name -> os.getenv("IOTHUB_EVENTHUB_NAME").
- local.settings.json NOT copied. Contained live storage AccountKey and IoT Hub
  SharedAccessKey in plaintext. Redacted local.settings.example.json created instead.
  BOTH KEYS SHOULD BE CONSIDERED BURNED.

## Firmware fixes applied this session
- test_hardware_full.py arrived wrapped in a bash heredoc (`cat > ~/test_all.py << EOF`)
  so it was not valid Python. Wrapper stripped; file now parses and runs directly.
- main.py: hardcoded /home/saad/ paths -> HYDROGROW_DATA_DIR env var defaulting to ~
- inference/nutrient.py: hardcoded model path -> NUTRIENT_MODEL_PATH env var
  defaulting to the in-repo ml/nutrient-prediction/models/ location
- firmware/requirements.txt created. scikit-learn PINNED to 1.8.0 because the pkl
  was serialized with that version; a mismatch can silently change predictions.

## Hygiene
- HF_API_KEY: rotate at huggingface.co (still live)
- Azure keys: moot, subscription disabled
- Old web repo git history verified CLEAN (.env and users.json never committed)
- users.json and .env deliberately excluded from this folder
- Confirm before publishing Unity/DT visuals
