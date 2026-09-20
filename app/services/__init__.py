# app/services/__init__.py
"""
Punto central de importación de los servicios de DevForge AI.

Los servicios contienen la lógica de negocio y SON los responsables de
hacer commit() al final de cada unidad de trabajo. Los repositorios solo
hacen flush().
"""

# --- A. Usuarios y Seguridad ---
from app.services.auth_service import AuthService
from app.services.usuario_service import UsuarioService

# --- B. Proyectos y Colaboración ---
from app.services.proyecto_service import ProyectoService
from app.services.colaboracion_service import ColaboracionService

# --- C. Modelado UML ---
from app.services.diagrama_service import DiagramaService

# --- D. Trazabilidad ---
from app.services.trazabilidad_service import TrazabilidadService

# --- E. Intercambio ---
from app.services.intercambio_service import IntercambioService

# --- G. IA ---
from app.services.ia_service import IAService

# --- H. Sincronización ---
from app.services.sincronizacion_service import SincronizacionService

# --- I. Notificaciones ---
from app.services.notificacion_service import NotificacionService

# --- Auditoría ---
from app.services.auditoria_service import AuditoriaService


__all__ = [
    # A
    "AuthService",
    "UsuarioService",
    # B
    "ProyectoService",
    "ColaboracionService",
    # C
    "DiagramaService",
    # D
    "TrazabilidadService",
    # E
    "IntercambioService",
    # G
    "IAService",
    # H
    "SincronizacionService",
    # I
    "NotificacionService",
    # Auditoría
    "AuditoriaService",
]