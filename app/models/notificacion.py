# app/models/notificacion.py
"""
Documentos del módulo I. Notificaciones — CICLO 2.

- Notificacion → notificaciones para el usuario (alguien comentó, cambió el
                 diagrama, terminó la generación de código, etc.) —
                 colección "notificaciones".

Alineado 1:1 con el script SQL (módulo I).

Cambios respecto al Ciclo 1 (tabla PostgreSQL → documento MongoDB):
- La FK id_usuario (INT) → PydanticObjectId con índice.
- id_referencia (BIGINT polimórfico, sin FK) → Optional[str]: guarda el
  str(id) de un Document (diagrama, trabajo de generación, comentario…) o
  el id uuid de un elemento embebido, según `tipo`. En MongoDB no hay FKs
  que romper: la referencia se resuelve en el servicio según el tipo.
- La relationship usuario desaparece: se resuelve con
  Usuario.get(self.id_usuario).
"""

from datetime import datetime, timezone
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


# ======================================================================
# Notificacion
# ======================================================================
class Notificacion(Document):
    """Notificación para un usuario (colección "notificaciones")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla notificaciones)
    # ------------------------------------------------------------------
    # Destinatario de la notificación.
    id_usuario: PydanticObjectId

    # 'COMENTARIO', 'CAMBIO_DIAGRAMA', 'GENERACION_COMPLETA', etc.
    tipo: str

    mensaje: str

    # id del recurso relacionado (diagrama, comentario, trabajo_generacion…).
    # Es polimórfica: NO lleva FK porque puede apuntar a distintas
    # colecciones según `tipo`. Antes BIGINT; ahora str (ObjectId o uuid).
    id_referencia: Optional[str] = None

    leida: bool = False

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "notificaciones"  # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_usuario"]

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