# app/schemas/diagrama_schema.py
"""
Esquemas Pydantic del módulo C. Modelado UML (Diagrama de Clases).

Cubre el documento Diagrama y sus 7 clases EMBEBIDAS:
- ClaseUML / AtributoUML / OperacionUML / ParametroOperacionUML
- InterfazUML / OperacionInterfazUML
- RelacionUML

Convención:
- *Base     → campos compartidos
- *Create   → entrada para creación
- *Update   → entrada para actualización parcial
- *Response → salida hacia el cliente (from_attributes=True)

Cambios respecto al Ciclo 1 (7 tablas → 1 documento):
- Clases, atributos, operaciones, parámetros, interfaces y relaciones ya
  no son filas con FK: son elementos EMBEBIDOS del documento Diagrama.
  Por eso sus *Response pierden id_diagrama / id_clase / id_operacion /
  id_interfaz (el alcance lo da la anidación) y su id es str uuid
  (lo genera el modelo o el propio lienzo, estable incluso antes de
  persistir).
- ClaseUMLResponse conserva id_creador / created_at / updated_at porque
  el modelo embebido los lleva (auditoría por clase).
- id_clase_origen / id_clase_destino de RelacionUML pasan de int (FK a
  clases_uml) a str uuid de las clases embebidas del MISMO diagrama.
- PosicionDecimal del Ciclo 1 se convierte en PosicionLienzo: sigue
  cuantizando a 2 decimales (0.01) para evitar el ruido flotante en el
  lienzo, pero devuelve float, el tipo que almacenan los documentos.
- DiagramaCompletoResponse se construye directo con
  model_validate(diagrama): el contenido vive embebido, sin joins.
- Los *Update se reutilizan tal cual en el ejecutor de acciones del
  Agente Dev (CU16-21): el payload que propone el LLM se valida con estos
  esquemas antes de tocar el lienzo (corrige las deficiencias 1 y 2 del
  Ciclo 1: cajas vacías y cambios sin estructura).
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal, Optional, Any

from beanie import PydanticObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _cuantizar_posicion(v):
    if v is None:
        return None
    # Cuantiza a 2 decimales (0.01) para que el lienzo no reciba
    # ruido tipo 12.300000000000001
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


PosicionLienzo = Annotated[float, BeforeValidator(_cuantizar_posicion)]

# ======================================================================
# Tipos reutilizables (alineados con app/models/diagrama.py)
# ======================================================================
Visibilidad = Literal["+", "-", "#", "~"]

TipoRelacion = Literal[
    "ASOCIACION",
    "AGREGACION",
    "COMPOSICION",
    "DEPENDENCIA",
    "GENERALIZACION",
    "REALIZACION",
]


# ======================================================================
# Diagrama
# ======================================================================
class DiagramaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    version_uml: str = Field(default="2.5.1", max_length=10)


class DiagramaCreate(DiagramaBase):
    """El id_proyecto y el id_creador se toman de la ruta y del token."""


class DiagramaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    version_uml: Optional[str] = Field(None, max_length=10)


class DiagramaResponse(DiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    id_proyecto: PydanticObjectId
    numero_version: int
    id_creador: PydanticObjectId
    created_at: datetime
    updated_at: datetime


# ======================================================================
# AtributoUML (embebido)
# ======================================================================
class AtributoUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_dato: str = Field(..., min_length=1, max_length=50)
    visibilidad: Visibilidad = Field(default="-")
    es_estatico: bool = Field(default=False)
    valor_defecto: Optional[str] = Field(None, max_length=100)
    orden: int = Field(default=0, ge=0)


class AtributoUMLCreate(AtributoUMLBase):
    """Llega anidado dentro de ClaseUMLCreate (el id lo genera el modelo)."""


class AtributoUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_dato: Optional[str] = Field(None, min_length=1, max_length=50)
    visibilidad: Optional[Visibilidad] = None
    es_estatico: Optional[bool] = None
    valor_defecto: Optional[str] = Field(None, max_length=100)
    orden: Optional[int] = Field(None, ge=0)


class AtributoUMLResponse(AtributoUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: str  # uuid del elemento embebido (antes int serial)
    # Sin id_clase: la anidación dentro de la clase ya da el alcance


# ======================================================================
# ParametroOperacionUML (embebido)
# ======================================================================
class ParametroOperacionUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_dato: str = Field(..., min_length=1, max_length=50)
    orden: int = Field(default=0, ge=0)


class ParametroOperacionUMLCreate(ParametroOperacionUMLBase):
    """Llega anidado dentro de OperacionUMLCreate."""


class ParametroOperacionUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_dato: Optional[str] = Field(None, min_length=1, max_length=50)
    orden: Optional[int] = Field(None, ge=0)


class ParametroOperacionUMLResponse(ParametroOperacionUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Sin id_operacion: la anidación dentro de la operación ya da el alcance


# ======================================================================
# OperacionUML (embebida)
# ======================================================================
class OperacionUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_retorno: str = Field(default="void", max_length=50)
    visibilidad: Visibilidad = Field(default="+")
    es_estatico: bool = Field(default=False)
    orden: int = Field(default=0, ge=0)


class OperacionUMLCreate(OperacionUMLBase):
    """Llega anidado dentro de ClaseUMLCreate."""

    parametros: list[ParametroOperacionUMLCreate] = Field(default_factory=list)


class OperacionUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_retorno: Optional[str] = Field(None, max_length=50)
    visibilidad: Optional[Visibilidad] = None
    es_estatico: Optional[bool] = None
    orden: Optional[int] = Field(None, ge=0)


class OperacionUMLResponse(OperacionUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Sin id_clase: la anidación dentro de la clase ya da el alcance
    parametros: list[ParametroOperacionUMLResponse] = Field(default_factory=list)


# ======================================================================
# ClaseUML (embebida)
# ======================================================================
class ClaseUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    es_abstracta: bool = Field(default=False)
    estereotipo: Optional[str] = Field(None, max_length=50)
    pos_x: PosicionLienzo = Field(default=0.0)
    pos_y: PosicionLienzo = Field(default=0.0)


class ClaseUMLCreate(ClaseUMLBase):
    """
    Crear una clase dentro del diagrama (se inserta en Diagrama.clases).
    La usa también la visión (CU14) para volcar el boceto reconocido como
    clases completas con atributos y operaciones, no cajas vacías.
    """

    atributos: list[AtributoUMLCreate] = Field(default_factory=list)
    operaciones: list[OperacionUMLCreate] = Field(default_factory=list)


class ClaseUMLUpdate(BaseModel):
    """
    Actualización parcial de una clase embebida. Es el mismo formato que
    el ejecutor del Agente Dev espera en el payload de MODIFICAR_CLASE.
    """

    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    es_abstracta: Optional[bool] = None
    estereotipo: Optional[str] = Field(None, max_length=50)
    pos_x: Optional[PosicionLienzo] = None
    pos_y: Optional[PosicionLienzo] = None


class ClaseUMLResponse(ClaseUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: str  # uuid del elemento embebido (antes int serial)
    # Sin id_diagrama: la anidación dentro del diagrama ya da el alcance
    id_creador: Optional[PydanticObjectId] = None
    created_at: datetime
    updated_at: datetime
    atributos: list[AtributoUMLResponse] = Field(default_factory=list)
    operaciones: list[OperacionUMLResponse] = Field(default_factory=list)


# ======================================================================
# OperacionInterfazUML (embebida)
# ======================================================================
class OperacionInterfazUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_retorno: str = Field(default="void", max_length=50)


class OperacionInterfazUMLCreate(OperacionInterfazUMLBase):
    """Llega anidado dentro de InterfazUMLCreate."""


class OperacionInterfazUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_retorno: Optional[str] = Field(None, max_length=50)


class OperacionInterfazUMLResponse(OperacionInterfazUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Sin id_interfaz: la anidación dentro de la interfaz ya da el alcance


# ======================================================================
# InterfazUML (embebida)
# ======================================================================
class InterfazUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    pos_x: PosicionLienzo = Field(default=0.0)
    pos_y: PosicionLienzo = Field(default=0.0)


class InterfazUMLCreate(InterfazUMLBase):
    """Crear una interfaz dentro del diagrama (se inserta en Diagrama.interfaces)."""

    operaciones: list[OperacionInterfazUMLCreate] = Field(default_factory=list)


class InterfazUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    pos_x: Optional[PosicionLienzo] = None
    pos_y: Optional[PosicionLienzo] = None


class InterfazUMLResponse(InterfazUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Sin id_diagrama: la anidación dentro del diagrama ya da el alcance
    operaciones: list[OperacionInterfazUMLResponse] = Field(default_factory=list)


# ======================================================================
# RelacionUML (embebida)
# ======================================================================
class RelacionUMLBase(BaseModel):
    # Referencias a los ids uuid de las ClaseUML embebidas del MISMO
    # diagrama (antes FK int a la tabla clases_uml)
    id_clase_origen: str = Field(..., min_length=1)
    id_clase_destino: str = Field(..., min_length=1)
    tipo_relacion: TipoRelacion
    multiplicidad_origen: Optional[str] = Field(None, max_length=10)
    multiplicidad_destino: Optional[str] = Field(None, max_length=10)
    nombre_asociacion: Optional[str] = Field(None, max_length=100)
    rol_origen: Optional[str] = Field(None, max_length=100)
    rol_destino: Optional[str] = Field(None, max_length=100)


class RelacionUMLCreate(RelacionUMLBase):
    """Crear una relación dentro del diagrama (se inserta en Diagrama.relaciones)."""


class RelacionUMLUpdate(BaseModel):
    id_clase_origen: Optional[str] = Field(None, min_length=1)
    id_clase_destino: Optional[str] = Field(None, min_length=1)
    tipo_relacion: Optional[TipoRelacion] = None
    multiplicidad_origen: Optional[str] = Field(None, max_length=10)
    multiplicidad_destino: Optional[str] = Field(None, max_length=10)
    nombre_asociacion: Optional[str] = Field(None, max_length=100)
    rol_origen: Optional[str] = Field(None, max_length=100)
    rol_destino: Optional[str] = Field(None, max_length=100)


class RelacionUMLResponse(RelacionUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Sin id_diagrama: la anidación dentro del diagrama ya da el alcance


# ======================================================================
# Compuestos (respuestas enriquecidas)
# ======================================================================
class DiagramaCompletoResponse(DiagramaResponse):
    """
    Diagrama con todo su contenido embebido: clases (con atributos y
    operaciones), interfaces y relaciones. Pensado para la carga inicial
    del editor, el motor de generación automática y el contexto que se
    arma para la IA (CU17).

    En el Ciclo 2 se construye directo con
    DiagramaCompletoResponse.model_validate(diagrama): no hay joins, el
    contenido ya vive dentro del documento.
    """

    clases: list[ClaseUMLResponse] = Field(default_factory=list)
    interfaces: list[InterfazUMLResponse] = Field(default_factory=list)
    relaciones: list[RelacionUMLResponse] = Field(default_factory=list)

# ======================================================================
# IA de visión (boceto/imagen → diagrama reconstruido) — movido desde
# ia_schema.py: el resultado es un DIAGRAMA del módulo C
# ======================================================================
class VisionReconocimientoResponse(BaseModel):
    """
    Resultado del reconocimiento de un boceto/imagen de diagrama.
    El cliente recibe un diagrama reconstruido listo para insertar.
    En el Ciclo 2 el reconocedor produce ClaseUMLCreate completos (atributos,
    operaciones y RelacionUMLCreate), no cajas vacías (deficiencia 1 del
    Ciclo 1): diagrama_reconstruido sigue el mismo formato que
    DiagramaCompletoResponse y se puede validar con los esquemas del módulo C.
    """

    exito: bool = True
    confianza: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confianza global del reconocimiento"
    )
    diagrama_reconstruido: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Estructura reconstruida: clases, atributos, operaciones y "
            "relaciones. Mismo formato que DiagramaCompletoResponse."
        ),
    )
    advertencias: list[str] = Field(default_factory=list)
    imagen_procesada_url: Optional[str] = None