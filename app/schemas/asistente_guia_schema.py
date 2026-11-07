# app/schemas/asistente_guia_schema.py
"""
Esquemas del Asistente Guía del Ciclo 2 (CU23): el "paseante" del
documento de diseño — ayuda al usuario a orientarse en la herramienta
con preguntas SOLO DE LECTURA sobre el proyecto/diagrama.

ARCHIVO NUEVO del Ciclo 2: en el Ciclo 1 no existía este rol (el módulo
G era un único "IA Asistente" que mezclaba todo). Diferencias con el
Agente Dev (agente_schema.py):
- NO propone acciones sobre el diagrama y NO toca el lienzo: responde
  texto y sugerencias de navegación; si el usuario pide un cambio, la
  respuesta lo invita a usar el canal del Agente Dev (CU16/CU18).
- Usa el motor liviano (llama3.2:3b, sección IA_* del config) y el mismo
  canal de mensajes: la pregunta entra como MensajeChat (rol USUARIO) y
  la respuesta se persiste como MensajeChat (rol ASISTENTE, modelo
  registrado) — por eso PreguntaGuiaRequest comparte los campos de
  contexto con MensajeChatCreate.
"""

from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field


# ======================================================================
# DTOs específicos de operación — Asistente Guía (CU23)
# ======================================================================
class PreguntaGuiaRequest(BaseModel):
    """
    Pregunta del usuario al Asistente Guía. id_proyecto/id_diagrama son
    opcionales: la guía también atiende dudas generales de la
    herramienta (p. ej. "¿cómo exporto a XMI?") sin diagrama abierto.
    """

    texto_pregunta: str = Field(..., min_length=1, max_length=4000)
    id_proyecto: Optional[PydanticObjectId] = None
    id_diagrama: Optional[PydanticObjectId] = None


class RespuestaGuiaResponse(BaseModel):
    """
    Respuesta de la guía: texto en lenguaje natural + sugerencias de
    navegación (secciones/acciones que puede intentar el usuario). No
    lleva acciones: si el usuario quiere un cambio real, la respuesta lo
    deriva al Agente Dev.
    """

    # Mensaje ASISTENTE persistido en mensajes_chat (para la conversación).
    id_mensaje: Optional[PydanticObjectId] = None
    texto_respuesta: str = Field(..., min_length=1)
    sugerencias: list[str] = Field(default_factory=list)
    # Motor que respondió ('llama3.2:3b' o respaldo) para comparar calidad.
    modelo: Optional[str] = None