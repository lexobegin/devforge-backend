# app/api/v1/__init__.py
"""
Routers de la API v1 de DevForge AI.

Cada router expone los endpoints de un módulo funcional y delega la
lógica de negocio en `app/services/`. Los routers NO contienen lógica de
negocio: solo validan entrada, llaman al servicio y formatean la salida.

CICLO 2: misma estructura y los MISMOS 13 routers que el Ciclo 1 (el
__all__ no cambia para no romper el include_router de main.py). Cada
router ya no recibe AsyncSession: los services se instancian sin sesión
y los ids de ruta son PydanticObjectId (str de ObjectId en el JSON).
"""

# --- A. Usuarios y Seguridad ---
from app.api.v1 import auth_router
from app.api.v1 import usuarios_router

# --- B. Proyectos y Colaboración ---
from app.api.v1 import proyectos_router
from app.api.v1 import colaboracion_router

# --- C. Modelado UML ---
from app.api.v1 import diagramas_router

# --- D. Trazabilidad ---
from app.api.v1 import trazabilidad_router

# --- E. Intercambio ---
from app.api.v1 import intercambio_router

# --- F. Generación ---
from app.api.v1 import generacion_router

# --- G. IA ---
from app.api.v1 import ia_router
from app.api.v1 import ai_vision_router

# --- H. Sincronización ---
from app.api.v1 import sincronizacion_router

# --- I. Notificaciones ---
from app.api.v1 import notificaciones_router

# --- Administración y Auditoría ---
from app.api.v1 import auditoria_router
from app.api.v1 import admin_router


__all__ = [
    # A
    "auth_router",
    "usuarios_router",
    # B
    "proyectos_router",
    "colaboracion_router",
    # C
    "diagramas_router",
    # D
    "trazabilidad_router",
    # E
    "intercambio_router",
    # F
    "generacion_router",
    # G
    "ia_router",
    "ai_vision_router",
    # H
    "sincronizacion_router",
    # I
    "notificaciones_router",
    # Auditoría
    "auditoria_router",
    # Administración de archivos (Tanda B24)
    "admin_router",
]