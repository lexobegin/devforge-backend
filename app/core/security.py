# app/core/security.py
"""
Seguridad de DevForge AI:
- Hash y verificación de contraseñas (bcrypt vía passlib).
- Generación y validación de tokens JWT (access y refresh).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings


# ----------------------------------------------------------------------
# Hash de contraseñas
# ----------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Devuelve el hash bcrypt de una contraseña en texto plano."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verifica que la contraseña en texto plano coincida con el hash."""
    try:
        return pwd_context.verify(plain_password, password_hash)
    except ValueError:
        # Hash inválido o corrupto
        return False


# ----------------------------------------------------------------------
# JWT
# ----------------------------------------------------------------------
# Tipos de token soportados
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def _create_token(
    *,
    subject: str | int,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Función interna: construye y firma un JWT."""
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(
    subject: str | int,
    *,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Genera un access token.
    `subject` normalmente es el id del usuario.
    `extra_claims` puede incluir rol, email, etc.
    """
    return _create_token(
        subject=subject,
        token_type=TOKEN_TYPE_ACCESS,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims=extra_claims,
    )


def create_refresh_token(subject: str | int) -> str:
    """Genera un refresh token de larga duración."""
    return _create_token(
        subject=subject,
        token_type=TOKEN_TYPE_REFRESH,
        expires_delta=timedelta(minutes=settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES),
    )


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodifica y valida un JWT.
    Lanza JWTError si el token es inválido, expirado o con firma incorrecta.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


def is_token_valid(token: str, *, expected_type: Optional[str] = None) -> bool:
    """
    Verificación rápida. Devuelve True/False sin lanzar excepciones.
    Opcionalmente valida que el token sea de un tipo específico
    ('access' o 'refresh').
    """
    try:
        payload = decode_token(token)
    except JWTError:
        return False
    if expected_type and payload.get("type") != expected_type:
        return False
    return True