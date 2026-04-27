"""
weather.py
──────────
Fetches all live weather features needed by the flood model.

Sources
───────
  Open-Meteo Forecast + Elevation API (free, no key needed)
    → rainfall_mm                hourly precipitation (mm)
    → soil_moisture_pct          volumetric soil moisture % (top 7 cm)
    → river_discharge_m3s        river discharge (m³/s)
    → elevation_m                surface elevation (m)

  OpenWeatherMap FREE 2.5 API
    → rainfall_7day_cumulative_mm  sum of rain over next 7×24h forecast slots
    → humidity_pct                 current relative humidity (%)
    → temperature_c                current temperature (°C)

  Derived locally
    → month                        UTC calendar month (1–12)
    → runoff_coefficient           weighted model from soil + impervious +
                                   slope + rain intensity (0–1)

  Model defaults (passed through from request, not fetched)
    → river_water_level_m
    → slope_degree
    → land_use_type
    → drainage_density
    → ndvi
    → distance_to_river_km
"""

import httpx
from datetime import datetime, timezone

from app.schemas import ModelFeatures, PredictionRequest


# ── API endpoints ─────────────────────────────────────────────────────────────

OPEN_METEO_FORECAST_URL  = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_FLOOD_URL     = "https://flood.api.open-meteo.com/v1/flood"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
OWM_WEATHER_URL          = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL         = "https://api.openweathermap.org/data/2.5/forecast"
OWM_ONECALL_URL          = "https://api.openweathermap.org/data/3.0/onecall"

# Fraction of impervious surface (0–1); adjust per region / land use
IMPERVIOUS_SURFACE_FRACTION = 0.30


# ── Helpers ───────────────────────────────────────────────────────────────────

def latest_val(hourly_list: list, fallback: float = 0.0) -> float:
    """Return the most recent non-None value from an hourly list."""
    valid = [v for v in reversed(hourly_list) if v is not None]
    return float(valid[0]) if valid else fallback


# ── Open-Meteo: rainfall, soil moisture, river discharge, elevation ────────────

async def fetch_openmeteo(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
) -> dict:
    """
    Fetches flood-relevant variables from Open-Meteo (free, no API key).

    Fields returned:
      precipitation           → rainfall_mm   (latest hourly value, mm)
      soil_moisture_0_to_7cm  → soil_moisture_pct  (fraction × 100)
      river_discharge         → river_discharge_m3s
      /v1/elevation           → elevation_m
    """
    forecast_params = {
        "latitude":      lat,
        "longitude":     lon,
        "hourly": [
            "precipitation",
            "soil_moisture_0_to_7cm",
        ],
        "forecast_days": 1,
        "timezone":      "auto",
    }

    resp = await client.get(OPEN_METEO_FORECAST_URL, params=forecast_params, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()

    hourly = data.get("hourly", {})

    rainfall_mm        = latest_val(hourly.get("precipitation", []),          fallback=0.0)
    soil_moisture_frac = latest_val(hourly.get("soil_moisture_0_to_7cm", []), fallback=0.0)

    # river_discharge is NOT available in the forecast API.
    # It must be fetched from the dedicated Open-Meteo Flood API.
    river_discharge_m3s = 0.0
    try:
        flood_resp = await client.get(
            OPEN_METEO_FLOOD_URL,
            params={
                "latitude":      lat,
                "longitude":     lon,
                "daily":         "river_discharge",
                "forecast_days": 1,
            },
            timeout=15.0,
        )
        if flood_resp.is_success:
            flood_daily = flood_resp.json().get("daily", {})
            discharge_list = flood_daily.get("river_discharge", [])
            river_discharge_m3s = latest_val(discharge_list, fallback=0.0)
    except Exception:
        pass  # graceful fallback — model still runs with 0.0

    # Convert volumetric fraction (0–1) → percentage
    soil_moisture_pct = round(soil_moisture_frac * 100, 2)

    # Elevation — separate endpoint
    elev_resp = await client.get(
        OPEN_METEO_ELEVATION_URL,
        params={"latitude": lat, "longitude": lon},
        timeout=10.0,
    )
    elevation_m = 0.0
    if elev_resp.is_success:
        elev_list = elev_resp.json().get("elevation", [0.0])
        elevation_m = float(elev_list[0]) if elev_list else 0.0

    return {
        "rainfall_mm":          round(rainfall_mm,         2),
        "soil_moisture_pct":    round(soil_moisture_pct,   2),
        "river_discharge_m3s":  round(river_discharge_m3s, 2),
        "elevation_m":          round(elevation_m,          1),
    }


# ── OpenWeatherMap: 7-day cumulative rain, humidity, temperature ───────────────

async def fetch_openweather(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    api_key: str,
) -> dict:
    """
    Uses OWM /data/2.5/weather (current) for humidity + temperature.
    Uses OWM /data/3.0/onecall (daily) for 7-day cumulative rainfall;
    falls back to /data/2.5/forecast (3h slots) for free-tier keys.

    All wind units: standard (m/s) — not used here.
    """
    common = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}

    # Current conditions
    curr_resp = await client.get(OWM_WEATHER_URL, params=common, timeout=15.0)
    curr_resp.raise_for_status()
    curr = curr_resp.json()

    humidity_pct  = float(curr.get("main", {}).get("humidity", 70.0))
    temperature_c = float(curr.get("main", {}).get("temp",      25.0))

    # 7-day cumulative rainfall — try One Call 3.0 first
    rainfall_7day = 0.0

    onecall_resp = await client.get(
        OWM_ONECALL_URL,
        params={**common, "exclude": "current,minutely,hourly,alerts"},
        timeout=15.0,
    )
    if onecall_resp.is_success:
        for day in onecall_resp.json().get("daily", [])[:7]:
            rain = day.get("rain", 0.0)
            if isinstance(rain, (int, float)):
                rainfall_7day += rain
    else:
        # Free-tier fallback: 5-day / 3-hour forecast (56 slots ≈ 7 days)
        fc_resp = await client.get(
            OWM_FORECAST_URL,
            params={**common, "cnt": 56},
            timeout=15.0,
        )
        if fc_resp.is_success:
            for item in fc_resp.json().get("list", []):
                rainfall_7day += item.get("rain", {}).get("3h", 0.0)

    return {
        "rainfall_7day_cumulative_mm": round(rainfall_7day,  2),
        "humidity_pct":                round(humidity_pct,   1),
        "temperature_c":               round(temperature_c,  2),
    }


# ── Derived features ───────────────────────────────────────────────────────────

def derive_features(
    meteo: dict,
    slope_degree: float,
) -> dict:
    """
    Compute features derived from live + default inputs.

    month
    -----
    UTC calendar month (1–12).

    runoff_coefficient  (dimensionless, 0–1)
    ----------------------------------------
    Weighted component model (Rational Method approximation):
        C_soil       = soil_moisture_pct / 100        (wetter → more runoff)
        C_impervious = IMPERVIOUS_SURFACE_FRACTION     (urban → more runoff)
        C_slope      = min(slope_degree / 45, 1)      (steeper → more runoff)
        C_rain       = min(rainfall_mm, 50) / 50      (intense rain → more)

    Weights: soil=0.35, impervious=0.30, slope=0.20, rain=0.15
    Final value clipped to [0, 1].
    """
    month = datetime.now(tz=timezone.utc).month

    c_soil       = meteo["soil_moisture_pct"] / 100.0
    c_impervious = IMPERVIOUS_SURFACE_FRACTION
    c_slope      = min(slope_degree / 45.0, 1.0)
    c_rain       = min(meteo["rainfall_mm"], 50.0) / 50.0

    weights    = [0.35, 0.30, 0.20, 0.15]
    components = [c_soil, c_impervious, c_slope, c_rain]
    runoff_coefficient = sum(w * c for w, c in zip(weights, components))
    runoff_coefficient = round(max(0.0, min(1.0, runoff_coefficient)), 4)

    return {
        "month":              month,
        "runoff_coefficient": runoff_coefficient,
    }


# ── Master fetch ──────────────────────────────────────────────────────────────

async def fetch_all_features(
    lat: float,
    lon: float,
    openweather_api_key: str,
    request: PredictionRequest,
) -> ModelFeatures:
    """
    Orchestrates all API calls and returns a ModelFeatures instance
    ready to be passed to the flood model.

    Call order:
      1. Open-Meteo   → rainfall_mm, soil_moisture_pct,
                        river_discharge_m3s, elevation_m
      2. OpenWeather  → rainfall_7day_cumulative_mm,
                        humidity_pct, temperature_c
      3. Derived      → month, runoff_coefficient
      4. Defaults     → river_water_level_m, slope_degree, land_use_type,
                        drainage_density, ndvi, distance_to_river_km
                        (from request body — user can override)
    """
    # Resolve defaults (request overrides take precedence)
    slope_degree         = request.slope_degree          if request.slope_degree          is not None else 3.0
    river_water_level_m  = request.river_water_level_m   if request.river_water_level_m   is not None else 2.5
    land_use_type        = request.land_use_type          if request.land_use_type          is not None else 2
    drainage_density     = request.drainage_density       if request.drainage_density       is not None else 1.2
    ndvi                 = request.ndvi                   if request.ndvi                   is not None else 0.4
    distance_to_river_km = request.distance_to_river_km  if request.distance_to_river_km   is not None else 1.5

    async with httpx.AsyncClient(timeout=20.0) as client:
        meteo_data   = await fetch_openmeteo(client, lat, lon)
        weather_data = await fetch_openweather(client, lat, lon, openweather_api_key)

    derived = derive_features(meteo_data, slope_degree)

    return ModelFeatures(
        # ── Live fetched — Open-Meteo ─────────────────────────────────────────
        rainfall_mm                 = meteo_data["rainfall_mm"],
        soil_moisture_pct           = meteo_data["soil_moisture_pct"],
        river_discharge_m3s         = meteo_data["river_discharge_m3s"],
        elevation_m                 = meteo_data["elevation_m"],
        # ── Live fetched — OpenWeatherMap ─────────────────────────────────────
        rainfall_7day_cumulative_mm = weather_data["rainfall_7day_cumulative_mm"],
        humidity_pct                = weather_data["humidity_pct"],
        temperature_c               = weather_data["temperature_c"],
        # ── Derived ───────────────────────────────────────────────────────────
        month              = derived["month"],
        runoff_coefficient = derived["runoff_coefficient"],
        # ── Model defaults (override from request if provided) ────────────────
        river_water_level_m  = river_water_level_m,
        slope_degree         = slope_degree,
        land_use_type        = land_use_type,
        drainage_density     = drainage_density,
        ndvi                 = ndvi,
        distance_to_river_km = distance_to_river_km,
    )
