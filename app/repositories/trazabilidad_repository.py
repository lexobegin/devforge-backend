# app/repositories/trazabilidad_repository.py
"""
Repositorio de acceso a datos del módulo D. Trazabilidad:

- HistorialCambioRepository    → colección `historial_cambios_diagrama`
- VersionDiagramaRepository    → colección `versiones_diagrama`
- ComentarioDiagramaRepository → colección `comentarios_diagrama`

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorios SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- Las 3 colecciones se conservan SEPARADAS (mismo criterio que los modelos:
  son listas abiertas que crecerían sin límite si se embebieran en el
  Diagrama).
- id_entidad pasa de INT (id de tabla hija) a STR uuid: referencia los ids
  de los elementos EMBEBIDOS del Diagrama del Ciclo 2 (ClaseUML.id,
  AtributoUML.id, OperacionUML.id, RelacionUML.id…).
- Los filtros desde/hasta/solo_no_resueltos van en la MISMA consulta
  find(...) de MongoDB (antes se encadenaba .where sobre el statement).
- next_numero_version: se lee la última versión y se suma 1 (el índice
  único uq_version_diagrama_numero sigue protegiendo las carreras).
- delete_versiones_antiguas: UN delete con $nin sobre los ids que se
  conservan (antes subquery NOT IN).
"""

from datetime import datetime
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.trazabilidad import (
    ComentarioDiagrama,
    HistorialCambioDiagrama,
    VersionDiagrama,
)


# ======================================================================
# HistorialCambioRepository
# ======================================================================
class HistorialCambioRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, cambio_id: PydanticObjectId
    ) -> Optional[HistorialCambioDiagrama]:
        return await HistorialCambioDiagrama.get(cambio_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 100,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> Sequence[HistorialCambioDiagrama]:
        """
        Historial de un diagrama ordenado del cambio más reciente al más
        antiguo. Permite filtrar por rango de fechas.
        """
        condiciones = [HistorialCambioDiagrama.id_diagrama == diagrama_id]
        if desde is not None:
            condiciones.append(HistorialCambioDiagrama.created_at >= desde)
        if hasta is not None:
            condiciones.append(HistorialCambioDiagrama.created_at <= hasta)
        return await (
            HistorialCambioDiagrama.find(*condiciones)
            .sort(-HistorialCambioDiagrama.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_entidad(
        self,
        diagrama_id: PydanticObjectId,
        tipo_entidad: str,
        id_entidad: str,
    ) -> Sequence[HistorialCambioDiagrama]:
        """
        Historial de un elemento concreto (ej. una clase), útil para
        reconstruir sus cambios a lo largo del tiempo. id_entidad es el
        uuid del elemento EMBEBIDO del Diagrama.
        """
        return await (
            HistorialCambioDiagrama.find(
                HistorialCambioDiagrama.id_diagrama == diagrama_id,
                HistorialCambioDiagrama.tipo_entidad == tipo_entidad,
                HistorialCambioDiagrama.id_entidad == id_entidad,
            )
            .sort(-HistorialCambioDiagrama.created_at)
            .to_list()
        )

    async def count_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        return await HistorialCambioDiagrama.find(
            HistorialCambioDiagrama.id_diagrama == diagrama_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, cambio: HistorialCambioDiagrama
    ) -> HistorialCambioDiagrama:
        await cambio.insert()
        return cambio

    async def delete(self, cambio: HistorialCambioDiagrama) -> None:
        await cambio.delete()


# ======================================================================
# VersionDiagramaRepository
# ======================================================================
class VersionDiagramaRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, version_id: PydanticObjectId
    ) -> Optional[VersionDiagrama]:
        return await VersionDiagrama.get(version_id)

    async def get_by_diagrama_numero(
        self,
        diagrama_id: PydanticObjectId,
        numero_version: int,
    ) -> Optional[VersionDiagrama]:
        return await VersionDiagrama.find_one(
            VersionDiagrama.id_diagrama == diagrama_id,
            VersionDiagrama.numero_version == numero_version,
        )

    async def get_ultima_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[VersionDiagrama]:
        """Devuelve la versión más alta guardada de un diagrama."""
        return await (
            VersionDiagrama.find(VersionDiagrama.id_diagrama == diagrama_id)
            .sort(-VersionDiagrama.numero_version)
            .first_or_none()
        )

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[VersionDiagrama]:
        return await (
            VersionDiagrama.find(VersionDiagrama.id_diagrama == diagrama_id)
            .sort(-VersionDiagrama.numero_version)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        return await VersionDiagrama.find(
            VersionDiagrama.id_diagrama == diagrama_id
        ).count()

    async def next_numero_version(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        """
        Siguiente número correlativo para una nueva versión del diagrama.
        (COALESCE(MAX, 0) + 1 del Ciclo 1: se lee la última y se suma 1.)
        """
        ultima = await self.get_ultima_by_diagrama(diagrama_id)
        if ultima is None:
            return 1
        return ultima.numero_version + 1

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, version: VersionDiagrama
    ) -> VersionDiagrama:
        await version.insert()
        return version

    async def delete(self, version: VersionDiagrama) -> None:
        await version.delete()

    async def delete_versiones_antiguas(
        self,
        diagrama_id: PydanticObjectId,
        *,
        conservar_ultimas: int = 50,
    ) -> int:
        """
        Conserva solo las N versiones más recientes de un diagrama.
        Devuelve cuántas versiones eliminó. ($nin del Ciclo 2 ≈ NOT IN.)
        """
        a_conservar = await (
            VersionDiagrama.find(VersionDiagrama.id_diagrama == diagrama_id)
            .sort(-VersionDiagrama.numero_version)
            .limit(conservar_ultimas)
            .to_list()
        )
        ids_conservar = [version.id for version in a_conservar]
        resultado = await VersionDiagrama.find(
            VersionDiagrama.id_diagrama == diagrama_id,
            {"_id": {"$nin": ids_conservar}},
        ).delete()
        return int(getattr(resultado, "deleted_count", 0) or 0)


# ======================================================================
# ComentarioDiagramaRepository
# ======================================================================
class ComentarioDiagramaRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, comentario_id: PydanticObjectId
    ) -> Optional[ComentarioDiagrama]:
        return await ComentarioDiagrama.get(comentario_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        solo_no_resueltos: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ComentarioDiagrama]:
        condiciones = [ComentarioDiagrama.id_diagrama == diagrama_id]
        if solo_no_resueltos:
            condiciones.append(ComentarioDiagrama.resuelto == False)  # noqa: E712
        return await (
            ComentarioDiagrama.find(*condiciones)
            .sort(-ComentarioDiagrama.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_entidad(
        self,
        diagrama_id: PydanticObjectId,
        tipo_entidad: str,
        id_entidad: str,
    ) -> Sequence[ComentarioDiagrama]:
        """
        Comentarios sobre un elemento específico (ej. una clase concreta;
        id_entidad = uuid del embebido del Diagrama).
        """
        return await (
            ComentarioDiagrama.find(
                ComentarioDiagrama.id_diagrama == diagrama_id,
                ComentarioDiagrama.tipo_entidad == tipo_entidad,
                ComentarioDiagrama.id_entidad == id_entidad,
            )
            .sort(-ComentarioDiagrama.created_at)
            .to_list()
        )

    async def list_generales_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[ComentarioDiagrama]:
        """Comentarios generales al diagrama (sin tipo_entidad ni
        id_entidad)."""
        return await (
            ComentarioDiagrama.find(
                ComentarioDiagrama.id_diagrama == diagrama_id,
                ComentarioDiagrama.tipo_entidad == None,  # noqa: E711 (Mongo: null)
                ComentarioDiagrama.id_entidad == None,    # noqa: E711 (Mongo: null)
            )
            .sort(-ComentarioDiagrama.created_at)
            .to_list()
        )

    async def count_no_resueltos(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        return await ComentarioDiagrama.find(
            ComentarioDiagrama.id_diagrama == diagrama_id,
            ComentarioDiagrama.resuelto == False,  # noqa: E712
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, comentario: ComentarioDiagrama
    ) -> ComentarioDiagrama:
        await comentario.insert()
        return comentario

    async def update(
        self, comentario: ComentarioDiagrama
    ) -> ComentarioDiagrama:
        await comentario.save()
        return comentario

    async def marcar_resuelto(
        self,
        comentario_id: PydanticObjectId,
        *,
        resuelto: bool = True,
    ) -> Optional[ComentarioDiagrama]:
        comentario = await self.get_by_id(comentario_id)
        if comentario is None:
            return None
        comentario.resuelto = resuelto
        await comentario.save()
        return comentario

    async def delete(self, comentario: ComentarioDiagrama) -> None:
        await comentario.delete()