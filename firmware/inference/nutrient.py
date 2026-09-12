import os
import joblib
import numpy as np

# Load nutrient model
MODEL_PATH = os.getenv(
    "NUTRIENT_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..",
                 "ml", "nutrient-prediction", "models", "nutrient_model.pkl"),
)

pipeline = joblib.load(MODEL_PATH)

# Feature order must match exactly what model was trained on
FEATURE_ORDER = [
    'pH', 'EC', 'N_Concentration', 'P_Concentration', 'K_Concentration',
    'Air_Temp', 'Humidity', 'Water_Level', 'Growth_Day', 'Treatment_%'
]

def estimate_npk(ph, ec):
    """
    Estimate N, P, K concentrations from pH and EC.
    EC (mS/cm) scales total nutrient load.
    pH shifts availability of each nutrient.
    Think of EC as total budget, pH as how that budget is split.
    """
    # Base concentrations from EC (linear approximation)
    n = ec * 40.0   # N is the biggest consumer of EC
    p = ec * 10.0
    k = ec * 20.0

    # pH corrections - nutrient availability drops outside optimal range
    if ph < 5.5:
        p *= 0.6
        k *= 0.7
    elif ph > 7.0:
        n *= 0.7

    return round(n, 2), round(p, 2), round(k, 2)


def predict_nutrient_status(ph, ec, air_temp, humidity, water_level,
                             growth_day=14, treatment_pct=100.0):
    """
    Predict nutrient deficiency from Pi sensor readings.

    Args:
        ph          : pH sensor reading
        ec          : EC sensor reading (mS/cm)
        air_temp    : air temperature (C)
        humidity    : relative humidity (%)
        water_level : water level reading
        growth_day  : day in grow cycle (default 14)
        treatment_pct: nutrient solution strength % (default 100)

    Returns:
        label      : 'Healthy', 'Nitrogen_Deficient', 'Phosphorus_Deficient', 'Potassium_Deficient'
        confidence : float 0-100
    """
    n, p, k = estimate_npk(ph, ec)

    input_values = [
        ph, ec, n, p, k,
        air_temp, humidity, water_level,
        growth_day, treatment_pct
    ]

    input_array = np.array(input_values).reshape(1, -1)

    label = pipeline.predict(input_array)[0]
    confidence = round(pipeline.predict_proba(input_array)[0].max() * 100, 1)

    return label, confidence
