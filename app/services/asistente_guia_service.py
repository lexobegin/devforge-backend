# app/services/asistente_guia_service.py
"""
Lógica del ASISTENTE GUÍA de DevForge AI (módulo G, CU23) — CICLO 2.

ARCHIVO NUEVO del Ciclo 2 (no existe en el Ciclo 1): en el Ciclo 1 el
módulo "IA Asistente" mezclaba todo en un solo canal. En el Ciclo 2 la
guía es el rol SOLO LECTURA del módulo G: orienta al usuario (qué puede
hacer, dónde está cada función, cómo continuar su diseño) y NUNCA propone
acciones sobre el diagrama — si el usuario pide un cambio real, la
respuesta lo deriva al canal del Agente Dev (CU16/CU18).

Diferencias con el orquestador (T16, CU18-CU21):
- NO crea AccionIA: su salida es texto + sugerencias de navegación
  (RespuestaGuiaResponse del canal lleva id_mensaje del mensaje ASISTENTE
  que el canal persiste).
- Usa el motor LIVIANO de la cadena: cada proveedor recibe su
  `modelo_para("guia")` (llama3.2:3b en Ollama), no el grande.
- NO toca NINGUNA colección: la conversación (mensajes_chat) es del canal
  (CU16, dueño único de las escrituras) y el contexto (contextos_ia) del
  gestor (CU17). Este service solo habla con motores: es el service más
  liviano del módulo G.

Flujo de `responder()` (contrato fijado y probado por el stub de la
Tanda 15 en canal_service):
1. LLAMADA POR LA CADENA: recorrer construir_cadena() en orden y usar el
   primer proveedor que responda (IAIndisponibleError conmuta; ErrorIA NO:
   responder mal no se arregla cambiando de motor — mismo contrato que el
   chat general y el orquestador).
2. PARSEO con extraer_json (prompts, T14): objeto
   {"texto_respuesta": str, "sugerencias": [str]}. Si el modelo respondió
   PROSA sin JSON, el turno NO falla: la prosa se entrega como texto sin
   sugerencias (misma decisión documentada del orquestador: la
   conversación nunca se pierde).
3. SANEAMIENTO de sugerencias: solo strings, sin vacíos, recortadas a
   MAX_LARGO_SUGERENCIA y como máximo MAX_SUGERENCIAS (el prompt del
   sistema pide 0-3; si el modelo se pasa, se recorta — la respuesta
   nunca rompe al frontend).

Sobre los parámetros de la firma (fijada en la T15 y consumida por el
canal con `AsistenteGuiaService().responder(...)`):
- `id_usuario` e `id_mensaje_origen` NO se usan para escribir: el acceso
  ya lo validó el canal vía gestor (membresía del proyecto si hay
  diagrama) y el mensaje USUARIO ya fue persistido antes de la llamada
  (id_mensaje_origen es su traza). Se mantienen en la firma porque el
  contrato del canal quedó cerrado en la T15 y porque dejan la puerta
  lista para auditorías futuras sin romper a los llamantes.
- `mensajes` llega ya ensamblado por el gestor (formato canónico OpenAI
  con SISTEMA_ASISTENTE_GUIA + historial + pregunta, y el resumen del
  diagrama si lo hay): la guía NO reconstruye contexto.

Costura de PRUEBA: `cadena` inyectable en el constructor (dobles del
arnés); en producción se omite y _llamar_cadena() materializa
construir_cadena(). La construcción es PEREZOSA (en _llamar_cadena, no en
__init__), igual que en el orquestador, para que el parcheo del factory a
nivel de módulo funcione en el E2E canal → guía.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from beanie import PydanticObjectId

from app.ia.llm_provider import (
    IAIndisponibleError,
    LlmProvider,
    RespuestaProveedorIA,
    construir_cadena,
)
from app.ia.prompts import extraer_json

# Límites del saneamiento de sugerencias (el prompt pide 0-3 cortas).
MAX_SUGERENCIAS = 3
MAX_LARGO_SUGERENCIA = 200


# ======================================================================
# Resultado del turno (lo que consume canal_service)
# ======================================================================
@dataclass
class TurnoGuia:
    """
    Salida de la guía para un turno (contrato del canal, T15):
    - texto_respuesta: explicación breve en español (JSON del modelo o
      prosa recortada si no hubo JSON).
    - sugerencias: 0-3 pasos/secciones concretas para continuar.
    - modelo: motor que REALMENTE respondió (el canal lo persiste en
      MensajeChat.modelo para comparar calidad entre motores).
    """

    texto_respuesta: str
    sugerencias: list[str] = field(default_factory=list)
    modelo: str = ""


# ======================================================================
# AsistenteGuiaService
# ======================================================================
class AsistenteGuiaService:
    """
    Rol SOLO LECTURA del módulo G (CU23): cadena de motores → JSON →
    texto + sugerencias. Sin acciones, sin colecciones, sin lienzo.
    """

    def __init__(
        self,
        cadena: Optional[List[LlmProvider]] = None,
    ) -> None:
        """
        `cadena` es una costura de PRUEBA (inyección de dobles del arnés);
        en producción se omite y _llamar_cadena() materializa
        construir_cadena(). La construcción es perezosa (igual que en el
        orquestador) para que el factory sea parcheable a nivel de módulo
        en el E2E canal → guía.
        """
        self._cadena_inyectada = cadena

    # ==================================================================
    # PUNTO DE ENTRADA (contrato fijado en canal_service, T15)
    # ==================================================================
    async def responder(
        self,
        *,
        id_usuario: PydanticObjectId,
        mensajes: List[dict],
        id_mensaje_origen: Optional[PydanticObjectId],
    ) -> TurnoGuia:
        """
        Turno de la GUÍA: llama a la cadena con el contexto armado por el
        gestor (CU17), parsea la respuesta y devuelve texto + sugerencias.
        No persiste nada: los mensajes USUARIO/ASISTENTE los escribe el
        canal (dueño único de mensajes_chat).
        """
        respuesta = await self._llamar_cadena(mensajes)
        texto, sugerencias = self._interpretar(respuesta.texto)
        return TurnoGuia(
            texto_respuesta=texto,
            sugerencias=sugerencias,
            modelo=respuesta.modelo,
        )

    # ==================================================================
    # CADENA DE PROVEEDORES (motor LIVIANO, misma conmutación)
    # ==================================================================
    async def _llamar_cadena(self, mensajes: List[dict]) -> RespuestaProveedorIA:
        """
        Recorre la cadena en orden y usa el primer proveedor que responda.
        IAIndisponibleError conmuta al siguiente; ErrorIA se PROPAGA
        (reintentar con otro motor no arregla una respuesta inválida).
        Cada proveedor recibe su modelo_para("guia") (motor liviano,
        llama3.2:3b en Ollama — la guía no necesita el grande).
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
            "Ningún proveedor IA respondió para el Asistente Guía"
        )

    # ==================================================================
    # INTERPRETACIÓN DE LA RESPUESTA DEL MODELO
    # ==================================================================
    def _interpretar(self, texto_modelo: str) -> tuple[str, list[str]]:
        """
        Respuesta cruda del motor → (texto_respuesta, sugerencias).

        - Objeto JSON esperado: {"texto_respuesta": str,
          "sugerencias": [str, ...]}.
        - Sin JSON parseable o forma inesperada (lista, string…) → la
          prosa completa se entrega como texto_respuesta SIN sugerencias
          (el turno no se pierde; misma decisión del orquestador).
        - sugerencias: items no-string o vacíos se descartan, cada una se
          recorta a MAX_LARGO_SUGERENCIA y se aceptan como máximo
          MAX_SUGERENCIAS (0-3 según el prompt del sistema).
        """
        datos = extraer_json(texto_modelo)

        if not isinstance(datos, dict):
            # Prosa sin JSON (o JSON de forma inesperada): responder solo
            # con texto, sin sugerencias.
            return texto_modelo.strip(), []

        texto = datos.get("texto_respuesta")
        if not isinstance(texto, str) or not texto.strip():
            # Modelo parsimonioso: texto de repliegue en español.
            texto = (
                "Aquí tienes sugerencias para continuar."
                if self._sanea_sugerencias(datos.get("sugerencias"))
                else "Revisé tu pregunta; no tengo sugerencias por ahora."
            )

        return texto.strip(), self._sanea_sugerencias(
            datos.get("sugerencias")
        )

    # ==================================================================
    # SANEAMIENTO DE SUGERENCIAS
    # ==================================================================
    @staticmethod
    def _sanea_sugerencias(brutas: object) -> list[str]:
        """
        Aplica el contrato de sugerencias al output del modelo:
        solo strings no vacíos, recortados a MAX_LARGO_SUGERENCIA y como
        máximo MAX_SUGERENCIAS (0-3). Nunca lanza: una sugerencia mal
        formada se descarta, no rompe la respuesta.
        """
        if not isinstance(brutas, list):
            return []
        limpias: list[str] = []
        for item in brutas:
            if not isinstance(item, str):
                continue
            texto = item.strip()[:MAX_LARGO_SUGERENCIA]
            if texto:
                limpias.append(texto)
            if len(limpias) == MAX_SUGERENCIAS:
                break
        return limpias