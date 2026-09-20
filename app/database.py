# app/database.py
"""
Conexión a PostgreSQL con SQLAlchemy 2.x en modo async (asyncpg).

Expone:
- engine: motor async global
- AsyncSessionLocal: fábrica de sesiones
- Base: clase base declarativa para todos los modelos ORM
- get_db(): dependencia FastAPI que entrega una sesión por request
- init_db() / close_db(): hooks de ciclo de vida
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# ----------------------------------------------------------------------
# Motor async
# ----------------------------------------------------------------------
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    future=True,
)


# ----------------------------------------------------------------------
# Fábrica de sesiones
# ----------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ----------------------------------------------------------------------
# Clase base declarativa (SQLAlchemy 2.x)
# ----------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base común para todos los modelos ORM de DevForge AI."""
    pass


# ----------------------------------------------------------------------
# Dependencia FastAPI
# ----------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Entrega una AsyncSession por request y garantiza su cierre.
    Uso: `db: AsyncSession = Depends(get_db)`
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ----------------------------------------------------------------------
# Ciclo de vida
# ----------------------------------------------------------------------
async def init_db() -> None:
    """
    Verifica la conexión a la base de datos al arrancar la app.
    La creación de tablas se maneja con Alembic (no autogenerar aquí).
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """Cierra el pool de conexiones al apagar la app."""
    await engine.dispose()