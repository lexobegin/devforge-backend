# app/schemas/intercambio_schema.py
"""
Esquemas Pydantic del módulo E. Intercambio de Modelos (XMI/XML):

- ExportacionDiagrama
- ImportacionDiagrama

Además incluye los payloads específicos para disparar una exportación o
una importación desde el cliente (no son entidades, son DTOs de operación).
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables
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

    id: int
    id_diagrama: int
    ruta_archivo: str
    id_usuario: int
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

    id: int
    id_diagrama: int
    estado: EstadoImportacion
    id_usuario: int
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
    resumen: dict = Field(
        default_factory=dict,
        description="Conteo de clases, atributos, relaciones… importados",
    )