# app/schemas/generacion_schema.py
"""
Esquemas Pydantic del módulo F. Generación Automática de Backend:

- TrabajoGeneracionCodigo
- EntidadGenerada   (EMBEDIDA en TrabajoGeneracionCodigo.entidades)
- ReglaMapeo        (EMBEDIDA en EntidadGenerada.reglas_mapeo)

Además incluye los DTOs de operación:
- GenerarBackendRequest     → payload para disparar una generación
- EstadoGeneracionResponse  → estado resumido para polling desde el front

Cambios respecto al Ciclo 1:
- entidades_generadas y reglas_mapeo desaparecen como tablas: están
  EMBEBIDAS en el trabajo (trabajo → entidades[] → reglas_mapeo[]).
  Por eso sus *Response pierden id propio, id_trabajo e id_entidad_generada:
  la anidación da el alcance y los ids vienen del documento Trabajo.
- id_clase_uml / id_atributo_uml pasan de FK int a str uuid de los elementos
  embebidos del Diagrama (ClaseUML.id, AtributoUML.id).
- EstadoGeneracion unifica EstadoTrabajoGeneracion del Ciclo 1 con el
  Literal de app/models/generacion.py (mismos 4 estados).
- StackDestino: Literal de 2 valores desde la Tanda B21 (el frontend manda
  stack_destino="REACT_TS_VITE" en el MISMO POST /generar y el router
  deriva a GeneradorFrontendService; Ciclo 1 ya traía el campo en el
  request precisamente para ese dispatch).
- TrabajoGeneracionDetalleResponse ya no necesita ensamblar nada a mano:
  model_validate(trabajo) trae entidades y reglas anidadas (antes 3 tablas
  con joins).
"""

from datetime import datetime
from typing import Any, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables (alineados con app/models/generacion.py)
# ======================================================================
EstadoGeneracion = Literal["PENDIENTE", "EN_PROCESO", "EXITOSO", "FALLIDO"]

# Tanda B21: el dispatch de POST /generar decide el service por el valor
# (SPRING_BOOT_JPA_POSTGRES → GeneratorService, REACT_TS_VITE →
# GeneradorFrontendService). Hasta B21 solo validaba el stack de backend.
StackDestino = Literal["SPRING_BOOT_JPA_POSTGRES", "REACT_TS_VITE"]


# ======================================================================
# ReglaMapeo (embebida)
# ======================================================================
class ReglaMapeoBase(BaseModel):
    # id uuid del AtributoUML embebido del diagrama (antes FK a atributos_uml).
    id_atributo_uml: str = Field(..., min_length=1)
    nombre_columna: str = Field(..., min_length=1, max_length=100)
    tipo_sql: str = Field(..., min_length=1, max_length=50)
    es_clave_primaria: bool = Field(default=False)
    es_nulleable: bool = Field(default=True)


class ReglaMapeoResponse(ReglaMapeoBase):
    model_config = ConfigDict(from_attributes=True)

    # Sin id ni id_entidad_generada: es embebida de EntidadGeneradaResponse
    # y la anidación da el alcance


# ======================================================================
# EntidadGenerada (embebida)
# ======================================================================
class EntidadGeneradaBase(BaseModel):
    # id uuid del ClaseUML embebido del diagrama (antes FK a clases_uml).
    id_clase_uml: str = Field(..., min_length=1)
    nombre_clase_java: str = Field(..., min_length=1, max_length=150)
    nombre_tabla: str = Field(..., min_length=1, max_length=150)


class EntidadGeneradaResponse(EntidadGeneradaBase):
    model_config = ConfigDict(from_attributes=True)

    # Sin id ni id_trabajo: es embebida de TrabajoGeneracionDetalleResponse
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

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    id_diagrama: PydanticObjectId
    id_usuario: PydanticObjectId
    estado: EstadoGeneracion
    ruta_salida: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class TrabajoGeneracionDetalleResponse(TrabajoGeneracionCodigoResponse):
    """
    Trabajo con el detalle completo de sus entidades y reglas de mapeo.
    En el Ciclo 2 se construye directo con model_validate(trabajo): el
    resultado vive embebido en el documento (antes 3 tablas con joins).
    """

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

    id: PydanticObjectId
    estado: EstadoGeneracion
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
    """Respuesta al pedir la descarga del proyecto generado (ambos stacks)."""

    id_trabajo: PydanticObjectId  # string hex en JSON (antes int serial)
    download_url: str = Field(..., description="URL para descargar el ZIP")
    tamanio_bytes: Optional[int] = Field(None, ge=0)
    incluye_postman: bool = True
    # Tanda B22: nombre real del archivo en el servidor (basename de
    # ruta_salida, ej. frontend_ventas_6aee…_20261107_143454.zip) para que
    # el frontend lo use como nombre de descarga en lugar de inventar
    # devforge-backend-<id>.zip. El /archivo lo manda además en
    # Content-Disposition (main.py lo expone por CORS desde B22).
    nombre_archivo: Optional[str] = Field(
        None, max_length=255, description="Nombre real del ZIP en el servidor"
    )
