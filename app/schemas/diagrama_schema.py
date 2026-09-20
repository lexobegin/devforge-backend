# app/schemas/diagrama_schema.py
"""
Esquemas Pydantic del módulo C. Modelado UML (Diagrama de Clases).

Cubre las 8 entidades:
- Diagrama
- ClaseUML / AtributoUML / OperacionUML / ParametroOperacionUML
- InterfazUML / OperacionInterfazUML
- RelacionUML

Convención:
- *Base     → campos compartidos
- *Create   → entrada para creación
- *Update   → entrada para actualización parcial
- *Response → salida hacia el cliente (from_attributes=True)
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional, Annotated

from pydantic import BaseModel, ConfigDict, Field, BeforeValidator


def _cuantizar_posicion(v):
    if v is None:
        return None
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

PosicionDecimal = Annotated[Decimal, BeforeValidator(_cuantizar_posicion)]

# ======================================================================
# Tipos reutilizables (alineados con los CHECK del SQL)
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
    pass


class DiagramaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    version_uml: Optional[str] = Field(None, max_length=10)


class DiagramaResponse(DiagramaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_proyecto: int
    numero_version: int
    id_creador: int
    created_at: datetime
    updated_at: datetime


# ======================================================================
# AtributoUML
# ======================================================================
class AtributoUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_dato: str = Field(..., min_length=1, max_length=50)
    visibilidad: Visibilidad = Field(default="-")
    es_estatico: bool = Field(default=False)
    valor_defecto: Optional[str] = Field(None, max_length=100)
    orden: int = Field(default=0, ge=0)


class AtributoUMLCreate(AtributoUMLBase):
    """El id_clase se toma de la ruta."""


class AtributoUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_dato: Optional[str] = Field(None, min_length=1, max_length=50)
    visibilidad: Optional[Visibilidad] = None
    es_estatico: Optional[bool] = None
    valor_defecto: Optional[str] = Field(None, max_length=100)
    orden: Optional[int] = Field(None, ge=0)


class AtributoUMLResponse(AtributoUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_clase: int


# ======================================================================
# ParametroOperacionUML
# ======================================================================
class ParametroOperacionUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_dato: str = Field(..., min_length=1, max_length=50)
    orden: int = Field(default=0, ge=0)


class ParametroOperacionUMLCreate(ParametroOperacionUMLBase):
    """El id_operacion se toma de la ruta."""


class ParametroOperacionUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_dato: Optional[str] = Field(None, min_length=1, max_length=50)
    orden: Optional[int] = Field(None, ge=0)


class ParametroOperacionUMLResponse(ParametroOperacionUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_operacion: int


# ======================================================================
# OperacionUML
# ======================================================================
class OperacionUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_retorno: str = Field(default="void", max_length=50)
    visibilidad: Visibilidad = Field(default="+")
    es_estatico: bool = Field(default=False)
    orden: int = Field(default=0, ge=0)


class OperacionUMLCreate(OperacionUMLBase):
    """El id_clase se toma de la ruta."""
    parametros: list[ParametroOperacionUMLCreate] = Field(default_factory=list)


class OperacionUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_retorno: Optional[str] = Field(None, max_length=50)
    visibilidad: Optional[Visibilidad] = None
    es_estatico: Optional[bool] = None
    orden: Optional[int] = Field(None, ge=0)


class OperacionUMLResponse(OperacionUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_clase: int
    parametros: list[ParametroOperacionUMLResponse] = Field(default_factory=list)


# ======================================================================
# ClaseUML
# ======================================================================
class ClaseUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    es_abstracta: bool = Field(default=False)
    estereotipo: Optional[str] = Field(None, max_length=50)
    pos_x: PosicionDecimal = Field(default=Decimal("0"))
    pos_y: PosicionDecimal = Field(default=Decimal("0"))


class ClaseUMLCreate(ClaseUMLBase):
    """El id_diagrama y el id_creador se toman de la ruta y del token."""
    atributos: list[AtributoUMLCreate] = Field(default_factory=list)
    operaciones: list[OperacionUMLCreate] = Field(default_factory=list)


class ClaseUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    es_abstracta: Optional[bool] = None
    estereotipo: Optional[str] = Field(None, max_length=50)
    pos_x: Optional[PosicionDecimal] = None
    pos_y: Optional[PosicionDecimal] = None


class ClaseUMLResponse(ClaseUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int
    id_creador: int
    created_at: datetime
    updated_at: datetime
    atributos: list[AtributoUMLResponse] = Field(default_factory=list)
    operaciones: list[OperacionUMLResponse] = Field(default_factory=list)


# ======================================================================
# OperacionInterfazUML
# ======================================================================
class OperacionInterfazUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo_retorno: str = Field(default="void", max_length=50)


class OperacionInterfazUMLCreate(OperacionInterfazUMLBase):
    """El id_interfaz se toma de la ruta."""


class OperacionInterfazUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_retorno: Optional[str] = Field(None, max_length=50)


class OperacionInterfazUMLResponse(OperacionInterfazUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_interfaz: int


# ======================================================================
# InterfazUML
# ======================================================================
class InterfazUMLBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    pos_x: Decimal = Field(default=Decimal("0"))
    pos_y: Decimal = Field(default=Decimal("0"))


class InterfazUMLCreate(InterfazUMLBase):
    """El id_diagrama se toma de la ruta."""
    operaciones: list[OperacionInterfazUMLCreate] = Field(default_factory=list)


class InterfazUMLUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    pos_x: Optional[Decimal] = None
    pos_y: Optional[Decimal] = None


class InterfazUMLResponse(InterfazUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int
    operaciones: list[OperacionInterfazUMLResponse] = Field(default_factory=list)


# ======================================================================
# RelacionUML
# ======================================================================
class RelacionUMLBase(BaseModel):
    id_clase_origen: int = Field(..., gt=0)
    id_clase_destino: int = Field(..., gt=0)
    tipo_relacion: TipoRelacion
    multiplicidad_origen: Optional[str] = Field(None, max_length=10)
    multiplicidad_destino: Optional[str] = Field(None, max_length=10)
    nombre_asociacion: Optional[str] = Field(None, max_length=100)
    rol_origen: Optional[str] = Field(None, max_length=100)
    rol_destino: Optional[str] = Field(None, max_length=100)


class RelacionUMLCreate(RelacionUMLBase):
    """El id_diagrama se toma de la ruta."""


class RelacionUMLUpdate(BaseModel):
    id_clase_origen: Optional[int] = Field(None, gt=0)
    id_clase_destino: Optional[int] = Field(None, gt=0)
    tipo_relacion: Optional[TipoRelacion] = None
    multiplicidad_origen: Optional[str] = Field(None, max_length=10)
    multiplicidad_destino: Optional[str] = Field(None, max_length=10)
    nombre_asociacion: Optional[str] = Field(None, max_length=100)
    rol_origen: Optional[str] = Field(None, max_length=100)
    rol_destino: Optional[str] = Field(None, max_length=100)


class RelacionUMLResponse(RelacionUMLBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_diagrama: int


# ======================================================================
# Compuestos (respuestas enriquecidas)
# ======================================================================
class DiagramaCompletoResponse(DiagramaResponse):
    """
    Diagrama con todo su contenido: clases (con atributos/operaciones),
    interfaces y relaciones. Pensado para carga inicial del editor y
    para el motor de generación automática.
    """

    clases: list[ClaseUMLResponse] = Field(default_factory=list)
    interfaces: list[InterfazUMLResponse] = Field(default_factory=list)
    relaciones: list[RelacionUMLResponse] = Field(default_factory=list)
