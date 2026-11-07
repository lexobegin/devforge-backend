# app/api/v1/notificaciones_router.py
"""
Endpoints del módulo I. Notificaciones — CICLO 2.

- GET    /api/v1/notificaciones                        → listar mis notificaciones
- GET    /api/v1/notificaciones/contador               → contador de no leídas (badge)
- GET    /api/v1/notificaciones/{id}                   → obtener una
- POST   /api/v1/notificaciones/marcar-leidas          → marcar varias / todas
- POST   /api/v1/notificaciones/{id}/leer              → marcar una como leída
- POST   /api/v1/notificaciones/{id}/no-leer           → marcar una como no leída
- DELETE /api/v1/notificaciones/{id}                   → eliminar una
- DELETE /api/v1/notificaciones/leidas                 → limpiar todas las leídas

CICLO 2 (reconvertido del Ciclo 1): SIN AsyncSession; ids de ruta
PydanticObjectId; errores de dominio del service traducidos a HTTP por
app/core/exceptions.py. Ruta estática /contador y /leidas ANTES de las
dinámicas /{id} (igual que el Ciclo 1).
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_active_user
from app.models.usuario import Usuario
from app.schemas.notificacion_schema import (
    ContadorNoLeidasResponse,
    MarcarNotificacionesLeidasRequest,
    NotificacionResponse,
)
from app.services.notificacion_service import NotificacionService

router = APIRouter()


# ======================================================================
# LISTAR Y CONTAR
# ======================================================================
@router.get(
    "",
    response_model=list[NotificacionResponse],
    summary="Listar mis notificaciones",
)
async def listar_notificaciones(
    solo_no_leidas: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
):
    service = NotificacionService()
    return await service.listar(
        current_user.id,
        solo_no_leidas=solo_no_leidas,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/contador",
    response_model=ContadorNoLeidasResponse,
    summary="Contador de notificaciones no leídas (badge)",
)
async def contador_no_leidas(
    current_user: Usuario = Depends(get_current_active_user),
) -> ContadorNoLeidasResponse:
    service = NotificacionService()
    return await service.contar_no_leidas(current_user.id)


# ======================================================================
# OBTENER UNA
# ======================================================================
@router.get(
    "/{notificacion_id}",
    response_model=NotificacionResponse,
    summary="Obtener una notificación",
)
async def obtener_notificacion(
    notificacion_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> NotificacionResponse:
    service = NotificacionService()
    return await service.obtener(
        notificacion_id, usuario_id=current_user.id
    )


# ======================================================================
# MARCAR LEÍDAS
# ======================================================================
@router.post(
    "/marcar-leidas",
    response_model=dict,
    summary="Marcar varias (o todas) notificaciones como leídas",
    description=(
        "Si `todas=True`, marca todas las no leídas. Si no, marca solo las "
        "de la lista `ids`. Devuelve el número de documentos actualizados."
    ),
)
async def marcar_leidas(
    datos: MarcarNotificacionesLeidasRequest,
    current_user: Usuario = Depends(get_current_active_user),
) -> dict:
    service = NotificacionService()
    total = await service.marcar_varias_leidas(
        current_user.id, ids=datos.ids, todas=datos.todas
    )
    return {"actualizadas": total}


@router.post(
    "/{notificacion_id}/leer",
    response_model=NotificacionResponse,
    summary="Marcar una notificación como leída",
)
async def marcar_leida(
    notificacion_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> NotificacionResponse:
    service = NotificacionService()
    return await service.marcar_leida(
        notificacion_id, usuario_id=current_user.id, leida=True
    )


@router.post(
    "/{notificacion_id}/no-leer",
    response_model=NotificacionResponse,
    summary="Marcar una notificación como no leída",
)
async def marcar_no_leida(
    notificacion_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> NotificacionResponse:
    service = NotificacionService()
    return await service.marcar_leida(
        notificacion_id, usuario_id=current_user.id, leida=False
    )


# ======================================================================
# ELIMINAR
# ======================================================================
@router.delete(
    "/leidas",
    response_model=dict,
    summary="Eliminar todas mis notificaciones leídas",
)
async def limpiar_leidas(
    current_user: Usuario = Depends(get_current_active_user),
) -> dict:
    service = NotificacionService()
    eliminadas = await service.limpiar_leidas(current_user.id)
    return {"eliminadas": eliminadas}


@router.delete(
    "/{notificacion_id}",
    status_code=204,
    summary="Eliminar una notificación",
)
async def eliminar_notificacion(
    notificacion_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = NotificacionService()
    await service.eliminar(notificacion_id, usuario_id=current_user.id)