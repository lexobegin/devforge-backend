# app/api/v1/diagramas_router.py
"""
Endpoints del módulo C. Modelado UML (Diagrama de Clases) — CICLO 2.

Diagramas:
- GET    /api/v1/diagramas/proyecto/{proyecto_id}   → listar por proyecto
- POST   /api/v1/diagramas/proyecto/{proyecto_id}   → crear
- GET    /api/v1/diagramas/{id}                     → obtener (básico)
- GET    /api/v1/diagramas/{id}/completo            → obtener con todo el contenido
- PUT    /api/v1/diagramas/{id}                     → actualizar
- DELETE /api/v1/diagramas/{id}                     → eliminar

Clases:
- GET    /api/v1/diagramas/{id}/clases              → listar clases
- POST   /api/v1/diagramas/{id}/clases              → crear clase
- GET    /api/v1/diagramas/clases/{clase_id}        → obtener clase
- PUT    /api/v1/diagramas/clases/{clase_id}        → actualizar clase
- DELETE /api/v1/diagramas/clases/{clase_id}        → eliminar clase

Atributos, operaciones y parámetros:
- POST   /api/v1/diagramas/clases/{clase_id}/atributos
- GET    /api/v1/diagramas/clases/{clase_id}/atributos
- PUT    /api/v1/diagramas/atributos/{atributo_id}
- DELETE /api/v1/diagramas/atributos/{atributo_id}
- POST   /api/v1/diagramas/clases/{clase_id}/operaciones
- GET    /api/v1/diagramas/clases/{clase_id}/operaciones
- PUT    /api/v1/diagramas/operaciones/{operacion_id}
- DELETE /api/v1/diagramas/operaciones/{operacion_id}
- POST   /api/v1/diagramas/operaciones/{operacion_id}/parametros
- PUT    /api/v1/diagramas/parametros/{parametro_id}
- DELETE /api/v1/diagramas/parametros/{parametro_id}

Interfaces:
- POST   /api/v1/diagramas/{id}/interfaces
- PUT    /api/v1/diagramas/interfaces/{interfaz_id}
- DELETE /api/v1/diagramas/interfaces/{interfaz_id}
- POST   /api/v1/diagramas/interfaces/{interfaz_id}/operaciones
- PUT    /api/v1/diagramas/operaciones-interfaz/{op_id}
- DELETE /api/v1/diagramas/operaciones-interfaz/{op_id}

Relaciones:
- GET    /api/v1/diagramas/{id}/relaciones
- POST   /api/v1/diagramas/{id}/relaciones
- PUT    /api/v1/diagramas/relaciones/{relacion_id}
- DELETE /api/v1/diagramas/relaciones/{relacion_id}

CICLO 2 (reconvertido del Ciclo 1): SIN AsyncSession (el DiagramaService
de la Tanda 9 trabaja sobre los EMBEBIDOS del documento Diagrama con el
patrón fetch → modificar → save del PADRE); ids de diagrama
PydanticObjectId; los ids de clase/atributo/operación/parámetro/interfaz/
relación son el uuid str del elemento embebido (igual que el Ciclo 1
usaba ints de tabla propia, aquí cambian a uuid str). Los errores de
dominio del service (NotFoundError/ValidationError/ForbiddenError/
ConflictError) los traduce el manejador de app/core/exceptions.py.
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_active_user
from app.models.usuario import Usuario
from app.schemas.diagrama_schema import (
    AtributoUMLCreate,
    AtributoUMLResponse,
    AtributoUMLUpdate,
    ClaseUMLCreate,
    ClaseUMLResponse,
    ClaseUMLUpdate,
    DiagramaCompletoResponse,
    DiagramaCreate,
    DiagramaResponse,
    DiagramaUpdate,
    InterfazUMLCreate,
    InterfazUMLResponse,
    InterfazUMLUpdate,
    OperacionInterfazUMLCreate,
    OperacionInterfazUMLResponse,
    OperacionInterfazUMLUpdate,
    OperacionUMLCreate,
    OperacionUMLResponse,
    OperacionUMLUpdate,
    ParametroOperacionUMLCreate,
    ParametroOperacionUMLResponse,
    ParametroOperacionUMLUpdate,
    RelacionUMLCreate,
    RelacionUMLResponse,
    RelacionUMLUpdate,
)
from app.services.diagrama_service import DiagramaService

router = APIRouter()


# ======================================================================
# DIAGRAMAS
# ======================================================================
@router.get(
    "/proyecto/{proyecto_id}",
    response_model=list[DiagramaResponse],
    summary="Listar diagramas de un proyecto",
)
async def listar_diagramas(
    proyecto_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = DiagramaService()
    return await service.listar_por_proyecto(
        proyecto_id, usuario_id=current_user.id
    )


@router.post(
    "/proyecto/{proyecto_id}",
    response_model=DiagramaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear diagrama en un proyecto",
)
async def crear_diagrama(
    proyecto_id: PydanticObjectId,
    datos: DiagramaCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> DiagramaResponse:
    service = DiagramaService()
    return await service.crear(
        proyecto_id, datos, usuario_id=current_user.id
    )


@router.get(
    "/{diagrama_id}",
    response_model=DiagramaResponse,
    summary="Obtener diagrama (metadata)",
)
async def obtener_diagrama(
    diagrama_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> DiagramaResponse:
    service = DiagramaService()
    return await service.obtener(diagrama_id, usuario_id=current_user.id)


@router.get(
    "/{diagrama_id}/completo",
    response_model=DiagramaCompletoResponse,
    summary="Obtener diagrama con TODO su contenido",
    description=(
        "Devuelve el diagrama con clases (y sus atributos/operaciones/parámetros), "
        "interfaces (y sus operaciones) y relaciones. Payload que consume el editor."
    ),
)
async def obtener_diagrama_completo(
    diagrama_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> DiagramaCompletoResponse:
    service = DiagramaService()
    return await service.obtener_completo(
        diagrama_id, usuario_id=current_user.id
    )


@router.put(
    "/{diagrama_id}",
    response_model=DiagramaResponse,
    summary="Actualizar metadata del diagrama",
)
async def actualizar_diagrama(
    diagrama_id: PydanticObjectId,
    datos: DiagramaUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> DiagramaResponse:
    service = DiagramaService()
    return await service.actualizar(
        diagrama_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/{diagrama_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar diagrama (y todo su contenido en cascada)",
)
async def eliminar_diagrama(
    diagrama_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar(diagrama_id, usuario_id=current_user.id)


# ======================================================================
# CLASES UML
# ======================================================================
@router.get(
    "/{diagrama_id}/clases",
    response_model=list[ClaseUMLResponse],
    summary="Listar clases del diagrama",
)
async def listar_clases(
    diagrama_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = DiagramaService()
    return await service.listar_clases(diagrama_id, usuario_id=current_user.id)


@router.post(
    "/{diagrama_id}/clases",
    response_model=ClaseUMLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear clase en el diagrama",
    description=(
        "Permite crear la clase con atributos y operaciones anidados en "
        "una sola llamada. El nombre debe ser único en el diagrama."
    ),
)
async def crear_clase(
    diagrama_id: PydanticObjectId,
    datos: ClaseUMLCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> ClaseUMLResponse:
    service = DiagramaService()
    return await service.crear_clase(
        diagrama_id, datos, usuario_id=current_user.id
    )


# OJO: ruta estática ANTES de las dinámicas para evitar colisiones
@router.get(
    "/clases/{clase_id}",
    response_model=ClaseUMLResponse,
    summary="Obtener clase con atributos y operaciones",
)
async def obtener_clase(
    clase_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> ClaseUMLResponse:
    service = DiagramaService()
    return await service.obtener_clase(clase_id, usuario_id=current_user.id)


@router.put(
    "/clases/{clase_id}",
    response_model=ClaseUMLResponse,
    summary="Actualizar clase",
)
async def actualizar_clase(
    clase_id: str,
    datos: ClaseUMLUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> ClaseUMLResponse:
    service = DiagramaService()
    return await service.actualizar_clase(
        clase_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/clases/{clase_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar clase (y relaciones asociadas)",
)
async def eliminar_clase(
    clase_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar_clase(clase_id, usuario_id=current_user.id)


# ======================================================================
# ATRIBUTOS
# ======================================================================
@router.get(
    "/clases/{clase_id}/atributos",
    response_model=list[AtributoUMLResponse],
    summary="Listar atributos de una clase",
)
async def listar_atributos(
    clase_id: str,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = DiagramaService()
    return await service.listar_atributos(clase_id, usuario_id=current_user.id)


@router.post(
    "/clases/{clase_id}/atributos",
    response_model=AtributoUMLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar atributo a una clase",
)
async def agregar_atributo(
    clase_id: str,
    datos: AtributoUMLCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> AtributoUMLResponse:
    service = DiagramaService()
    return await service.agregar_atributo(
        clase_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/atributos/{atributo_id}",
    response_model=AtributoUMLResponse,
    summary="Actualizar atributo",
)
async def actualizar_atributo(
    atributo_id: str,
    datos: AtributoUMLUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> AtributoUMLResponse:
    service = DiagramaService()
    return await service.actualizar_atributo(
        atributo_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/atributos/{atributo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar atributo",
)
async def eliminar_atributo(
    atributo_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar_atributo(atributo_id, usuario_id=current_user.id)


# ======================================================================
# OPERACIONES
# ======================================================================
@router.get(
    "/clases/{clase_id}/operaciones",
    response_model=list[OperacionUMLResponse],
    summary="Listar operaciones de una clase",
)
async def listar_operaciones(
    clase_id: str,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = DiagramaService()
    return await service.listar_operaciones(clase_id, usuario_id=current_user.id)


@router.post(
    "/clases/{clase_id}/operaciones",
    response_model=OperacionUMLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar operación (con parámetros anidados) a una clase",
)
async def agregar_operacion(
    clase_id: str,
    datos: OperacionUMLCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> OperacionUMLResponse:
    service = DiagramaService()
    return await service.agregar_operacion(
        clase_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/operaciones/{operacion_id}",
    response_model=OperacionUMLResponse,
    summary="Actualizar operación",
)
async def actualizar_operacion(
    operacion_id: str,
    datos: OperacionUMLUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> OperacionUMLResponse:
    service = DiagramaService()
    return await service.actualizar_operacion(
        operacion_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/operaciones/{operacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar operación (y sus parámetros)",
)
async def eliminar_operacion(
    operacion_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar_operacion(operacion_id, usuario_id=current_user.id)


# ======================================================================
# PARÁMETROS
# ======================================================================
@router.post(
    "/operaciones/{operacion_id}/parametros",
    response_model=ParametroOperacionUMLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar parámetro a una operación",
)
async def agregar_parametro(
    operacion_id: str,
    datos: ParametroOperacionUMLCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> ParametroOperacionUMLResponse:
    service = DiagramaService()
    return await service.agregar_parametro(
        operacion_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/parametros/{parametro_id}",
    response_model=ParametroOperacionUMLResponse,
    summary="Actualizar parámetro",
)
async def actualizar_parametro(
    parametro_id: str,
    datos: ParametroOperacionUMLUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> ParametroOperacionUMLResponse:
    service = DiagramaService()
    return await service.actualizar_parametro(
        parametro_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/parametros/{parametro_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar parámetro",
)
async def eliminar_parametro(
    parametro_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar_parametro(parametro_id, usuario_id=current_user.id)


# ======================================================================
# INTERFACES
# ======================================================================
@router.post(
    "/{diagrama_id}/interfaces",
    response_model=InterfazUMLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear interfaz en el diagrama (con operaciones anidadas)",
)
async def crear_interfaz(
    diagrama_id: PydanticObjectId,
    datos: InterfazUMLCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> InterfazUMLResponse:
    service = DiagramaService()
    return await service.crear_interfaz(
        diagrama_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/interfaces/{interfaz_id}",
    response_model=InterfazUMLResponse,
    summary="Actualizar interfaz",
)
async def actualizar_interfaz(
    interfaz_id: str,
    datos: InterfazUMLUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> InterfazUMLResponse:
    service = DiagramaService()
    return await service.actualizar_interfaz(
        interfaz_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/interfaces/{interfaz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar interfaz",
)
async def eliminar_interfaz(
    interfaz_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar_interfaz(interfaz_id, usuario_id=current_user.id)


@router.post(
    "/interfaces/{interfaz_id}/operaciones",
    response_model=OperacionInterfazUMLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar operación a una interfaz",
)
async def agregar_op_interfaz(
    interfaz_id: str,
    datos: OperacionInterfazUMLCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> OperacionInterfazUMLResponse:
    service = DiagramaService()
    return await service.agregar_op_interfaz(
        interfaz_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/operaciones-interfaz/{operacion_id}",
    response_model=OperacionInterfazUMLResponse,
    summary="Actualizar operación de interfaz",
)
async def actualizar_op_interfaz(
    operacion_id: str,
    datos: OperacionInterfazUMLUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> OperacionInterfazUMLResponse:
    service = DiagramaService()
    return await service.actualizar_op_interfaz(
        operacion_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/operaciones-interfaz/{operacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar operación de interfaz",
)
async def eliminar_op_interfaz(
    operacion_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar_op_interfaz(operacion_id, usuario_id=current_user.id)


# ======================================================================
# RELACIONES
# ======================================================================
@router.get(
    "/{diagrama_id}/relaciones",
    response_model=list[RelacionUMLResponse],
    summary="Listar relaciones del diagrama",
)
async def listar_relaciones(
    diagrama_id: PydanticObjectId,
    current_user: Usuario = Depends(get_current_active_user),
):
    service = DiagramaService()
    return await service.listar_relaciones(diagrama_id, usuario_id=current_user.id)


@router.post(
    "/{diagrama_id}/relaciones",
    response_model=RelacionUMLResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear relación entre dos clases",
    description=(
        "Ambas clases deben pertenecer al mismo diagrama y no pueden ser la misma. "
        "No se permiten relaciones duplicadas del mismo tipo entre las mismas clases."
    ),
)
async def crear_relacion(
    diagrama_id: PydanticObjectId,
    datos: RelacionUMLCreate,
    current_user: Usuario = Depends(get_current_active_user),
) -> RelacionUMLResponse:
    service = DiagramaService()
    return await service.crear_relacion(
        diagrama_id, datos, usuario_id=current_user.id
    )


@router.put(
    "/relaciones/{relacion_id}",
    response_model=RelacionUMLResponse,
    summary="Actualizar relación",
)
async def actualizar_relacion(
    relacion_id: str,
    datos: RelacionUMLUpdate,
    current_user: Usuario = Depends(get_current_active_user),
) -> RelacionUMLResponse:
    service = DiagramaService()
    return await service.actualizar_relacion(
        relacion_id, datos, usuario_id=current_user.id
    )


@router.delete(
    "/relaciones/{relacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar relación",
)
async def eliminar_relacion(
    relacion_id: str,
    current_user: Usuario = Depends(get_current_active_user),
) -> None:
    service = DiagramaService()
    await service.eliminar_relacion(relacion_id, usuario_id=current_user.id)