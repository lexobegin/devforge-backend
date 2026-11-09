# app/api/v1/generacion_router.py
"""
Endpoints del módulo F. Generación Automática de Código — CICLO 2.

- POST   /api/v1/generacion/diagramas/{id}/generar       → disparar generación
- GET    /api/v1/generacion/trabajos/{trabajo_id}        → ver detalle
- GET    /api/v1/generacion/trabajos/{trabajo_id}/estado → estado liviano (polling)
- GET    /api/v1/generacion/diagramas/{id}/trabajos      → historial de trabajos
- GET    /api/v1/generacion/trabajos/{trabajo_id}/descargar → URL de descarga
- GET    /api/v1/generacion/trabajos/{trabajo_id}/archivo   → descargar ZIP

CICLO 2 (reconvertido del Ciclo 1, cambios documentados):
- SIN AsyncSessionLocal ni BackgroundTasks: los services ejecutan el
  pipeline COMPLETO en la llamada (gate → mapeo/render → ZIP → embebidos
  → EXITOSO) y devuelven el trabajo terminado; por eso el POST responde
  200 OK y no 202+polling. El endpoint /estado se conserva por compatibilidad.
- TANDA B21 (CU24): el POST /generar hace DISPATCH por `stack_destino`
  (el Ciclo 1 ya traía el campo en GenerarBackendRequest para eso):
    * SPRING_BOOT_JPA_POSTGRES (default) → GeneratorService.generar_backend
      (package_base va por constructor, incluir_postman y nombre_proyecto
      aplican).
    * REACT_TS_VITE → GeneradorFrontendService.generar_frontend (CU24,
      Tanda 17: proyecto React + Vite + TS con CRUD por clase). Los
      campos package_base e incluir_postman NO aplican al stack frontend
      y se ignoran (documentado aquí; el modelo Pydantic los acepta
      porque el request es compartido).
  El resto de rutas (detalle/estado/historial/descarga/archivo) son
  AGNÓSTICAS del stack: leen TrabajoGeneracionCodigo sin importar el
  valor de stack_destino, y obtener_ruta_zip valida EXITOSO +
  pertenencia + archivo (sirve el ZIP de ambos stacks).
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
from app.models.generacion import TrabajoGeneracionCodigo
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
    summary="Generar el código del diagrama (backend Spring Boot o frontend React)",
    description=(
        "Ciclo 2: el pipeline completo corre en la llamada y responde con "
        "el trabajo en estado EXITOSO (o lanza el error de dominio "
        "correspondiente). Tanda B21: el dispatch la decide `stack_destino` "
        "— SPRING_BOOT_JPA_POSTGRES genera el backend Java (package_base / "
        "incluir_postman aplican) y REACT_TS_VITE genera el frontend React "
        "CRUD (CU24; package_base / incluir_postman se ignoran). El fallo "
        "de render/escritura deja el trabajo FALLIDO y relanza la "
        "excepción original."
    ),
)
async def generar_backend(
    diagrama_id: PydanticObjectId,
    datos: GenerarBackendRequest,
    current_user: Usuario = Depends(get_current_active_user),
) -> TrabajoGeneracionCodigoResponse:
    """Tanda B21: dispatch por stack_destino. El nombre de la función se
    conserva (firma pública de la Tanda 19; el arnés la inspecciona)."""
    trabajo: TrabajoGeneracionCodigo
    if datos.stack_destino == "REACT_TS_VITE":
        # Import local para evitar dependencia circular en tiempo de import
        # (services → code_generator.templates_react → …)
        from app.services.generador_frontend_service import (
            GeneradorFrontendService,
        )

        trabajo = await GeneradorFrontendService().generar_frontend(
            current_user.id,
            diagrama_id,
            nombre_proyecto=datos.nombre_proyecto,
        )
    else:
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

    # EntidadesGeneradas vive EMBEBIDA en el documento (entidades); el
    # response la expone como `entidades` — se arma explícito.
    # FIX B21: la T19 leía `trabajo.entidades_generadas` (nombre de la
    # tabla del Ciclo 1) → AttributeError disfrazado de 500 en
    # GET /trabajos/{id} para CUALQUIER trabajo EXITOSO con resultado
    # embebido (el E2E de la T19 solo probó el 404 de ajeno, nunca un
    # detalle EXITOSO). El campo del modelo Ciclo 2 es `entidades`
    # (app/models/generacion.py: entidades: list[EntidadGenerada]).
    base = TrabajoGeneracionCodigoResponse.model_validate(trabajo)
    return TrabajoGeneracionDetalleResponse(
        **base.model_dump(),
        entidades=[
            EntidadGeneradaResponse.model_validate(e)
            for e in (trabajo.entidades or [])
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
    summary="Obtener URL de descarga del proyecto generado (backend o frontend)",
    description=(
        "Devuelve la URL pública desde la que se puede descargar el ZIP. "
        "Requiere que el trabajo esté en estado EXITOSO. Agnóstico del "
        "stack (B21)."
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

    return DescargaProyectoResponse(
        id_trabajo=trabajo_id,
        download_url=(
            f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}"
            f"{settings.API_V1_PREFIX}/generacion/trabajos/{trabajo_id}/archivo"
        ),
        tamanio_bytes=ruta.stat().st_size if ruta.is_file() else None,
        # FIX B21: la T19 leía trabajo.incluye_postman (columna del Ciclo 1
        # que el documento Ciclo 2 NO tiene) → AttributeError disfrazado de
        # 500 en /descargar para CUALQUIER trabajo EXITOSO. El dato honesto
        # se lee del propio ZIP: la colección vive en backend/postman/*.json
        # (T18); el frontend React nunca la trae.
        incluye_postman=_zip_trae_postman(ruta),
        # Tanda B22: nombre real del ZIP (el frontend lo usa como nombre de
        # descarga; antes inventaba devforge-backend-<id>.zip para ambos
        # stacks).
        nombre_archivo=ruta.name if ruta.is_file() else None,
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
def _zip_trae_postman(ruta_zip: Path) -> bool:
    """FIX B21: el documento Ciclo 2 no guarda incluye_postman (era
    columna del Ciclo 1). El dato real está en el ZIP: la colección
    Postman se escribe en backend/postman/*.postman_collection.json
    (generator_service T18) cuando el pedido la incluyó; el ZIP del
    frontend React nunca la trae. Ante cualquier lectura imposible se
    responde False (nunca rompe la descarga)."""
    import zipfile

    if not ruta_zip.is_file():
        return False
    try:
        with zipfile.ZipFile(ruta_zip) as paquete:
            return any(
                "postman" in nombre.lower()
                for nombre in paquete.namelist()
            )
    except (OSError, zipfile.BadZipFile):
        return False



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
