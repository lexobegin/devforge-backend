# app/models/proyecto.py
"""
Documentos del módulo B. Proyectos y Colaboración (parte 1) — CICLO 2.

- Proyecto        → proyectos de software que un equipo modela/genera
                    (colección "proyectos").
- MiembroProyecto → usuario que pertenece a un proyecto y su rol
                    (documento EMBEBIDO dentro de Proyecto.miembros).

Cambios respecto al Ciclo 1 (tablas PostgreSQL → documentos MongoDB):
- La tabla miembros_proyecto desaparece como colección: cada miembro va
  EMBEBIDO dentro de su proyecto (Proyecto.miembros) como modelo pydantic
  (en Beanie los documentos embebidos son BaseModel). Leer el proyecto
  devuelve sus miembros sin joins.
- La unicidad (id_proyecto, id_usuario) del Ciclo 1
  (uq_miembro_proyecto_usuario) se garantiza en la capa de servicios
  consultando Proyecto.miembro(id_usuario) antes de insertar.
- id_propietario guarda el ObjectId del usuario propietario (antes FK a
  usuarios.id); el índice se declara en Settings.indexes.
- Las relationships de SQLAlchemy (propietario, miembros) desaparecen: el
  propietario se resuelve con Usuario.get(self.id_propietario).
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

# Literales que reemplazan a los CHECK del Ciclo 1
RolEnProyecto = Literal["PROPIETARIO", "EDITOR", "LECTOR"]
EstadoProyecto = Literal["ACTIVO", "ARCHIVADO"]


# ======================================================================
# MiembroProyecto (embebido)
# ======================================================================
class MiembroProyecto(BaseModel):  # embebido: los embebidos de Beanie son pydantic
    """Miembro de un proyecto (antes tabla miembros_proyecto)."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla miembros_proyecto)
    # ------------------------------------------------------------------
    id_usuario: PydanticObjectId

    rol_en_proyecto: RolEnProyecto = "EDITOR"

    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def es_propietario(self) -> bool:
        return self.rol_en_proyecto == "PROPIETARIO"

    def __repr__(self) -> str:
        return (
            f"<MiembroProyecto usuario={self.id_usuario} "
            f"rol={self.rol_en_proyecto!r}>"
        )


# ======================================================================
# Proyecto
# ======================================================================
class Proyecto(Document):
    """Proyecto de software (colección "proyectos")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla proyectos)
    # ------------------------------------------------------------------
    nombre: str

    descripcion: Optional[str] = None

    id_propietario: PydanticObjectId

    estado: EstadoProyecto = "ACTIVO"

    # Miembros EMBEBIDOS (antes tabla miembros_proyecto)
    miembros: list[MiembroProyecto] = Field(default_factory=list)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "proyectos"
        indexes = ["id_propietario"]   # índice que tenía la FK en PostgreSQL

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def esta_activo(self) -> bool:
        return self.estado == "ACTIVO"

    def miembro(
        self, id_usuario: PydanticObjectId
    ) -> Optional[MiembroProyecto]:
        """Devuelve la membresía del usuario en el proyecto (o None).

        Es la puerta de entrada al control de permisos: los routers y
        servicios consultan aquí antes de permitir editar, generar o
        administrar (verifica también la unicidad uq_miembro del Ciclo 1).
        """
        for miembro in self.miembros:
            if miembro.id_usuario == id_usuario:
                return miembro
        return None

    def __repr__(self) -> str:
        return (
            f"<Proyecto id={self.id} nombre={self.nombre!r} "
            f"estado={self.estado!r}>"
        )