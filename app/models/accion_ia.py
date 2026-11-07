# app/models/accion_ia.py
"""
Documento: acciones_ia (módulo G. IA del Ciclo 2, parte 3) — CICLO 2.

Acción estructurada que el Agente Dev (CU16-CU21) propone sobre el diagrama
y que el ejecutor del backend aplica (o el usuario rechaza) — colección
"acciones_ia".

NUEVO en el Ciclo 2: esta colección NO existe en el script SQL del Ciclo 1
(sustituye a la parte de "acción" de la tabla interacciones_ia).

Clave para el correcto funcionamiento del agente (deficiencias 1 y 2 del
Ciclo 1: reconocimiento visual y chat/voz que solo dibujaban "cajas vacías"):
- El LLM NO toca el lienzo directamente: responde con acciones
  estructuradas (tipo_accion + payload) que el backend valida y aplica
  sobre los elementos EMBEBIDOS del Diagrama. Así la IA crea clases con
  atributos, operaciones y relaciones REALES, no solo cajas.
- tipo_accion usa el MISMO vocabulario de tipo_operacion de la cola de
  sincronización offline (módulo H): 'CREAR_CLASE', 'MODIFICAR_ATRIBUTO',
  'ELIMINAR_RELACION', 'GENERAR_CODIGO'… Un solo vocabulario para que un
  cambio pueda nacer del chat, de la voz, del WebSocket o de un dispositivo
  offline y procesarse igual.
- Los ids dentro del payload referencian los ids uuid de los elementos
  embebidos del Diagrama (ClaseUML.id, AtributoUML.id, RelacionUML.id).

Decisiones de diseño (Colección nueva, sin CHECK en el SQL origen):
- estado sigue el ciclo de vida de la acción: PROPUESTA → APLICADA /
  RECHAZADA / FALLIDA (Literal en lugar de CHECK).
- detalle_resultado guarda el porqué de un rechazo/fallo o el id de la
  entidad creada, para mostrarlo en el chat.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from beanie import Document, PydanticObjectId
from pydantic import Field

# Literal que reemplaza al CHECK (colección nueva del Ciclo 2)
EstadoAccionIA = Literal["PROPUESTA", "APLICADA", "RECHAZADA", "FALLIDA"]


# ======================================================================
# AccionIA
# ======================================================================
class AccionIA(Document):
    """Acción del Agente Dev sobre un diagrama (colección "acciones_ia")."""

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    id_usuario: PydanticObjectId

    # None si la acción no está atada a un diagrama (p. ej. GENERAR_CODIGO
    # a nivel de proyecto).
    id_diagrama: Optional[PydanticObjectId] = None

    # Mensaje del chat (MensajeChat) que originó la acción; None si el
    # disparo fue otra vía (boceto, botón de generación…).
    id_mensaje: Optional[PydanticObjectId] = None

    # 'CREAR_CLASE', 'MODIFICAR_ATRIBUTO', 'ELIMINAR_RELACION',
    # 'GENERAR_CODIGO', etc. (mismo vocabulario que la cola offline).
    tipo_accion: str

    # Datos del cambio (estructura libre por tipo_accion): ids uuid de los
    # elementos embebidos afectados, nuevos valores, posiciones en el
    # lienzo…
    payload: dict[str, Any]

    estado: EstadoAccionIA = "PROPUESTA"

    # Detalle del resultado: error de validación UML, id de la clase
    # creada, motivo del rechazo por el usuario…
    detalle_resultado: Optional[str] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    aplicada_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "acciones_ia"  # colección nueva del Ciclo 2 (antes no existía)
        indexes = ["id_usuario", "id_diagrama"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def esta_pendiente(self) -> bool:
        """Propuesta que aún espera ser aplicada o rechazada."""
        return self.estado == "PROPUESTA"

    def marcar_aplicada(self) -> None:
        """Marca la acción como aplicada en el diagrama (uso desde
        services, tras validar y persistir el cambio)."""
        self.estado = "APLICADA"
        self.aplicada_at = datetime.now(timezone.utc)

    def marcar_rechazada(self, detalle: Optional[str] = None) -> None:
        """El usuario (o el validador) rechazó la acción propuesta."""
        self.estado = "RECHAZADA"
        self.detalle_resultado = detalle

    def marcar_fallida(self, detalle: Optional[str] = None) -> None:
        """La aplicación falló (p. ej. validación UML 2.5.1 incorrecta)."""
        self.estado = "FALLIDA"
        self.detalle_resultado = detalle

    def __repr__(self) -> str:
        return (
            f"<AccionIA id={self.id} tipo={self.tipo_accion!r} "
            f"estado={self.estado!r}>"
        )