# app/schemas/ia_schema.py
"""
Esquemas Pydantic del módulo G. IA Asistente (Voz / Texto / Imagen) — CICLO 2.

REDESIGN total respecto al Ciclo 1: la tabla interacciones_ia se RETIRA.
Mezclaba en una sola fila el mensaje, el contexto enviado y la acción
resultante; en el Ciclo 2 son 3 colecciones (app/models):
- MensajeChat  → cada mensaje del chat (usuario/asistente/sistema).
- ContextoIA   → contexto armado y enviado al modelo local en cada turno.
- AccionIA     → acción estructurada que el Agente Dev propone y el
                 ejecutor del backend aplica (CU16-21).

Flujo que estos esquemas soportan:
1. El usuario escribe o habla (VOZ → TranscripcionVozResponse con
   faster-whisper, sección VOZ_* del config) → PromptIARequest.
2. El service arma el contexto (ContextoIA) y consulta Ollama
   (qwen2.5:7b agente / llama3.2:3b guía).
3. El modelo NO toca el lienzo: responde con AccionIAPropuesta
   estructuradas → el service las persiste como AccionIA (estado PROPUESTA)
   y devuelve RespuestaIA.
4. El usuario confirma (ConfirmarAccionIARequest) → el ejecutor valida el
   payload con los *Update de diagrama_schema y aplica sobre los elementos
   embebidos (corrige las deficiencias 1 y 2 del Ciclo 1: cajas vacías).

Cambios de nombres:
- canal: CanalIA → origen: OrigenMensaje (mismo vocabulario que el modelo
  MensajeChat: TEXTO/VOZ).
- AccionIAPropuesta.tipo → tipo_accion (mismo nombre del campo del
  documento y del vocabulario compartido con la cola offline: 'CREAR_CLASE',
  'MODIFICAR_ATRIBUTO', 'ELIMINAR_RELACION', 'GENERAR_CODIGO'…).
- ConfirmarAccionIARequest.id_interaccion + índices → id_mensaje + ids de
  AccionIA: cada acción es ahora su propio documento, no un índice de lista.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables (alineados con app/models/mensaje_chat.py y
# app/models/accion_ia.py)
# ======================================================================
RolMensaje = Literal["USUARIO", "ASISTENTE", "SISTEMA"]

OrigenMensaje = Literal["TEXTO", "VOZ"]

EstadoAccionIA = Literal["PROPUESTA", "APLICADA", "RECHAZADA", "FALLIDA"]


# ======================================================================
# MensajeChat (sustituye a InteraccionIA, parte "mensaje")
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
# ContextoIA (sustituye a InteraccionIA, parte "contexto")
# ======================================================================
class ContextoIAResponse(BaseModel):
    """
    Contexto que el service envió al modelo en un turno (auditoría/depuración:
    por qué la IA "no vio" un elemento, tamaño de la ventana por motor).
    Solo lectura: lo construye el ensamblador de contexto, nunca el cliente.
    """

    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_usuario: PydanticObjectId
    id_diagrama: Optional[PydanticObjectId] = None
    modelo: str
    contenido: dict[str, Any]
    num_mensajes: int
    num_tokens: Optional[int] = None
    created_at: datetime


# ======================================================================
# AccionIA (sustituye a InteraccionIA, parte "acción")
# ======================================================================
class AccionIAPropuesta(BaseModel):
    """
    Acción estructurada que la IA propone ejecutar sobre el diagrama.
    El LLM no toca el lienzo: el backend valida el payload con los *Update
    de diagrama_schema antes de aplicarlo.
    Ejemplo:
        {"tipo_accion": "CREAR_CLASE", "payload": {"nombre": "Paciente",
         "atributos": [{"nombre": "ci", "tipo_dato": "str"}]}}
    """

    tipo_accion: str = Field(
        ...,
        max_length=50,
        description=(
            "Mismo vocabulario que tipo_operacion de la cola offline: "
            "'CREAR_CLASE','MODIFICAR_ATRIBUTO','ELIMINAR_RELACION',…"
        ),
    )
    payload: dict[str, Any] = Field(default_factory=dict)
    descripcion: Optional[str] = Field(None, max_length=255)


class AccionIAResponse(BaseModel):
    """Acción persistida con su ciclo de vida (PROPUESTA→APLICADA/…)."""

    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_usuario: PydanticObjectId
    id_diagrama: Optional[PydanticObjectId] = None
    # Mensaje del chat que originó la acción; None si el disparo fue otra
    # vía (boceto, botón de generación…).
    id_mensaje: Optional[PydanticObjectId] = None
    tipo_accion: str
    payload: dict[str, Any]
    estado: EstadoAccionIA
    detalle_resultado: Optional[str] = None
    created_at: datetime
    aplicada_at: Optional[datetime] = None


# ======================================================================
# DTOs específicos de operación — IA por voz/texto
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


class RespuestaIA(BaseModel):
    """
    Respuesta del servicio de IA antes de aplicar cambios al diagrama.
    El cliente decide si confirma las acciones propuestas
    (ConfirmarAccionIARequest); ninguna acción se aplica sola.
    """

    # Mensaje ASISTENTE creado en mensajes_chat (para encadenar la conversación).
    id_mensaje: Optional[PydanticObjectId] = None
    texto_respuesta: str = Field(..., description="Respuesta en lenguaje natural")
    acciones_propuestas: list[AccionIAPropuesta] = Field(default_factory=list)
    requiere_confirmacion: bool = Field(default=True)


class ConfirmarAccionIARequest(BaseModel):
    """
    Confirmación explícita de acciones propuestas por la IA.
    En el Ciclo 1 se confirmaban por ÍNDICE dentro de la interacción;
    ahora cada acción es un documento AccionIA y se confirman por id.
    """

    # Mensaje que originó las propuestas (para trazar la cadena completa).
    id_mensaje: PydanticObjectId
    acciones_a_aplicar: list[PydanticObjectId] = Field(
        default_factory=list,
        description="Ids de las AccionIA (estado PROPUESTA) a aplicar",
    )


# ======================================================================
# DTOs específicos de operación — IA de visión (boceto/imagen)
# ======================================================================
class VisionReconocimientoResponse(BaseModel):
    """
    Resultado del reconocimiento de un boceto/imagen de diagrama.
    El cliente recibe un diagrama reconstruido listo para insertar.
    En el Ciclo 2 el reconocedor produce ClaseUMLCreate completos (atributos,
    operaciones y RelacionUMLCreate), no cajas vacías (deficiencia 1 del
    Ciclo 1): diagrama_reconstruido sigue el mismo formato que
    DiagramaCompletoResponse y se puede validar con los esquemas del módulo C.
    """

    exito: bool = True
    confianza: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confianza global del reconocimiento"
    )
    diagrama_reconstruido: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Estructura reconstruida: clases, atributos, operaciones y "
            "relaciones. Mismo formato que DiagramaCompletoResponse."
        ),
    )
    advertencias: list[str] = Field(default_factory=list)
    imagen_procesada_url: Optional[str] = None