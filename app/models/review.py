"""
Modelo de reseñas de gasolineras - Simplificado
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship, Mapped

from . import Base


class GasStationReview(Base):
    """Modelo de reseñas de gasolineras - Simplificado sin votos ni moderación"""
    
    __tablename__ = "gas_station_reviews"
    
    # Campos principales
    id: Mapped[str] = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # Relación con gasolinera
    gas_station_id: Mapped[str] = Column(
        UUID(as_uuid=False), 
        ForeignKey("gas_stations.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Información del reviewer (simplificado)
    reviewer_name: Mapped[str] = Column(String(100), nullable=False)
    reviewer_ip: Mapped[str] = Column(INET, nullable=False)  # Para rate limiting
    
    # Contenido de la reseña
    rating: Mapped[int] = Column(Integer, nullable=False)  # 1-5 estrellas
    title: Mapped[Optional[str]] = Column(String(200), nullable=True)
    comment: Mapped[str] = Column(Text, nullable=False)
    
    # Estado simple (sin moderación compleja)
    status: Mapped[str] = Column(String(20), default="approved", nullable=False)  # approved, hidden
    
    # Timestamps
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relaciones
    gas_station = relationship("GasStation", back_populates="reviews")
    
    def __repr__(self) -> str:
        return f"<GasStationReview(id={self.id}, rating={self.rating}, reviewer={self.reviewer_name})>"
    
    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario"""
        return {
            "id": self.id,
            "gas_station_id": self.gas_station_id,
            "reviewer_name": self.reviewer_name,
            "rating": self.rating,
            "title": self.title,
            "comment": self.comment,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "age_days": self.calculate_age_days(),
        }
    
    def calculate_age_days(self) -> int:
        """Calcula la edad de la reseña en días"""
        return (datetime.utcnow() - self.created_at).days
    
    def is_recent(self) -> bool:
        """Verifica si la reseña es reciente (menos de 30 días)"""
        return self.calculate_age_days() <= 30
    
    @classmethod
    def create_from_form_data(cls, form_data: dict, request_info: dict) -> "GasStationReview":
        """Crea una reseña desde datos de formulario"""
        return cls(
            gas_station_id=form_data.get("gas_station_id"),
            reviewer_name=form_data.get("name", "").strip(),
            reviewer_ip=request_info.get("ip"),
            rating=int(form_data.get("rating", 1)),
            title=form_data.get("title", "").strip() or None,
            comment=form_data.get("comment", "").strip(),
            status="approved"  # Auto-aprobar por simplicidad
        )