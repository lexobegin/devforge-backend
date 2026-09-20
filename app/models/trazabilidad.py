# app/models/trazabilidad.py
"""
Modelos ORM del módulo D. Trazabilidad y Colaboración en Tiempo Real:

- HistorialCambioDiagrama  → registro de cada cambio hecho sobre un diagrama
                             (para deshacer y resolver conflictos entre varios
                             usuarios editando a la vez).
- VersionDiagrama          → snapshot completo del diagrama al guardar una versión.
- ComentarioDiagrama       → comentarios/anotaciones que los colaboradores
                             dejan sobre un elemento del diagrama.

Alineado 1:1 con el script SQL (módulo D).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ======================================================================
# HistorialCambioDiagrama
# ======================================================================
class HistorialCambioDiagrama(Base):
    __tablename__ = "historial_cambios_diagrama"
    __table_args__ = (
        CheckConstraint(
            "tipo_cambio IN ('CREAR','MODIFICAR','ELIMINAR')",
            name="ck_historial_tipo_cambio",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    tipo_cambio: Mapped[str] = mapped_column(String(20), nullable=False)

    # 'CLASE', 'ATRIBUTO', 'RELACION', etc.
    tipo_entidad: Mapped[str] = mapped_column(String(30), nullable=False)

    # id del elemento afectado (puede ser id de clase, atributo, relación…)
    id_entidad: Mapped[int] = mapped_column(Integer, nullable=False)

    # Snapshot del cambio (antes/después). Libre para evolucionar por tipo de entidad.
    datos_cambio: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    diagrama: Mapped["Diagrama"] = relationship(  # noqa: F821
        "Diagrama",
        foreign_keys=[id_diagrama],
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    def __repr__(self) -> str:
        return (
            f"<HistorialCambioDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"{self.tipo_cambio} {self.tipo_entidad}#{self.id_entidad}>"
        )


# ======================================================================
# VersionDiagrama
# ======================================================================
class VersionDiagrama(Base):
    __tablename__ = "versiones_diagrama"
    __table_args__ = (
        UniqueConstraint(
            "id_diagrama", "numero_version",
            name="uq_version_diagrama_numero",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    numero_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Copia completa del diagrama en ese momento (clases, atributos, relaciones…).
    contenido_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )

    comentario: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    diagrama: Mapped["Diagrama"] = relationship(  # noqa: F821
        "Diagrama",
        foreign_keys=[id_diagrama],
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    def __repr__(self) -> str:
        return (
            f"<VersionDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"v={self.numero_version}>"
        )


# ======================================================================
# ComentarioDiagrama
# ======================================================================
class ComentarioDiagrama(Base):
    __tablename__ = "comentarios_diagrama"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Sobre qué elemento comenta: 'CLASE', 'RELACION'… NULL si es general al diagrama.
    tipo_entidad: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # id del elemento comentado (NULL si es general al diagrama).
    id_entidad: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    texto: Mapped[str] = mapped_column(Text, nullable=False)

    resuelto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    diagrama: Mapped["Diagrama"] = relationship(  # noqa: F821
        "Diagrama",
        foreign_keys=[id_diagrama],
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    def __repr__(self) -> str:
        return (
            f"<ComentarioDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"resuelto={self.resuelto}>"
        )