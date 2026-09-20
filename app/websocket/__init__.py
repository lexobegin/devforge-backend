# app/websocket/__init__.py
"""
Módulo de colaboración en tiempo real por WebSocket.

- connection_manager: registro de conexiones activas por diagrama.
- collaboration_ws:  canal WS de edición colaborativa.
- events:            definición y parseo de eventos (class_created, etc.).
"""

from app.websocket.connection_manager import ConnectionManager, manager
from app.websocket.collaboration_ws import router

__all__ = ["ConnectionManager", "manager", "router"]