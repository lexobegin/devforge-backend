# app/schemas/generacion_schema.py
"""
Esquemas Pydantic del módulo F. Generación Automática de Backend:

- TrabajoGeneracionCodigo
- EntidadGenerada
- ReglaMapeo

Además incluye los DTOs de operación:
- GenerarBackendRequest     → payload para disparar una generación
- EstadoGeneracionResponse  → estado resumido para polling desde el front
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables
# ======================================================================
EstadoTrabajoGeneracion = Literal["PENDIENTE", "EN_PROCESO", "EXITOSO", "FALLIDO"]

StackDestino = Literal["SPRING_BOOT_JPA_POSTGRES"]


# ======================================================================
# ReglaMapeo
# ======================================================================
class ReglaMapeoBase(BaseModel):
    id_atributo_uml: int = Field(..., gt=0)
    nombre_columna: str = Field(..., min_length=1, max_length=100)
    tipo_sql: str = Field(..., min_length=1, max_length=50)
    es_clave_primaria: bool = Field(default=False)
    es_nulleable: bool = Field(default=True)


class ReglaMapeoResponse(ReglaMapeoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_entidad_generada: int


# ======================================================================
# EntidadGenerada
# ======================================================================
class EntidadGeneradaBase(BaseModel):
    id_clase_uml: int = Field(..., gt=0)
    nombre_clase_java: str = Field(..., min_length=1, max_length=150)
    nombre_tabla: str = Field(..., min_length=1, max_length=150)


class EntidadGeneradaResponse(EntidadGeneradaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_trabajo: int
    reglas_mapeo: list[ReglaMapeoResponse] = Field(default_factory=list)


# ======================================================================
# TrabajoGeneracionCodigo
# ======================================================================
class TrabajoGeneracionCodigoBase(BaseModel):
    stack_destino: StackDestino = Field(default="SPRING_BOOT_JPA_POSTGRES")


class TrabajoGeneracionCodigoCreate(TrabajoGeneracionCodigoBase):
    """
    El id_diagrama y el id_usuario se toman de la ruta y del token.
    `estado` arranca en PENDIENTE.
    """


class TrabajoGeneracionCodigoResponse(TrabajoGeneracionCodigoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int
    id_usuario: int
    estado: EstadoTrabajoGeneracion
    ruta_salida: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class TrabajoGeneracionDetalleResponse(TrabajoGeneracionCodigoResponse):
    """Trabajo con el detalle completo de sus entidades y reglas de mapeo."""

    entidades: list[EntidadGeneradaResponse] = Field(default_factory=list)


# ======================================================================
# DTOs específicos de operación
# ======================================================================
class GenerarBackendRequest(BaseModel):
    """
    Payload para disparar una nueva generación de backend Spring Boot a
    partir de un diagrama validado.
    """

    stack_destino: StackDestino = Field(default="SPRING_BOOT_JPA_POSTGRES")
    incluir_postman: bool = Field(
        default=True,
        description="Generar también la colección Postman del backend resultante",
    )
    nombre_proyecto: Optional[str] = Field(
        None,
        max_length=100,
        description="Nombre simbólico del proyecto generado (opcional)",
    )
    package_base: Optional[str] = Field(
        None,
        max_length=200,
        description="Package raíz Java, ej. 'com.devforge.generated.salud'",
    )


class EstadoGeneracionResponse(BaseModel):
    """
    Respuesta liviana para polling del estado de una generación.
    Pensada para que el frontend haga polling cada pocos segundos.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    estado: EstadoTrabajoGeneracion
    progreso: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Porcentaje estimado de avance (0-100), si se conoce",
    )
    mensaje: Optional[str] = Field(None, max_length=255)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class DescargaProyectoResponse(BaseModel):
    """Respuesta al pedir la descarga del backend generado."""

    id_trabajo: int
    download_url: str = Field(..., description="URL para descargar el ZIP del backend")
    tamanio_bytes: Optional[int] = Field(None, ge=0)
    incluye_postman: bool = True