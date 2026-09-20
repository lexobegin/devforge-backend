# app/services/auth_service.py
"""
Lógica de negocio de autenticación (módulo A. Usuarios y Seguridad):

- Registro de nuevos usuarios
- Login (email + password) → emisión de access + refresh tokens
- Refresh de access token a partir de un refresh token válido
- Cambio de contraseña por el propio usuario autenticado

Regla de la capa de servicios: aquí SÍ se hace commit().
Los repositorios solo hacen flush().
"""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.usuario import Usuario
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.usuario_schema import (
    PasswordChange,
    TokenResponse,
    UsuarioCreate,
    UsuarioLogin,
    UsuarioResponse,
)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.usuarios = UsuarioRepository(db)

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    async def registrar(self, datos: UsuarioCreate) -> UsuarioResponse:
        """
        Crea un nuevo usuario.
        - Verifica que el email no exista.
        - Hashea la contraseña antes de persistir.
        """
        if await self.usuarios.email_exists(datos.email):
            raise ConflictError("Ya existe un usuario registrado con ese email")

        usuario = Usuario(
            nombre_completo=datos.nombre_completo.strip(),
            email=datos.email.lower().strip(),
            password_hash=hash_password(datos.password),
            rol=datos.rol,
            activo=True,
        )

        usuario = await self.usuarios.create(usuario)
        await self.db.commit()
        await self.db.refresh(usuario)

        return UsuarioResponse.model_validate(usuario)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def login(self, datos: UsuarioLogin) -> TokenResponse:
        """
        Autentica al usuario y emite access + refresh token.
        """
        usuario = await self.usuarios.get_by_email(datos.email)

        # Mensaje genérico para no filtrar si el email existe o no.
        if usuario is None or not verify_password(datos.password, usuario.password_hash):
            raise UnauthorizedError("Credenciales inválidas")

        if not usuario.activo:
            raise ForbiddenError("La cuenta está desactivada")

        return self._emitir_tokens(usuario)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def refrescar_token(self, refresh_token: str) -> TokenResponse:
        """
        Genera un nuevo par de tokens a partir de un refresh token válido.
        El refresh token debe ser de tipo 'refresh' y pertenecer a un usuario activo.
        """
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise UnauthorizedError("Refresh token inválido o expirado")

        if payload.get("type") != TOKEN_TYPE_REFRESH:
            raise UnauthorizedError("El token enviado no es un refresh token")

        sub = payload.get("sub")
        if not sub:
            raise UnauthorizedError("Refresh token inválido")

        try:
            usuario_id = int(sub)
        except (TypeError, ValueError):
            raise UnauthorizedError("Refresh token inválido")

        usuario = await self.usuarios.get_by_id(usuario_id)
        if usuario is None:
            raise UnauthorizedError("Usuario no encontrado")

        if not usuario.activo:
            raise ForbiddenError("La cuenta está desactivada")

        return self._emitir_tokens(usuario)

    # ------------------------------------------------------------------
    # Cambio de contraseña (usuario autenticado)
    # ------------------------------------------------------------------
    async def cambiar_password(
        self, usuario: Usuario, datos: PasswordChange
    ) -> None:
        """
        Cambia la contraseña del usuario autenticado.
        Verifica primero la contraseña actual.
        """
        if not verify_password(datos.password_actual, usuario.password_hash):
            raise BadRequestError("La contraseña actual no es correcta")

        if datos.password_actual == datos.password_nueva:
            raise BadRequestError(
                "La nueva contraseña debe ser distinta a la actual"
            )

        usuario.password_hash = hash_password(datos.password_nueva)
        await self.usuarios.update(usuario)
        await self.db.commit()

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    def _emitir_tokens(self, usuario: Usuario) -> TokenResponse:
        """Construye la respuesta estándar con access + refresh token."""
        access = create_access_token(
            subject=usuario.id,
            extra_claims={
                "email": usuario.email,
                "rol": usuario.rol,
            },
        )
        refresh = create_refresh_token(subject=usuario.id)

        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            usuario=UsuarioResponse.model_validate(usuario),
        )