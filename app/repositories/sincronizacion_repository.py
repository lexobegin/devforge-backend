# app/repositories/sincronizacion_repository.py
"""
Repositorio de acceso a datos del módulo H. Sincronización Móvil/Web Offline:

- ColaSincronizacionRepository → tabla `cola_sincronizacion_movil`
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sincronizacion import ColaSincronizacionMovil


class ColaSincronizacionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, item_id: int) -> Optional[ColaSincronizacionMovil]:
        result = await self.db.execute(
            select(ColaSincronizacionMovil).where(
                ColaSincronizacionMovil.id == item_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_dispositivo_y_temporal(
        self, id_dispositivo: str, id_temporal_local: str
    ) -> Optional[ColaSincronizacionMovil]:
        """
        Busca un ítem ya registrado por su id local del dispositivo.
        Sirve para hacer idempotente el reenvío de un mismo cambio
        (si el cliente reintenta, no se duplica).
        """
        result = await self.db.execute(
            select(ColaSincronizacionMovil).where(
                ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
                ColaSincronizacionMovil.id_temporal_local == id_temporal_local,
            )
        )
        return result.scalar_one_or_none()

    async def list_pendientes_by_dispositivo(
        self, id_dispositivo: str
    ) -> Sequence[ColaSincronizacionMovil]:
        """Todos los ítems PENDIENTES de un dispositivo, en orden de llegada."""
        result = await self.db.execute(
            select(ColaSincronizacionMovil)
            .where(
                ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
                ColaSincronizacionMovil.estado == "PENDIENTE",
            )
            .order_by(ColaSincronizacionMovil.created_at.asc())
        )
        return result.scalars().all()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        estado: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ColaSincronizacionMovil]:
        stmt = (
            select(ColaSincronizacionMovil)
            .where(ColaSincronizacionMovil.id_diagrama == diagrama_id)
            .order_by(ColaSincronizacionMovil.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        if estado is not None:
            stmt = stmt.where(ColaSincronizacionMovil.estado == estado)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_by_usuario(
        self,
        usuario_id: int,
        *,
        estado: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ColaSincronizacionMovil]:
        stmt = (
            select(ColaSincronizacionMovil)
            .where(ColaSincronizacionMovil.id_usuario == usuario_id)
            .order_by(ColaSincronizacionMovil.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if estado is not None:
            stmt = stmt.where(ColaSincronizacionMovil.estado == estado)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_conflictos_by_diagrama(
        self, diagrama_id: int
    ) -> Sequence[ColaSincronizacionMovil]:
        """Ítems con estado CONFLICTO, pendientes de resolución manual."""
        result = await self.db.execute(
            select(ColaSincronizacionMovil)
            .where(
                ColaSincronizacionMovil.id_diagrama == diagrama_id,
                ColaSincronizacionMovil.estado == "CONFLICTO",
            )
            .order_by(ColaSincronizacionMovil.created_at.asc())
        )
        return result.scalars().all()

    async def count_by_estado(self, estado: str) -> int:
        result = await self.db.execute(
            select(func.count(ColaSincronizacionMovil.id)).where(
                ColaSincronizacionMovil.estado == estado
            )
        )
        return int(result.scalar_one())

    async def count_pendientes_by_dispositivo(self, id_dispositivo: str) -> int:
        result = await self.db.execute(
            select(func.count(ColaSincronizacionMovil.id)).where(
                ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
                ColaSincronizacionMovil.estado == "PENDIENTE",
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, item: ColaSincronizacionMovil
    ) -> ColaSincronizacionMovil:
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def bulk_create(
        self, items: list[ColaSincronizacionMovil]
    ) -> list[ColaSincronizacionMovil]:
        """Registra un batch completo de cambios offline de una sola vez."""
        self.db.add_all(items)
        await self.db.flush()
        for i in items:
            await self.db.refresh(i)
        return items

    async def update(
        self, item: ColaSincronizacionMovil
    ) -> ColaSincronizacionMovil:
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def marcar_sincronizado(
        self,
        item_id: int,
        *,
        cuando: Optional[datetime] = None,
    ) -> Optional[ColaSincronizacionMovil]:
        item = await self.get_by_id(item_id)
        if item is None:
            return None
        item.estado = "SINCRONIZADO"
        item.synced_at = cuando or datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def marcar_conflicto(
        self, item_id: int
    ) -> Optional[ColaSincronizacionMovil]:
        item = await self.get_by_id(item_id)
        if item is None:
            return None
        item.estado = "CONFLICTO"
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete(self, item: ColaSincronizacionMovil) -> None:
        await self.db.delete(item)
        await self.db.flush()

    async def delete_sincronizados_by_dispositivo(
        self, id_dispositivo: str
    ) -> int:
        """
        Housekeeping: elimina los ítems ya SINCRONIZADOS de un dispositivo.
        Se puede invocar periódicamente para no acumular filas.
        """
        from sqlalchemy import delete as sa_delete

        result = await self.db.execute(
            sa_delete(ColaSincronizacionMovil).where(
                ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
                ColaSincronizacionMovil.estado == "SINCRONIZADO",
            )
        )
        await self.db.flush()
        return int(result.rowcount or 0)