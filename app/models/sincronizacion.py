# app/models/sincronizacion.py
"""
Documentos del módulo H. Sincronización Móvil/Web Offline — CICLO 2.

- ColaSincronizacionMovil → cola de cambios hechos sin conexión (móvil o
                            web), pendientes de sincronizar cuando se
                            recupera la red — colección
                            "cola_sincronizacion_movil".

Alineado 1:1 con el script SQL (módulo H).

Nota: aunque la colección se llame "cola_sincronizacion_movil" (nombre
original del script), la usan tanto la app móvil Flutter como el frontend
web offline. El campo `id_dispositivo` es genérico: puede ser un deviceId
móvil o un id de navegador persistido en IndexedDB.

Cambios respecto al Ciclo 1 (tabla PostgreSQL → documento MongoDB):
- id_dispositivo sigue siendo texto libre: lo genera el cliente, no es FK.
- Las FKs id_usuario e id_diagrama (INT) → PydanticObjectId con índice;
  id_diagrama sigue siendo OPCIONAL (hay cambios offline no atados a un
  diagrama concreto).
- payload conserva su formato libre (antes JSONB): cada tipo_operacion
  define su propia estructura y el ejecutor del servidor la valida al
  sincronizar.
- CHECK ck_cola_sync_estado → Literal[EstadoSincronizacion].
- Las relationships (usuario, diagrama) desaparecen: se resuelven con
  Usuario.get(self.id_usuario) / Diagrama.get(self.id_diagrama).
- Conexión con el módulo G: el ejecutor de acciones de la IA reutiliza el
  mismo vocabulario de tipo_operacion ('CREAR_CLASE', 'MODIFICAR_ATRIBUTO',
  'ELIMINAR_RELACION'…): un cambio puede nacer offline, del WebSocket o del
  Agente Dev y procesarse por el mismo ejecutor.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from beanie import Document, PydanticObjectId
from pydantic import Field

# Literal que reemplaza al CHECK ck_cola_sync_estado del Ciclo 1
EstadoSincronizacion = Literal["PENDIENTE", "SINCRONIZADO", "CONFLICTO"]


# ======================================================================
# ColaSincronizacionMovil
# ======================================================================
class ColaSincronizacionMovil(Document):
    """Cambio hecho offline pendiente de sincronizar (colección
    "cola_sincronizacion_movil")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla cola_sincronizacion_movil)
    # ------------------------------------------------------------------
    # Identificador del dispositivo/navegador que originó el cambio offline.
    id_dispositivo: str

    id_usuario: PydanticObjectId

    # None si el cambio no está atado a un diagrama concreto.
    id_diagrama: Optional[PydanticObjectId] = None

    # id generado offline por el dispositivo (se resuelve al sincronizar).
    id_temporal_local: Optional[str] = None

    # 'CREAR_CLASE', 'MODIFICAR_ATRIBUTO', 'ELIMINAR_RELACION', etc.
    tipo_operacion: str

    # Datos del cambio realizado offline (estructura libre por tipo_operacion).
    payload: dict[str, Any]

    estado: EstadoSincronizacion = "PENDIENTE"

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    synced_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "cola_sincronizacion_movil"  # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_dispositivo", "id_usuario", "id_diagrama"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def esta_pendiente(self) -> bool:
        return self.estado == "PENDIENTE"

    @property
    def tiene_conflicto(self) -> bool:
        return self.estado == "CONFLICTO"

    def __repr__(self) -> str:
        return (
            f"<ColaSincronizacionMovil id={self.id} dispositivo={self.id_dispositivo!r} "
            f"op={self.tipo_operacion!r} estado={self.estado!r}>"
        )