# app/websocket/connection_manager.py
"""
Gestor de conexiones WebSocket activas de DevForge AI — CICLO 2.

Responsabilidades:
- Llevar el registro de conexiones por diagrama.
- Asociar cada conexión a un usuario y a una sesión colaborativa.
- Broadcast de mensajes a todos los clientes de un diagrama (o a todos
  menos al emisor).
- Broadcast de mensajes a un usuario específico (por si tiene varias
  pestañas abiertas).
- Cerrar conexiones huérfanas y limpiar registros.

No contiene lógica de negocio ni persistencia: solo mantiene el estado
en memoria de las conexiones activas.

Migrado del Ciclo 1 (cambios):
- Los ids (usuario, diagrama, sesión) son STR: ObjectId en hex en lugar
  de ints (y la sesión es el id str de SesionColaboracion). El estado de
  conexiones sigue viviendo SOLO en memoria del proceso, sin BD.
- accept() lo hace el endpoint ANTES de registrar (no aquí): connect()
  solo registra una conexión ya aceptada (igual que quedaba el Ciclo 1
  tras mover el accept al endpoint).
- El envío usa websocket.send_json: los ids de los mensajes viajan como
  str para que json.dumps no reviente con ObjectId.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger("devforge.ws")


# ======================================================================
# Representación de una conexión
# ======================================================================
@dataclass
class ConnectionInfo:
    websocket: WebSocket
    id_usuario: str
    nombre_usuario: str
    id_diagrama: str
    id_sesion: Optional[str] = None
    # Buffer de envío para serializar mensajes por conexión
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# ======================================================================
# Manager
# ======================================================================
class ConnectionManager:
    """
    Mantiene un mapa:
        id_diagrama → { id_conexion → ConnectionInfo }

    El id_conexion es un entero secuencial interno (para distinguir varias
    pestañas del mismo usuario).
    """

    def __init__(self) -> None:
        # { id_diagrama: { id_conexion: ConnectionInfo } }
        self._connections: dict[str, dict[int, ConnectionInfo]] = {}
        self._next_id: int = 1
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    async def connect(
        self,
        websocket: WebSocket,
        *,
        id_usuario: str,
        nombre_usuario: str,
        id_diagrama: str,
        id_sesion: Optional[str] = None,
    ) -> int:
        """
        Registra una conexión YA ACEPTADA (el accept lo hace el endpoint).
        Devuelve el id interno de conexión.
        """
        async with self._lock:
            id_conexion = self._next_id
            self._next_id += 1

            self._connections.setdefault(id_diagrama, {})[id_conexion] = (
                ConnectionInfo(
                    websocket=websocket,
                    id_usuario=id_usuario,
                    nombre_usuario=nombre_usuario,
                    id_diagrama=id_diagrama,
                    id_sesion=id_sesion,
                )
            )

        logger.info(
            "WS conectado: diagrama=%s usuario=%s conexion=%s",
            id_diagrama,
            id_usuario,
            id_conexion,
        )
        return id_conexion

    async def disconnect(self, id_diagrama: str, id_conexion: int) -> None:
        """Quita una conexión del registro."""
        async with self._lock:
            diagrama_conns = self._connections.get(id_diagrama)
            if not diagrama_conns:
                return
            info = diagrama_conns.pop(id_conexion, None)
            if diagrama_conns == {}:
                self._connections.pop(id_diagrama, None)

        if info is not None:
            logger.info(
                "WS desconectado: diagrama=%s usuario=%s conexion=%s",
                id_diagrama,
                info.id_usuario,
                id_conexion,
            )

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def get_connections(self, id_diagrama: str) -> list[ConnectionInfo]:
        """Lista las conexiones activas de un diagrama."""
        return list(self._connections.get(id_diagrama, {}).values())

    def count(self, id_diagrama: str) -> int:
        return len(self._connections.get(id_diagrama, {}))

    def usuarios_conectados(self, id_diagrama: str) -> list[dict[str, Any]]:
        """Lista usuarios únicos conectados al diagrama (para el panel)."""
        vistos: dict[str, dict[str, Any]] = {}
        for info in self.get_connections(id_diagrama):
            # Si el usuario tiene varias pestañas, solo lo contamos una vez
            if info.id_usuario not in vistos:
                vistos[info.id_usuario] = {
                    "id": info.id_usuario,
                    "nombre": info.nombre_usuario,
                    "conexiones": 0,
                }
            vistos[info.id_usuario]["conexiones"] += 1
        return list(vistos.values())

    # ------------------------------------------------------------------
    # Envío de mensajes
    # ------------------------------------------------------------------
    async def send_to_connection(
        self, id_conexion: int, mensaje: dict[str, Any]
    ) -> None:
        """Envía un mensaje a una conexión concreta (por su id interno)."""
        # Buscar la conexión en cualquier diagrama
        for diagrama_conns in self._connections.values():
            info = diagrama_conns.get(id_conexion)
            if info is not None:
                await self._safe_send(info, mensaje)
                return

    async def broadcast(
        self,
        id_diagrama: str,
        mensaje: dict[str, Any],
        *,
        excluir_conexion: Optional[int] = None,
    ) -> None:
        """
        Envía el mensaje a TODAS las conexiones del diagrama,
        opcionalmente excluyendo una (el emisor del cambio).
        """
        conexiones = self.get_connections(id_diagrama)
        await asyncio.gather(
            *[
                self._safe_send(info, mensaje)
                for info in conexiones
                if info.websocket is not None
                and _conexion_id(info, id_diagrama, self._connections) != excluir_conexion
            ],
            return_exceptions=True,
        )

    async def broadcast_to_usuario(
        self, id_usuario: str, mensaje: dict[str, Any]
    ) -> None:
        """
        Envía un mensaje a TODAS las conexiones de un usuario
        (por si tiene varias pestañas abiertas).
        """
        targets: list[ConnectionInfo] = []
        for diagrama_conns in self._connections.values():
            for info in diagrama_conns.values():
                if info.id_usuario == id_usuario:
                    targets.append(info)

        await asyncio.gather(
            *[self._safe_send(info, mensaje) for info in targets],
            return_exceptions=True,
        )

    async def close_connection(
        self, id_diagrama: str, id_conexion: int, *, code: int = 1000
    ) -> None:
        """Cierra la conexión WebSocket y la elimina del registro."""
        info = self._connections.get(id_diagrama, {}).get(id_conexion)
        if info is None:
            return
        try:
            await info.websocket.close(code=code)
        except Exception:
            pass
        finally:
            await self.disconnect(id_diagrama, id_conexion)

    async def close_all(self, id_diagrama: str) -> None:
        """Cierra todas las conexiones de un diagrama (al eliminar el diagrama)."""
        conexiones = self.get_connections(id_diagrama)
        for info in conexiones:
            try:
                await info.websocket.close(code=1001)  # going away
            except Exception:
                pass
        async with self._lock:
            self._connections.pop(id_diagrama, None)

    # ------------------------------------------------------------------
    # Envío seguro (con lock por conexión)
    # ------------------------------------------------------------------
    async def _safe_send(
        self, info: ConnectionInfo, mensaje: dict[str, Any]
    ) -> None:
        """
        Envía sin lanzar excepciones hacia el llamador.
        Usa un lock por conexión para serializar envíos concurrentes
        (varios broadcasts simultáneos al mismo socket).
        """
        async with info.lock:
            try:
                await info.websocket.send_json(mensaje)
            except Exception as exc:
                logger.warning(
                    "Error enviando por WS (usuario=%s): %s",
                    info.id_usuario,
                    exc,
                )


# ----------------------------------------------------------------------
# Helper: obtener el id_conexion de una ConnectionInfo
# ----------------------------------------------------------------------
def _conexion_id(
    info: ConnectionInfo,
    id_diagrama: str,
    connections: dict[str, dict[int, ConnectionInfo]],
) -> Optional[int]:
    for cid, i in connections.get(id_diagrama, {}).items():
        if i is info:
            return cid
    return None


# ======================================================================
# Instancia global (singleton)
# ======================================================================
manager = ConnectionManager()