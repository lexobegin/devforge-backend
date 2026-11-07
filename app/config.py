# app/config.py
"""
Configuración central de DevForge AI (backend FastAPI) — CICLO 2.

Carga las variables de entorno desde el archivo .env correspondiente
al entorno activo (desarrollo o producción) usando Pydantic Settings v2.

Cambios respecto al Ciclo 1:
- PostgreSQL/SQLAlchemy → MongoDB: desaparecen POSTGRES_*, DB_POOL_* y las
  propiedades DATABASE_URL / DATABASE_URL_SYNC; entran MONGODB_URI y MONGODB_DB.
- IA local obligatoria: la sección AI_* (nube) se sustituye por la sección IA_*
  del LlmProvider — Ollama como motor principal y OpenAI-compatible / Gemini
  como respaldos conmutables (IA_PROVIDER + IA_CADENA_RESPALDO).
- Voz: nueva sección VOZ_* (transcripción local con faster-whisper).
- Visión: nueva sección VISION_* (boceto → UML COMPLETO: nombres, atributos y
  relaciones; corrige la deficiencia del Ciclo 1 de las cajas "Clase1/Clase2").
- La generación de código sigue produciendo Spring Boot + BD relacional
  (se conservan GENERATED_BACKEND_*).

Parche de la Tanda 20 (hallazgo del arnés):
- Las listas CORS_* se leían con estilo separado por comas en los .env, pero
  pydantic-settings intenta json.loads ANTES de los validators para campos
  complejos (List[str]) y lanzaba SettingsError al importar. Solución oficial:
  Annotated[List[str], NoDecode] (pydantic-settings >= 2.4) + el validator
  _split_comma_separated, que ahora tolera AMBOS estilos (comas y JSON).
"""

import json
from functools import lru_cache
from typing import Annotated, List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración tipada de la aplicación.
    Todos los valores se leen desde variables de entorno / archivo .env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Aplicación
    # ------------------------------------------------------------------
    APP_NAME: str = "DevForge AI"
    APP_ENV: Literal["development", "production", "testing"] = "development"
    APP_DEBUG: bool = True
    APP_VERSION: str = "0.2.0"
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------
    # Servidor
    # ------------------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # Dominio público del backend (usado en CORS, docs, generación de URLs)
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"

    # ------------------------------------------------------------------
    # Base de datos (MongoDB async — Ciclo 2)
    # ------------------------------------------------------------------
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "devforge_db"

    # ------------------------------------------------------------------
    # JWT / Seguridad
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str = Field(
        default="CHANGE_ME_SUPER_SECRET_KEY",
        description="Clave secreta para firmar JWT. Cambiar en producción.",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas
    JWT_REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 días

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    # NoDecode: desactiva el intento de json.loads del source de dotenv/env
    # para estas listas; el valor crudo llega al validator, que acepta AMBOS
    # estilos: "http://a,http://b" (recomendado) y ["http://a","http://b"].
    CORS_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: Annotated[List[str], NoDecode] = ["*"]
    CORS_ALLOW_HEADERS: Annotated[List[str], NoDecode] = ["*"]

    # ------------------------------------------------------------------
    # WebSocket (colaboración en tiempo real)
    # ------------------------------------------------------------------
    WS_HEARTBEAT_INTERVAL: int = 30          # segundos entre pings
    WS_MAX_CONNECTIONS_PER_DIAGRAMA: int = 50

    # ------------------------------------------------------------------
    # IA local (Ciclo 2) — LlmProvider (D28 del informe)
    #   IA_PROVIDER: motor principal → ollama | openai_compat | gemini
    #   IA_CADENA_RESPALDO: orden de conmutación si el principal falla
    # ----------------------------------------------------------------------
    IA_PROVIDER: str = "ollama"
    IA_CADENA_RESPALDO: str = "openai_compat,gemini"
    IA_TIMEOUT_SECONDS: int = 120

    # Ollama (motor principal: local, sin costo; instalado en la misma VM)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_TEXT: str = "qwen2.5:7b"              # Agente Dev (CU16-CU21)
    OLLAMA_MODEL_LIGERO: str = "llama3.2:3b"           # Asistente Guía (CU23)
    OLLAMA_MODEL_EMBEDDINGS: str = "nomic-embed-text"  # contexto persistente (CU17)
    OLLAMA_TIMEOUT_SECONDS: int = 120

    # Respaldo 1: cualquier servidor compatible con la API de OpenAI
    OPENAI_COMPAT_BASE_URL: str = ""
    OPENAI_COMPAT_API_KEY: str = ""
    OPENAI_COMPAT_MODEL: str = "gpt-4o-mini"

    # Respaldo 2: Gemini en la nube (A4)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # ------------------------------------------------------------------
    # Voz (Ciclo 2) — transcripción local con faster-whisper
    # ------------------------------------------------------------------
    VOZ_ENABLED: bool = True
    VOZ_MODELO_WHISPER: str = "base"   # base en desarrollo; small en producción
    VOZ_IDIOMA: str = "es"

    # ------------------------------------------------------------------
    # Visión (boceto → UML completo; corrige el Punto 1 del Ciclo 1)
    #   OpenCV + Tesseract detectan candidatos; el LLM local los interpreta
    #   en un modelo estructurado (nombre real, atributos y relaciones)
    # ------------------------------------------------------------------
    VISION_USAR_IA_LOCAL: bool = True
    VISION_MAX_CLASES: int = 30

    # ------------------------------------------------------------------
    # Generación automática de código (Capa 2)
    # (los productos generados siguen siendo Spring Boot + BD relacional)
    # ------------------------------------------------------------------
    GENERATED_PROJECTS_DIR: str = "generated_projects"
    GENERATED_BACKEND_GROUP_ID: str = "com.devforge.generated"
    GENERATED_BACKEND_ARTIFACT_PREFIX: str = "backend"
    GENERATED_BACKEND_JAVA_VERSION: str = "17"
    GENERATED_BACKEND_SPRING_BOOT_VERSION: str = "3.2.5"
    GENERATED_BACKEND_POSTGRES_VERSION: str = "15"

    # ------------------------------------------------------------------
    # Almacenamiento / archivos
    # ------------------------------------------------------------------
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 20
    EXPORT_DIR: str = "exports"

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    # ------------------------------------------------------------------
    # Validadores
    # ------------------------------------------------------------------
    @field_validator("CORS_ORIGINS", "CORS_ALLOW_METHODS", "CORS_ALLOW_HEADERS", mode="before")
    @classmethod
    def _split_comma_separated(cls, value):
        """Acepta listas como cadena separada por comas en el .env (y también JSON)."""
        if isinstance(value, str):
            texto = value.strip()
            # Tolerancia con el estilo JSON del Ciclo 1 (OS env o .env viejo)
            if texto.startswith("["):
                try:
                    parsed = json.loads(texto)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:  # noqa: BLE001 — cae al split por comas
                    pass
            return [item.strip() for item in texto.split(",") if item.strip()]
        return value

    # ------------------------------------------------------------------
    # Propiedades derivadas
    # ------------------------------------------------------------------
    @property
    def IS_PRODUCTION(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def IA_CADENA_COMPLETA(self) -> List[str]:
        """Cadena completa de motores IA: principal + respaldos, en orden."""
        return [self.IA_PROVIDER] + [
            p for p in
            (x.strip() for x in self.IA_CADENA_RESPALDO.split(","))
            if p and p != self.IA_PROVIDER
        ]

    @property
    def MAX_UPLOAD_SIZE_BYTES(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de Settings."""
    return Settings()


# Alias cómodo para importar directo
settings = get_settings()
