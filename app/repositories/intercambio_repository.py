# app/repositories/intercambio_repository.py
"""
Repositorio de acceso a datos del módulo E. Intercambio de Modelos
(XMI/XML) — CICLO 2.

- ExportacionRepository → colección `exportaciones_diagrama`
- ImportacionRepository → colección `importaciones_diagrama`

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorios SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- Las 2 colecciones se conservan SEPARADAS (mismo criterio que los
  modelos: son bitácoras que crecen linealmente con el uso; embeberlas
  haría crecer el Diagrama sin límite).
- ids int → PydanticObjectId (ObjectId de Mongo).
- flush/refresh → insert()/save()/delete() de Beanie.
- En el Ciclo 2 estos registros documentan el round-trip DevForge ↔
  Enterprise Architect: el conversor XMI (lxml) llama a
  actualizar_estado con EXITOSO/FALLIDO al terminar cada operación.
"""

from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.intercambio import ExportacionDiagrama, ImportacionDiagrama


# ======================================================================
# ExportacionRepository
# ======================================================================
class ExportacionRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, exportacion_id: PydanticObjectId
    ) -> Optional[ExportacionDiagrama]:
        return await ExportacionDiagrama.get(exportacion_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ExportacionDiagrama]:
        return await (
            ExportacionDiagrama.find(
                ExportacionDiagrama.id_diagrama == diagrama_id
            )
            .sort(-ExportacionDiagrama.exported_at)
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
    ) -> Sequence[ExportacionDiagrama]:
        return await (
            ExportacionDiagrama.find(
                ExportacionDiagrama.id_usuario == usuario_id
            )
            .sort(-ExportacionDiagrama.exported_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        return await ExportacionDiagrama.find(
            ExportacionDiagrama.id_diagrama == diagrama_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, exportacion: ExportacionDiagrama
    ) -> ExportacionDiagrama:
        await exportacion.insert()
        return exportacion

    async def delete(self, exportacion: ExportacionDiagrama) -> None:
        await exportacion.delete()


# ======================================================================
# ImportacionRepository
# ======================================================================
class ImportacionRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, importacion_id: PydanticObjectId
    ) -> Optional[ImportacionDiagrama]:
        return await ImportacionDiagrama.get(importacion_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ImportacionDiagrama]:
        return await (
            ImportacionDiagrama.find(
                ImportacionDiagrama.id_diagrama == diagrama_id
            )
            .sort(-ImportacionDiagrama.imported_at)
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
    ) -> Sequence[ImportacionDiagrama]:
        return await (
            ImportacionDiagrama.find(
                ImportacionDiagrama.id_usuario == usuario_id
            )
            .sort(-ImportacionDiagrama.imported_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

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
        return await (
            ImportacionDiagrama.find(ImportacionDiagrama.estado == estado)
            .sort(-ImportacionDiagrama.imported_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        return await ImportacionDiagrama.find(
            ImportacionDiagrama.id_diagrama == diagrama_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, importacion: ImportacionDiagrama
    ) -> ImportacionDiagrama:
        await importacion.insert()
        return importacion

    async def update(
        self, importacion: ImportacionDiagrama
    ) -> ImportacionDiagrama:
        await importacion.save()
        return importacion

    async def actualizar_estado(
        self, importacion_id: PydanticObjectId, estado: str
    ) -> Optional[ImportacionDiagrama]:
        importacion = await self.get_by_id(importacion_id)
        if importacion is None:
            return None
        importacion.estado = estado
        await importacion.save()
        return importacion

    async def delete(self, importacion: ImportacionDiagrama) -> None:
        await importacion.delete()