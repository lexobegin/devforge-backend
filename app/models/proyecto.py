# app/models/proyecto.py
"""
Modelos ORM del módulo B. Proyectos y Colaboración (parte 1):

- Proyecto           → proyectos de software que un equipo modela/genera.
- MiembroProyecto    → usuarios que pertenecen a un proyecto y su rol.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ======================================================================
# Proyecto
# ======================================================================
class Proyecto(Base):
    __tablename__ = "proyectos"

    # ------------------------------------------------------------------
    # Columnas
    # ------------------------------------------------------------------
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    nombre: Mapped[str] = mapped_column(String(150), nullable=False)

    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    id_propietario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVO", server_default="ACTIVO"
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
    propietario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        back_populates="proyectos_propios",
        foreign_keys=[id_propietario],
    )

    miembros: Mapped[list["MiembroProyecto"]] = relationship(
        "MiembroProyecto",
        back_populates="proyecto",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def esta_activo(self) -> bool:
        return self.estado == "ACTIVO"

    def __repr__(self) -> str:
        return f"<Proyecto id={self.id} nombre={self.nombre!r} estado={self.estado!r}>"


# ======================================================================
# MiembroProyecto
# ======================================================================
class MiembroProyecto(Base):
    __tablename__ = "miembros_proyecto"
    __table_args__ = (
        UniqueConstraint("id_proyecto", "id_usuario", name="uq_miembro_proyecto_usuario"),
    )

    # ------------------------------------------------------------------
    # Columnas
    # ------------------------------------------------------------------
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_proyecto: Mapped[int] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    rol_en_proyecto: Mapped[str] = mapped_column(
        String(20), nullable=False, default="EDITOR", server_default="EDITOR"
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    proyecto: Mapped["Proyecto"] = relationship(
        "Proyecto", back_populates="miembros"
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario", back_populates="membresias"
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def es_propietario(self) -> bool:
        return self.rol_en_proyecto == "PROPIETARIO"

    def __repr__(self) -> str:
        return (
            f"<MiembroProyecto proyecto={self.id_proyecto} "
            f"usuario={self.id_usuario} rol={self.rol_en_proyecto!r}>"
        )