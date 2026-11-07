# app/api/v1/auditoria_router.py
"""
Endpoints del módulo de Auditoría (CU3 — Consultar Bitácora del Sistema)
— CICLO 2.

- GET /api/v1/auditoria                          → listar bitácora con filtros
- GET /api/v1/auditoria/entidad/{entidad}/{id}   → eventos de un recurso concreto
- GET /api/v1/auditoria/usuario/{usuario_id}     → eventos de un usuario
- GET /api/v1/auditoria/exportar/excel           → exportar a Excel
- GET /api/v1/auditoria/exportar/pdf             → exportar a PDF

Todos los endpoints requieren rol ADMIN.

CICLO 2 (reconvertido del Ciclo 1): SIN AsyncSession; el id del recurso
en la ruta de /entidad es str (los ObjectId van como hex; en el Ciclo 1
era el int del serial) y id_usuario es PydanticObjectId. Los filtros de
rango de fechas y el streaming de exportaciones se conservan igual.
"""

from datetime import datetime
from io import BytesIO
from typing import Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.dependencies import require_admin
from app.models.usuario import Usuario
from app.schemas.auditoria_schema import BitacoraSistemaResponse
from app.services.auditoria_service import AuditoriaService

router = APIRouter()


# ======================================================================
# LISTAR CON FILTROS
# ======================================================================
@router.get(
    "",
    response_model=dict,
    summary="Listar bitácora del sistema (solo ADMIN)",
    description=(
        "Permite filtrar por usuario, tipo de evento, entidad afectada y "
        "rango de fechas. Devuelve items + total para paginación."
    ),
)
async def listar_bitacora(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    id_usuario: Optional[PydanticObjectId] = Query(None),
    tipo_evento: Optional[str] = Query(None, max_length=50),
    entidad_afectada: Optional[str] = Query(None, max_length=30),
    desde: Optional[datetime] = Query(None, description="ISO 8601"),
    hasta: Optional[datetime] = Query(None, description="ISO 8601"),
    _admin: Usuario = Depends(require_admin),
) -> dict:
    service = AuditoriaService()
    items, total = await service.listar(
        skip=skip,
        limit=limit,
        id_usuario=id_usuario,
        tipo_evento=tipo_evento,
        entidad_afectada=entidad_afectada,
        desde=desde,
        hasta=hasta,
    )
    return {
        "items": [
            BitacoraSistemaResponse.model_validate(e).model_dump() for e in items
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ======================================================================
# POR ENTIDAD / POR USUARIO
# ======================================================================
@router.get(
    "/entidad/{entidad_afectada}/{id_entidad_afectada}",
    response_model=list[BitacoraSistemaResponse],
    summary="Eventos de un recurso concreto (solo ADMIN)",
    description=(
        "Ej: /auditoria/entidad/DIAGRAMA/665f1a… devuelve todos los eventos "
        "relacionados con ese diagrama (el id es el ObjectId en hex; en el "
        "Ciclo 1 era el int del serial)."
    ),
)
async def listar_por_entidad(
    entidad_afectada: str,
    id_entidad_afectada: str,
    _admin: Usuario = Depends(require_admin),
):
    service = AuditoriaService()
    items = await service.listar_por_entidad(
        entidad_afectada.upper(), id_entidad_afectada
    )
    return [BitacoraSistemaResponse.model_validate(e) for e in items]


@router.get(
    "/usuario/{usuario_id}",
    response_model=list[BitacoraSistemaResponse],
    summary="Eventos de un usuario (solo ADMIN)",
)
async def listar_por_usuario(
    usuario_id: PydanticObjectId,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _admin: Usuario = Depends(require_admin),
):
    service = AuditoriaService()
    items = await service.listar_por_usuario(
        usuario_id, skip=skip, limit=limit
    )
    return [BitacoraSistemaResponse.model_validate(e) for e in items]


# ======================================================================
# EXPORTAR A EXCEL / PDF
# ======================================================================
@router.get(
    "/exportar/excel",
    summary="Exportar bitácora a Excel (solo ADMIN)",
    description=(
        "Genera un archivo .xlsx con los eventos que cumplan los filtros. "
        "Respuesta directa como descarga."
    ),
)
async def exportar_excel(
    id_usuario: Optional[PydanticObjectId] = Query(None),
    tipo_evento: Optional[str] = Query(None, max_length=50),
    entidad_afectada: Optional[str] = Query(None, max_length=30),
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    _admin: Usuario = Depends(require_admin),
):
    service = AuditoriaService()
    contenido = await service.exportar_excel(
        id_usuario=id_usuario,
        tipo_evento=tipo_evento,
        entidad_afectada=entidad_afectada,
        desde=desde,
        hasta=hasta,
    )
    return StreamingResponse(
        BytesIO(contenido),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="bitacora_{_ts()}.xlsx"'
            )
        },
    )


@router.get(
    "/exportar/pdf",
    summary="Exportar bitácora a PDF (solo ADMIN)",
    description="Genera un PDF con los eventos que cumplan los filtros.",
)
async def exportar_pdf(
    id_usuario: Optional[PydanticObjectId] = Query(None),
    tipo_evento: Optional[str] = Query(None, max_length=50),
    entidad_afectada: Optional[str] = Query(None, max_length=30),
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    _admin: Usuario = Depends(require_admin),
):
    service = AuditoriaService()
    contenido = await service.exportar_pdf(
        id_usuario=id_usuario,
        tipo_evento=tipo_evento,
        entidad_afectada=entidad_afectada,
        desde=desde,
        hasta=hasta,
    )
    return StreamingResponse(
        BytesIO(contenido),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="bitacora_{_ts()}.pdf"'
            )
        },
    )


def _ts() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")