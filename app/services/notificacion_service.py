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
"""

from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

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
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notificaciones = NotificacionRepository(db)
        self.miembros = MiembroProyectoRepository(db)

    # ==================================================================
    # LECTURAS
    # ==================================================================
    async def listar(
        self,
        usuario_id: int,
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
        usuario_id: int,
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
        self, usuario_id: int
    ) -> ContadorNoLeidasResponse:
        total = await self.notificaciones.count_no_leidas(usuario_id)
        return ContadorNoLeidasResponse(total_no_leidas=total)

    async def obtener(
        self, notificacion_id: int, *, usuario_id: int
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
    async def crear(
        self, datos: NotificacionCreate, *, commit: bool = True
    ) -> NotificacionResponse:
        """
        Crea una notificación para un usuario concreto.

        `commit=False` permite usarlo desde otros servicios (generación,
        comentarios, etc.) dentro de una transacción mayor, dejando el
        commit al llamador.
        """
        notificacion = Notificacion(
            id_usuario=datos.id_usuario,
            tipo=datos.tipo,
            mensaje=datos.mensaje,
            id_referencia=datos.id_referencia,
            leida=False,
        )
        notificacion = await self.notificaciones.create(notificacion)
        if commit:
            await self.db.commit()
            await self.db.refresh(notificacion)
        return NotificacionResponse.model_validate(notificacion)

    async def crear_para_miembros_de_proyecto(
        self,
        proyecto_id: int,
        *,
        tipo: str,
        mensaje: str,
        id_referencia: Optional[int] = None,
        excluir_usuario_id: Optional[int] = None,
        commit: bool = True,
    ) -> int:
        """
        Notifica a todos los miembros de un proyecto (opcionalmente
        excluyendo al que disparó el evento).
        Devuelve cuántas notificaciones se crearon.
        """
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

        await self.notificaciones.bulk_create(notifs)
        if commit:
            await self.db.commit()
        return len(notifs)

    # ==================================================================
    # ACTUALIZACIÓN
    # ==================================================================
    async def marcar_leida(
        self, notificacion_id: int, *, usuario_id: int, leida: bool = True
    ) -> NotificacionResponse:
        notificacion = await self.notificaciones.get_by_id(notificacion_id)
        if notificacion is None:
            raise NotFoundError("Notificación no encontrada")
        if notificacion.id_usuario != usuario_id:
            raise ForbiddenError("No puede modificar notificaciones de otro usuario")

        notificacion = await self.notificaciones.marcar_leida(
            notificacion_id, leida=leida
        )
        await self.db.commit()
        await self.db.refresh(notificacion)
        return NotificacionResponse.model_validate(notificacion)

    async def marcar_varias_leidas(
        self,
        usuario_id: int,
        *,
        ids: Optional[list[int]] = None,
        todas: bool = False,
    ) -> int:
        """
        Marca varias notificaciones como leídas.
        - `todas=True` → todas las no leídas del usuario.
        - `ids=[...]` → solo esas (defensa por id_usuario en el repo).
        Devuelve cuántas filas se actualizaron.
        """
        if todas:
            actualizadas = await self.notificaciones.marcar_todas_leidas(usuario_id)
        else:
            if not ids:
                return 0
            actualizadas = await self.notificaciones.marcar_varias_leidas(
                usuario_id, ids
            )
        await self.db.commit()
        return actualizadas

    # ==================================================================
    # ELIMINACIÓN
    # ==================================================================
    async def eliminar(self, notificacion_id: int, *, usuario_id: int) -> None:
        notificacion = await self.notificaciones.get_by_id(notificacion_id)
        if notificacion is None:
            raise NotFoundError("Notificación no encontrada")
        if notificacion.id_usuario != usuario_id:
            raise ForbiddenError("No puede eliminar notificaciones de otro usuario")
        await self.notificaciones.delete(notificacion)
        await self.db.commit()

    async def limpiar_leidas(self, usuario_id: int) -> int:
        """Borra todas las notificaciones ya leídas del usuario."""
        eliminadas = await self.notificaciones.delete_leidas_by_usuario(usuario_id)
        await self.db.commit()
        return eliminadas