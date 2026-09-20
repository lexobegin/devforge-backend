# app/schemas/colaboracion_schema.py
"""
Esquemas Pydantic del módulo B. Colaboración (sesiones y participantes).
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# SesionColaboracion
# ======================================================================
class SesionColaboracionBase(BaseModel):
    id_proyecto: int = Field(..., gt=0)
    id_diagrama: int = Field(..., gt=0)


class SesionColaboracionCreate(SesionColaboracionBase):
    """Abrir una nueva sesión colaborativa sobre un diagrama."""


class SesionColaboracionResponse(SesionColaboracionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    ended_at: Optional[datetime] = None


# ======================================================================
# ParticipanteSesion
# ======================================================================
class ParticipanteSesionBase(BaseModel):
    id_usuario: int = Field(..., gt=0)


class ParticipanteSesionCreate(ParticipanteSesionBase):
    """Unirse a una sesión colaborativa."""


class ParticipanteSesionUpdate(BaseModel):
    """
    Actualización de la posición/foco del cursor en el lienzo.
    El contenido es libre (JSONB): x, y, zoom, elemento activo, etc.
    """

    posicion_cursor: Optional[dict[str, Any]] = None


class ParticipanteSesionResponse(ParticipanteSesionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_sesion: int
    joined_at: datetime
    left_at: Optional[datetime] = None
    posicion_cursor: Optional[dict[str, Any]] = None


# ======================================================================
# Respuestas compuestas
# ======================================================================
class SesionConParticipantesResponse(SesionColaboracionResponse):
    """Sesión con la lista de participantes actualmente conectados."""

    participantes: list[ParticipanteSesionResponse] = Field(default_factory=list)