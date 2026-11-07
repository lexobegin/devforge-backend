# app/websocket/__init__.py
"""
Módulo de colaboración en tiempo real por WebSocket — CICLO 2.

- connection_manager: registro de conexiones activas por diagrama.
- collaboration_ws:  canal WS de edición colaborativa.
- events:            definición y parseo de eventos (class_created, etc.).

Migrado del Ciclo 1 (SQLAlchemy/AsyncSessionLocal → Beanie/MongoDB):
- ids STR (ObjectId en hex para usuario/diagrama/sesión; uuid hex para
  los elementos EMBEBIDOS del Diagrama).
- Token resuelto con el patrón de core/dependencies.py (decode_token →
  PydanticObjectId(sub) → Usuario.get()) y membresía con
  MiembroProyectoRepository sin estado.
- Historial con HistorialCambioRepository().create() (insert autónomo,
  sin commit). El contrato de eventos del canal se conserva.

El router se monta en app/main.py (Tanda 20): include_router del
agregador `router` de este paquete — igual que el Ciclo 1.
"""

from app.websocket.connection_manager import ConnectionManager, manager
from app.websocket.collaboration_ws import router

__all__ = ["ConnectionManager", "manager", "router"]