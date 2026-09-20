# app/models/colaboracion.py
"""
Modelos ORM del módulo B. Proyectos y Colaboración (parte 2):

- SesionColaboracion     → sesión activa de edición colaborativa en tiempo real
                           sobre un diagrama.
- ParticipanteSesion     → usuario conectado dentro de una sesión, con su
                           posición/foco actual en el lienzo (para verlo en vivo).

Nota: la FK `sesiones_colaboracion.id_diagrama → diagramas.id` se declara aquí
con `use_alter=True` porque `diagramas` se define en otro archivo (diagrama.py).
SQLAlchemy la emitirá en el orden correcto (después de crear `diagramas`).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ======================================================================
# SesionColaboracion
# ======================================================================
class SesionColaboracion(Base):
    __tablename__ = "sesiones_colaboracion"

    # ------------------------------------------------------------------
    # Columnas
    # ------------------------------------------------------------------
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_proyecto: Mapped[int] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # FK hacia "diagramas" — declarada con use_alter para romper la dependencia
    # circular de orden de creación entre sesiones_colaboracion y diagramas.
    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey(
            "diagramas.id",
            ondelete="CASCADE",
            use_alter=True,
            name="fk_sesion_diagrama",
        ),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    proyecto: Mapped["Proyecto"] = relationship(  # noqa: F821
        "Proyecto",
        foreign_keys=[id_proyecto],
    )

    # La relación hacia Diagrama se define aquí solo por FK (sin back_populates)
    # para no forzar el import cruzado. diagrama.py puede añadir la inversa.
    diagrama: Mapped["Diagrama"] = relationship(  # noqa: F821
        "Diagrama",
        foreign_keys=[id_diagrama],
        lazy="selectin",
    )

    participantes: Mapped[list["ParticipanteSesion"]] = relationship(
        "ParticipanteSesion",
        back_populates="sesion",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def activa(self) -> bool:
        """Una sesión sigue activa mientras no tenga fecha de fin."""
        return self.ended_at is None

    def __repr__(self) -> str:
        return (
            f"<SesionColaboracion id={self.id} proyecto={self.id_proyecto} "
            f"diagrama={self.id_diagrama} activa={self.activa}>"
        )


# ======================================================================
# ParticipanteSesion
# ======================================================================
class ParticipanteSesion(Base):
    __tablename__ = "participantes_sesion"

    # ------------------------------------------------------------------
    # Columnas
    # ------------------------------------------------------------------
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_sesion: Mapped[int] = mapped_column(
        ForeignKey("sesiones_colaboracion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    left_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    # Posición/foco actual del usuario en el lienzo (x, y, zoom, elemento activo…)
    # Se usa JSONB para poder evolucionar el formato sin migraciones.
    posicion_cursor: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    sesion: Mapped["SesionColaboracion"] = relationship(
        "SesionColaboracion", back_populates="participantes"
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def conectado(self) -> bool:
        """Sigue conectado mientras no tenga fecha de salida."""
        return self.left_at is None

    def __repr__(self) -> str:
        return (
            f"<ParticipanteSesion id={self.id} sesion={self.id_sesion} "
            f"usuario={self.id_usuario} conectado={self.conectado}>"
        )