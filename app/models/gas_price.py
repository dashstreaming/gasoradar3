"""
Modelo de precios de combustibles - Adaptado a tu estructura existente
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, String, Float, DateTime, Boolean, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped

from . import Base


class GasPrice(Base):
    """Modelo de precios de combustible - Adaptado a tu estructura Supabase"""
    
    __tablename__ = "gas_prices"
    
    # Campos principales
    id: Mapped[str] = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # Relación con gasolinera
    gas_station_id: Mapped[str] = Column(
        UUID(as_uuid=False), 
        ForeignKey("gas_stations.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Información del precio
    fuel_type: Mapped[str] = Column(String(20), nullable=False)  # magna, premium, diesel
    price: Mapped[float] = Column(Float, nullable=False)
    source: Mapped[str] = Column(String(20), nullable=False)  # user, cre, system
    
    # Metadatos del reporte
    reported_by: Mapped[Optional[str]] = Column(String(100), nullable=True)  # IP o user ID
    confidence_score: Mapped[float] = Column(Float, default=1.0, nullable=False)  # 0.0 - 1.0
    validation_status: Mapped[str] = Column(String(20), default="pending", nullable=False)  # pending, validated, rejected
    
    # Información adicional
    notes: Mapped[Optional[str]] = Column(Text, nullable=True)
    pump_number: Mapped[Optional[int]] = Column(Integer, nullable=True)
    
    # Control de versiones
    is_current: Mapped[bool] = Column(Boolean, default=True, nullable=False)
    replaced_by_id: Mapped[Optional[str]] = Column(UUID(as_uuid=False), ForeignKey("gas_prices.id"), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    valid_until: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    
    # Relaciones
    gas_station = relationship("GasStation", back_populates="prices")
    
    def __repr__(self) -> str:
        return f"<GasPrice(id={self.id}, fuel_type={self.fuel_type}, price={self.price}, source={self.source})>"
    
    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario"""
        return {
            "id": self.id,
            "gas_station_id": self.gas_station_id,
            "fuel_type": self.fuel_type,
            "price": self.price,
            "source": self.source,
            "reported_by": self.reported_by,
            "confidence_score": self.confidence_score,
            "validation_status": self.validation_status,
            "notes": self.notes,
            "pump_number": self.pump_number,
            "is_current": self.is_current,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
        }
    
    def calculate_age_hours(self) -> float:
        """Calcula la edad del precio en horas"""
        return (datetime.utcnow() - self.created_at).total_seconds() / 3600
    
    def get_freshness_score(self) -> float:
        """
        Obtiene un score de frescura del precio (1.0 = muy fresco, 0.0 = muy viejo)
        """
        age_hours = self.calculate_age_hours()
        
        if age_hours <= 1:
            return 1.0
        elif age_hours <= 6:
            return 0.9
        elif age_hours <= 24:
            return 0.7
        elif age_hours <= 48:
            return 0.5
        elif age_hours <= 168:  # 1 semana
            return 0.3
        else:
            return 0.1
    
    def is_fresh(self) -> bool:
        """Verifica si el precio es considerado fresco (menos de 24 horas)"""
        return self.calculate_age_hours() <= 24
    
    @classmethod
    def create_from_user_report(cls, gas_station_id: str, fuel_type: str, price: float, 
                               reporter_ip: str, notes: str = None, pump_number: int = None) -> "GasPrice":
        """Crea un precio desde un reporte de usuario"""
        return cls(
            gas_station_id=gas_station_id,
            fuel_type=fuel_type.lower(),
            price=price,
            source="user",
            reported_by=reporter_ip,
            confidence_score=0.8,  # Confianza inicial para reportes de usuario
            validation_status="validated",  # Auto-aprobar por ahora
            notes=notes,
            pump_number=pump_number,
        )
    
    @classmethod 
    def create_from_cre_data(cls, gas_station_id: str, fuel_type: str, price: float) -> "GasPrice":
        """Crea un precio desde datos oficiales de CRE"""
        return cls(
            gas_station_id=gas_station_id,
            fuel_type=fuel_type.lower(),
            price=price,
            source="cre",
            reported_by="cre_system",
            confidence_score=1.0,  # Máxima confianza para datos oficiales
            validation_status="validated",
            notes="Precio oficial CRE",
        )