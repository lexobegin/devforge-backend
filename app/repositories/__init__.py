# app/repositories/__init__.py
"""
Punto central de importación de los repositorios de DevForge AI (CICLO 2).

Los repositorios encapsulan el acceso a datos (queries de Beanie/Motor
sobre MongoDB) y NO contienen lógica de negocio. La lógica vive en
`app/services/`.

Regla (Ciclo 2): los repositorios son SIN ESTADO (ya no reciben
AsyncSession; la conexión la lleva Beanie tras init_db()) y escriben con
insert()/save()/delete(). El control de transacciones del Ciclo 1
desaparece: cada save() persiste un documento completo, y la coherencia
la resuelve la capa de servicios RE-LEYENDO el documento antes de
modificar embebidos (fetch → modificar → save).
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

# --- G. IA (módulo G rediseñado: 3 repositorios, 3 colecciones nuevas) ---
# El InteraccionIARepository del Ciclo 1 se divide en: mensajes del chat
# (CU16), contexto enviado al modelo (CU17) y acciones del Agente Dev.
from app.repositories.mensaje_chat_repository import (
    MensajeChatRepository,
)
from app.repositories.contexto_ia_repository import (
    ContextoIARepository,
)
from app.repositories.accion_ia_repository import (
    AccionIARepository,
)

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
    # G — canal / contexto / acciones (antes InteraccionIARepository)
    "MensajeChatRepository",
    "ContextoIARepository",
    "AccionIARepository",
    # H
    "ColaSincronizacionRepository",
    # I
    "NotificacionRepository",
    # Auditoría
    "BitacoraRepository",
]