# app/schemas/trazabilidad_schema.py
"""
Esquemas Pydantic del módulo D. Trazabilidad y Colaboración en Tiempo Real:

- HistorialCambioDiagrama
- VersionDiagrama
- ComentarioDiagrama
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables
# ======================================================================
TipoCambio = Literal["CREAR", "MODIFICAR", "ELIMINAR"]


# ======================================================================
# HistorialCambioDiagrama
# ======================================================================
class HistorialCambioDiagramaBase(BaseModel):
    tipo_cambio: TipoCambio
    tipo_entidad: str = Field(..., max_length=30, description="'CLASE','ATRIBUTO','RELACION', etc.")
    id_entidad: int = Field(..., gt=0)
    datos_cambio: dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot del cambio (antes/después)",
    )


class HistorialCambioDiagramaCreate(HistorialCambioDiagramaBase):
    """
    El id_diagrama y el id_usuario se toman de la ruta y del token.
    Normalmente este registro lo genera el servicio internamente cuando
    se aplica un cambio al diagrama (no lo crea el cliente a mano).
    """


class HistorialCambioDiagramaResponse(HistorialCambioDiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int
    id_usuario: int
    created_at: datetime


# ======================================================================
# VersionDiagrama
# ======================================================================
class VersionDiagramaBase(BaseModel):
    contenido_json: dict[str, Any] = Field(
        ...,
        description="Copia completa del diagrama (clases, atributos, relaciones…)",
    )
    comentario: Optional[str] = Field(None, max_length=255)


class VersionDiagramaCreate(VersionDiagramaBase):
    """
    El id_diagrama y el id_usuario se toman de la ruta y del token.
    `numero_version` lo calcula el service (siguiente correlativo).
    """


class VersionDiagramaResponse(VersionDiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int
    numero_version: int
    id_usuario: int
    created_at: datetime


class VersionDiagramaResumenResponse(BaseModel):
    """Vista liviana: sin el contenido_json (que puede ser muy grande)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int
    numero_version: int
    id_usuario: int
    comentario: Optional[str] = None
    created_at: datetime


# ======================================================================
# ComentarioDiagrama
# ======================================================================
class ComentarioDiagramaBase(BaseModel):
    tipo_entidad: Optional[str] = Field(
        None, max_length=30, description="'CLASE','RELACION', o NULL si es general"
    )
    id_entidad: Optional[int] = Field(
        None, gt=0, description="id del elemento comentado; NULL si es general"
    )
    texto: str = Field(..., min_length=1, max_length=4000)


class ComentarioDiagramaCreate(ComentarioDiagramaBase):
    """El id_diagrama y el id_usuario se toman de la ruta y del token."""


class ComentarioDiagramaUpdate(BaseModel):
    texto: Optional[str] = Field(None, min_length=1, max_length=4000)
    resuelto: Optional[bool] = None


class ComentarioDiagramaResponse(ComentarioDiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int
    id_usuario: int
    resuelto: bool
    created_at: datetime