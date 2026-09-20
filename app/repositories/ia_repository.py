# app/repositories/ia_repository.py
"""
Repositorio de acceso a datos del módulo G. IA Asistente.

- InteraccionIARepository → tabla `interacciones_ia`
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ia import InteraccionIA


class InteraccionIARepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, interaccion_id: int) -> Optional[InteraccionIA]:
        result = await self.db.execute(
            select(InteraccionIA).where(InteraccionIA.id == interaccion_id)
        )
        return result.scalar_one_or_none()

    async def list_by_proyecto(
        self,
        proyecto_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InteraccionIA]:
        result = await self.db.execute(
            select(InteraccionIA)
            .where(InteraccionIA.id_proyecto == proyecto_id)
            .order_by(InteraccionIA.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InteraccionIA]:
        result = await self.db.execute(
            select(InteraccionIA)
            .where(InteraccionIA.id_diagrama == diagrama_id)
            .order_by(InteraccionIA.created_at.desc())
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
    ) -> Sequence[InteraccionIA]:
        result = await self.db.execute(
            select(InteraccionIA)
            .where(InteraccionIA.id_usuario == usuario_id)
            .order_by(InteraccionIA.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_canal(
        self,
        canal: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InteraccionIA]:
        """Filtra por 'VOZ' o 'TEXTO'."""
        result = await self.db.execute(
            select(InteraccionIA)
            .where(InteraccionIA.canal == canal)
            .order_by(InteraccionIA.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_aplicadas_by_diagrama(
        self, diagrama_id: int
    ) -> Sequence[InteraccionIA]:
        """Interacciones cuya acción la IA aplicó efectivamente al diagrama."""
        result = await self.db.execute(
            select(InteraccionIA)
            .where(
                InteraccionIA.id_diagrama == diagrama_id,
                InteraccionIA.accion_aplicada.is_(True),
            )
            .order_by(InteraccionIA.created_at.desc())
        )
        return result.scalars().all()

    async def count_by_proyecto(self, proyecto_id: int) -> int:
        result = await self.db.execute(
            select(func.count(InteraccionIA.id)).where(
                InteraccionIA.id_proyecto == proyecto_id
            )
        )
        return int(result.scalar_one())

    async def count_by_canal(self, canal: str) -> int:
        result = await self.db.execute(
            select(func.count(InteraccionIA.id)).where(
                InteraccionIA.canal == canal
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, interaccion: InteraccionIA) -> InteraccionIA:
        self.db.add(interaccion)
        await self.db.flush()
        await self.db.refresh(interaccion)
        return interaccion

    async def update(self, interaccion: InteraccionIA) -> InteraccionIA:
        await self.db.flush()
        await self.db.refresh(interaccion)
        return interaccion

    async def marcar_accion_aplicada(
        self, interaccion_id: int, *, aplicada: bool = True
    ) -> Optional[InteraccionIA]:
        interaccion = await self.get_by_id(interaccion_id)
        if interaccion is None:
            return None
        interaccion.accion_aplicada = aplicada
        await self.db.flush()
        await self.db.refresh(interaccion)
        return interaccion

    async def delete(self, interaccion: InteraccionIA) -> None:
        await self.db.delete(interaccion)
        await self.db.flush()