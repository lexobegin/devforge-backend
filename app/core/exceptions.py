# app/core/exceptions.py
"""
Excepciones de dominio y sus manejadores FastAPI — CICLO 2.

RECONVERTIDO del Ciclo 1 conservando el CONTRATO COMPLETO:
- Las 8 excepciones de dominio con los mismos nombres, status y códigos
  (NotFoundError, BadRequestError, UnauthorizedError, ForbiddenError,
  ConflictError, ValidationError, GenerationError, AIServiceError) y la
  misma firma: X("mensaje") con error_code/extra opcionales.
- Respuesta JSON uniforme: {"error", "detail", "path", "extra"}.

Cambios del Ciclo 2 (justificados, sin tocar a los services):
- FUERA los manejadores de IntegrityError/SQLAlchemyError (no existe
  SQLAlchemy). Su equivalente MongoDB: DuplicateKeyError de pymongo
  (violación de índice único de Beanie, p. ej. email) → 409
  DB_DUPLICATE_KEY.
- UnauthorizedError añade el header WWW-Authenticate: Bearer (lo hacía el
  manejador provisional y lo exige RFC 6750).
- El fallback genérico y los manejadores de RequestValidationError y
  HTTPException de Starlette se conservan tal cual.

Los services del Ciclo 2 (T5-T18) importan solo los nombres concretos y
construyen con un mensaje posicional: 0 cambios en ellos al reemplazar el
módulo provisional por este.
"""

from typing import Any, Dict, Optional

from bson.errors import InvalidId
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError
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
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    body: Dict[str, Any] = {
        "error": error_code,
        "detail": detail,
        "path": path,
    }
    if extra:
        body["extra"] = extra
    return JSONResponse(status_code=status_code, content=body, headers=headers)


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
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if isinstance(exc, UnauthorizedError)
            else None
        )
        return _error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            detail=exc.message,
            path=request.url.path,
            extra=exc.extra or None,
            headers=headers,
        )

    # ---------- HTTPException de Starlette/FastAPI ----------
    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        headers = getattr(exc, "headers", None)
        return _error_response(
            status_code=exc.status_code,
            error_code=f"HTTP_{exc.status_code}",
            detail=str(exc.detail),
            path=request.url.path,
            headers=headers,
        )

    # ---------- Errores de validación de Pydantic ----------
    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # jsonable_encoder OBLIGATORIO: exc.errors() trae objetos crudos en
        # ctx (el ValueError del validador, p. ej. ObjectId malformado) que
        # json.dumps no serializa — sin esto el 422 caería al fallback 500.
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            detail="Datos de entrada inválidos",
            path=request.url.path,
            extra={"errors": jsonable_encoder(exc.errors())},
        )

    # ---------- Integridad de MongoDB (equivalente del IntegrityError) ----
    @app.exception_handler(DuplicateKeyError)
    async def _handle_duplicate_key(
        request: Request, exc: DuplicateKeyError
    ) -> JSONResponse:
        # Ej: violación del índice único de email al registrar.
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            error_code="DB_DUPLICATE_KEY",
            detail="La operación viola una restricción de unicidad",
            path=request.url.path,
        )

    # ---------- ObjectId malformado en rutas/schemas ----------
    @app.exception_handler(InvalidId)
    async def _handle_invalid_id(
        request: Request, exc: InvalidId
    ) -> JSONResponse:
        # PydanticObjectId inválido: el Ciclo 1 respondía 422 cuando el id
        # de ruta no era un int; aquí el equivalente es el hex ObjectId.
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            detail="El identificador no es un ObjectId válido",
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