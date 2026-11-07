# app/schemas/intercambio_schema.py
"""
Esquemas Pydantic del módulo E. Intercambio de Modelos (XMI/XML):

- ExportacionDiagrama
- ImportacionDiagrama

Además incluye los payloads específicos para disparar una exportación o
una importación desde el cliente (no son entidades, son DTOs de operación).

Cambios respecto al Ciclo 1:
- Los ids int (serial/FK) pasan a PydanticObjectId de Beanie (se serializan
  como string hex en JSON).
- FormatoIntercambio conserva "EA" además de "XMI"/"XML": en el Ciclo 2 el
  conversor lxml apunta al round-trip DevForge ↔ Enterprise Architect, y
  estos registros documentan cada operación (estado EXITOSO/FALLIDO) para
  depurar la compatibilidad — trazabilidad que el Ciclo 1 no daba.
- ImportacionResultado.resumen pasa a dict[str, Any]: el conversor informa
  clases/atributos/relaciones/advertencias reconstruidas.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables (alineados con app/models/intercambio.py)
# ======================================================================
FormatoIntercambio = Literal["XMI", "XML", "EA"]
EstadoImportacion = Literal["PENDIENTE", "EXITOSO", "FALLIDO"]


# ======================================================================
# ExportacionDiagrama
# ======================================================================
class ExportacionDiagramaBase(BaseModel):
    formato: FormatoIntercambio = Field(default="XMI")


class ExportacionDiagramaCreate(ExportacionDiagramaBase):
    """
    El id_diagrama y el id_usuario se toman de la ruta y del token.
    `ruta_archivo` la calcula el service al materializar el archivo.
    """


class ExportacionDiagramaResponse(ExportacionDiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    id_diagrama: PydanticObjectId
    ruta_archivo: str
    id_usuario: PydanticObjectId
    exported_at: datetime


# ======================================================================
# ImportacionDiagrama
# ======================================================================
class ImportacionDiagramaBase(BaseModel):
    formato: FormatoIntercambio = Field(default="XMI")
    archivo_origen: str = Field(..., max_length=255)


class ImportacionDiagramaCreate(ImportacionDiagramaBase):
    """
    El id_diagrama y el id_usuario se toman de la ruta y del token.
    `estado` arranca en PENDIENTE por defecto.
    """


class ImportacionDiagramaUpdate(BaseModel):
    estado: Optional[EstadoImportacion] = None


class ImportacionDiagramaResponse(ImportacionDiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_diagrama: PydanticObjectId
    estado: EstadoImportacion
    id_usuario: PydanticObjectId
    imported_at: datetime


# ======================================================================
# DTOs específicos de operación
# ======================================================================
class ExportacionResultado(BaseModel):
    """
    Respuesta del endpoint de exportación: además del registro creado,
    incluye la URL desde la cual el cliente puede descargar el archivo.
    """

    exportacion: ExportacionDiagramaResponse
    download_url: str = Field(..., description="URL firmada o relativa para descargar el XMI")


class ImportacionResultado(BaseModel):
    """
    Respuesta del endpoint de importación: además del registro, incluye
    un resumen de lo que se reconstruyó en el diagrama.
    """

    importacion: ImportacionDiagramaResponse
    resumen: dict[str, Any] = Field(
        default_factory=dict,
        description="Conteo de clases, atributos, relaciones… importados",
    )