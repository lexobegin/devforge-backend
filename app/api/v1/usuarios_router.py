# app/api/v1/usuarios_router.py
"""
Endpoints de gestión de usuarios (módulo A. Usuarios y Seguridad) — CICLO 2.

- GET    /api/v1/usuarios              → listar (solo ADMIN)
- POST   /api/v1/usuarios              → crear (solo ADMIN)
- GET    /api/v1/usuarios/{id}         → obtener (ADMIN o el propio usuario)
- PUT    /api/v1/usuarios/{id}         → actualizar (ADMIN o el propio usuario)
- POST   /api/v1/usuarios/{id}/activar → reactivar cuenta (solo ADMIN)
- POST   /api/v1/usuarios/{id}/desactivar → desactivar cuenta (solo ADMIN)
- DELETE /api/v1/usuarios/{id}         → eliminar físicamente (solo ADMIN)

Reglas aplicadas desde el servicio:
- Un usuario normal solo puede editar su propio perfil y NO puede cambiar
  `rol` ni `activo`.
- Un ADMIN no puede desactivarse ni eliminarse a sí mismo.

CICLO 2 (reconvertido del Ciclo 1): SIN AsyncSession; ids de ruta
PydanticObjectId; la defensa 403 del GET usa ForbiddenError (el manejador
de app/core/exceptions.py la traduce con el mismo JSON uniforme).
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_current_active_user, require_admin
from app.core.exceptions import ForbiddenError
from app.models.usuario import Usuario
from app.schemas.usuario_schema import (
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)
from app.services.usuario_service import UsuarioService

router = APIRouter()


# ======================================================================
# GET / — Listar usuarios (solo ADMIN)
# ======================================================================
@router.get(
    "",
    response_model=dict,
    summary="Listar usuarios (solo ADMIN)",
    description="Devuelve una página de usuarios con metadatos de paginación.",
)
async def listar_usuarios(
    skip: int = Query(0, ge=0, description="Registros a saltar"),
    limit: int = Query(50, ge=1, le=200, description="Máx. registros por página"),
    solo_activos: bool = Query(False, description="Filtrar solo usuarios activos"),
    _admin: Usuario = Depends(require_admin),
) -> dict:
    service = UsuarioService()
    items, total = await service.listar(
        skip=skip, limit=limit, solo_activos=solo_activos
    )
    return {
        "items": [i.model_dump() for i in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ======================================================================
# POST / — Crear usuario (solo ADMIN)
# ======================================================================
@router.post(
    "",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario (solo ADMIN)",
    description="El administrador puede crear cuentas indicando el rol explícito.",
)
async def crear_usuario(
    datos: UsuarioCreate,
    _admin: Usuario = Depends(require_admin),
) -> UsuarioResponse:
    service = UsuarioService()
    return await service.crear(datos)


# ======================================================================
# GET /{usuario_id} — Obtener (ADMIN o el propio usuario)
# ======================================================================
@router.get(
    "/{usuario_id}",
    response_model=UsuarioResponse,
    summary="Obtener usuario",
    description=(
        "Un ADMIN puede consultar cualquier usuario. "
        "Un usuario normal solo puede consultarse a sí mismo."
    ),
)
async def obtener_usuario(
    usuario_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> UsuarioResponse:
    # Defensa previa a nivel router: si no es admin ni es él mismo → 403
    if not current_user.is_admin and current_user.id != usuario_id:
        raise ForbiddenError("No puede consultar el perfil de otro usuario")

    service = UsuarioService()
    return await service.obtener(usuario_id)


# ======================================================================
# PUT /{usuario_id} — Actualizar (ADMIN o el propio usuario)
# ======================================================================
@router.put(
    "/{usuario_id}",
    response_model=UsuarioResponse,
    summary="Actualizar usuario",
    description=(
        "Un ADMIN puede actualizar cualquier campo (incluido rol y activo). "
        "Un usuario normal solo puede actualizar su propio perfil y NO los "
        "campos sensibles (rol/activo)."
    ),
)
async def actualizar_usuario(
    usuario_id: PydanticObjectId,
    datos: UsuarioUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> UsuarioResponse:
    service = UsuarioService()
    return await service.actualizar(
        usuario_id,
        datos,
        es_admin=current_user.is_admin,
        current_user_id=current_user.id,
    )


# ======================================================================
# POST /{usuario_id}/activar — Reactivar (solo ADMIN)
# ======================================================================
@router.post(
    "/{usuario_id}/activar",
    response_model=UsuarioResponse,
    summary="Activar usuario (solo ADMIN)",
)
async def activar_usuario(
    usuario_id: PydanticObjectId,
    _admin: Usuario = Depends(require_admin),
) -> UsuarioResponse:
    service = UsuarioService()
    return await service.activar(usuario_id)


# ======================================================================
# POST /{usuario_id}/desactivar — Desactivar (solo ADMIN)
# ======================================================================
@router.post(
    "/{usuario_id}/desactivar",
    response_model=UsuarioResponse,
    summary="Desactivar usuario (solo ADMIN)",
    description="Soft-disable: no borra datos, solo marca `activo=False`.",
)
async def desactivar_usuario(
    usuario_id: PydanticObjectId,
    current_user: Usuario = Depends(require_admin),
) -> UsuarioResponse:
    service = UsuarioService()
    return await service.desactivar(
        usuario_id, current_user_id=current_user.id
    )


# ======================================================================
# DELETE /{usuario_id} — Eliminar físicamente (solo ADMIN)
# ======================================================================
@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar usuario (solo ADMIN)",
    description=(
        "Eliminación física. Uso excepcional: puede fallar si quedan "
        "referencias (proyectos, diagramas…). En operación normal use "
        "`desactivar`."
    ),
)
async def eliminar_usuario(
    usuario_id: PydanticObjectId,
    _admin: Usuario = Depends(require_admin),
) -> None:
    service = UsuarioService()
    await service.eliminar(usuario_id)