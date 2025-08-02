"""
API endpoints para precios - Con protecciones
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Form

from ..services.db_service import db_service
from ..services.protection_service import protection_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prices", tags=["Prices"])


@router.get("/current")
async def get_current_prices(
    fuel_type: Optional[str] = Query(None, description="Filtrar por tipo de combustible"),
    city: Optional[str] = Query(None, description="Filtrar por ciudad"),
    state: Optional[str] = Query(None, description="Filtrar por estado"),
    latitude: Optional[float] = Query(None, description="Latitud para búsqueda por cercanía"),
    longitude: Optional[float] = Query(None, description="Longitud para búsqueda por cercanía"),
    radius_km: Optional[int] = Query(25, ge=1, le=100, description="Radio de búsqueda en km"),
    sort_by: Optional[str] = Query("price", description="Ordenar por: price, updated, distance"),
    limit: int = Query(50, ge=1, le=200, description="Límite de resultados")
):
    """
    Obtiene precios actuales de combustible con filtros opcionales
    """
    try:
        prices_data = await db_service.get_current_prices_all_stations(
            fuel_type=fuel_type,
            city=city,
            state=state,
            limit=limit
        )
        
        # Si hay coordenadas, calcular distancias y filtrar por radio
        if latitude and longitude and radius_km:
            filtered_prices = []
            for price_data in prices_data:
                lat = price_data["location"]["latitude"]
                lng = price_data["location"]["longitude"]
                
                # Calcular distancia simple
                from math import sqrt
                lat_diff = lat - latitude
                lng_diff = lng - longitude
                distance_approx = sqrt(lat_diff**2 + lng_diff**2) * 111  # Aproximación en km
                
                if distance_approx <= radius_km:
                    price_data["distance_km"] = round(distance_approx, 2)
                    filtered_prices.append(price_data)
            
            prices_data = filtered_prices
        
        # Ordenamiento
        if sort_by == "updated":
            prices_data.sort(key=lambda x: x["updated_at"], reverse=True)
        elif sort_by == "distance" and latitude and longitude:
            prices_data.sort(key=lambda x: x.get("distance_km", 999))
        else:  # price
            prices_data.sort(key=lambda x: x["price"])
        
        return {
            "prices": prices_data,
            "total": len(prices_data),
            "filters": {
                "fuel_type": fuel_type,
                "city": city,
                "state": state,
                "radius_km": radius_km if latitude and longitude else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching current prices: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/report")
async def report_price(
    request: Request,
    gas_station_id: str = Form(..., description="ID de la gasolinera"),
    fuel_type: str = Form(..., description="Tipo de combustible"),
    reported_price: float = Form(..., ge=0, description="Precio por litro"),
    comments: Optional[str] = Form(None, description="Comentarios adicionales"),
    pump_number: Optional[int] = Form(None, description="Número de bomba"),
    reporter_name: Optional[str] = Form(None, description="Nombre del reportero"),
    captcha_token: Optional[str] = Form(None, alias="g-recaptcha-response", description="Token reCAPTCHA")
):
    """
    Reporta un nuevo precio de combustible (CON PROTECCIONES)
    """
    try:
        # Obtener IP del cliente
        client_ip = request.client.host if request.client else "127.0.0.1"
        
        # Preparar datos para validación
        form_data = {
            "gas_station_id": gas_station_id,
            "fuel_type": fuel_type,
            "reported_price": reported_price,
            "comments": comments,
            "pump_number": pump_number,
            "reporter_name": reporter_name,
            "g-recaptcha-response": captcha_token
        }
        
        # VALIDACIONES DE PROTECCIÓN
        validation_ok, validation_msg = await protection_service.validate_price_report(
            form_data, client_ip
        )
        
        if not validation_ok:
            logger.warning(f"Price report validation failed from {client_ip}: {validation_msg}")
            raise HTTPException(status_code=400, detail=validation_msg)
        
        # Verificar que la gasolinera existe
        station = await db_service.get_gas_station_by_id(gas_station_id)
        if not station:
            raise HTTPException(status_code=404, detail="Gasolinera no encontrada")
        
        # Verificar que la gasolinera vende este combustible
        if not station.has_fuel_type(fuel_type):
            raise HTTPException(
                status_code=400,
                detail=f"Esta gasolinera no vende {fuel_type}"
            )
        
        # Crear el reporte (esto también crea el precio automáticamente)
        report = await db_service.create_price_report(form_data, client_ip)
        
        logger.info(f"Price report created: {report.id} from {client_ip}")
        
        return {
            "success": True,
            "message": "Precio reportado correctamente",
            "report_id": report.id,
            "gas_station_name": station.name,
            "fuel_type": fuel_type.lower(),
            "reported_price": reported_price,
            "status": report.status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reporting price: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/statistics")
async def get_price_statistics(
    fuel_type: str = Query(..., description="Tipo de combustible"),
    region: Optional[str] = Query(None, description="Región específica")
):
    """
    Obtiene estadísticas de precios por combustible y región
    """
    try:
        stats = await db_service.get_price_statistics(fuel_type, region)
        
        if "error" in stats:
            raise HTTPException(status_code=404, detail=stats["error"])
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price statistics: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/cheapest")
async def get_cheapest_prices(
    fuel_type: str = Query(..., description="Tipo de combustible"),
    city: Optional[str] = Query(None, description="Ciudad"),
    state: Optional[str] = Query(None, description="Estado"),
    limit: int = Query(10, ge=1, le=50, description="Número de resultados")
):
    """
    Encuentra los precios más baratos por región
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
        logger.error(f"Error finding cheapest prices: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/validation-info")
async def get_price_validation_info(
    fuel_type: str = Query(..., description="Tipo de combustible"),
    region: Optional[str] = Query(None, description="Región para validación")
):
    """
    Obtiene información sobre los rangos de validación actuales
    """
    try:
        # Usar el servicio de protección para obtener info de validación
        is_valid, message, validation_info = await protection_service.validate_price_dynamically(
            fuel_type, 0, region  # Usar precio 0 solo para obtener rangos
        )
        
        return {
            "fuel_type": fuel_type,
            "region": region or "nacional",
            "validation_info": validation_info,
            "message": "Rangos de validación actuales"
        }
        
    except Exception as e:
        logger.error(f"Error getting validation info: {str(e)}")
        raise HTTPException(status_code=500, detail="Error obteniendo información de validación")