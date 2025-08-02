"""
API endpoints para gasolineras - Simplificado
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..services.db_service import db_service
from ..models.gas_station import GasStation


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gas-stations", tags=["Gas Stations"])


@router.get("/")
async def get_gas_stations(
    request: Request,
    latitude: Optional[float] = Query(None, description="Latitud para búsqueda por cercanía"),
    longitude: Optional[float] = Query(None, description="Longitud para búsqueda por cercanía"),
    radius_km: Optional[int] = Query(25, ge=1, le=100, description="Radio de búsqueda en km"),
    city: Optional[str] = Query(None, description="Filtrar por ciudad"),
    state: Optional[str] = Query(None, description="Filtrar por estado"),
    brand: Optional[str] = Query(None, description="Filtrar por marca"),
    fuel_type: Optional[str] = Query(None, description="Filtrar por tipo de combustible"),
    limit: int = Query(50, ge=1, le=200, description="Límite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginación")
):
    """
    Obtiene lista de gasolineras con filtros opcionales
    """
    try:
        stations = await db_service.get_gas_stations(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            city=city,
            state=state,
            brand=brand,
            fuel_type=fuel_type,
            limit=limit,
            offset=offset
        )
        
        # Convertir a formato de respuesta con precios actuales
        stations_data = []
        for station in stations:
            station_dict = station.to_dict()
            
            # Agregar precios actuales
            current_prices = await db_service.get_current_prices(station.id)
            station_dict["current_prices"] = current_prices
            
            # Agregar distancia si hay coordenadas
            if latitude and longitude:
                station_dict["distance_km"] = station.calculate_distance(latitude, longitude)
            
            stations_data.append(station_dict)
        
        return {
            "stations": stations_data,
            "total": len(stations_data),
            "limit": limit,
            "offset": offset,
            "filters": {
                "latitude": latitude,
                "longitude": longitude,
                "radius_km": radius_km,
                "city": city,
                "state": state,
                "brand": brand,
                "fuel_type": fuel_type
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching gas stations: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/{station_id}")
async def get_gas_station(station_id: str):
    """
    Obtiene detalles de una gasolinera específica
    """
    try:
        station = await db_service.get_gas_station_by_id(station_id)
        
        if not station:
            raise HTTPException(status_code=404, detail="Gasolinera no encontrada")
        
        # Convertir a diccionario
        station_dict = station.to_dict()
        
        # Agregar precios actuales
        current_prices = await db_service.get_current_prices(station.id)
        station_dict["current_prices"] = current_prices
        
        # Agregar reseñas recientes
        reviews = await db_service.get_reviews(station_id=station.id, limit=5)
        station_dict["recent_reviews"] = [review.to_dict() for review in reviews]
        
        return station_dict
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching gas station {station_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/search/cheapest")
async def get_cheapest_stations(
    fuel_type: str = Query(..., description="Tipo de combustible"),
    city: Optional[str] = Query(None, description="Ciudad"),
    state: Optional[str] = Query(None, description="Estado"),
    limit: int = Query(20, ge=1, le=50, description="Número de resultados")
):
    """
    Encuentra las gasolineras más baratas por región
    """
    try:
        if not city and not state:
            raise HTTPException(
                status_code=400, 
                detail="Debe especificar al menos ciudad o estado"
            )
        
        region = city or state
        stations = await db_service.search_stations_by_region(region, fuel_type, limit)
        
        if not stations:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron gasolineras en {region}"
            )
        
        return {
            "search_type": "region",
            "region": region,
            "fuel_type": fuel_type.lower(),
            "total_stations_found": len(stations),
            "stations": stations
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding cheapest stations: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/statistics/overview")
async def get_statistics_overview():
    """
    Obtiene estadísticas generales de gasolineras
    """
    try:
        # Obtener estadísticas básicas usando el servicio de DB
        # Por simplicidad, retornar datos mock por ahora
        # En el futuro se puede implementar conteos reales
        
        return {
            "total_stations": 15000,  # Placeholder
            "total_prices": 31938,    # De tus datos reales
            "fuel_types": ["magna", "premium", "diesel"],
            "coverage": {
                "states": 32,
                "cities": 500
            },
            "last_updated": "2024-01-01T12:00:00Z"
        }
        
    except Exception as e:
        logger.error(f"Error generating statistics: {str(e)}")
        raise HTTPException(status_code=500, detail="Error generando estadísticas")