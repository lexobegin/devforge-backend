# app/repositories/proyecto_repository.py
"""
Repositorio de acceso a datos del módulo B. Proyectos y Miembros.

Incluye dos repositorios:
- ProyectoRepository          → tabla `proyectos`
- MiembroProyectoRepository   → tabla `miembros_proyecto`
"""

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.proyecto import MiembroProyecto, Proyecto


# ======================================================================
# ProyectoRepository
# ======================================================================
class ProyectoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self,
        proyecto_id: int,
        *,
        con_miembros: bool = False,
    ) -> Optional[Proyecto]:
        stmt = select(Proyecto).where(Proyecto.id == proyecto_id)
        if con_miembros:
            stmt = stmt.options(selectinload(Proyecto.miembros))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_usuario(
        self,
        usuario_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        incluir_archivados: bool = False,
    ) -> Sequence[Proyecto]:
        """
        Proyectos en los que el usuario participa (como propietario o miembro),
        ordenados por fecha de actualización descendente.
        """
        stmt = (
            select(Proyecto)
            .join(MiembroProyecto, MiembroProyecto.id_proyecto == Proyecto.id)
            .where(MiembroProyecto.id_usuario == usuario_id)
            .order_by(Proyecto.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if not incluir_archivados:
            stmt = stmt.where(Proyecto.estado == "ACTIVO")
        result = await self.db.execute(stmt)
        return result.scalars().unique().all()

    async def count_for_usuario(
        self,
        usuario_id: int,
        *,
        incluir_archivados: bool = False,
    ) -> int:
        stmt = (
            select(func.count(func.distinct(Proyecto.id)))
            .select_from(Proyecto)
            .join(MiembroProyecto, MiembroProyecto.id_proyecto == Proyecto.id)
            .where(MiembroProyecto.id_usuario == usuario_id)
        )
        if not incluir_archivados:
            stmt = stmt.where(Proyecto.estado == "ACTIVO")
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        incluir_archivados: bool = False,
    ) -> Sequence[Proyecto]:
        """Uso administrativo: todos los proyectos de la plataforma."""
        stmt = select(Proyecto).order_by(Proyecto.updated_at.desc())
        if not incluir_archivados:
            stmt = stmt.where(Proyecto.estado == "ACTIVO")
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, proyecto: Proyecto) -> Proyecto:
        self.db.add(proyecto)
        await self.db.flush()
        await self.db.refresh(proyecto)
        return proyecto

    async def update(self, proyecto: Proyecto) -> Proyecto:
        await self.db.flush()
        await self.db.refresh(proyecto)
        return proyecto

    async def delete(self, proyecto: Proyecto) -> None:
        await self.db.delete(proyecto)
        await self.db.flush()

    async def archivar(self, proyecto_id: int) -> Optional[Proyecto]:
        proyecto = await self.get_by_id(proyecto_id)
        if proyecto is None:
            return None
        proyecto.estado = "ARCHIVADO"
        await self.db.flush()
        await self.db.refresh(proyecto)
        return proyecto

    async def activar(self, proyecto_id: int) -> Optional[Proyecto]:
        proyecto = await self.get_by_id(proyecto_id)
        if proyecto is None:
            return None
        proyecto.estado = "ACTIVO"
        await self.db.flush()
        await self.db.refresh(proyecto)
        return proyecto


# ======================================================================
# MiembroProyectoRepository
# ======================================================================
class MiembroProyectoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, miembro_id: int) -> Optional[MiembroProyecto]:
        result = await self.db.execute(
            select(MiembroProyecto).where(MiembroProyecto.id == miembro_id)
        )
        return result.scalar_one_or_none()

    async def get_by_proyecto_usuario(
        self, proyecto_id: int, usuario_id: int
    ) -> Optional[MiembroProyecto]:
        result = await self.db.execute(
            select(MiembroProyecto).where(
                MiembroProyecto.id_proyecto == proyecto_id,
                MiembroProyecto.id_usuario == usuario_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_proyecto(
        self, proyecto_id: int
    ) -> Sequence[MiembroProyecto]:
        result = await self.db.execute(
            select(MiembroProyecto)
            .where(MiembroProyecto.id_proyecto == proyecto_id)
            .order_by(MiembroProyecto.joined_at.asc())
        )
        return result.scalars().all()

    async def list_by_usuario(
        self, usuario_id: int
    ) -> Sequence[MiembroProyecto]:
        result = await self.db.execute(
            select(MiembroProyecto).where(MiembroProyecto.id_usuario == usuario_id)
        )
        return result.scalars().all()

    async def count_propietarios(self, proyecto_id: int) -> int:
        """Cuenta cuántos PROPIETARIO tiene un proyecto (para no dejar 0)."""
        result = await self.db.execute(
            select(func.count(MiembroProyecto.id)).where(
                MiembroProyecto.id_proyecto == proyecto_id,
                MiembroProyecto.rol_en_proyecto == "PROPIETARIO",
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, miembro: MiembroProyecto) -> MiembroProyecto:
        self.db.add(miembro)
        await self.db.flush()
        await self.db.refresh(miembro)
        return miembro

    async def update(self, miembro: MiembroProyecto) -> MiembroProyecto:
        await self.db.flush()
        await self.db.refresh(miembro)
        return miembro

    async def delete(self, miembro: MiembroProyecto) -> None:
        await self.db.delete(miembro)
        await self.db.flush()

    async def delete_by_proyecto_usuario(
        self, proyecto_id: int, usuario_id: int
    ) -> bool:
        miembro = await self.get_by_proyecto_usuario(proyecto_id, usuario_id)
        if miembro is None:
            return False
        await self.db.delete(miembro)
        await self.db.flush()
        return True