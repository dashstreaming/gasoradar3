"""
Aplicación principal de Gasoradar - Simplificada
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings, CORS_SETTINGS, LOGGING_CONFIG
from .database import init_database, close_database
from .api import gas_stations, prices, reviews

# Configurar logging
import logging.config
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Context manager para el ciclo de vida de la aplicación"""
    # Startup
    logger.info("🚀 Starting Gasoradar application...")
    
    try:
        # Inicializar base de datos (comentado porque tu DB ya existe)
        # await init_database()
        logger.info("✅ Database connection ready")
        
        logger.info("🎉 Application startup completed")
        
    except Exception as e:
        logger.error(f"❌ Failed to start application: {str(e)}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Gasoradar application...")
    
    try:
        await close_database()
        logger.info("✅ Database connections closed")
        logger.info("👋 Application shutdown completed")
        
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {str(e)}")


# Crear aplicación FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API para encontrar gasolineras baratas en México",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Configurar middlewares
app.add_middleware(CORSMiddleware, **CORS_SETTINGS)

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Configurar templates
templates = Jinja2Templates(directory="app/templates")

# Incluir routers de API
app.include_router(gas_stations.router, prefix="/api/v1")
app.include_router(prices.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")


# Manejadores de errores globales
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Manejador para errores HTTP"""
    logger.error(f"HTTP {exc.status_code} error at {request.url}: {exc.detail}")
    
    # Si es una request a la API, devolver JSON
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "path": str(request.url.path)
            }
        )
    
    # Para rutas web, mostrar página de error
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "404.html", 
            {"request": request, "message": "Página no encontrada"},
            status_code=404
        )
    
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request, 
            "status_code": exc.status_code,
            "message": exc.detail
        },
        status_code=exc.status_code
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Manejador para errores de validación"""
    logger.warning(f"Validation error at {request.url}: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "message": "Los datos enviados no son válidos"
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Manejador para errores generales no capturados"""
    logger.error(f"Unhandled error at {request.url}: {str(exc)}", exc_info=True)
    
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "Ha ocurrido un error interno del servidor"
            }
        )
    
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 500,
            "message": "Error interno del servidor"
        },
        status_code=500
    )


# Rutas principales de la aplicación web
@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request):
    """Página principal con lista de gasolineras"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "recaptcha_site_key": settings.recaptcha_site_key
    })


@app.get("/mapa", response_class=HTMLResponse, name="map")
async def map_view(request: Request):
    """Vista del mapa interactivo"""
    return templates.TemplateResponse("mapa.html", {
        "request": request,
        "google_maps_api_key": settings.google_maps_api_key,
        "recaptcha_site_key": settings.recaptcha_site_key
    })


@app.get("/reporte", response_class=HTMLResponse, name="report")
async def report_form(request: Request):
    """Formulario para reportar precios"""
    gas_station_id = request.query_params.get("station_id", "")
    return templates.TemplateResponse("reporte.html", {
        "request": request,
        "gas_station_id": gas_station_id,
        "recaptcha_site_key": settings.recaptcha_site_key
    })


@app.get("/reseña", response_class=HTMLResponse, name="review")
async def review_page(request: Request):
    """Página de reseñas de gasolineras"""
    gas_station_id = request.query_params.get("station_id", "")
    return templates.TemplateResponse("reseña.html", {
        "request": request,
        "gas_station_id": gas_station_id,
        "recaptcha_site_key": settings.recaptcha_site_key
    })


@app.get("/gasolinera/{station_id}", response_class=HTMLResponse, name="station_detail")
async def station_detail(request: Request, station_id: str):
    """Detalle de una gasolinera específica"""
    return templates.TemplateResponse("station_detail.html", {
        "request": request, 
        "station_id": station_id,
        "recaptcha_site_key": settings.recaptcha_site_key
    })


# Rutas de API adicionales
@app.get("/api/health")
async def health_check():
    """Health check para el load balancer"""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "timestamp": "2024-01-01T00:00:00Z"
    }


@app.get("/api/info")
async def app_info():
    """Información de la aplicación"""
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "debug": settings.debug,
        "environment": "development" if settings.debug else "production",
        "features": {
            "user_reports": True,
            "reviews": True,
            "price_validation": True,
            "rate_limiting": True,
            "captcha_protection": True
        }
    }


@app.get("/api/config/frontend")
async def get_frontend_config():
    """Configuración para el frontend"""
    return {
        "maps": {
            "google_maps_api_key": settings.google_maps_api_key if settings.debug else None,
            "default_center": {
                "lat": 23.6345,  # Centro de México
                "lng": -102.5528
            },
            "default_zoom": 6
        },
        "captcha": {
            "recaptcha_site_key": settings.recaptcha_site_key,
            "type": "recaptcha"
        },
        "features": {
            "user_reports": True,
            "reviews": True,
            "dynamic_validation": True
        },
        "limits": {
            "price_reports_per_hour": settings.price_reports_per_hour,
            "reviews_per_day": settings.reviews_per_day
        },
        "validation": {
            "price_tolerance_percent": settings.price_tolerance_percent,
            "fallback_ranges": settings.fallback_price_ranges
        }
    }


# Middleware personalizado para logging de requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log de requests importantes"""
    import time
    
    start_time = time.time()
    
    # Solo logear APIs importantes, no assets estáticos
    if request.url.path.startswith("/api/") or request.method == "POST":
        logger.info(f"📥 {request.method} {request.url} - Client: {request.client.host if request.client else 'unknown'}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    
    # Logear respuestas de APIs importantes
    if request.url.path.startswith("/api/") or request.method == "POST":
        logger.info(
            f"📤 {request.method} {request.url} - "
            f"Status: {response.status_code} - "
            f"Time: {process_time:.3f}s"
        )
    
    # Agregar header con tiempo de procesamiento
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


if __name__ == "__main__":
    import uvicorn
    
    # Configuración para desarrollo
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning"
    )