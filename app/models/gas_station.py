"""
Modelo de gasolineras - Adaptado a tu estructura existente
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column, String, Float, DateTime, Boolean, Text, Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped

from . import Base


class GasStation(Base):
    """Modelo de gasolinera - Adaptado a tu estructura Supabase"""

    __tablename__ = "gas_stations"

    # Campos principales
    id: Mapped[str] = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = Column(String(200), nullable=False)
    brand: Mapped[Optional[str]] = Column(String(100), nullable=True)
    address: Mapped[str] = Column(Text, nullable=False)

    # Ubicación geográfica
    latitude: Mapped[float] = Column(Float, nullable=False)
    longitude: Mapped[float] = Column(Float, nullable=False)

    # Información administrativa
    city: Mapped[Optional[str]] = Column(String(100), nullable=True)
    state: Mapped[Optional[str]] = Column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = Column(String(10), nullable=True)
    country: Mapped[str] = Column(String(3), default="MX", nullable=False)

    # Identificadores externos
    cre_id: Mapped[Optional[str]] = Column(String(50), nullable=True, unique=True)
    external_id: Mapped[Optional[str]] = Column(String(100), nullable=True)

    # Contacto
    phone: Mapped[Optional[str]] = Column(String(20), nullable=True)
    website: Mapped[Optional[str]] = Column(String(255), nullable=True)

    # Horarios (mantenemos para compatibilidad pero no los usaremos mucho)
    hours_monday: Mapped[Optional[str]] = Column(String(50), nullable=True)
    hours_tuesday: Mapped[Optional[str]] = Column(String(50), nullable=True)
    hours_wednesday: Mapped[Optional[str]] = Column(String(50), nullable=True)
    hours_thursday: Mapped[Optional[str]] = Column(String(50), nullable=True)
    hours_friday: Mapped[Optional[str]] = Column(String(50), nullable=True)
    hours_saturday: Mapped[Optional[str]] = Column(String(50), nullable=True)
    hours_sunday: Mapped[Optional[str]] = Column(String(50), nullable=True)

    # Servicios disponibles
    has_magna: Mapped[bool] = Column(Boolean, default=True, nullable=False)
    has_premium: Mapped[bool] = Column(Boolean, default=True, nullable=False)
    has_diesel: Mapped[bool] = Column(Boolean, default=True, nullable=False)
    has_convenience_store: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    has_car_wash: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    has_restroom: Mapped[bool] = Column(Boolean, default=True, nullable=False)
    has_atm: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    has_air_pump: Mapped[bool] = Column(Boolean, default=True, nullable=False)

    # Estadísticas
    average_rating: Mapped[Optional[float]] = Column(Float, default=0.0, nullable=True)
    total_reviews: Mapped[int] = Column(Integer, default=0, nullable=False)
    total_reports: Mapped[int] = Column(Integer, default=0, nullable=False)

    # Estado
    is_active: Mapped[bool] = Column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    verification_date: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)

    # Metadatos
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_price_update: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    data_source: Mapped[str] = Column(String(20), default="user", nullable=False)

    # Relaciones
    prices = relationship("GasPrice", back_populates="gas_station", lazy="select")
    reviews = relationship("GasStationReview", back_populates="gas_station", lazy="select")
    user_reports = relationship("UserPriceReport", back_populates="gas_station", lazy="select")

    def __repr__(self) -> str:
        return f"<GasStation(id={self.id}, name={self.name}, city={self.city})>"

    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario para APIs"""
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "phone": self.phone,
            "website": self.website,
            "services": {
                "magna": self.has_magna,
                "premium": self.has_premium,
                "diesel": self.has_diesel,
                "convenience_store": self.has_convenience_store,
                "car_wash": self.has_car_wash,
                "restroom": self.has_restroom,
                "atm": self.has_atm,
                "air_pump": self.has_air_pump,
            },
            "stats": {
                "average_rating": self.average_rating,
                "total_reviews": self.total_reviews,
                "total_reports": self.total_reports,
            },
            "status": {
                "is_active": self.is_active,
                "is_verified": self.is_verified,
                "data_source": self.data_source,
            },
            "metadata": {
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None,
                "last_price_update": self.last_price_update.isoformat() if self.last_price_update else None,
            }
        }

    def calculate_distance(self, lat: float, lng: float) -> float:
        """Calcula la distancia en kilómetros a un punto dado"""
        from math import sin, cos, sqrt, atan2, radians

        R = 6371.0  # Radio de la Tierra en km
        lat1, lon1 = radians(self.latitude), radians(self.longitude)
        lat2, lon2 = radians(lat), radians(lng)
        dlon, dlat = lon2 - lon1, lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return round(R * c, 2)

    def get_current_prices(self) -> dict:
        """Obtiene los precios actuales de esta gasolinera"""
        current_prices = {}
        for price in self.prices:
            if price.is_current:
                current_prices[price.fuel_type] = {
                    "price": price.price,
                    "source": price.source,
                    "updated_at": price.created_at.isoformat(),
                    "confidence": price.confidence_score
                }
        return current_prices

    def has_fuel_type(self, fuel_type: str) -> bool:
        """Verifica si la gasolinera vende un tipo de combustible"""
        fuel_mapping = {
            "magna": self.has_magna,
            "premium": self.has_premium,
            "diesel": self.has_diesel
        }
        return fuel_mapping.get(fuel_type.lower(), False)