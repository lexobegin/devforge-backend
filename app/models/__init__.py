# app/models/__init__.py
"""
Punto central de importación de todos los documentos de DevForge AI (Ciclo 2).

Cambios respecto al Ciclo 1:
- Los modelos ORM de SQLAlchemy son ahora DOCUMENTOS Beanie (MongoDB).
- Los NOMBRES DE CLASE se conservan (Usuario, Proyecto, ClaseUML, ...) para
  minimizar cambios en servicios, repositorios y routers.
- Lo que eran tablas "hijas" (miembros_proyecto, participantes_sesion,
  clases_uml, atributos_uml, ...) son ahora clases EMBEBIDAS (EmbeddedDoc)
  dentro de su documento padre, según el criterio embeber/referenciar del
  informe (sección 6.3).
- InteraccionIA (tabla interacciones_ia del Ciclo 1) se retira: la trazabilidad
  de IA del Ciclo 2 vive en las colecciones mensajes_chat, contextos_ia y
  acciones_ia (CU16-CU21).
- DOCUMENTOS es la lista que app/mongo.init_db() pasa a init_beanie para
  crear colecciones e índices (reemplaza a Alembic).

IMPORTANTE: cualquier documento nuevo debe agregarse aquí Y a DOCUMENTOS.
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

# --- G. IA del Ciclo 2: canal del Agente Dev, contexto persistente y trazabilidad ---
from app.models.mensaje_chat import MensajeChat
from app.models.contexto_ia import ContextoIA
from app.models.accion_ia import AccionIA

# --- H. Sincronización Móvil/Web Offline ---
from app.models.sincronizacion import ColaSincronizacionMovil

# --- I. Notificaciones ---
from app.models.notificacion import Notificacion

# --- Auditoría ---
from app.models.auditoria import BitacoraSistema


# ----------------------------------------------------------------------
# Lista de DOCUMENTOS para init_beanie (colecciones con índices).
# Una colección por documento raíz: 16 colecciones en el Ciclo 2.
# (Los embebidos NO van aquí: viven dentro de su documento padre.)
# ----------------------------------------------------------------------
DOCUMENTOS = [
    # A. Usuarios y Seguridad
    Usuario,
    # B. Proyectos y Colaboración
    Proyecto,
    SesionColaboracion,
    # C. Modelado UML
    Diagrama,
    # D. Trazabilidad
    HistorialCambioDiagrama,
    VersionDiagrama,
    ComentarioDiagrama,
    # E. Intercambio XMI
    ExportacionDiagrama,
    ImportacionDiagrama,
    # F. Generación de código
    TrabajoGeneracionCodigo,
    # G. IA (Ciclo 2)
    MensajeChat,
    ContextoIA,
    AccionIA,
    # H. Sincronización offline
    ColaSincronizacionMovil,
    # I. Notificaciones
    Notificacion,
    # Auditoría
    BitacoraSistema,
]

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
    # G (Ciclo 2)
    "MensajeChat",
    "ContextoIA",
    "AccionIA",
    # H
    "ColaSincronizacionMovil",
    # I
    "Notificacion",
    # Auditoría
    "BitacoraSistema",
    # Registro Beanie
    "DOCUMENTOS",
]