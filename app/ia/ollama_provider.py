# app/ia/ollama_provider.py
"""
Proveedor principal de IA: Ollama LOCAL en la misma VM — CICLO 2.

NUEVO en el Ciclo 2: la IA pasa de nube a LOCAL (sin costo por token, sin
enviar el código del usuario fuera del servidor). Este proveedor habla con
la REST API de Ollama vía httpx:
- POST /api/chat       → generación conversacional (stream=False),
- POST /api/embeddings → vectores para el contexto persistente (CU17),
- GET  /api/tags       → salud barata (modelos cargados).

Modelos configurados (sección IA_* / OLLAMA_* del config):
- OLLAMA_MODEL_TEXT       'qwen2.5:7b'      → Agente Dev (CU16-CU21)
- OLLAMA_MODEL_LIGERO     'llama3.2:3b'     → Asistente Guía (CU23)
- OLLAMA_MODEL_EMBEDDINGS 'nomic-embed-text'→ embeddings (CU17)

Manejo de errores (contrato de la ABC):
- httpx timeout/conexión o HTTP >= 500  → IAIndisponibleError (conmutar).
- HTTP 4xx o payload inesperado         → ErrorIA (no conmuta).
- `disponible()` NUNCA lanza: devuelve bool (para prechequeos).
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

# Timeout corto SOLO para el chequeo de salud (una generación tarda mucho
# más; el timeout real lo pone OLLAMA_TIMEOUT_SECONDS)
_TIMEOUT_SALUD_SEG = 5.0


class OllamaProvider(LlmProvider):
    """Motor principal: Ollama local (http://localhost:11434 por defecto)."""

    nombre = "ollama"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        super().__init__(settings, transport)
        self._base_url = self.settings.OLLAMA_BASE_URL.rstrip("/")

    # ------------------------------------------------------------------
    # Modelos por rol (props de la ABC)
    # ------------------------------------------------------------------
    @property
    def modelo_texto(self) -> str:
        return self.settings.OLLAMA_MODEL_TEXT        # 'qwen2.5:7b'

    @property
    def modelo_ligero(self) -> str:
        return self.settings.OLLAMA_MODEL_LIGERO      # 'llama3.2:3b'

    @property
    def modelo_embeddings(self) -> str:
        return self.settings.OLLAMA_MODEL_EMBEDDINGS  # 'nomic-embed-text'

    # ------------------------------------------------------------------
    # Generación conversacional: POST /api/chat
    # ------------------------------------------------------------------
    async def generar_chat(
        self,
        mensajes: List[Dict[str, str]],
        modelo: Optional[str] = None,
        temperatura: float = 0.2,
    ) -> RespuestaProveedorIA:
        self._validar_mensajes(mensajes)
        modelo = modelo or self.modelo_para("agente")
        cliente = self._obtener_cliente(float(self.settings.OLLAMA_TIMEOUT_SECONDS))

        # Ollama acepta directamente el formato OpenAI de roles
        # (system/user/assistant); stream=False para respuesta única.
        cuerpo: Dict[str, Any] = {
            "model": modelo,
            "messages": mensajes,
            "stream": False,
            "options": {"temperature": temperatura},
        }
        inicio = self._medir()
        try:
            respuesta = await cliente.post(f"{self._base_url}/api/chat", json=cuerpo)
        except httpx.HTTPError as exc:
            raise self._envolver_falla_red(exc, "Ollama") from exc

        if respuesta.status_code >= 500:
            raise IAIndisponibleError(
                f"Ollama respondió {respuesta.status_code} (motor caído o modelo no cargado)"
            )
        if respuesta.status_code >= 400:
            raise ErrorIA(
                f"Ollama rechazó la petición (HTTP {respuesta.status_code}): "
                f"{respuesta.text[:300]}"
            )

        datos = respuesta.json()
        mensaje = datos.get("message") or {}
        texto = (mensaje.get("content") or "").strip()
        if not texto:
            raise ErrorIA("Ollama devolvió una respuesta vacía (sin 'message.content')")

        # Contadores de tokens propios de Ollama
        return RespuestaProveedorIA(
            texto=texto,
            modelo=datos.get("model", modelo),
            proveedor=self.nombre,
            tokens_prompt=datos.get("prompt_eval_count"),
            tokens_respuesta=datos.get("eval_count"),
            latencia_seg=self._latencia(inicio),
            crudo=datos,
        )

    # ------------------------------------------------------------------
    # Embeddings: POST /api/embeddings
    # ------------------------------------------------------------------
    async def incrustar(
        self, texto: str, modelo: Optional[str] = None
    ) -> RespuestaEmbeddingsIA:
        if not texto or not texto.strip():
            raise ErrorIA("No se puede calcular el embedding de un texto vacío")
        modelo = modelo or self.modelo_embeddings
        cliente = self._obtener_cliente(float(self.settings.OLLAMA_TIMEOUT_SECONDS))

        try:
            respuesta = await cliente.post(
                f"{self._base_url}/api/embeddings",
                json={"model": modelo, "prompt": texto},
            )
        except httpx.HTTPError as exc:
            raise self._envolver_falla_red(exc, "Ollama") from exc

        if respuesta.status_code >= 500:
            raise IAIndisponibleError(
                f"Ollama respondió {respuesta.status_code} en /api/embeddings"
            )
        if respuesta.status_code >= 400:
            raise ErrorIA(
                f"Ollama rechazó el pedido de embeddings (HTTP {respuesta.status_code})"
            )

        datos = respuesta.json()
        vector = datos.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise ErrorIA("Respuesta de embeddings de Ollama sin 'embedding' (vector)")
        return RespuestaEmbeddingsIA(
            vector=[float(x) for x in vector],
            modelo=modelo,
            proveedor=self.nombre,
        )

    # ------------------------------------------------------------------
    # Salud: GET /api/tags (lista de modelos instalados)
    # ------------------------------------------------------------------
    async def disponible(self) -> bool:
        try:
            cliente = self._obtener_cliente(_TIMEOUT_SALUD_SEG)
            respuesta = await cliente.get(f"{self._base_url}/api/tags")
            return respuesta.status_code == 200
        except httpx.HTTPError:
            return False

    def __repr__(self) -> str:
        return (
            f"<OllamaProvider base={self._base_url!r} texto={self.modelo_texto!r} "
            f"ligero={self.modelo_ligero!r} embeddings={self.modelo_embeddings!r}>"
        )