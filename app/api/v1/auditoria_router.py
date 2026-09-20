# app/api/v1/auditoria_router.py
"""
Endpoints del módulo de Auditoría (CU3 — Consultar Bitácora del Sistema):

- GET /api/v1/auditoria                          → listar bitácora con filtros
- GET /api/v1/auditoria/entidad/{entidad}/{id}   → eventos de un recurso concreto
- GET /api/v1/auditoria/usuario/{usuario_id}     → eventos de un usuario
- GET /api/v1/auditoria/exportar/excel           → exportar a Excel
- GET /api/v1/auditoria/exportar/pdf             → exportar a PDF

Todos los endpoints requieren rol ADMIN.
"""

from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.database import get_db
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
    id_usuario: Optional[int] = Query(None, gt=0),
    tipo_evento: Optional[str] = Query(None, max_length=50),
    entidad_afectada: Optional[str] = Query(None, max_length=30),
    desde: Optional[datetime] = Query(None, description="ISO 8601"),
    hasta: Optional[datetime] = Query(None, description="ISO 8601"),
    _admin: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AuditoriaService(db)
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
        "Ej: /auditoria/entidad/DIAGRAMA/42 devuelve todos los eventos "
        "relacionados con el diagrama #42."
    ),
)
async def listar_por_entidad(
    entidad_afectada: str,
    id_entidad_afectada: int,
    _admin: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuditoriaService(db)
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
    usuario_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _admin: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuditoriaService(db)
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
    id_usuario: Optional[int] = Query(None, gt=0),
    tipo_evento: Optional[str] = Query(None, max_length=50),
    entidad_afectada: Optional[str] = Query(None, max_length=30),
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    _admin: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuditoriaService(db)
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
    id_usuario: Optional[int] = Query(None, gt=0),
    tipo_evento: Optional[str] = Query(None, max_length=50),
    entidad_afectada: Optional[str] = Query(None, max_length=30),
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    _admin: Usuario = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuditoriaService(db)
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