# app/models/ia.py
"""
Modelo ORM del módulo G. IA Asistente (Voz / Texto / Imagen):

- InteraccionIA → cada interacción del usuario con la IA integrada
                  (por voz o texto).

Alineado 1:1 con el script SQL (módulo G).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InteraccionIA(Base):
    __tablename__ = "interacciones_ia"
    __table_args__ = (
        CheckConstraint(
            "canal IN ('VOZ','TEXTO')",
            name="ck_interaccion_ia_canal",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_proyecto: Mapped[int] = mapped_column(
        ForeignKey("proyectos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Puede ser NULL si la interacción no está atada a un diagrama concreto.
    # El SQL usa ON DELETE SET NULL.
    id_diagrama: Mapped[Optional[int]] = mapped_column(
        ForeignKey("diagramas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # 'VOZ' o 'TEXTO'
    canal: Mapped[str] = mapped_column(String(10), nullable=False)

    # Lo que pidió el usuario (prompt tal cual, ya transcrito si fue por voz).
    texto_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Acción estructurada que la IA propuso/ejecutó (JSONB, libre por tipo de acción).
    respuesta_ia: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )

    # Si el cambio propuesto por la IA se aplicó realmente al diagrama.
    accion_aplicada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    proyecto: Mapped["Proyecto"] = relationship(  # noqa: F821
        "Proyecto",
        foreign_keys=[id_proyecto],
    )

    diagrama: Mapped[Optional["Diagrama"]] = relationship(  # noqa: F821
        "Diagrama",
        foreign_keys=[id_diagrama],
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    def __repr__(self) -> str:
        return (
            f"<InteraccionIA id={self.id} proyecto={self.id_proyecto} "
            f"canal={self.canal!r} aplicada={self.accion_aplicada}>"
        )