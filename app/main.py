"""
app/main.py
───────────
FastAPI routes. API key is loaded from .env — not passed in URLs.

Endpoints:
    GET  /              info
    GET  /health
    GET  /predict       ?lat=&lon=
    POST /predict       JSON body: {"lat": ..., "lon": ...}
    GET  /features      ?lat=&lon=   (debug — raw features, no model)
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import logging

from app.config import settings
from app.schemas import PredictionRequest, PredictionResponse, ModelFeatures
from app.weather import fetch_all_features
from app.model import FloodModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Flood Prediction API",
    description=(
        "Predicts flood risk from latitude & longitude using live weather data.\n\n"
        "**Sources:**\n"
        "- Open-Meteo (rainfall, soil moisture, river discharge, elevation)\n"
        "- OpenWeatherMap 2.5 (7-day cumulative rainfall, humidity, temperature)\n"
        "- Derived (month, runoff coefficient)\n\n"
        "**Model defaults (overridable in POST body):**\n"
        "- river_water_level_m = 2.5\n"
        "- slope_degree = 3.0\n"
        "- land_use_type = 2  (1=urban 2=agricultural 3=forest 4=wetland)\n"
        "- drainage_density = 1.2\n"
        "- ndvi = 0.4\n"
        "- distance_to_river_km = 1.5\n\n"
        "**Output:** `flood: 0 or 1` + flood_probability (2 dp) + confidence + verdict"
    ),
    version="1.0.0",
    contact={
        "name": "Flood AI",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model = FloodModel()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"], summary="API info")
async def root():
    return {
        "service": "Flood Prediction API",
        "version": "1.0.0",
        "status":  "running",
        "docs":    "/docs",
        "endpoints": {
            "predict_get":  "GET  /predict?lat=&lon=",
            "predict_post": "POST /predict  {lat, lon, ...overrides}",
            "features":     "GET  /features?lat=&lon=  (debug)",
            "health":       "GET  /health",
        },
    }


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status":       "healthy",
        "model_loaded": model.is_loaded,
        "api_key_set":  bool(settings.openweather_api_key),
    }


@app.get(
    "/predict",
    response_model=PredictionResponse,
    tags=["Prediction"],
    summary="Predict flood — GET",
)
async def predict_get(
    lat: float = Query(..., ge=-90,  le=90,  description="Latitude",  example=23.1),
    lon: float = Query(..., ge=-180, le=180, description="Longitude", example=85.3),
):
    """
    Returns flood prediction for the given coordinates.
    Model default parameters are used (not overridable via GET).
    Use POST /predict to override defaults.
    """
    req = PredictionRequest(lat=lat, lon=lon)
    return await _predict(req)


@app.post(
    "/predict",
    response_model=PredictionResponse,
    tags=["Prediction"],
    summary="Predict flood — POST",
)
async def predict_post(req: PredictionRequest):
    """
    Same as GET but accepts a JSON body.
    Optional fields to override model defaults:
    - river_water_level_m
    - slope_degree
    - land_use_type
    - drainage_density
    - ndvi
    - distance_to_river_km
    """
    return await _predict(req)


@app.get(
    "/features",
    response_model=ModelFeatures,
    tags=["Debug"],
    summary="Raw features (no model)",
)
async def get_features(
    lat: float = Query(..., ge=-90,  le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """Returns the 15 features that would be fed into the model, without running inference."""
    req = PredictionRequest(lat=lat, lon=lon)
    try:
        return await fetch_all_features(lat, lon, settings.openweather_api_key, req)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── Internal ──────────────────────────────────────────────────────────────────

async def _predict(req: PredictionRequest) -> PredictionResponse:
    logger.info(f"Prediction request: lat={req.lat}, lon={req.lon}")

    try:
        features = await fetch_all_features(
            req.lat, req.lon, settings.openweather_api_key, req
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather fetch failed: {e}")

    try:
        result = model.predict(features)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model error: {e}")

    return PredictionResponse(
        lat       = req.lat,
        lon       = req.lon,
        result    = result,
        features  = features,
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
