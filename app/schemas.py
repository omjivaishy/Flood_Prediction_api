"""
schemas.py
──────────
Request / response models for Flood Prediction API.

Model input vector (15 features, exact order):
    rainfall_mm, soil_moisture_pct, river_discharge_m3s, elevation_m,
    rainfall_7day_cumulative_mm, humidity_pct, temperature_c,
    month, runoff_coefficient,
    river_water_level_m, slope_degree, land_use_type,
    drainage_density, ndvi, distance_to_river_km
"""

from pydantic import BaseModel, Field
from typing import Optional


class ModelFeatures(BaseModel):
    """15 features fed into model.pkl."""

    # ── Fetched from Open-Meteo ────────────────────────────────────────────────
    rainfall_mm: float = Field(
        ..., description="Hourly precipitation (mm) — Open-Meteo"
    )
    soil_moisture_pct: float = Field(
        ..., description="Volumetric soil moisture % (top 7 cm) — Open-Meteo"
    )
    river_discharge_m3s: float = Field(
        ..., description="River discharge (m³/s) — Open-Meteo"
    )
    elevation_m: float = Field(
        ..., description="Surface elevation (m) — Open-Meteo"
    )

    # ── Fetched from OpenWeatherMap ────────────────────────────────────────────
    rainfall_7day_cumulative_mm: float = Field(
        ..., description="7-day cumulative rainfall (mm) — OpenWeatherMap"
    )
    humidity_pct: float = Field(
        ..., description="Current relative humidity (%) — OpenWeatherMap"
    )
    temperature_c: float = Field(
        ..., description="Current temperature (°C) — OpenWeatherMap"
    )

    # ── Derived ───────────────────────────────────────────────────────────────
    month: int = Field(
        ..., description="Calendar month (1–12) — derived from UTC time"
    )
    runoff_coefficient: float = Field(
        ...,
        description=(
            "Dimensionless runoff ratio (0–1) — derived from "
            "soil_moisture + impervious_surface + slope + rainfall_mm"
        ),
    )

    # ── Model defaults (user-overridable) ─────────────────────────────────────
    river_water_level_m: float = Field(
        default=2.5, description="River water level (m above gauge zero) — default value"
    )
    slope_degree: float = Field(
        default=3.0, description="Terrain slope (degrees) — default value"
    )
    land_use_type: int = Field(
        default=2,
        description="Land use code: 1=urban 2=agricultural 3=forest 4=wetland — default value",
    )
    drainage_density: float = Field(
        default=1.2, description="Drainage density (km/km²) — default value"
    )
    ndvi: float = Field(
        default=0.4, description="Normalized Difference Vegetation Index (0–1) — default value"
    )
    distance_to_river_km: float = Field(
        default=1.5, description="Distance to nearest river (km) — default value"
    )


class PredictionRequest(BaseModel):
    lat: float = Field(..., ge=-90,  le=90,  description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")

    # Optional overrides for model default parameters
    river_water_level_m: Optional[float] = Field(
        default=None, description="Override default river water level (m)"
    )
    slope_degree: Optional[float] = Field(
        default=None, description="Override default slope (degrees)"
    )
    land_use_type: Optional[int] = Field(
        default=None, description="Override default land use type (1–4)"
    )
    drainage_density: Optional[float] = Field(
        default=None, description="Override default drainage density (km/km²)"
    )
    ndvi: Optional[float] = Field(
        default=None, description="Override default NDVI (0–1)"
    )
    distance_to_river_km: Optional[float] = Field(
        default=None, description="Override default distance to river (km)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "lat": 23.1,
                "lon": 85.3,
                "river_water_level_m": 3.8,
                "slope_degree": 5.0,
                "land_use_type": 1,
                "drainage_density": 2.1,
                "ndvi": 0.3,
                "distance_to_river_km": 0.5,
            }
        }


class PredictionResult(BaseModel):
    flood: float = Field(
        ..., description="Flood probability (0.00–1.00)"
    )
    flood_probability: float = Field(
        ..., description="Raw model output rounded to 2 decimal places (0.00–1.00)"
    )
    confidence: float = Field(
        ..., description="Model confidence score (0.0–1.0)"
    )
    confidence_pct: str = Field(
        ..., description="Confidence as percentage string e.g. '87.30%'"
    )
    probability_flood: float = Field(
        ..., description="Probability of flood class (0.0–1.0)"
    )
    probability_safe: float = Field(
        ..., description="Probability of no-flood class (0.0–1.0)"
    )
    verdict: str = Field(
        ..., description="Human-readable verdict string"
    )


class PredictionResponse(BaseModel):
    lat:       float
    lon:       float
    result:    PredictionResult
    features:  ModelFeatures
    timestamp: str
