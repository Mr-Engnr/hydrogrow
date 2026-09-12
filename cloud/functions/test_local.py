#!/usr/bin/env python
"""Test the predict_disease function locally"""

import json
import numpy as np
import tensorflow as tf
from PIL import Image
import io
import os

# Load model
model_path = os.path.join(os.path.dirname(__file__), 'models', 'disease_model.tflite')
classes_path = os.path.join(os.path.dirname(__file__), 'models', 'disease_classes.json')

print(f"Model path: {model_path}")
print(f"Model exists: {os.path.exists(model_path)}")
print(f"Classes path: {classes_path}")
print(f"Classes exist: {os.path.exists(classes_path)}")

try:
    # Load the model
    interpreter = tf.lite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    print(f"\nInput details: {input_details}")
    print(f"Output details: {output_details}")
    
    # Load classes
    with open(classes_path) as f:
        classes = json.load(f)
    print(f"\nClasses: {classes}")
    
    # Test with a sample image
    test_image_path = r"C:\Users\User\Downloads\image.jpg"
    if os.path.exists(test_image_path):
        print(f"\nTesting with: {test_image_path}")
        img = Image.open(test_image_path).convert('RGB').resize((224, 224))
        img_array = np.array(img).astype(np.float32) / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        
        print(f"Image array shape: {img_array.shape}")
        print(f"Image array dtype: {img_array.dtype}")
        print(f"Image array min/max: {img_array.min()}/{img_array.max()}")
        
        # Run inference
        interpreter.set_tensor(input_details[0]['index'], img_array)
        interpreter.invoke()
        output = interpreter.get_tensor(output_details[0]['index'])
        
        print(f"\nOutput shape: {output.shape}")
        print(f"Output: {output}")
        
        predicted_class = classes[int(np.argmax(output[0]))]
        confidence = round(float(np.max(output[0])) * 100, 1)
        all_scores = {classes[i]: round(float(output[0][i]) * 100, 1) for i in range(len(classes))}
        
        print(f"\nPrediction: {predicted_class}")
        print(f"Confidence: {confidence}%")
        print(f"All scores: {all_scores}")
        print("\n✅ SUCCESS!")
    else:
        print(f"Test image not found: {test_image_path}")
        
except Exception as e:
    print(f"\n❌ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
