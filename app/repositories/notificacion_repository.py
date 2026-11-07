# app/repositories/notificacion_repository.py
"""
Repositorio de acceso a datos del módulo I. Notificaciones — CICLO 2.

- NotificacionRepository → colección `notificaciones`

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorio SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- ids int → PydanticObjectId (ObjectId de Mongo).
- flush/refresh → insert()/save()/delete() de Beanie.
- bulk_create hace un bucle de insert(): Mongo no devuelve filas que
  haya que "refrescar" como el add_all + refresh del Ciclo 1.
- marcar_varias_leidas / marcar_todas_leidas: el UPDATE ... WHERE IN del
  Ciclo 1 es UN update de MongoDB con la condición del usuario y
  leida=false en la MISMA consulta (defensa contra IDs ajenos incluida).
- delete_leidas_by_usuario usa UN delete con filtro (el rowcount del
  Ciclo 1 es el deleted_count de Mongo).
"""

from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.notificacion import Notificacion


# ======================================================================
# NotificacionRepository
# ======================================================================
class NotificacionRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, notificacion_id: PydanticObjectId
    ) -> Optional[Notificacion]:
        return await Notificacion.get(notificacion_id)

    async def list_by_usuario(
        self,
        usuario_id: PydanticObjectId,
        *,
        solo_no_leidas: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Notificacion]:
        condiciones = [Notificacion.id_usuario == usuario_id]
        if solo_no_leidas:
            condiciones.append(Notificacion.leida == False)  # noqa: E712
        return await (
            Notificacion.find(*condiciones)
            .sort(-Notificacion.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_usuario_y_tipo(
        self,
        usuario_id: PydanticObjectId,
        tipo: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Notificacion]:
        return await (
            Notificacion.find(
                Notificacion.id_usuario == usuario_id,
                Notificacion.tipo == tipo,
            )
            .sort(-Notificacion.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count_no_leidas(self, usuario_id: PydanticObjectId) -> int:
        """Contador para el badge del dropdown de notificaciones."""
        return await Notificacion.find(
            Notificacion.id_usuario == usuario_id,
            Notificacion.leida == False,  # noqa: E712
        ).count()

    async def count_by_usuario(self, usuario_id: PydanticObjectId) -> int:
        return await Notificacion.find(
            Notificacion.id_usuario == usuario_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, notificacion: Notificacion) -> Notificacion:
        await notificacion.insert()
        return notificacion

    async def bulk_create(
        self, notificaciones: list[Notificacion]
    ) -> list[Notificacion]:
        """
        Crea varias notificaciones a la vez (ej. notificar a todos los
        miembros de un proyecto cuando se completa una generación).
        (Cada insert() asigna el ObjectId de su ítem: el bucle sustituye
        al add_all + refresh del Ciclo 1.)
        """
        for notificacion in notificaciones:
            await notificacion.insert()
        return notificaciones

    async def update(self, notificacion: Notificacion) -> Notificacion:
        await notificacion.save()
        return notificacion

    async def marcar_leida(
        self,
        notificacion_id: PydanticObjectId,
        *,
        leida: bool = True,
    ) -> Optional[Notificacion]:
        notificacion = await self.get_by_id(notificacion_id)
        if notificacion is None:
            return None
        notificacion.leida = leida
        await notificacion.save()
        return notificacion

    async def marcar_varias_leidas(
        self,
        usuario_id: PydanticObjectId,
        ids: list[PydanticObjectId],
    ) -> int:
        """
        Marca varias notificaciones del usuario como leídas de una sola
        vez. Solo afecta a las que pertenecen al usuario (defensa contra
        IDs ajenos). Devuelve cuántas se actualizaron. ($in del Ciclo 2
        ≈ IN de SQL; la condición de usuario y leida=false viaja en la
        MISMA consulta.)
        """
        if not ids:
            return 0
        resultado = await Notificacion.find(
            Notificacion.id_usuario == usuario_id,
            {"_id": {"$in": ids}},
            Notificacion.leida == False,  # noqa: E712
        ).update({"$set": {"leida": True}})
        return int(getattr(resultado, "modified_count", 0) or 0)

    async def marcar_todas_leidas(
        self, usuario_id: PydanticObjectId
    ) -> int:
        """Marca todas las notificaciones no leídas de un usuario como
        leídas. Devuelve cuántas se actualizaron."""
        resultado = await Notificacion.find(
            Notificacion.id_usuario == usuario_id,
            Notificacion.leida == False,  # noqa: E712
        ).update({"$set": {"leida": True}})
        return int(getattr(resultado, "modified_count", 0) or 0)

    async def delete(self, notificacion: Notificacion) -> None:
        await notificacion.delete()

    async def delete_leidas_by_usuario(
        self, usuario_id: PydanticObjectId
    ) -> int:
        """Limpia todas las notificaciones ya leídas de un usuario.
        Devuelve cuántas borró."""
        resultado = await Notificacion.find(
            Notificacion.id_usuario == usuario_id,
            Notificacion.leida == True,  # noqa: E712
        ).delete()
        return int(getattr(resultado, "deleted_count", 0) or 0)