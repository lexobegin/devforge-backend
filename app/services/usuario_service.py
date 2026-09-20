# app/services/usuario_service.py
"""
Lógica de negocio para la gestión administrativa de usuarios
(módulo A. Usuarios y Seguridad).

A diferencia de AuthService (registro/login/refresh), este servicio lo usa
el ADMIN de la plataforma para listar, consultar, modificar y desactivar
cuentas. El usuario puede consultar y actualizar su propio perfil.
"""

from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models.usuario import Usuario
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.usuario_schema import (
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)


class UsuarioService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.usuarios = UsuarioRepository(db)

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def listar(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        solo_activos: bool = False,
    ) -> tuple[Sequence[UsuarioResponse], int]:
        """
        Lista usuarios con paginación.
        Devuelve (items, total) para que el endpoint arme la respuesta paginada.
        """
        items = await self.usuarios.list_all(
            skip=skip, limit=limit, solo_activos=solo_activos
        )
        total = await self.usuarios.count(solo_activos=solo_activos)
        return [UsuarioResponse.model_validate(u) for u in items], total

    async def obtener(self, usuario_id: int) -> UsuarioResponse:
        usuario = await self.usuarios.get_by_id(usuario_id)
        if usuario is None:
            raise NotFoundError("Usuario no encontrado")
        return UsuarioResponse.model_validate(usuario)

    async def obtener_por_email(self, email: str) -> UsuarioResponse:
        usuario = await self.usuarios.get_by_email(email)
        if usuario is None:
            raise NotFoundError("Usuario no encontrado")
        return UsuarioResponse.model_validate(usuario)

    # ------------------------------------------------------------------
    # Creación (uso administrativo)
    # ------------------------------------------------------------------
    async def crear(self, datos: UsuarioCreate) -> UsuarioResponse:
        """
        Crear un usuario desde el panel de administración.
        Es funcionalmente similar a AuthService.registrar, pero permitimos
        que el admin cree un usuario con rol específico explícitamente.
        """
        if await self.usuarios.email_exists(datos.email):
            raise ConflictError("Ya existe un usuario con ese email")

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
    # Actualización
    # ------------------------------------------------------------------
    async def actualizar(
        self,
        usuario_id: int,
        datos: UsuarioUpdate,
        *,
        es_admin: bool = False,
        current_user_id: Optional[int] = None,
    ) -> UsuarioResponse:
        """
        Actualiza parcialmente un usuario.

        Reglas:
        - Un usuario normal solo puede actualizar su propio perfil y NO puede
          cambiar su propio `rol` ni `activo`.
        - Un ADMIN puede actualizar cualquier usuario, incluido rol y activo.
        """
        usuario = await self.usuarios.get_by_id(usuario_id)
        if usuario is None:
            raise NotFoundError("Usuario no encontrado")

        if not es_admin and current_user_id != usuario_id:
            raise ForbiddenError("No puede modificar el perfil de otro usuario")

        # --- Nombre ---
        if datos.nombre_completo is not None:
            usuario.nombre_completo = datos.nombre_completo.strip()

        # --- Email (unicidad) ---
        if datos.email is not None:
            email_nuevo = datos.email.lower().strip()
            if email_nuevo != usuario.email:
                if await self.usuarios.email_exists(email_nuevo, exclude_id=usuario.id):
                    raise ConflictError("Ya existe otro usuario con ese email")
                usuario.email = email_nuevo

        # --- Password ---
        if datos.password is not None:
            usuario.password_hash = hash_password(datos.password)

        # --- Campos sensibles: solo ADMIN ---
        if datos.rol is not None:
            if not es_admin:
                raise ForbiddenError("Solo un administrador puede cambiar el rol")
            usuario.rol = datos.rol

        if datos.activo is not None:
            if not es_admin:
                raise ForbiddenError(
                    "Solo un administrador puede activar/desactivar cuentas"
                )
            # No permitir que un admin se desactive a sí mismo (evita lockout)
            if current_user_id == usuario.id and datos.activo is False:
                raise ForbiddenError("Un administrador no puede desactivarse a sí mismo")
            usuario.activo = datos.activo

        await self.usuarios.update(usuario)
        await self.db.commit()
        await self.db.refresh(usuario)
        return UsuarioResponse.model_validate(usuario)

    # ------------------------------------------------------------------
    # Activar / desactivar (soft-disable)
    # ------------------------------------------------------------------
    async def activar(self, usuario_id: int) -> UsuarioResponse:
        usuario = await self.usuarios.set_activo(usuario_id, True)
        if usuario is None:
            raise NotFoundError("Usuario no encontrado")
        await self.db.commit()
        await self.db.refresh(usuario)
        return UsuarioResponse.model_validate(usuario)

    async def desactivar(
        self, usuario_id: int, *, current_user_id: Optional[int] = None
    ) -> UsuarioResponse:
        if current_user_id == usuario_id:
            raise ForbiddenError("Un administrador no puede desactivarse a sí mismo")

        usuario = await self.usuarios.set_activo(usuario_id, False)
        if usuario is None:
            raise NotFoundError("Usuario no encontrado")
        await self.db.commit()
        await self.db.refresh(usuario)
        return UsuarioResponse.model_validate(usuario)

    # ------------------------------------------------------------------
    # Eliminación (física) — uso excepcional
    # ------------------------------------------------------------------
    async def eliminar(self, usuario_id: int) -> None:
        """
        Eliminación física del usuario.
        Uso excepcional: en la operación normal se prefiere `desactivar()`.
        Puede fallar si el usuario tiene FKs con ondelete=RESTRICT.
        """
        usuario = await self.usuarios.get_by_id(usuario_id)
        if usuario is None:
            raise NotFoundError("Usuario no encontrado")

        await self.usuarios.delete(usuario)
        await self.db.commit()