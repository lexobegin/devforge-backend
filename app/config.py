# app/config.py
"""
Configuración central de DevForge AI (backend FastAPI).

Carga las variables de entorno desde el archivo .env correspondiente
al entorno activo (desarrollo o producción) usando Pydantic Settings v2.
"""

from functools import lru_cache
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------
    # Servidor
    # ------------------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # Dominio público del backend (usado en CORS, docs, generación de URLs)
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"

    # ------------------------------------------------------------------
    # Base de datos (PostgreSQL async)
    # ------------------------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "12345"
    POSTGRES_DB: str = "devforge_db"

    # Pool de conexiones
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

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
    # Lista separada por comas en .env, ej: "http://localhost:5173,https://app.devforge.ai"
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # ------------------------------------------------------------------
    # WebSocket (colaboración en tiempo real)
    # ------------------------------------------------------------------
    WS_HEARTBEAT_INTERVAL: int = 30          # segundos entre pings
    WS_MAX_CONNECTIONS_PER_DIAGRAMA: int = 50

    # ------------------------------------------------------------------
    # Generación automática de código (Capa 2)
    # ------------------------------------------------------------------
    GENERATED_PROJECTS_DIR: str = "generated_projects"
    GENERATED_BACKEND_GROUP_ID: str = "com.devforge.generated"
    GENERATED_BACKEND_ARTIFACT_PREFIX: str = "backend"
    GENERATED_BACKEND_JAVA_VERSION: str = "17"
    GENERATED_BACKEND_SPRING_BOOT_VERSION: str = "3.2.5"
    GENERATED_BACKEND_POSTGRES_VERSION: str = "15"

    # ------------------------------------------------------------------
    # IA (nube, modo online)
    # ------------------------------------------------------------------
    AI_PROVIDER: str = "internal"            # "internal", "openai", ...
    AI_API_KEY: str = ""
    AI_MODEL_TEXT: str = "gpt-4o-mini"
    AI_MODEL_VISION: str = "gpt-4o"
    AI_TIMEOUT_SECONDS: int = 30

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
        """Permite definir listas como cadena separada por comas en el .env."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # ------------------------------------------------------------------
    # Propiedades derivadas
    # ------------------------------------------------------------------
    @property
    def DATABASE_URL(self) -> str:
        """URL async (asyncpg) para SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """URL sync (psycopg2) — útil para Alembic."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de Settings."""
    return Settings()


# Alias cómodo para importar directo
settings = get_settings()