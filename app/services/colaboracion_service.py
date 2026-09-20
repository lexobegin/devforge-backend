# app/services/colaboracion_service.py
"""
Lógica de negocio del módulo B. Colaboración (sesiones en tiempo real).

Se encarga de:
- Abrir una sesión colaborativa sobre un diagrama (o reutilizar la activa).
- Registrar la entrada/salida de participantes.
- Actualizar la posición del cursor de cada participante (JSONB).
- Cerrar sesiones cuando el diagrama/proyecto se archiva o cuando ya no
  quedan participantes.

NO emite eventos por WebSocket: eso lo hace la capa `websocket/`.
Este servicio es el que persiste el estado para que el WebSocket lo consulte.
"""

from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.colaboracion import ParticipanteSesion, SesionColaboracion
from app.repositories.colaboracion_repository import (
    ParticipanteSesionRepository,
    SesionColaboracionRepository,
)
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.colaboracion_schema import (
    ParticipanteSesionResponse,
    ParticipanteSesionUpdate,
    SesionColaboracionResponse,
    SesionConParticipantesResponse,
)


class ColaboracionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.sesiones = SesionColaboracionRepository(db)
        self.participantes = ParticipanteSesionRepository(db)
        self.diagramas = DiagramaRepository(db)
        self.miembros = MiembroProyectoRepository(db)

    # ------------------------------------------------------------------
    # Sesiones
    # ------------------------------------------------------------------
    async def abrir_o_obtener_sesion(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
    ) -> SesionColaboracionResponse:
        """
        Si existe una sesión activa para el diagrama, la devuelve.
        Si no, crea una nueva. En ambos casos verifica que el usuario sea
        miembro del proyecto del diagrama.
        """
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")

        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        sesion = await self.sesiones.get_sesion_activa_by_diagrama(diagrama_id)
        if sesion is None:
            sesion = SesionColaboracion(
                id_proyecto=diagrama.id_proyecto,
                id_diagrama=diagrama_id,
            )
            sesion = await self.sesiones.create(sesion)
            await self.db.commit()
            await self.db.refresh(sesion)

        return SesionColaboracionResponse.model_validate(sesion)

    async def obtener_sesion_con_participantes(
        self, sesion_id: int, *, usuario_id: int
    ) -> SesionConParticipantesResponse:
        sesion = await self.sesiones.get_by_id(sesion_id, con_participantes=True)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")
        await self._require_miembro(sesion.id_proyecto, usuario_id)
        return SesionConParticipantesResponse.model_validate(sesion)

    async def cerrar_sesion(self, sesion_id: int, *, usuario_id: int) -> None:
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")
        await self._require_miembro(sesion.id_proyecto, usuario_id)
        await self.sesiones.cerrar_sesion(sesion_id)
        await self.db.commit()

    # ------------------------------------------------------------------
    # Participantes
    # ------------------------------------------------------------------
    async def unir_participante(
        self, sesion_id: int, *, usuario_id: int
    ) -> ParticipanteSesionResponse:
        """
        Registra al usuario como participante de la sesión.
        Si ya estaba registrado y sigue conectado, devuelve el mismo registro.
        Si había salido antes (left_at no nulo), crea uno nuevo.
        """
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")

        await self._require_miembro(sesion.id_proyecto, usuario_id)

        # ¿Ya está conectado?
        existente = await self.participantes.get_by_sesion_usuario(
            sesion_id, usuario_id
        )
        if existente is not None and existente.left_at is None:
            return ParticipanteSesionResponse.model_validate(existente)

        participante = ParticipanteSesion(
            id_sesion=sesion_id,
            id_usuario=usuario_id,
        )
        participante = await self.participantes.create(participante)
        await self.db.commit()
        await self.db.refresh(participante)
        return ParticipanteSesionResponse.model_validate(participante)

    async def salir_participante(
        self, sesion_id: int, *, usuario_id: int
    ) -> None:
        """
        Marca la salida del participante. Si era el último conectado,
        cierra la sesión automáticamente.
        """
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")

        await self.participantes.marcar_salida_by_sesion_usuario(
            sesion_id, usuario_id
        )

        # Si no quedan conectados, cerrar sesión
        conectados = await self.participantes.count_conectados_by_sesion(sesion_id)
        if conectados == 0:
            await self.sesiones.cerrar_sesion(sesion_id)

        await self.db.commit()

    async def listar_participantes_conectados(
        self, sesion_id: int, *, usuario_id: int
    ) -> Sequence[ParticipanteSesionResponse]:
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")
        await self._require_miembro(sesion.id_proyecto, usuario_id)
        conectados = await self.participantes.list_conectados_by_sesion(sesion_id)
        return [ParticipanteSesionResponse.model_validate(p) for p in conectados]

    async def listar_conectados_por_diagrama(
        self, diagrama_id: int, *, usuario_id: int
    ) -> Sequence[ParticipanteSesionResponse]:
        """
        Todos los participantes conectados (de cualquier sesión activa)
        en un diagrama. Lo usa el panel de colaboradores del editor.
        """
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        conectados = await self.participantes.list_conectados_by_diagrama(
            diagrama_id
        )
        return [ParticipanteSesionResponse.model_validate(p) for p in conectados]

    # ------------------------------------------------------------------
    # Cursor / foco en el lienzo
    # ------------------------------------------------------------------
    async def actualizar_cursor(
        self,
        sesion_id: int,
        datos: ParticipanteSesionUpdate,
        *,
        usuario_id: int,
    ) -> ParticipanteSesionResponse:
        """
        Actualiza la posición/foco del cursor del participante actual.
        Persistimos el JSONB en `posicion_cursor` (x, y, zoom, elemento activo…).
        """
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")

        await self._require_miembro(sesion.id_proyecto, usuario_id)

        participante = await self.participantes.get_by_sesion_usuario(
            sesion_id, usuario_id
        )
        if participante is None:
            raise NotFoundError("El usuario no está unido a la sesión")

        participante = await self.participantes.actualizar_cursor(
            participante.id, datos.posicion_cursor
        )
        await self.db.commit()
        await self.db.refresh(participante)
        return ParticipanteSesionResponse.model_validate(participante)

    # ------------------------------------------------------------------
    # Cierre forzado (limpieza)
    # ------------------------------------------------------------------
    async def cerrar_sesiones_de_diagrama(
        self, diagrama_id: int, *, usuario_id: int
    ) -> int:
        """
        Cierra todas las sesiones activas de un diagrama y marca la salida
        de sus participantes. Se usa, por ejemplo, al archivar el proyecto
        o al eliminar el diagrama.
        """
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        # Marcar salida a todos los conectados
        activas = await self.sesiones.list_activas_by_proyecto(diagrama.id_proyecto)
        for sesion in activas:
            if sesion.id_diagrama != diagrama_id:
                continue
            conectados = await self.participantes.list_conectados_by_sesion(
                sesion.id
            )
            for p in conectados:
                await self.participantes.marcar_salida(p.id)

        cerradas = await self.sesiones.cerrar_todas_by_diagrama(diagrama_id)
        await self.db.commit()
        return cerradas

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    async def _require_miembro(
        self, proyecto_id: int, usuario_id: int
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            # 404 para no revelar existencia de proyectos ajenos
            raise NotFoundError("Recurso no encontrado")