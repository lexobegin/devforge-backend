# app/models/auditoria.py
"""
Modelo ORM del módulo de Auditoría:

- BitacoraSistema → bitácora general de eventos relevantes del sistema
                    (no confundir con historial_cambios_diagrama, que es
                    específico de cambios dentro de un diagrama).

Registra lo esencial: quién, qué, cuándo y sobre qué recurso.

Alineado 1:1 con el script SQL (módulo de Auditoría).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BitacoraSistema(Base):
    __tablename__ = "bitacora_sistema"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Quién generó el evento (NULL si lo disparó el propio sistema).
    id_usuario: Mapped[Optional[int]] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 'LOGIN','PROYECTO_CREADO','GENERACION_COMPLETADA', etc.
    tipo_evento: Mapped[str] = mapped_column(String(50), nullable=False)

    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)

    # 'PROYECTO','DIAGRAMA','TRABAJO_GENERACION' (opcional).
    entidad_afectada: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )

    # id del recurso relacionado (opcional). Polimórfico, sin FK.
    id_entidad_afectada: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    usuario: Mapped[Optional["Usuario"]] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    def __repr__(self) -> str:
        return (
            f"<BitacoraSistema id={self.id} tipo={self.tipo_evento!r} "
            f"usuario={self.id_usuario}>"
        )