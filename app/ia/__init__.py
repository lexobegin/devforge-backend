# app/ia/__init__.py
"""
Paquete de IA de DevForge AI — CICLO 2 (módulo G).

NUEVO en el Ciclo 2: la infraestructura de IA local, bajo los services.
Nada aquí toca la base de datos ni contiene lógica de negocio; es la
capa que los services del módulo G (canal, gestor de contexto,
orquestador del Agente Dev, ejecutor de acciones, Asistente Guía,
generador frontend) consumen para hablar con los motores:

- llm_provider.py       → ABC LlmProvider + errores (ErrorIA,
                          IAIndisponibleError) + respuestas uniformes +
                          construir_cadena() (factory de la cadena de
                          conmutación definida en config: IA_PROVIDER +
                          IA_CADENA_RESPALDO).
- ollama_provider.py    → motor PRINCIPAL local: qwen2.5:7b (Agente Dev
                          CU16-CU21), llama3.2:3b (Guía CU23) y
                          nomic-embed-text (embeddings CU17), por REST
                          httpx (/api/chat, /api/embeddings, /api/tags).
- proveedor_respaldo.py → respaldos conmutables: OpenAICompatProvider
                          (cualquier servidor compatible OpenAI) y
                          GeminiProvider (nube, A4).
- embeddings.py         → ServicioEmbeddings: conmutación + cache LRU +
                          similitud coseno + recuperar_relevantes
                          (base del contexto persistente, CU17).
- transcriptor_voz.py   → ServicioTranscripcion: faster-whisper local
                          (audio → texto, CU16; sección VOZ_* config).
- prompts.py            → prompts de sistema (Agente Dev, Guía, Visión,
                          chat general), ensambladores de mensajes y
                          utilidades (extraer_json, estimar_tokens,
                          VOCABULARIO_ACCIONES compartido con la cola
                          offline del módulo H).

Contrato de conmutación: una falla de RED o un 5xx del motor lanza
IAIndisponibleError → el consumidor intenta con el SIGUIENTE proveedor de
la cadena; un ErrorIA no conmuta (el problema no desaparece cambiando de
motor).
"""

from app.ia.llm_provider import (
    ErrorIA,
    IAIndisponibleError,
    LlmProvider,
    RespuestaEmbeddingsIA,
    RespuestaProveedorIA,
    construir_cadena,
)
from app.ia.ollama_provider import OllamaProvider
from app.ia.proveedor_respaldo import GeminiProvider, OpenAICompatProvider
from app.ia.embeddings import ServicioEmbeddings, similitud_coseno
from app.ia.transcriptor_voz import ServicioTranscripcion, Transcripcion
from app.ia.prompts import (
    VOCABULARIO_ACCIONES,
    estimar_tokens,
    extraer_json,
    rol_a_role,
)

__all__ = [
    # Errores y contratos base
    "ErrorIA",
    "IAIndisponibleError",
    "LlmProvider",
    "RespuestaProveedorIA",
    "RespuestaEmbeddingsIA",
    "construir_cadena",
    # Motores
    "OllamaProvider",
    "OpenAICompatProvider",
    "GeminiProvider",
    # Embeddings (CU17)
    "ServicioEmbeddings",
    "similitud_coseno",
    # Voz (CU16)
    "ServicioTranscripcion",
    "Transcripcion",
    # Prompts (CU16-CU21 / CU23 / visión)
    "VOCABULARIO_ACCIONES",
    "rol_a_role",
    "extraer_json",
    "estimar_tokens",
]