# app/api/v1/ia_router.py
"""
Endpoints del módulo G. IA Asistente (voz / texto) — CICLO 2.

MAPEO DEL CICLO 1 AL CICLO 2 (el módulo G se refundó como AGENTE DEV):
- POST /proyectos/{proyecto_id}/prompt  → IGUAL RUTA. En el Ciclo 1 lo
  atendía IAService; en el Ciclo 2 atiende CanalService.procesar_prompt
  (Tanda 15): si el PromptIARequest trae id_diagrama deriva al AGENTE DEV
  (orquestador T16), si no al CHAT GENERAL. La ruta conserva {proyecto_id}
  por compatibilidad, aunque el service deriva el proyecto del
  id_diagrama del payload (el schema Ciclo 2 no lo lleva en la ruta).
- POST /acciones/confirmar              → reemplaza
  POST /interacciones/{interaccion_id}/confirmar: la "interacción" es hoy
  el MensajeChat; ConfirmarAccionIARequest lleva id_mensaje + ids de
  AccionIA y EjecutorAccionesService (T16) las aplica al lienzo.
- GET  /mensajes/{id_mensaje}/acciones  → reemplaza
  GET /interacciones/{interaccion_id}: acciones propuestas en el turno de
  ese mensaje (nuevo list_by_mensaje del AccionIARepository).
- GET  /diagramas/{diagrama_id}/acciones → reemplaza
  GET /diagramas/{diagrama_id}/interacciones (AccionIARepository).
- GET  /proyectos/{proyecto_id}/acciones → reemplaza
  GET /proyectos/{proyecto_id}/interacciones (resuelve los diagramas del
  proyecto y consulta con $in — nuevo list_by_diagramas).

La IA de VISIÓN (boceto/imagen) va en `ai_vision_router.py`; la voz usa
TranscripcionVozResponse (transcriptor_voz de app/ia/, Tanda 11).
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_active_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.usuario import Usuario
from app.repositories.accion_ia_repository import AccionIARepository
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.ia_schema import (
    AccionIAResponse,
    ConfirmarAccionIARequest,
    PromptIARequest,
    RespuestaIA,
)
from app.services.canal_service import CanalService
from app.services.ejecutor_acciones_service import EjecutorAccionesService

router = APIRouter()


# ======================================================================
# PROMPT (VOZ / TEXTO) — misma ruta que el Ciclo 1
# ======================================================================
@router.post(
    "/proyectos/{proyecto_id}/prompt",
    response_model=RespuestaIA,
    summary="Enviar prompt de voz/texto a la IA (agente o chat general)",
    description=(
        "Persiste el mensaje del usuario, consulta al agente (o al chat "
        "general si no trae id_diagrama) y devuelve las ACCIONES "
        "PROPUESTAS sin aplicarlas. El cliente confirma por ids vía "
        "POST /acciones/confirmar antes de que el ejecutor toque el lienzo."
    ),
)
async def enviar_prompt(
    proyecto_id: PydanticObjectId,
    datos: PromptIARequest,
    current_user: Usuario = Depends(get_current_active_user),
) -> RespuestaIA:
    # El service deriva el proyecto del id_diagrama del payload y valida
    # la membresía de lectura; {proyecto_id} se conserva por compatibilidad
    # de ruta con el Ciclo 1.
    service = CanalService()
    return await service.procesar_prompt(current_user.id, datos)


# ======================================================================
# CONFIRMAR ACCIONES (antes /interacciones/{id}/confirmar)
# ======================================================================
@router.post(
    "/acciones/confirmar",
    response_model=list[AccionIAResponse],
    summary="Confirmar acciones propuestas por el agente",
    description=(
        "Aplica las AccionIA (ids) propuestas en el turno del mensaje "
        "indicado. Devuelve CADA acción con su estado final (APLICADA o "
        "FALLIDA; los fallos van en detalle_resultado). Solo el autor del "
        "prompt puede confirmar (lo valida el ejecutor)."
    ),
)
async def confirmar_acciones(
    datos: ConfirmarAccionIARequest,
    current_user: Usuario = Depends(get_current_active_user),
) -> list[AccionIAResponse]:
    service = EjecutorAccionesService()
    return await service.confirmar_acciones(current_user.id, datos)


# ======================================================================
# CONSULTAS
# ======================================================================
@router.get(
    "/mensajes/{id_mensaje}/acciones",
    response_model=list[AccionIAResponse],
    summary="Acciones propuestas en el turno de un mensaje",
    description=(
        "Reemplaza a GET /interacciones/{id} del Ciclo 1: la interacción "
        "es hoy el MensajeChat; devuelve sus AccionIA (cualquiera que sea "
        "su estado). Solo el dueño del mensaje puede consultarlo."
    ),
)
async def acciones_de_mensaje(
    id_mensaje: PydanticObjectId,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
):
    # Permisos: el mismo criterio del chat — solo el dueño lee su mensaje
    await CanalService().obtener_mensaje(
        id_mensaje, usuario_id=current_user.id
    )
    acciones = await AccionIARepository().list_by_mensaje(
        id_mensaje, skip=skip, limit=limit
    )
    return [AccionIAResponse.model_validate(a) for a in acciones]


@router.get(
    "/diagramas/{diagrama_id}/acciones",
    response_model=list[AccionIAResponse],
    summary="Historial de acciones del agente sobre un diagrama",
    description=(
        "Reemplaza a GET /diagramas/{id}/interacciones del Ciclo 1: las "
        "acciones (PROPUESTA/APLICADA/RECHAZADA/FALLIDA) ligadas al "
        "diagrama, la más nueva primero. Miembros del proyecto."
    ),
)
async def acciones_de_diagrama(
    diagrama_id: PydanticObjectId,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
):
    await _require_lectura_de_diagrama(diagrama_id, current_user)
    acciones = await AccionIARepository().list_by_diagrama(
        diagrama_id, skip=skip, limit=limit
    )
    return [AccionIAResponse.model_validate(a) for a in acciones]


@router.get(
    "/proyectos/{proyecto_id}/acciones",
    response_model=list[AccionIAResponse],
    summary="Historial de acciones del agente en todo el proyecto",
    description=(
        "Reemplaza a GET /proyectos/{id}/interacciones del Ciclo 1: "
        "resuelve los diagramas del proyecto y devuelve el historial "
        "combinado de acciones ($in sobre id_diagrama). Miembros del "
        "proyecto."
    ),
)
async def acciones_de_proyecto(
    proyecto_id: PydanticObjectId,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
):
    miembro = await MiembroProyectoRepository().get_by_proyecto_usuario(
        proyecto_id, current_user.id
    )
    if miembro is None:
        raise ForbiddenError("No pertenece a este proyecto")

    diagramas = await DiagramaRepository().list_by_proyecto(proyecto_id)
    acciones = await AccionIARepository().list_by_diagramas(
        [d.id for d in diagramas], skip=skip, limit=limit
    )
    return [AccionIAResponse.model_validate(a) for a in acciones]


# ======================================================================
# Helpers de pertenencia (mismo criterio del módulo C)
# ======================================================================
async def _require_lectura_de_diagrama(diagrama_id, current_user: Usuario) -> None:
    diagrama = await DiagramaRepository().get_by_id(diagrama_id)
    if diagrama is None:
        raise NotFoundError("Diagrama no encontrado")
    miembro = await MiembroProyectoRepository().get_by_proyecto_usuario(
        diagrama.id_proyecto, current_user.id
    )
    if miembro is None:
        raise NotFoundError("Recurso no encontrado")