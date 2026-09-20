# app/repositories/diagrama_repository.py
"""
Repositorio de acceso a datos del módulo C. Modelado UML.

Incluye los repositorios para las 8 tablas del módulo:
- DiagramaRepository
- ClaseUMLRepository
- AtributoUMLRepository
- OperacionUMLRepository
- ParametroOperacionUMLRepository
- InterfazUMLRepository
- OperacionInterfazUMLRepository
- RelacionUMLRepository
"""

from typing import Optional, Sequence

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.diagrama import (
    AtributoUML,
    ClaseUML,
    Diagrama,
    InterfazUML,
    OperacionInterfazUML,
    OperacionUML,
    ParametroOperacionUML,
    RelacionUML,
)


# ======================================================================
# DiagramaRepository
# ======================================================================
class DiagramaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, diagrama_id: int) -> Optional[Diagrama]:
        result = await self.db.execute(
            select(Diagrama).where(Diagrama.id == diagrama_id)
        )
        return result.scalar_one_or_none()

    async def get_completo(self, diagrama_id: int) -> Optional[Diagrama]:
        """
        Carga el diagrama con clases (y sus atributos/operaciones/parámetros),
        interfaces (con sus operaciones) y relaciones. Es el payload que
        consume el editor y el motor de generación.
        """
        stmt = (
            select(Diagrama)
            .where(Diagrama.id == diagrama_id)
            .options(
                selectinload(Diagrama.clases).selectinload(ClaseUML.atributos),
                selectinload(Diagrama.clases).selectinload(ClaseUML.operaciones)
                .selectinload(OperacionUML.parametros),
                selectinload(Diagrama.interfaces).selectinload(InterfazUML.operaciones),
                selectinload(Diagrama.relaciones),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_proyecto(
        self,
        proyecto_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Diagrama]:
        result = await self.db.execute(
            select(Diagrama)
            .where(Diagrama.id_proyecto == proyecto_id)
            .order_by(Diagrama.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_by_proyecto(self, proyecto_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Diagrama.id)).where(
                Diagrama.id_proyecto == proyecto_id
            )
        )
        return int(result.scalar_one())

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, diagrama: Diagrama) -> Diagrama:
        self.db.add(diagrama)
        await self.db.flush()
        await self.db.refresh(diagrama)
        return diagrama

    async def update(self, diagrama: Diagrama) -> Diagrama:
        await self.db.flush()
        await self.db.refresh(diagrama)
        return diagrama

    async def delete(self, diagrama: Diagrama) -> None:
        await self.db.delete(diagrama)
        await self.db.flush()

    async def incrementar_version(
        self, diagrama_id: int
    ) -> Optional[Diagrama]:
        diagrama = await self.get_by_id(diagrama_id)
        if diagrama is None:
            return None
        diagrama.numero_version = (diagrama.numero_version or 0) + 1
        await self.db.flush()
        await self.db.refresh(diagrama)
        return diagrama


# ======================================================================
# ClaseUMLRepository
# ======================================================================
class ClaseUMLRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, clase_id: int) -> Optional[ClaseUML]:
        result = await self.db.execute(
            select(ClaseUML).where(ClaseUML.id == clase_id)
        )
        return result.scalar_one_or_none()

    async def get_con_detalle(self, clase_id: int) -> Optional[ClaseUML]:
        """Clase con atributos y operaciones (y parámetros de cada operación)."""
        stmt = (
            select(ClaseUML)
            .where(ClaseUML.id == clase_id)
            .options(
                selectinload(ClaseUML.atributos),
                selectinload(ClaseUML.operaciones).selectinload(OperacionUML.parametros),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self, diagrama_id: int
    ) -> Sequence[ClaseUML]:
        result = await self.db.execute(
            select(ClaseUML)
            .where(ClaseUML.id_diagrama == diagrama_id)
            .order_by(ClaseUML.created_at.asc())
        )
        return result.scalars().all()

    async def exists_nombre_en_diagrama(
        self,
        diagrama_id: int,
        nombre: str,
        *,
        exclude_id: Optional[int] = None,
    ) -> bool:
        stmt = select(ClaseUML.id).where(
            ClaseUML.id_diagrama == diagrama_id,
            func.lower(ClaseUML.nombre) == nombre.lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(ClaseUML.id != exclude_id)
        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None

    async def create(self, clase: ClaseUML) -> ClaseUML:
        self.db.add(clase)
        await self.db.flush()
        await self.db.refresh(clase)
        return clase

    async def update(self, clase: ClaseUML) -> ClaseUML:
        await self.db.flush()
        await self.db.refresh(clase)
        return clase

    async def delete(self, clase: ClaseUML) -> None:
        await self.db.delete(clase)
        await self.db.flush()

    async def delete_by_diagrama(self, diagrama_id: int) -> int:
        """Elimina todas las clases de un diagrama. Devuelve cuántas borró."""
        result = await self.db.execute(
            sa_delete(ClaseUML).where(ClaseUML.id_diagrama == diagrama_id)
        )
        await self.db.flush()
        return int(result.rowcount or 0)


# ======================================================================
# AtributoUMLRepository
# ======================================================================
class AtributoUMLRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, atributo_id: int) -> Optional[AtributoUML]:
        result = await self.db.execute(
            select(AtributoUML).where(AtributoUML.id == atributo_id)
        )
        return result.scalar_one_or_none()

    async def list_by_clase(self, clase_id: int) -> Sequence[AtributoUML]:
        result = await self.db.execute(
            select(AtributoUML)
            .where(AtributoUML.id_clase == clase_id)
            .order_by(AtributoUML.orden.asc(), AtributoUML.id.asc())
        )
        return result.scalars().all()

    async def next_orden(self, clase_id: int) -> int:
        result = await self.db.execute(
            select(func.coalesce(func.max(AtributoUML.orden), -1)).where(
                AtributoUML.id_clase == clase_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create(self, atributo: AtributoUML) -> AtributoUML:
        self.db.add(atributo)
        await self.db.flush()
        await self.db.refresh(atributo)
        return atributo

    async def update(self, atributo: AtributoUML) -> AtributoUML:
        await self.db.flush()
        await self.db.refresh(atributo)
        return atributo

    async def delete(self, atributo: AtributoUML) -> None:
        await self.db.delete(atributo)
        await self.db.flush()


# ======================================================================
# OperacionUMLRepository
# ======================================================================
class OperacionUMLRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, operacion_id: int) -> Optional[OperacionUML]:
        result = await self.db.execute(
            select(OperacionUML).where(OperacionUML.id == operacion_id)
        )
        return result.scalar_one_or_none()

    async def get_con_parametros(self, operacion_id: int) -> Optional[OperacionUML]:
        stmt = (
            select(OperacionUML)
            .where(OperacionUML.id == operacion_id)
            .options(selectinload(OperacionUML.parametros))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_clase(self, clase_id: int) -> Sequence[OperacionUML]:
        result = await self.db.execute(
            select(OperacionUML)
            .where(OperacionUML.id_clase == clase_id)
            .order_by(OperacionUML.orden.asc(), OperacionUML.id.asc())
        )
        return result.scalars().all()

    async def next_orden(self, clase_id: int) -> int:
        result = await self.db.execute(
            select(func.coalesce(func.max(OperacionUML.orden), -1)).where(
                OperacionUML.id_clase == clase_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create(self, operacion: OperacionUML) -> OperacionUML:
        self.db.add(operacion)
        await self.db.flush()
        await self.db.refresh(operacion)
        return operacion

    async def update(self, operacion: OperacionUML) -> OperacionUML:
        await self.db.flush()
        await self.db.refresh(operacion)
        return operacion

    async def delete(self, operacion: OperacionUML) -> None:
        await self.db.delete(operacion)
        await self.db.flush()


# ======================================================================
# ParametroOperacionUMLRepository
# ======================================================================
class ParametroOperacionUMLRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, parametro_id: int) -> Optional[ParametroOperacionUML]:
        result = await self.db.execute(
            select(ParametroOperacionUML).where(
                ParametroOperacionUML.id == parametro_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_operacion(
        self, operacion_id: int
    ) -> Sequence[ParametroOperacionUML]:
        result = await self.db.execute(
            select(ParametroOperacionUML)
            .where(ParametroOperacionUML.id_operacion == operacion_id)
            .order_by(
                ParametroOperacionUML.orden.asc(),
                ParametroOperacionUML.id.asc(),
            )
        )
        return result.scalars().all()

    async def next_orden(self, operacion_id: int) -> int:
        result = await self.db.execute(
            select(func.coalesce(func.max(ParametroOperacionUML.orden), -1)).where(
                ParametroOperacionUML.id_operacion == operacion_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create(
        self, parametro: ParametroOperacionUML
    ) -> ParametroOperacionUML:
        self.db.add(parametro)
        await self.db.flush()
        await self.db.refresh(parametro)
        return parametro

    async def update(
        self, parametro: ParametroOperacionUML
    ) -> ParametroOperacionUML:
        await self.db.flush()
        await self.db.refresh(parametro)
        return parametro

    async def delete(self, parametro: ParametroOperacionUML) -> None:
        await self.db.delete(parametro)
        await self.db.flush()


# ======================================================================
# InterfazUMLRepository
# ======================================================================
class InterfazUMLRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, interfaz_id: int) -> Optional[InterfazUML]:
        result = await self.db.execute(
            select(InterfazUML).where(InterfazUML.id == interfaz_id)
        )
        return result.scalar_one_or_none()

    async def get_con_operaciones(self, interfaz_id: int) -> Optional[InterfazUML]:
        stmt = (
            select(InterfazUML)
            .where(InterfazUML.id == interfaz_id)
            .options(selectinload(InterfazUML.operaciones))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self, diagrama_id: int
    ) -> Sequence[InterfazUML]:
        result = await self.db.execute(
            select(InterfazUML)
            .where(InterfazUML.id_diagrama == diagrama_id)
            .order_by(InterfazUML.id.asc())
        )
        return result.scalars().all()

    async def create(self, interfaz: InterfazUML) -> InterfazUML:
        self.db.add(interfaz)
        await self.db.flush()
        await self.db.refresh(interfaz)
        return interfaz

    async def update(self, interfaz: InterfazUML) -> InterfazUML:
        await self.db.flush()
        await self.db.refresh(interfaz)
        return interfaz

    async def delete(self, interfaz: InterfazUML) -> None:
        await self.db.delete(interfaz)
        await self.db.flush()


# ======================================================================
# OperacionInterfazUMLRepository
# ======================================================================
class OperacionInterfazUMLRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self, operacion_id: int
    ) -> Optional[OperacionInterfazUML]:
        result = await self.db.execute(
            select(OperacionInterfazUML).where(
                OperacionInterfazUML.id == operacion_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_interfaz(
        self, interfaz_id: int
    ) -> Sequence[OperacionInterfazUML]:
        result = await self.db.execute(
            select(OperacionInterfazUML)
            .where(OperacionInterfazUML.id_interfaz == interfaz_id)
            .order_by(OperacionInterfazUML.id.asc())
        )
        return result.scalars().all()

    async def create(
        self, operacion: OperacionInterfazUML
    ) -> OperacionInterfazUML:
        self.db.add(operacion)
        await self.db.flush()
        await self.db.refresh(operacion)
        return operacion

    async def update(
        self, operacion: OperacionInterfazUML
    ) -> OperacionInterfazUML:
        await self.db.flush()
        await self.db.refresh(operacion)
        return operacion

    async def delete(self, operacion: OperacionInterfazUML) -> None:
        await self.db.delete(operacion)
        await self.db.flush()


# ======================================================================
# RelacionUMLRepository
# ======================================================================
class RelacionUMLRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, relacion_id: int) -> Optional[RelacionUML]:
        result = await self.db.execute(
            select(RelacionUML).where(RelacionUML.id == relacion_id)
        )
        return result.scalar_one_or_none()

    async def list_by_diagrama(
        self, diagrama_id: int
    ) -> Sequence[RelacionUML]:
        result = await self.db.execute(
            select(RelacionUML)
            .where(RelacionUML.id_diagrama == diagrama_id)
            .order_by(RelacionUML.id.asc())
        )
        return result.scalars().all()

    async def list_by_clase(self, clase_id: int) -> Sequence[RelacionUML]:
        """Relaciones donde la clase participa como origen o destino."""
        result = await self.db.execute(
            select(RelacionUML).where(
                (RelacionUML.id_clase_origen == clase_id)
                | (RelacionUML.id_clase_destino == clase_id)
            )
        )
        return result.scalars().all()

    async def exists_entre_clases(
        self,
        diagrama_id: int,
        id_clase_origen: int,
        id_clase_destino: int,
        tipo_relacion: str,
    ) -> bool:
        result = await self.db.execute(
            select(RelacionUML.id)
            .where(
                RelacionUML.id_diagrama == diagrama_id,
                RelacionUML.id_clase_origen == id_clase_origen,
                RelacionUML.id_clase_destino == id_clase_destino,
                RelacionUML.tipo_relacion == tipo_relacion,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def create(self, relacion: RelacionUML) -> RelacionUML:
        self.db.add(relacion)
        await self.db.flush()
        await self.db.refresh(relacion)
        return relacion

    async def update(self, relacion: RelacionUML) -> RelacionUML:
        await self.db.flush()
        await self.db.refresh(relacion)
        return relacion

    async def delete(self, relacion: RelacionUML) -> None:
        await self.db.delete(relacion)
        await self.db.flush()

    async def delete_by_clase(self, clase_id: int) -> int:
        """Elimina relaciones donde la clase sea origen o destino."""
        result = await self.db.execute(
            sa_delete(RelacionUML).where(
                (RelacionUML.id_clase_origen == clase_id)
                | (RelacionUML.id_clase_destino == clase_id)
            )
        )
        await self.db.flush()
        return int(result.rowcount or 0)