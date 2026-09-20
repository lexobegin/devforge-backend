# app/models/generacion.py
"""
Modelos ORM del módulo F. Generación Automática de Backend (Spring Boot):

- TrabajoGeneracionCodigo → un proceso de generación automática de backend
                            a partir de un diagrama.
- EntidadGenerada         → cada clase UML convertida en una entidad JPA/tabla
                            dentro de un trabajo de generación.
- ReglaMapeo              → regla de mapeo de un atributo UML hacia una columna
                            concreta de la tabla generada.

Alineado 1:1 con el script SQL (módulo F).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ======================================================================
# TrabajoGeneracionCodigo
# ======================================================================
class TrabajoGeneracionCodigo(Base):
    __tablename__ = "trabajos_generacion_codigo"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('PENDIENTE','EN_PROCESO','EXITOSO','FALLIDO')",
            name="ck_trabajo_generacion_estado",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_diagrama: Mapped[int] = mapped_column(
        ForeignKey("diagramas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    stack_destino: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="SPRING_BOOT_JPA_POSTGRES",
        server_default="SPRING_BOOT_JPA_POSTGRES",
    )

    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE"
    )

    # Carpeta/zip donde queda el backend generado (relativo a GENERATED_PROJECTS_DIR).
    ruta_salida: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    diagrama: Mapped["Diagrama"] = relationship(  # noqa: F821
        "Diagrama",
        foreign_keys=[id_diagrama],
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[id_usuario],
    )

    entidades: Mapped[list["EntidadGenerada"]] = relationship(
        "EntidadGenerada",
        back_populates="trabajo",
        cascade="all, delete-orphan",
    )

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

    def __repr__(self) -> str:
        return (
            f"<TrabajoGeneracionCodigo id={self.id} diagrama={self.id_diagrama} "
            f"estado={self.estado!r}>"
        )


# ======================================================================
# EntidadGenerada
# ======================================================================
class EntidadGenerada(Base):
    __tablename__ = "entidades_generadas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_trabajo: Mapped[int] = mapped_column(
        ForeignKey("trabajos_generacion_codigo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_clase_uml: Mapped[int] = mapped_column(
        ForeignKey("clases_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Nombre de la clase @Entity generada (ej. "Paciente", "HistoriaClinica").
    nombre_clase_java: Mapped[str] = mapped_column(String(150), nullable=False)

    # Tabla Postgres resultante (ej. "paciente", "historia_clinica").
    nombre_tabla: Mapped[str] = mapped_column(String(150), nullable=False)

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    trabajo: Mapped["TrabajoGeneracionCodigo"] = relationship(
        "TrabajoGeneracionCodigo", back_populates="entidades"
    )

    clase_uml: Mapped["ClaseUML"] = relationship(  # noqa: F821
        "ClaseUML",
        foreign_keys=[id_clase_uml],
    )

    reglas_mapeo: Mapped[list["ReglaMapeo"]] = relationship(
        "ReglaMapeo",
        back_populates="entidad_generada",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<EntidadGenerada id={self.id} java={self.nombre_clase_java!r} "
            f"tabla={self.nombre_tabla!r}>"
        )


# ======================================================================
# ReglaMapeo
# ======================================================================
class ReglaMapeo(Base):
    __tablename__ = "reglas_mapeo"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_entidad_generada: Mapped[int] = mapped_column(
        ForeignKey("entidades_generadas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    id_atributo_uml: Mapped[int] = mapped_column(
        ForeignKey("atributos_uml.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Nombre de la columna resultante (ej. "nombre_completo", "fecha_nacimiento").
    nombre_columna: Mapped[str] = mapped_column(String(100), nullable=False)

    # Tipo SQL resultante del mapeo (VARCHAR(150), INTEGER, DATE, BOOLEAN…).
    tipo_sql: Mapped[str] = mapped_column(String(50), nullable=False)

    es_clave_primaria: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    es_nulleable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    entidad_generada: Mapped["EntidadGenerada"] = relationship(
        "EntidadGenerada", back_populates="reglas_mapeo"
    )

    atributo_uml: Mapped["AtributoUML"] = relationship(  # noqa: F821
        "AtributoUML",
        foreign_keys=[id_atributo_uml],
    )

    def __repr__(self) -> str:
        return (
            f"<ReglaMapeo id={self.id} columna={self.nombre_columna!r} "
            f"tipo_sql={self.tipo_sql!r}>"
        )