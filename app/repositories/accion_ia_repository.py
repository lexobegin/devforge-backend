# app/repositories/accion_ia_repository.py
"""
Repositorio de acceso a datos de las acciones del Agente Dev (módulo G,
parte 3) — CICLO 2.

ARCHIVO NUEVO del Ciclo 2: la acción resultante era una parte de la tabla
`interacciones_ia` del Ciclo 1 (InteraccionIARepository); con el
rediseño del módulo G vive en la colección `acciones_ia` (AccionIA) y
este repositorio gestiona su ciclo de vida:
- el LLM NO toca el lienzo: propone (PROPUESTA) y el ejecutor del backend
  aplica el cambio sobre los embebidos del Diagrama — o el usuario
  rechaza (CU18-CU21);
- marcar_accion_aplicada(aplicada=True/False) del Ciclo 1 se segmenta en
  marcar_aplicada / marcar_rechazada / marcar_fallida, reutilizando los
  helpers del propio documento;
- tipo_accion usa el MISMO vocabulario de tipo_operacion de la cola
  offline (módulo H): el mismo ejecutor procesa ambas fuentes.

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorio SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- ids int → PydanticObjectId (ObjectId de Mongo).
- flush/refresh → insert()/save()/delete() de Beanie.
- Las horas usan datetime.now(timezone.utc) (aware, igual que los
  modelos; el utcnow() naive del Ciclo 1 se descarta).
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.accion_ia import AccionIA


def _ahora(cuando: Optional[datetime] = None) -> datetime:
    """Fecha de trabajo aware; permite inyectar `cuando` en tests."""
    return cuando or datetime.now(timezone.utc)


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

    async def list_by_mensaje(
        self,
        mensaje_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[AccionIA]:
        """
        Acciones propuestas en el turno de UN mensaje (traza
        mensaje ↔ acciones). NUEVO Tanda 19: alimenta
        GET /mensajes/{id_mensaje}/acciones del ia_router (el Ciclo 1 lo
        resolvía con la tabla interacciones_ia; aquí las acciones son
        documentos AccionIA ligados por id_mensaje).
        """
        return await (
            AccionIA.find(AccionIA.id_mensaje == mensaje_id)
            .sort(-AccionIA.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_diagramas(
        self,
        diagrama_ids: Sequence[PydanticObjectId],
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[AccionIA]:
        """
        Acciones de VARIOS diagramas (consultar $in). NUEVO Tanda 19:
        alimenta GET /proyectos/{proyecto_id}/acciones del ia_router —
        el router resuelve los ids de diagrama del proyecto y esta
        consulta trae el historial combinado. Los None se descartan
        (GENERAR_CODIGO no lleva diagrama).
        """
        ids = [d for d in diagrama_ids if d is not None]
        if not ids:
            return []
        from beanie.operators import In

        return await (
            AccionIA.find(In(AccionIA.id_diagrama, ids))
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