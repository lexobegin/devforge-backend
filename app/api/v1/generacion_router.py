# app/api/v1/generacion_router.py
"""
Endpoints del módulo F. Generación Automática de Backend (Spring Boot)
— CICLO 2.

- POST   /api/v1/generacion/diagramas/{id}/generar       → disparar generación
- GET    /api/v1/generacion/trabajos/{trabajo_id}        → ver detalle
- GET    /api/v1/generacion/trabajos/{trabajo_id}/estado → estado liviano (polling)
- GET    /api/v1/generacion/diagramas/{id}/trabajos      → historial de trabajos
- GET    /api/v1/generacion/trabajos/{trabajo_id}/descargar → URL de descarga
- GET    /api/v1/generacion/trabajos/{trabajo_id}/archivo   → descargar ZIP

CICLO 2 (reconvertido del Ciclo 1, cambios documentados):
- SIN AsyncSessionLocal ni BackgroundTasks: GeneratorService.generar_backend()
  (Tanda 18) ejecuta el pipeline COMPLETO en la llamada (gate → mapeo →
  render → ZIP → embebidos → EXITOSO) y devuelve el trabajo terminado;
  por eso el POST responde 200 OK y no 202+polling. El endpoint /estado
  se conserva por compatibilidad.
- package_base/nombre_proyecto/incluir_postman de GenerarBackendRequest
  se mapean directo al service (package_base va por constructor).
- Las consultas (detalle/estado/historial) usan el TrabajoGeneracionRepository
  sin estado + verificación de pertenencia (mismo criterio del módulo C:
  ajeno → 404 genérico "Recurso no encontrado").
"""

from pathlib import Path

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.core.dependencies import get_current_active_user
from app.core.exceptions import NotFoundError
from app.models.usuario import Usuario
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.generacion_repository import TrabajoGeneracionRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.generacion_schema import (
    DescargaProyectoResponse,
    EstadoGeneracionResponse,
    GenerarBackendRequest,
    TrabajoGeneracionDetalleResponse,
    TrabajoGeneracionCodigoResponse,
    EntidadGeneradaResponse,
)
from app.services.auditoria_service import AuditoriaService

router = APIRouter()


# ======================================================================
# DISPARAR GENERACIÓN
# ======================================================================
@router.post(
    "/diagramas/{diagrama_id}/generar",
    response_model=TrabajoGeneracionCodigoResponse,
    summary="Generar el backend Spring Boot del diagrama",
    description=(
        "Ciclo 2: el pipeline completo corre en la llamada (gate formal → "
        "mapeo UML→Java/SQL → render de plantillas → ZIP → resultado "
        "embebido) y responde con el trabajo en estado EXITOSO (o lanza el "
        "error de dominio correspondiente). El fallo de render/escritura "
        "deja el trabajo FALLIDO y relanza la excepción original."
    ),
)
async def generar_backend(
    diagrama_id: PydanticObjectId,
    datos: GenerarBackendRequest,
    current_user: Usuario = Depends(get_current_active_user),
) -> TrabajoGeneracionCodigoResponse:
    # Import local para evitar dependencia circular en tiempo de import
    # (code_generator → utils.validators → …)
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService(
        package_base=datos.package_base,
    )
    trabajo = await service.generar_backend(
        current_user.id,
        diagrama_id,
        incluir_postman=datos.incluir_postman,
        nombre_proyecto=datos.nombre_proyecto,
    )

    # Bitácora de trabajo creado (la de EXITOSO/FALLIDO ya la escribe el
    # service con las firmas del Ciclo 2)
    auditoria = AuditoriaService()
    try:
        await auditoria.registrar(
            tipo_evento="GENERACION_SOLICITADA",
            descripcion=(
                f"Generación de backend '{datos.nombre_proyecto or diagrama_id}' "
                f"solicitada (trabajo #{trabajo.id})"
            ),
            id_usuario=current_user.id,
            entidad_afectada="TRABAJO_GENERACION",
            id_entidad_afectada=str(trabajo.id),
        )
    except Exception:
        pass  # la bitácora no bloquea la respuesta (guarda del Ciclo 2)

    return TrabajoGeneracionCodigoResponse.model_validate(trabajo)


# ======================================================================
# CONSULTAS
# ======================================================================
@router.get(
    "/trabajos/{trabajo_id}",
    response_model=TrabajoGeneracionDetalleResponse,
    summary="Ver detalle de un trabajo de generación",
    description="Incluye las entidades y reglas de mapeo generadas (embebidas).",
)
async def obtener_trabajo(
    trabajo_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
):
    trabajos = TrabajoGeneracionRepository()
    trabajo = await trabajos.get_detalle(trabajo_id)
    if trabajo is None:
        raise NotFoundError("Trabajo de generación no encontrado")

    await _require_miembro_de_trabajo(trabajo, current_user)

    # EntidadesGeneradas vive EMBEBIDA en el documento (entidades_generadas);
    # el response la expone como `entidades` — se arma explícito.
    base = TrabajoGeneracionCodigoResponse.model_validate(trabajo)
    return TrabajoGeneracionDetalleResponse(
        **base.model_dump(),
        entidades=[
            EntidadGeneradaResponse.model_validate(e)
            for e in (trabajo.entidades_generadas or [])
        ],
    )


@router.get(
    "/trabajos/{trabajo_id}/estado",
    response_model=EstadoGeneracionResponse,
    summary="Estado liviano de un trabajo (polling)",
    description=(
        "Endpoint pensado para polling cada pocos segundos desde el frontend."
    ),
)
async def obtener_estado(
    trabajo_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> EstadoGeneracionResponse:
    trabajos = TrabajoGeneracionRepository()
    trabajo = await trabajos.get_by_id(trabajo_id)
    if trabajo is None:
        raise NotFoundError("Trabajo de generación no encontrado")

    await _require_miembro_de_trabajo(trabajo, current_user)

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
    diagrama_id: PydanticObjectId,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Usuario = Depends(get_current_active_user),
):
    await _require_miembro_de_diagrama(diagrama_id, current_user)

    trabajos = TrabajoGeneracionRepository()
    items = await trabajos.list_by_diagrama(
        diagrama_id, skip=skip, limit=limit
    )
    return [
        TrabajoGeneracionCodigoResponse.model_validate(t) for t in items
    ]


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
    trabajo_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> DescargaProyectoResponse:
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService()
    # obtener_ruta_zip valida trabajo EXITOSO + pertenencia + archivo
    ruta = await service.obtener_ruta_zip(trabajo_id, usuario_id=current_user.id)

    trabajo = await TrabajoGeneracionRepository().get_by_id(trabajo_id)
    return DescargaProyectoResponse(
        id_trabajo=trabajo_id,
        download_url=(
            f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}"
            f"{settings.API_V1_PREFIX}/generacion/trabajos/{trabajo_id}/archivo"
        ),
        tamanio_bytes=ruta.stat().st_size if ruta.is_file() else None,
        incluye_postman=bool(trabajo and trabajo.incluye_postman),
    )


@router.get(
    "/trabajos/{trabajo_id}/archivo",
    summary="Descargar el ZIP del backend generado",
    description="Streaming directo del archivo ZIP.",
)
async def descargar_zip(
    trabajo_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
):
    from app.code_generator.generator_service import GeneratorService

    service = GeneratorService()
    ruta_abs = await service.obtener_ruta_zip(
        trabajo_id, usuario_id=current_user.id
    )
    return FileResponse(
        path=ruta_abs,
        filename=Path(ruta_abs).name,
        media_type="application/zip",
    )


# ======================================================================
# Helpers de pertenencia (mismo criterio del módulo C / Tanda 18)
# ======================================================================
async def _require_miembro_de_trabajo(trabajo, current_user: Usuario) -> None:
    """Ajeno → 404 genérico (no revela trabajos de otros proyectos)."""
    diagrama = await DiagramaRepository().get_by_id(trabajo.id_diagrama)
    if diagrama is None:
        raise NotFoundError("Diagrama asociado no encontrado")
    miembro = await MiembroProyectoRepository().get_by_proyecto_usuario(
        diagrama.id_proyecto, current_user.id
    )
    if miembro is None:
        raise NotFoundError("Recurso no encontrado")


async def _require_miembro_de_diagrama(diagrama_id, current_user: Usuario) -> None:
    diagrama = await DiagramaRepository().get_by_id(diagrama_id)
    if diagrama is None:
        raise NotFoundError("Diagrama no encontrado")
    miembro = await MiembroProyectoRepository().get_by_proyecto_usuario(
        diagrama.id_proyecto, current_user.id
    )
    if miembro is None:
        raise NotFoundError("Recurso no encontrado")