# app/api/v1/auth_router.py
"""
Endpoints de autenticación (módulo A. Usuarios y Seguridad) — CICLO 2.

- POST /api/v1/auth/registro        → crear cuenta
- POST /api/v1/auth/login           → iniciar sesión (devuelve tokens)
- POST /api/v1/auth/refresh         → renovar access token con refresh token
- POST /api/v1/auth/cambiar-password → cambiar contraseña del usuario actual
- GET  /api/v1/auth/me              → perfil del usuario autenticado

CICLO 2 (reconvertido del Ciclo 1): SIN AsyncSession (los services se
instancian sin sesión) y SIN commit=True en la bitácora (MongoDB no tiene
transacciones aquí: cada insert() es autónomo, igual que el commit
independiente del Ciclo 1). Los ids del payload sub son el ObjectId del
usuario en hex (str), no el int del serial.
"""

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_active_user
from app.models.usuario import Usuario
from app.schemas.usuario_schema import (
    PasswordChange,
    RefreshTokenRequest,
    TokenResponse,
    UsuarioCreate,
    UsuarioLogin,
    UsuarioResponse,
)
from app.services.auditoria_service import AuditoriaService
from app.services.auth_service import AuthService

router = APIRouter()


# ======================================================================
# POST /registro
# ======================================================================
@router.post(
    "/registro",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo usuario",
    description="Crea una cuenta nueva con email único y contraseña hasheada.",
)
async def registro(
    datos: UsuarioCreate,
) -> UsuarioResponse:
    service = AuthService()
    usuario = await service.registrar(datos)

    # Bitácora del evento (insert autónomo, como el commit=True del Ciclo 1)
    auditoria = AuditoriaService()
    await auditoria.log_registro(usuario.id)

    return usuario


# ======================================================================
# POST /login
# ======================================================================
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    description=(
        "Autentica al usuario y devuelve un par de tokens (access + refresh). "
        "El access token debe enviarse en el header `Authorization: Bearer <token>`."
    ),
)
async def login(
    datos: UsuarioLogin,
) -> TokenResponse:
    service = AuthService()
    tokens = await service.login(datos)

    # Bitácora del login
    auditoria = AuditoriaService()
    await auditoria.log_login(tokens.usuario.id)

    return tokens


# ======================================================================
# POST /refresh
# ======================================================================
@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refrescar access token",
    description="Genera un nuevo par de tokens a partir de un refresh token válido.",
)
async def refresh(
    datos: RefreshTokenRequest,
) -> TokenResponse:
    service = AuthService()
    return await service.refrescar_token(datos.refresh_token)


# ======================================================================
# POST /cambiar-password
# ======================================================================
@router.post(
    "/cambiar-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar contraseña del usuario autenticado",
    description="Verifica la contraseña actual antes de actualizar.",
)
async def cambiar_password(
    datos: PasswordChange,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = AuthService()
    await service.cambiar_password(current_user, datos)


# ======================================================================
# GET /me
# ======================================================================
@router.get(
    "/me",
    response_model=UsuarioResponse,
    summary="Perfil del usuario autenticado",
    description="Devuelve la información del usuario logueado.",
)
async def me(
    current_user: Usuario = Depends(get_current_active_user),
) -> UsuarioResponse:
    return UsuarioResponse.model_validate(current_user)