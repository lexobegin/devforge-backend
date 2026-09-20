# app/schemas/ia_schema.py
"""
Esquemas Pydantic del módulo G. IA Asistente (Voz / Texto / Imagen):

- InteraccionIA (persistencia de cada interacción)
- DTOs específicos de operación para prompts de voz/texto y de visión.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables
# ======================================================================
CanalIA = Literal["VOZ", "TEXTO"]


# ======================================================================
# InteraccionIA
# ======================================================================
class InteraccionIABase(BaseModel):
    canal: CanalIA
    texto_prompt: str = Field(..., min_length=1, max_length=4000)
    respuesta_ia: Optional[dict[str, Any]] = None
    accion_aplicada: bool = Field(default=False)


class InteraccionIACreate(BaseModel):
    """
    El id_proyecto y el id_usuario se toman de la ruta y del token.
    El id_diagrama es opcional (puede ser un prompt a nivel proyecto).
    """

    id_diagrama: Optional[int] = Field(None, gt=0)
    canal: CanalIA
    texto_prompt: str = Field(..., min_length=1, max_length=4000)


class InteraccionIAResponse(InteraccionIABase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_proyecto: int
    id_diagrama: Optional[int] = None
    id_usuario: int
    created_at: datetime


# ======================================================================
# DTOs específicos de operación — IA por voz/texto
# ======================================================================
class PromptIARequest(BaseModel):
    """
    Payload para enviar un prompt de voz/texto al servicio de IA (modo online).
    Si el prompt vino por voz, la app ya lo transcribió y lo manda como texto.
    """

    texto_prompt: str = Field(..., min_length=1, max_length=4000)
    canal: CanalIA = Field(default="TEXTO")
    id_diagrama: Optional[int] = Field(
        None,
        gt=0,
        description="Si se especifica, la IA opera sobre ese diagrama",
    )
    contexto: Optional[dict[str, Any]] = Field(
        None,
        description="Contexto adicional (selección actual, clases existentes, etc.)",
    )


class AccionIAPropuesta(BaseModel):
    """
    Acción estructurada que la IA propone ejecutar sobre el diagrama.
    Ejemplo:
        {"tipo": "CREAR_CLASE", "payload": {"nombre": "Paciente", ...}}
    """

    tipo: str = Field(..., max_length=50, description="'CREAR_CLASE','AGREGAR_ATRIBUTO', etc.")
    payload: dict[str, Any] = Field(default_factory=dict)
    descripcion: Optional[str] = Field(None, max_length=255)


class RespuestaIA(BaseModel):
    """
    Respuesta del servicio de IA antes de aplicar cambios al diagrama.
    El cliente decide si confirma la acción (`accion_aplicada`).
    """

    texto_respuesta: str = Field(..., description="Respuesta en lenguaje natural")
    acciones_propuestas: list[AccionIAPropuesta] = Field(default_factory=list)
    requiere_confirmacion: bool = Field(default=True)


class ConfirmarAccionIARequest(BaseModel):
    """Confirmación explícita de una acción propuesta por la IA."""

    id_interaccion: int = Field(..., gt=0)
    acciones_a_aplicar: list[int] = Field(
        default_factory=list,
        description="Índices de las acciones de la interacción a aplicar",
    )


# ======================================================================
# DTOs específicos de operación — IA de visión (boceto/imagen)
# ======================================================================
class VisionReconocimientoResponse(BaseModel):
    """
    Resultado del reconocimiento de un boceto/imagen de diagrama.
    El cliente recibe un diagrama reconstruido listo para insertar.
    """

    exito: bool = True
    confianza: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confianza global del reconocimiento"
    )
    diagrama_reconstruido: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Estructura reconstruida: clases, atributos, operaciones y relaciones. "
            "Mismo formato que DiagramaCompletoResponse."
        ),
    )
    advertencias: list[str] = Field(default_factory=list)
    imagen_procesada_url: Optional[str] = None