# app/main.py
"""
Punto de entrada de DevForge AI (backend FastAPI, Capa 1) — CICLO 2.

Responsabilidades:
- Crear la instancia FastAPI con metadata y documentación.
- Configurar CORS, middleware y manejadores de errores.
- Registrar todos los routers de la API v1 (los MISMOS 13 del Ciclo 1).
- Registrar el router WebSocket de colaboración (agregador de app/websocket).
- Exponer endpoints base (root + health).
- Registrar los hooks de ciclo de vida (MongoDB init/close).

Cambios respecto al Ciclo 1:
- PostgreSQL/SQLAlchemy → MongoDB (app.mongo init_db/close_db, Tanda 2).
- Los 13 routers se CONSERVAN (app/api/v1/__init__.py de la Tanda 19):
  el módulo G es `ia_router`, refundado como AGENTE DEV (Tandas 15-16):
  POST /proyectos/{proyecto_id}/prompt deriva al orquestador si el payload
  trae id_diagrama, o al CHAT GENERAL si no; las acciones se confirman con
  POST /acciones/confirmar (EjecutorAccionesService).
  NOTA: el borrador de la Tanda 2 registraba `canal_router` y
  `asistente_router` como routers separados; esa división NO se materializó
  (Tanda 19): ambos roles viven en ia_router + ai_vision_router.
- La IA de VISIÓN (boceto → UML completo) va en ai_vision_router.
- WebSocket: se monta el AGREGADOR `router` del paquete app/websocket
  (Tanda 19b), ruta /ws/diagramas/{diagrama_id}.
- La generación de proyectos generados y las descargas XMI se sirven desde
  los propios routers (FileResponse sobre GENERATED_PROJECTS_DIR / EXPORT_DIR):
  NO hace falta StaticFiles en main.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.mongo import close_db, init_db

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
    logger.info("Conexión a MongoDB verificada.")
    try:
        yield
    finally:
        await close_db()
        logger.info("Conexión a MongoDB cerrada. Hasta luego.")


# ----------------------------------------------------------------------
# Instancia FastAPI
# ----------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Backend de la plataforma CASE colaborativa DevForge AI: "
        "usuarios, proyectos, modelado UML colaborativo (UML 2.5.1), "
        "trazabilidad, generación automática de backend Spring Boot y "
        "frontend React, Agente Dev (IA de equipo en el canal), "
        "Asistente Guía (aprendizaje de la herramienta), voz local y "
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
# Routers (API v1) — los MISMOS 13 routers que el Ciclo 1 (Tanda 19)
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

# --- G. IA (Agente Dev en el canal + Asistente Guía + prompt voz/texto) ---
app.include_router(
    ia_router.router,
    prefix=f"{settings.API_V1_PREFIX}/ia",
    tags=["IA (Agente Dev)"],
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
# WebSocket (colaboración en tiempo real) — agregador del paquete (Tanda 19b)
# ----------------------------------------------------------------------
from app.websocket import router as ws_router  # noqa: E402
app.include_router(ws_router)


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
