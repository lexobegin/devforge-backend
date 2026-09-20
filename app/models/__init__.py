# app/models/__init__.py
"""
Punto central de importación de todos los modelos ORM de DevForge AI.

Importante:
- Alembic detecta las tablas solo si los modelos están importados ANTES
  de llamar a `Base.metadata` (ver alembic/env.py).
- Cualquier nuevo modelo debe agregarse aquí.
"""

# --- A. Usuarios y Seguridad ---
from app.models.usuario import Usuario

# --- B. Proyectos y Colaboración ---
from app.models.proyecto import Proyecto, MiembroProyecto
from app.models.colaboracion import SesionColaboracion, ParticipanteSesion

# --- C. Modelado UML (Diagrama de Clases) ---
from app.models.diagrama import (
    Diagrama,
    ClaseUML,
    AtributoUML,
    OperacionUML,
    ParametroOperacionUML,
    InterfazUML,
    OperacionInterfazUML,
    RelacionUML,
)

# --- D. Trazabilidad y Colaboración en Tiempo Real ---
from app.models.trazabilidad import (
    HistorialCambioDiagrama,
    VersionDiagrama,
    ComentarioDiagrama,
)

# --- E. Intercambio de Modelos (XMI/XML) ---
from app.models.intercambio import (
    ExportacionDiagrama,
    ImportacionDiagrama,
)

# --- F. Generación Automática de Backend ---
from app.models.generacion import (
    TrabajoGeneracionCodigo,
    EntidadGenerada,
    ReglaMapeo,
)

# --- G. IA Asistente (Voz / Texto / Imagen) ---
from app.models.ia import InteraccionIA

# --- H. Sincronización Móvil/Web Offline ---
from app.models.sincronizacion import ColaSincronizacionMovil

# --- I. Notificaciones ---
from app.models.notificacion import Notificacion

# --- Auditoría ---
from app.models.auditoria import BitacoraSistema


__all__ = [
    # A
    "Usuario",
    # B
    "Proyecto",
    "MiembroProyecto",
    "SesionColaboracion",
    "ParticipanteSesion",
    # C
    "Diagrama",
    "ClaseUML",
    "AtributoUML",
    "OperacionUML",
    "ParametroOperacionUML",
    "InterfazUML",
    "OperacionInterfazUML",
    "RelacionUML",
    # D
    "HistorialCambioDiagrama",
    "VersionDiagrama",
    "ComentarioDiagrama",
    # E
    "ExportacionDiagrama",
    "ImportacionDiagrama",
    # F
    "TrabajoGeneracionCodigo",
    "EntidadGenerada",
    "ReglaMapeo",
    # G
    "InteraccionIA",
    # H
    "ColaSincronizacionMovil",
    # I
    "Notificacion",
    # Auditoría
    "BitacoraSistema",
]