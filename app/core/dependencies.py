# app/core/dependencies.py
"""
Dependencias comunes de FastAPI para DevForge AI:

- get_current_user            → usuario autenticado (a partir del JWT)
- get_current_active_user     → igual, pero exige que la cuenta esté activa
- require_admin               → exige rol ADMIN (usuarios.rol)
- require_project_member(...) → exige pertenencia a un proyecto con rol mínimo
                                (PROPIETARIO > EDITOR > LECTOR)
"""

from typing import Optional

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.database import get_db
from app.models.usuario import Usuario


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
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """
    Extrae el JWT del header Authorization: Bearer <token>,
    lo valida, y devuelve el Usuario correspondiente.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token ausente",
        headers={"WWW-Authenticate": "Bearer"},
    )

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

    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise unauthorized

    result = await db.execute(select(Usuario).where(Usuario.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise unauthorized

    return user


async def get_current_active_user(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    """Igual que get_current_user, pero exige que la cuenta esté activa."""
    if not current_user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario está desactivada",
        )
    return current_user


# ----------------------------------------------------------------------
# Rol global (usuarios.rol)
# ----------------------------------------------------------------------
async def require_admin(
    current_user: Usuario = Depends(get_current_active_user),
) -> Usuario:
    """Exige que el usuario tenga rol global ADMIN."""
    if current_user.rol != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de Administrador de la plataforma",
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
        proyecto_id: int = Path(..., description="ID del proyecto"),
        current_user: Usuario = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        # Import local para evitar ciclos con models.proyecto
        from app.models.proyecto import MiembroProyecto

        result = await db.execute(
            select(MiembroProyecto).where(
                MiembroProyecto.id_proyecto == proyecto_id,
                MiembroProyecto.id_usuario == current_user.id,
            )
        )
        miembro = result.scalar_one_or_none()

        if miembro is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No pertenece a este proyecto",
            )

        if ROL_PROYECTO_JERARQUIA[miembro.rol_en_proyecto] < ROL_PROYECTO_JERARQUIA[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol {min_role} o superior en el proyecto",
            )

        return miembro

    return _dependency