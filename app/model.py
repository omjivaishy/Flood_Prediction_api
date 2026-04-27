"""
model.py
────────
Loads model.pkl, runs flood prediction, returns probability + verdict.

Place model.pkl in the project root (same folder as main.py).

Model output:
  - Your model returns a value rounded to 2 decimal places.
  - If classifier with predict_proba  → uses probability directly.
  - If regressor returning 0.00–1.00  → treats value as probability.
  - Threshold for flood=1             → flood_probability >= 0.50
"""

import os
import numpy as np
import joblib

from app.schemas import ModelFeatures, PredictionResult


MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model.pkl")

# Feature order MUST match the column order used during model training
FEATURE_ORDER = [
    "rainfall_mm",
    "soil_moisture_pct",
    "river_discharge_m3s",
    "elevation_m",
    "rainfall_7day_cumulative_mm",
    "humidity_pct",
    "temperature_c",
    "month",
    "runoff_coefficient",
    "river_water_level_m",
    "slope_degree",
    "land_use_type",
    "drainage_density",
    "ndvi",
    "distance_to_river_km",
]


class FloodModel:
    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"model.pkl not found at {os.path.abspath(MODEL_PATH)}. "
                "Place your trained model.pkl in the project root."
            )
        self.clf       = joblib.load(MODEL_PATH)
        self.is_loaded = True
        print(f"[model] Loaded: {type(self.clf).__name__}")

    def _to_vector(self, f: ModelFeatures) -> np.ndarray:
        return np.array([[getattr(f, col) for col in FEATURE_ORDER]], dtype=np.float32)

    def predict(self, features: ModelFeatures) -> PredictionResult:
        vec = self._to_vector(features)

        if hasattr(self.clf, "predict_proba"):
            # Classifier path — predict_proba returns [P(0), P(1)]
            proba            = self.clf.predict_proba(vec)[0]
            prob_flood       = round(float(proba[1]), 2)   # 2 decimal places
            prob_safe        = round(float(proba[0]), 2)
            flood_probability = prob_flood
            flood            = round(prob_flood, 2)
            confidence       = round(float(max(prob_flood, prob_safe)), 4)

        else:
            # Regressor path — model returns a single 0.00–1.00 score
            raw_score         = float(self.clf.predict(vec)[0])
            flood_probability = round(np.clip(raw_score, 0.0, 1.0), 2)   # 2 decimal places
            flood             = round(flood_probability, 2)
            prob_flood        = flood_probability
            prob_safe         = round(1.0 - flood_probability, 2)
            confidence        = round(abs(flood_probability - 0.5) * 2, 4)  # distance from boundary

        confidence_pct = f"{confidence * 100:.2f}%"

        # ── Verdict ───────────────────────────────────────────────────────────
        if flood == 1:
            if confidence >= 0.85:
                verdict = f"FLOOD HIGHLY LIKELY ({confidence_pct} confidence)"
            elif confidence >= 0.65:
                verdict = f"FLOOD PREDICTED ({confidence_pct} confidence)"
            else:
                verdict = f"FLOOD POSSIBLE — low confidence ({confidence_pct})"
        else:
            if confidence >= 0.85:
                verdict = f"No flood ({confidence_pct} confidence)"
            elif confidence >= 0.65:
                verdict = f"No flood predicted ({confidence_pct} confidence)"
            else:
                verdict = f"No flood — borderline ({confidence_pct} confidence)"

        return PredictionResult(
            flood              = flood,
            flood_probability  = flood_probability,
            confidence         = confidence,
            confidence_pct     = confidence_pct,
            probability_flood  = prob_flood,
            probability_safe   = prob_safe,
            verdict            = verdict,
        )
