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

Migrado del Ciclo 1 (SQLAlchemy/AsyncSessionLocal → Beanie/MongoDB):
- diagrama_id de la ruta es STR (ObjectId en hex): se convierte a
  PydanticObjectId antes de consultar; un id malformado NO revienta
  (500): cierra con 4404, igual que un diagrama inexistente.
- _autenticar_usuario replica el patrón de core/dependencies.py (T19):
  decode_token → type == "access" → PydanticObjectId(sub) con
  try/except (el sub malformado es un token inválido, no un crash) →
  Usuario.get() de Beanie. Sin `select()` ni AsyncSessionLocal.
  NOTA DE REVISIÓN (arnés 19b): bson.errors.InvalidId NO es ValueError
  en pymongo ≥ 4.x (hereda de BSONError), así que las cláusulas
  incluyen InvalidId explícito — también corregido en dependencies.py,
  auth_service.py y sincronizacion_service.py.
- La membresía se consulta con MiembroProyectoRepository (repositorio
  SIN estado de la Tanda 9): get_by_proyecto_usuario(diagrama.id_proyecto,
  usuario.id). La conexión la lleva Beanie.
- El id del usuario en el manager y en los mensajes es str(usuario.id)
  (ObjectId hex): send_json usa json.dumps y no serializa ObjectId.
- El registro en historial usa HistorialCambioRepository().create()
  (insert autónomo de Beanie, SIN commit — regla de la Tanda 19) con
  ids PydanticObjectId, id_entidad str uuid (elementos EMBEBIDOS del
  Diagrama) y datos_cambio = payload del evento. Se conserva la política
  del Ciclo 1: si el registro falla el WS NO se rompe (solo se loguea),
  y sin id_entidad en el payload no se registra nada.
- Códigos de cierre intactos: 4401 (token), 4403 (sin acceso),
  4404 (diagrama).
"""

import logging
from typing import Optional

from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.security import TOKEN_TYPE_ACCESS, decode_token
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
    diagrama_id: str,
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
    #    (Ciclo 1: bloque async with AsyncSessionLocal con select(). Ciclo
    #    2: repositorios sin estado; el id malformado cierra 4404.)
    # ------------------------------------------------------------------
    try:
        diagrama_oid = PydanticObjectId(diagrama_id)
    except (TypeError, ValueError, InvalidId):
        await websocket.close(code=4404, reason="Diagrama no encontrado")
        return

    diagrama = await DiagramaRepository().get_by_id(diagrama_oid)
    if diagrama is None:
        await websocket.close(code=4404, reason="Diagrama no encontrado")
        return

    miembro = await MiembroProyectoRepository().get_by_proyecto_usuario(
        diagrama.id_proyecto, usuario.id
    )
    if miembro is None:
        await websocket.close(code=4403, reason="Sin acceso al diagrama")
        return

    id_proyecto = str(diagrama.id_proyecto)

    # ------------------------------------------------------------------
    # 3) Registrar conexión
    #    (Ids como str: send_json no serializa ObjectId.)
    # ------------------------------------------------------------------
    id_usuario_str = str(usuario.id)
    nombre_usuario = usuario.nombre_completo

    id_conexion = await manager.connect(
        websocket,
        id_usuario=id_usuario_str,
        nombre_usuario=nombre_usuario,
        id_diagrama=diagrama_id,
    )

    # Notificar entrada al resto
    await manager.broadcast(
        diagrama_id,
        build_message(
            "join",
            {"id_usuario": id_usuario_str, "nombre": nombre_usuario},
            sender={"id": id_usuario_str, "nombre": nombre_usuario},
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
        logger.info("WS desconectado por el cliente: usuario=%s", id_usuario_str)
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
                {"id_usuario": id_usuario_str, "nombre": nombre_usuario},
                sender={"id": id_usuario_str, "nombre": nombre_usuario},
            ),
        )


# ======================================================================
# Autenticación
# ======================================================================
async def _autenticar_usuario(token: str) -> Optional[Usuario]:
    """
    Ciclo 1: sub = int(id) + select(Usuario). Ciclo 2: el sub del JWT es
    el ObjectId en hex; un sub malformado es un token inválido (mismo
    patrón que core/dependencies.py) y el usuario se resuelve con
    Usuario.get() de Beanie.
    """
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
        usuario_id = PydanticObjectId(sub)
    except (TypeError, ValueError, InvalidId):
        return None

    usuario = await Usuario.get(usuario_id)

    if usuario is None or not usuario.activo:
        return None
    return usuario


# ======================================================================
# Procesamiento de mensajes
# ======================================================================
async def _procesar_mensaje(
    *,
    mensaje,
    id_conexion: int,
    id_diagrama: str,
    id_proyecto: str,
    usuario: Usuario,
) -> None:
    tipo = mensaje.type
    payload = mensaje.payload or {}
    sender = {
        "id": str(usuario.id),
        "nombre": usuario.nombre_completo,
    }

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

        # 2) Registrar en historial (insert autónomo, independiente del
        #    request REST que persistió el cambio)
        await _registrar_cambio_en_historial(
            id_diagrama=id_diagrama,
            usuario_id=str(usuario.id),
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
    id_diagrama: str,
    usuario_id: str,
    evento: str,
    payload: dict,
) -> None:
    """
    Inserta un registro en `historial_cambios_diagrama` para el cambio
    recibido por WS. Se hace en su propia transacción lógica (insert
    autónomo de Beanie, SIN commit — regla de la Tanda 19) para que el
    historial quede aunque el cliente caiga.

    Ciclo 2: id_diagrama/id_usuario van como PydanticObjectId y
    id_entidad es el uuid str del elemento EMBEBIDO del Diagrama.
    """
    tipo_cambio = EVENTO_A_CAMBIO.get(evento)
    tipo_entidad = EVENTO_A_ENTIDAD.get(evento)
    if not tipo_cambio or not tipo_entidad:
        return

    # id_entidad: lo sacamos del payload según convención
    id_entidad = _extraer_id_entidad(evento, payload)
    if id_entidad is None:
        # Sin id_entidad no podemos registrar (el campo es obligatorio)
        return

    # Import local para evitar cargar estos módulos si el WS no se usa
    from app.models.trazabilidad import HistorialCambioDiagrama
    from app.repositories.trazabilidad_repository import HistorialCambioRepository

    try:
        await HistorialCambioRepository().create(
            HistorialCambioDiagrama(
                id_diagrama=PydanticObjectId(id_diagrama),
                id_usuario=PydanticObjectId(usuario_id),
                tipo_cambio=tipo_cambio,
                tipo_entidad=tipo_entidad,
                id_entidad=id_entidad,
                datos_cambio=payload,
            )
        )
    except Exception as exc:
        # No romper el WS si falla el registro de historial
        logger.warning("No se pudo registrar cambio en historial: %s", exc)


def _extraer_id_entidad(evento: str, payload: dict) -> Optional[str]:
    """
    Saca el id de la entidad afectada del payload según el tipo de evento.
    Convención: cada payload trae el id del elemento como `id` o `id_clase`
    o `id_atributo`, etc. En el Ciclo 2 son uuid str (ids de elementos
    EMBEBIDOS del Diagrama): ya no se convierte a int.
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
        if k in payload and payload[k] is not None:
            valor = str(payload[k]).strip()
            if valor:
                return valor
    return None