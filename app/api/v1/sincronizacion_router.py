# app/api/v1/sincronizacion_router.py
"""
Endpoints del módulo H. Sincronización Móvil/Web Offline:

- POST /api/v1/sincronizacion/batch                          → enviar lote offline
- GET  /api/v1/sincronizacion/diagramas/{id}/conflictos      → listar conflictos pendientes
- POST /api/v1/sincronizacion/conflictos/{id}/resolver       → resolver conflicto
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.sincronizacion_schema import (
    BatchSincronizacionRequest,
    BatchSincronizacionResponse,
    ConflictoSyncResponse,
    ResolverConflictoRequest,
)
from app.services.sincronizacion_service import SincronizacionService

router = APIRouter()


# ======================================================================
# BATCH OFFLINE
# ======================================================================
@router.post(
    "/batch",
    response_model=BatchSincronizacionResponse,
    summary="Enviar lote de cambios offline",
    description=(
        "Recibe el batch completo de cambios hechos offline desde el cliente "
        "(móvil o web). Los procesa en orden FIFO, aplica los que puede y "
        "marca conflictos para los que no. Devuelve el mapeo de "
        "id_temporal_local → id_real."
    ),
)
async def enviar_batch(
    datos: BatchSincronizacionRequest,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BatchSincronizacionResponse:
    service = SincronizacionService(db)
    return await service.procesar_batch(datos, usuario_id=current_user.id)


# ======================================================================
# CONFLICTOS
# ======================================================================
@router.get(
    "/diagramas/{diagrama_id}/conflictos",
    response_model=list[ConflictoSyncResponse],
    summary="Listar conflictos pendientes de un diagrama",
    description=(
        "Solo el PROPIETARIO del proyecto puede consultar los conflictos "
        "para resolverlos manualmente."
    ),
)
async def listar_conflictos(
    diagrama_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = SincronizacionService(db)
    return await service.listar_conflictos(
        diagrama_id, usuario_id=current_user.id
    )


@router.post(
    "/conflictos/{conflicto_id}/resolver",
    response_model=ConflictoSyncResponse,
    summary="Resolver un conflicto (solo PROPIETARIO)",
    description=(
        "El PROPIETARIO elige la estrategia:\n"
        "- OFFLINE: aplicar el cambio offline.\n"
        "- SERVIDOR: descartar el cambio offline.\n"
        "- FUSIONAR: aplicar un payload fusionado custom."
    ),
)
async def resolver_conflicto(
    conflicto_id: int,
    datos: ResolverConflictoRequest,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ConflictoSyncResponse:
    service = SincronizacionService(db)
    return await service.resolver_conflicto(
        conflicto_id,
        estrategia=datos.estrategia,
        payload_fusionado=datos.payload_fusionado,
        usuario_id=current_user.id,
    )