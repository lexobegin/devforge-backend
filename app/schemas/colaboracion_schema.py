# app/schemas/colaboracion_schema.py
"""
Esquemas Pydantic del módulo B. Colaboración (sesiones y participantes).

Cambios respecto al Ciclo 1:
- Los ids pasan de int (serial/FK de PostgreSQL) a PydanticObjectId
  (Beanie los serializa como string hex en JSON).
- ParticipanteSesion ya NO es una tabla con id propio: es un documento
  EMBEBIDO dentro de SesionColaboracion.participantes. Por eso
  ParticipanteSesionResponse pierde id e id_sesion (el alcance lo da la
  anidación dentro de la sesión que lo contiene).
- posicion_cursor conserva su formato libre (antes JSONB): el WebSocket
  del Ciclo 2 guarda x, y, zoom y el elemento enfocado sin migraciones.
- SesionConParticipantesResponse se llena directo con
  model_validate(sesion): los participantes viajan embebidos, sin joins.
"""

from datetime import datetime
from typing import Any, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# SesionColaboracion
# ======================================================================
class SesionColaboracionBase(BaseModel):
    id_proyecto: PydanticObjectId = Field(
        ..., description="Proyecto al que pertenece (se envía como string)"
    )
    id_diagrama: PydanticObjectId = Field(
        ..., description="Diagrama que se edita (se envía como string)"
    )


class SesionColaboracionCreate(SesionColaboracionBase):
    """Abrir una nueva sesión colaborativa sobre un diagrama."""


class SesionColaboracionResponse(SesionColaboracionBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    started_at: datetime
    ended_at: Optional[datetime] = None


# ======================================================================
# ParticipanteSesion (embebido en SesionColaboracion.participantes)
# ======================================================================
class ParticipanteSesionBase(BaseModel):
    id_usuario: PydanticObjectId = Field(
        ..., description="Usuario conectado (se envía como string)"
    )


class ParticipanteSesionCreate(ParticipanteSesionBase):
    """Unirse a una sesión colaborativa (se inserta en .participantes)."""


class ParticipanteSesionUpdate(BaseModel):
    """
    Actualización de la posición/foco del cursor en el lienzo.
    El contenido es libre (antes JSONB): x, y, zoom, elemento activo, etc.
    """

    posicion_cursor: Optional[dict[str, Any]] = None


class ParticipanteSesionResponse(ParticipanteSesionBase):
    model_config = ConfigDict(from_attributes=True)

    # Sin id ni id_sesion: el participante va EMBEBIDO en la sesión
    joined_at: datetime
    left_at: Optional[datetime] = None
    posicion_cursor: Optional[dict[str, Any]] = None


# ======================================================================
# Respuestas compuestas
# ======================================================================
class SesionConParticipantesResponse(SesionColaboracionResponse):
    """
    Sesión con la lista de participantes actualmente conectados.

    En el Ciclo 2 se construye directo con
    SesionConParticipantesResponse.model_validate(sesion): los
    participantes ya viven embebidos en el documento, sin joins.
    """

    participantes: list[ParticipanteSesionResponse] = Field(default_factory=list)