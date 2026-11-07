# app/repositories/ia_repository.py
"""
Repositorio de acceso a datos del módulo G. IA Asistente — CICLO 2.

En el Ciclo 1 había UN solo repositorio (InteraccionIARepository) sobre la
tabla `interacciones_ia`, que mezclaba en una sola fila el mensaje del
chat, el contexto enviado al modelo y la acción resultante. En el Ciclo 2
esa tabla se divide en 3 COLECCIONES nuevas y el repositorio en 3:

- MensajeChatRepository → colección `mensajes_chat` (la conversación;
  entrada del Agente Dev CU16-CU21 y del Asistente Guía CU23).
- ContextoIARepository  → colección `contextos_ia`  (lo que se envió al
  modelo en cada turno, CU17).
- AccionIARepository    → colección `acciones_ia`   (ciclo de vida de cada
  acción del Agente Dev sobre el diagrama).

Correspondencia con los métodos del Ciclo 1 (InteraccionIARepository):
- list_by_canal / count_by_canal ('VOZ'/'TEXTO') →
  MensajeChatRepository.list_by_origen / count_by_origen: el canal de
  entrada vive ahora en MensajeChat.origen.
- list_by_proyecto / count_by_proyecto → MensajeChatRepository: es el
  único de los 3 con id_proyecto (existe chat general del usuario).
- list_aplicadas_by_diagrama → AccionIARepository.list_aplicadas_by_diagrama
  (estado "APLICADA").
- marcar_accion_aplicada(aplicada=True/False) → AccionIARepository.
  marcar_aplicada / marcar_rechazada / marcar_fallida: el ciclo de vida
  de la acción dejó de ser booleano (PROPUESTA → APLICADA / RECHAZADA /
  FALLIDA) y reutiliza los helpers del propio documento.
- update genérico → MensajeChat/AccionIA lo conservan; ContextoIA no lo
  tiene: el contexto de un turno ya enviado no se reescribe (para
  corregirlo se arma y guarda uno nuevo).

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorios SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- ids int → PydanticObjectId (ObjectId de Mongo).
- flush/refresh → insert()/save()/delete() de Beanie.
- list_historial_by_diagrama es NUEVO: últimos N mensajes en ORDEN
  CRONOLÓGICO, la ventana del historial que el ensamblador de contexto
  (CU17) manda al modelo en cada turno.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.accion_ia import AccionIA
from app.models.contexto_ia import ContextoIA
from app.models.mensaje_chat import MensajeChat


def _ahora(cuando: Optional[datetime] = None) -> datetime:
    """Fecha de trabajo aware; permite inyectar `cuando` en tests."""
    return cuando or datetime.now(timezone.utc)


# ======================================================================
# MensajeChatRepository
# ======================================================================
class MensajeChatRepository:
    """La conversación completa: mensajes de TEXTO y de VOZ (transcripción
    local con faster-whisper) entre el usuario y la IA."""

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, mensaje_id: PydanticObjectId
    ) -> Optional[MensajeChat]:
        return await MensajeChat.get(mensaje_id)

    async def list_by_proyecto(
        self,
        proyecto_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[MensajeChat]:
        return await (
            MensajeChat.find(MensajeChat.id_proyecto == proyecto_id)
            .sort(-MensajeChat.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[MensajeChat]:
        return await (
            MensajeChat.find(MensajeChat.id_diagrama == diagrama_id)
            .sort(-MensajeChat.created_at)
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
    ) -> Sequence[MensajeChat]:
        return await (
            MensajeChat.find(MensajeChat.id_usuario == usuario_id)
            .sort(-MensajeChat.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_origen(
        self,
        origen: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[MensajeChat]:
        """Filtra por 'TEXTO' o 'VOZ' (antes list_by_canal)."""
        return await (
            MensajeChat.find(MensajeChat.origen == origen)
            .sort(-MensajeChat.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_historial_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        limit: int = 20,
    ) -> Sequence[MensajeChat]:
        """
        Últimos `limit` mensajes del chat del diagrama en ORDEN
        CRONOLÓGICO (del más viejo al más nuevo). Es la ventana del
        historial que el ensamblador de contexto (CU17) incluye en cada
        turno y la que se renderiza al abrir el chat.
        """
        recientes = await (
            MensajeChat.find(MensajeChat.id_diagrama == diagrama_id)
            .sort(-MensajeChat.created_at)
            .limit(limit)
            .to_list()
        )
        return list(reversed(recientes))

    async def count_by_proyecto(self, proyecto_id: PydanticObjectId) -> int:
        return await MensajeChat.find(
            MensajeChat.id_proyecto == proyecto_id
        ).count()

    async def count_by_origen(self, origen: str) -> int:
        """(Antes count_by_canal.)"""
        return await MensajeChat.find(MensajeChat.origen == origen).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, mensaje: MensajeChat) -> MensajeChat:
        await mensaje.insert()
        return mensaje

    async def update(self, mensaje: MensajeChat) -> MensajeChat:
        await mensaje.save()
        return mensaje

    async def delete(self, mensaje: MensajeChat) -> None:
        await mensaje.delete()


# ======================================================================
# ContextoIARepository
# ======================================================================
class ContextoIARepository:
    """
    Bitácora de lo enviado al modelo en cada turno (CU17): resumen del
    diagrama, ventana del historial, elementos seleccionados… Solo se
    crea y se consulta: el contexto de un turno ya enviado no se
    reescribe (para corregirlo se arma y guarda uno nuevo), por eso no
    hay update.
    """

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, contexto_id: PydanticObjectId
    ) -> Optional[ContextoIA]:
        return await ContextoIA.get(contexto_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ContextoIA]:
        return await (
            ContextoIA.find(ContextoIA.id_diagrama == diagrama_id)
            .sort(-ContextoIA.created_at)
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
    ) -> Sequence[ContextoIA]:
        return await (
            ContextoIA.find(ContextoIA.id_usuario == usuario_id)
            .sort(-ContextoIA.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def get_ultimo_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[ContextoIA]:
        """
        Último contexto enviado para un diagrama: permite rearmar el
        mismo turno tras una caída sin recalcular el ensamblado (ni el
        embedding de nomic-embed-text).
        """
        return await (
            ContextoIA.find(ContextoIA.id_diagrama == diagrama_id)
            .sort(-ContextoIA.created_at)
            .first_or_none()
        )

    async def count_by_diagrama(self, diagrama_id: PydanticObjectId) -> int:
        return await ContextoIA.find(
            ContextoIA.id_diagrama == diagrama_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, contexto: ContextoIA) -> ContextoIA:
        await contexto.insert()
        return contexto

    async def delete(self, contexto: ContextoIA) -> None:
        await contexto.delete()


# ======================================================================
# AccionIARepository
# ======================================================================
class AccionIARepository:
    """
    Ciclo de vida de las acciones del Agente Dev (CU16-CU21): el LLM NO
    toca el lienzo, propone (PROPUESTA) y el ejecutor del backend aplica
    el cambio sobre los embebidos del Diagrama — o el usuario rechaza.
    tipo_accion usa el MISMO vocabulario de tipo_operacion de la cola
    offline (módulo H): el mismo ejecutor procesa ambas fuentes.
    """

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, accion_id: PydanticObjectId
    ) -> Optional[AccionIA]:
        return await AccionIA.get(accion_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[AccionIA]:
        return await (
            AccionIA.find(AccionIA.id_diagrama == diagrama_id)
            .sort(-AccionIA.created_at)
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
    ) -> Sequence[AccionIA]:
        return await (
            AccionIA.find(AccionIA.id_usuario == usuario_id)
            .sort(-AccionIA.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_pendientes_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[AccionIA]:
        """Acciones PROPUESTA que aún esperan al ejecutor o la decisión
        del usuario (aceptar/rechazar)."""
        return await (
            AccionIA.find(
                AccionIA.id_diagrama == diagrama_id,
                AccionIA.estado == "PROPUESTA",
            )
            .sort(-AccionIA.created_at)
            .to_list()
        )

    async def list_aplicadas_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[AccionIA]:
        """Acciones que la IA aplicó efectivamente al diagrama
        (estado APLICADA)."""
        return await (
            AccionIA.find(
                AccionIA.id_diagrama == diagrama_id,
                AccionIA.estado == "APLICADA",
            )
            .sort(-AccionIA.created_at)
            .to_list()
        )

    async def count_pendientes_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        """Contador para el badge de propuestas sin resolver del chat."""
        return await AccionIA.find(
            AccionIA.id_diagrama == diagrama_id,
            AccionIA.estado == "PROPUESTA",
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, accion: AccionIA) -> AccionIA:
        await accion.insert()
        return accion

    async def update(self, accion: AccionIA) -> AccionIA:
        await accion.save()
        return accion

    async def delete(self, accion: AccionIA) -> None:
        await accion.delete()

    async def marcar_aplicada(
        self,
        accion_id: PydanticObjectId,
        *,
        cuando: Optional[datetime] = None,
    ) -> Optional[AccionIA]:
        """Marca la acción como APLICADA (antes
        marcar_accion_aplicada(aplicada=True))."""
        accion = await self.get_by_id(accion_id)
        if accion is None:
            return None
        if cuando is None:
            # Helper del documento: estado + aplicada_at en un paso.
            accion.marcar_aplicada()
        else:
            accion.estado = "APLICADA"
            accion.aplicada_at = cuando
        await accion.save()
        return accion

    async def marcar_rechazada(
        self,
        accion_id: PydanticObjectId,
        *,
        detalle: Optional[str] = None,
    ) -> Optional[AccionIA]:
        """El usuario (o el validador UML) rechazó la propuesta."""
        accion = await self.get_by_id(accion_id)
        if accion is None:
            return None
        accion.marcar_rechazada(detalle)
        await accion.save()
        return accion

    async def marcar_fallida(
        self,
        accion_id: PydanticObjectId,
        *,
        detalle: Optional[str] = None,
    ) -> Optional[AccionIA]:
        """La aplicación falló (p. ej. validación UML 2.5.1 incorrecta)."""
        accion = await self.get_by_id(accion_id)
        if accion is None:
            return None
        accion.marcar_fallida(detalle)
        await accion.save()
        return accion