# app/models/auditoria.py
"""
Documentos del módulo de Auditoría — CICLO 2.

- BitacoraSistema → bitácora general de eventos relevantes del sistema
                    (no confundir con historial_cambios_diagrama, que es
                    específico de cambios dentro de un diagrama) —
                    colección "bitacora_sistema".

Registra lo esencial: quién, qué, cuándo y sobre qué recurso.

Alineado 1:1 con el script SQL (módulo de Auditoría).

Cambios respecto al Ciclo 1 (tabla PostgreSQL → documento MongoDB):
- id_usuario (FK con ondelete SET NULL) → Optional[PydanticObjectId]: None
  significa que el evento lo disparó el propio sistema (mismo significado
  que el NULL del Ciclo 1, sin ON DELETE: en MongoDB no hay cascadas).
- id_entidad_afectada (BIGINT polimórfico, sin FK) → Optional[str]: str(id)
  de un Document o id uuid de un elemento embebido, según
  `entidad_afectada`.
- La relationship usuario desaparece.
"""

from datetime import datetime, timezone
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


# ======================================================================
# BitacoraSistema
# ======================================================================
class BitacoraSistema(Document):
    """Evento general del sistema (colección "bitacora_sistema")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla bitacora_sistema)
    # ------------------------------------------------------------------
    # Quién generó el evento (None si lo disparó el propio sistema).
    id_usuario: Optional[PydanticObjectId] = None

    # 'LOGIN', 'PROYECTO_CREADO', 'GENERACION_COMPLETADA', etc.
    tipo_evento: str

    descripcion: str

    # 'PROYECTO', 'DIAGRAMA', 'TRABAJO_GENERACION' (opcional).
    entidad_afectada: Optional[str] = None

    # id del recurso relacionado (opcional). Polimórfico, sin FK.
    id_entidad_afectada: Optional[str] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "bitacora_sistema"  # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_usuario"]

    def __repr__(self) -> str:
        return (
            f"<BitacoraSistema id={self.id} tipo={self.tipo_evento!r} "
            f"usuario={self.id_usuario}>"
        )