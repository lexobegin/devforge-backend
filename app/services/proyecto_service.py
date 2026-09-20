# app/services/proyecto_service.py
"""
Lógica de negocio del módulo B. Proyectos y Miembros.

Reglas clave:
- Al crear un proyecto, el creador queda automáticamente como PROPIETARIO.
- Un proyecto no puede quedar sin al menos un PROPIETARIO.
- No se puede duplicar un miembro en un proyecto.
- El usuario que no pertenece al proyecto no puede verlo ni modificarlo
  (excepto ADMIN de la plataforma).
"""

from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.proyecto import MiembroProyecto, Proyecto
from app.repositories.proyecto_repository import (
    MiembroProyectoRepository,
    ProyectoRepository,
)
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.proyecto_schema import (
    MiembroProyectoCreate,
    MiembroProyectoResponse,
    MiembroProyectoUpdate,
    ProyectoConMiembrosResponse,
    ProyectoCreate,
    ProyectoResponse,
    ProyectoUpdate,
)


class ProyectoService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.proyectos = ProyectoRepository(db)
        self.miembros = MiembroProyectoRepository(db)
        self.usuarios = UsuarioRepository(db)

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def listar_para_usuario(
        self,
        usuario_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        incluir_archivados: bool = False,
    ) -> tuple[Sequence[ProyectoResponse], int]:
        """
        Proyectos en los que el usuario es propietario o miembro.
        Devuelve (items, total).
        """
        items = await self.proyectos.list_for_usuario(
            usuario_id,
            skip=skip,
            limit=limit,
            incluir_archivados=incluir_archivados,
        )
        total = await self.proyectos.count_for_usuario(
            usuario_id, incluir_archivados=incluir_archivados
        )
        return [ProyectoResponse.model_validate(p) for p in items], total

    async def listar_todos(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        incluir_archivados: bool = False,
    ) -> tuple[Sequence[ProyectoResponse], int]:
        """Uso exclusivo del ADMIN de la plataforma."""
        items = await self.proyectos.list_all(
            skip=skip, limit=limit, incluir_archivados=incluir_archivados
        )
        # Nota: el repo no expone count_all() aún; usamos len() como aproximación
        # si necesitas total real, agrega `count_all()` en ProyectoRepository.
        total = len(items)
        return [ProyectoResponse.model_validate(p) for p in items], total

    async def obtener(
        self,
        proyecto_id: int,
        *,
        usuario_id: int,
        es_admin: bool = False,
        con_miembros: bool = False,
    ) -> ProyectoResponse | ProyectoConMiembrosResponse:
        """
        Obtiene un proyecto verificando que el usuario tenga acceso:
        - ADMIN: siempre.
        - No admin: debe ser miembro (cualquier rol).
        """
        proyecto = await self.proyectos.get_by_id(
            proyecto_id, con_miembros=con_miembros
        )
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")

        if not es_admin:
            miembro = await self.miembros.get_by_proyecto_usuario(
                proyecto_id, usuario_id
            )
            if miembro is None:
                # 404 en vez de 403: no revelar la existencia de proyectos ajenos.
                raise NotFoundError("Proyecto no encontrado")

        if con_miembros:
            return ProyectoConMiembrosResponse.model_validate(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------
    async def crear(
        self, datos: ProyectoCreate, *, usuario_id: int
    ) -> ProyectoResponse:
        """
        Crea el proyecto y agrega al creador como miembro con rol PROPIETARIO,
        todo en la misma transacción.
        """
        proyecto = Proyecto(
            nombre=datos.nombre.strip(),
            descripcion=(datos.descripcion or "").strip() or None,
            id_propietario=usuario_id,
            estado="ACTIVO",
        )
        proyecto = await self.proyectos.create(proyecto)

        # Creador = PROPIETARIO
        miembro = MiembroProyecto(
            id_proyecto=proyecto.id,
            id_usuario=usuario_id,
            rol_en_proyecto="PROPIETARIO",
        )
        await self.miembros.create(miembro)

        await self.db.commit()
        await self.db.refresh(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    # ------------------------------------------------------------------
    # Actualización
    # ------------------------------------------------------------------
    async def actualizar(
        self,
        proyecto_id: int,
        datos: ProyectoUpdate,
        *,
        usuario_id: int,
    ) -> ProyectoResponse:
        """
        Solo PROPIETARIO o EDITOR pueden modificar el proyecto.
        Cambiar el estado a ARCHIVADO solo lo puede hacer el PROPIETARIO.
        """
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")

        miembro = await self._require_rol(
            proyecto_id, usuario_id, roles=("PROPIETARIO", "EDITOR")
        )

        if datos.nombre is not None:
            proyecto.nombre = datos.nombre.strip()

        if datos.descripcion is not None:
            proyecto.descripcion = datos.descripcion.strip() or None

        if datos.estado is not None:
            if miembro.rol_en_proyecto != "PROPIETARIO":
                raise ForbiddenError(
                    "Solo el propietario puede archivar o reactivar el proyecto"
                )
            if datos.estado not in ("ACTIVO", "ARCHIVADO"):
                raise ValidationError("Estado inválido")
            proyecto.estado = datos.estado

        await self.proyectos.update(proyecto)
        await self.db.commit()
        await self.db.refresh(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    async def archivar(self, proyecto_id: int, *, usuario_id: int) -> ProyectoResponse:
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")
        await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))
        proyecto = await self.proyectos.archivar(proyecto_id)
        await self.db.commit()
        await self.db.refresh(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    async def reactivar(self, proyecto_id: int, *, usuario_id: int) -> ProyectoResponse:
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")
        await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))
        proyecto = await self.proyectos.activar(proyecto_id)
        await self.db.commit()
        await self.db.refresh(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    # ------------------------------------------------------------------
    # Eliminación
    # ------------------------------------------------------------------
    async def eliminar(self, proyecto_id: int, *, usuario_id: int) -> None:
        """Solo el PROPIETARIO puede eliminar el proyecto."""
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")
        await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))
        await self.proyectos.delete(proyecto)
        await self.db.commit()

    # ==================================================================
    # MIEMBROS
    # ==================================================================
    async def listar_miembros(
        self, proyecto_id: int, *, usuario_id: int
    ) -> Sequence[MiembroProyectoResponse]:
        await self._require_miembro(proyecto_id, usuario_id)
        miembros = await self.miembros.list_by_proyecto(proyecto_id)
        return [MiembroProyectoResponse.model_validate(m) for m in miembros]

    async def agregar_miembro(
        self,
        proyecto_id: int,
        datos: MiembroProyectoCreate,
        *,
        usuario_id: int,
    ) -> MiembroProyectoResponse:
        """
        Solo PROPIETARIO puede agregar miembros (según rol requerido).
        No se puede agregar un segundo PROPIETARIO desde aquí (regla del sistema).
        """
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")

        await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))

        # Verificar que el usuario a agregar existe
        nuevo_usuario = await self.usuarios.get_by_id(datos.id_usuario)
        if nuevo_usuario is None:
            raise NotFoundError("El usuario a agregar no existe")

        if not nuevo_usuario.activo:
            raise ValidationError("El usuario a agregar está desactivado")

        # Verificar que no sea ya miembro
        ya_miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, datos.id_usuario
        )
        if ya_miembro is not None:
            raise ConflictError("El usuario ya es miembro de este proyecto")

        # Regla: no permitir un segundo PROPIETARIO por esta vía
        if datos.rol_en_proyecto == "PROPIETARIO":
            raise ValidationError(
                "Use transferir_propiedad() para asignar otro PROPIETARIO"
            )

        miembro = MiembroProyecto(
            id_proyecto=proyecto_id,
            id_usuario=datos.id_usuario,
            rol_en_proyecto=datos.rol_en_proyecto,
        )
        miembro = await self.miembros.create(miembro)
        await self.db.commit()
        await self.db.refresh(miembro)
        return MiembroProyectoResponse.model_validate(miembro)

    async def cambiar_rol_miembro(
        self,
        proyecto_id: int,
        miembro_id: int,
        datos: MiembroProyectoUpdate,
        *,
        usuario_id: int,
    ) -> MiembroProyectoResponse:
        """
        Solo PROPIETARIO puede cambiar roles de otros miembros.
        No se puede cambiar el rol del PROPIETARIO actual (para eso existe
        transferir_propiedad).
        """
        await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))

        miembro = await self.miembros.get_by_id(miembro_id)
        if miembro is None or miembro.id_proyecto != proyecto_id:
            raise NotFoundError("Miembro no encontrado en este proyecto")

        if miembro.rol_en_proyecto == "PROPIETARIO":
            raise ForbiddenError(
                "No se puede cambiar el rol del propietario. "
                "Use transferir_propiedad() si quiere transferir el proyecto."
            )

        if datos.rol_en_proyecto == "PROPIETARIO":
            raise ValidationError(
                "Use transferir_propiedad() para asignar un nuevo PROPIETARIO"
            )

        miembro.rol_en_proyecto = datos.rol_en_proyecto
        await self.miembros.update(miembro)
        await self.db.commit()
        await self.db.refresh(miembro)
        return MiembroProyectoResponse.model_validate(miembro)

    async def quitar_miembro(
        self,
        proyecto_id: int,
        miembro_id: int,
        *,
        usuario_id: int,
    ) -> None:
        """
        Solo PROPIETARIO puede quitar miembros.
        No se puede quitar al PROPIETARIO (debe transferir primero o eliminar
        el proyecto completo).
        Un miembro también puede quitarse a sí mismo (salirse del proyecto).
        """
        miembro = await self.miembros.get_by_id(miembro_id)
        if miembro is None or miembro.id_proyecto != proyecto_id:
            raise NotFoundError("Miembro no encontrado en este proyecto")

        if miembro.rol_en_proyecto == "PROPIETARIO":
            raise ForbiddenError(
                "No se puede quitar al propietario del proyecto"
            )

        # El propio miembro puede salirse sin ser PROPIETARIO
        es_el_mismo = miembro.id_usuario == usuario_id
        if not es_el_mismo:
            await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))

        await self.miembros.delete(miembro)
        await self.db.commit()

    async def transferir_propiedad(
        self,
        proyecto_id: int,
        nuevo_propietario_id: int,
        *,
        usuario_id: int,
    ) -> MiembroProyectoResponse:
        """
        Transfiere el rol PROPIETARIO del proyecto actual a otro miembro.
        - Solo el PROPIETARIO actual puede hacerlo.
        - El nuevo propietario debe ser ya miembro del proyecto.
        - El propietario actual queda como EDITOR.
        """
        await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))

        # Actual = usuario_id
        actual = await self.miembros.get_by_proyecto_usuario(proyecto_id, usuario_id)
        nuevo = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, nuevo_propietario_id
        )
        if nuevo is None:
            raise NotFoundError(
                "El nuevo propietario debe ser miembro del proyecto"
            )
        if actual.id == nuevo.id:
            raise ValidationError("El usuario ya es propietario del proyecto")

        # Intercambio de roles
        actual.rol_en_proyecto = "EDITOR"
        nuevo.rol_en_proyecto = "PROPIETARIO"

        # Actualizar también el id_propietario en la tabla proyectos
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        proyecto.id_propietario = nuevo_propietario_id

        await self.miembros.update(actual)
        await self.miembros.update(nuevo)
        await self.proyectos.update(proyecto)
        await self.db.commit()
        await self.db.refresh(nuevo)
        return MiembroProyectoResponse.model_validate(nuevo)

    # ==================================================================
    # Helpers internos
    # ==================================================================
    async def _require_miembro(
        self, proyecto_id: int, usuario_id: int
    ) -> MiembroProyecto:
        """Verifica que el usuario sea miembro del proyecto (cualquier rol)."""
        miembro = await self.miembros.get_by_proyecto_usuario(proyecto_id, usuario_id)
        if miembro is None:
            raise NotFoundError("Proyecto no encontrado")
        return miembro

    async def _require_rol(
        self,
        proyecto_id: int,
        usuario_id: int,
        *,
        roles: tuple[str, ...],
    ) -> MiembroProyecto:
        """Verifica que el usuario tenga uno de los roles indicados."""
        miembro = await self.miembros.get_by_proyecto_usuario(proyecto_id, usuario_id)
        if miembro is None:
            raise NotFoundError("Proyecto no encontrado")
        if miembro.rol_en_proyecto not in roles:
            raise ForbiddenError(
                f"Se requiere rol {' o '.join(roles)} en el proyecto"
            )
        return miembro