# app/api/v1/generacion_router.py
"""
Endpoints del módulo F. Generación Automática de Backend (Spring Boot):

- POST   /api/v1/generacion/diagramas/{id}/generar       → disparar generación
- GET    /api/v1/generacion/trabajos/{trabajo_id}        → ver detalle
- GET    /api/v1/generacion/trabajos/{trabajo_id}/estado → estado liviano (polling)
- GET    /api/v1/generacion/diagramas/{id}/trabajos      → historial de trabajos
- GET    /api/v1/generacion/trabajos/{trabajo_id}/descargar → descargar ZIP
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user
from app.core.exceptions import BadRequestError, NotFoundError
from app.database import AsyncSessionLocal, get_db
from app.models.usuario import Usuario
from app.repositories.generacion_repository import TrabajoGeneracionRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.generacion_schema import (
    DescargaProyectoResponse,
    EstadoGeneracionResponse,
    GenerarBackendRequest,
    TrabajoGeneracionDetalleResponse,
    TrabajoGeneracionCodigoResponse,
)
from app.services.auditoria_service import AuditoriaService
from app.services.notificacion_service import NotificacionService

router = APIRouter()


# ======================================================================
# DISPARAR GENERACIÓN
# ======================================================================
@router.post(
    "/diagramas/{diagrama_id}/generar",
    response_model=TrabajoGeneracionCodigoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar generación automática de backend Spring Boot",
    description=(
        "Crea un trabajo en estado PENDIENTE y lo procesa en background. "
        "El cliente puede consultar el estado con GET /trabajos/{id}/estado."
    ),
)
async def generar_backend(
    diagrama_id: int,
    datos: GenerarBackendRequest,
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TrabajoGeneracionCodigoResponse:
    # Import local para evitar dependencia circular en tiempo de import
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService(db)
    trabajo = await service.crear_trabajo(
        diagrama_id, datos, usuario_id=current_user.id
    )

    # Procesar en background con su propia sesión de BD
    background_tasks.add_task(
        _procesar_generacion_bg,
        trabajo_id=trabajo.id,
        usuario_id=current_user.id,
    )

    return trabajo


async def _procesar_generacion_bg(trabajo_id: int, usuario_id: int) -> None:
    """
    Ejecuta el motor de generación en background con su propia AsyncSession.
    Al terminar:
      - Marca el trabajo como EXITOSO/FALLIDO.
      - Registra en bitácora.
      - Notifica al usuario.
    """
    from app.code_generator.generator_service import GeneratorService

    async with AsyncSessionLocal() as db:
        service = GeneratorService(db)
        try:
            await service.procesar_trabajo(trabajo_id, usuario_id=usuario_id)
        except Exception:
            # El propio service deja el trabajo en FALLIDO; no re-lanzamos
            # para no romper el BackgroundTasks.
            pass


# ======================================================================
# CONSULTAS
# ======================================================================
@router.get(
    "/trabajos/{trabajo_id}",
    response_model=TrabajoGeneracionDetalleResponse,
    summary="Ver detalle de un trabajo de generación",
    description="Incluye las entidades y reglas de mapeo generadas.",
)
async def obtener_trabajo(
    trabajo_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService(db)
    return await service.obtener_trabajo(trabajo_id, usuario_id=current_user.id)


@router.get(
    "/trabajos/{trabajo_id}/estado",
    response_model=EstadoGeneracionResponse,
    summary="Estado liviano de un trabajo (polling)",
    description=(
        "Endpoint pensado para polling cada pocos segundos desde el frontend."
    ),
)
async def obtener_estado(
    trabajo_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> EstadoGeneracionResponse:
    trabajos = TrabajoGeneracionRepository(db)
    trabajo = await trabajos.get_by_id(trabajo_id)
    if trabajo is None:
        raise NotFoundError("Trabajo de generación no encontrado")

    # Verificar pertenencia al proyecto del diagrama
    miembros = MiembroProyectoRepository(db)
    from app.repositories.diagrama_repository import DiagramaRepository

    diagrama = await DiagramaRepository(db).get_by_id(trabajo.id_diagrama)
    if diagrama is None:
        raise NotFoundError("Diagrama asociado no encontrado")
    miembro = await miembros.get_by_proyecto_usuario(
        diagrama.id_proyecto, current_user.id
    )
    if miembro is None:
        raise NotFoundError("Recurso no encontrado")

    return EstadoGeneracionResponse(
        id=trabajo.id,
        estado=trabajo.estado,
        progreso=None,   # el progreso se puede agregar más adelante
        mensaje=None,
        started_at=trabajo.started_at,
        finished_at=trabajo.finished_at,
    )


@router.get(
    "/diagramas/{diagrama_id}/trabajos",
    response_model=list[TrabajoGeneracionCodigoResponse],
    summary="Historial de trabajos de generación de un diagrama",
)
async def listar_trabajos(
    diagrama_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService(db)
    return await service.listar_trabajos(
        diagrama_id, usuario_id=current_user.id, skip=skip, limit=limit
    )


# ======================================================================
# DESCARGA DEL ZIP
# ======================================================================
@router.get(
    "/trabajos/{trabajo_id}/descargar",
    response_model=DescargaProyectoResponse,
    summary="Obtener URL de descarga del backend generado",
    description=(
        "Devuelve la URL pública desde la que se puede descargar el ZIP. "
        "Requiere que el trabajo esté en estado EXITOSO."
    ),
)
async def obtener_url_descarga(
    trabajo_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DescargaProyectoResponse:
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService(db)
    return await service.obtener_url_descarga(
        trabajo_id, usuario_id=current_user.id
    )


@router.get(
    "/trabajos/{trabajo_id}/archivo",
    summary="Descargar el ZIP del backend generado",
    description="Streaming directo del archivo ZIP.",
)
async def descargar_zip(
    trabajo_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService(db)
    ruta_abs = await service.obtener_ruta_zip(
        trabajo_id, usuario_id=current_user.id
    )
    return FileResponse(
        path=ruta_abs,
        filename=Path(ruta_abs).name,
        media_type="application/zip",
    )