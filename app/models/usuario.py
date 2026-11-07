# app/models/usuario.py
"""
Documento: usuarios (módulo A. Usuarios y Seguridad) — CICLO 2.

Representa a Ingenieros de Software, Líderes de Proyecto y Administradores
de la plataforma DevForge AI.

Cambios respecto al Ciclo 1 (tabla PostgreSQL → documento MongoDB):
- SQLAlchemy Base → beanie.Document; el nombre de la COLECCIÓN se conserva
  ("usuarios") para que la migración de datos sea directa.
- email sigue siendo único e indexado (Indexed(str, unique=True)); el índice
  lo crea init_beanie al arrancar (reemplaza al índice de la tabla SQL).
- Las relationships de SQLAlchemy desaparecen: en MongoDB no hay joins.
  - proyectos_propios: se consultan con Proyecto.find(Proyecto.id_propietario == self.id)
  - membresias: ahora viven EMBEBIDAS en cada proyecto (Proyecto.miembros),
    con el rol dentro de cada proyecto (MiembroProyecto).
"""

from datetime import datetime, timezone
from typing import Literal

from beanie import Document, Indexed
from pydantic import Field

RolGlobal = Literal["ADMIN", "LIDER", "DESARROLLADOR"]


class Usuario(Document):
    """Usuario de la plataforma (coleccion 'usuarios')."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla usuarios)
    # ------------------------------------------------------------------
    nombre_completo: str

    email: Indexed(str, unique=True)

    password_hash: str

    rol: RolGlobal = "DESARROLLADOR"

    activo: bool = True

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "usuarios"          # mismo nombre que la tabla del Ciclo 1

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def is_admin(self) -> bool:
        return self.rol == "ADMIN"

    def __repr__(self) -> str:
        return f"<Usuario id={self.id} email={self.email!r} rol={self.rol!r}>"