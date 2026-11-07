# app/schemas/sincronizacion_schema.py
"""
Esquemas Pydantic del módulo H. Sincronización Móvil/Web Offline:

- ColaSincronizacionMovil (persistencia)
- DTOs de operación para el envío de lotes (batches) desde el cliente
  offline y la resolución de conflictos.

Cambios respecto al Ciclo 1:
- id_usuario e id_diagrama pasan de FK int a PydanticObjectId de Beanie;
  id_diagrama sigue OPCIONAL (hay cambios no atados a un diagrama).
- ResultadoCambioSync.id_real pasa de int a Optional[str]: en el Ciclo 2 el
  recurso creado puede ser un elemento embebido (uuid) o un documento.
- EstadoSincronizacion es idéntico al de app/models/sincronizacion.py.
- El vocabulario de tipo_operacion es el MISMO que tipo_accion de acciones_ia
  (módulo G): un cambio puede nacer del chat, de la voz, del WebSocket o de
  un dispositivo offline y procesarse por el mismo ejecutor.
- En el Ciclo 2 el batch se procesa en orden y cada ítem queda registrado en
  la colección cola_sincronizacion_movil: los CONFLICTO quedan visibles para
  que el PROPIETARIO los resuelva con ResolverConflictoRequest.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables (alineados con app/models/sincronizacion.py)
# ======================================================================
EstadoSincronizacion = Literal["PENDIENTE", "SINCRONIZADO", "CONFLICTO"]


# ======================================================================
# ColaSincronizacionMovil
# ======================================================================
class ColaSincronizacionMovilBase(BaseModel):
    id_dispositivo: str = Field(
        ..., min_length=1, max_length=100,
        description="deviceId móvil o id de navegador persistido",
    )
    id_diagrama: Optional[PydanticObjectId] = None
    id_temporal_local: Optional[str] = Field(None, max_length=100)
    tipo_operacion: str = Field(
        ..., min_length=1, max_length=50,
        description="'CREAR_CLASE','MODIFICAR_ATRIBUTO','ELIMINAR_RELACION', etc.",
    )
    payload: dict[str, Any] = Field(default_factory=dict)


class ColaSincronizacionMovilCreate(ColaSincronizacionMovilBase):
    """
    El id_usuario se toma del token.
    Este esquema lo usa internamente el service al recibir un batch.
    """


class ColaSincronizacionMovilResponse(ColaSincronizacionMovilBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    id_usuario: PydanticObjectId
    estado: EstadoSincronizacion
    created_at: datetime
    synced_at: Optional[datetime] = None


# ======================================================================
# DTOs específicos de operación — envío de batch desde cliente offline
# ======================================================================
class CambioOfflineItem(BaseModel):
    """
    Un ítem individual de la cola offline que el cliente envía al backend
    al recuperar conexión. `id_temporal_local` es la referencia que el
    cliente generó localmente (SQLite / IndexedDB) y que el backend
    resolverá al id real.
    """

    id_temporal_local: str = Field(..., min_length=1, max_length=100)
    tipo_operacion: str = Field(..., min_length=1, max_length=50)
    payload: dict[str, Any] = Field(default_factory=dict)
    # Marca de tiempo local (para "último en escribir gana" en conflictos simples)
    timestamp_local: Optional[datetime] = None


class BatchSincronizacionRequest(BaseModel):
    """
    Payload para enviar un lote completo de cambios offline.
    El backend los procesa en orden y devuelve el mapeo de ids temporales
    a ids reales, más el detalle de conflictos detectados.
    """

    id_dispositivo: str = Field(..., min_length=1, max_length=100)
    id_diagrama: PydanticObjectId  # string hex en JSON (antes int)
    cambios: list[CambioOfflineItem] = Field(..., min_length=1)


class ResultadoCambioSync(BaseModel):
    """Resultado del procesamiento de un ítem individual del batch."""

    id_temporal_local: str
    estado: EstadoSincronizacion = Field(
        ..., description="SINCRONIZADO si se aplicó, CONFLICTO si quedó para revisión"
    )
    # id definitivo del recurso creado/modificado (si aplicó). Antes int.
    # En el Ciclo 2 es str: uuid del elemento embebido (ClaseUML.id,
    # AtributoUML.id…) o str(ObjectId) del documento creado, según
    # tipo_operacion.
    id_real: Optional[str] = Field(
        None,
        max_length=64,
        description="uuid del elemento embebido o str(id) del documento creado",
    )
    motivo_conflicto: Optional[str] = Field(None, max_length=255)


class BatchSincronizacionResponse(BaseModel):
    """Respuesta al cliente tras procesar el lote offline."""

    id_dispositivo: str
    id_diagrama: PydanticObjectId
    total_recibidos: int
    total_sincronizados: int
    total_conflictos: int
    resultados: list[ResultadoCambioSync] = Field(default_factory=list)


# ======================================================================
# DTOs específicos de operación — resolución de conflictos
# ======================================================================
class ConflictoSyncResponse(BaseModel):
    """
    Vista de un conflicto pendiente de resolución manual por el
    PROPIETARIO del proyecto (reutiliza versiones_diagrama como rama
    alternativa hasta que se resuelva).
    """

    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_dispositivo: str
    id_usuario: PydanticObjectId
    id_diagrama: Optional[PydanticObjectId] = None
    tipo_operacion: str
    payload: dict[str, Any]
    created_at: datetime


class ResolverConflictoRequest(BaseModel):
    """
    El PROPIETARIO decide qué versión conservar:
    - 'OFFLINE' → aplicar el cambio offline
    - 'SERVIDOR' → descartar el cambio offline y conservar el estado actual
    - 'FUSIONAR' → aplicar una fusión custom provista en `payload_fusionado`
    """

    estrategia: Literal["OFFLINE", "SERVIDOR", "FUSIONAR"]
    payload_fusionado: Optional[dict[str, Any]] = Field(
        None,
        description="Requerido solo si estrategia='FUSIONAR'",
    )