# app/models/usuario.py
"""
Modelo ORM: usuarios (módulo A. Usuarios y Seguridad).

Representa a Ingenieros de Software, Líderes de Proyecto y Administradores
de la plataforma DevForge AI.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    # ------------------------------------------------------------------
    # Columnas
    # ------------------------------------------------------------------
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)

    email: Mapped[str] = mapped_column(
        String(150), nullable=False, unique=True, index=True
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    rol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DESARROLLADOR",
        server_default="DESARROLLADOR",
    )

    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    # ------------------------------------------------------------------
    # Relaciones (se irán completando cuando existan los modelos destino)
    # ------------------------------------------------------------------
    # Proyectos donde el usuario es propietario
    proyectos_propios: Mapped[list["Proyecto"]] = relationship(  # noqa: F821
        "Proyecto",
        back_populates="propietario",
        foreign_keys="Proyecto.id_propietario",
    )

    # Membresías a proyectos (con rol dentro de cada uno)
    membresias: Mapped[list["MiembroProyecto"]] = relationship(  # noqa: F821
        "MiembroProyecto",
        back_populates="usuario",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def is_admin(self) -> bool:
        return self.rol == "ADMIN"

    def __repr__(self) -> str:
        return f"<Usuario id={self.id} email={self.email!r} rol={self.rol!r}>"