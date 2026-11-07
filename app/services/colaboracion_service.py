# app/services/colaboracion_service.py
"""
Lógica de negocio del módulo B. Colaboración (sesiones en tiempo real).

Se encarga de:
- Abrir una sesión colaborativa sobre un diagrama (o reutilizar la activa).
- Registrar la entrada/salida de participantes.
- Actualizar la posición del cursor de cada participante (dict libre,
  antes JSONB).
- Cerrar sesiones cuando el diagrama/proyecto se archiva o cuando ya no
  quedan participantes.

NO emite eventos por WebSocket: eso lo hace la capa `websocket/`.
Este servicio es el que persiste el estado para que el WebSocket lo consulte.

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Servicio SIN ESTADO: sin AsyncSession ni commit()/refresh(). Cada
  insert()/save() del repositorio persiste de inmediato.
- La tabla participantes_sesion desapareció: cada participante va EMBEBIDO
  en SesionColaboracion.participantes. Las escrituras RE-LEEN la sesión,
  mutan la lista embebida y la guardan (fetch → modificar → save); un
  participante reingresado genera una NUEVA entrada (la anterior conserva
  su left_at, como las filas del Ciclo 1).
- get_by_id(con_participantes=True) ya no existe: leer la sesión siempre
  trae sus participantes.
- _require_miembro consulta el miembro EMBEBIDO del proyecto
  (MiembroProyectoRepository re-lee el documento Proyecto).
"""

from typing import Sequence

from beanie import PydanticObjectId

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
    """Sesiones colaborativas y presencia de sus participantes."""

    def __init__(self) -> None:
        self.sesiones = SesionColaboracionRepository()
        self.participantes = ParticipanteSesionRepository()
        self.diagramas = DiagramaRepository()
        self.miembros = MiembroProyectoRepository()

    # ------------------------------------------------------------------
    # Sesiones
    # ------------------------------------------------------------------
    async def abrir_o_obtener_sesion(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
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
            # insert() asigna el ObjectId y persiste: sin commit/refresh
            sesion = await self.sesiones.create(sesion)

        return SesionColaboracionResponse.model_validate(sesion)

    async def obtener_sesion_con_participantes(
        self,
        sesion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> SesionConParticipantesResponse:
        # Los participantes vienen embebidos (antes con_participantes=True)
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")
        await self._require_miembro(sesion.id_proyecto, usuario_id)
        return SesionConParticipantesResponse.model_validate(sesion)

    async def cerrar_sesion(
        self,
        sesion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> None:
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")
        await self._require_miembro(sesion.id_proyecto, usuario_id)
        await self.sesiones.cerrar_sesion(sesion_id)

    # ------------------------------------------------------------------
    # Participantes
    # ------------------------------------------------------------------
    async def unir_participante(
        self,
        sesion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
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
            id_usuario=usuario_id,
        )
        # create() recibe la sesión RE-LEÍDA: agrega el embebido y la guarda
        participante = await self.participantes.create(sesion, participante)
        return ParticipanteSesionResponse.model_validate(participante)

    async def salir_participante(
        self,
        sesion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> None:
        """
        Marca la salida del participante. Si era el último conectado,
        cierra la sesión automáticamente.
        """
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")

        # Localizar la entrada ABIERTA del usuario: un reingreso agrega una
        # NUEVA entrada embebida, así que participante() (primer match)
        # podría devolver una vieja ya cerrada. La salida marca la que
        # sigue conectada y es idempotente si ya se fue.
        participante = next(
            (
                p
                for p in sesion.participantes
                if p.id_usuario == usuario_id and p.left_at is None
            ),
            None,
        )
        if participante is not None:
            await self.participantes.marcar_salida(sesion, participante)

        # Si no quedan conectados, cerrar sesión
        conectados = await self.participantes.count_conectados_by_sesion(
            sesion_id
        )
        if conectados == 0:
            await self.sesiones.cerrar_sesion(sesion_id)

    async def listar_participantes_conectados(
        self,
        sesion_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> Sequence[ParticipanteSesionResponse]:
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")
        await self._require_miembro(sesion.id_proyecto, usuario_id)
        conectados = await self.participantes.list_conectados_by_sesion(
            sesion_id
        )
        return [ParticipanteSesionResponse.model_validate(p) for p in conectados]

    async def listar_conectados_por_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
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
        sesion_id: PydanticObjectId,
        datos: ParticipanteSesionUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> ParticipanteSesionResponse:
        """
        Actualiza la posición/foco del cursor del participante actual.
        Persistimos el dict libre en `posicion_cursor` (x, y, zoom,
        elemento activo…).
        """
        sesion = await self.sesiones.get_by_id(sesion_id)
        if sesion is None:
            raise NotFoundError("Sesión no encontrada")

        await self._require_miembro(sesion.id_proyecto, usuario_id)

        # El embebido no tiene id propio y un reingreso deja varias entradas
        # del mismo usuario: se actualiza la ABIERTA (la que sigue en la
        # sesión), no la primera que aparezca.
        participante = next(
            (
                p
                for p in sesion.participantes
                if p.id_usuario == usuario_id and p.left_at is None
            ),
            None,
        )
        if participante is None:
            raise NotFoundError("El usuario no está unido a la sesión")

        participante = await self.participantes.actualizar_cursor(
            sesion, participante, datos.posicion_cursor
        )
        return ParticipanteSesionResponse.model_validate(participante)

    # ------------------------------------------------------------------
    # Cierre forzado (limpieza)
    # ------------------------------------------------------------------
    async def cerrar_sesiones_de_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
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

        # Marcar salida a todos los conectados (cada sesión re-leída lleva
        # sus participantes embebidos; el save persiste la lista completa)
        activas = await self.sesiones.list_activas_by_proyecto(
            diagrama.id_proyecto
        )
        for sesion in activas:
            if sesion.id_diagrama != diagrama_id:
                continue
            for p in sesion.participantes:
                if p.conectado:
                    await self.participantes.marcar_salida(sesion, p)

        # UN update_many cierra todas las sesiones activas del diagrama
        cerradas = await self.sesiones.cerrar_todas_by_diagrama(diagrama_id)
        return cerradas

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    async def _require_miembro(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> None:
        # El miembro vive EMBEBIDO en el proyecto: el repositorio re-lee
        # el documento Proyecto y busca en su lista miembros.
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            # 404 para no revelar existencia de proyectos ajenos
            raise NotFoundError("Recurso no encontrado")