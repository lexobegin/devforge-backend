# app/models/sincronizacion.py
"""
Modelo ORM del módulo H. Sincronización Móvil/Web Offline:

- ColaSincronizacionMovil → cola de cambios hechos sin conexión (móvil o web),
                            pendientes de sincronizar cuando se recupera la red.

Alineado 1:1 con el script SQL (módulo H).

Nota: aunque la tabla se llame "cola_sincronizacion_movil" (nombre original del
script), la usan tanto la app móvil Flutter como el frontend web offline. El
campo `id_dispositivo` es genérico: puede ser un deviceId móvil o un id de
navegador persistido en IndexedDB.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ColaSincronizacionMovil(Base):
    __tablename__ = "cola_sincronizacion_movil"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('PENDIENTE','SINCRONIZADO','CONFLICTO')",
            name="ck_cola_sync_estado",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Identificador del dispositivo/navegador que originó el cambio offline.
    id_dispositivo: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Puede ser NULL si el cambio no está atado a un diagrama concreto.
    id_diagrama: Mapped[Optional[int]] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # id generado offline por el dispositivo (se resuelve al sincronizar).
    id_temporal_local: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # 'CREAR_CLASE', 'MODIFICAR_ATRIBUTO', 'ELIMINAR_RELACION', etc.
    tipo_operacion: Mapped[str] = mapped_column(String(20), nullable=False)

    # Datos del cambio realizado offline (estructura libre por tipo_operacion).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    diagrama: Mapped[Optional["Diagrama"]] = relationship(  # noqa: F821
        "Diagrama",
        foreign_keys=[id_diagrama],
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def esta_pendiente(self) -> bool:
        return self.estado == "PENDIENTE"

    @property
    def tiene_conflicto(self) -> bool:
        return self.estado == "CONFLICTO"

    def __repr__(self) -> str:
        return (
            f"<ColaSincronizacionMovil id={self.id} dispositivo={self.id_dispositivo!r} "
            f"op={self.tipo_operacion!r} estado={self.estado!r}>"
        )