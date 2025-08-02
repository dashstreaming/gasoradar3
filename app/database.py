"""
Configuración de base de datos con Supabase
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from .config import settings


# URL de conexión a Supabase (debe incluir +asyncpg://)
DATABASE_URL = settings.database_url

# Motor asíncrono
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,  # Solo mostrar SQL queries en debug
    future=True,
    poolclass=NullPool  # Para Supabase/serverless
)

# Sessionmaker para AsyncSession
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_async_session() -> AsyncSession:
    """
    Generador de sesión de base de datos para dependency injection
    """
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database() -> None:
    """
    Inicializar la base de datos (crear tablas si no existen)
    Solo usado para desarrollo/testing ya que tu DB ya está poblada
    """
    from .models import Base
    
    async with engine.begin() as conn:
        # En producción, comentar esta línea ya que tu DB ya existe
        # await conn.run_sync(Base.metadata.create_all)
        pass


async def close_database() -> None:
    """
    Cerrar las conexiones de base de datos
    """
    await engine.dispose()