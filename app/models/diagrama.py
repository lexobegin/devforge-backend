# app/models/diagrama.py
"""
Modelos ORM del módulo C. Modelado UML (Diagrama de Clases):

- Diagrama                  → un diagrama de clases dentro de un proyecto.
- ClaseUML                  → una clase UML (futura entidad/tabla al generar).
- AtributoUML               → atributo de una clase (futura columna).
- OperacionUML              → operación/método de una clase.
- ParametroOperacionUML     → parámetro de entrada de una operación.
- InterfazUML               → interfaz UML («contrato»).
- OperacionInterfazUML      → operación declarada por una interfaz.
- RelacionUML               → relación entre dos clases (asociación, herencia…).

Alineado 1:1 con el script SQL (módulo C).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ======================================================================
# Diagrama
# ======================================================================
class Diagrama(Base):
    __tablename__ = "diagramas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_proyecto: Mapped[int] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(String(150), nullable=False)

    version_uml: Mapped[str] = mapped_column(
        String(10), nullable=False, default="2.5.1", server_default="2.5.1"
    )

    numero_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    id_creador: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    proyecto: Mapped["Proyecto"] = relationship(  # noqa: F821
        "Proyecto",
        foreign_keys=[id_proyecto],
    )

    creador: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_creador],
    )

    clases: Mapped[list["ClaseUML"]] = relationship(
        "ClaseUML",
        back_populates="diagrama",
        cascade="all, delete-orphan",
    )

    interfaces: Mapped[list["InterfazUML"]] = relationship(
        "InterfazUML",
        back_populates="diagrama",
        cascade="all, delete-orphan",
    )

    relaciones: Mapped[list["RelacionUML"]] = relationship(
        "RelacionUML",
        back_populates="diagrama",
        cascade="all, delete-orphan",
        foreign_keys="RelacionUML.id_diagrama",
    )

    def __repr__(self) -> str:
        return (
            f"<Diagrama id={self.id} proyecto={self.id_proyecto} "
            f"nombre={self.nombre!r} v={self.numero_version}>"
        )


# ======================================================================
# ClaseUML
# ======================================================================
class ClaseUML(Base):
    __tablename__ = "clases_uml"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(String(150), nullable=False)

    es_abstracta: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    estereotipo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    pos_x: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=True, default=0, server_default="0"
    )

    pos_y: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=True, default=0, server_default="0"
    )

    id_creador: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    diagrama: Mapped["Diagrama"] = relationship(
        "Diagrama", back_populates="clases"
    )

    creador: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario", foreign_keys=[id_creador]
    )

    atributos: Mapped[list["AtributoUML"]] = relationship(
        "AtributoUML",
        back_populates="clase",
        cascade="all, delete-orphan",
        order_by="AtributoUML.orden",
    )

    operaciones: Mapped[list["OperacionUML"]] = relationship(
        "OperacionUML",
        back_populates="clase",
        cascade="all, delete-orphan",
        order_by="OperacionUML.orden",
    )

    def __repr__(self) -> str:
        return f"<ClaseUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# AtributoUML
# ======================================================================
class AtributoUML(Base):
    __tablename__ = "atributos_uml"
    __table_args__ = (
        CheckConstraint(
            "visibilidad IN ('+','-','#','~')",
            name="ck_atributo_visibilidad",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_clase: Mapped[int] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(String(100), nullable=False)

    tipo_dato: Mapped[str] = mapped_column(String(50), nullable=False)

    visibilidad: Mapped[str] = mapped_column(
        String(1), nullable=False, default="-", server_default="-"
    )

    es_estatico: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    valor_defecto: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    orden: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    clase: Mapped["ClaseUML"] = relationship(
        "ClaseUML", back_populates="atributos"
    )

    def __repr__(self) -> str:
        return (
            f"<AtributoUML id={self.id} nombre={self.nombre!r} "
            f"tipo={self.tipo_dato!r}>"
        )


# ======================================================================
# OperacionUML
# ======================================================================
class OperacionUML(Base):
    __tablename__ = "operaciones_uml"
    __table_args__ = (
        CheckConstraint(
            "visibilidad IN ('+','-','#','~')",
            name="ck_operacion_visibilidad",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_clase: Mapped[int] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(String(100), nullable=False)

    tipo_retorno: Mapped[str] = mapped_column(
        String(50), nullable=False, default="void", server_default="void"
    )

    visibilidad: Mapped[str] = mapped_column(
        String(1), nullable=False, default="+", server_default="+"
    )

    es_estatico: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    orden: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    clase: Mapped["ClaseUML"] = relationship(
        "ClaseUML", back_populates="operaciones"
    )

    parametros: Mapped[list["ParametroOperacionUML"]] = relationship(
        "ParametroOperacionUML",
        back_populates="operacion",
        cascade="all, delete-orphan",
        order_by="ParametroOperacionUML.orden",
    )

    def __repr__(self) -> str:
        return f"<OperacionUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# ParametroOperacionUML
# ======================================================================
class ParametroOperacionUML(Base):
    __tablename__ = "parametros_operacion_uml"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_operacion: Mapped[int] = mapped_column(
        ForeignKey("operaciones_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(String(100), nullable=False)

    tipo_dato: Mapped[str] = mapped_column(String(50), nullable=False)

    orden: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    operacion: Mapped["OperacionUML"] = relationship(
        "OperacionUML", back_populates="parametros"
    )

    def __repr__(self) -> str:
        return (
            f"<ParametroOperacionUML id={self.id} nombre={self.nombre!r} "
            f"tipo={self.tipo_dato!r}>"
        )


# ======================================================================
# InterfazUML
# ======================================================================
class InterfazUML(Base):
    __tablename__ = "interfaces_uml"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(String(150), nullable=False)

    pos_x: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=True, default=0, server_default="0"
    )

    pos_y: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=True, default=0, server_default="0"
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    diagrama: Mapped["Diagrama"] = relationship(
        "Diagrama", back_populates="interfaces"
    )

    operaciones: Mapped[list["OperacionInterfazUML"]] = relationship(
        "OperacionInterfazUML",
        back_populates="interfaz",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<InterfazUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# OperacionInterfazUML
# ======================================================================
class OperacionInterfazUML(Base):
    __tablename__ = "operaciones_interfaz_uml"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_interfaz: Mapped[int] = mapped_column(
        ForeignKey("interfaces_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(String(100), nullable=False)

    tipo_retorno: Mapped[str] = mapped_column(
        String(50), nullable=False, default="void", server_default="void"
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    interfaz: Mapped["InterfazUML"] = relationship(
        "InterfazUML", back_populates="operaciones"
    )

    def __repr__(self) -> str:
        return f"<OperacionInterfazUML id={self.id} nombre={self.nombre!r}>"


# ======================================================================
# RelacionUML
# ======================================================================
class RelacionUML(Base):
    __tablename__ = "relaciones_uml"
    __table_args__ = (
        CheckConstraint(
            "tipo_relacion IN "
            "('ASOCIACION','AGREGACION','COMPOSICION','DEPENDENCIA',"
            "'GENERALIZACION','REALIZACION')",
            name="ck_relacion_tipo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_clase_origen: Mapped[int] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_clase_destino: Mapped[int] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo_relacion: Mapped[str] = mapped_column(String(20), nullable=False)

    multiplicidad_origen: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )

    multiplicidad_destino: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )

    nombre_asociacion: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    rol_origen: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    rol_destino: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    diagrama: Mapped["Diagrama"] = relationship(
        "Diagrama",
        back_populates="relaciones",
        foreign_keys=[id_diagrama],
    )

    clase_origen: Mapped["ClaseUML"] = relationship(
        "ClaseUML", foreign_keys=[id_clase_origen]
    )

    clase_destino: Mapped["ClaseUML"] = relationship(
        "ClaseUML", foreign_keys=[id_clase_destino]
    )

    def __repr__(self) -> str:
        return (
            f"<RelacionUML id={self.id} tipo={self.tipo_relacion!r} "
            f"{self.id_clase_origen}->{self.id_clase_destino}>"
        )