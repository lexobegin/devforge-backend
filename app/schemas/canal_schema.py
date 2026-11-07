# app/schemas/canal_schema.py
"""
Esquemas del canal de entrada del Ciclo 2 (CU16): mensajes de TEXTO y de
VOZ entre el usuario y la IA — la puerta de entrada del Agente Dev
(CU18-CU21) y del Asistente Guía (CU23).

ARCHIVO NUEVO del Ciclo 2: estos esquemas vivían en ia_schema.py del
Ciclo 1 (módulo "IA Asistente" único); con el rediseño del módulo G
(3 colecciones: mensajes_chat / contextos_ia / acciones_ia) el archivo se
divide, y el canal queda con lo suyo:
- MensajeChat*   → la conversación (entrada y salida del canal).
- TranscripcionVozResponse → audio → texto con faster-whisper local
  (sección VOZ_* del config); NUEVO del Ciclo 2.
- PromptIARequest → el mensaje de entrada que canal_service recibe y
  deriva al orquestador del Agente Dev o al Asistente Guía.

Lo que el canal DEVUELVE (respuesta con acciones) vive en
agente_schema.py (RespuestaIA del orquestador); el Asistente Guía
responde con RespuestaGuiaResponse (asistente_guia_schema.py).
"""

from datetime import datetime
from typing import Any, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables (idénticos a app/models/mensaje_chat.py)
# ======================================================================
RolMensaje = Literal["USUARIO", "ASISTENTE", "SISTEMA"]

OrigenMensaje = Literal["TEXTO", "VOZ"]


# ======================================================================
# MensajeChat (antes parte "mensaje" de InteraccionIA)
# ======================================================================
class MensajeChatCreate(BaseModel):
    """
    Mensaje que el usuario envía al chat (texto o transcript de voz).
    El rol es siempre USUARIO: los mensajes ASISTENTE/SISTEMA los crean los
    services internamente. id_proyecto/id_diagrama son opcionales: también
    existe chat general sin diagrama abierto.
    """

    contenido: str = Field(..., min_length=1, max_length=4000)
    origen: OrigenMensaje = Field(
        default="TEXTO",
        description="VOZ si el texto viene de la transcripción con faster-whisper",
    )
    id_proyecto: Optional[PydanticObjectId] = None
    id_diagrama: Optional[PydanticObjectId] = None


class MensajeChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (colección nueva, sin int)
    id_usuario: PydanticObjectId
    id_proyecto: Optional[PydanticObjectId] = None
    id_diagrama: Optional[PydanticObjectId] = None
    rol: RolMensaje
    contenido: str
    origen: OrigenMensaje
    # Motor que respondió ('qwen2.5:7b', 'llama3.2:3b'…); None en mensajes
    # del usuario o del sistema.
    modelo: Optional[str] = None
    created_at: datetime


# ======================================================================
# Voz: audio → texto local (faster-whisper)
# ======================================================================
class TranscripcionVozResponse(BaseModel):
    """
    Resultado de transcribir un audio con faster-whisper (local, sección
    VOZ_* del config). El frontend/móvil lo muestra editable antes de
    enviar el texto como PromptIARequest (origen=VOZ).
    NUEVO en el Ciclo 2: en el Ciclo 1 la transcripción era online y no se
    exponía como esquema.
    """

    texto_transcrito: str = Field(..., min_length=1, max_length=4000)
    motor: str = Field(
        default="faster-whisper",
        description="Modelo local usado (VOZ_MODELO del config)",
    )
    idioma_detectado: Optional[str] = Field(
        None, max_length=10, description="ej. 'es', 'en'"
    )
    duracion_audio_seg: Optional[float] = Field(None, ge=0)
    tiempo_transcripcion_seg: Optional[float] = Field(
        None, ge=0, description="Costo de procesamiento local (referencia)"
    )


# ======================================================================
# Entrada del canal (canal_service la deriva al orquestador o a la guía)
# ======================================================================
class PromptIARequest(BaseModel):
    """
    Payload para enviar un prompt de voz/texto al servicio de IA.
    Si el prompt vino por voz, la transcripción (faster-whisper) ya se
    resolvió y llega como texto con origen='VOZ'.
    """

    texto_prompt: str = Field(..., min_length=1, max_length=4000)
    origen: OrigenMensaje = Field(default="TEXTO")
    id_diagrama: Optional[PydanticObjectId] = Field(
        None,
        description="Si se especifica, la IA opera sobre ese diagrama",
    )
    contexto: Optional[dict[str, Any]] = Field(
        None,
        description="Contexto adicional (selección actual, clases existentes, etc.)",
    )