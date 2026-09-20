# app/repositories/usuario_repository.py
"""
Repositorio de acceso a datos para el módulo A. Usuarios y Seguridad.

No contiene lógica de negocio (eso es `services/auth_service.py`).
Solo operaciones atómicas sobre la tabla `usuarios`.
"""

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usuario import Usuario


class UsuarioRepository:
    """Operaciones CRUD y consultas sobre `usuarios`."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, usuario_id: int) -> Optional[Usuario]:
        result = await self.db.execute(
            select(Usuario).where(Usuario.id == usuario_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[Usuario]:
        result = await self.db.execute(
            select(Usuario).where(func.lower(Usuario.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        solo_activos: bool = False,
    ) -> Sequence[Usuario]:
        stmt = select(Usuario).order_by(Usuario.created_at.desc())
        if solo_activos:
            stmt = stmt.where(Usuario.activo.is_(True))
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def count(self, *, solo_activos: bool = False) -> int:
        stmt = select(func.count(Usuario.id))
        if solo_activos:
            stmt = stmt.where(Usuario.activo.is_(True))
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def email_exists(self, email: str, *, exclude_id: Optional[int] = None) -> bool:
        stmt = select(Usuario.id).where(func.lower(Usuario.email) == email.lower())
        if exclude_id is not None:
            stmt = stmt.where(Usuario.id != exclude_id)
        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, usuario: Usuario) -> Usuario:
        self.db.add(usuario)
        await self.db.flush()   # asigna id sin cerrar la transacción
        await self.db.refresh(usuario)
        return usuario

    async def update(self, usuario: Usuario) -> Usuario:
        await self.db.flush()
        await self.db.refresh(usuario)
        return usuario

    async def delete(self, usuario: Usuario) -> None:
        await self.db.delete(usuario)
        await self.db.flush()

    async def set_activo(self, usuario_id: int, activo: bool) -> Optional[Usuario]:
        usuario = await self.get_by_id(usuario_id)
        if usuario is None:
            return None
        usuario.activo = activo
        await self.db.flush()
        await self.db.refresh(usuario)
        return usuario