# app/models/intercambio.py
"""
Modelos ORM del módulo E. Intercambio de Modelos (XMI/XML):

- ExportacionDiagrama  → registro de una exportación del diagrama a un archivo externo.
- ImportacionDiagrama  → registro de una importación de un modelo externo
                         hacia la plataforma.

Alineado 1:1 con el script SQL (módulo E).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ======================================================================
# ExportacionDiagrama
# ======================================================================
class ExportacionDiagrama(Base):
    __tablename__ = "exportaciones_diagrama"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    formato: Mapped[str] = mapped_column(
        String(10), nullable=False, default="XMI", server_default="XMI"
    )

    ruta_archivo: Mapped[str] = mapped_column(String(255), nullable=False)

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )

    exported_at: Mapped[datetime] = mapped_column(
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
            f"<ExportacionDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"formato={self.formato!r}>"
        )


# ======================================================================
# ImportacionDiagrama
# ======================================================================
class ImportacionDiagrama(Base):
    __tablename__ = "importaciones_diagrama"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('PENDIENTE','EXITOSO','FALLIDO')",
            name="ck_importacion_estado",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    formato: Mapped[str] = mapped_column(
        String(10), nullable=False, default="XMI", server_default="XMI"
    )

    archivo_origen: Mapped[str] = mapped_column(String(255), nullable=False)

    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE"
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
    )

    imported_at: Mapped[datetime] = mapped_column(
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
            f"<ImportacionDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"estado={self.estado!r}>"
        )