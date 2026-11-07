# app/services/canal_service.py
"""
Lógica del CANAL DE ENTRADA de la IA (módulo G, CU16) — CICLO 2.

ARCHIVO NUEVO del Ciclo 2 (no existe en el Ciclo 1): la tabla
`interacciones_ia` del Ciclo 1 mezclaba mensaje, contexto y acción; el
rediseño del módulo G separa la CONVERSACIÓN (colección mensajes_chat) y
el CONTEXTO (contextos_ia, gestor_contexto_service). Este service es la
PUERTA del chat: recibe el prompt (TEXTO o VOZ ya transcrito), persiste
los mensajes del usuario y de la IA, y deriva cada turno al destino que
corresponda:

- id_diagrama presente  → AGENTE DEV (orquestador_agente_service, CU18,
  Tanda 16): el turno llega con el contexto armado por el gestor (CU17)
  y vuelve con acciones propuestas SIN aplicar (ninguna acción se aplica
  sola: el usuario confirma por ids de AccionIA).
- id_diagrama ausente   → CHAT GENERAL: el propio canal habla con la
  cadena de proveedores (conmutación por IAIndisponibleError, mismo
  patrón de ServicioEmbeddings) usando el prompt SISTEMA_CHAT_GENERAL.
  No propone acciones (acciones_propuestas=[] y requiere_confirmacion=
  False en la RespuestaIA).
- PreguntaGuiaRequest   → ASISTENTE GUÍA (asistente_guia_service, CU23,
  Tanda 17): solo lectura, devuelve texto + sugerencias.

Decisiones de diseño:
- EL CANAL ES EL DUEÑO DE mensajes_chat: TODA escritura de la
  conversación (USUARIO y ASISTENTE) pasa por aquí, también en los turnos
  del agente y de la guía — los services destino solo hablan con motores
  y con sus propias colecciones (acciones_ia en T16).
- El mensaje USUARIO se persiste ANTES de llamar al motor y la respuesta
  ASISTENTE se persiste con el modelo que REALMENTE respondió
  (RespuestaProveedorIA / contrato T16-T17): si la IA falla, la
  conversación queda intacta y el turno se puede reintentar.
- El contexto se arma ANTES de persistir el mensaje del usuario (el
  gestor lee la ventana del historial): así el mensaje nuevo no puede
  aparecer duplicado dentro de su propia ventana. Por eso el
  id_mensaje_origen se entrega al orquestador/guía después de armar.
- id_proyecto del mensaje: PromptIARequest no lo trae; con id_diagrama se
  DERIVA del diagrama (gestor.preparar_* lo valida y lo devuelve en
  TurnoContexto). En la guía se respeta el id_proyecto del request solo
  si no hay diagrama.
- origen del mensaje ASISTENTE es siempre "TEXTO" (origen describe por
  dónde entró el mensaje del usuario; la respuesta de la IA es texto).
- VOZ: transcribir_audio() delega en ServicioTranscripcion (faster-whisper
  local, sección VOZ_* del config) y mapea la dataclass Transcripcion al
  esquema TranscripcionVozResponse. El texto salido de la transcripción
  viaja después como PromptIARequest(origen="VOZ").
- ERRORES DE LA CAPA IA: ErrorIA e IAIndisponibleError se PROPAGAN tal
  cual (contrato del módulo G); el mapeo HTTP (503/502) se registra en
  main.py junto a los routers (Tanda 19).
- DERIVACIÓN con import DIFERIDO: orquestador (T16) y guía (T17) se
  importan dentro de los métodos — igual que construir_cadena() importa
  a sus proveedores — para no crear dependencias circulares con services
  que a su vez consumen el gestor de contexto. Contrato esperado:
    orquestador.procesar_turno(id_usuario=, id_diagrama=, mensajes=,
        id_mensaje_origen=) → objeto con texto_respuesta,
        acciones_propuestas, modelo, requiere_confirmacion
    guia.responder(id_usuario=, mensajes=, id_mensaje_origen=)
        → objeto con texto_respuesta, sugerencias, modelo
- SIN ESTADO, con costuras de PRUEBA (`gestor`, `transcriptor`, `cadena`
  inyectables); en producción se omiten y se construye todo real.
"""

from typing import List, Optional, Sequence

from beanie import PydanticObjectId

from app.core.exceptions import ForbiddenError, NotFoundError
from app.ia.llm_provider import (
    IAIndisponibleError,
    LlmProvider,
    RespuestaProveedorIA,
    construir_cadena,
)
from app.ia.transcriptor_voz import ServicioTranscripcion
from app.models.mensaje_chat import MensajeChat
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.mensaje_chat_repository import MensajeChatRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.agente_schema import RespuestaIA
from app.schemas.asistente_guia_schema import (
    PreguntaGuiaRequest,
    RespuestaGuiaResponse,
)
from app.schemas.canal_schema import (
    MensajeChatResponse,
    PromptIARequest,
    TranscripcionVozResponse,
)
from app.services.gestor_contexto_service import GestorContextoService

# Tope de lectura para armar el chat general en memoria (misma razón que
# LIMITE_LECTURA_GENERAL del gestor: el repo no filtra id_diagrama=None).
LIMITE_CHAT_GENERAL = 200


# ======================================================================
# CanalService
# ======================================================================
class CanalService:
    """Puerta de entrada del chat con la IA (CU16): voz, mensajes y
    derivación al Agente Dev, al chat general o al Asistente Guía."""

    def __init__(
        self,
        gestor: Optional[GestorContextoService] = None,
        transcriptor: Optional[ServicioTranscripcion] = None,
        cadena: Optional[List[LlmProvider]] = None,
    ) -> None:
        """
        Costuras de PRUEBA: `gestor`, `transcriptor` y `cadena` permiten
        inyectar dobles en el arnés; en producción se omiten y se
        construyen las piezas reales (GestorContextoService,
        ServicioTranscripcion y construir_cadena()).
        """
        self.mensajes = MensajeChatRepository()
        self.diagramas = DiagramaRepository()
        self.miembros = MiembroProyectoRepository()
        self.gestor = gestor or GestorContextoService()
        self.transcriptor = transcriptor or ServicioTranscripcion()
        self._cadena_inyectada = cadena

    # ==================================================================
    # VOZ (CU16): audio → texto local
    # ==================================================================
    async def transcribir_audio(self, bytes_audio: bytes) -> TranscripcionVozResponse:
        """
        Transcribe audio con faster-whisper (LOCAL). El frontend muestra
        el texto editable y lo envía como PromptIARequest(origen="VOZ").
        Los errores de la capa IA (ErrorIA: voz deshabilitada, librería
        ausente, audio vacío/silencio) se propagan tal cual.
        """
        transcripcion = await self.transcriptor.transcribir(bytes_audio)
        return TranscripcionVozResponse(
            texto_transcrito=transcripcion.texto,
            motor=transcripcion.motor,
            idioma_detectado=transcripcion.idioma_detectado,
            duracion_audio_seg=transcripcion.duracion_audio_seg,
            tiempo_transcripcion_seg=transcripcion.tiempo_procesamiento_seg,
        )

    # ==================================================================
    # ENTRADA DEL CANAL (CU16)
    # ==================================================================
    async def procesar_prompt(
        self,
        usuario_id: PydanticObjectId,
        datos: PromptIARequest,
    ) -> RespuestaIA:
        """
        Punto de entrada del prompt de voz/texto (PromptIARequest):
        deriva al AGENTE DEV si el prompt llega con id_diagrama, o al
        CHAT GENERAL si no. La respuesta NUNCA trae acciones aplicadas.
        """
        if datos.id_diagrama is not None:
            return await self._procesar_turno_agente(usuario_id, datos)
        return await self._procesar_chat_general(usuario_id, datos)

    async def procesar_pregunta_guia(
        self,
        usuario_id: PydanticObjectId,
        datos: PreguntaGuiaRequest,
    ) -> RespuestaGuiaResponse:
        """
        Canal del ASISTENTE GUÍA (CU16 → CU23, solo lectura). La pregunta
        entra como MensajeChat (rol USUARIO) y la respuesta se persiste
        como MensajeChat (rol ASISTENTE, modelo registrado).
        """
        if datos.id_diagrama is not None:
            turno = await self.gestor.preparar_turno_guia(
                usuario_id,
                datos.texto_pregunta,
                id_diagrama=datos.id_diagrama,
            )
            id_proyecto = turno.id_proyecto
        else:
            turno = await self.gestor.preparar_turno_guia(
                usuario_id,
                datos.texto_pregunta,
                id_proyecto=datos.id_proyecto,
            )
            id_proyecto = datos.id_proyecto

        mensaje_usuario = await self._crear_mensaje(
            usuario_id,
            datos.texto_pregunta,
            origen="TEXTO",
            id_proyecto=id_proyecto,
            id_diagrama=datos.id_diagrama,
            rol="USUARIO",
        )

        # Import DIFERIDO: asistente_guia_service llega en la Tanda 17.
        from app.services.asistente_guia_service import AsistenteGuiaService

        resultado = await AsistenteGuiaService().responder(
            id_usuario=usuario_id,
            mensajes=turno.mensajes,
            id_mensaje_origen=mensaje_usuario.id,
        )

        mensaje_asistente = await self._crear_mensaje(
            usuario_id,
            resultado.texto_respuesta,
            origen="TEXTO",
            id_proyecto=id_proyecto,
            id_diagrama=datos.id_diagrama,
            rol="ASISTENTE",
            modelo=resultado.modelo,
        )
        return RespuestaGuiaResponse(
            id_mensaje=mensaje_asistente.id,
            texto_respuesta=resultado.texto_respuesta,
            sugerencias=list(resultado.sugerencias),
            modelo=resultado.modelo,
        )

    # ==================================================================
    # LECTURAS DE LA CONVERSACIÓN
    # ==================================================================
    async def listar_historial(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[MensajeChatResponse]:
        """
        Historial del chat de un diagrama (miembros del proyecto), el más
        nuevo primero (mismo orden que devuelven los repositorios).
        """
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro_lectura(diagrama.id_proyecto, usuario_id)
        items = await self.mensajes.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )
        return [MensajeChatResponse.model_validate(m) for m in items]

    async def listar_chat_general(
        self,
        usuario_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[MensajeChatResponse]:
        """
        Mensajes del chat GENERAL del usuario (sin diagrama). El
        repositorio no tiene el filtro id_diagrama IS NULL (capa cerrada
        en la Tanda 10): se filtra en memoria sobre una lectura acotada
        (LIMITE_CHAT_GENERAL).
        """
        leidos = await self.mensajes.list_by_usuario(
            usuario_id, skip=0, limit=LIMITE_CHAT_GENERAL
        )
        generales = [m for m in leidos if m.id_diagrama is None]
        return [
            MensajeChatResponse.model_validate(m)
            for m in generales[skip : skip + limit]
        ]

    async def obtener_mensaje(
        self,
        mensaje_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> MensajeChatResponse:
        """Devuelve un mensaje del chat (solo su dueño)."""
        mensaje = await self.mensajes.get_by_id(mensaje_id)
        if mensaje is None:
            raise NotFoundError("Mensaje no encontrado")
        if mensaje.id_usuario != usuario_id:
            raise ForbiddenError(
                "No puede consultar mensajes de otro usuario"
            )
        return MensajeChatResponse.model_validate(mensaje)

    # ==================================================================
    # HELPERS INTERNOS
    # ==================================================================
    async def _procesar_turno_agente(
        self,
        usuario_id: PydanticObjectId,
        datos: PromptIARequest,
    ) -> RespuestaIA:
        """Turno del AGENTE DEV (CU16 → CU18) con diagrama abierto."""
        # 1. Contexto CU17 (valida diagrama + membresía y arma mensajes).
        turno = await self.gestor.preparar_turno_agente(
            usuario_id,
            datos.id_diagrama,
            datos.texto_prompt,
            seleccion=datos.contexto,
        )
        # 2. Mensaje USUARIO (persistido ANTES del motor; id_proyecto
        #    derivado del diagrama validado por el gestor).
        mensaje_usuario = await self._crear_mensaje(
            usuario_id,
            datos.texto_prompt,
            origen=datos.origen,
            id_proyecto=turno.id_proyecto,
            id_diagrama=datos.id_diagrama,
            rol="USUARIO",
        )
        # 3. Derivación al orquestador (import DIFERIDO: llega en la
        #    Tanda 16). El orquestador habla con la cadena, parsea el
        #    JSON y crea las AccionIA PROPUESTA (no toca mensajes_chat).
        from app.services.orquestador_agente_service import (
            OrquestadorAgenteService,
        )

        resultado = await OrquestadorAgenteService().procesar_turno(
            id_usuario=usuario_id,
            id_diagrama=datos.id_diagrama,
            mensajes=turno.mensajes,
            id_mensaje_origen=mensaje_usuario.id,
        )
        # 4. Respuesta ASISTENTE con el modelo que REALMENTE respondió.
        mensaje_asistente = await self._crear_mensaje(
            usuario_id,
            resultado.texto_respuesta,
            origen="TEXTO",
            id_proyecto=turno.id_proyecto,
            id_diagrama=datos.id_diagrama,
            rol="ASISTENTE",
            modelo=resultado.modelo,
        )
        return RespuestaIA(
            id_mensaje=mensaje_asistente.id,
            texto_respuesta=resultado.texto_respuesta,
            acciones_propuestas=list(resultado.acciones_propuestas),
            requiere_confirmacion=resultado.requiere_confirmacion,
        )

    async def _procesar_chat_general(
        self,
        usuario_id: PydanticObjectId,
        datos: PromptIARequest,
    ) -> RespuestaIA:
        """
        Turno de CHAT GENERAL (sin diagrama): el canal habla directo con
        la cadena de proveedores (conmutación por IAIndisponibleError) y
        responde SOLO texto, sin acciones.
        """
        turno = await self.gestor.preparar_turno_chat_general(
            usuario_id, datos.texto_prompt
        )
        mensaje_usuario = await self._crear_mensaje(
            usuario_id,
            datos.texto_prompt,
            origen=datos.origen,
            id_proyecto=None,
            id_diagrama=None,
            rol="USUARIO",
        )
        respuesta = await self._generar_chat_general(turno.mensajes)
        mensaje_asistente = await self._crear_mensaje(
            usuario_id,
            respuesta.texto,
            origen="TEXTO",
            id_proyecto=None,
            id_diagrama=None,
            rol="ASISTENTE",
            modelo=respuesta.modelo,
        )
        return RespuestaIA(
            id_mensaje=mensaje_asistente.id,
            texto_respuesta=respuesta.texto,
            acciones_propuestas=[],
            requiere_confirmacion=False,
        )

    async def _generar_chat_general(
        self,
        mensajes: List[dict],
    ) -> RespuestaProveedorIA:
        """
        Conmutación del chat general: recorre la cadena y usa el primer
        proveedor que responda (mismo contrato que ServicioEmbeddings).
        IAIndisponibleError conmuta; ErrorIA NO (responder mal no se
        arregla cambiando de motor) y se propaga.
        """
        cadena = self._cadena_inyectada or construir_cadena()
        ultimo_error: Optional[Exception] = None
        for proveedor in cadena:
            try:
                return await proveedor.generar_chat(
                    mensajes,
                    modelo=proveedor.modelo_para("guia"),
                )
            except IAIndisponibleError as exc:
                ultimo_error = exc  # conmutar: intentar el siguiente
                continue
        raise ultimo_error or IAIndisponibleError(
            "Ningún proveedor IA respondió para el chat general"
        )

    async def _require_miembro_lectura(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> None:
        """Membresía mínima (lectura) para ver el chat del diagrama."""
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            # 404 genérico para no revelar proyectos ajenos (mismo
            # criterio que diagrama_service).
            raise NotFoundError("Recurso no encontrado")

    async def _crear_mensaje(
        self,
        usuario_id: PydanticObjectId,
        contenido: str,
        *,
        origen: str,
        id_proyecto: Optional[PydanticObjectId],
        id_diagrama: Optional[PydanticObjectId],
        rol: str,
        modelo: Optional[str] = None,
    ) -> MensajeChat:
        """Única puerta de escritura de la conversación (mensajes_chat)."""
        mensaje = MensajeChat(
            id_usuario=usuario_id,
            id_proyecto=id_proyecto,
            id_diagrama=id_diagrama,
            rol=rol,
            contenido=contenido,
            origen=origen,
            modelo=modelo,
        )
        return await self.mensajes.create(mensaje)