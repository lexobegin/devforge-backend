# app/mongo.py
"""
Conexión a MongoDB con Motor + Beanie (Ciclo 2 — sustituye a app/database.py).

Expone:
- init_db(): conecta el cliente Motor, verifica la conexión e inicializa Beanie
  con todos los documentos y sus índices (reemplaza a Alembic).
- close_db(): cierra la conexión al apagar la app.
- get_db(): dependencia FastAPI que entrega el handle de la base para
  operaciones crudas (agregaciones, búsquedas por similitud, etc.).
  Nota: las operaciones ODM normales NO la necesitan — los documentos Beanie
  (Usuario.find(...), etc.) usan la conexión ya inicializada.

El cliente NO se crea al importar el módulo (sin efectos secundarios):
se crea dentro de init_db() durante el lifespan de la aplicación.
"""

import logging
from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.models import DOCUMENTOS

logger = logging.getLogger("devforge.mongo")

# ----------------------------------------------------------------------
# Estado global del cliente
# ----------------------------------------------------------------------
client: Optional[AsyncIOMotorClient] = None
database: Optional[AsyncIOMotorDatabase] = None


# ----------------------------------------------------------------------
# Ciclo de vida
# ----------------------------------------------------------------------
async def init_db() -> None:
    """
    Conecta a MongoDB e inicializa Beanie con los documentos del proyecto.

    - Los índices declarados en cada Document (p. ej. email único) se crean
      aquí automáticamente: reemplaza a las migraciones de Alembic.
    - Cambios estructurales posteriores (campos nuevos) NO requieren
      migración: MongoDB es schema-flexible; los índices nuevos se crean
      al reiniciar el servicio.
    """
    global client, database

    client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        appname=settings.APP_NAME,
    )

    # Verificación temprana: si MongoDB no responde, fallar al arrancar
    # (igual que hacía el SELECT 1 del Ciclo 1, mejor saberlo ya).
    await client.admin.command("ping")
    logger.info("Ping a MongoDB correcto (%s)", settings.MONGODB_URI)

    database = client[settings.MONGODB_DB]

    await init_beanie(
        database=database,
        document_models=DOCUMENTOS,
    )
    logger.info(
        "Beanie inicializado con %d documentos en la BD '%s'",
        len(DOCUMENTOS),
        settings.MONGODB_DB,
    )


async def close_db() -> None:
    """Cierra el cliente MongoDB al apagar la app."""
    global client, database
    if client is not None:
        client.close()
        logger.info("Conexión a MongoDB cerrada.")
    client = None
    database = None


# ----------------------------------------------------------------------
# Dependencia FastAPI (solo para operaciones crudas puntuales)
# ----------------------------------------------------------------------
def get_db() -> AsyncIOMotorDatabase:
    """
    Entrega el handle de la base para operaciones crudas (agregaciones,
    $lookup, búsquedas vectoriales, etc.).

    Uso: `db: AsyncIOMotorDatabase = Depends(get_db)`
    Requiere que init_db() ya se haya ejecutado (lifespan).
    """
    if database is None:
        raise RuntimeError("MongoDB no inicializado: init_db() no se ha ejecutado.")
    return database