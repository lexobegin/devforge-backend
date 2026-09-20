# app/repositories/auditoria_repository.py
"""
Repositorio de acceso a datos del módulo de Auditoría:

- BitacoraRepository → tabla `bitacora_sistema`
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditoria import BitacoraSistema


class BitacoraRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, evento_id: int) -> Optional[BitacoraSistema]:
        result = await self.db.execute(
            select(BitacoraSistema).where(BitacoraSistema.id == evento_id)
        )
        return result.scalar_one_or_none()

    async def list_paginado(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        id_usuario: Optional[int] = None,
        tipo_evento: Optional[str] = None,
        entidad_afectada: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> Sequence[BitacoraSistema]:
        """
        Listado con todos los filtros opcionales. Es la query que usará
        el endpoint de la bitácora del sistema (CU3) — el admin filtra
        por fecha, usuario, tipo de evento, etc.
        """
        stmt = (
            select(BitacoraSistema)
            .order_by(BitacoraSistema.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if id_usuario is not None:
            stmt = stmt.where(BitacoraSistema.id_usuario == id_usuario)
        if tipo_evento is not None:
            stmt = stmt.where(BitacoraSistema.tipo_evento == tipo_evento)
        if entidad_afectada is not None:
            stmt = stmt.where(BitacoraSistema.entidad_afectada == entidad_afectada)
        if desde is not None:
            stmt = stmt.where(BitacoraSistema.created_at >= desde)
        if hasta is not None:
            stmt = stmt.where(BitacoraSistema.created_at <= hasta)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def count_con_filtros(
        self,
        *,
        id_usuario: Optional[int] = None,
        tipo_evento: Optional[str] = None,
        entidad_afectada: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> int:
        """Conteo total respetando los mismos filtros (para paginación)."""
        stmt = select(func.count(BitacoraSistema.id))
        if id_usuario is not None:
            stmt = stmt.where(BitacoraSistema.id_usuario == id_usuario)
        if tipo_evento is not None:
            stmt = stmt.where(BitacoraSistema.tipo_evento == tipo_evento)
        if entidad_afectada is not None:
            stmt = stmt.where(BitacoraSistema.entidad_afectada == entidad_afectada)
        if desde is not None:
            stmt = stmt.where(BitacoraSistema.created_at >= desde)
        if hasta is not None:
            stmt = stmt.where(BitacoraSistema.created_at <= hasta)
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def list_by_entidad(
        self,
        entidad_afectada: str,
        id_entidad_afectada: int,
    ) -> Sequence[BitacoraSistema]:
        """Historial de eventos de un recurso concreto (ej. un diagrama)."""
        result = await self.db.execute(
            select(BitacoraSistema)
            .where(
                BitacoraSistema.entidad_afectada == entidad_afectada,
                BitacoraSistema.id_entidad_afectada == id_entidad_afectada,
            )
            .order_by(BitacoraSistema.created_at.desc())
        )
        return result.scalars().all()

    async def list_by_usuario(
        self,
        usuario_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[BitacoraSistema]:
        result = await self.db.execute(
            select(BitacoraSistema)
            .where(BitacoraSistema.id_usuario == usuario_id)
            .order_by(BitacoraSistema.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_tipo_evento(
        self,
        tipo_evento: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[BitacoraSistema]:
        result = await self.db.execute(
            select(BitacoraSistema)
            .where(BitacoraSistema.tipo_evento == tipo_evento)
            .order_by(BitacoraSistema.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, evento: BitacoraSistema) -> BitacoraSistema:
        self.db.add(evento)
        await self.db.flush()
        await self.db.refresh(evento)
        return evento

    async def delete(self, evento: BitacoraSistema) -> None:
        await self.db.delete(evento)
        await self.db.flush()