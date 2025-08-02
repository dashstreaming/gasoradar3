"""
Modelo de reportes de precios de usuarios - Simplificado
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship, Mapped

from . import Base


class UserPriceReport(Base):
    """Modelo de reportes de precios por usuarios - Simplificado"""
    
    __tablename__ = "user_price_reports"
    
    # Campos principales
    id: Mapped[str] = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # Relación con gasolinera
    gas_station_id: Mapped[str] = Column(
        UUID(as_uuid=False), 
        ForeignKey("gas_stations.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Datos del reporte
    fuel_type: Mapped[str] = Column(String(20), nullable=False)  # magna, premium, diesel
    reported_price: Mapped[float] = Column(Float, nullable=False)
    
    # Información del reportero (simplificado - solo IP para rate limiting)
    reporter_ip: Mapped[str] = Column(INET, nullable=False)
    reporter_name: Mapped[Optional[str]] = Column(String(100), nullable=True)
    
    # Detalles del reporte
    comments: Mapped[Optional[str]] = Column(Text, nullable=True)
    pump_number: Mapped[Optional[int]] = Column(Integer, nullable=True)
    
    # Estado simple (sin moderación compleja)
    status: Mapped[str] = Column(String(20), default="pending", nullable=False)  # pending, processed, rejected
    
    # Timestamps
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    
    # Relaciones
    gas_station = relationship("GasStation", back_populates="user_reports")
    
    def __repr__(self) -> str:
        return f"<UserPriceReport(id={self.id}, fuel_type={self.fuel_type}, price={self.reported_price})>"
    
    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario"""
        return {
            "id": self.id,
            "gas_station_id": self.gas_station_id,
            "fuel_type": self.fuel_type,
            "reported_price": self.reported_price,
            "reporter_name": self.reporter_name,
            "comments": self.comments,
            "pump_number": self.pump_number,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
    
    def calculate_age_hours(self) -> float:
        """Calcula la edad del reporte en horas"""
        return (datetime.utcnow() - self.created_at).total_seconds() / 3600
    
    def process_report(self) -> bool:
        """
        Procesa el reporte y crea un precio oficial
        Retorna True si se procesó exitosamente
        """
        if self.status != "pending":
            return False
        
        # Crear precio oficial desde este reporte
        from .gas_price import GasPrice
        
        new_price = GasPrice.create_from_user_report(
            gas_station_id=self.gas_station_id,
            fuel_type=self.fuel_type,
            price=self.reported_price,
            reporter_ip=str(self.reporter_ip),
            notes=self.comments,
            pump_number=self.pump_number
        )
        
        # Marcar como procesado
        self.status = "processed"
        self.processed_at = datetime.utcnow()
        
        return True
    
    @classmethod
    def create_from_form_data(cls, form_data: dict, request_info: dict) -> "UserPriceReport":
        """Crea un reporte desde datos de formulario"""
        return cls(
            gas_station_id=form_data.get("gas_station_id"),
            fuel_type=form_data.get("fuel_type", "").lower(),
            reported_price=float(form_data.get("reported_price", 0)),
            reporter_ip=request_info.get("ip"),
            reporter_name=form_data.get("reporter_name", "").strip() or None,
            comments=form_data.get("comments", "").strip() or None,
            pump_number=form_data.get("pump_number"),
        )