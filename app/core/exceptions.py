# app/core/exceptions.py
"""
Excepciones personalizadas de DevForge AI y sus manejadores FastAPI.

Objetivo: que los routers/services puedan lanzar errores de dominio claros
(NotFound, Forbidden, Conflict, etc.) y que se traduzcan SIEMPRE a una
respuesta JSON uniforme:

    {
        "error": "NOT_FOUND",
        "detail": "El proyecto no existe",
        "path": "/api/v1/proyectos/42"
    }
"""

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException


# ======================================================================
# Excepciones de dominio
# ======================================================================
class DevForgeException(Exception):
    """Base para todas las excepciones de dominio de la plataforma."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"
    message: str = "Error interno del servidor"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        error_code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.message = message or self.message
        self.error_code = error_code or self.error_code
        self.extra = extra or {}
        super().__init__(self.message)


class NotFoundError(DevForgeException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"
    message = "Recurso no encontrado"


class BadRequestError(DevForgeException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "BAD_REQUEST"
    message = "Solicitud inválida"


class UnauthorizedError(DevForgeException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"
    message = "No autenticado"


class ForbiddenError(DevForgeException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"
    message = "No tiene permisos para realizar esta acción"


class ConflictError(DevForgeException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"
    message = "Conflicto con el estado actual del recurso"


class ValidationError(DevForgeException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"
    message = "Datos inválidos"


class GenerationError(DevForgeException):
    """Error específico del motor de generación automática de código."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "GENERATION_ERROR"
    message = "Error durante la generación automática de código"


class AIServiceError(DevForgeException):
    """Error al comunicarse con la IA (nube) o al procesar su respuesta."""
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "AI_SERVICE_ERROR"
    message = "Error al procesar la solicitud con el servicio de IA"


# ======================================================================
# Helper de respuesta uniforme
# ======================================================================
def _error_response(
    *,
    status_code: int,
    error_code: str,
    detail: str,
    path: str,
    extra: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    body: Dict[str, Any] = {
        "error": error_code,
        "detail": detail,
        "path": path,
    }
    if extra:
        body["extra"] = extra
    return JSONResponse(status_code=status_code, content=body)


# ======================================================================
# Registro de manejadores
# ======================================================================
def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos los manejadores de excepciones en la app FastAPI."""

    # -------------------- Excepciones de dominio --------------------
    @app.exception_handler(DevForgeException)
    async def _handle_devforge_exception(
        request: Request, exc: DevForgeException
    ) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            detail=exc.message,
            path=request.url.path,
            extra=exc.extra or None,
        )

    # -------------------- HTTPException de Starlette/FastAPI --------------------
    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            error_code=f"HTTP_{exc.status_code}",
            detail=str(exc.detail),
            path=request.url.path,
        )

    # -------------------- Errores de validación de Pydantic --------------------
    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            detail="Datos de entrada inválidos",
            path=request.url.path,
            extra={"errors": exc.errors()},
        )

    # -------------------- Integridad referencial de PostgreSQL --------------------
    @app.exception_handler(IntegrityError)
    async def _handle_integrity_error(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        # Ej: violación de UNIQUE(email), FK inexistente, CHECK fallido
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            error_code="DB_INTEGRITY_ERROR",
            detail="La operación viola una restricción de la base de datos",
            path=request.url.path,
        )

    # -------------------- Cualquier error de SQLAlchemy --------------------
    @app.exception_handler(SQLAlchemyError)
    async def _handle_sqlalchemy_error(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DB_ERROR",
            detail="Error al acceder a la base de datos",
            path=request.url.path,
        )

    # -------------------- Fallback genérico --------------------
    @app.exception_handler(Exception)
    async def _handle_unexpected(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_ERROR",
            detail="Error inesperado en el servidor",
            path=request.url.path,
        )