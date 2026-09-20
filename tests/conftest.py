# tests/conftest.py
"""
Fixtures compartidos para los tests del backend.

Estrategia:
- Se usa una base de datos SQLite en memoria para tests rápidos, con
  adaptación del motor async a SQLite (aiosqlite).
- La app FastAPI se arranca con `dependency_overrides` para inyectar la
  sesión de test.
- Se proveen helpers: `client` (httpx AsyncClient), `db_session`,
  `usuario_creado`, `token_usuario`.

Nota: si necesitas probar contra PostgreSQL real (por JSONB, CHECK
constraints, etc.), cambia la URL del engine en `_TEST_DATABASE_URL`.
"""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
from app.main import app
from app.models.usuario import Usuario

# ----------------------------------------------------------------------
# Configuración de BD de test
# ----------------------------------------------------------------------
# SQLite en memoria con aiosqlite. Para PostgreSQL real, usar:
# _TEST_DATABASE_URL = "postgresql+asyncpg://devforge:devforge@localhost:5432/devforge_test"
_TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ----------------------------------------------------------------------
# Event loop (pytest-asyncio)
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ----------------------------------------------------------------------
# Engine + sesión de test
# ----------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(
        _TEST_DATABASE_URL,
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with SessionLocal() as session:
        yield session


# ----------------------------------------------------------------------
# Cliente HTTP
# ----------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Cliente HTTP con la dependencia `get_db` sobreescrita para usar la
    sesión de test.
    """
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ----------------------------------------------------------------------
# Helpers: usuario registrado + token
# ----------------------------------------------------------------------
@pytest_asyncio.fixture
async def usuario_creado(client: AsyncClient) -> dict:
    """Registra un usuario y devuelve sus datos."""
    payload = {
        "nombre_completo": "Juan Pérez",
        "email": "juan@example.com",
        "password": "password123",
        "rol": "DESARROLLADOR",
    }
    r = await client.post("/api/v1/auth/registro", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


@pytest_asyncio.fixture
async def token_usuario(client: AsyncClient, usuario_creado: dict) -> str:
    """Devuelve un access token válido para el usuario registrado."""
    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": usuario_creado["email"],
            "password": "password123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(token_usuario: str) -> dict:
    """Headers con Authorization Bearer listos para usar."""
    return {"Authorization": f"Bearer {token_usuario}"}