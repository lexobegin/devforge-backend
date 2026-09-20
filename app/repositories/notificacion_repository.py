# app/repositories/notificacion_repository.py
"""
Repositorio de acceso a datos del módulo I. Notificaciones:

- NotificacionRepository → tabla `notificaciones`
"""

from typing import Optional, Sequence

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notificacion import Notificacion


class NotificacionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, notificacion_id: int) -> Optional[Notificacion]:
        result = await self.db.execute(
            select(Notificacion).where(Notificacion.id == notificacion_id)
        )
        return result.scalar_one_or_none()

    async def list_by_usuario(
        self,
        usuario_id: int,
        *,
        solo_no_leidas: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Notificacion]:
        stmt = (
            select(Notificacion)
            .where(Notificacion.id_usuario == usuario_id)
            .order_by(Notificacion.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if solo_no_leidas:
            stmt = stmt.where(Notificacion.leida.is_(False))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_by_usuario_y_tipo(
        self,
        usuario_id: int,
        tipo: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Notificacion]:
        result = await self.db.execute(
            select(Notificacion)
            .where(
                Notificacion.id_usuario == usuario_id,
                Notificacion.tipo == tipo,
            )
            .order_by(Notificacion.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_no_leidas(self, usuario_id: int) -> int:
        """Contador para el badge del dropdown de notificaciones."""
        result = await self.db.execute(
            select(func.count(Notificacion.id)).where(
                Notificacion.id_usuario == usuario_id,
                Notificacion.leida.is_(False),
            )
        )
        return int(result.scalar_one())

    async def count_by_usuario(self, usuario_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Notificacion.id)).where(
                Notificacion.id_usuario == usuario_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, notificacion: Notificacion) -> Notificacion:
        self.db.add(notificacion)
        await self.db.flush()
        await self.db.refresh(notificacion)
        return notificacion

    async def bulk_create(
        self, notificaciones: list[Notificacion]
    ) -> list[Notificacion]:
        """
        Crea varias notificaciones a la vez (ej. notificar a todos los
        miembros de un proyecto cuando se completa una generación).
        """
        self.db.add_all(notificaciones)
        await self.db.flush()
        for n in notificaciones:
            await self.db.refresh(n)
        return notificaciones

    async def update(self, notificacion: Notificacion) -> Notificacion:
        await self.db.flush()
        await self.db.refresh(notificacion)
        return notificacion

    async def marcar_leida(
        self, notificacion_id: int, *, leida: bool = True
    ) -> Optional[Notificacion]:
        notificacion = await self.get_by_id(notificacion_id)
        if notificacion is None:
            return None
        notificacion.leida = leida
        await self.db.flush()
        await self.db.refresh(notificacion)
        return notificacion

    async def marcar_varias_leidas(
        self, usuario_id: int, ids: list[int]
    ) -> int:
        """
        Marca varias notificaciones del usuario como leídas de una sola vez.
        Solo afecta a las que pertenecen al usuario (defensa contra IDs ajenos).
        Devuelve cuántas filas se actualizaron.
        """
        if not ids:
            return 0
        result = await self.db.execute(
            sa_update(Notificacion)
            .where(
                Notificacion.id_usuario == usuario_id,
                Notificacion.id.in_(ids),
                Notificacion.leida.is_(False),
            )
            .values(leida=True)
        )
        await self.db.flush()
        return int(result.rowcount or 0)

    async def marcar_todas_leidas(self, usuario_id: int) -> int:
        """Marca todas las notificaciones no leídas de un usuario como leídas."""
        result = await self.db.execute(
            sa_update(Notificacion)
            .where(
                Notificacion.id_usuario == usuario_id,
                Notificacion.leida.is_(False),
            )
            .values(leida=True)
        )
        await self.db.flush()
        return int(result.rowcount or 0)

    async def delete(self, notificacion: Notificacion) -> None:
        await self.db.delete(notificacion)
        await self.db.flush()

    async def delete_leidas_by_usuario(self, usuario_id: int) -> int:
        """Limpia todas las notificaciones ya leídas de un usuario."""
        from sqlalchemy import delete as sa_delete

        result = await self.db.execute(
            sa_delete(Notificacion).where(
                Notificacion.id_usuario == usuario_id,
                Notificacion.leida.is_(True),
            )
        )
        await self.db.flush()
        return int(result.rowcount or 0)