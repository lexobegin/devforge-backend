# app/schemas/proyecto_schema.py
"""
Esquemas Pydantic del módulo B. Proyectos y Miembros.

Cambios respecto al Ciclo 1:
- Los ids pasan de int (serial/FK de PostgreSQL) a PydanticObjectId
  (Beanie los serializa como string hex en JSON).
- MiembroProyecto ya NO es una tabla con id propio: es un documento
  EMBEBIDO dentro de Proyecto.miembros. Por eso:
  - MiembroProyectoResponse pierde id e id_proyecto (el alcance lo da la
    anidación dentro del proyecto que lo contiene).
  - La unicidad (proyecto, usuario) del Ciclo 1
    (uq_miembro_proyecto_usuario) la garantiza la capa de servicios con
    Proyecto.miembro(id_usuario) antes de insertar.
- ProyectoConMiembrosResponse se llena directo con
  model_validate(proyecto): los miembros viajan embebidos, sin joins.
"""

from datetime import datetime
from typing import Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# Tipos reutilizables (alineados con app/models/proyecto.py)
EstadoProyecto = Literal["ACTIVO", "ARCHIVADO"]
RolEnProyecto = Literal["PROPIETARIO", "EDITOR", "LECTOR"]


# ======================================================================
# Proyecto
# ======================================================================
class ProyectoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    descripcion: Optional[str] = Field(None, max_length=2000)


class ProyectoCreate(ProyectoBase):
    """El propietario se toma del usuario autenticado, no del payload."""


class ProyectoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    descripcion: Optional[str] = Field(None, max_length=2000)
    estado: Optional[EstadoProyecto] = None


class ProyectoResponse(ProyectoBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    id_propietario: PydanticObjectId
    estado: EstadoProyecto
    created_at: datetime
    updated_at: datetime


# ======================================================================
# MiembroProyecto (embebido en Proyecto.miembros)
# ======================================================================
class MiembroProyectoBase(BaseModel):
    id_usuario: PydanticObjectId = Field(
        ..., description="Usuario miembro (se envía y recibe como string)"
    )
    rol_en_proyecto: RolEnProyecto = Field(default="EDITOR")


class MiembroProyectoCreate(MiembroProyectoBase):
    """Agregar un miembro a un proyecto (se inserta en Proyecto.miembros)."""


class MiembroProyectoUpdate(BaseModel):
    """Cambiar el rol de un miembro ya existente."""

    rol_en_proyecto: RolEnProyecto


class MiembroProyectoResponse(MiembroProyectoBase):
    model_config = ConfigDict(from_attributes=True)

    # Sin id ni id_proyecto: el miembro va EMBEBIDO en el proyecto
    joined_at: datetime


# ======================================================================
# Compuestos (para respuestas anidadas cómodas)
# ======================================================================
class ProyectoConMiembrosResponse(ProyectoResponse):
    """
    Proyecto con la lista de miembros incluida (uso en detalle).

    En el Ciclo 2 se construye directo con
    ProyectoConMiembrosResponse.model_validate(proyecto): los miembros
    ya viven embebidos en el documento, sin joins.
    """

    miembros: list[MiembroProyectoResponse] = Field(default_factory=list)