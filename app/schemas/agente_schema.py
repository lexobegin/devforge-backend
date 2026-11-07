# app/schemas/agente_schema.py
"""
Esquemas del Agente Dev del Ciclo 2 (CU18-CU21): edición del diagrama vía
guía, revisión, consulta y resumen — el LLM NO toca el lienzo, responde
con acciones estructuradas que el ejecutor del backend valida y aplica.

ARCHIVO NUEVO del Ciclo 2: estos esquemas vivían en ia_schema.py del
Ciclo 1 (módulo "IA Asistente" único); con el rediseño del módulo G el
archivo se divide y aquí queda lo del AGENTE:
- ContextoIAResponse  → el contexto que el gestor de contexto (CU17) armó
  y envió al modelo en un turno (auditoría/depuración: por qué la IA
  "no vio" un elemento, tamaño de la ventana por motor).
- AccionIAPropuesta / AccionIAResponse → la acción estructurada
  (tipo_accion + payload) con su ciclo de vida
  (PROPUESTA → APLICADA / RECHAZADA / FALLIDA).
- RespuestaIA → lo que el orquestador devuelve al canal antes de aplicar
  nada; el usuario decide (ninguna acción se aplica sola).
- ConfirmarAccionIARequest → confirmación explícita por ids de AccionIA
  (en el Ciclo 1 eran índices dentro de la interacción).

El "informe de validación" del modelo (ProblemaModelo y compañía) vive en
generacion_schema.py — es el mismo informe que usa el gate del
generador (CU6/CU24).
"""

from datetime import datetime
from typing import Any, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipo reutilizable (idéntico a app/models/accion_ia.py)
# ======================================================================
EstadoAccionIA = Literal["PROPUESTA", "APLICADA", "RECHAZADA", "FALLIDA"]


# ======================================================================
# ContextoIA (antes parte "contexto" de InteraccionIA) — CU17
# ======================================================================
class ContextoIAResponse(BaseModel):
    """
    Contexto que el service envió al modelo en un turno (auditoría/depuración:
    por qué la IA "no vio" un elemento, tamaño de la ventana por motor).
    Solo lectura: lo construye el ensamblador de contexto, nunca el cliente.
    """

    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_usuario: PydanticObjectId
    id_diagrama: Optional[PydanticObjectId] = None
    modelo: str
    contenido: dict[str, Any]
    num_mensajes: int
    num_tokens: Optional[int] = None
    created_at: datetime


# ======================================================================
# AccionIA (antes parte "acción" de InteraccionIA) — CU18
# ======================================================================
class AccionIAPropuesta(BaseModel):
    """
    Acción estructurada que la IA propone ejecutar sobre el diagrama.
    El LLM no toca el lienzo: el backend valida el payload con los *Update
    de diagrama_schema antes de aplicarlo.
    Ejemplo:
        {"tipo_accion": "CREAR_CLASE", "payload": {"nombre": "Paciente",
         "atributos": [{"nombre": "ci", "tipo_dato": "str"}]}}
    """

    tipo_accion: str = Field(
        ...,
        max_length=50,
        description=(
            "Mismo vocabulario que tipo_operacion de la cola offline: "
            "'CREAR_CLASE','MODIFICAR_ATRIBUTO','ELIMINAR_RELACION',…"
        ),
    )
    payload: dict[str, Any] = Field(default_factory=dict)
    descripcion: Optional[str] = Field(None, max_length=255)


class AccionIAResponse(BaseModel):
    """Acción persistida con su ciclo de vida (PROPUESTA→APLICADA/…)."""

    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_usuario: PydanticObjectId
    id_diagrama: Optional[PydanticObjectId] = None
    # Mensaje del chat que originó la acción; None si el disparo fue otra
    # vía (boceto, botón de generación…).
    id_mensaje: Optional[PydanticObjectId] = None
    tipo_accion: str
    payload: dict[str, Any]
    estado: EstadoAccionIA
    detalle_resultado: Optional[str] = None
    created_at: datetime
    aplicada_at: Optional[datetime] = None


# ======================================================================
# DTOs específicos de operación — orquestador (CU18-CU21)
# ======================================================================
class RespuestaIA(BaseModel):
    """
    Respuesta del servicio de IA antes de aplicar cambios al diagrama.
    El cliente decide si confirma las acciones propuestas
    (ConfirmarAccionIARequest); ninguna acción se aplica sola.
    """

    # Mensaje ASISTENTE creado en mensajes_chat (para encadenar la conversación).
    id_mensaje: Optional[PydanticObjectId] = None
    texto_respuesta: str = Field(..., description="Respuesta en lenguaje natural")
    acciones_propuestas: list[AccionIAPropuesta] = Field(default_factory=list)
    requiere_confirmacion: bool = Field(default=True)


class ConfirmarAccionIARequest(BaseModel):
    """
    Confirmación explícita de acciones propuestas por la IA.
    En el Ciclo 1 se confirmaban por ÍNDICE dentro de la interacción;
    ahora cada acción es un documento AccionIA y se confirman por id.
    """

    # Mensaje que originó las propuestas (para trazar la cadena completa).
    id_mensaje: PydanticObjectId
    acciones_a_aplicar: list[PydanticObjectId] = Field(
        default_factory=list,
        description="Ids de las AccionIA (estado PROPUESTA) a aplicar",
    )