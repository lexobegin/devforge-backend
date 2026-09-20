# app/api/v1/ai_vision_router.py
"""
Endpoints del módulo de IA de VISIÓN (boceto/imagen → diagrama de clases).

- POST /api/v1/ai-vision/diagramas/{diagrama_id}/reconocer    → subir imagen y reconocer
- POST /api/v1/ai-vision/reconocer                            → reconocer sin persistir

La IA de visión corre del lado del BACKEND (requiere más cómputo que
reconocimiento de voz). El cliente sube una foto/imagen del boceto y
recibe un diagrama reconstruido listo para insertar.

El módulo `app/ai_vision/` (vision_service, sketch_recognition,
uml_reconstructor) hace el trabajo pesado. Aquí solo se recibe la imagen
y se delega.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user
from app.core.exceptions import BadRequestError
from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.ia_schema import VisionReconocimientoResponse

router = APIRouter()


# ======================================================================
# RECONOCIMIENTO CON PERSISTENCIA EN UN DIAGRAMA
# ======================================================================
@router.post(
    "/diagramas/{diagrama_id}/reconocer",
    response_model=VisionReconocimientoResponse,
    summary="Reconocer boceto y persistir el diagrama reconstruido",
    description=(
        "Sube una imagen (JPG/PNG) del boceto. El backend la procesa y "
        "devuelve las clases/atributos/relaciones detectados. Si el usuario "
        "confirma, el cliente los inserta al diagrama vía endpoints CRUD."
    ),
)
async def reconocer_y_persistir(
    diagrama_id: int,
    imagen: UploadFile = File(..., description="Imagen del boceto (jpg/png)"),
    idioma: str = Form("es", description="Idioma esperado del texto en el boceto"),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> VisionReconocimientoResponse:
    contenido = await _validar_imagen(imagen)

    # Verificar pertenencia al proyecto del diagrama
    from app.repositories.diagrama_repository import DiagramaRepository
    from app.repositories.proyecto_repository import MiembroProyectoRepository

    diagrama = await DiagramaRepository(db).get_by_id(diagrama_id)
    if diagrama is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Diagrama no encontrado")
    miembro = await MiembroProyectoRepository(db).get_by_proyecto_usuario(
        diagrama.id_proyecto, current_user.id
    )
    if miembro is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Recurso no encontrado")

    # Delegar al módulo ai_vision
    from app.ai_vision.vision_service import VisionService

    vision = VisionService()
    return await vision.reconocer_boceto(
        imagen_bytes=contenido,
        nombre_archivo=imagen.filename or "boceto",
        idioma=idioma,
    )


# ======================================================================
# RECONOCIMIENTO SIN PERSISTENCIA
# ======================================================================
@router.post(
    "/reconocer",
    response_model=VisionReconocimientoResponse,
    summary="Reconocer boceto sin asociarlo a ningún diagrama",
    description=(
        "Útil para previsualizar el resultado antes de decidir en qué "
        "diagrama insertarlo."
    ),
)
async def reconocer_sin_persistir(
    imagen: UploadFile = File(..., description="Imagen del boceto (jpg/png)"),
    idioma: str = Form("es"),
    _current_user: Usuario = Depends(get_current_active_user),
) -> VisionReconocimientoResponse:
    contenido = await _validar_imagen(imagen)

    from app.ai_vision.vision_service import VisionService

    vision = VisionService()
    return await vision.reconocer_boceto(
        imagen_bytes=contenido,
        nombre_archivo=imagen.filename or "boceto",
        idioma=idioma,
    )


# ======================================================================
# Helpers
# ======================================================================
async def _validar_imagen(imagen: UploadFile) -> bytes:
    """Valida extensión, tamaño y devuelve los bytes de la imagen."""
    if not imagen.filename:
        raise BadRequestError("Debe enviar una imagen")

    ext = Path(imagen.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise BadRequestError(
            "Formato no soportado. Use JPG, PNG o WEBP."
        )

    contenido = await imagen.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contenido) > max_bytes:
        raise BadRequestError(
            f"La imagen excede el tamaño máximo permitido "
            f"({settings.MAX_UPLOAD_SIZE_MB} MB)"
        )
    if not contenido:
        raise BadRequestError("La imagen está vacía")

    return contenido