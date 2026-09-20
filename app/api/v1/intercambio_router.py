# app/api/v1/intercambio_router.py
"""
Endpoints del módulo E. Intercambio de Modelos (XMI/XML):

- POST   /api/v1/intercambio/diagramas/{id}/exportar         → exportar a XMI/XML
- GET    /api/v1/intercambio/diagramas/{id}/exportaciones    → historial de exportaciones
- POST   /api/v1/intercambio/diagramas/{id}/importar         → importar XMI/XML (multipart)
- GET    /api/v1/intercambio/diagramas/{id}/importaciones    → historial de importaciones
- GET    /api/v1/intercambio/descargas/{ruta}                → descargar archivo exportado

El endpoint de importación recibe `UploadFile` (multipart/form-data) y lee
el contenido como texto. El endpoint de exportación devuelve el registro
+ URL de descarga.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user
from app.core.exceptions import BadRequestError, NotFoundError
from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.intercambio_schema import (
    ExportacionDiagramaResponse,
    ExportacionResultado,
    ImportacionDiagramaCreate,
    ImportacionDiagramaResponse,
    ImportacionResultado,
)
from app.services.auditoria_service import AuditoriaService
from app.services.intercambio_service import IntercambioService

router = APIRouter()


# ======================================================================
# EXPORTAR
# ======================================================================
@router.post(
    "/diagramas/{diagrama_id}/exportar",
    response_model=ExportacionResultado,
    summary="Exportar diagrama a XMI/XML",
    description=(
        "Genera el archivo a partir del diagrama completo, lo persiste en "
        "el servidor y devuelve el registro + URL de descarga."
    ),
)
async def exportar_diagrama(
    diagrama_id: int,
    formato: str = Query("XMI", pattern="^(XMI|XML|EA|xmi|xml|ea)$"),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExportacionResultado:
    service = IntercambioService(db)
    resultado = await service.exportar_diagrama(
        diagrama_id, usuario_id=current_user.id, formato=formato
    )

    # Bitácora
    auditoria = AuditoriaService(db)
    await auditoria.log_exportacion(
        resultado.exportacion.id, diagrama_id, current_user.id, commit=True
    )

    return resultado


@router.get(
    "/diagramas/{diagrama_id}/exportaciones",
    response_model=list[ExportacionDiagramaResponse],
    summary="Listar exportaciones de un diagrama",
)
async def listar_exportaciones(
    diagrama_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = IntercambioService(db)
    return await service.listar_exportaciones(
        diagrama_id, usuario_id=current_user.id, skip=skip, limit=limit
    )


# ======================================================================
# IMPORTAR
# ======================================================================
@router.post(
    "/diagramas/{diagrama_id}/importar",
    response_model=ImportacionResultado,
    status_code=status.HTTP_201_CREATED,
    summary="Importar XMI/XML a un diagrama",
    description=(
        "Recibe un archivo XMI/XML (multipart/form-data), lo parsea y hace "
        "merge sobre el diagrama destino. Las clases existentes por nombre "
        "se saltan; las nuevas se agregan."
    ),
)
async def importar_diagrama(
    diagrama_id: int,
    archivo: UploadFile = File(..., description="Archivo XMI/XML"),
    formato: str = Form("XMI", description="'XMI' o 'XML'"),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ImportacionResultado:
    # Validaciones básicas del archivo
    if not archivo.filename:
        raise BadRequestError("Debe enviar un archivo")

    extension = Path(archivo.filename).suffix.lower()
    if extension not in (".xmi", ".xml"):
        raise BadRequestError(
            "Extensión de archivo no soportada. Use .xmi o .xml"
        )

    contenido_bytes = await archivo.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contenido_bytes) > max_bytes:
        raise BadRequestError(
            f"El archivo excede el tamaño máximo permitido "
            f"({settings.MAX_UPLOAD_SIZE_MB} MB)"
        )

    #try:
    #    contenido_texto = _decodificar_xml(contenido_bytes)
    #except UnicodeDecodeError:
    #    raise BadRequestError(
    #        "El archivo debe estar codificado en UTF-8"
    #    )

    contenido_texto = _decodificar_xml(contenido_bytes)

    datos = ImportacionDiagramaCreate(
        formato=formato.upper(),
        archivo_origen=archivo.filename,
    )

    service = IntercambioService(db)
    resultado = await service.importar_diagrama(
        diagrama_id,
        datos,
        contenido_texto,
        usuario_id=current_user.id,
    )

    # Bitácora
    auditoria = AuditoriaService(db)
    await auditoria.log_importacion(
        resultado.importacion.id, diagrama_id, current_user.id, commit=True
    )

    return resultado


@router.get(
    "/diagramas/{diagrama_id}/importaciones",
    response_model=list[ImportacionDiagramaResponse],
    summary="Listar importaciones de un diagrama",
)
async def listar_importaciones(
    diagrama_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = IntercambioService(db)
    return await service.listar_importaciones(
        diagrama_id, usuario_id=current_user.id, skip=skip, limit=limit
    )


# ======================================================================
# DESCARGA DE ARCHIVO EXPORTADO
# ======================================================================
@router.get(
    "/descargas/{ruta:path}",
    summary="Descargar archivo exportado (XMI/XML)",
    description=(
        "Devuelve el archivo exportado por su ruta relativa. La ruta es la "
        "que devuelve el endpoint de exportación."
    ),
)
async def descargar_exportado(
    ruta: str,
    _current_user: Usuario = Depends(get_current_active_user),
):
    # Sanear: impedir path traversal
    base = Path(settings.EXPORT_DIR).resolve()
    ruta_abs = (base / ruta).resolve()

    # Verificar que la ruta resuelta siga dentro de la base
    try:
        ruta_abs.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ruta inválida",
        )

    if not ruta_abs.is_file():
        raise NotFoundError("Archivo no encontrado")

    return FileResponse(
        path=ruta_abs,
        filename=ruta_abs.name,
        media_type="application/xml",
    )

def _decodificar_xml(contenido: bytes) -> str:
    """
    Decodifica bytes de un XML probando varias codificaciones comunes.
    Enterprise Architect exporta en windows-1252; DevForge AI en UTF-8.
    """
    # Probar en orden de probabilidad
    for encoding in ("utf-8", "utf-8-sig", "windows-1252", "iso-8859-1", "latin-1"):
        try:
            return contenido.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Fallback con reemplazo de caracteres inválidos
    return contenido.decode("utf-8", errors="replace")