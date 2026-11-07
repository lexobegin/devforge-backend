# app/ia/prompts.py
"""
Prompts de sistema y ensamblado de mensajes del módulo G — CICLO 2.

NUEVO en el Ciclo 2. Los services del módulo G (canal, gestor de contexto,
orquestador, guía, visión) NO escriben sus prompts a mano: usan estas
plantillas, que garantizan:
- la REGLA DE ORO del Agente Dev: el LLM NO toca el lienzo; responde SOLO
  con JSON estructurado (texto_respuesta + acciones[]), y cada acción
  lleva tipo_accion del MISMO vocabulario de la cola offline (módulo H);
- que el modelo reciba el resumen del diagrama y los ids uuid reales de
  los elementos EMBEBIDOS (para que las acciones referencien elementos
  existentes y no inventen ids);
- un formato de respuesta PARSEABLE (extraer_json) para el orquestador.

Contenido:
- VOCABULARIO_ACCIONES: los tipos soportados (idénticos a
  _aplicar_cambio_offline de sincronizacion_service + GENERAR_CODIGO).
- Prompts de sistema: AGENTE_DEV (CU16-CU21), ASISTENTE_GUIA (CU23),
  VISION_BOCETO (boceto → UML completo) y CHAT_GENERAL.
- Ensambladores de mensajes: * → list[dict] formato canónico OpenAI
  [{"role": "system"|"user"|"assistant", "content": ...}] listo para
  LlmProvider.generar_chat().
- Utilidades: rol_a_role (MensajeChat.rol → role del formato), 
  formatear_resumen_diagrama, extraer_json, estimar_tokens.

Los textos de los prompts son la instrucción que corrige las deficiencias
1 y 2 del Ciclo 1 (cajas "Clase1/Clase2" y acciones que no aplicaban
nada): se exige nombre real, atributos, operaciones y relaciones, y el
vocabulario cerrado de acciones.
"""

import json
import re
from typing import Any, Dict, List, Optional

# ======================================================================
# Vocabulario compartido de acciones (tipo_accion ≡ tipo_operacion)
# ======================================================================
# EXACTAMENTE los 8 tipos que hoy despacha _aplicar_cambio_offline del
# sincronizacion_service (módulo H) + GENERAR_CODIGO, que no toca el
# lienzo: se registra como AccionIA para que el generador la atienda.
VOCABULARIO_ACCIONES: tuple = (
    "CREAR_CLASE",
    "MODIFICAR_CLASE",
    "ELIMINAR_CLASE",
    "AGREGAR_ATRIBUTO",
    "MODIFICAR_ATRIBUTO",
    "ELIMINAR_ATRIBUTO",
    "CREAR_RELACION",
    "ELIMINAR_RELACION",
    "GENERAR_CODIGO",
)

# Reglas de payload por tipo (resumen en lenguaje llano para el prompt)
_PAYLOADS_DOC = (
    "- CREAR_CLASE: {\"nombre\": str, \"es_abstracta\": bool, "
    "\"estereotipo\": str?, \"pos_x\": float, \"pos_y\": float, "
    "\"atributos\": [{\"nombre\": str, \"tipo_dato\": str, "
    "\"visibilidad\": \"PUBLICO|PRIVADO|PROTEGIDO\", \"valor_defecto\": str?, "
    "\"es_estatico\": bool?}], \"operaciones\": [{\"nombre\": str, "
    "\"tipo_retorno\": str, \"visibilidad\": \"PUBLICO|PRIVADO|PROTEGIDO\"}]} "
    "  (los atributos y operaciones viajan embebidos en la misma acción)",
    "- MODIFICAR_CLASE: {\"id_clase\": uuid, \"nombre\": str?, "
    "\"es_abstracta\": bool?, \"estereotipo\": str?, \"pos_x\": float?, "
    "\"pos_y\": float?}  (solo los campos a cambiar)",
    "- ELIMINAR_CLASE: {\"id_clase\": uuid}",
    "- AGREGAR_ATRIBUTO: {\"id_clase\": uuid, \"nombre\": str, "
    "\"tipo_dato\": str, \"visibilidad\": \"PUBLICO|PRIVADO|PROTEGIDO\", "
    "\"valor_defecto\": str?, \"es_estatico\": bool?}",
    "- MODIFICAR_ATRIBUTO: {\"id_clase\": uuid, \"id_atributo\": uuid, "
    "\"nombre\": str?, \"tipo_dato\": str?, \"visibilidad\": str?, "
    "\"valor_defecto\": str?}  (solo los campos a cambiar)",
    "- ELIMINAR_ATRIBUTO: {\"id_clase\": uuid, \"id_atributo\": uuid}",
    "- CREAR_RELACION: {\"id_clase_origen\": uuid, \"id_clase_destino\": uuid, "
    "\"tipo_relacion\": \"ASOCIACION|HERENCIA|AGREGACION|COMPOSICION|DEPENDENCIA\", "
    "\"multiplicidad_origen\": str?, \"multiplicidad_destino\": str?, "
    "\"nombre_asociacion\": str?}",
    "- ELIMINAR_RELACION: {\"id_relacion\": uuid}",
    "- GENERAR_CODIGO: {\"id_proyecto\": str}  (sin id_diagrama: genera el "
    "código Spring Boot del proyecto; el ejecutor lo encadena al generador)",
)


# ======================================================================
# Prompts de sistema
# ======================================================================
SISTEMA_AGENTE_DEV: str = f"""Eres el Agente Dev de DevForge AI, una herramienta de modelado UML.
Trabajas sobre UN diagrama de clases a la vez y AYUDAS a editarlo.

REGLA ABSOLUTA: NO modificas el diagrama directamente. Tu única salida
posible es UN objeto JSON válido, sin texto fuera del JSON, con esta forma:
{{
  "texto_respuesta": "explicación breve en español para el usuario",
  "acciones": [
    {{"tipo_accion": "...", "payload": {{ ... }}, "descripcion": "..."}}
  ]
}}

Reglas para "acciones":
1. Cada tipo_accion DEBE pertenecer a este vocabulario cerrado:
{chr(10).join('- ' + t for t in VOCABULARIO_ACCIONES)}
2. El payload exacto de cada tipo:
{chr(10).join(_PAYLOADS_DOC)}
3. Los ids (id_clase, id_atributo, id_relacion, id_clase_origen,
   id_clase_destino) son los "id" uuid que el usuario te entrega en el
   contexto (diagrama actual). NUNCA inventes ids: si un elemento no está
   en el contexto, créalo (CREAR_CLASE / AGREGAR_ATRIBUTO / CREAR_RELACION)
   o pregunta.
4. Si el usuario pide algo que no requiere cambios, devuelve "acciones": []
   y explica en texto_respuesta.
5. Los cambios se aplican SOLO si el usuario confirma: avisa qué vas a
   hacer y no asumas confirmación.
6. Sigue UML 2.5.1: tipos de datos primitivos (str, int, float, bool,
   Date...), visibilidad PUBLICO/PRIVADO/PROTEGIDO y los 5 tipos de
   relación del vocabulario.
7. Responde SIEMPRE en español, JSON UTF-8, sin bloques de código fuera
   del objeto JSON y sin comentarios.
"""


SISTEMA_ASISTENTE_GUIA: str = """Eres el Asistente Guía de DevForge AI (CU23): el guía de la
herramienta de modelado UML. Ayudas al usuario a ORIENTARSE: qué puede
hacer, dónde está cada función y cómo continuar su diseño.

LÍMITES:
- SOLO LECTURA: no propones acciones sobre el diagrama ni lo editas.
  Si el usuario pide un cambio real, responde en texto cómo usar el canal
  del Agente Dev (el chat de edición) para lograrlo.
- Tu única salida posible es UN objeto JSON válido, sin texto fuera del JSON:
{
  "texto_respuesta": "respuesta breve y concreta en español",
  "sugerencias": ["acción o sección sugerida 1", "sugerencia 2"]
}

Reglas:
1. "sugerencias" tiene 0 a 3 strings cortos con pasos o secciones concretas.
2. Responde SIEMPRE en español y menciona los nombres reales de las
   funciones de DevForge (diagramas, proyectos, exportar XMI, generar
   código, colaborar, sincronizar móvil).
3. Si no sabes algo del estado del proyecto/diagrama, di qué puede mirar
   el usuario en la interfaz; NO inventes contenido del diagrama.
"""


SISTEMA_VISION_BOCETO: str = """Eres el módulo de visión de DevForge AI: reconstruyes un diagrama de
clases UML a partir de los candidatos detectados en una FOTO o BOCETO
(cajas, líneas y textos crudos de OpenCV/Tesseract).

Tu única salida posible es UN objeto JSON válido, sin texto fuera del JSON:
{
  "texto_respuesta": "resumen breve en español de lo reconocido",
  "diagrama": {
    "clases": [
      {"nombre": "NombreReal", "es_abstracta": false, "estereotipo": null,
       "pos_x": 0.0, "pos_y": 0.0,
       "atributos": [{"nombre": "ci", "tipo_dato": "str",
                      "visibilidad": "PRIVADO", "valor_defecto": null}],
       "operaciones": [{"nombre": "registrar", "tipo_retorno": "bool",
                        "visibilidad": "PUBLICO"}]}
    ],
    "relaciones": [
      {"clase_origen": "NombreReal", "clase_destino": "OtraClase",
       "tipo_relacion": "ASOCIACION|HERENCIA|AGREGACION|COMPOSICION|DEPENDENCIA",
       "multiplicidad_origen": null, "multiplicidad_destino": null,
       "nombre_asociacion": null}
    ]
  },
  "confianza": 0.0,
  "advertencias": ["lo que no se pudo leer con certeza"]
}

Reglas:
1. CORRIGE los nombres mal OCR-detectados con vocabulario de dominio
   plausible (p. ej. "Pac1ente" → "Paciente"). NUNCA dejes "Clase1",
   "Clase2" ni nombres sin sentido: es preferible menos clases con nombre
   real que muchas cajas vacías.
2. DEDUCE atributos y operaciones razonables a partir de los textos dentro
   de cada caja (+/-/# antes del texto indican visibilidad).
3. Las relaciones referencian clases por NOMBRE (clase_origen/
   clase_destino); el backend las convertirá a ids uuid.
4. "confianza" es un float en [0,1]; lista en "advertencias" toda caja
   dudosa o línea sin interpretar.
5. Responde SIEMPRE en español (los nombres de clases pueden ir en el
   idioma del dominio del usuario).
"""


SISTEMA_CHAT_GENERAL: str = """Eres el asistente de DevForge AI en el chat general (sin diagrama
abierto). Respondes dudas generales sobre modelado UML y sobre el uso de
la herramienta: proyectos, diagramas, colaboración en tiempo real,
exportación XMI compatible con Enterprise Architect, generación de código
Spring Boot, sincronización offline móvil y notificaciones.

Reglas:
1. Responde en español, breve y concreto.
2. Si la duda requiere editar un diagrama, invita a abrir un diagrama y
   usar el chat de edición del Agente Dev.
3. NO inventes datos de proyectos o diagramas del usuario.
"""


# ======================================================================
# Ensamblado de mensajes (formato canónico OpenAI)
# ======================================================================
def rol_a_role(rol: str) -> str:
    """
    MensajeChat.rol (USUARIO/ASISTENTE/SISTEMA) → role del formato canónico
    (user/assistant/system). Un rol desconocido es un bug del llamador:
    lanza ValueError para verlo en pruebas.
    """
    mapeo = {"USUARIO": "user", "ASISTENTE": "assistant", "SISTEMA": "system"}
    if rol not in mapeo:
        raise ValueError(f"Rol de MensajeChat no reconocido: '{rol}'")
    return mapeo[rol]


def _mensajes_de(historial: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Filtra/valida el historial ya convertido a formato canónico."""
    return [
        {"role": h["role"], "content": h["content"]}
        for h in historial
        if h.get("role") and h.get("content")
    ]


def _serializar_contexto(contexto: Dict[str, Any]) -> str:
    """Contexto compacto y legible para meterlo en el mensaje del usuario."""
    return json.dumps(contexto, ensure_ascii=False, default=str)


def mensajes_agente_dev(
    texto_usuario: str,
    resumen_diagrama: Optional[Dict[str, Any]] = None,
    historial: Optional[List[Dict[str, str]]] = None,
    seleccion_actual: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """
    Mensajes del turno del AGENTE DEV (CU16-CU21).

    - historial: conversación previa ya convertida con rol_a_role (el
      service arma la ventana; aquí solo se pasa por el filtro).
    - resumen_diagrama: dict armado por el gestor de contexto con el
      estado del lienzo (clases con id uuid + atributos + operaciones,
      relaciones con ids, nombre del diagrama).
    - seleccion_actual: elementos seleccionados por el usuario en el
      lienzo (para interpretar "este atributo", "esa clase").
    """
    mensajes: List[Dict[str, str]] = [{"role": "system", "content": SISTEMA_AGENTE_DEV}]
    mensajes.extend(_mensajes_de(historial or []))

    bloques: List[str] = []
    if resumen_diagrama:
        bloques.append(
            "Diagrama actual:\n" + formatear_resumen_diagrama(resumen_diagrama)
        )
    if seleccion_actual:
        bloques.append(
            "Elementos seleccionados por el usuario:\n"
            + _serializar_contexto(seleccion_actual)
        )
    bloques.append(f"Petición del usuario: {texto_usuario}")
    mensajes.append({"role": "user", "content": "\n\n".join(bloques)})
    return mensajes


def mensajes_asistente_guia(
    pregunta: str,
    resumen_diagrama: Optional[Dict[str, Any]] = None,
    historial: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Mensajes del turno del ASISTENTE GUÍA (CU23, solo lectura)."""
    mensajes: List[Dict[str, str]] = [
        {"role": "system", "content": SISTEMA_ASISTENTE_GUIA}
    ]
    mensajes.extend(_mensajes_de(historial or []))

    contenido = f"Pregunta del usuario: {pregunta}"
    if resumen_diagrama:
        contenido += (
            "\n\nEstado del proyecto/diagrama (solo para orientar, NO editar):\n"
            + formatear_resumen_diagrama(resumen_diagrama)
        )
    mensajes.append({"role": "user", "content": contenido})
    return mensajes


def mensajes_vision_boceto(
    candidatos: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Mensajes del turno de VISION: los candidatos crudos de OpenCV/Tesseract
    (cajas, líneas, textos con confianza OCR) en un dict; el modelo los
    interpreta como clases/atributos/relaciones completas.
    """
    return [
        {"role": "system", "content": SISTEMA_VISION_BOCETO},
        {
            "role": "user",
            "content": (
                "Candidatos detectados en la imagen (cajas, líneas, textos OCR):\n"
                + _serializar_contexto(candidatos)
            ),
        },
    ]


def mensajes_chat_general(
    texto_usuario: str,
    historial: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Mensajes del turno de CHAT GENERAL (sin diagrama)."""
    mensajes: List[Dict[str, str]] = [{"role": "system", "content": SISTEMA_CHAT_GENERAL}]
    mensajes.extend(_mensajes_de(historial or []))
    mensajes.append({"role": "user", "content": texto_usuario})
    return mensajes


# ======================================================================
# Utilidades
# ======================================================================
def formatear_resumen_diagrama(resumen: Dict[str, Any]) -> str:
    """
    Resumen del diagrama (dict del gestor de contexto) → texto compacto y
    legible para el prompt. Tolerante a claves ausentes (usa .get).
    """
    lineas: List[str] = []
    nombre = resumen.get("nombre") or resumen.get("nombre_diagrama")
    if nombre:
        lineas.append(f"Diagrama: {nombre}")

    clases = resumen.get("clases") or []
    for clase in clases:
        marcador = "«abstracta» " if clase.get("es_abstracta") else ""
        lineas.append(
            f"- Clase {marcador}{clase.get('nombre')} (id={clase.get('id')})"
        )
        for atributo in clase.get("atributos") or []:
            defecto = atributo.get("valor_defecto")
            sufijo = f" = {defecto}" if defecto not in (None, "") else ""
            lineas.append(
                f"    · {atributo.get('visibilidad', 'PUBLICO')} "
                f"{atributo.get('nombre')}: {atributo.get('tipo_dato')}{sufijo} "
                f"(id={atributo.get('id')})"
            )
        for operacion in clase.get("operaciones") or []:
            lineas.append(
                f"    · {operacion.get('visibilidad', 'PUBLICO')} "
                f"{operacion.get('nombre')}(): {operacion.get('tipo_retorno')} "
                f"(id={operacion.get('id')})"
            )

    relaciones = resumen.get("relaciones") or []
    for relacion in relaciones:
        lineas.append(
            f"- Relación {relacion.get('tipo_relacion', 'ASOCIACION')}: "
            f"{relacion.get('origen')} ({relacion.get('multiplicidad_origen') or '-'})"
            f" → {relacion.get('destino')} "
            f"({relacion.get('multiplicidad_destino') or '-'}) "
            f"[origen={relacion.get('id_clase_origen')}, "
            f"destino={relacion.get('id_clase_destino')}, "
            f"id={relacion.get('id')}]"
        )

    if not lineas:
        return "(diagrama vacío)"
    return "\n".join(lineas)


_RE_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extraer_json(texto: str) -> Optional[Any]:
    """
    Extrae el primer objeto/array JSON de la respuesta del modelo:
    1) dentro de un bloque ```json ... ```;
    2) si no hay bloque, el primer fragmento balanceado de {} o [].
    Devuelve None si no hay nada parseable (el orquestador decide si
    reintentar o responder solo con texto).
    """
    if not texto:
        return None

    # 1) Bloques con fence
    for coincidencia in _RE_JSON_FENCE.finditer(texto):
        try:
            return json.loads(coincidencia.group(1))
        except json.JSONDecodeError:
            continue

    # 2) Fragmento balanceado (el modelo suele añadir prosa alrededor)
    for abre, cierra in (("{", "}"), ("[", "]")):
        inicio = texto.find(abre)
        while inicio != -1:
            profundidad = 0
            for fin in range(inicio, len(texto)):
                if texto[fin] == abre:
                    profundidad += 1
                elif texto[fin] == cierra:
                    profundidad -= 1
                    if profundidad == 0:
                        try:
                            return json.loads(texto[inicio : fin + 1])
                        except json.JSONDecodeError:
                            break
            inicio = texto.find(abre, inicio + 1)
    return None


def estimar_tokens(texto: str) -> int:
    """
    Estimación gruesa del conteo de tokens (≈ 4 caracteres por token,
    suficiente para dimensionar la ventana del contexto; el dato REAL del
    motor se registra en RespuestaProveedorIA.tokens_prompt).
    """
    if not texto:
        return 0
    return max(1, round(len(texto) / 4))