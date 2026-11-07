# app/models/mensaje_chat.py
"""
Documento: mensajes_chat (módulo G. IA del Ciclo 2, parte 1) — CICLO 2.

Mensaje individual del chat entre el usuario y la IA: canal de entrada del
Agente Dev (CU16-CU21) y del Asistente Guía (CU23).

NUEVO en el Ciclo 2: esta colección NO existe en el script SQL del Ciclo 1.
Junto a contextos_ia y acciones_ia sustituye a la tabla interacciones_ia del
Ciclo 1, que mezclaba en una sola fila el mensaje, el contexto enviado y la
acción resultante. Separarlos permite:
- reconstruir la conversación completa (mensajes_chat),
- auditar qué contexto recibió el modelo en cada turno (contextos_ia),
- seguir el ciclo de vida de cada acción del agente (acciones_ia).

Decisiones de diseño (Colección nueva, sin CHECK en el SQL origen):
- rol distingue quién escribe: USUARIO, ASISTENTE o SISTEMA (avisos del
  propio DevForge, p. ej. cuando Ollama no responde y se usa un respaldo).
- origen registra por dónde entró el mensaje del usuario: TEXTO o VOZ
  (transcripción local con faster-whisper, sección VOZ_* del config).
- modelo guarda qué motor respondió ('qwen2.5:7b' para el Agente Dev,
  'llama3.2:3b' para el Asistente Guía, o un respaldo), para comparar
  calidad entre motores.
- id_proyecto / id_diagrama son OPCIONALES: existe chat general del
  usuario además del chat atado a un diagrama concreto.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from beanie import Document, PydanticObjectId
from pydantic import Field

# Literales de la colección nueva (equivalen a CHECK que no existió en el SQL)
RolMensaje = Literal["USUARIO", "ASISTENTE", "SISTEMA"]
OrigenMensaje = Literal["TEXTO", "VOZ"]


# ======================================================================
# MensajeChat
# ======================================================================
class MensajeChat(Document):
    """Mensaje del chat con la IA (colección "mensajes_chat")."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id_usuario: PydanticObjectId

    # Contexto de la conversación (opcionales: también hay chat general)
    id_proyecto: Optional[PydanticObjectId] = None

    id_diagrama: Optional[PydanticObjectId] = None

    rol: RolMensaje

    # Texto del mensaje; en origen VOZ es el transcript de faster-whisper.
    contenido: str

    origen: OrigenMensaje = "TEXTO"

    # Motor que respondió ('qwen2.5:7b', 'llama3.2:3b' o respaldo);
    # None en mensajes del usuario o del sistema.
    modelo: Optional[str] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "mensajes_chat"  # colección nueva del Ciclo 2 (antes no existía)
        indexes = ["id_usuario", "id_diagrama"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def es_del_usuario(self) -> bool:
        return self.rol == "USUARIO"

    def __repr__(self) -> str:
        return (
            f"<MensajeChat id={self.id} rol={self.rol!r} "
            f"origen={self.origen!r} modelo={self.modelo!r}>"
        )