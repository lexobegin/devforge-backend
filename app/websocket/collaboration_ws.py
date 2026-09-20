# app/websocket/collaboration_ws.py
"""
Canal WebSocket de colaboración en tiempo real sobre un diagrama.

Endpoint:
    ws://<host>/ws/diagramas/{diagrama_id}?token=<jwt>

Flujo:
1) El cliente se conecta enviando el JWT como query param (los WS no
   pueden usar el header Authorization de forma estándar desde el navegador).
2) El servidor valida el token, verifica que el usuario sea miembro del
   proyecto del diagrama y acepta la conexión.
3) El servidor emite `join` a los demás colaboradores.
4) El cliente envía mensajes (cursor_moved, class_created, etc.).
5) El servidor retransmite los mensajes a los demás colaboradores y,
   para los cambios reales, registra en `historial_cambios_diagrama`.
6) Al desconectarse, el servidor emite `leave` y limpia la conexión.

NO aplica cambios al modelo en BD: eso lo hace el cliente vía REST.
El WS solo retransmite y notifica cambios ya persistidos.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import select

from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.websocket.connection_manager import manager
from app.websocket.events import (
    EVENTO_A_CAMBIO,
    EVENTO_A_ENTIDAD,
    TIPOS_DE_CAMBIO,
    build_error,
    build_message,
    parse_message,
)

logger = logging.getLogger("devforge.ws")
router = APIRouter()


# ======================================================================
# Endpoint WS
# ======================================================================
@router.websocket("/ws/diagramas/{diagrama_id}")
async def collaboration_endpoint(
    websocket: WebSocket,
    diagrama_id: int,
    token: Optional[str] = Query(
        None, description="JWT de acceso del usuario (query param)"
    ),
):
    # ------------------------------------------------------------------
    # 0) Aceptar PRIMERO (antes de cualquier validación async)
    # ------------------------------------------------------------------
    await websocket.accept()
    # ------------------------------------------------------------------
    # 1) Validar token
    # ------------------------------------------------------------------
    if not token:
        await websocket.close(code=4401, reason="Token ausente")
        return

    usuario = await _autenticar_usuario(token)
    if usuario is None:
        await websocket.close(code=4401, reason="Token inválido o expirado")
        return

    # ------------------------------------------------------------------
    # 2) Verificar pertenencia al proyecto del diagrama
    # ------------------------------------------------------------------
    async with AsyncSessionLocal() as db:
        diagrama = await DiagramaRepository(db).get_by_id(diagrama_id)
        if diagrama is None:
            await websocket.close(code=4404, reason="Diagrama no encontrado")
            return

        miembro = await MiembroProyectoRepository(db).get_by_proyecto_usuario(
            diagrama.id_proyecto, usuario.id
        )
        if miembro is None:
            await websocket.close(code=4403, reason="Sin acceso al diagrama")
            return

        id_proyecto = diagrama.id_proyecto

    ##await websocket.accept()
    # ------------------------------------------------------------------
    # 3) Registrar conexión
    # ------------------------------------------------------------------
    id_conexion = await manager.connect(
        websocket,
        id_usuario=usuario.id,
        nombre_usuario=usuario.nombre_completo,
        id_diagrama=diagrama_id,
    )

    # Notificar entrada al resto
    await manager.broadcast(
        diagrama_id,
        build_message(
            "join",
            {"id_usuario": usuario.id, "nombre": usuario.nombre_completo},
            sender={"id": usuario.id, "nombre": usuario.nombre_completo},
        ),
        excluir_conexion=id_conexion,
    )

    # Snapshot inicial: lista de conectados al diagrama
    await manager.send_to_connection(
        id_conexion,
        build_message(
            "sync_snapshot",
            {
                "conectados": manager.usuarios_conectados(diagrama_id),
            },
        ),
    )

    # ------------------------------------------------------------------
    # 4) Bucle de mensajes
    # ------------------------------------------------------------------
    try:
        while True:
            raw = await websocket.receive_text()
            mensaje = parse_message(raw)

            if mensaje is None:
                await manager.send_to_connection(
                    id_conexion,
                    build_error("BAD_MESSAGE", "Mensaje inválido o mal formado"),
                )
                continue

            await _procesar_mensaje(
                mensaje=mensaje,
                id_conexion=id_conexion,
                id_diagrama=diagrama_id,
                id_proyecto=id_proyecto,
                usuario=usuario,
            )

    except WebSocketDisconnect:
        logger.info("WS desconectado por el cliente: usuario=%s", usuario.id)
    except Exception as exc:
        logger.exception("Error inesperado en WS: %s", exc)
    finally:
        # ------------------------------------------------------------------
        # 5) Limpieza
        # ------------------------------------------------------------------
        await manager.disconnect(diagrama_id, id_conexion)
        await manager.broadcast(
            diagrama_id,
            build_message(
                "leave",
                {"id_usuario": usuario.id, "nombre": usuario.nombre_completo},
                sender={"id": usuario.id, "nombre": usuario.nombre_completo},
            ),
        )


# ======================================================================
# Autenticación
# ======================================================================
async def _autenticar_usuario(token: str) -> Optional[Usuario]:
    try:
        payload = decode_token(token)
    except JWTError:
        return None

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        return None

    sub = payload.get("sub")
    if not sub:
        return None

    try:
        usuario_id = int(sub)
    except (TypeError, ValueError):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
        user = result.scalar_one_or_none()

    if user is None or not user.activo:
        return None
    return user


# ======================================================================
# Procesamiento de mensajes
# ======================================================================
async def _procesar_mensaje(
    *,
    mensaje,
    id_conexion: int,
    id_diagrama: int,
    id_proyecto: int,
    usuario: Usuario,
) -> None:
    tipo = mensaje.type
    payload = mensaje.payload or {}
    sender = {"id": usuario.id, "nombre": usuario.nombre_completo}

    # ------------------------------------------------------------------
    # Ping / pong (keepalive)
    # ------------------------------------------------------------------
    if tipo == "ping":
        await manager.send_to_connection(
            id_conexion, build_message("pong", {})
        )
        return

    # ------------------------------------------------------------------
    # Presencia (cursor, selección) — broadcast directo, no se persiste
    # ------------------------------------------------------------------
    if tipo in ("cursor_moved", "selection_changed"):
        await manager.broadcast(
            id_diagrama,
            build_message(tipo, payload, sender=sender),
            excluir_conexion=id_conexion,
        )
        return

    # ------------------------------------------------------------------
    # request_sync → responder con snapshot de conectados
    # ------------------------------------------------------------------
    if tipo == "request_sync":
        await manager.send_to_connection(
            id_conexion,
            build_message(
                "sync_snapshot",
                {"conectados": manager.usuarios_conectados(id_diagrama)},
            ),
        )
        return

    # ------------------------------------------------------------------
    # Cambios reales sobre el diagrama
    # ------------------------------------------------------------------
    if tipo in TIPOS_DE_CAMBIO:
        # 1) Retransmitir a los demás
        await manager.broadcast(
            id_diagrama,
            build_message(tipo, payload, sender=sender),
            excluir_conexion=id_conexion,
        )

        # 2) Registrar en historial (transacción corta y separada)
        await _registrar_cambio_en_historial(
            id_diagrama=id_diagrama,
            usuario_id=usuario.id,
            evento=tipo,
            payload=payload,
        )
        return

    # ------------------------------------------------------------------
    # Tipo desconocido
    # ------------------------------------------------------------------
    await manager.send_to_connection(
        id_conexion,
        build_error(
            "UNKNOWN_EVENT",
            f"Tipo de evento no soportado: '{tipo}'",
        ),
    )


# ======================================================================
# Registro en historial
# ======================================================================
async def _registrar_cambio_en_historial(
    *,
    id_diagrama: int,
    usuario_id: int,
    evento: str,
    payload: dict,
) -> None:
    """
    Inserta un registro en `historial_cambios_diagrama` para el cambio
    recibido por WS. Se hace en su propia transacción (independiente del
    request REST) para que el historial quede aunque el cliente caiga.
    """
    tipo_cambio = EVENTO_A_CAMBIO.get(evento)
    tipo_entidad = EVENTO_A_ENTIDAD.get(evento)
    if not tipo_cambio or not tipo_entidad:
        return

    # id_entidad: lo sacamos del payload según convención
    id_entidad = _extraer_id_entidad(evento, payload)
    if id_entidad is None:
        # Sin id_entidad no podemos registrar (la columna es NOT NULL)
        return

    # Import local para evitar cargar estos módulos si el WS no se usa
    from app.models.trazabilidad import HistorialCambioDiagrama
    from app.repositories.trazabilidad_repository import HistorialCambioRepository

    try:
        async with AsyncSessionLocal() as db:
            repo = HistorialCambioRepository(db)
            await repo.create(
                HistorialCambioDiagrama(
                    id_diagrama=id_diagrama,
                    id_usuario=usuario_id,
                    tipo_cambio=tipo_cambio,
                    tipo_entidad=tipo_entidad,
                    id_entidad=id_entidad,
                    datos_cambio=payload,
                )
            )
            await db.commit()
    except Exception as exc:
        # No romper el WS si falla el registro de historial
        logger.warning("No se pudo registrar cambio en historial: %s", exc)


def _extraer_id_entidad(evento: str, payload: dict) -> Optional[int]:
    """
    Saca el id de la entidad afectada del payload según el tipo de evento.
    Convención: cada payload trae el id del elemento como `id` o `id_clase`
    o `id_atributo`, etc.
    """
    claves = [
        "id",
        "id_clase",
        "id_atributo",
        "id_operacion",
        "id_relacion",
        "id_interfaz",
    ]
    for k in claves:
        if k in payload:
            try:
                return int(payload[k])
            except (TypeError, ValueError):
                continue
    return None