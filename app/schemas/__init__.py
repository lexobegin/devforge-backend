# app/schemas/__init__.py
"""
Punto central de importación de todos los esquemas Pydantic de DevForge AI.

Permite importar de forma plana:
    from app.schemas import UsuarioResponse, ProyectoCreate, ...

Estado de la conversión Ciclo 2 (TANDAS 7 y 8 completas):
- TANDA 7: A. Usuarios · B. Proyectos · B. Colaboración · C. Diagrama UML.
- TANDA 8: D. Trazabilidad · E. Intercambio XMI · F. Generación de código ·
  G. IA (rediseñada: mensajes_chat / contextos_ia / acciones_ia sustituyen a
  interacciones_ia) · H. Sincronización · I. Notificaciones.
- REORGANIZACIÓN del módulo G (espejo de la estructura del Ciclo 2):
  ia_schema.py se divide en canal_schema.py (CU16: mensajes + voz),
  agente_schema.py (CU17-CU21: contexto, acciones y confirmación) y
  asistente_guia_schema.py (CU23); VisionReconocimientoResponse pasa a
  diagrama_schema.py (la visión produce un diagrama del módulo C).
- AUDITORÍA (Paso 0 de services): auditoria_schema.py se registra aquí
  (el módulo existía en el Ciclo 1, su repositorio ya estaba en la
  Tanda 9; el schema llegó tarde del Ciclo 1).

Cambios generales respecto al Ciclo 1:
- Los ids int (serial/FK) se exponen como string: PydanticObjectId de
  Beanie para referencias entre documentos (se serializa como string hex
  en JSON) y str uuid para los elementos embebidos del Diagrama.
- Miembros de proyecto, participantes de sesión, entidades generadas y
  reglas de mapeo son EMBEBIDOS: sus *Response pierden el id propio y el
  id del padre.
- InteraccionIA* queda RETIRADA: su lugar lo toman MensajeChat*,
  ContextoIAResponse y AccionIA* (módulo G rediseñado y dividido en los
  3 archivos de canal/agente/asistente_guia), más
  TranscripcionVozResponse para la voz local con faster-whisper.
- Los *Update se reutilizan para validar el payload de las acciones de la
  IA antes de aplicarlas al lienzo (Agente Dev CU16-21), y el vocabulario
  tipo_accion/tipo_operacion es el mismo en IA y sincronización offline.
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
    PosicionLienzo,
    VisionReconocimientoResponse,
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

# --- E. Intercambio XMI ---
from app.schemas.intercambio_schema import (
    ExportacionDiagramaBase,
    ExportacionDiagramaCreate,
    ExportacionDiagramaResponse,
    ImportacionDiagramaBase,
    ImportacionDiagramaCreate,
    ImportacionDiagramaUpdate,
    ImportacionDiagramaResponse,
    ExportacionResultado,
    ImportacionResultado,
    FormatoIntercambio,
    EstadoImportacion,
)

# --- F. Generación de código ---
from app.schemas.generacion_schema import (
    ReglaMapeoBase,
    ReglaMapeoResponse,
    EntidadGeneradaBase,
    EntidadGeneradaResponse,
    TrabajoGeneracionCodigoBase,
    TrabajoGeneracionCodigoCreate,
    TrabajoGeneracionCodigoResponse,
    TrabajoGeneracionDetalleResponse,
    GenerarBackendRequest,
    EstadoGeneracionResponse,
    DescargaProyectoResponse,
    EstadoGeneracion,
    StackDestino,
)

# --- G. Canal de entrada (CU16: mensajes de texto y voz) ---
from app.schemas.canal_schema import (
    MensajeChatCreate,
    MensajeChatResponse,
    TranscripcionVozResponse,
    PromptIARequest,
    RolMensaje,
    OrigenMensaje,
)

# --- G. Agente Dev (CU17-CU21: contexto, acciones y confirmación) ---
from app.schemas.agente_schema import (
    ContextoIAResponse,
    AccionIAPropuesta,
    AccionIAResponse,
    RespuestaIA,
    ConfirmarAccionIARequest,
    EstadoAccionIA,
)

# --- G. Asistente Guía (CU23, solo lectura) ---
from app.schemas.asistente_guia_schema import (
    PreguntaGuiaRequest,
    RespuestaGuiaResponse,
)

# --- H. Sincronización ---
from app.schemas.sincronizacion_schema import (
    ColaSincronizacionMovilBase,
    ColaSincronizacionMovilCreate,
    ColaSincronizacionMovilResponse,
    CambioOfflineItem,
    BatchSincronizacionRequest,
    ResultadoCambioSync,
    BatchSincronizacionResponse,
    ConflictoSyncResponse,
    ResolverConflictoRequest,
    EstadoSincronizacion,
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

# --- Auditoría ---
from app.schemas.auditoria_schema import (
    BitacoraSistemaResponse,
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
    "Visibilidad", "TipoRelacion", "PosicionLienzo",
    "VisionReconocimientoResponse",
    # D
    "HistorialCambioDiagramaBase", "HistorialCambioDiagramaCreate",
    "HistorialCambioDiagramaResponse",
    "VersionDiagramaBase", "VersionDiagramaCreate", "VersionDiagramaResponse",
    "VersionDiagramaResumenResponse",
    "ComentarioDiagramaBase", "ComentarioDiagramaCreate",
    "ComentarioDiagramaUpdate", "ComentarioDiagramaResponse",
    "TipoCambio",
    # E
    "ExportacionDiagramaBase", "ExportacionDiagramaCreate",
    "ExportacionDiagramaResponse",
    "ImportacionDiagramaBase", "ImportacionDiagramaCreate",
    "ImportacionDiagramaUpdate", "ImportacionDiagramaResponse",
    "ExportacionResultado", "ImportacionResultado",
    "FormatoIntercambio", "EstadoImportacion",
    # F
    "ReglaMapeoBase", "ReglaMapeoResponse",
    "EntidadGeneradaBase", "EntidadGeneradaResponse",
    "TrabajoGeneracionCodigoBase", "TrabajoGeneracionCodigoCreate",
    "TrabajoGeneracionCodigoResponse", "TrabajoGeneracionDetalleResponse",
    "GenerarBackendRequest", "EstadoGeneracionResponse", "DescargaProyectoResponse",
    "EstadoGeneracion", "StackDestino",
    # G — canal (CU16) · agente (CU17-CU21) · guía (CU23)
    "MensajeChatCreate", "MensajeChatResponse", "TranscripcionVozResponse",
    "PromptIARequest", "RolMensaje", "OrigenMensaje",
    "ContextoIAResponse", "AccionIAPropuesta", "AccionIAResponse",
    "RespuestaIA", "ConfirmarAccionIARequest", "EstadoAccionIA",
    "PreguntaGuiaRequest", "RespuestaGuiaResponse",
    # H
    "ColaSincronizacionMovilBase", "ColaSincronizacionMovilCreate",
    "ColaSincronizacionMovilResponse",
    "CambioOfflineItem", "BatchSincronizacionRequest", "ResultadoCambioSync",
    "BatchSincronizacionResponse", "ConflictoSyncResponse",
    "ResolverConflictoRequest", "EstadoSincronizacion",
    # I
    "NotificacionBase", "NotificacionCreate", "NotificacionResponse",
    "MarcarNotificacionesLeidasRequest", "ContadorNoLeidasResponse",
    "TipoNotificacion",
    # Auditoría
    "BitacoraSistemaResponse",
]