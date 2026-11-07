# app/ia/proveedor_respaldo.py
"""
Proveedores de RESPALDO del módulo G — CICLO 2.

NUEVO en el Ciclo 2. Actúan SOLO cuando el motor principal (Ollama local)
está caído o sin cargar, siguiendo `settings.IA_CADENA_RESPALDO`:

1. OpenAICompatProvider ('openai_compat')
   Cualquier servidor compatible con la API de OpenAI que el despliegue
   pueda alcanzar (vLLM, LM Studio, LiteLLM, incluso OpenAI real):
   - POST {base}/chat/completions  (Authorization: Bearer <key>)
   - POST {base}/embeddings
   - GET  {base}/models            (salud)
   Si OPENAI_COMPAT_BASE_URL queda vacío, el proveedor se declara
   "no configurado": disponible()=False y toda llamada lanza
   IAIndisponibleError (conmutar al siguiente).

2. GeminiProvider ('gemini')
   Gemini en la nube (A4): API generativelanguage con header
   x-goog-api-key:
   - POST .../models/{modelo}:generateContent
   - POST .../models/{modelo}:embedContent
   - GET  .../models               (salud)
   Traducción de roles: 'assistant' → 'model'; el mensaje 'system' NO va
   en contents sino en systemInstruction (regla de la API de Gemini).

Ambos comparten el contrato de la ABC (mismos errores, misma respuesta
uniforme) y usan el timeout general IA_TIMEOUT_SECONDS.
"""

from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings
from app.ia.llm_provider import (
    ErrorIA,
    IAIndisponibleError,
    LlmProvider,
    RespuestaEmbeddingsIA,
    RespuestaProveedorIA,
)

# Timeout corto SOLO para cheques de salud
_TIMEOUT_SALUD_SEG = 5.0

_BASE_GEMINI = "https://generativelanguage.googleapis.com/v1beta"


class _RespaldoBase(LlmProvider):
    """Comportamiento común de los respaldos: sin configuración → indisponible."""

    nombre = "respaldo"

    # Cada subclase describe qué variable de configuración le falta
    def _falta_configuracion(self) -> Optional[str]:
        raise NotImplementedError

    def _si_no_configurado(self) -> None:
        """Lanza la conmutación cuando al respaldo le faltan credenciales."""
        variable = self._falta_configuracion()
        if variable:
            raise IAIndisponibleError(
                f"respaldo '{self.nombre}' no configurado (defina {variable} en el .env)"
            )

    # ------------------------------------------------------------------
    @property
    def modelo_texto(self) -> str:
        raise NotImplementedError

    @property
    def modelo_ligero(self) -> str:
        raise NotImplementedError

    @property
    def modelo_embeddings(self) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------
    async def disponible(self) -> bool:
        """Sin configuración → falso (NO es un error: es su estado normal)."""
        if self._falta_configuracion():
            return False
        try:
            cliente = self._obtener_cliente(_TIMEOUT_SALUD_SEG)
            respuesta = await cliente.get(self._url_salud())
            return respuesta.status_code == 200
        except httpx.HTTPError:
            return False

    def _url_salud(self) -> str:
        raise NotImplementedError


# ======================================================================
# Respaldo 1: servidor compatible con la API de OpenAI
# ======================================================================
class OpenAICompatProvider(_RespaldoBase):
    """Habla con {OPENAI_COMPAT_BASE_URL} usando el dialecto OpenAI."""

    nombre = "openai_compat"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        super().__init__(settings, transport)
        self._base_url = (self.settings.OPENAI_COMPAT_BASE_URL or "").rstrip("/")
        self._api_key = self.settings.OPENAI_COMPAT_API_KEY or ""

    # ------------------------------------------------------------------
    @property
    def modelo_texto(self) -> str:
        return self.settings.OPENAI_COMPAT_MODEL

    @property
    def modelo_ligero(self) -> str:
        # El respaldo no distingue motor grande/liviano: usa el principal
        return self.settings.OPENAI_COMPAT_MODEL

    @property
    def modelo_embeddings(self) -> str:
        # Mismo modelo de chat para embeddings (el despliegue lo ajusta)
        return self.settings.OPENAI_COMPAT_MODEL

    def _falta_configuracion(self) -> Optional[str]:
        if not self._base_url:
            return "OPENAI_COMPAT_BASE_URL"
        return None

    def _encabezados(self) -> Dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def _url_salud(self) -> str:
        return f"{self._base_url}/models"

    # ------------------------------------------------------------------
    async def generar_chat(
        self,
        mensajes: List[Dict[str, str]],
        modelo: Optional[str] = None,
        temperatura: float = 0.2,
    ) -> RespuestaProveedorIA:
        self._si_no_configurado()
        self._validar_mensajes(mensajes)
        modelo = modelo or self.modelo_para("agente")
        cliente = self._obtener_cliente(float(self.settings.IA_TIMEOUT_SECONDS))

        cuerpo: Dict[str, Any] = {
            "model": modelo,
            "messages": mensajes,  # formato OpenAI nativo
            "temperature": temperatura,
        }
        inicio = self._medir()
        try:
            respuesta = await cliente.post(
                f"{self._base_url}/chat/completions",
                json=cuerpo,
                headers=self._encabezados(),
            )
        except httpx.HTTPError as exc:
            raise self._envolver_falla_red(exc, self.nombre) from exc

        if respuesta.status_code >= 500:
            raise IAIndisponibleError(
                f"{self.nombre} respondió {respuesta.status_code} en /chat/completions"
            )
        if respuesta.status_code >= 400:
            raise ErrorIA(
                f"{self.nombre} rechazó la petición (HTTP {respuesta.status_code}): "
                f"{respuesta.text[:300]}"
            )

        datos = respuesta.json()
        try:
            texto = (datos["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            raise ErrorIA(
                f"Respuesta de {self.nombre} sin 'choices[0].message.content'"
            ) from None
        if not texto:
            raise ErrorIA(f"{self.nombre} devolvió una respuesta vacía")

        uso = datos.get("usage") or {}
        return RespuestaProveedorIA(
            texto=texto,
            modelo=datos.get("model", modelo),
            proveedor=self.nombre,
            tokens_prompt=uso.get("prompt_tokens"),
            tokens_respuesta=uso.get("completion_tokens"),
            latencia_seg=self._latencia(inicio),
            crudo=datos,
        )

    # ------------------------------------------------------------------
    async def incrustar(
        self, texto: str, modelo: Optional[str] = None
    ) -> RespuestaEmbeddingsIA:
        self._si_no_configurado()
        if not texto or not texto.strip():
            raise ErrorIA("No se puede calcular el embedding de un texto vacío")
        modelo = modelo or self.modelo_embeddings
        cliente = self._obtener_cliente(float(self.settings.IA_TIMEOUT_SECONDS))

        try:
            respuesta = await cliente.post(
                f"{self._base_url}/embeddings",
                json={"model": modelo, "input": [texto]},
                headers=self._encabezados(),
            )
        except httpx.HTTPError as exc:
            raise self._envolver_falla_red(exc, self.nombre) from exc

        if respuesta.status_code >= 500:
            raise IAIndisponibleError(
                f"{self.nombre} respondió {respuesta.status_code} en /embeddings"
            )
        if respuesta.status_code >= 400:
            raise ErrorIA(
                f"{self.nombre} rechazó el pedido de embeddings (HTTP {respuesta.status_code})"
            )

        datos = respuesta.json()
        try:
            vector = datos["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError):
            raise ErrorIA(
                f"Respuesta de embeddings de {self.nombre} sin 'data[0].embedding'"
            ) from None
        return RespuestaEmbeddingsIA(
            vector=[float(x) for x in vector],
            modelo=modelo,
            proveedor=self.nombre,
        )


# ======================================================================
# Respaldo 2: Gemini en la nube
# ======================================================================
class GeminiProvider(_RespaldoBase):
    """Habla con la API de Gemini (generativelanguage.googleapis.com)."""

    nombre = "gemini"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        super().__init__(settings, transport)
        self._api_key = self.settings.GEMINI_API_KEY or ""

    # ------------------------------------------------------------------
    @property
    def modelo_texto(self) -> str:
        return self.settings.GEMINI_MODEL

    @property
    def modelo_ligero(self) -> str:
        return self.settings.GEMINI_MODEL

    @property
    def modelo_embeddings(self) -> str:
        # Modelo de embeddings de Gemini (texto → vector)
        return "text-embedding-004"

    def _falta_configuracion(self) -> Optional[str]:
        if not self._api_key:
            return "GEMINI_API_KEY"
        return None

    def _url_salud(self) -> str:
        return f"{_BASE_GEMINI}/models"

    # Esquema de autenticación: la API de Gemini recibe la clave en el
    # header x-goog-api-key (por llamada), no en el cuerpo ni en la URL.

    # ------------------------------------------------------------------
    @staticmethod
    def _a_contents_y_system(mensajes: List[Dict[str, str]]):
        """
        Formato OpenAI → formato Gemini:
        - 'system'     → systemInstruction (fuera de contents),
        - 'assistant'  → role 'model',
        - 'user'       → role 'user'.
        """
        sistema: Optional[str] = None
        contents: List[Dict[str, Any]] = []
        for m in mensajes:
            if m["role"] == "system":
                sistema = (sistema + "\n\n" if sistema else "") + m["content"]
            else:
                contents.append(
                    {
                        "role": "model" if m["role"] == "assistant" else "user",
                        "parts": [{"text": m["content"]}],
                    }
                )
        return contents, sistema

    # ------------------------------------------------------------------
    async def generar_chat(
        self,
        mensajes: List[Dict[str, str]],
        modelo: Optional[str] = None,
        temperatura: float = 0.2,
    ) -> RespuestaProveedorIA:
        self._si_no_configurado()
        self._validar_mensajes(mensajes)
        modelo = modelo or self.modelo_para("agente")
        cliente = self._obtener_cliente(float(self.settings.IA_TIMEOUT_SECONDS))

        contents, sistema = self._a_contents_y_system(mensajes)
        cuerpo: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperatura},
        }
        if sistema:
            cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}

        inicio = self._medir()
        try:
            respuesta = await cliente.post(
                f"{_BASE_GEMINI}/models/{modelo}:generateContent",
                json=cuerpo,
                headers={"x-goog-api-key": self._api_key},
            )
        except httpx.HTTPError as exc:
            raise self._envolver_falla_red(exc, self.nombre) from exc

        if respuesta.status_code >= 500:
            raise IAIndisponibleError(
                f"{self.nombre} respondió {respuesta.status_code} en generateContent"
            )
        if respuesta.status_code >= 400:
            raise ErrorIA(
                f"{self.nombre} rechazó la petición (HTTP {respuesta.status_code}): "
                f"{respuesta.text[:300]}"
            )

        datos = respuesta.json()
        # Bloqueo de seguridad o sin candidatos → el motor respondió, pero
        # no hay texto: NO conmuta (otro motor no cambia el filtro).
        if datos.get("promptFeedback", {}).get("blockReason"):
            raise ErrorIA(
                f"Gemini bloqueó el prompt: {datos['promptFeedback']['blockReason']}"
            )
        candidatos = datos.get("candidates") or []
        if not candidatos:
            raise ErrorIA("Gemini devolvió la respuesta sin 'candidates'")

        partes = (candidatos[0].get("content") or {}).get("parts") or []
        texto = "".join(p.get("text", "") for p in partes).strip()
        if not texto:
            raise ErrorIA("Gemini devolvió una respuesta vacía (sin parts.text)")

        uso = datos.get("usageMetadata") or {}
        return RespuestaProveedorIA(
            texto=texto,
            modelo=modelo,
            proveedor=self.nombre,
            tokens_prompt=uso.get("promptTokenCount"),
            tokens_respuesta=uso.get("candidatesTokenCount"),
            latencia_seg=self._latencia(inicio),
            crudo=datos,
        )

    # ------------------------------------------------------------------
    async def incrustar(
        self, texto: str, modelo: Optional[str] = None
    ) -> RespuestaEmbeddingsIA:
        self._si_no_configurado()
        if not texto or not texto.strip():
            raise ErrorIA("No se puede calcular el embedding de un texto vacío")
        modelo = modelo or self.modelo_embeddings
        cliente = self._obtener_cliente(float(self.settings.IA_TIMEOUT_SECONDS))

        try:
            respuesta = await cliente.post(
                f"{_BASE_GEMINI}/models/{modelo}:embedContent",
                json={"content": {"parts": [{"text": texto}]}},
                headers={"x-goog-api-key": self._api_key},
            )
        except httpx.HTTPError as exc:
            raise self._envolver_falla_red(exc, self.nombre) from exc

        if respuesta.status_code >= 500:
            raise IAIndisponibleError(
                f"{self.nombre} respondió {respuesta.status_code} en embedContent"
            )
        if respuesta.status_code >= 400:
            raise ErrorIA(
                f"{self.nombre} rechazó el pedido de embeddings (HTTP {respuesta.status_code})"
            )

        datos = respuesta.json()
        vector = (datos.get("embedding") or {}).get("values")
        if not isinstance(vector, list) or not vector:
            raise ErrorIA(
                f"Respuesta de embeddings de {self.nombre} sin 'embedding.values'"
            )
        return RespuestaEmbeddingsIA(
            vector=[float(x) for x in vector],
            modelo=modelo,
            proveedor=self.nombre,
        )


# (Sin código tras las clases: la autenticación de Gemini viaja en el
#  header x-goog-api-key de cada llamada, ver arriba.)