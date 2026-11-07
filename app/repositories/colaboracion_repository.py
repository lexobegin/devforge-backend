# app/repositories/colaboracion_repository.py
"""
Repositorio de acceso a datos del módulo B. Colaboración.

Incluye dos repositorios:
- SesionColaboracionRepository → colección `sesiones_colaboracion`
- ParticipanteSesionRepository → participantes EMBEBIDOS en
                                 SesionColaboracion.participantes

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorios SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- La tabla participantes_sesion desapareció: cada participante va EMBEBIDO
  en su sesión. Consecuencias en ParticipanteSesionRepository:
    * Los participantes ya NO tienen id propio: la clave es el par
      (sesión, id_usuario); get_by_id se retira.
    * Toda ESCRITURA recibe la SesionColaboracion RE-LEÍDA de la base,
      modifica su lista `participantes` y la guarda (regla
      fetch→modificar→save de Beanie).
    * get_by_id(con_participantes=True) ya no necesita selectinload: leer
      la sesión SIEMPRE trae sus participantes (el parámetro se retiró).
- list_conectados_by_diagrama ya no hace JOIN sesiones × participantes:
  se leen las sesiones activas y se filtran sus embebidos.
- cerrar_todas_by_diagrama usa UN update_many de MongoDB en lugar del
  bucle de flush del Ciclo 1.
- Las horas se generan con datetime.now(timezone.utc) (conscientes, igual
  que los default_factory de los modelos del Ciclo 2; el utcnow() naive
  del Ciclo 1 mezclaba zonas con los datetime de Mongo).
"""

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from beanie import PydanticObjectId

from app.models.colaboracion import ParticipanteSesion, SesionColaboracion


def _ahora(cuando: Optional[datetime] = None) -> datetime:
    """Fecha de trabajo aware; permite inyectar `cuando` en tests/cierres."""
    return cuando or datetime.now(timezone.utc)


# ======================================================================
# SesionColaboracionRepository
# ======================================================================
class SesionColaboracionRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, sesion_id: PydanticObjectId
    ) -> Optional[SesionColaboracion]:
        """Los participantes SIEMPRE vienen embebidos (antes
        con_participantes=True)."""
        return await SesionColaboracion.get(sesion_id)

    async def get_sesion_activa_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[SesionColaboracion]:
        """
        Devuelve la sesión activa (ended_at nulo) de un diagrama.
        Un diagrama debería tener a lo sumo una sesión activa a la vez.
        """
        return await (
            SesionColaboracion.find(
                SesionColaboracion.id_diagrama == diagrama_id,
                SesionColaboracion.ended_at == None,  # noqa: E711 (Mongo: null)
            )
            .sort(-SesionColaboracion.started_at)
            .first_or_none()
        )

    async def list_activas_by_proyecto(
        self, proyecto_id: PydanticObjectId
    ) -> Sequence[SesionColaboracion]:
        return await (
            SesionColaboracion.find(
                SesionColaboracion.id_proyecto == proyecto_id,
                SesionColaboracion.ended_at == None,  # noqa: E711 (Mongo: null)
            )
            .sort(-SesionColaboracion.started_at)
            .to_list()
        )

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[SesionColaboracion]:
        return await (
            SesionColaboracion.find(
                SesionColaboracion.id_diagrama == diagrama_id
            )
            .sort(-SesionColaboracion.started_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, sesion: SesionColaboracion
    ) -> SesionColaboracion:
        await sesion.insert()
        return sesion

    async def update(
        self, sesion: SesionColaboracion
    ) -> SesionColaboracion:
        await sesion.save()
        return sesion

    async def cerrar_sesion(
        self,
        sesion_id: PydanticObjectId,
        *,
        cuando: Optional[datetime] = None,
    ) -> Optional[SesionColaboracion]:
        """Marca `ended_at` en la sesión (la cierra)."""
        sesion = await self.get_by_id(sesion_id)
        if sesion is None:
            return None
        sesion.ended_at = _ahora(cuando)
        await sesion.save()
        return sesion

    async def cerrar_todas_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        cuando: Optional[datetime] = None,
    ) -> int:
        """
        Cierra todas las sesiones activas de un diagrama con UN
        update_many. Devuelve cuántas cerró. Útil cuando se archiva o
        elimina un diagrama.
        """
        resultado = await SesionColaboracion.find(
            SesionColaboracion.id_diagrama == diagrama_id,
            SesionColaboracion.ended_at == None,  # noqa: E711 (Mongo: null)
        ).update({"$set": {"ended_at": _ahora(cuando)}})
        return int(getattr(resultado, "modified_count", 0) or 0)


# ======================================================================
# ParticipanteSesionRepository (embebidos en SesionColaboracion)
# ======================================================================
class ParticipanteSesionRepository:
    """
    Operaciones sobre los participantes EMBEBIDOS de una sesión. En el
    Ciclo 1 cada método recibía/devolvía filas de participantes_sesion;
    en el Ciclo 2 la unidad de persistencia es la SESIÓN: los métodos de
    escritura reciben la SesionColaboracion re-leída de la base, modifican
    su lista `participantes` y la guardan.
    """

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_sesion_usuario(
        self,
        sesion_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> Optional[ParticipanteSesion]:
        sesion = await SesionColaboracion.get(sesion_id)
        if sesion is None:
            return None
        return sesion.participante(usuario_id)

    async def list_conectados_by_sesion(
        self, sesion_id: PydanticObjectId
    ) -> Sequence[ParticipanteSesion]:
        """Participantes que siguen conectados (left_at nulo), ordenados
        por joined_at. (Antes una query con left_at IS NULL; ahora se
        filtra la lista embebida de la sesión.)"""
        sesion = await SesionColaboracion.get(sesion_id)
        if sesion is None:
            return []
        return sorted(
            (p for p in sesion.participantes if p.conectado),
            key=lambda p: p.joined_at,
        )

    async def count_conectados_by_sesion(
        self, sesion_id: PydanticObjectId
    ) -> int:
        conectados = await self.list_conectados_by_sesion(sesion_id)
        return len(conectados)

    async def list_conectados_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[ParticipanteSesion]:
        """
        Participantes conectados en cualquier sesión activa de un diagrama.
        Útil para el panel de colaboradores del editor. (Sustituye al JOIN
        sesiones × participantes del Ciclo 1.)
        """
        sesiones = await SesionColaboracion.find(
            SesionColaboracion.id_diagrama == diagrama_id,
            SesionColaboracion.ended_at == None,  # noqa: E711 (Mongo: null)
        ).to_list()
        conectados = [
            p
            for sesion in sesiones
            for p in sesion.participantes
            if p.conectado
        ]
        return sorted(conectados, key=lambda p: p.joined_at)

    # ------------------------------------------------------------------
    # Escrituras (reciben la SesionColaboracion re-leída y la persisten)
    # ------------------------------------------------------------------
    async def create(
        self,
        sesion: SesionColaboracion,
        participante: ParticipanteSesion,
    ) -> ParticipanteSesion:
        sesion.participantes.append(participante)
        await sesion.save()
        return participante

    async def update(
        self,
        sesion: SesionColaboracion,
        participante: ParticipanteSesion,
    ) -> ParticipanteSesion:
        await sesion.save()
        return participante

    async def actualizar_cursor(
        self,
        sesion: SesionColaboracion,
        participante: ParticipanteSesion,
        posicion_cursor: Optional[dict[str, Any]],
    ) -> ParticipanteSesion:
        """Actualiza solo el campo libre de posición del cursor (antes
        JSONB): x, y, zoom y elemento enfocado, sin migraciones."""
        participante.posicion_cursor = posicion_cursor
        await sesion.save()
        return participante

    async def marcar_salida(
        self,
        sesion: SesionColaboracion,
        participante: ParticipanteSesion,
        *,
        cuando: Optional[datetime] = None,
    ) -> ParticipanteSesion:
        """Marca `left_at` (el participante se desconectó)."""
        participante.left_at = _ahora(cuando)
        await sesion.save()
        return participante

    async def marcar_salida_by_sesion_usuario(
        self,
        sesion_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
        *,
        cuando: Optional[datetime] = None,
    ) -> bool:
        sesion = await SesionColaboracion.get(sesion_id)
        if sesion is None:
            return False
        participante = sesion.participante(usuario_id)
        if participante is None:
            return False
        participante.left_at = _ahora(cuando)
        await sesion.save()
        return True