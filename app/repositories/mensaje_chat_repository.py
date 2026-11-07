# app/repositories/mensaje_chat_repository.py
"""
Repositorio de acceso a datos del canal de chat (módulo G, parte 1)
— CICLO 2.

ARCHIVO NUEVO del Ciclo 2: los mensajes eran una parte de la tabla
`interacciones_ia` del Ciclo 1 (InteraccionIARepository); con el rediseño
del módulo G, la conversación vive en la colección `mensajes_chat`
(MensajeChat) y este repositorio la gestiona:
- canal de entrada del Agente Dev (CU16-CU21) y del Asistente Guía (CU23);
- list_by_origen/count_by_origen sustituyen a list_by_canal/count_by_canal
  (el canal de entrada vive en MensajeChat.origen: TEXTO/VOZ);
- es el único repositorio del módulo G con id_proyecto (existe chat
  general del usuario, sin diagrama).

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorio SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- ids int → PydanticObjectId (ObjectId de Mongo).
- flush/refresh → insert()/save()/delete() de Beanie.
- list_historial_by_diagrama es NUEVO: últimos N mensajes en ORDEN
  CRONOLÓGICO, la ventana del historial que el ensamblador de contexto
  (CU17) manda al modelo en cada turno.
"""

from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.mensaje_chat import MensajeChat


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