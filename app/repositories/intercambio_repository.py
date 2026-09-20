# app/repositories/intercambio_repository.py
"""
Repositorio de acceso a datos del módulo E. Intercambio de Modelos (XMI/XML):

- ExportacionRepository → tabla `exportaciones_diagrama`
- ImportacionRepository → tabla `importaciones_diagrama`
"""

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intercambio import ExportacionDiagrama, ImportacionDiagrama


# ======================================================================
# ExportacionRepository
# ======================================================================
class ExportacionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, exportacion_id: int) -> Optional[ExportacionDiagrama]:
        result = await self.db.execute(
            select(ExportacionDiagrama).where(
                ExportacionDiagrama.id == exportacion_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ExportacionDiagrama]:
        result = await self.db.execute(
            select(ExportacionDiagrama)
            .where(ExportacionDiagrama.id_diagrama == diagrama_id)
            .order_by(ExportacionDiagrama.exported_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_usuario(
        self,
        usuario_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ExportacionDiagrama]:
        result = await self.db.execute(
            select(ExportacionDiagrama)
            .where(ExportacionDiagrama.id_usuario == usuario_id)
            .order_by(ExportacionDiagrama.exported_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_by_diagrama(self, diagrama_id: int) -> int:
        result = await self.db.execute(
            select(func.count(ExportacionDiagrama.id)).where(
                ExportacionDiagrama.id_diagrama == diagrama_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, exportacion: ExportacionDiagrama) -> ExportacionDiagrama:
        self.db.add(exportacion)
        await self.db.flush()
        await self.db.refresh(exportacion)
        return exportacion

    async def delete(self, exportacion: ExportacionDiagrama) -> None:
        await self.db.delete(exportacion)
        await self.db.flush()


# ======================================================================
# ImportacionRepository
# ======================================================================
class ImportacionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, importacion_id: int) -> Optional[ImportacionDiagrama]:
        result = await self.db.execute(
            select(ImportacionDiagrama).where(
                ImportacionDiagrama.id == importacion_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ImportacionDiagrama]:
        result = await self.db.execute(
            select(ImportacionDiagrama)
            .where(ImportacionDiagrama.id_diagrama == diagrama_id)
            .order_by(ImportacionDiagrama.imported_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_usuario(
        self,
        usuario_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ImportacionDiagrama]:
        result = await self.db.execute(
            select(ImportacionDiagrama)
            .where(ImportacionDiagrama.id_usuario == usuario_id)
            .order_by(ImportacionDiagrama.imported_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_estado(
        self,
        estado: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ImportacionDiagrama]:
        """
        Útil para reintentar importaciones fallidas o para monitoreo
        de las que están en PENDIENTE.
        """
        result = await self.db.execute(
            select(ImportacionDiagrama)
            .where(ImportacionDiagrama.estado == estado)
            .order_by(ImportacionDiagrama.imported_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_by_diagrama(self, diagrama_id: int) -> int:
        result = await self.db.execute(
            select(func.count(ImportacionDiagrama.id)).where(
                ImportacionDiagrama.id_diagrama == diagrama_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, importacion: ImportacionDiagrama) -> ImportacionDiagrama:
        self.db.add(importacion)
        await self.db.flush()
        await self.db.refresh(importacion)
        return importacion

    async def update(self, importacion: ImportacionDiagrama) -> ImportacionDiagrama:
        await self.db.flush()
        await self.db.refresh(importacion)
        return importacion

    async def actualizar_estado(
        self, importacion_id: int, estado: str
    ) -> Optional[ImportacionDiagrama]:
        importacion = await self.get_by_id(importacion_id)
        if importacion is None:
            return None
        importacion.estado = estado
        await self.db.flush()
        await self.db.refresh(importacion)
        return importacion

    async def delete(self, importacion: ImportacionDiagrama) -> None:
        await self.db.delete(importacion)
        await self.db.flush()