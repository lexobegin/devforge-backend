# app/models/colaboracion.py
"""
Documentos del módulo B. Proyectos y Colaboración (parte 2) — CICLO 2.

- SesionColaboracion → sesión activa de edición colaborativa en tiempo real
                       sobre un diagrama (colección "sesiones_colaboracion").
- ParticipanteSesion → usuario conectado dentro de una sesión, con su
                       posición/foco actual en el lienzo para verlo en vivo
                       (documento EMBEBIDO en SesionColaboracion.participantes).

Cambios respecto al Ciclo 1 (tablas PostgreSQL → documentos MongoDB):
- La tabla participantes_sesion desaparece como colección: cada participante
  va EMBEBIDO dentro de su sesión. El evento PRESENCIA del WebSocket
  actualiza el cursor sobre este mismo documento y una lectura de la sesión
  devuelve el estado completo de presencia sin joins.
- posicion_cursor conserva su formato libre (antes JSONB): el WebSocket del
  Ciclo 2 guarda x, y, zoom y el elemento enfocado sin migraciones.
- Las FK desaparecen: id_proyecto e id_diagrama son ObjectIds con índice
  (la nota de use_alter del Ciclo 1 ya no aplica: no hay orden de creación
  de tablas que romper).
- Las relationships (proyecto, diagrama, participantes) desaparecen: el
  diagrama se resuelve con Diagrama.get(self.id_diagrama).
"""

from datetime import datetime, timezone
from typing import Any, Optional

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field


# ======================================================================
# ParticipanteSesion (embebido)
# ======================================================================
class ParticipanteSesion(BaseModel):  # embebido: los embebidos de Beanie son pydantic
    """Participante de una sesión colaborativa (antes tabla
    participantes_sesion)."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla participantes_sesion)
    # ------------------------------------------------------------------
    id_usuario: PydanticObjectId

    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    left_at: Optional[datetime] = None

    # Posición/foco actual del usuario en el lienzo (x, y, zoom, elemento
    # activo…). Formato libre — antes columna JSONB.
    posicion_cursor: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def conectado(self) -> bool:
        """Sigue conectado mientras no tenga fecha de salida."""
        return self.left_at is None

    def __repr__(self) -> str:
        return (
            f"<ParticipanteSesion usuario={self.id_usuario} "
            f"conectado={self.conectado}>"
        )


# ======================================================================
# SesionColaboracion
# ======================================================================
class SesionColaboracion(Document):
    """Sesión de edición colaborativa (colección "sesiones_colaboracion")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla sesiones_colaboracion)
    # ------------------------------------------------------------------
    id_proyecto: PydanticObjectId

    id_diagrama: PydanticObjectId

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    ended_at: Optional[datetime] = None

    # Participantes EMBEBIDOS (antes tabla participantes_sesion)
    participantes: list[ParticipanteSesion] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "sesiones_colaboracion"  # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_proyecto", "id_diagrama"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def activa(self) -> bool:
        """Una sesión sigue activa mientras no tenga fecha de fin."""
        return self.ended_at is None

    def participante(
        self, id_usuario: PydanticObjectId
    ) -> Optional[ParticipanteSesion]:
        """Devuelve la participación del usuario en la sesión (o None),
        esté conectado o ya haya salido."""
        for participante in self.participantes:
            if participante.id_usuario == id_usuario:
                return participante
        return None

    @property
    def conectados(self) -> list[ParticipanteSesion]:
        """Participantes conectados ahora mismo (para el broadcast de
        PRESENCIA del WebSocket)."""
        return [p for p in self.participantes if p.conectado]

    def __repr__(self) -> str:
        return (
            f"<SesionColaboracion id={self.id} proyecto={self.id_proyecto} "
            f"diagrama={self.id_diagrama} activa={self.activa}>"
        )