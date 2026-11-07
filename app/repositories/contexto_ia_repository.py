# app/repositories/contexto_ia_repository.py
"""
Repositorio de acceso a datos del contexto de la IA (módulo G, parte 2)
— CICLO 2.

ARCHIVO NUEVO del Ciclo 2: el contexto enviado al modelo era una parte de
la tabla `interacciones_ia` del Ciclo 1 (InteraccionIARepository); con el
rediseño del módulo G vive en la colección `contextos_ia` (ContextoIA) y
este repositorio lo gestiona — es la bitácora del gestor de contexto
(CU17): resumen del diagrama, ventana del historial, elementos
seleccionados e instrucciones de sistema.

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorio SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- ids int → PydanticObjectId (ObjectId de Mongo).
- flush/refresh → insert()/delete() de Beanie.
- NO hay update: el contexto de un turno ya enviado no se reescribe
  (para corregirlo se arma y guarda uno nuevo).
- get_ultimo_by_diagrama permite rearmar el mismo turno tras una caída
  sin recalcular el ensamblado (ni el embedding de nomic-embed-text).
"""

from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.contexto_ia import ContextoIA


# ======================================================================
# ContextoIARepository
# ======================================================================
class ContextoIARepository:
    """
    Bitácora de lo enviado al modelo en cada turno (CU17): resumen del
    diagrama, ventana del historial, elementos seleccionados… Solo se
    crea y se consulta: el contexto de un turno ya enviado no se
    reescribe (para corregirlo se arma y guarda uno nuevo), por eso no
    hay update.
    """

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, contexto_id: PydanticObjectId
    ) -> Optional[ContextoIA]:
        return await ContextoIA.get(contexto_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ContextoIA]:
        return await (
            ContextoIA.find(ContextoIA.id_diagrama == diagrama_id)
            .sort(-ContextoIA.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_usuario(
        self,
        usuario_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ContextoIA]:
        return await (
            ContextoIA.find(ContextoIA.id_usuario == usuario_id)
            .sort(-ContextoIA.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def get_ultimo_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[ContextoIA]:
        """
        Último contexto enviado para un diagrama: permite rearmar el
        mismo turno tras una caída sin recalcular el ensamblado (ni el
        embedding de nomic-embed-text).
        """
        return await (
            ContextoIA.find(ContextoIA.id_diagrama == diagrama_id)
            .sort(-ContextoIA.created_at)
            .first_or_none()
        )

    async def count_by_diagrama(self, diagrama_id: PydanticObjectId) -> int:
        return await ContextoIA.find(
            ContextoIA.id_diagrama == diagrama_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, contexto: ContextoIA) -> ContextoIA:
        await contexto.insert()
        return contexto

    async def delete(self, contexto: ContextoIA) -> None:
        await contexto.delete()