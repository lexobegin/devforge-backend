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

    # ------------------------------------------------------------------
    # Tanda B23: datos VISUALES del usuario resueltos por el service al
    # listar miembros (join en memoria contra la colección usuarios).
    # Opcionales y nulables: el embebido NO los almacena; si el service
    # no pudo resolverlos (usuario borrado), quedan None y el cliente
    # muestra el id (comportamiento anterior).
    # ------------------------------------------------------------------
    nombre_usuario: Optional[str] = None
    email_usuario: Optional[str] = None


# ======================================================================
# Tanda B23 — Candidatos a miembro (GET /proyectos/{id}/candidatos)
# ======================================================================
# Repara el 403 del modal de miembros: GET /usuarios es solo-ADMIN, así
# que un PROPIETARIO con rol global DESARROLLADOR no podía listar
# usuarios para elegir a quién invitar. Este endpoint es POR PROYECTO:
# exige ser PROPIETARIO del proyecto (o ADMIN de la plataforma) y
# devuelve SOLO usuarios activos que AÚN no son miembros — lo mínimo
# que el selector con buscador necesita, sin exponer el padrón completo.
RolGlobal = Literal["ADMIN", "LIDER", "DESARROLLADOR"]


class UsuarioCandidatoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    nombre_completo: str
    email: str
    rol: RolGlobal


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
