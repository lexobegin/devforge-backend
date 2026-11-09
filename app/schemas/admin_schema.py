# app/schemas/admin_schema.py
"""
Esquemas Pydantic del módulo de ADMINISTRACIÓN de archivos (Tanda B24).

Punto 5 del reporte de pruebas del 2026-11-07: los artefactos que el
backend escribe en disco (XMI de intercambio en `exports/`, ZIPs y
carpetas de proyectos generados en `generated_projects/`, imágenes
subidas a `uploads/`) NO tenían ninguna vía de administración: se
acumulaban sin que el ADMIN pudiera verlos, descargarlos ni borrarlos.

Este módulo NO agrega almacenamiento nuevo: expone en solo-lectura
(listar) y con borrado explícito (eliminar) lo que ya existe en las
tres carpetas de settings. NUNCA se borra fuera de esas raíces (ver
_resolver_en_raiz de admin_router.py).

- `ruta` es RELATIVA a la raíz del tipo (posix, con "/") — igual que
  `ExportacionDiagrama.ruta_archivo` — para no acoplar a rutas absolutas
  del servidor.
- `modificado_at` es el mtime del archivo (datetime aware UTC).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Tipos de raíz administrable. La clave es la que viaja en la query
# (`tipo`) del frontend; el valor NO viaja (el router lo mapea a la
# carpeta real de settings).
TipoArchivoAdmin = Literal["exports", "generados", "uploads"]

TIPOS_VALIDOS = ("exports", "generados", "uploads")


class ArchivoAdminResponse(BaseModel):
    """Un archivo administrable (metadata, sin contenido)."""

    nombre: str = Field(..., description="Nombre del archivo (basename)")
    tipo: TipoArchivoAdmin = Field(
        ..., description="Raíz a la que pertenece: exports | generados | uploads"
    )
    ruta: str = Field(
        ...,
        description="Ruta relativa a la raíz del tipo (posix). Es la clave "
        "para descargar/eliminar",
    )
    tamano_bytes: int = Field(..., ge=0)
    modificado_at: datetime = Field(..., description="mtime del archivo (UTC)")


class ListadoArchivosAdminResponse(BaseModel):
    """Página del listado (mismo formato items/total que el resto)."""

    items: list[ArchivoAdminResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    skip: int = Field(0, ge=0)
    limit: int = Field(100, ge=1)
