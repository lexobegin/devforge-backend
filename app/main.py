# app/main.py
"""
Punto de entrada de DevForge AI (backend FastAPI, Capa 1).

Responsabilidades:
- Crear la instancia FastAPI con metadata y documentación.
- Configurar CORS, middleware y manejadores de errores.
- Registrar todos los routers de la API v1.
- Registrar el router WebSocket de colaboración.
- Exponer endpoints base (root + health).
- Registrar los hooks de ciclo de vida (DB init/close).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.database import close_db, init_db

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(level=settings.LOG_LEVEL, format=settings.LOG_FORMAT)
logger = logging.getLogger("devforge")


# ----------------------------------------------------------------------
# Ciclo de vida (lifespan)
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando DevForge AI backend (env=%s)", settings.APP_ENV)
    await init_db()
    logger.info("Conexión a PostgreSQL verificada.")
    try:
        yield
    finally:
        await close_db()
        logger.info("Conexión a PostgreSQL cerrada. Hasta luego.")


# ----------------------------------------------------------------------
# Instancia FastAPI
# ----------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Backend de la plataforma CASE colaborativa DevForge AI: "
        "usuarios, proyectos, modelado UML colaborativo, trazabilidad, "
        "generación automática de backend Spring Boot, IA asistente y "
        "sincronización offline."
    ),
    docs_url="/docs" if not settings.IS_PRODUCTION else None,
    redoc_url="/redoc" if not settings.IS_PRODUCTION else None,
    openapi_url="/openapi.json" if not settings.IS_PRODUCTION else None,
    lifespan=lifespan,
)


# ----------------------------------------------------------------------
# CORS
# ----------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


# ----------------------------------------------------------------------
# Manejadores de errores personalizados
# ----------------------------------------------------------------------
register_exception_handlers(app)


# ----------------------------------------------------------------------
# Routers (API v1)
# ----------------------------------------------------------------------
from app.api.v1 import (  # noqa: E402
    ai_vision_router,
    auditoria_router,
    auth_router,
    colaboracion_router,
    diagramas_router,
    generacion_router,
    ia_router,
    intercambio_router,
    notificaciones_router,
    proyectos_router,
    sincronizacion_router,
    trazabilidad_router,
    usuarios_router,
)

# --- A. Usuarios y Seguridad ---
app.include_router(
    auth_router.router,
    prefix=f"{settings.API_V1_PREFIX}/auth",
    tags=["Auth"],
)
app.include_router(
    usuarios_router.router,
    prefix=f"{settings.API_V1_PREFIX}/usuarios",
    tags=["Usuarios"],
)

# --- B. Proyectos y Colaboración ---
app.include_router(
    proyectos_router.router,
    prefix=f"{settings.API_V1_PREFIX}/proyectos",
    tags=["Proyectos"],
)
app.include_router(
    colaboracion_router.router,
    prefix=f"{settings.API_V1_PREFIX}/colaboracion",
    tags=["Colaboración"],
)

# --- C. Modelado UML ---
app.include_router(
    diagramas_router.router,
    prefix=f"{settings.API_V1_PREFIX}/diagramas",
    tags=["Diagramas UML"],
)

# --- D. Trazabilidad ---
app.include_router(
    trazabilidad_router.router,
    prefix=f"{settings.API_V1_PREFIX}/trazabilidad",
    tags=["Trazabilidad"],
)

# --- E. Intercambio ---
app.include_router(
    intercambio_router.router,
    prefix=f"{settings.API_V1_PREFIX}/intercambio",
    tags=["Intercambio XMI"],
)

# --- F. Generación ---
app.include_router(
    generacion_router.router,
    prefix=f"{settings.API_V1_PREFIX}/generacion",
    tags=["Generación de Código"],
)

# --- G. IA ---
app.include_router(
    ia_router.router,
    prefix=f"{settings.API_V1_PREFIX}/ia",
    tags=["IA (voz/texto)"],
)
app.include_router(
    ai_vision_router.router,
    prefix=f"{settings.API_V1_PREFIX}/ai-vision",
    tags=["IA Visión (boceto)"],
)

# --- H. Sincronización ---
app.include_router(
    sincronizacion_router.router,
    prefix=f"{settings.API_V1_PREFIX}/sincronizacion",
    tags=["Sincronización Offline"],
)

# --- I. Notificaciones ---
app.include_router(
    notificaciones_router.router,
    prefix=f"{settings.API_V1_PREFIX}/notificaciones",
    tags=["Notificaciones"],
)

# --- Administración y Auditoría ---
app.include_router(
    auditoria_router.router,
    prefix=f"{settings.API_V1_PREFIX}/auditoria",
    tags=["Auditoría"],
)


# ----------------------------------------------------------------------
# WebSocket (colaboración en tiempo real)
# ----------------------------------------------------------------------
# Se activará cuando implementemos app/websocket/collaboration_ws.py
from app.websocket import collaboration_ws
app.include_router(collaboration_ws.router)


# ----------------------------------------------------------------------
# Endpoints base
# ----------------------------------------------------------------------
@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "docs": "/docs" if not settings.IS_PRODUCTION else None,
    }


@app.get("/health", tags=["Health"])
async def health():
    """Health-check simple para Nginx / balanceadores / monitoreo."""
    return {"status": "ok", "env": settings.APP_ENV}