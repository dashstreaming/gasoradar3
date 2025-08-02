"""
Servicio de base de datos - Operaciones CRUD básicas
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from statistics import mean

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload

from ..database import get_async_session
from ..models.gas_station import GasStation
from ..models.gas_price import GasPrice
from ..models.user_report import UserPriceReport
from ..models.review import GasStationReview


logger = logging.getLogger(__name__)


class DatabaseService:
    """Servicio para operaciones comunes de base de datos"""
    
    async def get_gas_stations(self, 
                              latitude: Optional[float] = None,
                              longitude: Optional[float] = None,
                              radius_km: Optional[int] = 25,
                              city: Optional[str] = None,
                              state: Optional[str] = None,
                              brand: Optional[str] = None,
                              fuel_type: Optional[str] = None,
                              limit: int = 50,
                              offset: int = 0) -> List[GasStation]:
        """
        Obtiene gasolineras con filtros opcionales
        """
        async with get_async_session() as session:
            query = select(GasStation).where(GasStation.is_active == True)
            
            # Filtros de ubicación
            if latitude and longitude and radius_km:
                # Aproximación simple de rango por grados
                lat_range = radius_km / 111.0  # ~111 km por grado de latitud
                lng_range = radius_km / (111.0 * abs(latitude / 90.0))
                
                query = query.where(
                    and_(
                        GasStation.latitude.between(latitude - lat_range, latitude + lat_range),
                        GasStation.longitude.between(longitude - lng_range, longitude + lng_range)
                    )
                )
            
            # Filtros de texto
            if city:
                query = query.where(GasStation.city.ilike(f"%{city}%"))
            if state:
                query = query.where(GasStation.state.ilike(f"%{state}%"))
            if brand:
                query = query.where(GasStation.brand.ilike(f"%{brand}%"))
            
            # Filtro por tipo de combustible
            if fuel_type:
                fuel_type = fuel_type.lower()
                if fuel_type == "magna":
                    query = query.where(GasStation.has_magna == True)
                elif fuel_type == "premium":
                    query = query.where(GasStation.has_premium == True)
                elif fuel_type == "diesel":
                    query = query.where(GasStation.has_diesel == True)
            
            # Ordenamiento por distancia si hay coordenadas
            if latitude and longitude:
                query = query.order_by(
                    func.abs(GasStation.latitude - latitude) + 
                    func.abs(GasStation.longitude - longitude)
                )
            else:
                query = query.order_by(GasStation.name)
            
            # Paginación
            query = query.offset(offset).limit(limit)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_gas_station_by_id(self, station_id: str) -> Optional[GasStation]:
        """Obtiene una gasolinera por ID con precios y reseñas"""
        async with get_async_session() as session:
            query = select(GasStation).where(
                and_(
                    GasStation.id == station_id,
                    GasStation.is_active == True
                )
            ).options(
                selectinload(GasStation.prices),
                selectinload(GasStation.reviews)
            )
            
            result = await session.execute(query)
            return result.scalar_one_or_none()
    
    async def get_current_prices(self, station_id: str) -> Dict[str, Optional[Dict]]:
        """Obtiene los precios actuales de una gasolinera"""
        async with get_async_session() as session:
            query = select(GasPrice).where(
                and_(
                    GasPrice.gas_station_id == station_id,
                    GasPrice.is_current == True,
                    GasPrice.validation_status == "validated"
                )
            ).order_by(desc(GasPrice.created_at))
            
            result = await session.execute(query)
            prices = result.scalars().all()
            
            # Organizar por tipo de combustible
            current_prices = {}
            for price in prices:
                if price.fuel_type not in current_prices:
                    current_prices[price.fuel_type] = {
                        "price": price.price,
                        "source": price.source,
                        "confidence": price.confidence_score,
                        "updated_at": price.created_at.isoformat(),
                        "age_hours": price.calculate_age_hours(),
                        "is_fresh": price.is_fresh()
                    }
            
            return current_prices
    
    async def get_current_prices_all_stations(self, 
                                            fuel_type: Optional[str] = None,
                                            city: Optional[str] = None,
                                            state: Optional[str] = None,
                                            limit: int = 100) -> List[Dict]:
        """Obtiene precios actuales de múltiples gasolineras"""
        async with get_async_session() as session:
            query = select(GasPrice, GasStation).join(
                GasStation, GasPrice.gas_station_id == GasStation.id
            ).where(
                and_(
                    GasPrice.is_current == True,
                    GasPrice.validation_status == "validated",
                    GasStation.is_active == True
                )
            )
            
            if fuel_type:
                query = query.where(GasPrice.fuel_type == fuel_type.lower())
            
            if city:
                query = query.where(GasStation.city.ilike(f"%{city}%"))
            
            if state:
                query = query.where(GasStation.state.ilike(f"%{state}%"))
            
            query = query.order_by(GasPrice.price.asc()).limit(limit)
            
            result = await session.execute(query)
            rows = result.all()
            
            prices_data = []
            for price, station in rows:
                prices_data.append({
                    "gas_station_id": station.id,
                    "gas_station_name": station.name,
                    "gas_station_address": station.address,
                    "gas_station_brand": station.brand,
                    "fuel_type": price.fuel_type,
                    "price": price.price,
                    "source": price.source,
                    "confidence": price.confidence_score,
                    "updated_at": price.created_at.isoformat(),
                    "age_hours": price.calculate_age_hours(),
                    "location": {
                        "latitude": station.latitude,
                        "longitude": station.longitude,
                        "city": station.city,
                        "state": station.state
                    }
                })
            
            return prices_data
    
    async def create_price_report(self, report_data: dict, request_ip: str) -> UserPriceReport:
        """Crea un nuevo reporte de precio"""
        async with get_async_session() as session:
            # Crear el reporte
            report = UserPriceReport.create_from_form_data(
                report_data, 
                {"ip": request_ip}
            )
            
            session.add(report)
            await session.flush()  # Para obtener el ID
            
            # Crear precio oficial inmediatamente
            price = GasPrice.create_from_user_report(
                gas_station_id=report.gas_station_id,
                fuel_type=report.fuel_type,
                price=report.reported_price,
                reporter_ip=request_ip,
                notes=report.comments,
                pump_number=report.pump_number
            )
            
            session.add(price)
            
            # Marcar reporte como procesado
            report.process_report()
            
            # Actualizar estadísticas de la gasolinera
            station_query = select(GasStation).where(GasStation.id == report.gas_station_id)
            station_result = await session.execute(station_query)
            station = station_result.scalar_one_or_none()
            
            if station:
                station.total_reports += 1
                station.last_price_update = datetime.utcnow()
            
            await session.commit()
            await session.refresh(report)
            
            logger.info(f"Created price report: {report.id} -> Price: {price.id}")
            return report
    
    async def create_review(self, review_data: dict, request_ip: str) -> GasStationReview:
        """Crea una nueva reseña"""
        async with get_async_session() as session:
            # Crear la reseña
            review = GasStationReview.create_from_form_data(
                review_data,
                {"ip": request_ip}
            )
            
            session.add(review)
            await session.flush()
            
            # Actualizar estadísticas de la gasolinera
            station_query = select(GasStation).where(GasStation.id == review.gas_station_id)
            station_result = await session.execute(station_query)
            station = station_result.scalar_one_or_none()
            
            if station:
                # Recalcular rating promedio
                if station.total_reviews == 0:
                    station.average_rating = review.rating
                else:
                    total_points = (station.average_rating * station.total_reviews) + review.rating
                    station.average_rating = total_points / (station.total_reviews + 1)
                
                station.total_reviews += 1
            
            await session.commit()
            await session.refresh(review)
            
            logger.info(f"Created review: {review.id}")
            return review
    
    async def get_reviews(self, 
                         station_id: Optional[str] = None,
                         limit: int = 20,
                         offset: int = 0) -> List[GasStationReview]:
        """Obtiene reseñas"""
        async with get_async_session() as session:
            query = select(GasStationReview).where(
                GasStationReview.status == "approved"
            )
            
            if station_id:
                query = query.where(GasStationReview.gas_station_id == station_id)
            
            query = query.order_by(desc(GasStationReview.created_at))
            query = query.offset(offset).limit(limit)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_price_statistics(self, fuel_type: str, region: Optional[str] = None) -> Dict:
        """Obtiene estadísticas de precios"""
        async with get_async_session() as session:
            # Obtener precios recientes
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            
            query = select(GasPrice.price).where(
                and_(
                    GasPrice.fuel_type == fuel_type.lower(),
                    GasPrice.created_at >= cutoff_date,
                    GasPrice.is_current == True,
                    GasPrice.validation_status == "validated"
                )
            )
            
            # Filtrar por región si se especifica
            if region:
                query = query.join(GasStation).where(
                    or_(
                        GasStation.state.ilike(f"%{region}%"),
                        GasStation.city.ilike(f"%{region}%")
                    )
                )
            
            result = await session.execute(query)
            prices = [row[0] for row in result.fetchall()]
            
            if not prices:
                return {"error": "No hay datos de precios disponibles"}
            
            return {
                "fuel_type": fuel_type,
                "region": region or "nacional",
                "sample_size": len(prices),
                "average": round(mean(prices), 2),
                "minimum": min(prices),
                "maximum": max(prices),
                "range": round(max(prices) - min(prices), 2)
            }
    
    async def search_stations_by_region(self, region: str, fuel_type: str, limit: int = 20) -> List[Dict]:
        """Busca estaciones más baratas por región"""
        async with get_async_session() as session:
            # Buscar gasolineras en la región
            query = select(GasStation).where(
                and_(
                    GasStation.is_active == True,
                    or_(
                        GasStation.city.ilike(f"%{region}%"),
                        GasStation.state.ilike(f"%{region}%")
                    )
                )
            )
            
            result = await session.execute(query)
            stations = result.scalars().all()
            
            if not stations:
                return []
            
            # Obtener precios de estas estaciones
            station_ids = [s.id for s in stations]
            
            price_query = select(GasPrice, GasStation).join(
                GasStation, GasPrice.gas_station_id == GasStation.id
            ).where(
                and_(
                    GasPrice.gas_station_id.in_(station_ids),
                    GasPrice.fuel_type == fuel_type.lower(),
                    GasPrice.is_current == True,
                    GasPrice.validation_status == "validated"
                )
            ).order_by(GasPrice.price.asc()).limit(limit)
            
            price_result = await session.execute(price_query)
            price_rows = price_result.all()
            
            stations_with_prices = []
            for price, station in price_rows:
                stations_with_prices.append({
                    "gas_station_id": station.id,
                    "name": station.name,
                    "brand": station.brand,
                    "address": station.address,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "price": price.price,
                    "source": price.source,
                    "confidence": price.confidence_score,
                    "updated_at": price.created_at.isoformat(),
                    "age_hours": price.calculate_age_hours()
                })
            
            return stations_with_prices


# Instancia global del servicio
db_service = DatabaseService()