# app/api/v1/colaboracion_router.py
"""
Endpoints REST auxiliares del módulo B. Colaboración.

La colaboración en TIEMPO REAL se hace por WebSocket (ver
`app/websocket/collaboration_ws.py`). Estos endpoints REST son para:
- Abrir/obtener la sesión activa de un diagrama.
- Consultar participantes conectados (para el panel de colaboradores).
- Unirse/salir formalmente de una sesión (además del evento WS).
- Actualizar la posición del cursor por HTTP (fallback si el WS cae).
- Cerrar sesiones activas de un diagrama (limpieza).

Endpoints:
- POST   /api/v1/colaboracion/diagramas/{diagrama_id}/sesion     → abrir/obtener
- GET    /api/v1/colaboracion/sesiones/{sesion_id}               → con participantes
- POST   /api/v1/colaboracion/sesiones/{sesion_id}/unirse        → unirse
- POST   /api/v1/colaboracion/sesiones/{sesion_id}/salir         → salir
- GET    /api/v1/colaboracion/sesiones/{sesion_id}/participantes → conectados
- GET    /api/v1/colaboracion/diagramas/{diagrama_id}/conectados → todos del diagrama
- PUT    /api/v1/colaboracion/sesiones/{sesion_id}/cursor        → actualizar cursor
- DELETE /api/v1/colaboracion/sesiones/{sesion_id}               → cerrar sesión
- DELETE /api/v1/colaboracion/diagramas/{diagrama_id}/sesiones   → cerrar todas
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.colaboracion_schema import (
    ParticipanteSesionResponse,
    ParticipanteSesionUpdate,
    SesionColaboracionResponse,
    SesionConParticipantesResponse,
)
from app.services.colaboracion_service import ColaboracionService

router = APIRouter()


# ======================================================================
# ABRIR / OBTENER SESIÓN
# ======================================================================
@router.post(
    "/diagramas/{diagrama_id}/sesion",
    response_model=SesionColaboracionResponse,
    summary="Abrir (o reutilizar) la sesión colaborativa activa de un diagrama",
    description=(
        "Si ya existe una sesión activa para el diagrama, la devuelve. "
        "Si no, crea una nueva. Idempotente."
    ),
)
async def abrir_sesion(
    diagrama_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SesionColaboracionResponse:
    service = ColaboracionService(db)
    return await service.abrir_o_obtener_sesion(
        diagrama_id, usuario_id=current_user.id
    )


@router.get(
    "/sesiones/{sesion_id}",
    response_model=SesionConParticipantesResponse,
    summary="Obtener sesión con sus participantes",
)
async def obtener_sesion(
    sesion_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SesionConParticipantesResponse:
    service = ColaboracionService(db)
    return await service.obtener_sesion_con_participantes(
        sesion_id, usuario_id=current_user.id
    )


# ======================================================================
# ENTRAR / SALIR
# ======================================================================
@router.post(
    "/sesiones/{sesion_id}/unirse",
    response_model=ParticipanteSesionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Unirse a una sesión colaborativa",
    description=(
        "Registra al usuario como participante. Si ya estaba conectado, "
        "devuelve el mismo registro (idempotente)."
    ),
)
async def unirse(
    sesion_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteSesionResponse:
    service = ColaboracionService(db)
    return await service.unir_participante(
        sesion_id, usuario_id=current_user.id
    )


@router.post(
    "/sesiones/{sesion_id}/salir",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Salir de una sesión colaborativa",
    description=(
        "Marca la salida del participante. Si era el último conectado, "
        "cierra la sesión automáticamente."
    ),
)
async def salir(
    sesion_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ColaboracionService(db)
    await service.salir_participante(sesion_id, usuario_id=current_user.id)


# ======================================================================
# PARTICIPANTES
# ======================================================================
@router.get(
    "/sesiones/{sesion_id}/participantes",
    response_model=list[ParticipanteSesionResponse],
    summary="Listar participantes conectados de una sesión",
)
async def listar_participantes(
    sesion_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = ColaboracionService(db)
    return await service.listar_participantes_conectados(
        sesion_id, usuario_id=current_user.id
    )


@router.get(
    "/diagramas/{diagrama_id}/conectados",
    response_model=list[ParticipanteSesionResponse],
    summary="Listar TODOS los conectados de un diagrama",
    description=(
        "Participantes conectados en cualquier sesión activa del diagrama. "
        "Lo usa el panel de colaboradores del editor."
    ),
)
async def listar_conectados_por_diagrama(
    diagrama_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = ColaboracionService(db)
    return await service.listar_conectados_por_diagrama(
        diagrama_id, usuario_id=current_user.id
    )


# ======================================================================
# CURSOR
# ======================================================================
@router.put(
    "/sesiones/{sesion_id}/cursor",
    response_model=ParticipanteSesionResponse,
    summary="Actualizar la posición del cursor en el lienzo",
    description=(
        "Fallback HTTP del evento WS `cursor_moved`. Persiste la posición "
        "JSONB del cursor del participante actual."
    ),
)
async def actualizar_cursor(
    sesion_id: int,
    datos: ParticipanteSesionUpdate,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteSesionResponse:
    service = ColaboracionService(db)
    return await service.actualizar_cursor(
        sesion_id, datos, usuario_id=current_user.id
    )


# ======================================================================
# CIERRE
# ======================================================================
@router.delete(
    "/sesiones/{sesion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar una sesión colaborativa",
)
async def cerrar_sesion(
    sesion_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ColaboracionService(db)
    await service.cerrar_sesion(sesion_id, usuario_id=current_user.id)


@router.delete(
    "/diagramas/{diagrama_id}/sesiones",
    response_model=dict,
    summary="Cerrar todas las sesiones activas de un diagrama",
    description=(
        "Marca la salida de todos los conectados y cierra todas las sesiones "
        "activas del diagrama. Devuelve el número de sesiones cerradas."
    ),
)
async def cerrar_sesiones_de_diagrama(
    diagrama_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ColaboracionService(db)
    cerradas = await service.cerrar_sesiones_de_diagrama(
        diagrama_id, usuario_id=current_user.id
    )
    return {"sesiones_cerradas": cerradas}