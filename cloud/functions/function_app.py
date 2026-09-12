import azure.functions as func
import logging
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from azure.storage.blob import BlobServiceClient
from azure.digitaltwins.core import DigitalTwinsClient
from azure.identity import DefaultAzureCredential

app = func.FunctionApp()

def get_alert_status(key, value):
    if key == "ph":
        if value < 6.0: return "Low pH: Use pH Up Nutrient"
        if value > 8.0: return "High pH: Use pH Down Nutrient"
    elif key == "waterLevel" and value < 20:
        return "Critical: Low Water Level"
    elif key == "temperature" and (value < 18 or value > 30):
        return "Warning: Temperature out of range"
    return "Normal"


# 1. PROCESS TELEMETRY
@app.function_name(name="processTelemetry")
@app.event_hub_message_trigger(
    arg_name="events",
    event_hub_name=os.getenv("IOTHUB_EVENTHUB_NAME", "iothub-ehub-changeme"),
    connection="IotHubConnection"
)
def processTelemetry(events: func.EventHubEvent):
    try:
        message = events.get_body().decode('utf-8').strip()
        if not message:
            logging.warning("Empty message received")
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON: {e}")
            return

        # Unwrap if IoT Hub sends a batch array
        if isinstance(data, list):
            data = data[0]

        data["timestamp"] = datetime.utcnow().isoformat()
        logging.info(f"Received data: {data}")

        # Save to Blob
        connection_string = os.getenv("AzureWebJobsStorage")
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        blob_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.json"
        blob_client = blob_service_client.get_blob_client(container="telemetry-data", blob=blob_name)
        blob_client.upload_blob(json.dumps(data), overwrite=True)
        logging.info("Saved to Blob.")

        # Update Digital Twins
        try:
            dt_client = DigitalTwinsClient(os.getenv("ADT_URL"), DefaultAzureCredential())
            # Normalize sensor keys: the Pi sends "pH" and "water_level";
            # legacy senders use "ph"/"waterLevel". Map both to the twin keys.
            normalized = dict(data)
            normalized["ph"] = data.get("pH", data.get("ph"))
            normalized["waterLevel"] = data.get("water_level", data.get("waterLevel"))

            mapping = {
                "ph": "watertank1", "ec": "watertank1", "waterLevel": "watertank1",
                "temperature": "environment1", "humidity": "environment1"
            }
            for key, value in normalized.items():
                if key in mapping and value is not None:
                    twin_id = mapping[key]
                    patch = [{"op": "add", "path": f"/{key}", "value": value}]
                    if key in ["ph", "waterLevel", "temperature"]:
                        patch.append({"op": "add", "path": "/alertStatus", "value": get_alert_status(key, value)})
                    dt_client.update_digital_twin(twin_id, patch)

            # Plant twins: disease comes from the nested "disease_predictions"
            # object the Pi sends; nutrient_status is a single reading shared
            # by the planted twins (plant3 has no live nutrient reading).
            disease_predictions = data.get("disease_predictions", {})
            nutrient_data = data.get("nutrient_status", {})
            nutrient_label = nutrient_data.get("label")
            nutrient_conf = nutrient_data.get("confidence")

            planted_plants = ["plant1", "plant2"]
            plant_keys = ["plant1", "plant2", "plant3"]
            for plant_id in plant_keys:
                plant_patch = []

                # plant3 arrives as None when the hole is empty, so the
                # truthiness check skips it before any .get() is attempted.
                if plant_id in disease_predictions and disease_predictions[plant_id]:
                    plant_data = disease_predictions[plant_id]
                    disease_status = plant_data.get("label", "Unknown")
                    # Pi's disease model (MobileNetV2) outputs 0-1; Unity expects 0-100.
                    disease_confidence = float(plant_data.get("confidence", 0.0)) * 100
                    plant_patch.append({"op": "add", "path": "/disease_status", "value": disease_status})
                    plant_patch.append({"op": "add", "path": "/disease_confidence", "value": disease_confidence})
                    plant_patch.append({"op": "add", "path": "/diseased", "value": disease_status != "Healthy"})

                # Pi's nutrient model already sends confidence on a 0-100 scale; write as-is.
                if plant_id in planted_plants and nutrient_label is not None:
                    plant_patch.append({"op": "add", "path": "/nutrient_status", "value": nutrient_label})
                    plant_patch.append({"op": "add", "path": "/nutrient_confidence", "value": float(nutrient_conf or 0.0)})

                if plant_patch:
                    dt_client.update_digital_twin(plant_id, plant_patch)

            logging.info("Digital Twins updated.")
        except Exception as e:
            logging.error(f"DT update failed: {e}")

    except Exception as e:
        logging.error(f"Error: {e}")


# 2. GET TWIN
@app.route(route="twins/{twinId}", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_twin(req: func.HttpRequest) -> func.HttpResponse:
    try:
        twin_id = req.route_params.get("twinId")
        dt_client = DigitalTwinsClient(
            os.getenv("ADT_URL"),
            DefaultAzureCredential()
        )
        twin = dt_client.get_digital_twin(twin_id)
        return func.HttpResponse(
            json.dumps(twin),
            mimetype="application/json",
            status_code=200,
            headers={"Access-Control-Allow-Origin": "*"}
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
            headers={"Access-Control-Allow-Origin": "*"}
        )


# 3. ANALYTICS
@app.route(route="analytics", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def analytics(req: func.HttpRequest) -> func.HttpResponse:
    try:
        days = int(req.params.get("days", 7))
        connection_string = os.environ["AzureWebJobsStorage"]
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client("telemetry-data")
        cutoff = datetime.utcnow() - timedelta(days=days)

        daily_ph = defaultdict(list)
        daily_ec = defaultdict(list)
        daily_temp = defaultdict(list)
        daily_humidity = defaultdict(list)

        for blob in container_client.list_blobs():
            try:
                name = blob.name.replace(".json", "")
                date_part = name.split("_")[0]
                blob_date = datetime.strptime(date_part, "%Y%m%d")
                if blob_date >= cutoff:
                    blob_client = container_client.get_blob_client(blob)
                    data = json.loads(blob_client.download_blob().readall())
                    day_key = blob_date.strftime("%Y-%m-%d")
                    if "ph" in data: daily_ph[day_key].append(data["ph"])
                    if "ec" in data: daily_ec[day_key].append(data["ec"])
                    if "temperature" in data: daily_temp[day_key].append(data["temperature"])
                    if "humidity" in data: daily_humidity[day_key].append(data["humidity"])
            except Exception:
                continue

        labels = sorted(daily_ph.keys())
        def avg(lst): return round(sum(lst) / len(lst), 2) if lst else 0

        return func.HttpResponse(json.dumps({
            "labels": labels,
            "daily_avg_ph": [avg(daily_ph[d]) for d in labels],
            "daily_avg_ec": [avg(daily_ec[d]) for d in labels],
            "daily_avg_temp": [avg(daily_temp[d]) for d in labels],
            "daily_avg_humidity": [avg(daily_humidity[d]) for d in labels],
            "overall_week_avg_ph": avg([v for vals in daily_ph.values() for v in vals])
        }), mimetype="application/json", status_code=200)

    except Exception as e:
        return func.HttpResponse(str(e), status_code=500)


# 3. PREDICT DISEASE
@app.route(route="predict-disease", auth_level=func.AuthLevel.ANONYMOUS, methods=["POST"])
def predict_disease(req: func.HttpRequest) -> func.HttpResponse:
    import numpy as np
    import tflite_runtime.interpreter as tflite
    from PIL import Image
    import io

    try:
        image_data = req.get_body()
        if not image_data:
            return func.HttpResponse(json.dumps({"error": "No image provided"}), mimetype="application/json", status_code=400)

        model_path = os.path.join(os.path.dirname(__file__), 'models', 'disease_model.tflite')
        classes_path = os.path.join(os.path.dirname(__file__), 'models', 'disease_classes.json')

        interpreter = tflite.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        with open(classes_path) as f:
            classes = json.load(f)

        img = Image.open(io.BytesIO(image_data)).convert('RGB').resize((224, 224))
        img_array = np.expand_dims(np.array(img).astype(np.float32) / 255.0, axis=0)

        interpreter.set_tensor(input_details[0]['index'], img_array)
        interpreter.invoke()
        output = interpreter.get_tensor(output_details[0]['index'])

        predicted_class = classes[int(np.argmax(output[0]))]
        confidence = round(float(np.max(output[0])) * 100, 1)
        status = "healthy" if predicted_class == "Healthy" else "disease"

        result = {
            "prediction": predicted_class,
            "confidence": confidence,
            "status": status,
            "all_scores": {classes[i]: round(float(output[0][i]) * 100, 1) for i in range(len(classes))}
        }

        try:
            dt_client = DigitalTwinsClient(os.getenv("ADT_URL"), DefaultAzureCredential())
            dt_client.update_digital_twin("plant1", [
                {"op": "add", "path": "/disease", "value": (status == "disease")},
                {"op": "add", "path": "/alertStatus", "value": f"Status: {predicted_class}"}
            ])
        except Exception as e:
            logging.error(f"Plant twin update failed: {e}")

        return func.HttpResponse(json.dumps(result), mimetype="application/json", status_code=200, headers={"Access-Control-Allow-Origin": "*"})

    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), mimetype="application/json", status_code=500)
    