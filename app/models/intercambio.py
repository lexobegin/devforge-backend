# app/models/intercambio.py
"""
Documentos del módulo E. Intercambio de Modelos (XMI/XML) — CICLO 2.

- ExportacionDiagrama → registro de una exportación del diagrama a un archivo
                        externo (colección "exportaciones_diagrama").
- ImportacionDiagrama → registro de una importación de un modelo externo
                        hacia la plataforma (colección "importaciones_diagrama").

Cambios respecto al Ciclo 1 (tablas PostgreSQL → documentos MongoDB):
- Ambas tablas se conservan como COLECCIONES SEPARADAS: son bitácoras de
  intercambio que crecen linealmente con el uso (embeberlas haría crecer el
  diagrama sin límite).
- Los ids pasan de FK INT a ObjectIds con índice (id_diagrama, id_usuario).
- En el Ciclo 2 estos registros documentan el round-trip DevForge ↔
  Enterprise Architect: el conversor XMI (lxml) los llena al terminar cada
  operación, con estado EXITOSO/FALLIDO — trazabilidad que el Ciclo 1 no
  daba para depurar la compatibilidad con EA.
"""

from datetime import datetime, timezone
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import Field

# Literal que reemplaza al CHECK ck_importacion_estado del Ciclo 1
EstadoImportacion = Literal["PENDIENTE", "EXITOSO", "FALLIDO"]


# ======================================================================
# ExportacionDiagrama
# ======================================================================
class ExportacionDiagrama(Document):
    """Exportación de un diagrama (colección "exportaciones_diagrama")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla exportaciones_diagrama)
    # ------------------------------------------------------------------
    id_diagrama: PydanticObjectId

    formato: str = "XMI"

    ruta_archivo: str

    id_usuario: PydanticObjectId

    exported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "exportaciones_diagrama"  # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_diagrama"]

    def __repr__(self) -> str:
        return (
            f"<ExportacionDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"formato={self.formato!r}>"
        )


# ======================================================================
# ImportacionDiagrama
# ======================================================================
class ImportacionDiagrama(Document):
    """Importación de un modelo externo (colección "importaciones_diagrama")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla importaciones_diagrama)
    # ------------------------------------------------------------------
    id_diagrama: PydanticObjectId

    formato: str = "XMI"

    archivo_origen: str

    estado: EstadoImportacion = "PENDIENTE"

    id_usuario: PydanticObjectId

    imported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "importaciones_diagrama"  # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_diagrama"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def exitoso(self) -> bool:
        return self.estado == "EXITOSO"

    @property
    def fallo(self) -> bool:
        return self.estado == "FALLIDO"

    def __repr__(self) -> str:
        return (
            f"<ImportacionDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"estado={self.estado!r}>"
        )