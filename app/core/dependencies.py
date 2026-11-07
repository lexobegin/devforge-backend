# app/core/dependencies.py
"""
Dependencias comunes de FastAPI para DevForge AI — CICLO 2.

RECONVERTIDO del Ciclo 1 (mismo contrato):
- get_current_user            → usuario autenticado (a partir del JWT)
- get_current_active_user     → igual, pero exige que la cuenta esté activa
- require_admin               → exige rol ADMIN (usuarios.rol)
- require_project_role(...)   → fábrica: exige pertenencia a un proyecto
                                con rol mínimo (PROPIETARIO > EDITOR > LECTOR)

Cambios del Ciclo 2:
- SIN AsyncSession ni select(): el usuario se resuelve con Usuario.get()
  (Beanie) y el miembro con MiembroProyectoRepository (repositorio sin
  estado de la Tanda 9; la conexión la lleva Beanie).
- El `sub` del JWT ya es el ObjectId en hex (str(usuario.id)); el
  PydanticObjectId(sub) inválido se trata como token inválido (401).
- Las HTTPException a mano se sustituyen por las excepciones de dominio
  del módulo C (UnauthorizedError/ForbiddenError), que
  register_exception_handlers traduce a la respuesta JSON uniforme; el
  401 conserva el header WWW-Authenticate: Bearer.
- bearer_scheme y ROL_PROYECTO_JERARQUIA se conservan del Ciclo 1.
"""

from typing import Optional

from beanie import PydanticObjectId
from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.models.usuario import Usuario
from app.repositories.proyecto_repository import MiembroProyectoRepository


# ----------------------------------------------------------------------
# Esquema Bearer (para que Swagger muestre el candado)
# ----------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=False)


# ----------------------------------------------------------------------
# Jerarquía de roles dentro de un proyecto
# ----------------------------------------------------------------------
ROL_PROYECTO_JERARQUIA = {
    "LECTOR": 1,
    "EDITOR": 2,
    "PROPIETARIO": 3,
}


# ----------------------------------------------------------------------
# Usuario autenticado
# ----------------------------------------------------------------------
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Usuario:
    """
    Extrae el JWT del header Authorization: Bearer <token>,
    lo valida, y devuelve el Usuario correspondiente.
    """
    unauthorized = UnauthorizedError("Credenciales inválidas o token ausente")

    if credentials is None or not credentials.credentials:
        raise unauthorized

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise unauthorized

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise unauthorized

    sub = payload.get("sub")
    if not sub:
        raise unauthorized

    # Ciclo 1: user_id = int(sub). Ciclo 2: el sub es el ObjectId en hex;
    # un sub malformado NO es un 500: es un token inválido (401).
    try:
        usuario_id = PydanticObjectId(sub)
    except (TypeError, ValueError):
        raise unauthorized

    user = await Usuario.get(usuario_id)

    if user is None:
        raise unauthorized

    return user


async def get_current_active_user(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    """Igual que get_current_user, pero exige que la cuenta esté activa."""
    if not current_user.activo:
        raise ForbiddenError("La cuenta de usuario está desactivada")
    return current_user


# ----------------------------------------------------------------------
# Rol global (usuarios.rol)
# ----------------------------------------------------------------------
async def require_admin(
    current_user: Usuario = Depends(get_current_active_user),
) -> Usuario:
    """Exige que el usuario tenga rol global ADMIN."""
    if not current_user.is_admin:
        raise ForbiddenError(
            "Se requiere rol de Administrador de la plataforma"
        )
    return current_user


# ----------------------------------------------------------------------
# Rol dentro de un proyecto (miembros_proyecto.rol_en_proyecto)
# ----------------------------------------------------------------------
def require_project_role(min_role: str):
    """
    Fábrica de dependencias. Devuelve una dependencia que:
    1) Recibe el id del proyecto desde el path como `proyecto_id`.
    2) Verifica que el usuario sea miembro con al menos `min_role`.

    Uso:
        @router.get("/proyectos/{proyecto_id}/diagramas",
                    dependencies=[Depends(require_project_role("EDITOR"))])
        async def listar(...): ...
    """
    if min_role not in ROL_PROYECTO_JERARQUIA:
        raise ValueError(f"Rol inválido: {min_role}")

    async def _dependency(
        proyecto_id: PydanticObjectId = Path(..., description="ID del proyecto"),
        current_user: Usuario = Depends(get_current_active_user),
    ):
        # Repositorio SIN ESTADO: la conexión la lleva Beanie (Tanda 9).
        miembro = await MiembroProyectoRepository().get_by_proyecto_usuario(
            proyecto_id, current_user.id
        )

        if miembro is None:
            raise ForbiddenError("No pertenece a este proyecto")

        if (
            ROL_PROYECTO_JERARQUIA[miembro.rol_en_proyecto]
            < ROL_PROYECTO_JERARQUIA[min_role]
        ):
            raise ForbiddenError(
                f"Se requiere rol {min_role} o superior en el proyecto"
            )

        return miembro

    return _dependency