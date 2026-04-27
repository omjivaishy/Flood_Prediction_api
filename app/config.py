"""
config.py
─────────
Single source of truth for all configuration.
Loads from .env file automatically.

Usage anywhere in the app:
    from app.config import settings
    key = settings.openweather_api_key
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # OpenWeatherMap
    openweather_api_key: str

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
