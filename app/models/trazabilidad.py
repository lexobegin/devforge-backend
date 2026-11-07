# app/models/trazabilidad.py
"""
Documentos del módulo D. Trazabilidad y Colaboración en Tiempo Real — CICLO 2.

- HistorialCambioDiagrama → registro de cada cambio hecho sobre un diagrama
                            (para deshacer y resolver conflictos entre varios
                            usuarios editando a la vez) — colección
                            "historial_cambios_diagrama".
- VersionDiagrama         → snapshot completo del diagrama al guardar una
                            versión — colección "versiones_diagrama".
- ComentarioDiagrama      → comentarios/anotaciones que los colaboradores
                            dejan sobre un elemento del diagrama — colección
                            "comentarios_diagrama".

Cambios respecto al Ciclo 1 (tablas PostgreSQL → documentos MongoDB):
- Las 3 tablas se conservan como COLECCIONES SEPARADAS (a diferencia de
  clases/atributos/relaciones, que van embebidas): son listas abiertas que
  crecen con cada cambio/versión/comentario, y embeberlas haría crecer el
  documento del diagrama sin límite.
- id_entidad pasa de INT (id de tabla hija) a STR uuid: referencia el id de
  los elementos EMBEBIDOS del Diagrama del Ciclo 2 (ClaseUML.id,
  AtributoUML.id, OperacionUML.id, RelacionUML.id…).
- datos_cambio y contenido_json conservan su formato libre (antes JSONB).
- contenido_json es ahora el volcado del documento Diagrama completo
  (Diagrama.model_dump()), que ya incluye clases, interfaces y relaciones
  embebidas: restaurar una versión = reemplazar el contenido del diagrama.
- La unicidad (id_diagrama, numero_version) del Ciclo 1
  (uq_version_diagrama_numero) se conserva como índice único compuesto.
- Las relationships desaparecen; id_diagrama/id_usuario son ObjectIds con
  índice.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from beanie import Document, PydanticObjectId
from pymongo import ASCENDING, IndexModel
from pydantic import Field

# Literal que reemplaza al CHECK ck_historial_tipo_cambio del Ciclo 1
TipoCambio = Literal["CREAR", "MODIFICAR", "ELIMINAR"]


# ======================================================================
# HistorialCambioDiagrama
# ======================================================================
class HistorialCambioDiagrama(Document):
    """Cambio sobre un diagrama (colección "historial_cambios_diagrama")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla historial_cambios_diagrama)
    # ------------------------------------------------------------------
    id_diagrama: PydanticObjectId

    id_usuario: PydanticObjectId

    tipo_cambio: TipoCambio

    # 'CLASE', 'ATRIBUTO', 'RELACION', etc.
    tipo_entidad: str

    # id uuid del elemento embebido afectado (ClaseUML.id, AtributoUML.id,
    # RelacionUML.id…). En el Ciclo 1 era el id INT de la tabla hija.
    id_entidad: str

    # Snapshot del cambio (antes/después). Libre para evolucionar por tipo
    # de entidad.
    datos_cambio: dict[str, Any]

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "historial_cambios_diagrama"  # mismo nombre que la tabla
        indexes = ["id_diagrama", "id_usuario"]

    def __repr__(self) -> str:
        return (
            f"<HistorialCambioDiagrama id={self.id} "
            f"diagrama={self.id_diagrama} "
            f"{self.tipo_cambio} {self.tipo_entidad}#{self.id_entidad}>"
        )


# ======================================================================
# VersionDiagrama
# ======================================================================
class VersionDiagrama(Document):
    """Snapshot/version de un diagrama (colección "versiones_diagrama")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla versiones_diagrama)
    # ------------------------------------------------------------------
    id_diagrama: PydanticObjectId

    numero_version: int

    # Copia completa del diagrama en ese momento (clases, interfaces,
    # relaciones…): Diagrama.model_dump() del documento embebido del Ciclo 2.
    contenido_json: dict[str, Any]

    id_usuario: PydanticObjectId

    comentario: Optional[str] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "versiones_diagrama"   # mismo nombre que la tabla del Ciclo 1
        # uq_version_diagrama_numero del Ciclo 1 → índice único compuesto
        indexes = [
            IndexModel(
                [("id_diagrama", ASCENDING), ("numero_version", ASCENDING)],
                unique=True,
                name="uq_version_diagrama_numero",
            ),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def restaurar_en(self, diagrama) -> None:
        """Reemplaza el contenido del diagrama con este snapshot y guarda.

        La usan deshacer/restore del historial (módulo D): como el contenido
        embebido del Ciclo 2 vive dentro del Diagrama, restaurar es
        reemplazar clases/interfaces/relaciones y persistir 1 documento.
        """
        # Import diferido: evita acoplar trazabilidad ↔ diagrama a nivel de
        # módulo (diagrama.py no conoce a trazabilidad; aquí solo se usa al
        # momento de restaurar).
        from app.models.diagrama import ClaseUML, InterfazUML, RelacionUML

        diagrama.clases = [
            ClaseUML(**c) for c in self.contenido_json.get("clases", [])
        ]
        diagrama.interfaces = [
            InterfazUML(**i) for i in self.contenido_json.get("interfaces", [])
        ]
        diagrama.relaciones = [
            RelacionUML(**r) for r in self.contenido_json.get("relaciones", [])
        ]
        await diagrama.save()

    def __repr__(self) -> str:
        return (
            f"<VersionDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"v={self.numero_version}>"
        )


# ======================================================================
# ComentarioDiagrama
# ======================================================================
class ComentarioDiagrama(Document):
    """Comentario sobre un diagrama (colección "comentarios_diagrama")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla comentarios_diagrama)
    # ------------------------------------------------------------------
    id_diagrama: PydanticObjectId

    id_usuario: PydanticObjectId

    # Sobre qué elemento comenta: 'CLASE', 'RELACION'… None si es general
    # al diagrama.
    tipo_entidad: Optional[str] = None

    # id uuid del elemento comentado (None si es general al diagrama).
    id_entidad: Optional[str] = None

    texto: str

    resuelto: bool = False

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "comentarios_diagrama"  # mismo nombre que la tabla del Ciclo 1
        indexes = ["id_diagrama", "id_usuario"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def es_general(self) -> bool:
        """True si el comentario no apunta a un elemento concreto."""
        return self.id_entidad is None

    def __repr__(self) -> str:
        return (
            f"<ComentarioDiagrama id={self.id} diagrama={self.id_diagrama} "
            f"resuelto={self.resuelto}>"
        )