# app/repositories/trazabilidad_repository.py
"""
Repositorio de acceso a datos del módulo D. Trazabilidad:

- HistorialCambioRepository     → tabla `historial_cambios_diagrama`
- VersionDiagramaRepository     → tabla `versiones_diagrama`
- ComentarioDiagramaRepository  → tabla `comentarios_diagrama`
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trazabilidad import (
    ComentarioDiagrama,
    HistorialCambioDiagrama,
    VersionDiagrama,
)


# ======================================================================
# HistorialCambioRepository
# ======================================================================
class HistorialCambioRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, cambio_id: int) -> Optional[HistorialCambioDiagrama]:
        result = await self.db.execute(
            select(HistorialCambioDiagrama).where(
                HistorialCambioDiagrama.id == cambio_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> Sequence[HistorialCambioDiagrama]:
        """
        Historial de un diagrama ordenado del cambio más reciente al más antiguo.
        Permite filtrar por rango de fechas.
        """
        stmt = (
            select(HistorialCambioDiagrama)
            .where(HistorialCambioDiagrama.id_diagrama == diagrama_id)
            .order_by(HistorialCambioDiagrama.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if desde is not None:
            stmt = stmt.where(HistorialCambioDiagrama.created_at >= desde)
        if hasta is not None:
            stmt = stmt.where(HistorialCambioDiagrama.created_at <= hasta)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_by_entidad(
        self,
        diagrama_id: int,
        tipo_entidad: str,
        id_entidad: int,
    ) -> Sequence[HistorialCambioDiagrama]:
        """
        Historial de un elemento concreto (ej. una clase), útil para
        reconstruir sus cambios a lo largo del tiempo.
        """
        result = await self.db.execute(
            select(HistorialCambioDiagrama)
            .where(
                HistorialCambioDiagrama.id_diagrama == diagrama_id,
                HistorialCambioDiagrama.tipo_entidad == tipo_entidad,
                HistorialCambioDiagrama.id_entidad == id_entidad,
            )
            .order_by(HistorialCambioDiagrama.created_at.desc())
        )
        return result.scalars().all()

    async def count_by_diagrama(self, diagrama_id: int) -> int:
        result = await self.db.execute(
            select(func.count(HistorialCambioDiagrama.id)).where(
                HistorialCambioDiagrama.id_diagrama == diagrama_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, cambio: HistorialCambioDiagrama
    ) -> HistorialCambioDiagrama:
        self.db.add(cambio)
        await self.db.flush()
        await self.db.refresh(cambio)
        return cambio

    async def delete(self, cambio: HistorialCambioDiagrama) -> None:
        await self.db.delete(cambio)
        await self.db.flush()


# ======================================================================
# VersionDiagramaRepository
# ======================================================================
class VersionDiagramaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, version_id: int) -> Optional[VersionDiagrama]:
        result = await self.db.execute(
            select(VersionDiagrama).where(VersionDiagrama.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_by_diagrama_numero(
        self, diagrama_id: int, numero_version: int
    ) -> Optional[VersionDiagrama]:
        result = await self.db.execute(
            select(VersionDiagrama).where(
                VersionDiagrama.id_diagrama == diagrama_id,
                VersionDiagrama.numero_version == numero_version,
            )
        )
        return result.scalar_one_or_none()

    async def get_ultima_by_diagrama(
        self, diagrama_id: int
    ) -> Optional[VersionDiagrama]:
        """Devuelve la versión más alta guardada de un diagrama."""
        result = await self.db.execute(
            select(VersionDiagrama)
            .where(VersionDiagrama.id_diagrama == diagrama_id)
            .order_by(VersionDiagrama.numero_version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[VersionDiagrama]:
        result = await self.db.execute(
            select(VersionDiagrama)
            .where(VersionDiagrama.id_diagrama == diagrama_id)
            .order_by(VersionDiagrama.numero_version.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_by_diagrama(self, diagrama_id: int) -> int:
        result = await self.db.execute(
            select(func.count(VersionDiagrama.id)).where(
                VersionDiagrama.id_diagrama == diagrama_id
            )
        )
        return int(result.scalar_one())

    async def next_numero_version(self, diagrama_id: int) -> int:
        """
        Siguiente número correlativo para una nueva versión del diagrama.
        Usa COALESCE(MAX, 0) + 1.
        """
        result = await self.db.execute(
            select(
                func.coalesce(func.max(VersionDiagrama.numero_version), 0)
            ).where(VersionDiagrama.id_diagrama == diagrama_id)
        )
        return int(result.scalar_one()) + 1

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, version: VersionDiagrama) -> VersionDiagrama:
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(version)
        return version

    async def delete(self, version: VersionDiagrama) -> None:
        await self.db.delete(version)
        await self.db.flush()

    async def delete_versiones_antiguas(
        self,
        diagrama_id: int,
        *,
        conservar_ultimas: int = 50,
    ) -> int:
        """
        Conserva solo las N versiones más recientes de un diagrama.
        Devuelve cuántas versiones eliminó.
        """
        # IDs de las que se conservan
        subq = (
            select(VersionDiagrama.id)
            .where(VersionDiagrama.id_diagrama == diagrama_id)
            .order_by(VersionDiagrama.numero_version.desc())
            .limit(conservar_ultimas)
            .subquery()
        )
        # Eliminar las que NO están en esa lista
        from sqlalchemy import delete as sa_delete

        result = await self.db.execute(
            sa_delete(VersionDiagrama).where(
                VersionDiagrama.id_diagrama == diagrama_id,
                VersionDiagrama.id.notin_(select(subq.c.id)),
            )
        )
        await self.db.flush()
        return int(result.rowcount or 0)


# ======================================================================
# ComentarioDiagramaRepository
# ======================================================================
class ComentarioDiagramaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, comentario_id: int) -> Optional[ComentarioDiagrama]:
        result = await self.db.execute(
            select(ComentarioDiagrama).where(
                ComentarioDiagrama.id == comentario_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        solo_no_resueltos: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ComentarioDiagrama]:
        stmt = (
            select(ComentarioDiagrama)
            .where(ComentarioDiagrama.id_diagrama == diagrama_id)
            .order_by(ComentarioDiagrama.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if solo_no_resueltos:
            stmt = stmt.where(ComentarioDiagrama.resuelto.is_(False))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_by_entidad(
        self,
        diagrama_id: int,
        tipo_entidad: str,
        id_entidad: int,
    ) -> Sequence[ComentarioDiagrama]:
        """
        Comentarios sobre un elemento específico (ej. una clase concreta).
        """
        result = await self.db.execute(
            select(ComentarioDiagrama)
            .where(
                ComentarioDiagrama.id_diagrama == diagrama_id,
                ComentarioDiagrama.tipo_entidad == tipo_entidad,
                ComentarioDiagrama.id_entidad == id_entidad,
            )
            .order_by(ComentarioDiagrama.created_at.desc())
        )
        return result.scalars().all()

    async def list_generales_by_diagrama(
        self, diagrama_id: int
    ) -> Sequence[ComentarioDiagrama]:
        """Comentarios generales al diagrama (sin tipo_entidad ni id_entidad)."""
        result = await self.db.execute(
            select(ComentarioDiagrama)
            .where(
                ComentarioDiagrama.id_diagrama == diagrama_id,
                ComentarioDiagrama.tipo_entidad.is_(None),
                ComentarioDiagrama.id_entidad.is_(None),
            )
            .order_by(ComentarioDiagrama.created_at.desc())
        )
        return result.scalars().all()

    async def count_no_resueltos(self, diagrama_id: int) -> int:
        result = await self.db.execute(
            select(func.count(ComentarioDiagrama.id)).where(
                ComentarioDiagrama.id_diagrama == diagrama_id,
                ComentarioDiagrama.resuelto.is_(False),
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, comentario: ComentarioDiagrama) -> ComentarioDiagrama:
        self.db.add(comentario)
        await self.db.flush()
        await self.db.refresh(comentario)
        return comentario

    async def update(self, comentario: ComentarioDiagrama) -> ComentarioDiagrama:
        await self.db.flush()
        await self.db.refresh(comentario)
        return comentario

    async def marcar_resuelto(
        self, comentario_id: int, *, resuelto: bool = True
    ) -> Optional[ComentarioDiagrama]:
        comentario = await self.get_by_id(comentario_id)
        if comentario is None:
            return None
        comentario.resuelto = resuelto
        await self.db.flush()
        await self.db.refresh(comentario)
        return comentario

    async def delete(self, comentario: ComentarioDiagrama) -> None:
        await self.db.delete(comentario)
        await self.db.flush()