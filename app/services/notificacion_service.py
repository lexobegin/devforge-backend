# app/services/notificacion_service.py
"""
Lógica de negocio del módulo I. Notificaciones.

Cubre:
- Crear notificaciones individuales o en lote (por ejemplo, notificar a
  todos los miembros de un proyecto cuando termina una generación).
- Listar notificaciones del usuario (con o sin filtro de no leídas).
- Marcar leídas (una, varias o todas).
- Contador de no leídas (para el badge del dropdown).
- Limpieza de leídas.

Regla: un usuario solo puede ver y modificar SUS PROPIAS notificaciones.

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Servicio SIN ESTADO: sin AsyncSession ni commit()/refresh(). Cada
  create()/save()/delete() del repositorio persiste de inmediato, así
  que el parámetro `commit` del Ciclo 1 DESAPARECE de crear() y de
  crear_para_miembros_de_proyecto(): ya no hay transacción que diferir.
- Ids: usuario_id/notificacion_id pasan de int a PydanticObjectId;
  id_referencia pasa de BIGINT polimórfico a Optional[str] (str del
  ObjectId de un documento o uuid de un elemento embebido, según
  `tipo`), igual que ya viene alineado en NotificacionCreate del
  Ciclo 2.
- marcar_varias_leidas recibe list[PydanticObjectId] (el request del
  router ya trae ids de Mongo) y el repositorio hace UN update con la
  defensa por id_usuario incluida en la MISMA consulta ($in ≈ IN).
"""

from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.notificacion import Notificacion
from app.repositories.notificacion_repository import NotificacionRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.notificacion_schema import (
    ContadorNoLeidasResponse,
    NotificacionCreate,
    NotificacionResponse,
)


class NotificacionService:
    def __init__(self) -> None:
        self.notificaciones = NotificacionRepository()
        self.miembros = MiembroProyectoRepository()

    # ==================================================================
    # LECTURAS
    # ==================================================================
    async def listar(
        self,
        usuario_id: PydanticObjectId,
        *,
        solo_no_leidas: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[NotificacionResponse]:
        items = await self.notificaciones.list_by_usuario(
            usuario_id,
            solo_no_leidas=solo_no_leidas,
            skip=skip,
            limit=limit,
        )
        return [NotificacionResponse.model_validate(n) for n in items]

    async def listar_por_tipo(
        self,
        usuario_id: PydanticObjectId,
        tipo: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[NotificacionResponse]:
        items = await self.notificaciones.list_by_usuario_y_tipo(
            usuario_id, tipo, skip=skip, limit=limit
        )
        return [NotificacionResponse.model_validate(n) for n in items]

    async def contar_no_leidas(
        self, usuario_id: PydanticObjectId
    ) -> ContadorNoLeidasResponse:
        total = await self.notificaciones.count_no_leidas(usuario_id)
        return ContadorNoLeidasResponse(total_no_leidas=total)

    async def obtener(
        self,
        notificacion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> NotificacionResponse:
        notificacion = await self.notificaciones.get_by_id(notificacion_id)
        if notificacion is None:
            raise NotFoundError("Notificación no encontrada")
        if notificacion.id_usuario != usuario_id:
            raise ForbiddenError("No puede consultar notificaciones de otro usuario")
        return NotificacionResponse.model_validate(notificacion)

    # ==================================================================
    # CREACIÓN
    # ==================================================================
    async def crear(self, datos: NotificacionCreate) -> NotificacionResponse:
        """
        Crea una notificación para un usuario concreto.

        (En el Ciclo 1 tenía el parámetro `commit=False` para dejar el
        commit en manos del servicio invocante dentro de una transacción
        mayor; en el Ciclo 2 insert() ya persiste de inmediato, así que
        no hay nada que diferir.)
        """
        notificacion = Notificacion(
            id_usuario=datos.id_usuario,
            tipo=datos.tipo,
            mensaje=datos.mensaje,
            id_referencia=datos.id_referencia,
            leida=False,
        )
        notificacion = await self.notificaciones.create(notificacion)
        return NotificacionResponse.model_validate(notificacion)

    async def crear_para_miembros_de_proyecto(
        self,
        proyecto_id: PydanticObjectId,
        *,
        tipo: str,
        mensaje: str,
        id_referencia: Optional[str] = None,
        excluir_usuario_id: Optional[PydanticObjectId] = None,
    ) -> int:
        """
        Notifica a todos los miembros de un proyecto (opcionalmente
        excluyendo al que disparó el evento).
        Devuelve cuántas notificaciones se crearon.
        """
        # El repositorio re-lee el Proyecto y devuelve los miembros
        # EMBEBIDOS ordenados por joined_at (mismos objetos que el Ciclo 1,
        # ahora sin id de fila: la clave es id_usuario).
        miembros = await self.miembros.list_by_proyecto(proyecto_id)
        if not miembros:
            return 0

        notifs: list[Notificacion] = []
        for m in miembros:
            if excluir_usuario_id is not None and m.id_usuario == excluir_usuario_id:
                continue
            notifs.append(
                Notificacion(
                    id_usuario=m.id_usuario,
                    tipo=tipo,
                    mensaje=mensaje,
                    id_referencia=id_referencia,
                    leida=False,
                )
            )

        if not notifs:
            return 0

        # bulk_create es un bucle de insert(): cada uno asigna su ObjectId
        # (el add_all + commit del Ciclo 1 ya no tiene equivalente).
        await self.notificaciones.bulk_create(notifs)
        return len(notifs)

    # ==================================================================
    # ACTUALIZACIÓN
    # ==================================================================
    async def marcar_leida(
        self,
        notificacion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        leida: bool = True,
    ) -> NotificacionResponse:
        notificacion = await self.notificaciones.get_by_id(notificacion_id)
        if notificacion is None:
            raise NotFoundError("Notificación no encontrada")
        if notificacion.id_usuario != usuario_id:
            raise ForbiddenError("No puede modificar notificaciones de otro usuario")

        # (El Ciclo 1 seguía con commit() + refresh(); el repositorio del
        #  Ciclo 2 re-obtiene el documento, fija `leida` y hace save().)
        notificacion = await self.notificaciones.marcar_leida(
            notificacion_id, leida=leida
        )
        return NotificacionResponse.model_validate(notificacion)

    async def marcar_varias_leidas(
        self,
        usuario_id: PydanticObjectId,
        *,
        ids: Optional[list[PydanticObjectId]] = None,
        todas: bool = False,
    ) -> int:
        """
        Marca varias notificaciones como leídas.
        - `todas=True` → todas las no leídas del usuario.
        - `ids=[...]` → solo esas (defensa por id_usuario en el repo).
        Devuelve cuántas se actualizaron.
        """
        if todas:
            actualizadas = await self.notificaciones.marcar_todas_leidas(usuario_id)
        else:
            if not ids:
                return 0
            actualizadas = await self.notificaciones.marcar_varias_leidas(
                usuario_id, ids
            )
        return actualizadas

    # ==================================================================
    # ELIMINACIÓN
    # ==================================================================
    async def eliminar(
        self,
        notificacion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> None:
        notificacion = await self.notificaciones.get_by_id(notificacion_id)
        if notificacion is None:
            raise NotFoundError("Notificación no encontrada")
        if notificacion.id_usuario != usuario_id:
            raise ForbiddenError("No puede eliminar notificaciones de otro usuario")
        await self.notificaciones.delete(notificacion)

    async def limpiar_leidas(self, usuario_id: PydanticObjectId) -> int:
        """Borra todas las notificaciones ya leídas del usuario."""
        return await self.notificaciones.delete_leidas_by_usuario(usuario_id)