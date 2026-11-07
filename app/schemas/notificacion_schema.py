# app/schemas/notificacion_schema.py
"""
Esquemas Pydantic del módulo I. Notificaciones:

- Notificacion (persistencia)
- DTOs de operación para marcar como leídas y consultar el contador.

Cambios respecto al Ciclo 1:
- id_usuario e id (int serial) → PydanticObjectId de Beanie (string hex en
  JSON).
- id_referencia (BIGINT polimórfico sin FK) → Optional[str]: guarda el
  str(id) de un Document (diagrama, comentario, trabajo de generación…) o el
  id uuid de un elemento embebido, según `tipo`. Se resuelve en el service.
- TipoNotificacion se mantiene como Literal con los 8 tipos del Ciclo 1
  (el modelo lo deja como texto libre para no romper los avisos históricos,
  pero la entrada del cliente/servicios se valida aquí).
- MarcarNotificacionesLeidasRequest.ids → list[PydanticObjectId].
"""

from datetime import datetime
from typing import Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


# ======================================================================
# Tipos reutilizables
# ======================================================================
TipoNotificacion = Literal[
    "COMENTARIO",
    "CAMBIO_DIAGRAMA",
    "GENERACION_COMPLETA",
    "GENERACION_FALLIDA",
    "MIEMBRO_AGREGADO",
    "CONFLICTO_PENDIENTE",
    "VERSION_GUARDADA",
    "SISTEMA",
]


# ======================================================================
# Notificacion
# ======================================================================
class NotificacionBase(BaseModel):
    tipo: TipoNotificacion
    mensaje: str = Field(..., min_length=1, max_length=255)
    # Polimórfica según `tipo`: str(id) de un Document o uuid de un elemento
    # embebido. Antes BIGINT; ahora string.
    id_referencia: Optional[str] = Field(
        None,
        max_length=64,
        description="id del recurso relacionado (diagrama, comentario, trabajo…)",
    )


class NotificacionCreate(BaseModel):
    """
    El id_usuario (destinatario) lo determina el service según la lógica
    de negocio (ej. los miembros del proyecto). Este esquema lo usan los
    services internamente, no el cliente directamente.
    """

    id_usuario: PydanticObjectId
    tipo: TipoNotificacion
    mensaje: str = Field(..., min_length=1, max_length=255)
    id_referencia: Optional[str] = Field(None, max_length=64)


class NotificacionResponse(NotificacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    id_usuario: PydanticObjectId
    leida: bool
    created_at: datetime


# ======================================================================
# DTOs específicos de operación
# ======================================================================
class MarcarNotificacionesLeidasRequest(BaseModel):
    """
    Marca como leídas varias notificaciones a la vez.
    Si `ids` viene vacío y `todas=True`, marca todas las del usuario.
    """

    ids: list[PydanticObjectId] = Field(default_factory=list)
    todas: bool = Field(default=False)


class ContadorNoLeidasResponse(BaseModel):
    """Contador liviano para el badge del dropdown de notificaciones."""

    total_no_leidas: int = Field(..., ge=0)