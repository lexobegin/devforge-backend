# app/models/generacion.py
"""
Documentos del módulo F. Generación Automática de Código — CICLO 2.

- TrabajoGeneracionCodigo → un proceso de generación automática a partir de
                            un diagrama (colección "trabajos_generacion_codigo").
- EntidadGenerada         → cada clase UML convertida en una entidad JPA/tabla
                            (EMBEDIDA en TrabajoGeneracionCodigo.entidades).
- ReglaMapeo              → regla de mapeo de un atributo UML hacia una columna
                            concreta de la tabla generada (EMBEDIDA en
                            EntidadGenerada.reglas_mapeo).

Cambios respecto al Ciclo 1 (tablas PostgreSQL → documentos MongoDB):
- entidades_generadas y reglas_mapeo desaparecen como tablas: van EMBEBIDAS
  en el trabajo (trabajo → entidades[] → reglas_mapeo[]). Leer el resultado
  completo de una generación cuesta 1 consulta (antes 3 con joins) y el
  resultado se elimina en cascada junto con el trabajo.
- id_clase_uml e id_atributo_uml pasan de FK INT a STR uuid: referencian los
  ids de los elementos EMBEBIDOS del Diagrama del Ciclo 2 (ClaseUML.id,
  AtributoUML.id).
- stack_destino sigue siendo texto libre: en el Ciclo 2 admite además el
  frontend React (CU24), p. ej. "REACT_TS_VITE", junto al clásico
  "SPRING_BOOT_JPA_POSTGRES".
- Los productos generados SIGUEN siendo relacionales (Spring Boot + JPA +
  PostgreSQL, GENERATED_BACKEND_* del config): lo único que cambia es dónde
  se guarda la bitácora del trabajo.
- Helpers esta_pendiente/esta_en_proceso/fue_exitoso/fallo se conservan.

Nota de orden: ReglaMapeo se define antes que EntidadGenerada (pydantic
resuelve las anotaciones en orden de declaración), igual que en diagrama.py.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

# Literal que reemplaza al CHECK ck_trabajo_generacion_estado del Ciclo 1
EstadoGeneracion = Literal["PENDIENTE", "EN_PROCESO", "EXITOSO", "FALLIDO"]


# ======================================================================
# ReglaMapeo (embebida)
# ======================================================================
class ReglaMapeo(BaseModel):  # embebido: los embebidos de Beanie son pydantic
    """Mapeo atributo UML → columna SQL (antes tabla reglas_mapeo)."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla reglas_mapeo)
    # ------------------------------------------------------------------
    # id uuid del AtributoUML embebido del diagrama (antes FK a atributos_uml).
    id_atributo_uml: str

    # Nombre de la columna resultante (ej. "nombre_completo", "fecha_nacimiento").
    nombre_columna: str

    # Tipo SQL resultante del mapeo (VARCHAR(150), INTEGER, DATE, BOOLEAN…).
    tipo_sql: str

    es_clave_primaria: bool = False

    es_nulleable: bool = True

    def __repr__(self) -> str:
        return (
            f"<ReglaMapeo id={self.id_atributo_uml[:8]}… "
            f"columna={self.nombre_columna!r} tipo_sql={self.tipo_sql!r}>"
        )


# ======================================================================
# EntidadGenerada (embebida)
# ======================================================================
class EntidadGenerada(BaseModel):  # embebido: los embebidos de Beanie son pydantic
    """Entidad JPA generada a partir de una clase UML (antes tabla
    entidades_generadas)."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla entidades_generadas)
    # ------------------------------------------------------------------
    # id uuid del ClaseUML embebido del diagrama (antes FK a clases_uml).
    id_clase_uml: str

    # Nombre de la clase @Entity generada (ej. "Paciente", "HistoriaClinica").
    nombre_clase_java: str

    # Tabla Postgres resultante (ej. "paciente", "historia_clinica").
    nombre_tabla: str

    # Reglas EMBEBIDAS (antes tabla reglas_mapeo)
    reglas_mapeo: list[ReglaMapeo] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def regla_de_atributo(self, id_atributo_uml: str) -> Optional[ReglaMapeo]:
        """Devuelve la regla de mapeo de un atributo UML (o None)."""
        for regla in self.reglas_mapeo:
            if regla.id_atributo_uml == id_atributo_uml:
                return regla
        return None

    def __repr__(self) -> str:
        return (
            f"<EntidadGenerada java={self.nombre_clase_java!r} "
            f"tabla={self.nombre_tabla!r}>"
        )


# ======================================================================
# TrabajoGeneracionCodigo
# ======================================================================
class TrabajoGeneracionCodigo(Document):
    """Trabajo de generación de código (colección
    "trabajos_generacion_codigo")."""

    # ------------------------------------------------------------------
    # Campos (antes columnas de la tabla trabajos_generacion_codigo)
    # ------------------------------------------------------------------
    id_diagrama: PydanticObjectId

    id_usuario: PydanticObjectId

    stack_destino: str = "SPRING_BOOT_JPA_POSTGRES"

    estado: EstadoGeneracion = "PENDIENTE"

    # Carpeta/zip donde queda el backend generado (relativo a
    # GENERATED_PROJECTS_DIR).
    ruta_salida: Optional[str] = None

    started_at: Optional[datetime] = None

    finished_at: Optional[datetime] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Resultado EMBEBIDO (antes tablas entidades_generadas y reglas_mapeo)
    # ------------------------------------------------------------------
    entidades: list[EntidadGenerada] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Configuración del documento
    # ------------------------------------------------------------------
    class Settings:
        name = "trabajos_generacion_codigo"  # mismo nombre que la tabla
        indexes = ["id_diagrama", "id_usuario"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def esta_pendiente(self) -> bool:
        return self.estado == "PENDIENTE"

    @property
    def esta_en_proceso(self) -> bool:
        return self.estado == "EN_PROCESO"

    @property
    def fue_exitoso(self) -> bool:
        return self.estado == "EXITOSO"

    @property
    def fallo(self) -> bool:
        return self.estado == "FALLIDO"

    def entidad_de_clase(self, id_clase_uml: str) -> Optional[EntidadGenerada]:
        """Devuelve la entidad generada para una clase UML (o None).

        La usa el generador (CU6/CU24) para actualizar/consultar el
        resultado por clase sin recorrer la lista a mano.
        """
        for entidad in self.entidades:
            if entidad.id_clase_uml == id_clase_uml:
                return entidad
        return None

    def __repr__(self) -> str:
        return (
            f"<TrabajoGeneracionCodigo id={self.id} "
            f"diagrama={self.id_diagrama} estado={self.estado!r}>"
        )