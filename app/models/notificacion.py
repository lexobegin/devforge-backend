# app/models/notificacion.py
"""
Modelo ORM del módulo I. Notificaciones:

- Notificacion → notificaciones para el usuario (alguien comentó, cambió el
                 diagrama, terminó la generación de código, etc.).

Alineado 1:1 con el script SQL (módulo I).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Destinatario de la notificación.
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 'COMENTARIO','CAMBIO_DIAGRAMA','GENERACION_COMPLETA', etc.
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)

    mensaje: Mapped[str] = mapped_column(String(255), nullable=False)

    # id del recurso relacionado (diagrama, comentario, trabajo_generacion…).
    # Es polimórfica: NO lleva FK porque puede apuntar a distintas tablas
    # según `tipo`. Se guarda como BIGINT simple.
    id_referencia: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )

    leida: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def marcar_leida(self) -> None:
        """Marca la notificación como leída (uso desde services)."""
        self.leida = True

    def __repr__(self) -> str:
        return (
            f"<Notificacion id={self.id} usuario={self.id_usuario} "
            f"tipo={self.tipo!r} leida={self.leida}>"
        )