# app/services/trazabilidad_service.py
"""
Lógica de negocio del módulo D. Trazabilidad.

Cubre:
- Registro del historial de cambios por diagrama (lo usa el WS y los
  servicios de diagrama al aplicar cambios).
- Snapshot de versiones completas del diagrama.
- Comentarios/anotaciones de los colaboradores.
"""

from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.trazabilidad import (
    ComentarioDiagrama,
    HistorialCambioDiagrama,
    VersionDiagrama,
)
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.repositories.trazabilidad_repository import (
    ComentarioDiagramaRepository,
    HistorialCambioRepository,
    VersionDiagramaRepository,
)
from app.schemas.trazabilidad_schema import (
    ComentarioDiagramaCreate,
    ComentarioDiagramaResponse,
    ComentarioDiagramaUpdate,
    HistorialCambioDiagramaCreate,
    HistorialCambioDiagramaResponse,
    VersionDiagramaCreate,
    VersionDiagramaResponse,
    VersionDiagramaResumenResponse,
)


class TrazabilidadService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.historial = HistorialCambioRepository(db)
        self.versiones = VersionDiagramaRepository(db)
        self.comentarios = ComentarioDiagramaRepository(db)
        self.diagramas = DiagramaRepository(db)
        self.miembros = MiembroProyectoRepository(db)

    # ==================================================================
    # HISTORIAL DE CAMBIOS
    # ==================================================================
    async def registrar_cambio(
        self,
        diagrama_id: int,
        datos: HistorialCambioDiagramaCreate,
        *,
        usuario_id: int,
    ) -> HistorialCambioDiagramaResponse:
        """
        Registra un cambio individual en el historial.
        Este método lo invocan los demás servicios al aplicar cambios y
        también el WebSocket al procesar ediciones en vivo.
        """
        cambio = HistorialCambioDiagrama(
            id_diagrama=diagrama_id,
            id_usuario=usuario_id,
            tipo_cambio=datos.tipo_cambio,
            tipo_entidad=datos.tipo_entidad,
            id_entidad=datos.id_entidad,
            datos_cambio=datos.datos_cambio,
        )
        cambio = await self.historial.create(cambio)
        # Nota: no hacemos commit aquí; quien llama decide el commit para
        # que un mismo cambio quede en la misma transacción que la mutación.
        return HistorialCambioDiagramaResponse.model_validate(cambio)

    async def listar_historial(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[HistorialCambioDiagramaResponse]:
        await self._require_miembro_de_diagrama(diagrama_id, usuario_id)
        items = await self.historial.list_by_diagrama(
            diagrama_id,
            desde=desde,
            hasta=hasta,
            skip=skip,
            limit=limit,
        )
        return [HistorialCambioDiagramaResponse.model_validate(i) for i in items]

    async def listar_historial_de_elemento(
        self,
        diagrama_id: int,
        tipo_entidad: str,
        id_entidad: int,
        *,
        usuario_id: int,
    ) -> Sequence[HistorialCambioDiagramaResponse]:
        await self._require_miembro_de_diagrama(diagrama_id, usuario_id)
        items = await self.historial.list_by_entidad(
            diagrama_id, tipo_entidad, id_entidad
        )
        return [HistorialCambioDiagramaResponse.model_validate(i) for i in items]

    # ==================================================================
    # VERSIONES
    # ==================================================================
    async def guardar_version(
        self,
        diagrama_id: int,
        datos: VersionDiagramaCreate,
        *,
        usuario_id: int,
    ) -> VersionDiagramaResponse:
        """
        Guarda un snapshot completo del diagrama.
        El número de versión lo calcula el service (siguiente correlativo).
        Además incrementa `diagramas.numero_version`.
        """
        await self._require_editor_de_diagrama(diagrama_id, usuario_id)

        # Consistencia: el contenido no puede ser vacío
        if not isinstance(datos.contenido_json, dict) or not datos.contenido_json:
            raise ValidationError("El contenido de la versión no puede estar vacío")

        numero = await self.versiones.next_numero_version(diagrama_id)

        version = VersionDiagrama(
            id_diagrama=diagrama_id,
            numero_version=numero,
            contenido_json=datos.contenido_json,
            id_usuario=usuario_id,
            comentario=datos.comentario,
        )
        version = await self.versiones.create(version)

        # Incrementar la versión del diagrama
        await self.diagramas.incrementar_version(diagrama_id)

        await self.db.commit()
        await self.db.refresh(version)
        return VersionDiagramaResponse.model_validate(version)

    async def listar_versiones(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[VersionDiagramaResumenResponse]:
        await self._require_miembro_de_diagrama(diagrama_id, usuario_id)
        items = await self.versiones.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )
        return [VersionDiagramaResumenResponse.model_validate(v) for v in items]

    async def obtener_version(
        self, version_id: int, *, usuario_id: int
    ) -> VersionDiagramaResponse:
        version = await self.versiones.get_by_id(version_id)
        if version is None:
            raise NotFoundError("Versión no encontrada")
        await self._require_miembro_de_diagrama(version.id_diagrama, usuario_id)
        return VersionDiagramaResponse.model_validate(version)

    async def obtener_ultima_version(
        self, diagrama_id: int, *, usuario_id: int
    ) -> Optional[VersionDiagramaResponse]:
        await self._require_miembro_de_diagrama(diagrama_id, usuario_id)
        version = await self.versiones.get_ultima_by_diagrama(diagrama_id)
        if version is None:
            return None
        return VersionDiagramaResponse.model_validate(version)

    # ==================================================================
    # COMENTARIOS
    # ==================================================================
    async def crear_comentario(
        self,
        diagrama_id: int,
        datos: ComentarioDiagramaCreate,
        *,
        usuario_id: int,
    ) -> ComentarioDiagramaResponse:
        await self._require_editor_de_diagrama(diagrama_id, usuario_id)

        # Coherencia: si hay tipo_entidad, debe haber id_entidad (y viceversa)
        if (datos.tipo_entidad is None) != (datos.id_entidad is None):
            raise ValidationError(
                "Si indica tipo_entidad, debe indicar id_entidad (y viceversa). "
                "Para comentario general deje ambos en null."
            )

        comentario = ComentarioDiagrama(
            id_diagrama=diagrama_id,
            id_usuario=usuario_id,
            tipo_entidad=datos.tipo_entidad,
            id_entidad=datos.id_entidad,
            texto=datos.texto.strip(),
            resuelto=False,
        )
        comentario = await self.comentarios.create(comentario)
        await self.db.commit()
        await self.db.refresh(comentario)
        return ComentarioDiagramaResponse.model_validate(comentario)

    async def listar_comentarios(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
        solo_no_resueltos: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ComentarioDiagramaResponse]:
        await self._require_miembro_de_diagrama(diagrama_id, usuario_id)
        items = await self.comentarios.list_by_diagrama(
            diagrama_id,
            solo_no_resueltos=solo_no_resueltos,
            skip=skip,
            limit=limit,
        )
        return [ComentarioDiagramaResponse.model_validate(c) for c in items]

    async def listar_comentarios_de_elemento(
        self,
        diagrama_id: int,
        tipo_entidad: str,
        id_entidad: int,
        *,
        usuario_id: int,
    ) -> Sequence[ComentarioDiagramaResponse]:
        await self._require_miembro_de_diagrama(diagrama_id, usuario_id)
        items = await self.comentarios.list_by_entidad(
            diagrama_id, tipo_entidad, id_entidad
        )
        return [ComentarioDiagramaResponse.model_validate(c) for c in items]

    async def actualizar_comentario(
        self,
        comentario_id: int,
        datos: ComentarioDiagramaUpdate,
        *,
        usuario_id: int,
    ) -> ComentarioDiagramaResponse:
        comentario = await self.comentarios.get_by_id(comentario_id)
        if comentario is None:
            raise NotFoundError("Comentario no encontrado")

        await self._require_editor_de_diagrama(comentario.id_diagrama, usuario_id)

        # Solo el autor puede editar el texto
        if datos.texto is not None:
            if comentario.id_usuario != usuario_id:
                raise ForbiddenError("Solo el autor puede editar su comentario")
            comentario.texto = datos.texto.strip()

        # Cualquier editor del proyecto puede marcarlo resuelto
        if datos.resuelto is not None:
            comentario.resuelto = datos.resuelto

        await self.comentarios.update(comentario)
        await self.db.commit()
        await self.db.refresh(comentario)
        return ComentarioDiagramaResponse.model_validate(comentario)

    async def eliminar_comentario(
        self, comentario_id: int, *, usuario_id: int
    ) -> None:
        comentario = await self.comentarios.get_by_id(comentario_id)
        if comentario is None:
            raise NotFoundError("Comentario no encontrado")

        await self._require_editor_de_diagrama(comentario.id_diagrama, usuario_id)

        if comentario.id_usuario != usuario_id:
            raise ForbiddenError("Solo el autor puede eliminar su comentario")

        await self.comentarios.delete(comentario)
        await self.db.commit()

    # ==================================================================
    # HELPERS INTERNOS
    # ==================================================================
    async def _require_miembro_de_diagrama(
        self, diagrama_id: int, usuario_id: int
    ) -> None:
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        miembro = await self.miembros.get_by_proyecto_usuario(
            diagrama.id_proyecto, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")

    async def _require_editor_de_diagrama(
        self, diagrama_id: int, usuario_id: int
    ) -> None:
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        miembro = await self.miembros.get_by_proyecto_usuario(
            diagrama.id_proyecto, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ForbiddenError(
                "Se requiere rol EDITOR o PROPIETARIO en el proyecto"
            )