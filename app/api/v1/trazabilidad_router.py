# app/api/v1/trazabilidad_router.py
"""
Endpoints del módulo D. Trazabilidad — CICLO 2.

Historial de cambios:
- GET    /api/v1/trazabilidad/diagramas/{id}/historial              → historial del diagrama
- GET    /api/v1/trazabilidad/diagramas/{id}/historial/{tipo}/{eid} → historial de un elemento

Versiones:
- GET    /api/v1/trazabilidad/diagramas/{id}/versiones              → listar (sin contenido)
- POST   /api/v1/trazabilidad/diagramas/{id}/versiones              → guardar snapshot
- GET    /api/v1/trazabilidad/versiones/{version_id}                → obtener (con contenido)
- GET    /api/v1/trazabilidad/diagramas/{id}/versiones/ultima       → última versión

Comentarios:
- GET    /api/v1/trazabilidad/diagramas/{id}/comentarios            → listar
- GET    /api/v1/trazabilidad/diagramas/{id}/comentarios/{tipo}/{eid} → comentarios de un elemento
- POST   /api/v1/trazabilidad/diagramas/{id}/comentarios            → crear
- PUT    /api/v1/trazabilidad/comentarios/{comentario_id}           → actualizar (texto/resuelto)
- DELETE /api/v1/trazabilidad/comentarios/{comentario_id}           → eliminar

CICLO 2 (reconvertido del Ciclo 1): SIN AsyncSession; ids de ruta
PydanticObjectId; el id_entidad de las rutas /{tipo}/{eid} es str (los
elementos van EMBEBIDOS en el Diagrama con uuid str; en el Ciclo 1 era el
int del serial). El contenido_json de las versiones se guarda igual
(ahora dentro del documento, sin límite de columnas).
"""

from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_current_active_user
from app.models.usuario import Usuario
from app.schemas.trazabilidad_schema import (
    ComentarioDiagramaCreate,
    ComentarioDiagramaResponse,
    ComentarioDiagramaUpdate,
    HistorialCambioDiagramaResponse,
    VersionDiagramaCreate,
    VersionDiagramaResponse,
    VersionDiagramaResumenResponse,
)
from app.services.trazabilidad_service import TrazabilidadService

router = APIRouter()


# ======================================================================
# HISTORIAL
# ======================================================================
@router.get(
    "/diagramas/{diagrama_id}/historial",
    response_model=list[HistorialCambioDiagramaResponse],
    summary="Listar historial de cambios de un diagrama",
    description="Permite filtrar por rango de fechas (desde/hasta) y paginar.",
)
async def listar_historial(
    diagrama_id: PydanticObjectId,
    desde: Optional[datetime] = Query(None, description="ISO 8601"),
    hasta: Optional[datetime] = Query(None, description="ISO 8601"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: Usuario = Depends(get_current_active_user),
):
    service = TrazabilidadService()
    return await service.listar_historial(
        diagrama_id,
        usuario_id=current_user.id,
        desde=desde,
        hasta=hasta,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/diagramas/{diagrama_id}/historial/{tipo_entidad}/{id_entidad}",
    response_model=list[HistorialCambioDiagramaResponse],
    summary="Historial de cambios de un elemento concreto",
    description=(
        "Ej: tipo_entidad='CLASE', id_entidad=<uuid de la clase embebida> "
        "devuelve todos los cambios hechos sobre esa clase."
    ),
)
async def listar_historial_de_elemento(
    diagrama_id: PydanticObjectId,
    tipo_entidad: str,
    id_entidad: str,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = TrazabilidadService()
    return await service.listar_historial_de_elemento(
        diagrama_id,
        tipo_entidad.upper(),
        id_entidad,
        usuario_id=current_user.id,
    )


# ======================================================================
# VERSIONES
# ======================================================================
@router.get(
    "/diagramas/{diagrama_id}/versiones",
    response_model=list[VersionDiagramaResumenResponse],
    summary="Listar versiones del diagrama (sin contenido completo)",
    description=(
        "Devuelve metadatos de las versiones, sin el `contenido_json` que "
        "puede ser muy grande. Para obtener una versión completa use "
        "GET /versiones/{version_id}."
    ),
)
async def listar_versiones(
    diagrama_id: PydanticObjectId,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
):
    service = TrazabilidadService()
    return await service.listar_versiones(
        diagrama_id,
        usuario_id=current_user.id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/diagramas/{diagrama_id}/versiones",
    response_model=VersionDiagramaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Guardar un snapshot completo del diagrama",
    description=(
        "El número de versión se calcula automáticamente (correlativo). "
        "Además incrementa `diagramas.numero_version`."
    ),
)
async def guardar_version(
    diagrama_id: PydanticObjectId,
    datos: VersionDiagramaCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> VersionDiagramaResponse:
    service = TrazabilidadService()
    return await service.guardar_version(
        diagrama_id, datos, usuario_id=current_user.id
    )


@router.get(
    "/versiones/{version_id}",
    response_model=VersionDiagramaResponse,
    summary="Obtener una versión completa (incluye contenido_json)",
)
async def obtener_version(
    version_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> VersionDiagramaResponse:
    service = TrazabilidadService()
    return await service.obtener_version(
        version_id, usuario_id=current_user.id
    )


@router.get(
    "/diagramas/{diagrama_id}/versiones/ultima",
    response_model=VersionDiagramaResponse | None,
    summary="Obtener la última versión guardada del diagrama",
    description="Devuelve `null` si el diagrama aún no tiene versiones guardadas.",
)
async def obtener_ultima_version(
    diagrama_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = TrazabilidadService()
    return await service.obtener_ultima_version(
        diagrama_id, usuario_id=current_user.id
    )


# ======================================================================
# COMENTARIOS
# ======================================================================
@router.get(
    "/diagramas/{diagrama_id}/comentarios",
    response_model=list[ComentarioDiagramaResponse],
    summary="Listar comentarios del diagrama",
)
async def listar_comentarios(
    diagrama_id: PydanticObjectId,
    solo_no_resueltos: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: Usuario = Depends(get_current_active_user),
):
    service = TrazabilidadService()
    return await service.listar_comentarios(
        diagrama_id,
        usuario_id=current_user.id,
        solo_no_resueltos=solo_no_resueltos,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/diagramas/{diagrama_id}/comentarios/{tipo_entidad}/{id_entidad}",
    response_model=list[ComentarioDiagramaResponse],
    summary="Comentarios sobre un elemento concreto del diagrama",
)
async def listar_comentarios_de_elemento(
    diagrama_id: PydanticObjectId,
    tipo_entidad: str,
    id_entidad: str,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = TrazabilidadService()
    return await service.listar_comentarios_de_elemento(
        diagrama_id,
        tipo_entidad.upper(),
        id_entidad,
        usuario_id=current_user.id,
    )


@router.post(
    "/diagramas/{diagrama_id}/comentarios",
    response_model=ComentarioDiagramaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear comentario sobre el diagrama o un elemento",
    description=(
        "Si `tipo_entidad` e `id_entidad` vienen informados, es un comentario "
        "sobre un elemento (clase, relación, etc.). Si vienen ambos en null, "
        "es un comentario general del diagrama."
    ),
)
async def crear_comentario(
    diagrama_id: PydanticObjectId,
    datos: ComentarioDiagramaCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> ComentarioDiagramaResponse:
    service = TrazabilidadService()
    return await service.crear_comentario(
        diagrama_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/comentarios/{comentario_id}",
    response_model=ComentarioDiagramaResponse,
    summary="Actualizar comentario (texto y/o marcar como resuelto)",
    description=(
        "Solo el autor puede editar el `texto`. Cualquier EDITOR/PROPIETARIO "
        "del proyecto puede marcar `resuelto`."
    ),
)
async def actualizar_comentario(
    comentario_id: PydanticObjectId,
    datos: ComentarioDiagramaUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> ComentarioDiagramaResponse:
    service = TrazabilidadService()
    return await service.actualizar_comentario(
        comentario_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/comentarios/{comentario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar comentario (solo el autor)",
)
async def eliminar_comentario(
    comentario_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = TrazabilidadService()
    await service.eliminar_comentario(
        comentario_id, usuario_id=current_user.id
    )