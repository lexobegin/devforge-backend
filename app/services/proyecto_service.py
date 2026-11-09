# app/services/proyecto_service.py
"""
Lógica de negocio del módulo B. Proyectos y Miembros.

Reglas clave:
- Al crear un proyecto, el creador queda automáticamente como PROPIETARIO.
- Un proyecto no puede quedar sin al menos un PROPIETARIO.
- No se puede duplicar un miembro en un proyecto.
- El usuario que no pertenece al proyecto no puede verlo ni modificarlo
  (excepto ADMIN de la plataforma).

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Servicio SIN ESTADO: sin AsyncSession ni commit()/refresh(); cada
  insert()/save()/delete() persiste de inmediato.
- La tabla miembros_proyecto desapareció: los miembros van EMBEBIDOS en
  Proyecto.miembros. Por eso `_require_miembro`/`_require_rol` RE-LEEN el
  documento y devuelven el PROYECTO (no la fila del miembro): quien muta
  membresías lo hace sobre el documento re-leído y lo guarda (regla
  fetch → modificar → save de Beanie).
- crear() ya no son dos INSERT dentro de una transacción: el PROPIETARIO
  viaja embebido y basta UN insert() del documento.
- cambiar_rol_miembro/quitar_miembro identifican al miembro por su
  id_usuario: el embebido no tiene id propio y la clave es el par
  (proyecto, id_usuario) que en el Ciclo 1 garantizaba uq_miembro.
- transferir_propiedad queda en UN save() (en el Ciclo 1 eran tres UPDATE
  + commit), y updated_at se fija aquí (el onupdate=func.now() de
  SQLAlchemy no existe en MongoDB).
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from beanie import PydanticObjectId

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
    UsuarioCandidatoResponse,
)


def _ahora() -> datetime:
    """Sustituye al onupdate=func.now() del Ciclo 1: marca aware UTC."""
    return datetime.now(timezone.utc)


class ProyectoService:
    def __init__(self) -> None:
        self.proyectos = ProyectoRepository()
        self.miembros = MiembroProyectoRepository()
        self.usuarios = UsuarioRepository()

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def listar_para_usuario(
        self,
        usuario_id: PydanticObjectId,
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
        """
        Uso exclusivo del ADMIN de la plataforma.
        El Ciclo 1 aproximaba el total con len(items) porque el repo no
        exponía count_all(); aquí Beanie cuenta con la MISMA condición del
        listado (find(...).count()), así que el total es real.
        """
        items = await self.proyectos.list_all(
            skip=skip, limit=limit, incluir_archivados=incluir_archivados
        )
        condiciones = (
            [] if incluir_archivados else [Proyecto.estado == "ACTIVO"]
        )
        total = await Proyecto.find(*condiciones).count()
        return [ProyectoResponse.model_validate(p) for p in items], total

    async def obtener(
        self,
        proyecto_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        es_admin: bool = False,
        con_miembros: bool = False,
    ) -> ProyectoResponse | ProyectoConMiembrosResponse:
        """
        Obtiene un proyecto verificando que el usuario tenga acceso:
        - ADMIN: siempre.
        - No admin: debe ser miembro (cualquier rol).
        Leer el proyecto SIEMPRE trae sus miembros embebidos, así que la
        verificación se hace sobre el propio documento (antes
        get_by_proyecto_usuario sobre la tabla hija).
        """
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")

        if not es_admin and proyecto.miembro(usuario_id) is None:
            # 404 en vez de 403: no revelar la existencia de proyectos ajenos.
            raise NotFoundError("Proyecto no encontrado")

        if con_miembros:
            return ProyectoConMiembrosResponse.model_validate(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------
    async def crear(
        self, datos: ProyectoCreate, *, usuario_id: PydanticObjectId
    ) -> ProyectoResponse:
        """
        Crea el proyecto y agrega al creador como miembro con rol
        PROPIETARIO, todo en la misma "transacción": en el Ciclo 1 eran dos
        INSERT con commit; aquí el miembro va EMBEBIDO y basta UN insert().
        """
        proyecto = Proyecto(
            nombre=datos.nombre.strip(),
            descripcion=(datos.descripcion or "").strip() or None,
            id_propietario=usuario_id,
            estado="ACTIVO",
            miembros=[
                MiembroProyecto(
                    id_usuario=usuario_id,
                    rol_en_proyecto="PROPIETARIO",
                )
            ],
        )
        proyecto = await self.proyectos.create(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    # ------------------------------------------------------------------
    # Actualización
    # ------------------------------------------------------------------
    async def actualizar(
        self,
        proyecto_id: PydanticObjectId,
        datos: ProyectoUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> ProyectoResponse:
        """
        Solo PROPIETARIO o EDITOR pueden modificar el proyecto.
        Cambiar el estado a ARCHIVADO solo lo puede hacer el PROPIETARIO.
        """
        proyecto = await self._require_rol(
            proyecto_id, usuario_id, roles=("PROPIETARIO", "EDITOR")
        )
        miembro = proyecto.miembro(usuario_id)

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

        proyecto.updated_at = _ahora()
        proyecto = await self.proyectos.update(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    async def archivar(
        self, proyecto_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> ProyectoResponse:
        """
        Ciclo 1: proyectos.archivar(proyecto_id) (UPDATE con onupdate).
        Ciclo 2: se fija el estado y updated_at sobre el documento re-leído
        y se guarda (fetch → modificar → save).
        """
        proyecto = await self._require_rol(
            proyecto_id, usuario_id, roles=("PROPIETARIO",)
        )
        proyecto.estado = "ARCHIVADO"
        proyecto.updated_at = _ahora()
        proyecto = await self.proyectos.update(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    async def reactivar(
        self, proyecto_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> ProyectoResponse:
        """Espejo de `archivar`: devuelve el proyecto a ACTIVO."""
        proyecto = await self._require_rol(
            proyecto_id, usuario_id, roles=("PROPIETARIO",)
        )
        proyecto.estado = "ACTIVO"
        proyecto.updated_at = _ahora()
        proyecto = await self.proyectos.update(proyecto)
        return ProyectoResponse.model_validate(proyecto)

    # ------------------------------------------------------------------
    # Eliminación
    # ------------------------------------------------------------------
    async def eliminar(
        self, proyecto_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> None:
        """
        Solo el PROPIETARIO puede eliminar el proyecto.
        En MongoDB no hay cascadas: las colecciones hijas (diagramas,
        sesiones, etc.) se limpian con sus propios servicios cuando se
        orquesta el borrado.
        """
        proyecto = await self._require_rol(
            proyecto_id, usuario_id, roles=("PROPIETARIO",)
        )
        await self.proyectos.delete(proyecto)

    # ==================================================================
    # MIEMBROS
    # ==================================================================
    async def listar_miembros(
        self,
        proyecto_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> Sequence[MiembroProyectoResponse]:
        await self._require_miembro(proyecto_id, usuario_id)
        miembros = await self.miembros.list_by_proyecto(proyecto_id)

        # ------------------------------------------------------------------
        # Tanda B23: el embebido solo trae id_usuario — sin el join, un
        # LECTOR/EDITOR no-ADMIN veía "Usuario 6aee4aad…" en el modal
        # (GET /usuarios/{id} también es ADMIN-o-el-propio). Resolvemos
        # nombre/email en UNA consulta $in y poblamos los campos
        # opcionales de la respuesta; si un usuario ya no existe, quedan
        # None y el cliente muestra el id como antes.
        # ------------------------------------------------------------------
        usuarios = await self.usuarios.get_by_ids(
            [m.id_usuario for m in miembros]
        )
        por_id = {u.id: u for u in usuarios}

        respuesta: list[MiembroProyectoResponse] = []
        for m in miembros:
            item = MiembroProyectoResponse.model_validate(m)
            u = por_id.get(m.id_usuario)
            if u is not None:
                item.nombre_usuario = u.nombre_completo
                item.email_usuario = u.email
            respuesta.append(item)
        return respuesta

    async def listar_candidatos(
        self,
        proyecto_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        es_admin: bool = False,
        buscar: Optional[str] = None,
        limit: int = 20,
    ) -> Sequence[UsuarioCandidatoResponse]:
        """
        Tanda B23: usuarios activos que pueden SER agregados al proyecto
        (no son miembros aún). Repara el 403 del modal de miembros:
        GET /usuarios es solo-ADMIN y el PROPIETARIO suele ser
        DESARROLLADOR.

        Permisos: PROPIETARIO del proyecto, o ADMIN de la plataforma (el
        admin puede no ser miembro; _require_rol le daría 404, así que
        el bypass se resuelve ANTES con la misma semántica de obtener()).
        """
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")

        if es_admin:
            if proyecto.miembro(usuario_id) is None:
                # El admin no-miembro ve el proyecto igual (obtener() lo
                # permite); aquí solo hace falta que exista.
                pass
        else:
            proyecto = await self._require_rol(
                proyecto_id, usuario_id, roles=("PROPIETARIO",)
            )

        excluir = [m.id_usuario for m in proyecto.miembros]
        candidatos = await self.usuarios.buscar_candidatos(
            excluir_ids=excluir, buscar=buscar, limit=limit
        )
        return [UsuarioCandidatoResponse.model_validate(u) for u in candidatos]

    async def agregar_miembro(
        self,
        proyecto_id: PydanticObjectId,
        datos: MiembroProyectoCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> MiembroProyectoResponse:
        """
        Solo PROPIETARIO puede agregar miembros (según rol requerido).
        No se puede agregar un segundo PROPIETARIO desde aquí (regla del
        sistema).
        """
        proyecto = await self._require_rol(
            proyecto_id, usuario_id, roles=("PROPIETARIO",)
        )

        # Verificar que el usuario a agregar existe
        nuevo_usuario = await self.usuarios.get_by_id(datos.id_usuario)
        if nuevo_usuario is None:
            raise NotFoundError("El usuario a agregar no existe")

        if not nuevo_usuario.activo:
            raise ValidationError("El usuario a agregar está desactivado")

        # Verificar que no sea ya miembro (antes get_by_proyecto_usuario
        # sobre la tabla hija; ahora la búsqueda es sobre el embebido y
        # equivale a la uq_miembro del Ciclo 1)
        if proyecto.miembro(datos.id_usuario) is not None:
            raise ConflictError("El usuario ya es miembro de este proyecto")

        # Regla: no permitir un segundo PROPIETARIO por esta vía
        if datos.rol_en_proyecto == "PROPIETARIO":
            raise ValidationError(
                "Use transferir_propiedad() para asignar otro PROPIETARIO"
            )

        miembro = MiembroProyecto(
            id_usuario=datos.id_usuario,
            rol_en_proyecto=datos.rol_en_proyecto,
        )
        miembro = await self.miembros.create(proyecto, miembro)
        return MiembroProyectoResponse.model_validate(miembro)

    async def cambiar_rol_miembro(
        self,
        proyecto_id: PydanticObjectId,
        id_usuario_objetivo: PydanticObjectId,
        datos: MiembroProyectoUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> MiembroProyectoResponse:
        """
        Solo PROPIETARIO puede cambiar roles de otros miembros.
        No se puede cambiar el rol del PROPIETARIO actual (para eso existe
        transferir_propiedad).

        Ciclo 1: el router pasaba `miembro_id` (id de la fila en
        miembros_proyecto). Ciclo 2: el embebido no tiene id propio, así
        que el miembro se identifica por su id_usuario.
        """
        proyecto = await self._require_rol(
            proyecto_id, usuario_id, roles=("PROPIETARIO",)
        )

        miembro = proyecto.miembro(id_usuario_objetivo)
        if miembro is None:
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
        await self.miembros.update(proyecto, miembro)
        return MiembroProyectoResponse.model_validate(miembro)

    async def quitar_miembro(
        self,
        proyecto_id: PydanticObjectId,
        id_usuario_objetivo: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> None:
        """
        Solo PROPIETARIO puede quitar miembros.
        No se puede quitar al PROPIETARIO (debe transferir primero o eliminar
        el proyecto completo).
        Un miembro también puede quitarse a sí mismo (salirse del proyecto).

        Ciclo 1: el router pasaba `miembro_id` de la fila; Ciclo 2: el
        miembro se identifica por su id_usuario (ver cambiar_rol_miembro).
        """
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            raise NotFoundError("Proyecto no encontrado")

        miembro = proyecto.miembro(id_usuario_objetivo)
        if miembro is None:
            raise NotFoundError("Miembro no encontrado en este proyecto")

        if miembro.rol_en_proyecto == "PROPIETARIO":
            raise ForbiddenError(
                "No se puede quitar al propietario del proyecto"
            )

        # El propio miembro puede salirse sin ser PROPIETARIO
        es_el_mismo = miembro.id_usuario == usuario_id
        if not es_el_mismo:
            # Re-lectura fresca para mutar con la regla de Beanie
            proyecto = await self._require_rol(
                proyecto_id, usuario_id, roles=("PROPIETARIO",)
            )

        await self.miembros.delete(proyecto, miembro)

    async def transferir_propiedad(
        self,
        proyecto_id: PydanticObjectId,
        nuevo_propietario_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> MiembroProyectoResponse:
        """
        Transfiere el rol PROPIETARIO del proyecto actual a otro miembro.
        - Solo el PROPIETARIO actual puede hacerlo.
        - El nuevo propietario debe ser ya miembro del proyecto.
        - El propietario actual queda como EDITOR.
        """
        await self._require_rol(proyecto_id, usuario_id, roles=("PROPIETARIO",))

        # Re-lectura fresca del documento para mutarlo (regla de Beanie)
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        actual = proyecto.miembro(usuario_id)
        nuevo = proyecto.miembro(nuevo_propietario_id)
        if nuevo is None:
            raise NotFoundError(
                "El nuevo propietario debe ser miembro del proyecto"
            )
        # Ciclo 1: actual.id == nuevo.id (ids de fila). Ciclo 2: la membresía
        # es única por usuario, basta comparar el id_usuario.
        if actual.id_usuario == nuevo.id_usuario:
            raise ValidationError("El usuario ya es propietario del proyecto")

        # Intercambio de roles
        actual.rol_en_proyecto = "EDITOR"
        nuevo.rol_en_proyecto = "PROPIETARIO"

        # Actualizar también el id_propietario en la "tabla" proyectos
        proyecto.id_propietario = nuevo_propietario_id
        proyecto.updated_at = _ahora()

        # Ciclo 1: tres UPDATE + commit. Ciclo 2: un solo save() del documento.
        proyecto = await self.proyectos.update(proyecto)
        return MiembroProyectoResponse.model_validate(nuevo)

    # ==================================================================
    # Helpers internos
    # ==================================================================
    async def _require_miembro(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> Proyecto:
        """
        Verifica que el usuario sea miembro del proyecto (cualquier rol).

        Ciclo 1: devolvía la fila de miembros_proyecto. Ciclo 2: devuelve el
        DOCUMENTO Proyecto re-leído de la base (los miembros van embebidos y
        las mutaciones se hacen sobre él, regla fetch → modificar → save).
        """
        proyecto = await self.proyectos.get_by_id(proyecto_id)
        if proyecto is None:
            # 404 en vez de 403: no revelar la existencia de proyectos ajenos.
            raise NotFoundError("Proyecto no encontrado")

        if proyecto.miembro(usuario_id) is None:
            raise NotFoundError("Proyecto no encontrado")

        return proyecto

    async def _require_rol(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
        *,
        roles: tuple[str, ...],
    ) -> Proyecto:
        """Verifica que el usuario tenga uno de los roles indicados."""
        proyecto = await self._require_miembro(proyecto_id, usuario_id)
        miembro = proyecto.miembro(usuario_id)
        if miembro.rol_en_proyecto not in roles:
            raise ForbiddenError(
                f"Se requiere rol {' o '.join(roles)} en el proyecto"
            )
        return proyecto
