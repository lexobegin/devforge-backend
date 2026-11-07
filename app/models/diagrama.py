# app/models/diagrama.py
"""
Documentos del módulo C. Modelado UML (Diagrama de Clases) — CICLO 2.

- Diagrama               → un diagrama de clases dentro de un proyecto
                           (colección "diagramas").
- ClaseUML               → una clase UML (EMBEDIDA en Diagrama.clases).
- AtributoUML            → atributo de una clase, futura columna al
                           generar (EMBEDIDO en ClaseUML.atributos).
- OperacionUML           → operación/método de una clase (EMBEDIDO).
- ParametroOperacionUML  → parámetro de entrada de una operación (EMBEDIDO).
- InterfazUML            → interfaz UML «contrato» (EMBEDIDA).
- OperacionInterfazUML   → operación declarada por una interfaz (EMBEDIDO).
- RelacionUML            → relación entre dos clases: asociación,
                           agregación, composición, dependencia,
                           generalización o realización (EMBEDIDA).

Cambios clave respecto al Ciclo 1 (7 tablas → 1 documento):
- En Ciclo 1 un diagrama se dispersaba en 7 tablas relacionadas
  (diagramas, clases_uml, atributos_uml, operaciones_uml,
  parametros_operacion_uml, interfaces_uml, relaciones_uml): leer el
  lienzo completo costaba hasta 7 consultas. En Ciclo 2 TODO el diagrama
  vive en UN documento: la lectura del lienzo es atómica (1 consulta) y
  cada cambio colaborativo es una única escritura coherente.
- Esta estructura es la que explota el Agente Dev (CU18): el ejecutor de
  acciones modifica clases/atributos/relaciones embebidas y guarda el
  documento completo validando contra UML 2.5.1 (corrige la deficiencia
  del Ciclo 1 de dibujar "cajas vacías").
- Los ids INT autoincrementales de las tablas hijas se sustituyen por ids
  uuid (hex) generados en la aplicación: el lienzo, el WebSocket y las
  acciones de la IA los usan como referencia estable incluso antes de
  persistir (el frontend también puede generarlos).
- id_clase_origen / id_clase_destino de RelacionUML ya no son FK a la
  tabla clases_uml: son referencias a los ids uuid de las clases
  embebidas del MISMO diagrama.
- Las relationships de SQLAlchemy desaparecen; los helpers clase(),
  interfaz(), relacion() y buscar_clase_por_nombre() dan acceso directo a
  los elementos embebidos.
- version_uml y numero_version se conservan (UML 2.5.1 + versionado).
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

# Literales que reemplazan a los CHECK del Ciclo 1
VisibilidadUML = Literal["+", "-", "#", "~"]
TipoRelacion = Literal[
    "ASOCIACION",
    "AGREGACION",
    "COMPOSICION",
    "DEPENDENCIA",
    "GENERALIZACION",
    "REALIZACION",
]


# ======================================================================
# ParametroOperacionUML (embebido)
# ======================================================================
class ParametroOperacionUML(BaseModel):  # embebido: los embebidos de Beanie son pydantic
    """Parámetro de entrada de una operación (antes tabla
    parametros_operacion_uml)."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id: str = Field(default_factory=lambda: uuid4().hex)

    nombre: str

    tipo_dato: str

    orden: int = 0

    def __repr__(self) -> str:
        return (
            f"<ParametroOperacionUML id={self.id} nombre={self.nombre!r} "
            f"tipo={self.tipo_dato!r}>"
        )


# ======================================================================
# AtributoUML (embebido)
# ======================================================================
class AtributoUML(BaseModel):  # embebido
    """Atributo de una clase UML (antes tabla atributos_uml)."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id: str = Field(default_factory=lambda: uuid4().hex)

    nombre: str

    tipo_dato: str

    visibilidad: VisibilidadUML = "-"

    es_estatico: bool = False

    valor_defecto: Optional[str] = None

    orden: int = 0

    def __repr__(self) -> str:
        return (
            f"<AtributoUML id={self.id} nombre={self.nombre!r} "
            f"tipo={self.tipo_dato!r}>"
        )


# ======================================================================
# OperacionUML (embebida)
# ======================================================================
class OperacionUML(BaseModel):  # embebido
    """Operación/método de una clase UML (antes tabla operaciones_uml)."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id: str = Field(default_factory=lambda: uuid4().hex)

    nombre: str

    tipo_retorno: str = "void"

    visibilidad: VisibilidadUML = "+"

    es_estatico: bool = False

    orden: int = 0

    # Parámetros EMBEBIDOS (antes tabla parametros_operacion_uml)
    parametros: list[ParametroOperacionUML] = Field(default_factory=list)

    def __repr__(self) -> str:
        return f"<OperacionUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# OperacionInterfazUML (embebida)
# ======================================================================
class OperacionInterfazUML(BaseModel):  # embebido
    """Operación declarada por una interfaz (antes tabla
    operaciones_interfaz_uml)."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id: str = Field(default_factory=lambda: uuid4().hex)

    nombre: str

    tipo_retorno: str = "void"

    def __repr__(self) -> str:
        return f"<OperacionInterfazUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# InterfazUML (embebida)
# ======================================================================
class InterfazUML(BaseModel):  # embebido
    """Interfaz UML «contrato» (antes tabla interfaces_uml)."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id: str = Field(default_factory=lambda: uuid4().hex)

    nombre: str

    pos_x: float = 0.0

    pos_y: float = 0.0

    # Operaciones EMBEBIDAS (antes tabla operaciones_interfaz_uml)
    operaciones: list[OperacionInterfazUML] = Field(default_factory=list)

    def __repr__(self) -> str:
        return f"<InterfazUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# ClaseUML (embebida)
# ======================================================================
class ClaseUML(BaseModel):  # embebido
    """Clase UML del diagrama (antes tabla clases_uml)."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id: str = Field(default_factory=lambda: uuid4().hex)

    nombre: str

    es_abstracta: bool = False

    estereotipo: Optional[str] = None

    pos_x: float = 0.0

    pos_y: float = 0.0

    # ObjectId del usuario creador (antes FK a usuarios.id). Opcional solo
    # para importaciones XMI del Ciclo 1; los servicios lo asignan siempre.
    id_creador: Optional[PydanticObjectId] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Elementos EMBEBIDOS de la clase
    # (antes tablas atributos_uml y operaciones_uml)
    # ------------------------------------------------------------------
    atributos: list[AtributoUML] = Field(default_factory=list)

    operaciones: list[OperacionUML] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def atributo(self, id_atributo: str) -> Optional[AtributoUML]:
        """Devuelve el atributo con ese id (o None)."""
        for atributo in self.atributos:
            if atributo.id == id_atributo:
                return atributo
        return None

    def operacion(self, id_operacion: str) -> Optional[OperacionUML]:
        """Devuelve la operación con ese id (o None)."""
        for operacion in self.operaciones:
            if operacion.id == id_operacion:
                return operacion
        return None

    def __repr__(self) -> str:
        return f"<ClaseUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# RelacionUML (embebida)
# ======================================================================
class RelacionUML(BaseModel):  # embebido
    """Relación entre dos clases del mismo diagrama (antes tabla
    relaciones_uml)."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id: str = Field(default_factory=lambda: uuid4().hex)

    # Referencias a los ids uuid de las ClaseUML embebidas
    id_clase_origen: str

    id_clase_destino: str

    tipo_relacion: TipoRelacion

    multiplicidad_origen: Optional[str] = None

    multiplicidad_destino: Optional[str] = None

    nombre_asociacion: Optional[str] = None

    rol_origen: Optional[str] = None

    rol_destino: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"<RelacionUML id={self.id} tipo={self.tipo_relacion!r} "
            f"{self.id_clase_origen}->{self.id_clase_destino}>"
        )


# ======================================================================
# Diagrama
# ======================================================================
class Diagrama(Document):
    """Diagrama de clases UML (colección "diagramas")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla diagramas)
    # ------------------------------------------------------------------
    id_proyecto: PydanticObjectId

    nombre: str

    version_uml: str = "2.5.1"

    numero_version: int = 1

    id_creador: PydanticObjectId

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Contenido del lienzo EMBEBIDO
    # (antes tablas clases_uml, interfaces_uml y relaciones_uml)
    # ------------------------------------------------------------------
    clases: list[ClaseUML] = Field(default_factory=list)

    interfaces: list[InterfazUML] = Field(default_factory=list)

    relaciones: list[RelacionUML] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "diagramas"           # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_proyecto", "id_creador"]

    # ------------------------------------------------------------------
    # Helpers — acceso directo a los elementos embebidos
    # (los usan el WebSocket de colaboración, el ejecutor de acciones del
    #  Agente Dev y el exportador/importador XMI)
    # ------------------------------------------------------------------
    def clase(self, id_clase: str) -> Optional[ClaseUML]:
        """Devuelve la clase embebida con ese id (o None)."""
        for clase in self.clases:
            if clase.id == id_clase:
                return clase
        return None

    def interfaz(self, id_interfaz: str) -> Optional[InterfazUML]:
        """Devuelve la interfaz embebida con ese id (o None)."""
        for interfaz in self.interfaces:
            if interfaz.id == id_interfaz:
                return interfaz
        return None

    def relacion(self, id_relacion: str) -> Optional[RelacionUML]:
        """Devuelve la relación embebida con ese id (o None)."""
        for relacion in self.relaciones:
            if relacion.id == id_relacion:
                return relacion
        return None

    def buscar_clase_por_nombre(self, nombre: str) -> Optional[ClaseUML]:
        """Resuelve una clase por nombre (sin distinguir mayúsculas).

        La usa el Agente Dev (CU18) cuando la acción de la IA nombra la
        clase en lenguaje natural («añade un atributo a la clase
        Usuario...») y necesita su id uuid.
        """
        objetivo = nombre.strip().casefold()
        for clase in self.clases:
            if clase.nombre.strip().casefold() == objetivo:
                return clase
        return None

    def __repr__(self) -> str:
        return (
            f"<Diagrama id={self.id} proyecto={self.id_proyecto} "
            f"nombre={self.nombre!r} v={self.numero_version}>"
        )