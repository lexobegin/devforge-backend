# app/repositories/sincronizacion_repository.py
"""
Repositorio de acceso a datos del módulo H. Sincronización Móvil/Web
Offline — CICLO 2.

- ColaSincronizacionRepository → colección `cola_sincronizacion_movil`

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorio SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- ids int → PydanticObjectId (ObjectId de Mongo); id_dispositivo e
  id_temporal_local siguen siendo str (los genera el cliente).
- flush/refresh → insert()/save()/delete() de Beanie.
- bulk_create hace un bucle de insert(): Mongo no devuelve filas que
  haya que "refrescar" como el add_all + refresh del Ciclo 1; cada
  insert() asigna el ObjectId de su ítem.
- delete_sincronizados_by_dispositivo usa UN delete con filtro (el
  rowcount del Ciclo 1 es el deleted_count de Mongo).
- Conexión con el módulo G: tipo_operacion es el MISMO vocabulario de
  tipo_accion de la IA, así que el ejecutor de servicios procesa un
  cambio offline igual que una acción del Agente Dev.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.sincronizacion import ColaSincronizacionMovil


def _ahora(cuando: Optional[datetime] = None) -> datetime:
    """Fecha de trabajo aware; permite inyectar `cuando` en tests."""
    return cuando or datetime.now(timezone.utc)


# ======================================================================
# ColaSincronizacionRepository
# ======================================================================
class ColaSincronizacionRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, item_id: PydanticObjectId
    ) -> Optional[ColaSincronizacionMovil]:
        return await ColaSincronizacionMovil.get(item_id)

    async def get_by_dispositivo_y_temporal(
        self, id_dispositivo: str, id_temporal_local: str
    ) -> Optional[ColaSincronizacionMovil]:
        """
        Busca un ítem ya registrado por su id local del dispositivo.
        Sirve para hacer idempotente el reenvío de un mismo cambio
        (si el cliente reintenta, no se duplica).
        """
        return await ColaSincronizacionMovil.find_one(
            ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
            ColaSincronizacionMovil.id_temporal_local == id_temporal_local,
        )

    async def list_pendientes_by_dispositivo(
        self, id_dispositivo: str
    ) -> Sequence[ColaSincronizacionMovil]:
        """Todos los ítems PENDIENTES de un dispositivo, en orden de
        llegada."""
        return await (
            ColaSincronizacionMovil.find(
                ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
                ColaSincronizacionMovil.estado == "PENDIENTE",
            )
            .sort(+ColaSincronizacionMovil.created_at)
            .to_list()
        )

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        estado: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ColaSincronizacionMovil]:
        condiciones = [ColaSincronizacionMovil.id_diagrama == diagrama_id]
        if estado is not None:
            condiciones.append(ColaSincronizacionMovil.estado == estado)
        return await (
            ColaSincronizacionMovil.find(*condiciones)
            .sort(+ColaSincronizacionMovil.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_usuario(
        self,
        usuario_id: PydanticObjectId,
        *,
        estado: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ColaSincronizacionMovil]:
        condiciones = [ColaSincronizacionMovil.id_usuario == usuario_id]
        if estado is not None:
            condiciones.append(ColaSincronizacionMovil.estado == estado)
        return await (
            ColaSincronizacionMovil.find(*condiciones)
            .sort(-ColaSincronizacionMovil.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_conflictos_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[ColaSincronizacionMovil]:
        """Ítems con estado CONFLICTO, pendientes de resolución manual."""
        return await (
            ColaSincronizacionMovil.find(
                ColaSincronizacionMovil.id_diagrama == diagrama_id,
                ColaSincronizacionMovil.estado == "CONFLICTO",
            )
            .sort(+ColaSincronizacionMovil.created_at)
            .to_list()
        )

    async def count_by_estado(self, estado: str) -> int:
        return await ColaSincronizacionMovil.find(
            ColaSincronizacionMovil.estado == estado
        ).count()

    async def count_pendientes_by_dispositivo(
        self, id_dispositivo: str
    ) -> int:
        return await ColaSincronizacionMovil.find(
            ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
            ColaSincronizacionMovil.estado == "PENDIENTE",
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, item: ColaSincronizacionMovil
    ) -> ColaSincronizacionMovil:
        await item.insert()
        return item

    async def bulk_create(
        self, items: list[ColaSincronizacionMovil]
    ) -> list[ColaSincronizacionMovil]:
        """Registra un batch completo de cambios offline de una sola vez.
        (Cada insert() asigna el ObjectId de su ítem: el bucle sustituye
        al add_all + refresh del Ciclo 1.)"""
        for item in items:
            await item.insert()
        return items

    async def update(
        self, item: ColaSincronizacionMovil
    ) -> ColaSincronizacionMovil:
        await item.save()
        return item

    async def marcar_sincronizado(
        self,
        item_id: PydanticObjectId,
        *,
        cuando: Optional[datetime] = None,
    ) -> Optional[ColaSincronizacionMovil]:
        item = await self.get_by_id(item_id)
        if item is None:
            return None
        item.estado = "SINCRONIZADO"
        item.synced_at = _ahora(cuando)
        await item.save()
        return item

    async def marcar_conflicto(
        self, item_id: PydanticObjectId
    ) -> Optional[ColaSincronizacionMovil]:
        item = await self.get_by_id(item_id)
        if item is None:
            return None
        item.estado = "CONFLICTO"
        await item.save()
        return item

    async def delete(self, item: ColaSincronizacionMovil) -> None:
        await item.delete()

    async def delete_sincronizados_by_dispositivo(
        self, id_dispositivo: str
    ) -> int:
        """
        Housekeeping: elimina los ítems ya SINCRONIZADOS de un
        dispositivo. Se puede invocar periódicamente para no acumular
        documentos. Devuelve cuántos borró (el rowcount del Ciclo 1 es
        el deleted_count de Mongo).
        """
        resultado = await ColaSincronizacionMovil.find(
            ColaSincronizacionMovil.id_dispositivo == id_dispositivo,
            ColaSincronizacionMovil.estado == "SINCRONIZADO",
        ).delete()
        return int(getattr(resultado, "deleted_count", 0) or 0)