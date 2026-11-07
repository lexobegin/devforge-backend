# app/models/contexto_ia.py
"""
Documento: contextos_ia (módulo G. IA del Ciclo 2, parte 2) — CICLO 2.

Contexto armado y enviado al modelo local en cada turno de chat/acción
(CU17, contexto persistente): resumen del diagrama, ventana del historial
recortada, elementos seleccionados e instrucciones de sistema.

NUEVO en el Ciclo 2: esta colección NO existe en el script SQL del Ciclo 1
(sustituye a la parte de "contexto" de la tabla interacciones_ia).

Por qué persistir el contexto enviado:
- depurar por qué la IA "no vio" un elemento (se quedó fuera de la ventana),
- medir el tamaño de lo enviado a cada motor (qwen2.5:7b admite más contexto
  que llama3.2:3b) y ajustar la ventana por motor,
- rearmar el mismo contexto tras una caída sin recalcular el embedding
  (OLLAMA_MODEL_EMBEDDINGS = nomic-embed-text).

Decisiones de diseño (Colección nueva, sin CHECK en el SQL origen):
- contenido conserva formato libre (antes JSONB): el ensamblador del
  contexto evoluciona sin migraciones.
- num_mensajes y num_tokens cuantifican la ventana enviada.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from beanie import Document, PydanticObjectId
from pydantic import Field


# ======================================================================
# ContextoIA
# ======================================================================
class ContextoIA(Document):
    """Contexto enviado al modelo local en un turno (colección
    "contextos_ia")."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id_usuario: PydanticObjectId

    # None si el turno fue en el chat general (sin diagrama abierto).
    id_diagrama: Optional[PydanticObjectId] = None

    # Motor al que se le entregó el contexto ('qwen2.5:7b',
    # 'llama3.2:3b' o respaldo).
    modelo: str

    # Contexto armado: resumen del diagrama, historial incluido,
    # elementos seleccionados, instrucciones de sistema…
    contenido: dict[str, Any]

    # Cuántos mensajes de historial se incluyeron (ventana del chat).
    num_mensajes: int = 0

    # Tamaño estimado del contexto en tokens (para ajustar la ventana).
    num_tokens: Optional[int] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "contextos_ia"  # colección nueva del Ciclo 2 (antes no existía)
        indexes = ["id_usuario", "id_diagrama"]

    def __repr__(self) -> str:
        return (
            f"<ContextoIA id={self.id} modelo={self.modelo!r} "
            f"mensajes={self.num_mensajes} tokens={self.num_tokens}>"
        )