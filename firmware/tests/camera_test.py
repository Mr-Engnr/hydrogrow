import os
import time
import numpy as np
from datetime import datetime
from picamera2 import Picamera2
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image as keras_image

# -- CONFIG ------------------------------------------------------------
DATA_DIR     = os.getenv("HYDROGROW_DATA_DIR", os.path.expanduser("~"))
SAVE_DIR     = os.path.join(DATA_DIR, "captures")
MODEL_PATH   = os.path.join(DATA_DIR, "models", "lettuce_mobilenetv2.h5")
CAPTURE_WAIT = 10   # seconds before each capture
RESULT_WAIT  = 5    # seconds after showing result
IMG_SIZE     = (224, 224)

CLASS_LABELS = ['Bacterial', 'Healthy', 'Septoria_blight_on_lettuce']

# -- SETUP ---------------------------------------------------------------
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

print("Loading disease model...")
model = load_model(MODEL_PATH)
print("Model loaded.\n")

print("Starting camera...")
cam = Picamera2()
config = cam.create_still_configuration(main={"size": (1280, 720)})
cam.configure(config)
cam.start()
time.sleep(2)
print("Camera ready.\n")

def predict(img_path):
    img  = keras_image.load_img(img_path, target_size=IMG_SIZE)
    arr  = keras_image.img_to_array(img) / 255.0
    arr  = np.expand_dims(arr, axis=0)
    probs = model.predict(arr, verbose=0)[0]
    idx   = int(np.argmax(probs))
    label = CLASS_LABELS[idx]
    conf  = float(probs[idx]) * 100
    return label, conf, probs

# -- MAIN LOOP -------------------------------------------------------------
count = 0
try:
    while True:
        count += 1
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(SAVE_DIR, f"plant_{ts}.jpg")

        # Capture
        cam.capture_file(filepath)
        print(f"[{datetime.now():%H:%M:%S}] #{count} Image captured -> {filepath}")

        # Predict
        label, conf, probs = predict(filepath)
        is_diseased = label != 'Healthy'
        status = "DISEASED" if is_diseased else "HEALTHY"

        print(f"  Result: {status} -- {label} ({conf:.1f}%)")
        for i, p in enumerate(probs):
            print(f"    {CLASS_LABELS[i]:<28} {p*100:5.1f}%")

        if is_diseased:
            print(f"  ALERT: Plant shows signs of {label}")
        else:
            print("  Plant looks healthy")

        print(f"  Waiting {RESULT_WAIT}s before next cycle...\n")
        time.sleep(RESULT_WAIT)

        print(f"  Waiting {CAPTURE_WAIT}s before next capture...")
        time.sleep(CAPTURE_WAIT)

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    cam.stop()
    print(f"Camera stopped. Total images captured: {count}")
