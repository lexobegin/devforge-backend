# app/schemas/__init__.py
"""
Punto central de importación de todos los esquemas Pydantic de DevForge AI.

Permite importar de forma plana:
    from app.schemas import UsuarioResponse, ProyectoCreate, ...
"""

# --- A. Usuarios ---
from app.schemas.usuario_schema import (
    UsuarioBase,
    UsuarioCreate,
    UsuarioUpdate,
    UsuarioResponse,
    UsuarioLogin,
    TokenResponse,
    RefreshTokenRequest,
    PasswordChange,
    RolGlobal,
)

# --- B. Proyectos ---
from app.schemas.proyecto_schema import (
    ProyectoBase,
    ProyectoCreate,
    ProyectoUpdate,
    ProyectoResponse,
    ProyectoConMiembrosResponse,
    MiembroProyectoBase,
    MiembroProyectoCreate,
    MiembroProyectoUpdate,
    MiembroProyectoResponse,
    EstadoProyecto,
    RolEnProyecto,
)

# --- B. Colaboración ---
from app.schemas.colaboracion_schema import (
    SesionColaboracionBase,
    SesionColaboracionCreate,
    SesionColaboracionResponse,
    SesionConParticipantesResponse,
    ParticipanteSesionBase,
    ParticipanteSesionCreate,
    ParticipanteSesionUpdate,
    ParticipanteSesionResponse,
)

# --- C. Diagrama UML ---
from app.schemas.diagrama_schema import (
    DiagramaBase,
    DiagramaCreate,
    DiagramaUpdate,
    DiagramaResponse,
    DiagramaCompletoResponse,
    ClaseUMLBase,
    ClaseUMLCreate,
    ClaseUMLUpdate,
    ClaseUMLResponse,
    AtributoUMLBase,
    AtributoUMLCreate,
    AtributoUMLUpdate,
    AtributoUMLResponse,
    OperacionUMLBase,
    OperacionUMLCreate,
    OperacionUMLUpdate,
    OperacionUMLResponse,
    ParametroOperacionUMLBase,
    ParametroOperacionUMLCreate,
    ParametroOperacionUMLUpdate,
    ParametroOperacionUMLResponse,
    InterfazUMLBase,
    InterfazUMLCreate,
    InterfazUMLUpdate,
    InterfazUMLResponse,
    OperacionInterfazUMLBase,
    OperacionInterfazUMLCreate,
    OperacionInterfazUMLUpdate,
    OperacionInterfazUMLResponse,
    RelacionUMLBase,
    RelacionUMLCreate,
    RelacionUMLUpdate,
    RelacionUMLResponse,
    Visibilidad,
    TipoRelacion,
)

# --- D. Trazabilidad ---
from app.schemas.trazabilidad_schema import (
    HistorialCambioDiagramaBase,
    HistorialCambioDiagramaCreate,
    HistorialCambioDiagramaResponse,
    VersionDiagramaBase,
    VersionDiagramaCreate,
    VersionDiagramaResponse,
    VersionDiagramaResumenResponse,
    ComentarioDiagramaBase,
    ComentarioDiagramaCreate,
    ComentarioDiagramaUpdate,
    ComentarioDiagramaResponse,
    TipoCambio,
)

# --- E. Intercambio ---
from app.schemas.intercambio_schema import (
    ExportacionDiagramaBase,
    ExportacionDiagramaCreate,
    ExportacionDiagramaResponse,
    ExportacionResultado,
    ImportacionDiagramaBase,
    ImportacionDiagramaCreate,
    ImportacionDiagramaUpdate,
    ImportacionDiagramaResponse,
    ImportacionResultado,
    FormatoIntercambio,
    EstadoImportacion,
)

# --- F. Generación ---
from app.schemas.generacion_schema import (
    TrabajoGeneracionCodigoBase,
    TrabajoGeneracionCodigoCreate,
    TrabajoGeneracionCodigoResponse,
    TrabajoGeneracionDetalleResponse,
    EntidadGeneradaBase,
    EntidadGeneradaResponse,
    ReglaMapeoBase,
    ReglaMapeoResponse,
    GenerarBackendRequest,
    EstadoGeneracionResponse,
    DescargaProyectoResponse,
    EstadoTrabajoGeneracion,
    StackDestino,
)

# --- G. IA ---
from app.schemas.ia_schema import (
    InteraccionIABase,
    InteraccionIACreate,
    InteraccionIAResponse,
    PromptIARequest,
    AccionIAPropuesta,
    RespuestaIA,
    ConfirmarAccionIARequest,
    VisionReconocimientoResponse,
    CanalIA,
)

# --- H. Sincronización ---
from app.schemas.sincronizacion_schema import (
    ColaSincronizacionMovilBase,
    ColaSincronizacionMovilCreate,
    ColaSincronizacionMovilResponse,
    CambioOfflineItem,
    BatchSincronizacionRequest,
    BatchSincronizacionResponse,
    ResultadoCambioSync,
    ConflictoSyncResponse,
    ResolverConflictoRequest,
    EstadoColaSync,
)

# --- I. Notificaciones ---
from app.schemas.notificacion_schema import (
    NotificacionBase,
    NotificacionCreate,
    NotificacionResponse,
    MarcarNotificacionesLeidasRequest,
    ContadorNoLeidasResponse,
    TipoNotificacion,
)


__all__ = [
    # A
    "UsuarioBase", "UsuarioCreate", "UsuarioUpdate", "UsuarioResponse",
    "UsuarioLogin", "TokenResponse", "RefreshTokenRequest", "PasswordChange",
    "RolGlobal",
    # B. Proyectos
    "ProyectoBase", "ProyectoCreate", "ProyectoUpdate", "ProyectoResponse",
    "ProyectoConMiembrosResponse",
    "MiembroProyectoBase", "MiembroProyectoCreate", "MiembroProyectoUpdate",
    "MiembroProyectoResponse", "EstadoProyecto", "RolEnProyecto",
    # B. Colaboración
    "SesionColaboracionBase", "SesionColaboracionCreate",
    "SesionColaboracionResponse", "SesionConParticipantesResponse",
    "ParticipanteSesionBase", "ParticipanteSesionCreate",
    "ParticipanteSesionUpdate", "ParticipanteSesionResponse",
    # C
    "DiagramaBase", "DiagramaCreate", "DiagramaUpdate", "DiagramaResponse",
    "DiagramaCompletoResponse",
    "ClaseUMLBase", "ClaseUMLCreate", "ClaseUMLUpdate", "ClaseUMLResponse",
    "AtributoUMLBase", "AtributoUMLCreate", "AtributoUMLUpdate", "AtributoUMLResponse",
    "OperacionUMLBase", "OperacionUMLCreate", "OperacionUMLUpdate", "OperacionUMLResponse",
    "ParametroOperacionUMLBase", "ParametroOperacionUMLCreate",
    "ParametroOperacionUMLUpdate", "ParametroOperacionUMLResponse",
    "InterfazUMLBase", "InterfazUMLCreate", "InterfazUMLUpdate", "InterfazUMLResponse",
    "OperacionInterfazUMLBase", "OperacionInterfazUMLCreate",
    "OperacionInterfazUMLUpdate", "OperacionInterfazUMLResponse",
    "RelacionUMLBase", "RelacionUMLCreate", "RelacionUMLUpdate", "RelacionUMLResponse",
    "Visibilidad", "TipoRelacion",
    # D
    "HistorialCambioDiagramaBase", "HistorialCambioDiagramaCreate",
    "HistorialCambioDiagramaResponse",
    "VersionDiagramaBase", "VersionDiagramaCreate", "VersionDiagramaResponse",
    "VersionDiagramaResumenResponse",
    "ComentarioDiagramaBase", "ComentarioDiagramaCreate",
    "ComentarioDiagramaUpdate", "ComentarioDiagramaResponse", "TipoCambio",
    # E
    "ExportacionDiagramaBase", "ExportacionDiagramaCreate",
    "ExportacionDiagramaResponse", "ExportacionResultado",
    "ImportacionDiagramaBase", "ImportacionDiagramaCreate",
    "ImportacionDiagramaUpdate", "ImportacionDiagramaResponse",
    "ImportacionResultado", "FormatoIntercambio", "EstadoImportacion",
    # F
    "TrabajoGeneracionCodigoBase", "TrabajoGeneracionCodigoCreate",
    "TrabajoGeneracionCodigoResponse", "TrabajoGeneracionDetalleResponse",
    "EntidadGeneradaBase", "EntidadGeneradaResponse",
    "ReglaMapeoBase", "ReglaMapeoResponse",
    "GenerarBackendRequest", "EstadoGeneracionResponse", "DescargaProyectoResponse",
    "EstadoTrabajoGeneracion", "StackDestino",
    # G
    "InteraccionIABase", "InteraccionIACreate", "InteraccionIAResponse",
    "PromptIARequest", "AccionIAPropuesta", "RespuestaIA",
    "ConfirmarAccionIARequest", "VisionReconocimientoResponse", "CanalIA",
    # H
    "ColaSincronizacionMovilBase", "ColaSincronizacionMovilCreate",
    "ColaSincronizacionMovilResponse",
    "CambioOfflineItem", "BatchSincronizacionRequest", "BatchSincronizacionResponse",
    "ResultadoCambioSync", "ConflictoSyncResponse", "ResolverConflictoRequest",
    "EstadoColaSync",
    # I
    "NotificacionBase", "NotificacionCreate", "NotificacionResponse",
    "MarcarNotificacionesLeidasRequest", "ContadorNoLeidasResponse",
    "TipoNotificacion",
]