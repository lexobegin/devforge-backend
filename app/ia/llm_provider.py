# app/ia/llm_provider.py
"""
Capa de proveedores LLM de DevForge AI (Ciclo 2) — el ABC del módulo G.

NUEVO en el Ciclo 2: en el Ciclo 1 la IA era una llamada online a la nube
(sin abstracción de motor). En el Ciclo 2 la IA es LOCAL obligatoria
(Ollama instalado en la misma VM) con respaldos conmutables, así que todos
los motores (principal y respaldos) implementan la MISMA interfaz
`LlmProvider` y los services del módulo G (canal, gestor de contexto,
orquestador, guía) no saben a quién le están hablando.

Decisiones de diseño (D28 del informe):
- La CADENA de proveedores la define `settings.IA_CADENA_COMPLETA`
  (IA_PROVIDER + IA_CADENA_RESPALDO, en orden). `construir_cadena()` la
  materializa en instancias listas para usar.
- Conmutación por FALLA: quien consume la cadena (ServicioEmbeddings aquí;
  canal_service / orquestador_agente en su tanda) recorre proveedores en
  orden y usa el primero que responda. `disponible()` permite un chequeo
  barato previo, pero la decisión final la da intentar y capturar
  `IAIndisponibleError`.
- Modelos por ROL (no por proveedor): `modelo_para("agente")` devuelve el
  motor grande (qwen2.5:7b, CU16-CU21) y `modelo_para("guia")` el liviano
  (llama3.2:3b, CU23). Cada proveedor mapea ese rol a su configuración.
- Los mensajes viajan SIEMPRE en formato OpenAI
  [{"role": "system"|"user"|"assistant", "content": "..."}]; cada
  proveedor traduce al dialecto propio (Gemini usa "model" por
  "assistant" y separa el system en systemInstruction).
- SIN base de datos y SIN lógica de negocio: esta capa solo habla HTTP
  con los motores (httpx). Todo lo que toque MongoDB vive en services.

Errores:
- `IAIndisponibleError`  → el motor no respondió (red/timeout/5xx/no
  configurado). SEÑAL DE CONMUTACIÓN: si un proveedor la lanza se intenta
  con el siguiente de la cadena.
- `ErrorIA`              → el motor respondió pero con un problema
  (payload inválido, formato inesperado, voz deshabilitada…). NO
  conmuta: reintentar con otro motor no arregla un prompt inválido.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

import httpx

from app.config import Settings, settings

# Rol de consumo: el Agente Dev (CU16-CU21) usa el motor grande; el
# Asistente Guía (CU23) el liviano.
UsoMotor = Literal["agente", "guia"]

# Roles de mensaje en formato OpenAI (formato canónico de este módulo)
RolesValidos = ("system", "user", "assistant")


# ======================================================================
# Errores de la capa IA
# ======================================================================
class ErrorIA(Exception):
    """
    Error general de la capa IA (el motor respondió pero con un problema,
    o la función pedida está deshabilitada). NO dispara conmutación.
    """

    def __init__(self, detalle: str):
        self.detalle = detalle
        super().__init__(detalle)


class IAIndisponibleError(ErrorIA):
    """
    El proveedor no está disponible (sin red, timeout, 5xx, no configurado).
    Es la señal para CONMUTAR al siguiente proveedor de la cadena.
    """

    def __init__(self, detalle: str):
        super().__init__(f"Proveedor IA indisponible: {detalle}")


# ======================================================================
# Respuestas uniformes (dataclasses, no esquemas HTTP: es capa interna)
# ======================================================================
@dataclass
class RespuestaProveedorIA:
    """Texto generado por un LLM, con metadatos de auditoría.

    Los metadatos (tokens, latencia, proveedor) son los que persisten los
    services en `MensajeChat.modelo` y en los logs del turno, para poder
    comparar calidad entre motores (qwen2.5:7b vs llama3.2:3b vs respaldo).
    """

    texto: str
    modelo: str                      # modelo concreto que respondió
    proveedor: str                   # 'ollama' | 'openai_compat' | 'gemini'
    tokens_prompt: Optional[int] = None
    tokens_respuesta: Optional[int] = None
    latencia_seg: Optional[float] = None
    crudo: Optional[Dict[str, Any]] = field(
        default=None, repr=False
    )  # payload crudo del motor (depuración)


@dataclass
class RespuestaEmbeddingsIA:
    """Vector de embedding devuelto por un proveedor."""

    vector: List[float]
    modelo: str
    proveedor: str
    dimension: Optional[int] = None

    def __post_init__(self):
        if self.dimension is None:
            self.dimension = len(self.vector)


# ======================================================================
# ABC LlmProvider
# ======================================================================
class LlmProvider(ABC):
    """
    Interfaz común de todos los motores IA (principal y respaldos).

    Un proveedor:
    - recibe `settings` (inyectables para pruebas) y crea su cliente HTTP,
    - traduce el formato canónico de mensajes a su dialecto,
    - convierte las fallas de red en `IAIndisponibleError` y las respuestas
      inválidas en `ErrorIA`.
    """

    # Nombre canónico del proveedor (igual que en IA_CADENA_COMPLETA)
    nombre: str = "abstracto"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        """
        `transport` es un parámetro de PRUEBA (httpx.MockTransport en el
        arnés de verificación); en producción siempre es None y el cliente
        sale a la red real.
        """
        self.settings = settings or settings_global()
        self._transport = transport
        self._cliente: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Infraestructura HTTP común
    # ------------------------------------------------------------------
    def _obtener_cliente(self, timeout_seg: float) -> httpx.AsyncClient:
        """Cliente httpx reutilizable (se cierra con `cerrar()`)."""
        if self._cliente is None or self._cliente.is_closed:
            kwargs: Dict[str, Any] = {"timeout": timeout_seg}
            if self._transport is not None:  # solo en pruebas
                kwargs["transport"] = self._transport
            self._cliente = httpx.AsyncClient(**kwargs)
        return self._cliente

    async def cerrar(self) -> None:
        """Cierra el cliente HTTP (útil entre pruebas / cierre de app)."""
        if self._cliente is not None and not self._cliente.is_closed:
            await self._cliente.aclose()

    def _medir(self) -> float:
        """Marca de inicio para la latencia de cada llamada."""
        return time.monotonic()

    @staticmethod
    def _latencia(desde: float) -> float:
        return round(time.monotonic() - desde, 4)

    @staticmethod
    def _envolver_falla_red(exc: httpx.HTTPError, proveedor: str) -> IAIndisponibleError:
        """Traduce cualquier error de httpx a conmutación explícita."""
        return IAIndisponibleError(f"{proveedor} sin respuesta ({type(exc).__name__}: {exc})")

    # ------------------------------------------------------------------
    # API abstracta (cada proveedor la implementa a su dialecto)
    # ------------------------------------------------------------------
    @abstractmethod
    async def generar_chat(
        self,
        mensajes: List[Dict[str, str]],
        modelo: Optional[str] = None,
        temperatura: float = 0.2,
    ) -> RespuestaProveedorIA:
        """Genera una respuesta a partir de una conversación completa."""

    @abstractmethod
    async def incrustar(
        self, texto: str, modelo: Optional[str] = None
    ) -> RespuestaEmbeddingsIA:
        """Calcula el embedding de un texto (CU17, contexto persistente)."""

    @abstractmethod
    async def disponible(self) -> bool:
        """Chequeo barato de salud (para prechequeo, NO para decidir solo)."""

    # ------------------------------------------------------------------
    # Helpers comunes (implementación concreta compartida)
    # ------------------------------------------------------------------
    def modelo_para(self, uso: UsoMotor) -> str:
        """Modelo de este proveedor según el rol de consumo.

        - 'agente' → motor grande (OLLAMA_MODEL_TEXT en Ollama; el modelo
          principal configurado en los respaldos).
        - 'guia'   → motor liviano (OLLAMA_MODEL_LIGERO en Ollama; en los
          respaldos no hay distinción y también se usa el principal).
        """
        if uso == "guia":
            return self.modelo_ligero
        return self.modelo_texto

    @property
    def modelo_texto(self) -> str:
        """Modelo por defecto para generación (cada proveedor lo fija)."""
        raise NotImplementedError

    @property
    def modelo_ligero(self) -> str:
        raise NotImplementedError

    @property
    def modelo_embeddings(self) -> str:
        raise NotImplementedError

    async def generar(
        self,
        prompt: str,
        instruccion_sistema: Optional[str] = None,
        uso: UsoMotor = "agente",
        modelo: Optional[str] = None,
        temperatura: float = 0.2,
    ) -> RespuestaProveedorIA:
        """Envoltorio de `generar_chat` para el caso de un solo turno."""
        mensajes: List[Dict[str, str]] = []
        if instruccion_sistema:
            mensajes.append({"role": "system", "content": instruccion_sistema})
        mensajes.append({"role": "user", "content": prompt})
        return await self.generar_chat(
            mensajes,
            modelo=modelo or self.modelo_para(uso),
            temperatura=temperatura,
        )

    @staticmethod
    def _validar_mensajes(mensajes: List[Dict[str, str]]) -> None:
        """Defensa: formato canónico {role, content} y roles conocidos."""
        if not mensajes:
            raise ErrorIA("La lista de mensajes está vacía: no hay nada que enviar al motor")
        for m in mensajes:
            if not isinstance(m, dict) or "role" not in m or "content" not in m:
                raise ErrorIA(
                    "Mensaje mal formado para el motor IA (debe llevar 'role' y 'content')"
                )
            if m["role"] not in RolesValidos:
                raise ErrorIA(f"Rol de mensaje no soportado por el motor IA: '{m['role']}'")


def settings_global() -> Settings:
    """Configuración global (importada arriba; permite inyección en pruebas)."""
    return settings


# ======================================================================
# Factory de la cadena de proveedores
# ======================================================================
def construir_cadena(cfg: Optional[Settings] = None) -> List[LlmProvider]:
    """
    Materializa `settings.IA_CADENA_COMPLETA` en instancias LlmProvider,
    en el orden de conmutación (principal primero).

    Ejemplo (por defecto): IA_PROVIDER=ollama y
    IA_CADENA_RESPALDO=openai_compat,gemini  →
        [OllamaProvider, OpenAICompatProvider, GeminiProvider]

    Un nombre desconocido en la cadena es un error de CONFIGURACIÓN (no
    de ejecución): se aborta en el arranque, no a mitad de un turno.
    """
    cfg = cfg or settings_global()
    # Import diferido: llm_provider no depende de las implementaciones al
    # importarse (las implementaciones SÍ importan de llm_provider).
    from app.ia.ollama_provider import OllamaProvider
    from app.ia.proveedor_respaldo import GeminiProvider, OpenAICompatProvider

    fabricas = {
        "ollama": OllamaProvider,
        "openai_compat": OpenAICompatProvider,
        "gemini": GeminiProvider,
    }

    cadena: List[LlmProvider] = []
    for nombre in cfg.IA_CADENA_COMPLETA:
        fabrica = fabricas.get(nombre)
        if fabrica is None:
            raise ErrorIA(
                f"Proveedor IA desconocido en la cadena: '{nombre}' "
                f"(válidos: {', '.join(sorted(fabricas))})"
            )
        cadena.append(fabrica(cfg))
    return cadena