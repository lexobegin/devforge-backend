# app/api/v1/proyectos_router.py
"""
Endpoints de gestión de proyectos y miembros (módulo B):

Proyectos:
- GET    /api/v1/proyectos                     → listar los del usuario
- POST   /api/v1/proyectos                     → crear
- GET    /api/v1/proyectos/{id}                → obtener (con o sin miembros)
- PUT    /api/v1/proyectos/{id}                → actualizar
- POST   /api/v1/proyectos/{id}/archivar       → archivar
- POST   /api/v1/proyectos/{id}/reactivar      → reactivar
- DELETE /api/v1/proyectos/{id}                → eliminar (solo PROPIETARIO)

Miembros:
- GET    /api/v1/proyectos/{id}/miembros                    → listar
- POST   /api/v1/proyectos/{id}/miembros                    → agregar
- PUT    /api/v1/proyectos/{id}/miembros/{miembro_id}       → cambiar rol
- DELETE /api/v1/proyectos/{id}/miembros/{miembro_id}       → quitar
- POST   /api/v1/proyectos/{id}/transferir-propiedad        → transferir
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_admin
from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.proyecto_schema import (
    MiembroProyectoCreate,
    MiembroProyectoResponse,
    MiembroProyectoUpdate,
    ProyectoConMiembrosResponse,
    ProyectoCreate,
    ProyectoResponse,
    ProyectoUpdate,
)
from app.services.auditoria_service import AuditoriaService
from app.services.proyecto_service import ProyectoService

router = APIRouter()


# ======================================================================
# PROYECTOS — listar y crear
# ======================================================================
@router.get(
    "",
    response_model=dict,
    summary="Listar proyectos del usuario",
    description=(
        "Devuelve los proyectos en los que el usuario es propietario o miembro. "
        "Un ADMIN puede pasar `todos=true` para ver todos los proyectos de la plataforma."
    ),
)
async def listar_proyectos(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    incluir_archivados: bool = Query(False),
    todos: bool = Query(False, description="Solo ADMIN: listar todos"),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ProyectoService(db)

    if todos and current_user.is_admin:
        items, total = await service.listar_todos(
            skip=skip, limit=limit, incluir_archivados=incluir_archivados
        )
    else:
        items, total = await service.listar_para_usuario(
            current_user.id,
            skip=skip,
            limit=limit,
            incluir_archivados=incluir_archivados,
        )

    return {
        "items": [i.model_dump() for i in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post(
    "",
    response_model=ProyectoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear proyecto",
    description="El creador queda automáticamente como PROPIETARIO del proyecto.",
)
async def crear_proyecto(
    datos: ProyectoCreate,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProyectoResponse:
    service = ProyectoService(db)
    proyecto = await service.crear(datos, usuario_id=current_user.id)

    auditoria = AuditoriaService(db)
    await auditoria.log_proyecto_creado(
        proyecto.id, current_user.id, proyecto.nombre, commit=True
    )

    return proyecto


# ======================================================================
# PROYECTOS — operaciones por id
# ======================================================================
@router.get(
    "/{proyecto_id}",
    response_model=ProyectoConMiembrosResponse,
    summary="Obtener proyecto (con miembros)",
    description="Incluye la lista de miembros del proyecto.",
)
async def obtener_proyecto(
    proyecto_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProyectoService(db)
    return await service.obtener(
        proyecto_id,
        usuario_id=current_user.id,
        es_admin=current_user.is_admin,
        con_miembros=True,
    )


@router.put(
    "/{proyecto_id}",
    response_model=ProyectoResponse,
    summary="Actualizar proyecto",
    description=(
        "PROPIETARIO o EDITOR pueden cambiar nombre/descripción. "
        "Solo el PROPIETARIO puede cambiar el estado (archivar/reactivar)."
    ),
)
async def actualizar_proyecto(
    proyecto_id: int,
    datos: ProyectoUpdate,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProyectoResponse:
    service = ProyectoService(db)
    return await service.actualizar(
        proyecto_id, datos, usuario_id=current_user.id
    )


@router.post(
    "/{proyecto_id}/archivar",
    response_model=ProyectoResponse,
    summary="Archivar proyecto (solo PROPIETARIO)",
)
async def archivar_proyecto(
    proyecto_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProyectoResponse:
    service = ProyectoService(db)
    return await service.archivar(proyecto_id, usuario_id=current_user.id)


@router.post(
    "/{proyecto_id}/reactivar",
    response_model=ProyectoResponse,
    summary="Reactivar proyecto (solo PROPIETARIO)",
)
async def reactivar_proyecto(
    proyecto_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProyectoResponse:
    service = ProyectoService(db)
    return await service.reactivar(proyecto_id, usuario_id=current_user.id)


@router.delete(
    "/{proyecto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar proyecto (solo PROPIETARIO)",
    description="Eliminación física en cascada de miembros, diagramas y datos asociados.",
)
async def eliminar_proyecto(
    proyecto_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ProyectoService(db)
    await service.eliminar(proyecto_id, usuario_id=current_user.id)


# ======================================================================
# MIEMBROS
# ======================================================================
@router.get(
    "/{proyecto_id}/miembros",
    response_model=list[MiembroProyectoResponse],
    summary="Listar miembros del proyecto",
)
async def listar_miembros(
    proyecto_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProyectoService(db)
    return await service.listar_miembros(proyecto_id, usuario_id=current_user.id)


@router.post(
    "/{proyecto_id}/miembros",
    response_model=MiembroProyectoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar miembro (solo PROPIETARIO)",
    description=(
        "No se puede agregar un segundo PROPIETARIO por esta vía. "
        "Use `transferir-propiedad` para eso."
    ),
)
async def agregar_miembro(
    proyecto_id: int,
    datos: MiembroProyectoCreate,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MiembroProyectoResponse:
    service = ProyectoService(db)
    return await service.agregar_miembro(
        proyecto_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/{proyecto_id}/miembros/{miembro_id}",
    response_model=MiembroProyectoResponse,
    summary="Cambiar rol de un miembro (solo PROPIETARIO)",
)
async def cambiar_rol_miembro(
    proyecto_id: int,
    miembro_id: int,
    datos: MiembroProyectoUpdate,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MiembroProyectoResponse:
    service = ProyectoService(db)
    return await service.cambiar_rol_miembro(
        proyecto_id, miembro_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/{proyecto_id}/miembros/{miembro_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar miembro",
    description=(
        "El PROPIETARIO puede quitar a cualquier miembro (excepto a sí mismo). "
        "Un miembro también puede quitarse a sí mismo (salirse del proyecto)."
    ),
)
async def quitar_miembro(
    proyecto_id: int,
    miembro_id: int,
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ProyectoService(db)
    await service.quitar_miembro(
        proyecto_id, miembro_id, usuario_id=current_user.id
    )


@router.post(
    "/{proyecto_id}/transferir-propiedad",
    response_model=MiembroProyectoResponse,
    summary="Transferir propiedad del proyecto (solo PROPIETARIO actual)",
    description=(
        "El PROPIETARIO actual pasa a EDITOR y el nuevo usuario pasa a "
        "PROPIETARIO. El nuevo propietario debe ser ya miembro del proyecto."
    ),
)
async def transferir_propiedad(
    proyecto_id: int,
    nuevo_propietario_id: int = Query(..., gt=0),
    current_user: Usuario = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MiembroProyectoResponse:
    service = ProyectoService(db)
    return await service.transferir_propiedad(
        proyecto_id, nuevo_propietario_id, usuario_id=current_user.id
    )