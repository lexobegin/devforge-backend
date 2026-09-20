# app/repositories/colaboracion_repository.py
"""
Repositorio de acceso a datos del módulo B. Colaboración.

Incluye dos repositorios:
- SesionColaboracionRepository     → tabla `sesiones_colaboracion`
- ParticipanteSesionRepository     → tabla `participantes_sesion`
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.colaboracion import ParticipanteSesion, SesionColaboracion


# ======================================================================
# SesionColaboracionRepository
# ======================================================================
class SesionColaboracionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self,
        sesion_id: int,
        *,
        con_participantes: bool = False,
    ) -> Optional[SesionColaboracion]:
        stmt = select(SesionColaboracion).where(SesionColaboracion.id == sesion_id)
        if con_participantes:
            stmt = stmt.options(selectinload(SesionColaboracion.participantes))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sesion_activa_by_diagrama(
        self, diagrama_id: int
    ) -> Optional[SesionColaboracion]:
        """
        Devuelve la sesión activa (ended_at IS NULL) de un diagrama.
        Un diagrama debería tener a lo sumo una sesión activa a la vez.
        """
        result = await self.db.execute(
            select(SesionColaboracion)
            .where(
                SesionColaboracion.id_diagrama == diagrama_id,
                SesionColaboracion.ended_at.is_(None),
            )
            .order_by(SesionColaboracion.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_activas_by_proyecto(
        self, proyecto_id: int
    ) -> Sequence[SesionColaboracion]:
        result = await self.db.execute(
            select(SesionColaboracion)
            .where(
                SesionColaboracion.id_proyecto == proyecto_id,
                SesionColaboracion.ended_at.is_(None),
            )
            .order_by(SesionColaboracion.started_at.desc())
        )
        return result.scalars().all()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[SesionColaboracion]:
        result = await self.db.execute(
            select(SesionColaboracion)
            .where(SesionColaboracion.id_diagrama == diagrama_id)
            .order_by(SesionColaboracion.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, sesion: SesionColaboracion) -> SesionColaboracion:
        self.db.add(sesion)
        await self.db.flush()
        await self.db.refresh(sesion)
        return sesion

    async def update(self, sesion: SesionColaboracion) -> SesionColaboracion:
        await self.db.flush()
        await self.db.refresh(sesion)
        return sesion

    async def cerrar_sesion(
        self, sesion_id: int, *, cuando: Optional[datetime] = None
    ) -> Optional[SesionColaboracion]:
        """Marca `ended_at` en la sesión (la cierra)."""
        sesion = await self.get_by_id(sesion_id)
        if sesion is None:
            return None
        sesion.ended_at = cuando or datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(sesion)
        return sesion

    async def cerrar_todas_by_diagrama(
        self, diagrama_id: int, *, cuando: Optional[datetime] = None
    ) -> int:
        """
        Cierra todas las sesiones activas de un diagrama.
        Devuelve cuántas cerró. Útil cuando se archiva/elimina un diagrama.
        """
        sesiones = await self.list_by_diagrama(diagrama_id, limit=1000)
        cerradas = 0
        now = cuando or datetime.utcnow()
        for s in sesiones:
            if s.ended_at is None:
                s.ended_at = now
                cerradas += 1
        if cerradas:
            await self.db.flush()
        return cerradas


# ======================================================================
# ParticipanteSesionRepository
# ======================================================================
class ParticipanteSesionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, participante_id: int) -> Optional[ParticipanteSesion]:
        result = await self.db.execute(
            select(ParticipanteSesion).where(ParticipanteSesion.id == participante_id)
        )
        return result.scalar_one_or_none()

    async def get_by_sesion_usuario(
        self, sesion_id: int, usuario_id: int
    ) -> Optional[ParticipanteSesion]:
        result = await self.db.execute(
            select(ParticipanteSesion).where(
                ParticipanteSesion.id_sesion == sesion_id,
                ParticipanteSesion.id_usuario == usuario_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_conectados_by_sesion(
        self, sesion_id: int
    ) -> Sequence[ParticipanteSesion]:
        """Participantes que siguen conectados (left_at IS NULL)."""
        result = await self.db.execute(
            select(ParticipanteSesion)
            .where(
                ParticipanteSesion.id_sesion == sesion_id,
                ParticipanteSesion.left_at.is_(None),
            )
            .order_by(ParticipanteSesion.joined_at.asc())
        )
        return result.scalars().all()

    async def count_conectados_by_sesion(self, sesion_id: int) -> int:
        result = await self.db.execute(
            select(func.count(ParticipanteSesion.id)).where(
                ParticipanteSesion.id_sesion == sesion_id,
                ParticipanteSesion.left_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def list_conectados_by_diagrama(
        self, diagrama_id: int
    ) -> Sequence[ParticipanteSesion]:
        """
        Participantes conectados en cualquier sesión activa de un diagrama.
        Útil para el panel de colaboradores del editor.
        """
        result = await self.db.execute(
            select(ParticipanteSesion)
            .join(
                SesionColaboracion,
                SesionColaboracion.id == ParticipanteSesion.id_sesion,
            )
            .where(
                SesionColaboracion.id_diagrama == diagrama_id,
                SesionColaboracion.ended_at.is_(None),
                ParticipanteSesion.left_at.is_(None),
            )
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, participante: ParticipanteSesion) -> ParticipanteSesion:
        self.db.add(participante)
        await self.db.flush()
        await self.db.refresh(participante)
        return participante

    async def update(self, participante: ParticipanteSesion) -> ParticipanteSesion:
        await self.db.flush()
        await self.db.refresh(participante)
        return participante

    async def actualizar_cursor(
        self,
        participante_id: int,
        posicion_cursor: Optional[dict],
    ) -> Optional[ParticipanteSesion]:
        """Actualiza solo el campo JSONB de posición de cursor."""
        participante = await self.get_by_id(participante_id)
        if participante is None:
            return None
        participante.posicion_cursor = posicion_cursor
        await self.db.flush()
        await self.db.refresh(participante)
        return participante

    async def marcar_salida(
        self, participante_id: int, *, cuando: Optional[datetime] = None
    ) -> Optional[ParticipanteSesion]:
        """Marca `left_at` (el participante se desconectó)."""
        participante = await self.get_by_id(participante_id)
        if participante is None:
            return None
        participante.left_at = cuando or datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(participante)
        return participante

    async def marcar_salida_by_sesion_usuario(
        self,
        sesion_id: int,
        usuario_id: int,
        *,
        cuando: Optional[datetime] = None,
    ) -> bool:
        participante = await self.get_by_sesion_usuario(sesion_id, usuario_id)
        if participante is None:
            return False
        participante.left_at = cuando or datetime.utcnow()
        await self.db.flush()
        return True