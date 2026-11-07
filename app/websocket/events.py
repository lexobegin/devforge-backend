# app/websocket/events.py
"""
Definición de eventos del canal WebSocket de colaboración — CICLO 2.

Estructura de cada mensaje (JSON):
{
    "type": "<event_type>",
    "payload": {...},
    "timestamp": "2025-01-15T10:30:00Z",   # opcional, lo agrega el servidor
    "sender": {"id": "684f2c9a...", "nombre": "..."}   # opcional, lo agrega el servidor
}

Tipos de eventos soportados:
- Conexión:    join, leave
- Presencia:   cursor_moved, selection_changed
- Cambios:     class_created, class_updated, class_deleted,
               attribute_created, attribute_updated, attribute_deleted,
               operation_created, operation_updated, operation_deleted,
               relation_created, relation_updated, relation_deleted,
               interface_created, interface_updated, interface_deleted
- Sincronía:   diagram_updated, request_sync, sync_snapshot
- Sistema:     error, ping, pong

Migrado al Ciclo 2 (Beanie/MongoDB):
- TODOS los ids del canal son STR: ObjectId en hex para usuario /
  diagrama / sesión, y uuid hex para los elementos EMBEBIDOS del
  Diagrama (clases, atributos, ...). El contrato de eventos (nombres de
  eventos y forma del payload) se conserva del Ciclo 1: solo cambia el
  tipo de los ids.
- UserRef.id pasa de int a str (ObjectId en hex).
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ======================================================================
# Tipos de evento
# ======================================================================
EventType = Literal[
    # Conexión / presencia
    "join",
    "leave",
    "cursor_moved",
    "selection_changed",
    # Cambios sobre el diagrama (nivel clase)
    "class_created",
    "class_updated",
    "class_deleted",
    # Cambios sobre atributos
    "attribute_created",
    "attribute_updated",
    "attribute_deleted",
    # Cambios sobre operaciones
    "operation_created",
    "operation_updated",
    "operation_deleted",
    # Cambios sobre relaciones
    "relation_created",
    "relation_updated",
    "relation_deleted",
    # Cambios sobre interfaces
    "interface_created",
    "interface_updated",
    "interface_deleted",
    # Sincronía
    "diagram_updated",
    "request_sync",
    "sync_snapshot",
    # Sistema
    "error",
    "ping",
    "pong",
    # Notificaciones de IA
    "ai_action_applied",
]


# ======================================================================
# Payloads
# ======================================================================
class UserRef(BaseModel):
    """Referencia mínima al usuario para no enviar todo el objeto."""

    # Ciclo 1: id int. Ciclo 2: ObjectId en hex (str).
    id: str
    nombre: str


class WSMessage(BaseModel):
    """
    Mensaje genérico del WebSocket.
    `payload` es libre: cada tipo de evento lo interpreta.
    """

    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None
    sender: Optional[UserRef] = None


# ======================================================================
# Helpers de construcción
# ======================================================================
def build_message(
    event_type: EventType,
    payload: Optional[dict[str, Any]] = None,
    *,
    sender: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Construye el dict listo para `json.dumps()` con timestamp del servidor.
    Si se pasa `sender` (con claves `id` y `nombre`), lo adjunta.
    """
    msg: dict[str, Any] = {
        "type": event_type,
        "payload": payload or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if sender is not None:
        msg["sender"] = {
            "id": sender.get("id"),
            "nombre": sender.get("nombre", ""),
        }
    return msg


def build_error(code: str, mensaje: str) -> dict[str, Any]:
    """Construye un mensaje de error estándar del WS."""
    return build_message("error", {"code": code, "mensaje": mensaje})


def parse_message(raw: str) -> Optional[WSMessage]:
    """
    Parsea un mensaje recibido del cliente.
    Devuelve None si el JSON es inválido o el `type` no es reconocido.
    """
    import json

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict) or "type" not in data:
        return None

    try:
        return WSMessage.model_validate(data)
    except Exception:
        return None


# ======================================================================
# Tipos de cambio válidos (para validación y auditoría)
# ======================================================================
TIPOS_DE_CAMBIO: set[str] = {
    "class_created",
    "class_updated",
    "class_deleted",
    "attribute_created",
    "attribute_updated",
    "attribute_deleted",
    "operation_created",
    "operation_updated",
    "operation_deleted",
    "relation_created",
    "relation_updated",
    "relation_deleted",
    "interface_created",
    "interface_updated",
    "interface_deleted",
}


# Mapeo: evento WS → tipo_entidad para historial_cambios_diagrama.
# (Ciclo 2: id_entidad es el uuid str del elemento EMBEBIDO del Diagrama;
# los literales coinciden con el campo tipo_entidad: str de la Tanda 4.)
EVENTO_A_ENTIDAD: dict[str, str] = {
    "class_created": "CLASE",
    "class_updated": "CLASE",
    "class_deleted": "CLASE",
    "attribute_created": "ATRIBUTO",
    "attribute_updated": "ATRIBUTO",
    "attribute_deleted": "ATRIBUTO",
    "operation_created": "OPERACION",
    "operation_updated": "OPERACION",
    "operation_deleted": "OPERACION",
    "relation_created": "RELACION",
    "relation_updated": "RELACION",
    "relation_deleted": "RELACION",
    "interface_created": "INTERFAZ",
    "interface_updated": "INTERFAZ",
    "interface_deleted": "INTERFAZ",
}


# Mapeo: evento WS → tipo_cambio para historial_cambios_diagrama.
# (Los valores coinciden con TipoCambio = Literal["CREAR","MODIFICAR",
# "ELIMINAR"] del modelo trazabilidad de la Tanda 4.)
EVENTO_A_CAMBIO: dict[str, str] = {
    "class_created": "CREAR",
    "class_updated": "MODIFICAR",
    "class_deleted": "ELIMINAR",
    "attribute_created": "CREAR",
    "attribute_updated": "MODIFICAR",
    "attribute_deleted": "ELIMINAR",
    "operation_created": "CREAR",
    "operation_updated": "MODIFICAR",
    "operation_deleted": "ELIMINAR",
    "relation_created": "CREAR",
    "relation_updated": "MODIFICAR",
    "relation_deleted": "ELIMINAR",
    "interface_created": "CREAR",
    "interface_updated": "MODIFICAR",
    "interface_deleted": "ELIMINAR",
}