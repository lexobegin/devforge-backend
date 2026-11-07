# app/services/__init__.py
"""
Punto central de importación de los servicios de DevForge AI — CICLO 2.

Los servicios contienen la lógica de negocio y orquestan repositorios
SIN ESTADO. En MongoDB/Beanie no hay transacciones: cada insert()/save()/
delete() persiste de inmediato y la coherencia se logra RE-LEYENDO el
documento antes de mutar embebidos (fetch → modificar → save).

Tanda 11 (services núcleo): módulos A (usuarios/seguridad), B (proyectos
y colaboración) y Auditoría. Tanda 12: diagrama (C) y trazabilidad (D).
Tanda 13: intercambio (E), sincronización (H) y notificaciones (I) — con
ella quedó CERRADA la conversión de los services heredados del Ciclo 1.
Tanda 14: infraestructura IA bajo los services (app/ia/, sin BD).
Tanda 15: services NUEVOS del módulo G — canal de entrada (CU16) y
gestor de contexto (CU17). Tanda 16: el CEREBRO del agente —
orquestador (CU18-CU21: cadena → JSON → AccionIA PROPUESTA) y ejecutor
de acciones (confirmación → validación *Update → lienzo). Tanda 17:
asistente guía (CU23, solo lectura: texto + sugerencias) y generador
de frontend React (CU24, REACT_TS_VITE con templates_react). Quedan:
code_generator del Ciclo 1 (generator_service ⭐ + mapping_engine ⭐)
y utils/validators (T18).
"""

# --- A. Usuarios y Seguridad ---
from app.services.auth_service import AuthService
from app.services.usuario_service import UsuarioService

# --- B. Proyectos y Colaboración ---
from app.services.proyecto_service import ProyectoService
from app.services.colaboracion_service import ColaboracionService

# --- Auditoría ---
from app.services.auditoria_service import AuditoriaService

# --- C. Modelado UML (Diagrama) ---
from app.services.diagrama_service import DiagramaService

# --- D. Trazabilidad ---
from app.services.trazabilidad_service import TrazabilidadService

# --- E. Intercambio XMI/XML ---
from app.services.intercambio_service import IntercambioService

# --- H. Sincronización Móvil/Web Offline ---
from app.services.sincronizacion_service import SincronizacionService

# --- I. Notificaciones ---
from app.services.notificacion_service import NotificacionService

# --- G. IA: canal (CU16) + gestor de contexto (CU17) ---
from app.services.canal_service import CanalService
from app.services.gestor_contexto_service import GestorContextoService

# --- G. IA: agente dev — orquestador (CU18-CU21) + ejecutor de acciones ---
from app.services.orquestador_agente_service import OrquestadorAgenteService
from app.services.ejecutor_acciones_service import EjecutorAccionesService

# --- G. IA: guía (CU23) + F. generador frontend React (CU24, T17) ---
from app.services.asistente_guia_service import AsistenteGuiaService
from app.services.generador_frontend_service import GeneradorFrontendService


__all__ = [
    # A
    "AuthService",
    "UsuarioService",
    # B
    "ProyectoService",
    "ColaboracionService",
    # Auditoría
    "AuditoriaService",
    # C
    "DiagramaService",
    # D
    "TrazabilidadService",
    # E
    "IntercambioService",
    # H
    "SincronizacionService",
    # I
    "NotificacionService",
    # G — IA (T15: canal de entrada + gestor de contexto)
    "CanalService",
    "GestorContextoService",
    # G — IA (T16: agente dev)
    "OrquestadorAgenteService",
    "EjecutorAccionesService",
    # G — IA (T17: guía) + F — generación frontend React (CU24)
    "AsistenteGuiaService",
    "GeneradorFrontendService",
]