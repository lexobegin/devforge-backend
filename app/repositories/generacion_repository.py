# app/repositories/generacion_repository.py
"""
Repositorio de acceso a datos del módulo F. Generación Automática:

- TrabajoGeneracionRepository    → tabla `trabajos_generacion_codigo`
- EntidadGeneradaRepository      → tabla `entidades_generadas`
- ReglaMapeoRepository           → tabla `reglas_mapeo`
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.generacion import (
    EntidadGenerada,
    ReglaMapeo,
    TrabajoGeneracionCodigo,
)


# ======================================================================
# TrabajoGeneracionRepository
# ======================================================================
class TrabajoGeneracionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, trabajo_id: int) -> Optional[TrabajoGeneracionCodigo]:
        result = await self.db.execute(
            select(TrabajoGeneracionCodigo).where(
                TrabajoGeneracionCodigo.id == trabajo_id
            )
        )
        return result.scalar_one_or_none()

    async def get_detalle(self, trabajo_id: int) -> Optional[TrabajoGeneracionCodigo]:
        """
        Trabajo con sus entidades generadas y las reglas de mapeo de cada una.
        Es el payload que se usa para mostrar el resumen de una generación.
        """
        stmt = (
            select(TrabajoGeneracionCodigo)
            .where(TrabajoGeneracionCodigo.id == trabajo_id)
            .options(
                selectinload(TrabajoGeneracionCodigo.entidades)
                .selectinload(EntidadGenerada.reglas_mapeo)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self,
        diagrama_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[TrabajoGeneracionCodigo]:
        result = await self.db.execute(
            select(TrabajoGeneracionCodigo)
            .where(TrabajoGeneracionCodigo.id_diagrama == diagrama_id)
            .order_by(TrabajoGeneracionCodigo.created_at.desc())
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
    ) -> Sequence[TrabajoGeneracionCodigo]:
        result = await self.db.execute(
            select(TrabajoGeneracionCodigo)
            .where(TrabajoGeneracionCodigo.id_usuario == usuario_id)
            .order_by(TrabajoGeneracionCodigo.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_by_estado(
        self,
        estado: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[TrabajoGeneracionCodigo]:
        """Útil para reintentar PENDIENTES o monitorear EN_PROCESO."""
        result = await self.db.execute(
            select(TrabajoGeneracionCodigo)
            .where(TrabajoGeneracionCodigo.estado == estado)
            .order_by(TrabajoGeneracionCodigo.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_ultimo_exitoso_by_diagrama(
        self, diagrama_id: int
    ) -> Optional[TrabajoGeneracionCodigo]:
        """Último trabajo EXITOSO de un diagrama (para ofrecer descarga directa)."""
        result = await self.db.execute(
            select(TrabajoGeneracionCodigo)
            .where(
                TrabajoGeneracionCodigo.id_diagrama == diagrama_id,
                TrabajoGeneracionCodigo.estado == "EXITOSO",
            )
            .order_by(TrabajoGeneracionCodigo.finished_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_by_diagrama(self, diagrama_id: int) -> int:
        result = await self.db.execute(
            select(func.count(TrabajoGeneracionCodigo.id)).where(
                TrabajoGeneracionCodigo.id_diagrama == diagrama_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, trabajo: TrabajoGeneracionCodigo
    ) -> TrabajoGeneracionCodigo:
        self.db.add(trabajo)
        await self.db.flush()
        await self.db.refresh(trabajo)
        return trabajo

    async def update(
        self, trabajo: TrabajoGeneracionCodigo
    ) -> TrabajoGeneracionCodigo:
        await self.db.flush()
        await self.db.refresh(trabajo)
        return trabajo

    async def marcar_en_proceso(
        self, trabajo_id: int, *, cuando: Optional[datetime] = None
    ) -> Optional[TrabajoGeneracionCodigo]:
        trabajo = await self.get_by_id(trabajo_id)
        if trabajo is None:
            return None
        trabajo.estado = "EN_PROCESO"
        trabajo.started_at = cuando or datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(trabajo)
        return trabajo

    async def marcar_exitoso(
        self,
        trabajo_id: int,
        *,
        ruta_salida: str,
        cuando: Optional[datetime] = None,
    ) -> Optional[TrabajoGeneracionCodigo]:
        trabajo = await self.get_by_id(trabajo_id)
        if trabajo is None:
            return None
        trabajo.estado = "EXITOSO"
        trabajo.ruta_salida = ruta_salida
        trabajo.finished_at = cuando or datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(trabajo)
        return trabajo

    async def marcar_fallido(
        self, trabajo_id: int, *, cuando: Optional[datetime] = None
    ) -> Optional[TrabajoGeneracionCodigo]:
        trabajo = await self.get_by_id(trabajo_id)
        if trabajo is None:
            return None
        trabajo.estado = "FALLIDO"
        trabajo.finished_at = cuando or datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(trabajo)
        return trabajo

    async def delete(self, trabajo: TrabajoGeneracionCodigo) -> None:
        await self.db.delete(trabajo)
        await self.db.flush()


# ======================================================================
# EntidadGeneradaRepository
# ======================================================================
class EntidadGeneradaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, entidad_id: int) -> Optional[EntidadGenerada]:
        result = await self.db.execute(
            select(EntidadGenerada).where(EntidadGenerada.id == entidad_id)
        )
        return result.scalar_one_or_none()

    async def get_con_reglas(self, entidad_id: int) -> Optional[EntidadGenerada]:
        stmt = (
            select(EntidadGenerada)
            .where(EntidadGenerada.id == entidad_id)
            .options(selectinload(EntidadGenerada.reglas_mapeo))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_trabajo(
        self, trabajo_id: int
    ) -> Sequence[EntidadGenerada]:
        result = await self.db.execute(
            select(EntidadGenerada)
            .where(EntidadGenerada.id_trabajo == trabajo_id)
            .order_by(EntidadGenerada.id.asc())
        )
        return result.scalars().all()

    async def get_by_trabajo_y_clase(
        self, trabajo_id: int, clase_uml_id: int
    ) -> Optional[EntidadGenerada]:
        result = await self.db.execute(
            select(EntidadGenerada).where(
                EntidadGenerada.id_trabajo == trabajo_id,
                EntidadGenerada.id_clase_uml == clase_uml_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_by_trabajo(self, trabajo_id: int) -> int:
        result = await self.db.execute(
            select(func.count(EntidadGenerada.id)).where(
                EntidadGenerada.id_trabajo == trabajo_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, entidad: EntidadGenerada) -> EntidadGenerada:
        self.db.add(entidad)
        await self.db.flush()
        await self.db.refresh(entidad)
        return entidad

    async def bulk_create(
        self, entidades: list[EntidadGenerada]
    ) -> list[EntidadGenerada]:
        """Crea varias entidades de una vez (usado por el generador)."""
        self.db.add_all(entidades)
        await self.db.flush()
        for e in entidades:
            await self.db.refresh(e)
        return entidades

    async def update(self, entidad: EntidadGenerada) -> EntidadGenerada:
        await self.db.flush()
        await self.db.refresh(entidad)
        return entidad

    async def delete(self, entidad: EntidadGenerada) -> None:
        await self.db.delete(entidad)
        await self.db.flush()

    async def delete_by_trabajo(self, trabajo_id: int) -> int:
        from sqlalchemy import delete as sa_delete

        result = await self.db.execute(
            sa_delete(EntidadGenerada).where(
                EntidadGenerada.id_trabajo == trabajo_id
            )
        )
        await self.db.flush()
        return int(result.rowcount or 0)


# ======================================================================
# ReglaMapeoRepository
# ======================================================================
class ReglaMapeoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, regla_id: int) -> Optional[ReglaMapeo]:
        result = await self.db.execute(
            select(ReglaMapeo).where(ReglaMapeo.id == regla_id)
        )
        return result.scalar_one_or_none()

    async def list_by_entidad(
        self, entidad_id: int
    ) -> Sequence[ReglaMapeo]:
        result = await self.db.execute(
            select(ReglaMapeo)
            .where(ReglaMapeo.id_entidad_generada == entidad_id)
            .order_by(ReglaMapeo.id.asc())
        )
        return result.scalars().all()

    async def get_by_entidad_y_atributo(
        self, entidad_id: int, atributo_uml_id: int
    ) -> Optional[ReglaMapeo]:
        result = await self.db.execute(
            select(ReglaMapeo).where(
                ReglaMapeo.id_entidad_generada == entidad_id,
                ReglaMapeo.id_atributo_uml == atributo_uml_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_claves_primarias_by_entidad(
        self, entidad_id: int
    ) -> Sequence[ReglaMapeo]:
        """Reglas de mapeo que marcan la PK de la entidad."""
        result = await self.db.execute(
            select(ReglaMapeo).where(
                ReglaMapeo.id_entidad_generada == entidad_id,
                ReglaMapeo.es_clave_primaria.is_(True),
            )
        )
        return result.scalars().all()

    async def count_by_entidad(self, entidad_id: int) -> int:
        result = await self.db.execute(
            select(func.count(ReglaMapeo.id)).where(
                ReglaMapeo.id_entidad_generada == entidad_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, regla: ReglaMapeo) -> ReglaMapeo:
        self.db.add(regla)
        await self.db.flush()
        await self.db.refresh(regla)
        return regla

    async def bulk_create(self, reglas: list[ReglaMapeo]) -> list[ReglaMapeo]:
        self.db.add_all(reglas)
        await self.db.flush()
        for r in reglas:
            await self.db.refresh(r)
        return reglas

    async def update(self, regla: ReglaMapeo) -> ReglaMapeo:
        await self.db.flush()
        await self.db.refresh(regla)
        return regla

    async def delete(self, regla: ReglaMapeo) -> None:
        await self.db.delete(regla)
        await self.db.flush()

    async def delete_by_entidad(self, entidad_id: int) -> int:
        from sqlalchemy import delete as sa_delete

        result = await self.db.execute(
            sa_delete(ReglaMapeo).where(
                ReglaMapeo.id_entidad_generada == entidad_id
            )
        )
        await self.db.flush()
        return int(result.rowcount or 0)