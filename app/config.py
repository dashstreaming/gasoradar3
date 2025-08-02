"""
Configuración simplificada de la aplicación Gasoradar
"""
import os
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings

# CARGAR .env EXPLÍCITAMENTE
from dotenv import load_dotenv
load_dotenv()  # Busca .env en el directorio actual


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────
    app_name: str = "Gasoradar"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, env="DEBUG")
    secret_key: str = Field(default="dev-secret-key", env="SECRET_KEY")

    # ── Database ───────────────────────────────────────
    database_url: str = Field(default="postgresql+asyncpg://localhost/gasoradar", env="DATABASE_URL")
    
    # ── Supabase ───────────────────────────────────────
    supabase_url: str = Field(default="", env="SUPABASE_URL")
    supabase_key: str = Field(default="", env="SUPABASE_KEY")
    supabase_service_key: str = Field(default="", env="SUPABASE_SERVICE_KEY")

    # ── CAPTCHA ────────────────────────────────────────
    recaptcha_site_key: str = Field(default="", env="RECAPTCHA_SITE_KEY")
    recaptcha_secret_key: str = Field(default="", env="RECAPTCHA_SECRET_KEY")

    # ── Maps ───────────────────────────────────────────
    google_maps_api_key: str = Field(default="", env="GOOGLE_MAPS_API_KEY")

    # ── Rate Limiting (protección contra sabotaje) ─────
    price_reports_per_hour: int = 3  # Máximo 3 reportes de precio por IP por hora
    reviews_per_day: int = 2         # Máximo 2 reseñas por IP por día

    # ── Validación dinámica de precios ─────────────────
    price_tolerance_percent: float = 15.0  # ±15% del promedio actual
    min_samples_for_validation: int = 5     # Mínimo de precios para calcular promedio
    price_data_freshness_days: int = 30     # Solo usar precios de últimos 30 días
    
    # Rangos de fallback si no hay datos suficientes
    fallback_price_ranges: dict = {
        "magna": {"min": 15.0, "max": 35.0},
        "premium": {"min": 18.0, "max": 40.0},
        "diesel": {"min": 16.0, "max": 38.0}
    }

    class Config:
        env_file = ".env"
        case_sensitive = False


# Instancia global
settings = Settings()


# Configuración CORS
CORS_SETTINGS = {
    "allow_origins": ["*"],  # En producción, especificar dominios
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}


# Configuración de logging
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        }
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["default"],
    },
}