# app/schemas/sincronizacion_schema.py
"""
Esquemas Pydantic del módulo H. Sincronización Móvil/Web Offline:

- ColaSincronizacionMovil (persistencia)
- DTOs de operación para el envío de lotes (batches) desde el cliente
  offline y la resolución de conflictos.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables
# ======================================================================
EstadoColaSync = Literal["PENDIENTE", "SINCRONIZADO", "CONFLICTO"]


# ======================================================================
# ColaSincronizacionMovil
# ======================================================================
class ColaSincronizacionMovilBase(BaseModel):
    id_dispositivo: str = Field(
        ..., min_length=1, max_length=100,
        description="deviceId móvil o id de navegador persistido",
    )
    id_diagrama: Optional[int] = Field(None, gt=0)
    id_temporal_local: Optional[str] = Field(None, max_length=100)
    tipo_operacion: str = Field(
        ..., min_length=1, max_length=20,
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

    id: int
    id_usuario: int
    estado: EstadoColaSync
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
    tipo_operacion: str = Field(..., min_length=1, max_length=20)
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
    id_diagrama: int = Field(..., gt=0)
    cambios: list[CambioOfflineItem] = Field(..., min_length=1)


class ResultadoCambioSync(BaseModel):
    """Resultado del procesamiento de un ítem individual del batch."""

    id_temporal_local: str
    estado: EstadoColaSync = Field(
        ..., description="SINCRONIZADO si se aplicó, CONFLICTO si quedó para revisión"
    )
    id_real: Optional[int] = Field(
        None, description="id definitivo del recurso creado/modificado (si aplicó)"
    )
    motivo_conflicto: Optional[str] = Field(None, max_length=255)


class BatchSincronizacionResponse(BaseModel):
    """Respuesta al cliente tras procesar el lote offline."""

    id_dispositivo: str
    id_diagrama: int
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

    id: int
    id_dispositivo: str
    id_usuario: int
    id_diagrama: Optional[int] = None
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