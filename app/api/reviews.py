"""
API endpoints para reseñas - Con protecciones
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Form

from ..services.db_service import db_service
from ..services.protection_service import protection_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/")
async def get_reviews(
    gas_station_id: Optional[str] = Query(None, description="Filtrar por gasolinera"),
    min_rating: Optional[int] = Query(None, ge=1, le=5, description="Calificación mínima"),
    limit: int = Query(20, ge=1, le=100, description="Elementos por página"),
    offset: int = Query(0, ge=0, description="Offset para paginación")
):
    """
    Obtiene lista de reseñas con filtros opcionales
    """
    try:
        reviews = await db_service.get_reviews(
            station_id=gas_station_id,
            limit=limit,
            offset=offset
        )
        
        # Filtrar por rating mínimo si se especifica
        if min_rating:
            reviews = [r for r in reviews if r.rating >= min_rating]
        
        # Convertir a diccionarios
        reviews_data = []
        for review in reviews:
            review_dict = review.to_dict()
            
            # Agregar nombre de gasolinera si no está filtrado por estación
            if not gas_station_id and hasattr(review, 'gas_station'):
                review_dict["gas_station_name"] = review.gas_station.name
            
            reviews_data.append(review_dict)
        
        return {
            "reviews": reviews_data,
            "total": len(reviews_data),
            "limit": limit,
            "offset": offset,
            "filters": {
                "gas_station_id": gas_station_id,
                "min_rating": min_rating
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/{review_id}")
async def get_review(review_id: str):
    """
    Obtiene detalles de una reseña específica
    """
    try:
        # Por simplicidad, usar el servicio básico
        # En una implementación más completa, se agregaría get_review_by_id al db_service
        reviews = await db_service.get_reviews(limit=1000)  # Buscar en todas
        review = next((r for r in reviews if r.id == review_id), None)
        
        if not review:
            raise HTTPException(status_code=404, detail="Reseña no encontrada")
        
        return review.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching review {review_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/")
async def create_review(
    request: Request,
    gas_station_id: str = Form(..., description="ID de la gasolinera"),
    name: str = Form(..., min_length=2, max_length=100, description="Tu nombre"),
    rating: int = Form(..., ge=1, le=5, description="Calificación (1-5 estrellas)"),
    comment: str = Form(..., min_length=10, max_length=1000, description="Tu comentario"),
    title: Optional[str] = Form(None, max_length=200, description="Título opcional"),
    captcha_token: Optional[str] = Form(None, alias="g-recaptcha-response", description="Token reCAPTCHA")
):
    """
    Crea una nueva reseña de gasolinera (CON PROTECCIONES)
    """
    try:
        # Obtener IP del cliente
        client_ip = request.client.host if request.client else "127.0.0.1"
        
        # Preparar datos para validación
        form_data = {
            "gas_station_id": gas_station_id,
            "name": name,
            "rating": rating,
            "comment": comment,
            "title": title,
            "g-recaptcha-response": captcha_token
        }
        
        # VALIDACIONES DE PROTECCIÓN
        validation_ok, validation_msg = await protection_service.validate_review(
            form_data, client_ip
        )
        
        if not validation_ok:
            logger.warning(f"Review validation failed from {client_ip}: {validation_msg}")
            raise HTTPException(status_code=400, detail=validation_msg)
        
        # Verificar que la gasolinera existe
        station = await db_service.get_gas_station_by_id(gas_station_id)
        if not station:
            raise HTTPException(status_code=404, detail="Gasolinera no encontrada")
        
        # Crear la reseña
        review = await db_service.create_review(form_data, client_ip)
        
        logger.info(f"Review created: {review.id} from {client_ip}")
        
        return {
            "success": True,
            "message": "Reseña publicada correctamente",
            "review_id": review.id,
            "gas_station_name": station.name,
            "rating": rating,
            "status": review.status,
            "review": review.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating review: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/statistics/overview")
async def get_reviews_statistics(
    gas_station_id: Optional[str] = Query(None, description="Filtrar por gasolinera"),
    days_back: int = Query(30, ge=1, le=365, description="Días hacia atrás")
):
    """
    Obtiene estadísticas generales de reseñas
    """
    try:
        # Por simplicidad, retornar estadísticas básicas
        # En el futuro se pueden implementar conteos reales por fecha
        
        reviews = await db_service.get_reviews(
            station_id=gas_station_id,
            limit=1000  # Obtener suficientes para estadísticas
        )
        
        if not reviews:
            return {
                "total_reviews": 0,
                "average_rating": 0,
                "rating_breakdown": {},
                "gas_station_id": gas_station_id
            }
        
        # Calcular estadísticas
        total_reviews = len(reviews)
        average_rating = sum(r.rating for r in reviews) / total_reviews
        
        # Distribución por rating
        rating_breakdown = {}
        for i in range(1, 6):
            rating_breakdown[str(i)] = len([r for r in reviews if r.rating == i])
        
        return {
            "period_days": days_back,
            "gas_station_id": gas_station_id,
            "total_reviews": total_reviews,
            "average_rating": round(average_rating, 2),
            "rating_breakdown": rating_breakdown,
            "recent_reviews": [r.to_dict() for r in reviews[:5]]  # Últimas 5
        }
        
    except Exception as e:
        logger.error(f"Error getting reviews statistics: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/latest")
async def get_latest_reviews(
    limit: int = Query(10, ge=1, le=50, description="Número de reseñas recientes")
):
    """
    Obtiene las reseñas más recientes del sistema
    """
    try:
        reviews = await db_service.get_reviews(limit=limit)
        
        reviews_data = []
        for review in reviews:
            review_dict = review.to_dict()
            
            # Agregar info básica de la gasolinera
            if hasattr(review, 'gas_station'):
                review_dict["gas_station_name"] = review.gas_station.name
                review_dict["gas_station_city"] = review.gas_station.city
            
            reviews_data.append(review_dict)
        
        return {
            "latest_reviews": reviews_data,
            "total": len(reviews_data)
        }
        
    except Exception as e:
        logger.error(f"Error fetching latest reviews: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")