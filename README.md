# Flood Prediction API

Predicts flood risk from latitude & longitude using live weather data + your trained model.

## Project Structure

```
flood-api/
├── main.py                 ← entry point  (python main.py)
├── model.pkl               ← put YOUR trained model here
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
└── app/
    ├── __init__.py
    ├── main.py             ← FastAPI routes
    ├── schemas.py          ← Pydantic request / response models
    ├── weather.py          ← Open-Meteo + OpenWeather + derived features
    ├── model.py            ← loads model.pkl, runs inference
    └── config.py           ← env settings
```

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# → edit .env and add your OpenWeatherMap API key

# 3. Drop your trained model
cp /path/to/your/model.pkl model.pkl

# 4. Run
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger UI → http://localhost:8000/docs

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health + model status |
| GET | `/predict?lat=&lon=` | Predict with defaults |
| POST | `/predict` | Predict with optional overrides |
| GET | `/features?lat=&lon=` | Debug: raw features, no inference |

---

## API Usage

### GET — minimal (uses all defaults)
```
GET /predict?lat=23.1&lon=85.3
```

### POST — with default overrides
```json
POST /predict
{
  "lat": 23.1,
  "lon": 85.3,
  "river_water_level_m": 3.8,
  "slope_degree": 5.0,
  "land_use_type": 1,
  "drainage_density": 2.1,
  "ndvi": 0.3,
  "distance_to_river_km": 0.5
}
```

### Response
```json
{
  "lat": 23.1,
  "lon": 85.3,
  "result": {
    "flood": 1,
    "flood_probability": 0.83,
    "confidence": 0.66,
    "confidence_pct": "66.00%",
    "probability_flood": 0.83,
    "probability_safe": 0.17,
    "verdict": "FLOOD PREDICTED (66.00% confidence)"
  },
  "features": {
    "rainfall_mm": 12.4,
    "soil_moisture_pct": 72.3,
    "river_discharge_m3s": 340.1,
    "elevation_m": 58.0,
    "rainfall_7day_cumulative_mm": 94.5,
    "humidity_pct": 88.0,
    "temperature_c": 28.3,
    "month": 7,
    "runoff_coefficient": 0.5275,
    "river_water_level_m": 3.8,
    "slope_degree": 5.0,
    "land_use_type": 1,
    "drainage_density": 2.1,
    "ndvi": 0.3,
    "distance_to_river_km": 0.5
  },
  "timestamp": "2026-04-27T10:00:00Z"
}
```

---

## Features & Sources

| Feature | Source | Notes |
|---------|--------|-------|
| `rainfall_mm` | Open-Meteo | Latest hourly `precipitation` |
| `soil_moisture_pct` | Open-Meteo | `soil_moisture_0_to_7cm` × 100 |
| `river_discharge_m3s` | Open-Meteo | `river_discharge` hourly |
| `elevation_m` | Open-Meteo | `/v1/elevation` endpoint |
| `rainfall_7day_cumulative_mm` | OpenWeatherMap | Sum of daily rain, 7 days |
| `humidity_pct` | OpenWeatherMap | Current relative humidity |
| `temperature_c` | OpenWeatherMap | Current temperature (°C) |
| `month` | Derived | UTC calendar month (1–12) |
| `runoff_coefficient` | Derived | Weighted: soil×0.35 + impervious×0.30 + slope×0.20 + rain×0.15 |
| `river_water_level_m` | Default: 2.5 | Overridable in POST body |
| `slope_degree` | Default: 3.0 | Overridable in POST body |
| `land_use_type` | Default: 2 | Overridable in POST body (1=urban 2=agri 3=forest 4=wetland) |
| `drainage_density` | Default: 1.2 | Overridable in POST body |
| `ndvi` | Default: 0.4 | Overridable in POST body |
| `distance_to_river_km` | Default: 1.5 | Overridable in POST body |

---

## Plugging in Your Model

Open `app/model.py` and check:

1. **`FEATURE_ORDER`** list — must match column order from training (15 features).
2. **Classifier vs regressor** — both paths handled automatically:
   - If your model has `predict_proba` → uses `proba[1]` as flood probability.
   - If regressor returning 0.00–1.00 → treats output directly as score.
3. **Threshold** — default is `>= 0.50` for `flood = 1`. Adjust in `model.py`.
4. **Verdict tiers** — confidence bands (85%, 65%) in `model.py` → tune as needed.

---

## Docker

```bash
docker build -t flood-api .
docker run -p 8000:8000 \
  -v $(pwd)/model.pkl:/api/model.pkl \
  --env-file .env \
  flood-api
```
