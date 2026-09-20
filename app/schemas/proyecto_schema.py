# app/schemas/proyecto_schema.py
"""
Esquemas Pydantic del módulo B. Proyectos y Miembros.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Tipos reutilizables
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

    id: int
    id_propietario: int
    estado: EstadoProyecto
    created_at: datetime
    updated_at: datetime


# ======================================================================
# MiembroProyecto
# ======================================================================
class MiembroProyectoBase(BaseModel):
    id_usuario: int = Field(..., gt=0)
    rol_en_proyecto: RolEnProyecto = Field(default="EDITOR")


class MiembroProyectoCreate(MiembroProyectoBase):
    """Agregar un miembro a un proyecto."""


class MiembroProyectoUpdate(BaseModel):
    """Cambiar el rol de un miembro ya existente."""

    rol_en_proyecto: RolEnProyecto


class MiembroProyectoResponse(MiembroProyectoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_proyecto: int
    joined_at: datetime


# ======================================================================
# Compuestos (para respuestas anidadas cómodas)
# ======================================================================
class ProyectoConMiembrosResponse(ProyectoResponse):
    """Proyecto con la lista de miembros incluida (uso en detalle)."""

    miembros: list[MiembroProyectoResponse] = Field(default_factory=list)