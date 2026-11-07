# app/services/gestor_contexto_service.py
"""
Lógica del GESTOR DE CONTEXTO de la IA (módulo G, CU17) — CICLO 2.

ARCHIVO NUEVO del Ciclo 2 (no existe en el Ciclo 1): en el Ciclo 1 la
tabla `interacciones_ia` guardaba un "contexto" plano por interacción y
el historial se recortaba a mano. En el Ciclo 2 este service es el
ENSAMBLADOR del contexto que se envía al modelo en cada turno:

1. RESUMEN DEL DIAGRAMA: lee el lienzo EMBEBIDO del DiagramaDocument
   (clases → atributos → operaciones, relaciones) y lo aplana a un dict
   con los ids uuid REALES de cada elemento (la regla del Agente Dev:
   "NUNCA inventes ids" funciona porque el modelo SÍ los recibe).
2. VENTANA DEL HISTORIAL: los últimos N mensajes del chat del diagrama
   en ORDEN CRONOLÓGICO (MensajeChatRepository.list_historial_by_diagrama).
3. RECUPERACIÓN SEMÁNTICA (contexto persistente): los mensajes más viejos
   que la ventana se incrustan con ServicioEmbeddings
   (OLLAMA_MODEL_EMBEDDINGS = nomic-embed-text) y
   recuperar_relevantes() devuelve los k más cercanos a la consulta del
   turno; se anteponen a la ventana conservando su orden cronológico real.
4. ENSAMBLADO: delega en app.ia.prompts (mensajes_agente_dev /
   mensajes_asistente_guia / mensajes_chat_general) el formato canónico
   OpenAI [{role, content}] listo para LlmProvider.generar_chat().
5. PERSISTENCIA Y AUDITORÍA: guarda un documento ContextoIA por turno
   (colección "contextos_ia"): qué resumen se envió, qué mensajes entraron
   a la ventana, cuáles se recuperaron por similitud, el motor solicitado
   y el tamaño estimado en tokens. Es la bitácora para depurar por qué la
   IA "no vio" un elemento y para ajustar la ventana por motor.

Decisiones de diseño:
- VENTANA POR MOTOR: qwen2.5:7b admite más contexto que llama3.2:3b, así
  que el tamaño de la ventana se elige comparando el modelo solicitado
  contra settings.OLLAMA_MODEL_TEXT / OLLAMA_MODEL_LIGERO
  (tam_ventana_para). Los respaldos usan la ventana por defecto.
- DEGRADACIÓN controlada: si TODA la cadena de embeddings está caída
  (IAIndisponibleError) u otra ErrorIA sale de la capa IA, el turno NO
  falla: se arma el contexto solo con la ventana inmediata y la causa
  queda registrada en contenido["advertencias"] (la recuperación
  semántica es una mejora, no un requisito, para poder chatear).
- SIMILITUD_MINIMA: los recuperados con similitud por debajo del umbral
  se descartan (con vectores nulos o poco relacionados no se gasta
  espacio de contexto).
- PERMISOS: leer el resumen exige ser MIEMBRO del proyecto del diagrama
  (lectura). Mismo criterio defensivo que diagrama_service: diagrama
  inexistente → "Diagrama no encontrado"; ajeno → "Recurso no encontrado"
  (404, para no revelar existencia).
- El modelo registrado en ContextoIA es el SOLICITADO (el principal de la
  cadena para ese rol); si el orquestador conmuta a un respaldo, el motor
  que realmente respondió queda en MensajeChat.modelo (lo persiste el
  canal con la respuesta).
- SIN ESTADO: los repositorios se crean en __init__ y la conexión la
  lleva Beanie. ServicioEmbeddings es inyectable (`embeddings=...`) como
  costura de prueba; en producción se construye con construir_cadena().
"""

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from beanie import PydanticObjectId

from app.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.ia.embeddings import ServicioEmbeddings
from app.ia.llm_provider import ErrorIA, UsoMotor, construir_cadena
from app.ia.prompts import (
    estimar_tokens,
    mensajes_agente_dev,
    mensajes_asistente_guia,
    mensajes_chat_general,
    rol_a_role,
)
from app.models.contexto_ia import ContextoIA
from app.models.diagrama import Diagrama
from app.models.mensaje_chat import MensajeChat
from app.repositories.contexto_ia_repository import ContextoIARepository
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.mensaje_chat_repository import MensajeChatRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.agente_schema import ContextoIAResponse

# ----------------------------------------------------------------------
# Parámetros de la ventana y de la recuperación semántica (CU17)
# ----------------------------------------------------------------------
VENTANA_AGENTE = 20        # mensajes para el motor grande (qwen2.5:7b)
VENTANA_GUIA = 10          # mensajes para el motor liviano (llama3.2:3b)
VENTANA_DEFAULT = 14       # respaldos / modelo no reconocido
LIMITE_CANDIDATOS = 60     # cuántos mensajes previos a la ventana se consideran
K_RECUPERADOS = 5          # top-k de recuperar_relevantes
SIMILITUD_MINIMA = 0.15    # umbral: debajo de esto el mensaje no aporta
LIMITE_LECTURA_GENERAL = 200  # tope de lectura para armar la ventana general


def tam_ventana_para(modelo: str) -> int:
    """
    Tamaño de la ventana del historial según el motor solicitado
    (ventana por motor, decisión CU17):
    - motor grande (OLLAMA_MODEL_TEXT) → VENTANA_AGENTE,
    - motor liviano (OLLAMA_MODEL_LIGERO) → VENTANA_GUIA,
    - cualquier otro (respaldos) → VENTANA_DEFAULT.
    """
    if modelo == settings.OLLAMA_MODEL_TEXT:
        return VENTANA_AGENTE
    if modelo == settings.OLLAMA_MODEL_LIGERO:
        return VENTANA_GUIA
    return VENTANA_DEFAULT


# ======================================================================
# Resultado de la preparación de un turno
# ======================================================================
@dataclass
class TurnoContexto:
    """
    Todo lo que un turno necesita tras armar el contexto:
    - mensajes: conversación completa en formato canónico OpenAI, lista
      para LlmProvider.generar_chat() (system + historial + petición).
    - modelo: motor solicitado para el turno (el que queda auditado).
    - contexto_id: id del ContextoIA persistido (auditoría/depuración).
    - id_proyecto / resumen: proyecto del diagrama y resumen enviado
      (None en los turnos sin diagrama: guía general y chat general).
    - num_mensajes / num_tokens: tamaño de la ventana incluida y del
      contexto completo estimado (estimar_tokens).
    """

    mensajes: list[dict[str, str]]
    modelo: str
    contexto_id: Optional[PydanticObjectId] = None
    id_proyecto: Optional[PydanticObjectId] = None
    resumen: Optional[dict[str, Any]] = None
    num_mensajes: int = 0
    num_tokens: int = 0


# ======================================================================
# GestorContextoService
# ======================================================================
class GestorContextoService:
    """Ensambla, dimensiona y audita el contexto de cada turno (CU17)."""

    def __init__(
        self,
        embeddings: Optional[ServicioEmbeddings] = None,
    ) -> None:
        """
        `embeddings` es una costura de PRUEBA (inyección del servicio de
        embeddings); en producción se omite y se construye con la cadena
        real de proveedores (construir_cadena()).
        """
        self.contextos = ContextoIARepository()
        self.mensajes = MensajeChatRepository()
        self.diagramas = DiagramaRepository()
        self.miembros = MiembroProyectoRepository()
        if embeddings is None:
            embeddings = ServicioEmbeddings(construir_cadena())
        self.embeddings = embeddings

    # ==================================================================
    # PREPARACIÓN DE TURNOS
    # ==================================================================
    async def preparar_turno_agente(
        self,
        id_usuario: PydanticObjectId,
        id_diagrama: PydanticObjectId,
        texto_usuario: str,
        *,
        seleccion: Optional[dict[str, Any]] = None,
    ) -> TurnoContexto:
        """
        Turno del AGENTE DEV (CU16 → CU18): resumen del diagrama + ventana
        + recuperación semántica, ensamblados con el prompt SISTEMA_AGENTE_
        DEV. `seleccion` es el contexto adicional del cliente (elementos
        seleccionados en el lienzo, etc.).
        """
        nombres_cadena, modelo = self._cadena_y_modelo("agente")
        diagrama = await self._diagrama_para_lectura(id_diagrama, id_usuario)
        resumen = self._resumen_de_diagrama(diagrama)
        ventana, recuperados, puntuaciones, advertencias = (
            await self._historial_de_diagrama(
                id_diagrama, texto_usuario, tam_ventana_para(modelo)
            )
        )
        return await self._armar_y_persistir_turno(
            id_usuario=id_usuario,
            uso="agente",
            prompt_sistema="SISTEMA_AGENTE_DEV",
            texto_turno=texto_usuario,
            modelo=modelo,
            nombres_cadena=nombres_cadena,
            mensajes_historial=list(recuperados) + list(ventana),
            ventana=ventana,
            puntuaciones=puntuaciones,
            resumen=resumen,
            seleccion=seleccion,
            id_diagrama=id_diagrama,
            id_proyecto=diagrama.id_proyecto,
            advertencias=advertencias,
        )

    async def preparar_turno_guia(
        self,
        id_usuario: PydanticObjectId,
        texto_pregunta: str,
        *,
        id_proyecto: Optional[PydanticObjectId] = None,
        id_diagrama: Optional[PydanticObjectId] = None,
    ) -> TurnoContexto:
        """
        Turno del ASISTENTE GUÍA (CU23, solo lectura). Con id_diagrama
        incluye el resumen del lienzo y el historial del chat del diagrama
        (motor liviano); sin diagrama atiende la duda con la ventana del
        chat general del usuario.
        """
        nombres_cadena, modelo = self._cadena_y_modelo("guia")
        resumen: Optional[dict[str, Any]] = None
        id_proyecto_final = id_proyecto
        ventana: list[MensajeChat] = []
        recuperados: list[MensajeChat] = []
        puntuaciones: list[tuple[PydanticObjectId, float]] = []
        advertencias: list[str] = []

        if id_diagrama is not None:
            diagrama = await self._diagrama_para_lectura(id_diagrama, id_usuario)
            resumen = self._resumen_de_diagrama(diagrama)
            id_proyecto_final = diagrama.id_proyecto
            ventana, recuperados, puntuaciones, advertencias = (
                await self._historial_de_diagrama(
                    id_diagrama, texto_pregunta, tam_ventana_para(modelo)
                )
            )
        else:
            ventana = await self._ventana_general(
                id_usuario, tam_ventana_para(modelo)
            )

        return await self._armar_y_persistir_turno(
            id_usuario=id_usuario,
            uso="guia",
            prompt_sistema="SISTEMA_ASISTENTE_GUIA",
            texto_turno=texto_pregunta,
            modelo=modelo,
            nombres_cadena=nombres_cadena,
            mensajes_historial=list(recuperados) + list(ventana),
            ventana=ventana,
            puntuaciones=puntuaciones,
            resumen=resumen,
            seleccion=None,
            id_diagrama=id_diagrama,
            id_proyecto=id_proyecto_final,
            advertencias=advertencias,
        )

    async def preparar_turno_chat_general(
        self,
        id_usuario: PydanticObjectId,
        texto: str,
    ) -> TurnoContexto:
        """
        Turno de CHAT GENERAL (PromptIARequest sin id_diagrama): sin
        resumen ni recuperación semántica; la ventana son los últimos
        mensajes generales del propio usuario.
        DECISIÓN: usa el motor LIVIANO (modelo_para("guia")) — el chat
        general no propone acciones ni edita diagramas, no necesita el
        motor grande.
        """
        nombres_cadena, modelo = self._cadena_y_modelo("guia")
        ventana = await self._ventana_general(
            id_usuario, tam_ventana_para(modelo)
        )
        return await self._armar_y_persistir_turno(
            id_usuario=id_usuario,
            uso="chat_general",
            prompt_sistema="SISTEMA_CHAT_GENERAL",
            texto_turno=texto,
            modelo=modelo,
            nombres_cadena=nombres_cadena,
            mensajes_historial=list(ventana),
            ventana=ventana,
            puntuaciones=[],
            resumen=None,
            seleccion=None,
            id_diagrama=None,
            id_proyecto=None,
            advertencias=[],
        )

    # ==================================================================
    # AUDITORÍA / LECTURA (los esquemas los consume el router en T19)
    # ==================================================================
    async def obtener_contexto(
        self,
        contexto_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> ContextoIAResponse:
        """Devuelve el contexto enviado en un turno (solo su dueño)."""
        contexto = await self.contextos.get_by_id(contexto_id)
        if contexto is None:
            raise NotFoundError("Contexto no encontrado")
        if contexto.id_usuario != usuario_id:
            raise ForbiddenError(
                "No puede consultar contextos de otro usuario"
            )
        return ContextoIAResponse.model_validate(contexto)

    async def listar_por_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ContextoIAResponse]:
        """
        Bitácora de contextos de un diagrama (miembros del proyecto):
        para depurar por qué la IA "no vio" un elemento y comparar el
        tamaño de la ventana entre motores.
        """
        await self._diagrama_para_lectura(diagrama_id, usuario_id)
        items = await self.contextos.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )
        return [ContextoIAResponse.model_validate(c) for c in items]

    # ==================================================================
    # HELPERS INTERNOS
    # ==================================================================
    def _cadena_y_modelo(self, uso: UsoMotor) -> tuple[list[str], str]:
        """
        (nombres de la cadena de conmutación, modelo solicitado para el
        rol). El modelo auditado en ContextoIA es el del PRINCIPAL; el
        motor real que respondió lo registra el canal en MensajeChat.
        """
        cadena = construir_cadena()
        return [p.nombre for p in cadena], cadena[0].modelo_para(uso)

    async def _diagrama_para_lectura(
        self,
        id_diagrama: PydanticObjectId,
        id_usuario: PydanticObjectId,
    ) -> Diagrama:
        """
        Diagrama existente + membresía del proyecto (lectura). Mismo
        criterio defensivo de diagrama_service: ajeno → 404 genérico.
        """
        diagrama = await self.diagramas.get_by_id(id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        miembro = await self.miembros.get_by_proyecto_usuario(
            diagrama.id_proyecto, id_usuario
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        return diagrama

    def _resumen_de_diagrama(self, diagrama: Diagrama) -> dict[str, Any]:
        """
        Lienzo EMBEBIDO → dict plano con los ids uuid reales. Es EXACTO
        el formato que prompts.formatear_resumen_diagrama y el prompt del
        Agente Dev esperan (clases con atributos/operaciones y relaciones
        con origen/destino resueltos por nombre).
        """
        nombres = {c.id: c.nombre for c in diagrama.clases}
        clases = [
            {
                "id": c.id,
                "nombre": c.nombre,
                "es_abstracta": c.es_abstracta,
                "estereotipo": c.estereotipo,
                "pos_x": c.pos_x,
                "pos_y": c.pos_y,
                "atributos": [
                    {
                        "id": a.id,
                        "nombre": a.nombre,
                        "tipo_dato": a.tipo_dato,
                        "visibilidad": a.visibilidad,
                        "valor_defecto": a.valor_defecto,
                        "es_estatico": a.es_estatico,
                    }
                    for a in c.atributos
                ],
                "operaciones": [
                    {
                        "id": o.id,
                        "nombre": o.nombre,
                        "tipo_retorno": o.tipo_retorno,
                        "visibilidad": o.visibilidad,
                    }
                    for o in c.operaciones
                ],
            }
            for c in diagrama.clases
        ]
        relaciones = [
            {
                "id": r.id,
                "tipo_relacion": r.tipo_relacion,
                "id_clase_origen": r.id_clase_origen,
                "id_clase_destino": r.id_clase_destino,
                "origen": nombres.get(r.id_clase_origen),
                "destino": nombres.get(r.id_clase_destino),
                "multiplicidad_origen": r.multiplicidad_origen,
                "multiplicidad_destino": r.multiplicidad_destino,
                "nombre_asociacion": r.nombre_asociacion,
            }
            for r in diagrama.relaciones
        ]
        return {
            "nombre": diagrama.nombre,
            "total_clases": len(clases),
            "total_relaciones": len(relaciones),
            "clases": clases,
            "relaciones": relaciones,
        }

    async def _historial_de_diagrama(
        self,
        id_diagrama: PydanticObjectId,
        consulta: str,
        tam_ventana: int,
    ) -> tuple[
        list[MensajeChat],
        list[MensajeChat],
        list[tuple[PydanticObjectId, float]],
        list[str],
    ]:
        """
        (ventana, recuperados, puntuaciones, advertencias).

        - ventana: últimos tam_ventana mensajes, cronológicos.
        - recuperados: mensajes ANTERIORES a la ventana que la consulta
          hace relevantes (recuperación semántica CU17), en orden
          cronológico; se anteponen a la ventana sin romper el orden real.
        - puntuaciones: (id_mensaje, similitud) de los aceptados, para la
          auditoría en ContextoIA.contenido.
        - advertencias: degradación si la capa IA no está disponible.
        """
        leidos = await self.mensajes.list_historial_by_diagrama(
            id_diagrama, limit=tam_ventana + LIMITE_CANDIDATOS
        )
        if not leidos:
            return [], [], [], []
        ventana = list(leidos[-tam_ventana:])
        anteriores = list(leidos[:-tam_ventana])
        if not anteriores or not (consulta and consulta.strip()):
            return ventana, [], [], []

        try:
            puntuadas = await self.embeddings.recuperar_relevantes(
                consulta,
                [m.contenido for m in anteriores],
                k=K_RECUPERADOS,
            )
        except ErrorIA as exc:
            # Conmutación agotada / motor respondió mal: el turno sigue
            # con la ventana inmediata y la causa queda auditada.
            return (
                ventana,
                [],
                [],
                [f"recuperación semántica degradada (embeddings caídos): {exc}"],
            )

        ids_ventana = {m.id for m in ventana}
        elegidos = [
            anteriores[indice]
            for indice, sim in puntuadas
            if sim >= SIMILITUD_MINIMA
            and anteriores[indice].id not in ids_ventana
        ]
        puntuaciones = [
            (anteriores[indice].id, round(sim, 4))
            for indice, sim in puntuadas
            if sim >= SIMILITUD_MINIMA
            and anteriores[indice].id not in ids_ventana
        ]
        return ventana, elegidos, puntuaciones, []

    async def _ventana_general(
        self,
        id_usuario: PydanticObjectId,
        tam_ventana: int,
    ) -> list[MensajeChat]:
        """
        Ventana del CHAT GENERAL (mensajes sin diagrama del usuario), en
        orden cronológico. El repositorio no tiene el filtro
        id_diagrama IS NULL (la capa de repositorios quedó cerrada en la
        Tanda 10): se filtra en memoria sobre una lectura acotada
        (LIMITE_LECTURA_GENERAL) — el chat general de un usuario es corto.
        """
        leidos = await self.mensajes.list_by_usuario(
            id_usuario, skip=0, limit=LIMITE_LECTURA_GENERAL
        )
        generales = [m for m in leidos if m.id_diagrama is None]
        # list_by_usuario ordena DESC (más nuevo primero): ventana = los
        # primeros tam_ventana reordenados cronológicamente.
        return list(reversed(generales[:tam_ventana]))

    @staticmethod
    def _historial_canonico(
        mensajes: Sequence[MensajeChat],
    ) -> list[dict[str, str]]:
        """MensajeChat → formato canónico OpenAI (rol_a_role)."""
        historial: list[dict[str, str]] = []
        for mensaje in mensajes:
            try:
                role = rol_a_role(mensaje.rol)
            except ValueError:
                # Documento corrupto con un rol fuera del Literal: se
                # salta ese mensaje en vez de romper el turno.
                continue
            historial.append({"role": role, "content": mensaje.contenido})
        return historial

    async def _armar_y_persistir_turno(
        self,
        *,
        id_usuario: PydanticObjectId,
        uso: str,
        prompt_sistema: str,
        texto_turno: str,
        modelo: str,
        nombres_cadena: list[str],
        mensajes_historial: list[MensajeChat],
        ventana: list[MensajeChat],
        puntuaciones: list[tuple[PydanticObjectId, float]],
        resumen: Optional[dict[str, Any]],
        seleccion: Optional[dict[str, Any]],
        id_diagrama: Optional[PydanticObjectId],
        id_proyecto: Optional[PydanticObjectId],
        advertencias: list[str],
    ) -> TurnoContexto:
        """
        Ensambla los mensajes con el ensamblador del rol, estima tokens y
        persiste el ContextoIA del turno (auditoría CU17).

        `mensajes_historial` es lo que va al modelo (recuperados + ventana,
        en orden cronológico); `ventana` es solo la parte de la ventana
        inmediata, que se audita aparte en contenido["ventana"].
        """
        historial = self._historial_canonico(mensajes_historial)
        if uso == "agente":
            mensajes = mensajes_agente_dev(
                texto_turno, resumen, historial, seleccion
            )
        elif uso == "guia":
            mensajes = mensajes_asistente_guia(
                texto_turno, resumen, historial
            )
        else:
            mensajes = mensajes_chat_general(texto_turno, historial)

        num_mensajes = len(mensajes_historial)
        num_tokens = sum(estimar_tokens(m["content"]) for m in mensajes)

        contexto = await self.contextos.create(
            ContextoIA(
                id_usuario=id_usuario,
                id_diagrama=id_diagrama,
                modelo=modelo,
                contenido={
                    "uso": uso,
                    "prompt_sistema": prompt_sistema,
                    "modelo_solicitado": modelo,
                    "cadena_conmutacion": nombres_cadena,
                    "id_diagrama": str(id_diagrama) if id_diagrama else None,
                    "resumen": resumen,
                    "seleccion": seleccion,
                    "ventana": [
                        {"id": str(m.id), "rol": m.rol}
                        for m in ventana
                    ],
                    "recuperados_semanticos": [
                        {"id_mensaje": str(mid), "similitud": sim}
                        for mid, sim in puntuaciones
                    ],
                    "num_tokens_estimados": num_tokens,
                    "advertencias": advertencias,
                },
                num_mensajes=num_mensajes,
                num_tokens=num_tokens,
            )
        )
        return TurnoContexto(
            mensajes=mensajes,
            modelo=modelo,
            contexto_id=contexto.id,
            id_proyecto=id_proyecto,
            resumen=resumen,
            num_mensajes=num_mensajes,
            num_tokens=num_tokens,
        )