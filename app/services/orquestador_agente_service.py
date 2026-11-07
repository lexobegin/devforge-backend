# app/services/orquestador_agente_service.py
"""
Lógica del ORQUESTADOR DEL AGENTE DEV (módulo G, CU18-CU21) — CICLO 2.

ARCHIVO NUEVO del Ciclo 2 (no existe en el Ciclo 1): en el Ciclo 1 la
tabla `interacciones_ia` guardaba en una sola fila el mensaje, el
contexto y la "acción" que casi nunca se aplicaba (deficiencia 2 del
Ciclo 1). En el Ciclo 2 este service es el CEREBRO del turno del agente:
habla con la cadena de motores, PARSEA la respuesta JSON del modelo y
convierte cada acción propuesta en un documento AccionIA en estado
PROPUESTA. No toca el lienzo (eso lo hace ejecutor_acciones_service, tras
la confirmación del usuario) ni la conversación (mensajes_chat es del
canal, CU16).

Flujo de `procesar_turno()` (contrato fijado y probado por el stub de la
Tanda 15 en canal_service):
1. LLAMADA POR LA CADENA: recorre construir_cadena() en orden y usa el
   primer proveedor que responda (IAIndisponibleError conmuta; ErrorIA NO:
   responder mal no se arregla cambiando de motor). El modelo pedido a
   cada proveedor es `modelo_para("agente")` — el motor grande
   (qwen2.5:7b en Ollama), el rol CU18-CU21.
2. PARSEO: `extraer_json()` (app.ia.prompts) extrae el objeto
   {"texto_respuesta": ..., "acciones": [...]} de la respuesta (con o sin
   bloque ```json). Si el modelo respondió PROSA sin JSON, el turno NO
   falla: la prosa se entrega como texto_respuesta sin acciones
   (decisión documentada; la conversación nunca se pierde).
3. FILTRO DEL VOCABULARIO: cada acción con tipo_accion fuera de
   VOCABULARIO_ACCIONES (los mismos 9 tipos de la cola offline del módulo
   H + GENERAR_CODIGO) o con payload no-dict se DESCARTA y el motivo se
   anexa al texto_respuesta como aviso; las válidas siguen.
4. CREACIÓN DE AccionIA PROPUESTA: una fila por acción válida en la
   colección acciones_ia (id_usuario, id_diagrama, id_mensaje del turno,
   payload íntegro). La acción NACE PROPUESTA: NINGUNA acción se aplica
   sola — el usuario confirma por ids y el ejecutor (T16) aplica.
5. GENERAR_CODIGO: es la única acción que no apunta a un diagrama (se
   persiste con id_diagrama=None). Como el modelo NO puede inventar el
   id_proyecto (regla "NUNCA inventes ids"), el orquestador lo INYECTA
   REAL: lectura mínima del documento Diagrama del turno para tomar su
   id_proyecto y sobrescribir payload["id_proyecto"] (metadato del turno,
   NO lectura/escritura del lienzo). Si el diagrama ya no existe, el
   payload queda como venga y el ejecutor marcará la acción FALLIDA.

Decisiones de diseño:
- EL MODELO AUDITADO es el que REALMENTE respondió (RespuestaProveedorIA.
  modelo): el canal lo persiste en MensajeChat.modelo; el ContextoIA del
  gestor (CU17) ya guardó el solicitado. Así se comparan motores con
  datos reales aunque la cadena conmute.
- requiere_confirmacion = True SOLO si quedaron acciones válidas por
  confirmar (misma semántica del chat general: sin acciones → False).
- SIN ESTADO y sin dependencia del canal/gestor: recibe `mensajes` ya
  ensamblados (formato canónico OpenAI) — el contexto lo armó el gestor
  CU17 y la validación de acceso ya la hizo el canal vía gestor.
- Costura de PRUEBA: `cadena` inyectable en el constructor (dobles del
  arnés); en producción se omite y se construye con construir_cadena().
  La construcción de la cadena es PEREZOSA (en _llamar_cadena, no en
  __init__) para que el parcheo del factory a nivel de módulo funcione en
  pruebas de integración canal → orquestador.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional

from beanie import PydanticObjectId

from app.ia.llm_provider import (
    IAIndisponibleError,
    LlmProvider,
    RespuestaProveedorIA,
    construir_cadena,
)
from app.ia.prompts import VOCABULARIO_ACCIONES, extraer_json
from app.models.accion_ia import AccionIA
from app.repositories.accion_ia_repository import AccionIARepository
from app.repositories.diagrama_repository import DiagramaRepository
from app.schemas.agente_schema import AccionIAPropuesta


# ======================================================================
# Resultado del turno (lo que consume canal_service)
# ======================================================================
@dataclass
class TurnoAgente:
    """
    Salida del orquestador para un turno del Agente Dev:
    - texto_respuesta: explicación en lenguaje natural (JSON del modelo,
      prosa recortada si no hubo JSON, con avisos de acciones descartadas).
    - acciones_propuestas: acciones válidas ya PERSISTIDAS como AccionIA
      (estado PROPUESTA), en el formato ligero AccionIAPropuesta; el
      frontend confirma por ids que obtiene del listado de pendientes del
      ejecutor (AccionIAResponse), no de aquí.
    - modelo: motor que REALMENTE respondió (auditoría en MensajeChat).
    - requiere_confirmacion: True solo si hay acciones por confirmar.
    """

    texto_respuesta: str
    acciones_propuestas: list[AccionIAPropuesta] = field(default_factory=list)
    modelo: str = ""
    requiere_confirmacion: bool = False


# ======================================================================
# OrquestadorAgenteService
# ======================================================================
class OrquestadorAgenteService:
    """
    Cerebro del Agente Dev (CU18-CU21): cadena de motores → JSON →
    AccionIA PROPUESTA. El lienzo NO lo toca: propone y espera la
    confirmación del usuario (ejecutor_acciones_service).
    """

    def __init__(
        self,
        cadena: Optional[List[LlmProvider]] = None,
    ) -> None:
        """
        `cadena` es una costura de PRUEBA (inyección de dobles del arnés);
        en producción se omite y _llamar_cadena() materializa
        construir_cadena(). La construcción es perezosa para que el
        factory sea parcheable a nivel de módulo en pruebas de integración.
        """
        self.acciones = AccionIARepository()
        self.diagramas = DiagramaRepository()
        self._cadena_inyectada = cadena

    # ==================================================================
    # PUNTO DE ENTRADA (contrato fijado en canal_service, T15)
    # ==================================================================
    async def procesar_turno(
        self,
        *,
        id_usuario: PydanticObjectId,
        id_diagrama: PydanticObjectId,
        mensajes: List[dict],
        id_mensaje_origen: Optional[PydanticObjectId],
    ) -> TurnoAgente:
        """
        Turno del AGENTE DEV: llama a la cadena con el contexto armado por
        el gestor (CU17), parsea la respuesta y persiste las acciones
        PROPUESTA. El `id_mensaje_origen` es el mensaje USUARIO que el
        canal persistió antes de llamar (traza mensaje ↔ acciones).
        """
        respuesta = await self._llamar_cadena(mensajes)

        texto, acciones_brutas = self._interpretar(respuesta.texto)

        propuestas: list[AccionIAPropuesta] = []
        for tipo, payload, descripcion in acciones_brutas:
            if tipo == "GENERAR_CODIGO":
                # Única acción sin diagrama: el backend inyecta el
                # id_proyecto REAL (el modelo no puede inventarlo).
                payload = await self._fijar_id_proyecto(payload, id_diagrama)
            accion = await self.acciones.create(
                AccionIA(
                    id_usuario=id_usuario,
                    id_diagrama=None if tipo == "GENERAR_CODIGO" else id_diagrama,
                    id_mensaje=id_mensaje_origen,
                    tipo_accion=tipo,
                    payload=payload,
                    estado="PROPUESTA",
                )
            )
            propuestas.append(
                AccionIAPropuesta(
                    tipo_accion=accion.tipo_accion,
                    payload=accion.payload,
                    descripcion=descripcion,
                )
            )

        return TurnoAgente(
            texto_respuesta=texto,
            acciones_propuestas=propuestas,
            modelo=respuesta.modelo,
            requiere_confirmacion=bool(propuestas),
        )

    # ==================================================================
    # CADENA DE PROVEEDORES (misma conmutación que el chat general)
    # ==================================================================
    async def _llamar_cadena(self, mensajes: List[dict]) -> RespuestaProveedorIA:
        """
        Recorre la cadena en orden y usa el primer proveedor que responda.
        IAIndisponibleError conmuta al siguiente; ErrorIA se PROPAGA
        (reintentar con otro motor no arregla una respuesta inválida).
        Cada proveedor recibe su modelo_para("agente") (motor grande).
        """
        cadena = self._cadena_inyectada or construir_cadena()
        ultimo_error: Optional[Exception] = None
        for proveedor in cadena:
            try:
                return await proveedor.generar_chat(
                    mensajes,
                    modelo=proveedor.modelo_para("agente"),
                )
            except IAIndisponibleError as exc:
                ultimo_error = exc  # conmutar: intentar el siguiente
                continue
        raise ultimo_error or IAIndisponibleError(
            "Ningún proveedor IA respondió para el Agente Dev"
        )

    # ==================================================================
    # INTERPRETACIÓN DE LA RESPUESTA DEL MODELO
    # ==================================================================
    def _interpretar(self, texto_modelo: str) -> tuple[str, list[tuple[str, dict, Optional[str]]]]:
        """
        Respuesta cruda del motor → (texto_respuesta, acciones válidas).

        - Objeto JSON esperado: {"texto_respuesta": str,
          "acciones": [{"tipo_accion": str, "payload": dict,
                        "descripcion": str?}]}.
        - Sin JSON parseable o forma inesperada (lista, string…) → la
          prosa completa se entrega como texto_respuesta SIN acciones
          (el turno no se pierde; decisión documentada).
        - Acciones descartadas (tipo fuera del vocabulario, payload no
          dict, item no-dict) anexan un aviso al texto_respuesta y NO se
          persisten: el vocabulario es cerrado (módulo H + GENERAR_CODIGO).
        """
        datos: Any = extraer_json(texto_modelo)

        if not isinstance(datos, dict):
            # Prosa sin JSON (o JSON de forma inesperada): responder solo
            # con texto, sin acciones ni confirmación.
            return texto_modelo.strip(), []

        texto = datos.get("texto_respuesta")
        if not isinstance(texto, str) or not texto.strip():
            # Modelo parsimonioso: texto genérico en español.
            total = len(datos.get("acciones") or [])
            texto = (
                f"Propuse {total} acción(es) para tu solicitud."
                if total
                else "Revisé tu solicitud; no propongo cambios por ahora."
            )

        acciones: list[tuple[str, dict, Optional[str]]] = []
        descartes: list[str] = []
        for item in datos.get("acciones") or []:
            if not isinstance(item, dict):
                descartes.append(
                    "acción descartada: el item no es un objeto JSON"
                )
                continue
            tipo = str(item.get("tipo_accion", "")).strip().upper()
            if tipo not in VOCABULARIO_ACCIONES:
                descartes.append(
                    f"acción descartada: tipo '{tipo or 'vacío'}' "
                    f"está fuera del vocabulario soportado"
                )
                continue
            payload = item.get("payload")
            if payload is None:
                payload = {}
            if not isinstance(payload, dict):
                descartes.append(
                    f"acción descartada ({tipo}): el payload no es un objeto"
                )
                continue
            descripcion = item.get("descripcion")
            if isinstance(descripcion, str):
                # El esquema AccionIAPropuesta limita descripcion a 255.
                descripcion = descripcion.strip()[:255] or None
            else:
                descripcion = None
            acciones.append((tipo, payload, descripcion))

        if descartes:
            texto = texto.rstrip() + "\n\n" + "\n".join(
                f"(Aviso: {d}.)" for d in descartes
            )
        return texto, acciones

    # ==================================================================
    # GENERAR_CODIGO: inyección del id_proyecto REAL
    # ==================================================================
    async def _fijar_id_proyecto(
        self,
        payload: dict,
        id_diagrama: PydanticObjectId,
    ) -> dict:
        """
        GENERAR_CODIGO no puede depender de que el modelo "recuerde" el
        id del proyecto (regla: NUNCA inventes ids): el orquestador toma
        el id_proyecto REAL del diagrama del turno (lectura mínima de
        metadatos del documento; el lienzo no se toca) y sobrescribe
        payload["id_proyecto"]. Si el diagrama ya no existe, el payload
        queda intacto y el ejecutor marcará la acción FALLIDA.
        """
        diagrama = await self.diagramas.get_by_id(id_diagrama)
        if diagrama is not None:
            payload = dict(payload)  # no mutar el dict del modelo
            payload["id_proyecto"] = str(diagrama.id_proyecto)
        return payload