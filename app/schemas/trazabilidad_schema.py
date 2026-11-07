# app/schemas/trazabilidad_schema.py
"""
Esquemas Pydantic del módulo D. Trazabilidad y Colaboración en Tiempo Real:

- HistorialCambioDiagrama
- VersionDiagrama
- ComentarioDiagrama

Cambios respecto al Ciclo 1:
- Los ids int (serial/FK) pasan a string: PydanticObjectId de Beanie para
  id_diagrama/id_usuario (referencias entre documentos, se serializan como
  string hex en JSON) y str uuid para id_entidad, que ahora referencia los
  elementos EMBEBIDOS del Diagrama (ClaseUML.id, AtributoUML.id,
  RelacionUML.id…), no una tabla hija.
- VersionDiagramaCreate no lleva numero_version: lo calcula el service
  (siguiente correlativo respetando el índice único uq_version_diagrama_numero).
- VersionDiagramaResumenResponse se mantiene: la lista de versiones se
  consulta sin contenido_json (puede pesar megas), y el detalle completo se
  pide versión por versión.
- datos_cambio y contenido_json siguen siendo dict libres (antes JSONB).
- TipoCambio es idéntico al de app/models/trazabilidad.py (un solo
  vocabulario para el historial, la cola offline y el Agente Dev).
"""

from datetime import datetime
from typing import Any, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables (alineados con app/models/trazabilidad.py)
# ======================================================================
TipoCambio = Literal["CREAR", "MODIFICAR", "ELIMINAR"]


# ======================================================================
# HistorialCambioDiagrama
# ======================================================================
class HistorialCambioDiagramaBase(BaseModel):
    tipo_cambio: TipoCambio
    tipo_entidad: str = Field(..., max_length=30, description="'CLASE','ATRIBUTO','RELACION', etc.")
    # id uuid del elemento embebido afectado (ClaseUML.id, AtributoUML.id…);
    # antes FK int a la tabla hija.
    id_entidad: str = Field(..., min_length=1)
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

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    id_diagrama: PydanticObjectId
    id_usuario: PydanticObjectId
    created_at: datetime


# ======================================================================
# VersionDiagrama
# ======================================================================
class VersionDiagramaBase(BaseModel):
    contenido_json: dict[str, Any] = Field(
        ...,
        description=(
            "Copia completa del diagrama en ese momento. En el Ciclo 2 es el "
            "volcado del documento Diagrama (Diagrama.model_dump()), que ya "
            "incluye clases, interfaces y relaciones embebidas."
        ),
    )
    comentario: Optional[str] = Field(None, max_length=255)


class VersionDiagramaCreate(VersionDiagramaBase):
    """
    El id_diagrama y el id_usuario se toman de la ruta y del token.
    `numero_version` lo calcula el service (siguiente correlativo).
    """


class VersionDiagramaResponse(VersionDiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_diagrama: PydanticObjectId
    numero_version: int
    id_usuario: PydanticObjectId
    created_at: datetime


class VersionDiagramaResumenResponse(BaseModel):
    """Vista liviana: sin el contenido_json (que puede ser muy grande)."""

    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_diagrama: PydanticObjectId
    numero_version: int
    id_usuario: PydanticObjectId
    comentario: Optional[str] = None
    created_at: datetime


# ======================================================================
# ComentarioDiagrama
# ======================================================================
class ComentarioDiagramaBase(BaseModel):
    tipo_entidad: Optional[str] = Field(
        None, max_length=30, description="'CLASE','RELACION', o NULL si es general"
    )
    # id uuid del elemento comentado (ClaseUML.id, RelacionUML.id…);
    # None si el comentario es general al diagrama. Antes FK int.
    id_entidad: Optional[str] = Field(
        None, min_length=1, description="id del elemento comentado; NULL si es general"
    )
    texto: str = Field(..., min_length=1, max_length=4000)


class ComentarioDiagramaCreate(ComentarioDiagramaBase):
    """El id_diagrama y el id_usuario se toman de la ruta y del token."""


class ComentarioDiagramaUpdate(BaseModel):
    texto: Optional[str] = Field(None, min_length=1, max_length=4000)
    resuelto: Optional[bool] = None


class ComentarioDiagramaResponse(ComentarioDiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_diagrama: PydanticObjectId
    id_usuario: PydanticObjectId
    resuelto: bool
    created_at: datetime