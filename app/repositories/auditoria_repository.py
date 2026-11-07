# app/repositories/auditoria_repository.py
"""
Repositorio de acceso a datos del módulo de Auditoría:

- BitacoraRepository → colección `bitacora_sistema`

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorio SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- id_usuario es Optional[PydanticObjectId]: None = evento disparado por el
  propio sistema (el ON DELETE SET NULL del Ciclo 1 desaparece: en MongoDB
  no hay cascadas).
- id_entidad_afectada pasa de BIGINT a str: str(ObjectId) de un Document o
  uuid de un elemento embebido, según `entidad_afectada`.
- list_paginado/count_con_filtros arman UNA lista de condiciones y hacen
  UNA consulta find(...) (antes se encadenaba .where sobre el statement).
"""

from datetime import datetime
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.auditoria import BitacoraSistema


class BitacoraRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, evento_id: PydanticObjectId
    ) -> Optional[BitacoraSistema]:
        return await BitacoraSistema.get(evento_id)

    async def list_paginado(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        id_usuario: Optional[PydanticObjectId] = None,
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
        condiciones = []
        if id_usuario is not None:
            condiciones.append(BitacoraSistema.id_usuario == id_usuario)
        if tipo_evento is not None:
            condiciones.append(BitacoraSistema.tipo_evento == tipo_evento)
        if entidad_afectada is not None:
            condiciones.append(
                BitacoraSistema.entidad_afectada == entidad_afectada
            )
        if desde is not None:
            condiciones.append(BitacoraSistema.created_at >= desde)
        if hasta is not None:
            condiciones.append(BitacoraSistema.created_at <= hasta)
        return await (
            BitacoraSistema.find(*condiciones)
            .sort(-BitacoraSistema.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count_con_filtros(
        self,
        *,
        id_usuario: Optional[PydanticObjectId] = None,
        tipo_evento: Optional[str] = None,
        entidad_afectada: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> int:
        """Conteo total respetando los mismos filtros (para paginación)."""
        condiciones = []
        if id_usuario is not None:
            condiciones.append(BitacoraSistema.id_usuario == id_usuario)
        if tipo_evento is not None:
            condiciones.append(BitacoraSistema.tipo_evento == tipo_evento)
        if entidad_afectada is not None:
            condiciones.append(
                BitacoraSistema.entidad_afectada == entidad_afectada
            )
        if desde is not None:
            condiciones.append(BitacoraSistema.created_at >= desde)
        if hasta is not None:
            condiciones.append(BitacoraSistema.created_at <= hasta)
        return await BitacoraSistema.find(*condiciones).count()

    async def list_by_entidad(
        self,
        entidad_afectada: str,
        id_entidad_afectada: str,
    ) -> Sequence[BitacoraSistema]:
        """Historial de eventos de un recurso concreto (ej. un diagrama)."""
        return await (
            BitacoraSistema.find(
                BitacoraSistema.entidad_afectada == entidad_afectada,
                BitacoraSistema.id_entidad_afectada == id_entidad_afectada,
            )
            .sort(-BitacoraSistema.created_at)
            .to_list()
        )

    async def list_by_usuario(
        self,
        usuario_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[BitacoraSistema]:
        return await (
            BitacoraSistema.find(BitacoraSistema.id_usuario == usuario_id)
            .sort(-BitacoraSistema.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_tipo_evento(
        self,
        tipo_evento: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[BitacoraSistema]:
        return await (
            BitacoraSistema.find(BitacoraSistema.tipo_evento == tipo_evento)
            .sort(-BitacoraSistema.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, evento: BitacoraSistema) -> BitacoraSistema:
        await evento.insert()
        return evento

    async def delete(self, evento: BitacoraSistema) -> None:
        await evento.delete()