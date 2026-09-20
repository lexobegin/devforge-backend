# app/ai_vision/vision_service.py
"""
Servicio orquestador del reconocimiento de bocetos/imágenes de diagramas.

Flujo:
1. Recibe los bytes de la imagen.
2. Llama a SketchRecognizer para detectar cajas, texto y líneas.
3. Llama a UMLReconstructor para reconstruir clases, atributos,
   operaciones y relaciones.
4. Devuelve un `VisionReconocimientoResponse` con la estructura resultante
   lista para que el cliente la inserte en el diagrama.

Opcionalmente, si hay conexión y proveedor externo de visión configurado,
se puede delegar a un modelo en la nube para mayor precisión. Ese camino
queda como punto de extensión (no implementado en esta versión).
"""

import logging
from io import BytesIO
from typing import Any

from app.config import settings
from app.core.exceptions import AIServiceError, BadRequestError
from app.schemas.ia_schema import VisionReconocimientoResponse

logger = logging.getLogger("devforge.ai_vision")


class VisionService:
    """Servicio de IA de visión para bocetos de diagramas."""

    def __init__(self) -> None:
        # Import diferido: si OpenCV/NumPy no están instalados, el módulo
        # arranca igual y solo falla cuando se invoca el reconocimiento.
        from app.ai_vision.sketch_recognition import SketchRecognizer
        from app.ai_vision.uml_reconstructor import UMLReconstructor

        self.recognizer = SketchRecognizer()
        self.reconstructor = UMLReconstructor()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    async def reconocer_boceto(
        self,
        *,
        imagen_bytes: bytes,
        nombre_archivo: str = "boceto",
        idioma: str = "es",
    ) -> VisionReconocimientoResponse:
        """
        Ejecuta el pipeline completo: detección + reconstrucción.

        Devuelve un `VisionReconocimientoResponse` con:
        - diagrama_reconstruido: dict con clases y relaciones
        - advertencias: mensajes no bloqueantes (ej. OCR vacío)
        - confianza: valor aproximado basado en cantidad de cajas con texto
        """
        if not imagen_bytes:
            raise BadRequestError("La imagen está vacía")

        try:
            deteccion = self.recognizer.detectar(
                imagen_bytes, idioma=idioma
            )
        except RuntimeError as exc:
            # Dependencias de visión no instaladas
            raise AIServiceError(str(exc)) from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
        except Exception as exc:
            logger.exception("Error en detección de boceto")
            raise AIServiceError(
                f"Error inesperado al procesar la imagen: {exc}"
            ) from exc

        try:
            diagrama = self.reconstructor.reconstruir(deteccion)
        except Exception as exc:
            logger.exception("Error en reconstrucción UML")
            raise AIServiceError(
                f"Error inesperado al reconstruir el diagrama: {exc}"
            ) from exc

        confianza = self._calcular_confianza(deteccion, diagrama)

        return VisionReconocimientoResponse(
            exito=len(diagrama.get("clases", [])) > 0,
            confianza=confianza,
            diagrama_reconstruido={
                "clases": diagrama.get("clases", []),
                "relaciones": diagrama.get("relaciones", []),
            },
            advertencias=diagrama.get("advertencias", []),
            imagen_procesada_url=None,   # no persistimos la imagen en esta versión
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _calcular_confianza(
        self, deteccion: Any, diagrama: dict[str, Any]
    ) -> float:
        """
        Calcula una confianza aproximada en [0, 1] según:
        - Porcentaje de cajas con texto reconocido
        - Cantidad total de clases detectadas
        - Cantidad de miembros (atributos + operaciones)
        """
        cajas = getattr(deteccion, "cajas", []) or []
        if not cajas:
            return 0.0

        con_texto = sum(1 for c in cajas if c.lineas_texto)
        ratio_texto = con_texto / len(cajas)

        clases = diagrama.get("clases", []) or []
        total_miembros = sum(
            len(c.get("atributos", [])) + len(c.get("operaciones", []))
            for c in clases
        )

        # Normalizaciones simples (0-1)
        factor_clases = min(len(clases) / 5.0, 1.0)         # 5+ clases → 1.0
        factor_miembros = min(total_miembros / 15.0, 1.0)   # 15+ miembros → 1.0

        # Promedio ponderado
        confianza = (
            ratio_texto * 0.5
            + factor_clases * 0.3
            + factor_miembros * 0.2
        )
        return round(min(max(confianza, 0.0), 1.0), 3)


# ======================================================================
# Instancia por defecto (no se usa como singleton; los routers crean una)
# ======================================================================
def get_vision_service() -> VisionService:
    return VisionService()