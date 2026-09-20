# app/api/v1/ia_router.py
"""
Endpoints del módulo G. IA Asistente (voz / texto).

- POST   /api/v1/ia/proyectos/{proyecto_id}/prompt          → enviar prompt de voz/texto
- POST   /api/v1/ia/interacciones/{interaccion_id}/confirmar → confirmar acciones propuestas
- GET    /api/v1/ia/interacciones/{interaccion_id}           → obtener interacción
- GET    /api/v1/ia/proyectos/{proyecto_id}/interacciones    → historial por proyecto
- GET    /api/v1/ia/diagramas/{diagrama_id}/interacciones    → historial por diagrama

La IA de VISIÓN (boceto/imagen) va en `ai_vision_router.py`.
"""

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.ia_schema import (
    ConfirmarAccionIARequest,
    InteraccionIAResponse,
    PromptIARequest,
    RespuestaIA,
)
from app.services.ia_service import IAService

router = APIRouter()


# ======================================================================
# PROMPT (VOZ / TEXTO)
# ======================================================================
@router.post(
    "/proyectos/{proyecto_id}/prompt",
    response_model=RespuestaIA,
    summary="Enviar prompt de voz/texto a la IA (modo online)",
    description=(
        "Persiste la interacción, delega en el proveedor de IA y devuelve "
        "las acciones propuestas. El cliente debe confirmar antes de aplicar."
    ),
)
async def enviar_prompt(
    proyecto_id: int,
    datos: PromptIARequest,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RespuestaIA:
    service = IAService(db)
    return await service.procesar_prompt(
        proyecto_id, datos, usuario_id=current_user.id
    )


# ======================================================================
# CONFIRMAR ACCIONES
# ======================================================================
@router.post(
    "/interacciones/{interaccion_id}/confirmar",
    response_model=InteraccionIAResponse,
    summary="Confirmar acciones propuestas por la IA",
    description=(
        "Marca como aplicadas las acciones de una interacción. El cliente ya "
        "aplicó los cambios al diagrama (vía WS o REST); esto solo deja "
        "constancia. Solo el autor de la interacción puede confirmarla."
    ),
)
async def confirmar_acciones(
    interaccion_id: int,
    datos: ConfirmarAccionIARequest,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> InteraccionIAResponse:
    service = IAService(db)
    return await service.confirmar_acciones(
        interaccion_id,
        datos.acciones_a_aplicar,
        usuario_id=current_user.id,
    )


# ======================================================================
# CONSULTAS
# ======================================================================
@router.get(
    "/interacciones/{interaccion_id}",
    response_model=InteraccionIAResponse,
    summary="Obtener una interacción de IA",
)
async def obtener_interaccion(
    interaccion_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> InteraccionIAResponse:
    service = IAService(db)
    return await service.obtener_interaccion(
        interaccion_id, usuario_id=current_user.id
    )


@router.get(
    "/proyectos/{proyecto_id}/interacciones",
    response_model=list[InteraccionIAResponse],
    summary="Historial de interacciones de IA de un proyecto",
)
async def listar_por_proyecto(
    proyecto_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = IAService(db)
    return await service.listar_por_proyecto(
        proyecto_id, usuario_id=current_user.id, skip=skip, limit=limit
    )


@router.get(
    "/diagramas/{diagrama_id}/interacciones",
    response_model=list[InteraccionIAResponse],
    summary="Historial de interacciones de IA de un diagrama",
)
async def listar_por_diagrama(
    diagrama_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = IAService(db)
    return await service.listar_por_diagrama(
        diagrama_id, usuario_id=current_user.id, skip=skip, limit=limit
    )