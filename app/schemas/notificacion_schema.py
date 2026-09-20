# app/schemas/notificacion_schema.py
"""
Esquemas Pydantic del módulo I. Notificaciones:

- Notificacion (persistencia)
- DTOs de operación para marcar como leídas y consultar el contador.
"""

from datetime import datetime
from typing import Literal, Optional

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
    id_referencia: Optional[int] = Field(
        None, gt=0,
        description="id del recurso relacionado (diagrama, comentario, trabajo…)",
    )


class NotificacionCreate(BaseModel):
    """
    El id_usuario (destinatario) lo determina el service según la lógica
    de negocio (ej. los miembros del proyecto). Este esquema lo usan los
    services internamente, no el cliente directamente.
    """

    id_usuario: int = Field(..., gt=0)
    tipo: TipoNotificacion
    mensaje: str = Field(..., min_length=1, max_length=255)
    id_referencia: Optional[int] = Field(None, gt=0)


class NotificacionResponse(NotificacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_usuario: int
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

    ids: list[int] = Field(default_factory=list)
    todas: bool = Field(default=False)


class ContadorNoLeidasResponse(BaseModel):
    """Contador liviano para el badge del dropdown de notificaciones."""

    total_no_leidas: int = Field(..., ge=0)