"""
Servicio de protección: CAPTCHA + Rate limiting + Validación dinámica de precios
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from statistics import mean

import aiohttp
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_async_session


logger = logging.getLogger(__name__)


class ProtectionService:
    """Servicio para proteger contra bots y sabotaje"""
    
    def __init__(self):
        # Rate limiting en memoria (en producción usar Redis)
        self._price_reports: Dict[str, deque] = defaultdict(deque)
        self._reviews: Dict[str, deque] = defaultdict(deque)
        
        # Configuración de reCAPTCHA
        self.recaptcha_secret = settings.recaptcha_secret_key
        self.recaptcha_verify_url = "https://www.google.com/recaptcha/api/siteverify"
        
        # Configuración de validación dinámica
        self.price_tolerance = settings.price_tolerance_percent / 100.0  # Convertir a decimal
        self.min_samples = settings.min_samples_for_validation
        self.freshness_days = settings.price_data_freshness_days
        self.fallback_ranges = settings.fallback_price_ranges
    
    async def verify_recaptcha(self, token: str, user_ip: str = None) -> Tuple[bool, str]:
        """
        Verifica token de reCAPTCHA
        """
        if not token:
            return False, "Token CAPTCHA requerido"
        
        if not self.recaptcha_secret:
            logger.warning("reCAPTCHA secret not configured, bypassing verification")
            return True, "Bypassed in development"
        
        payload = {
            "secret": self.recaptcha_secret,
            "response": token
        }
        
        if user_ip:
            payload["remoteip"] = user_ip
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.recaptcha_verify_url, data=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        success = result.get("success", False)
                        
                        if success:
                            # Para reCAPTCHA v3, verificar score
                            score = result.get("score")
                            if score is not None and score < 0.5:
                                return False, "Score CAPTCHA muy bajo"
                            
                            logger.info(f"reCAPTCHA verified: score={score}")
                            return True, "CAPTCHA verificado"
                        else:
                            error_codes = result.get("error-codes", [])
                            logger.warning(f"reCAPTCHA failed: {error_codes}")
                            return False, "CAPTCHA inválido"
                    else:
                        logger.error(f"reCAPTCHA API error: HTTP {response.status}")
                        return False, "Error verificando CAPTCHA"
                        
        except Exception as e:
            logger.error(f"reCAPTCHA verification error: {str(e)}")
            return False, "Error verificando CAPTCHA"
    
    def check_price_report_rate_limit(self, ip: str) -> Tuple[bool, str]:
        """
        Verifica rate limit para reportes de precio (3 por hora)
        """
        now = datetime.utcnow().timestamp()
        cutoff = now - 3600  # 1 hora atrás
        
        # Limpiar reportes antiguos
        while self._price_reports[ip] and self._price_reports[ip][0] < cutoff:
            self._price_reports[ip].popleft()
        
        # Verificar límite
        current_count = len(self._price_reports[ip])
        if current_count >= settings.price_reports_per_hour:
            return False, f"Límite excedido: {current_count}/{settings.price_reports_per_hour} reportes por hora"
        
        # Registrar nuevo reporte
        self._price_reports[ip].append(now)
        return True, "Rate limit OK"
    
    def check_review_rate_limit(self, ip: str) -> Tuple[bool, str]:
        """
        Verifica rate limit para reseñas (2 por día)
        """
        now = datetime.utcnow().timestamp()
        cutoff = now - 86400  # 24 horas atrás
        
        # Limpiar reseñas antiguas
        while self._reviews[ip] and self._reviews[ip][0] < cutoff:
            self._reviews[ip].popleft()
        
        # Verificar límite
        current_count = len(self._reviews[ip])
        if current_count >= settings.reviews_per_day:
            return False, f"Límite excedido: {current_count}/{settings.reviews_per_day} reseñas por día"
        
        # Registrar nueva reseña
        self._reviews[ip].append(now)
        return True, "Rate limit OK"
    
    async def validate_price_dynamically(self, fuel_type: str, reported_price: float, 
                                       region: str = None) -> Tuple[bool, str, Dict]:
        """
        Valida precio contra promedios actuales del mercado (±15%)
        """
        try:
            async with get_async_session() as session:
                # Obtener precios recientes del combustible
                cutoff_date = datetime.utcnow() - timedelta(days=self.freshness_days)
                
                # Query para obtener precios recientes y válidos
                from ..models.gas_price import GasPrice
                from ..models.gas_station import GasStation
                
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
                        GasStation.state.ilike(f"%{region}%")
                    )
                
                result = await session.execute(query)
                prices = [row[0] for row in result.fetchall()]
                
                # Verificar si tenemos suficientes datos
                if len(prices) < self.min_samples:
                    return self._validate_with_fallback(fuel_type, reported_price)
                
                # Calcular estadísticas del mercado
                market_avg = mean(prices)
                tolerance = self.price_tolerance
                min_valid = market_avg * (1 - tolerance)
                max_valid = market_avg * (1 + tolerance)
                
                # Validar precio reportado
                is_valid = min_valid <= reported_price <= max_valid
                
                validation_info = {
                    "market_average": round(market_avg, 2),
                    "tolerance_percent": self.price_tolerance * 100,
                    "valid_range": {
                        "min": round(min_valid, 2),
                        "max": round(max_valid, 2)
                    },
                    "samples_count": len(prices),
                    "reported_price": reported_price
                }
                
                if is_valid:
                    return True, "Precio dentro del rango de mercado", validation_info
                else:
                    reason = f"Precio fuera del rango válido (${min_valid:.2f} - ${max_valid:.2f})"
                    return False, reason, validation_info
                    
        except Exception as e:
            logger.error(f"Error validating price dynamically: {str(e)}")
            return self._validate_with_fallback(fuel_type, reported_price)
    
    def _validate_with_fallback(self, fuel_type: str, reported_price: float) -> Tuple[bool, str, Dict]:
        """
        Validación de fallback usando rangos fijos cuando no hay datos suficientes
        """
        ranges = self.fallback_ranges.get(fuel_type.lower())
        if not ranges:
            return True, "No hay límites definidos para este combustible", {}
        
        min_price = ranges["min"]
        max_price = ranges["max"]
        is_valid = min_price <= reported_price <= max_price
        
        validation_info = {
            "fallback_mode": True,
            "valid_range": {"min": min_price, "max": max_price},
            "reported_price": reported_price
        }
        
        if is_valid:
            return True, "Precio válido (modo fallback)", validation_info
        else:
            reason = f"Precio fuera del rango fallback (${min_price} - ${max_price})"
            return False, reason, validation_info
    
    async def validate_price_report(self, form_data: dict, request_ip: str) -> Tuple[bool, str]:
        """
        Validación completa para reporte de precio:
        1. CAPTCHA
        2. Rate limiting
        3. Validación dinámica de precio
        """
        # 1. Verificar CAPTCHA
        captcha_token = form_data.get("g-recaptcha-response")
        captcha_valid, captcha_msg = await self.verify_recaptcha(captcha_token, request_ip)
        if not captcha_valid:
            return False, f"CAPTCHA: {captcha_msg}"
        
        # 2. Verificar rate limiting
        rate_limit_ok, rate_msg = self.check_price_report_rate_limit(request_ip)
        if not rate_limit_ok:
            return False, f"Rate limit: {rate_msg}"
        
        # 3. Validar precio dinámicamente
        fuel_type = form_data.get("fuel_type", "")
        try:
            price = float(form_data.get("reported_price", 0))
        except (ValueError, TypeError):
            return False, "Precio inválido"
        
        price_valid, price_msg, _ = await self.validate_price_dynamically(fuel_type, price)
        if not price_valid:
            return False, f"Precio: {price_msg}"
        
        return True, "Todas las validaciones pasaron"
    
    async def validate_review(self, form_data: dict, request_ip: str) -> Tuple[bool, str]:
        """
        Validación completa para reseña:
        1. CAPTCHA
        2. Rate limiting
        3. Validación básica de contenido
        """
        # 1. Verificar CAPTCHA
        captcha_token = form_data.get("g-recaptcha-response")
        captcha_valid, captcha_msg = await self.verify_recaptcha(captcha_token, request_ip)
        if not captcha_valid:
            return False, f"CAPTCHA: {captcha_msg}"
        
        # 2. Verificar rate limiting
        rate_limit_ok, rate_msg = self.check_review_rate_limit(request_ip)
        if not rate_limit_ok:
            return False, f"Rate limit: {rate_msg}"
        
        # 3. Validación básica de contenido
        name = form_data.get("name", "").strip()
        comment = form_data.get("comment", "").strip()
        rating = form_data.get("rating")
        
        if len(name) < 2:
            return False, "Nombre muy corto (mínimo 2 caracteres)"
        
        if len(comment) < 10:
            return False, "Comentario muy corto (mínimo 10 caracteres)"
        
        try:
            rating_int = int(rating)
            if not 1 <= rating_int <= 5:
                return False, "Calificación debe estar entre 1 y 5"
        except (ValueError, TypeError):
            return False, "Calificación inválida"
        
        return True, "Todas las validaciones pasaron"


# Instancia global del servicio
protection_service = ProtectionService()