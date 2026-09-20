# app/repositories/__init__.py
"""
Punto central de importación de los repositorios de DevForge AI.

Los repositorios encapsulan el acceso a datos (queries SQLAlchemy async)
y NO contienen lógica de negocio. La lógica vive en `app/services/`.

Regla: los repositorios solo hacen flush(), nunca commit().
El commit lo maneja la capa de servicios.
"""

# --- A. Usuarios ---
from app.repositories.usuario_repository import UsuarioRepository

# --- B. Proyectos ---
from app.repositories.proyecto_repository import (
    ProyectoRepository,
    MiembroProyectoRepository,
)

# --- B. Colaboración ---
from app.repositories.colaboracion_repository import (
    SesionColaboracionRepository,
    ParticipanteSesionRepository,
)

# --- C. Diagrama UML ---
from app.repositories.diagrama_repository import (
    DiagramaRepository,
    ClaseUMLRepository,
    AtributoUMLRepository,
    OperacionUMLRepository,
    ParametroOperacionUMLRepository,
    InterfazUMLRepository,
    OperacionInterfazUMLRepository,
    RelacionUMLRepository,
)

# --- D. Trazabilidad ---
from app.repositories.trazabilidad_repository import (
    HistorialCambioRepository,
    VersionDiagramaRepository,
    ComentarioDiagramaRepository,
)

# --- E. Intercambio ---
from app.repositories.intercambio_repository import (
    ExportacionRepository,
    ImportacionRepository,
)

# --- F. Generación ---
from app.repositories.generacion_repository import (
    TrabajoGeneracionRepository,
    EntidadGeneradaRepository,
    ReglaMapeoRepository,
)

# --- G. IA ---
from app.repositories.ia_repository import InteraccionIARepository

# --- H. Sincronización ---
from app.repositories.sincronizacion_repository import (
    ColaSincronizacionRepository,
)

# --- I. Notificaciones ---
from app.repositories.notificacion_repository import NotificacionRepository

# --- Auditoría ---
from app.repositories.auditoria_repository import BitacoraRepository


__all__ = [
    # A
    "UsuarioRepository",
    # B
    "ProyectoRepository",
    "MiembroProyectoRepository",
    "SesionColaboracionRepository",
    "ParticipanteSesionRepository",
    # C
    "DiagramaRepository",
    "ClaseUMLRepository",
    "AtributoUMLRepository",
    "OperacionUMLRepository",
    "ParametroOperacionUMLRepository",
    "InterfazUMLRepository",
    "OperacionInterfazUMLRepository",
    "RelacionUMLRepository",
    # D
    "HistorialCambioRepository",
    "VersionDiagramaRepository",
    "ComentarioDiagramaRepository",
    # E
    "ExportacionRepository",
    "ImportacionRepository",
    # F
    "TrabajoGeneracionRepository",
    "EntidadGeneradaRepository",
    "ReglaMapeoRepository",
    # G
    "InteraccionIARepository",
    # H
    "ColaSincronizacionRepository",
    # I
    "NotificacionRepository",
    # Auditoría
    "BitacoraRepository",
]