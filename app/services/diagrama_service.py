# app/services/diagrama_service.py
"""
Lógica de negocio del módulo C. Modelado UML (Diagrama de Clases).

Cubre:
- CRUD del diagrama
- CRUD de clases, atributos, operaciones, parámetros
- CRUD de interfaces y sus operaciones
- CRUD de relaciones entre clases
- Carga del diagrama completo (clases + interfaces + relaciones)
- Validación básica de notación UML 2.5+

Cada cambio significativo se registra en `historial_cambios_diagrama`
(vía TrazabilidadService) para que el editor pueda deshacer y detectar
conflictos entre colaboradores.
"""

from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.diagrama import (
    AtributoUML,
    ClaseUML,
    Diagrama,
    InterfazUML,
    OperacionInterfazUML,
    OperacionUML,
    ParametroOperacionUML,
    RelacionUML,
)
from app.repositories.diagrama_repository import (
    AtributoUMLRepository,
    ClaseUMLRepository,
    DiagramaRepository,
    InterfazUMLRepository,
    OperacionInterfazUMLRepository,
    OperacionUMLRepository,
    ParametroOperacionUMLRepository,
    RelacionUMLRepository,
)
from app.repositories.proyecto_repository import MiembroProyectoRepository
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
import logging

logger = logging.getLogger("devforge.diagrama")

class DiagramaService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.diagramas = DiagramaRepository(db)
        self.clases = ClaseUMLRepository(db)
        self.atributos = AtributoUMLRepository(db)
        self.operaciones = OperacionUMLRepository(db)
        self.parametros = ParametroOperacionUMLRepository(db)
        self.interfaces = InterfazUMLRepository(db)
        self.ops_interfaz = OperacionInterfazUMLRepository(db)
        self.relaciones = RelacionUMLRepository(db)
        self.miembros = MiembroProyectoRepository(db)

    # ==================================================================
    # DIAGRAMA
    # ==================================================================
    async def listar_por_proyecto(
        self,
        proyecto_id: int,
        *,
        usuario_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[DiagramaResponse]:
        await self._require_miembro(proyecto_id, usuario_id)
        items = await self.diagramas.list_by_proyecto(
            proyecto_id, skip=skip, limit=limit
        )
        return [DiagramaResponse.model_validate(d) for d in items]

    async def obtener(
        self, diagrama_id: int, *, usuario_id: int
    ) -> DiagramaResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        return DiagramaResponse.model_validate(diagrama)

    async def obtener_completo(
        self, diagrama_id: int, *, usuario_id: int
    ) -> DiagramaCompletoResponse:
        """
        Devuelve el diagrama con todas sus clases (y atributos/operaciones/
        parámetros), interfaces (y sus operaciones) y relaciones.
        Es el payload que consume el editor.
        """
        diagrama = await self.diagramas.get_completo(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        return DiagramaCompletoResponse.model_validate(diagrama)

    async def crear(
        self,
        proyecto_id: int,
        datos: DiagramaCreate,
        *,
        usuario_id: int,
    ) -> DiagramaResponse:
        await self._require_miembro(proyecto_id, usuario_id)
        diagrama = Diagrama(
            id_proyecto=proyecto_id,
            nombre=datos.nombre.strip(),
            version_uml=datos.version_uml,
            numero_version=1,
            id_creador=usuario_id,
        )
        diagrama = await self.diagramas.create(diagrama)
        await self.db.commit()
        await self.db.refresh(diagrama)
        return DiagramaResponse.model_validate(diagrama)

    async def actualizar(
        self,
        diagrama_id: int,
        datos: DiagramaUpdate,
        *,
        usuario_id: int,
    ) -> DiagramaResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            diagrama.nombre = datos.nombre.strip()
        if datos.version_uml is not None:
            diagrama.version_uml = datos.version_uml

        await self.diagramas.update(diagrama)
        await self.db.commit()
        await self.db.refresh(diagrama)
        return DiagramaResponse.model_validate(diagrama)

    async def eliminar(self, diagrama_id: int, *, usuario_id: int) -> None:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.diagramas.delete(diagrama)
        await self.db.commit()

    # ==================================================================
    # CLASES UML
    # ==================================================================
    async def crear_clase(
        self,
        diagrama_id: int,
        datos: ClaseUMLCreate,
        *,
        usuario_id: int,
    ) -> ClaseUMLResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        # Validación UML: nombre único en el diagrama
        if await self.clases.exists_nombre_en_diagrama(diagrama_id, datos.nombre):
            raise ConflictError(
                f"Ya existe una clase con el nombre '{datos.nombre}' en este diagrama"
            )

        self._validar_nombre_uml(datos.nombre)

        clase = ClaseUML(
            id_diagrama=diagrama_id,
            nombre=datos.nombre.strip(),
            es_abstracta=datos.es_abstracta,
            estereotipo=datos.estereotipo,
            pos_x=datos.pos_x,
            pos_y=datos.pos_y,
            id_creador=usuario_id,
        )
        clase = await self.clases.create(clase)

        # Crear atributos y operaciones anidados (si vienen en el payload)
        for attr in datos.atributos:
            await self._crear_atributo_interno(clase.id, attr)
        for op in datos.operaciones:
            op_creada = await self._crear_operacion_interna(clase.id, op)
            for param in op.parametros:
                await self._crear_parametro_interno(op_creada.id, param)

        await self.db.commit()
        return await self._clase_response_con_detalle(clase.id)

    async def listar_clases(
        self, diagrama_id: int, *, usuario_id: int
    ) -> Sequence[ClaseUMLResponse]:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        clases = await self.clases.list_by_diagrama(diagrama_id)
        return [ClaseUMLResponse.model_validate(c) for c in clases]

    async def obtener_clase(
        self, clase_id: int, *, usuario_id: int
    ) -> ClaseUMLResponse:
        clase = await self.clases.get_con_detalle(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        await self._require_miembro_de_clase(clase, usuario_id)
        return ClaseUMLResponse.model_validate(clase)

    async def actualizar_clase(
        self,
        clase_id: int,
        datos: ClaseUMLUpdate,
        *,
        usuario_id: int,
    ) -> ClaseUMLResponse:
        # ------------------------------------------------------------------
        # 1) Cargar clase y validar permisos
        # ------------------------------------------------------------------
        print(f">>> 1. ENTRÓ id={clase_id}")
        clase = await self.clases.get_by_id(clase_id)
        print(f">>> 2. clase={clase}")
        if clase is None:
            raise NotFoundError("Clase no encontrada")

        # Acceso seguro al diagrama: si la relación no está eager-loaded,
        # la cargamos explícitamente para evitar MissingGreenlet en async.
        ##if clase.diagrama is None:
        ##    logger.warning("clase %s sin diagrama cargado; recargando", clase_id)
        ##    clase = await self.clases.get_con_detalle(clase_id)
        ##    if clase is None or clase.diagrama is None:
        ##        raise NotFoundError("Clase sin diagrama asociado")

        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        print(f">>> 3. diagrama={diagrama}")

        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        print(f">>> 4. editor OK")
        # ------------------------------------------------------------------
        # 2) Log del payload que llega (para depurar el 500)
        # ------------------------------------------------------------------
        payload = datos.model_dump(exclude_unset=True)
        logger.info(
            "[actualizar_clase] id=%s usuario=%s payload=%s",
            clase_id,
            usuario_id,
            payload,
        )

        # ------------------------------------------------------------------
        # 3) Aplicar cambios al modelo
        # ------------------------------------------------------------------
        try:
            if datos.nombre is not None:
                self._validar_nombre_uml(datos.nombre)
                if await self.clases.exists_nombre_en_diagrama(
                    clase.id_diagrama, datos.nombre, exclude_id=clase.id
                ):
                    raise ConflictError(
                        f"Ya existe otra clase con el nombre '{datos.nombre}'"
                    )
                clase.nombre = datos.nombre.strip()

            if datos.es_abstracta is not None:
                clase.es_abstracta = datos.es_abstracta
            if datos.estereotipo is not None:
                clase.estereotipo = datos.estereotipo or None
            if datos.pos_x is not None:
                clase.pos_x = datos.pos_x
            if datos.pos_y is not None:
                clase.pos_y = datos.pos_y

            # ------------------------------------------------------------------
            # 4) Persistir
            # ------------------------------------------------------------------
            logger.debug("[actualizar_clase] antes de update: pos_x=%r pos_y=%r",
                        clase.pos_x, clase.pos_y)
            print(f">>> 5. antes de update")
            await self.clases.update(clase)
            print(f">>> 6. antes de commit")
            await self.db.commit()
            print(f">>> 7. commit OK")

            logger.info("[actualizar_clase] commit OK id=%s", clase_id)

        except (ConflictError, ValidationError, NotFoundError):
            # Errores de negocio: propagar tal cual, sin envolver
            await self.db.rollback()
            raise

        except Exception:
            # Error inesperado (típicamente de BD): log completo + rollback
            await self.db.rollback()
            logger.exception(
                "[actualizar_clase] FALLO id=%s payload=%s",
                clase_id,
                payload,
            )
            raise

        # ------------------------------------------------------------------
        # 5) Devolver respuesta con detalle
        # ------------------------------------------------------------------
        return await self._clase_response_con_detalle(clase.id)

    async def eliminar_clase(self, clase_id: int, *, usuario_id: int) -> None:
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        # Eliminar relaciones asociadas (cascade ya lo haría por FK, pero
        # lo hacemos explícito para dejar el historial limpio)
        try:
            await self.relaciones.delete_by_clase(clase_id)
            await self.clases.delete(clase)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            logger.exception("FALLO al eliminar clase %s", clase_id)
            raise

    # ==================================================================
    # ATRIBUTOS
    # ==================================================================
    async def agregar_atributo(
        self,
        clase_id: int,
        datos: AtributoUMLCreate,
        *,
        usuario_id: int,
    ) -> AtributoUMLResponse:
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        attr = await self._crear_atributo_interno(clase_id, datos)
        await self.db.commit()
        await self.db.refresh(attr)
        return AtributoUMLResponse.model_validate(attr)

    async def listar_atributos(
        self, clase_id: int, *, usuario_id: int
    ) -> Sequence[AtributoUMLResponse]:
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        await self._require_miembro_de_clase(clase, usuario_id)
        items = await self.atributos.list_by_clase(clase_id)
        return [AtributoUMLResponse.model_validate(a) for a in items]

    async def actualizar_atributo(
        self,
        atributo_id: int,
        datos: AtributoUMLUpdate,
        *,
        usuario_id: int,
    ) -> AtributoUMLResponse:
        attr = await self.atributos.get_by_id(atributo_id)
        if attr is None:
            raise NotFoundError("Atributo no encontrado")
        clase = await self.clases.get_by_id(attr.id_clase)
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            attr.nombre = datos.nombre.strip()
        if datos.tipo_dato is not None:
            attr.tipo_dato = datos.tipo_dato
        if datos.visibilidad is not None:
            attr.visibilidad = datos.visibilidad
        if datos.es_estatico is not None:
            attr.es_estatico = datos.es_estatico
        if datos.valor_defecto is not None:
            attr.valor_defecto = datos.valor_defecto or None
        if datos.orden is not None:
            attr.orden = datos.orden

        await self.atributos.update(attr)
        await self.db.commit()
        await self.db.refresh(attr)
        return AtributoUMLResponse.model_validate(attr)

    async def eliminar_atributo(self, atributo_id: int, *, usuario_id: int) -> None:
        attr = await self.atributos.get_by_id(atributo_id)
        if attr is None:
            raise NotFoundError("Atributo no encontrado")
        clase = await self.clases.get_by_id(attr.id_clase)
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.atributos.delete(attr)
        await self.db.commit()

    # ==================================================================
    # OPERACIONES
    # ==================================================================
    async def agregar_operacion(
        self,
        clase_id: int,
        datos: OperacionUMLCreate,
        *,
        usuario_id: int,
    ) -> OperacionUMLResponse:
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        op = await self._crear_operacion_interna(clase_id, datos)
        for param in datos.parametros:
            await self._crear_parametro_interno(op.id, param)

        await self.db.commit()
        op = await self.operaciones.get_con_parametros(op.id)
        return OperacionUMLResponse.model_validate(op)

    async def listar_operaciones(
        self, clase_id: int, *, usuario_id: int
    ) -> Sequence[OperacionUMLResponse]:
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        await self._require_miembro_de_clase(clase, usuario_id)
        ops = await self.operaciones.list_by_clase(clase_id)
        return [OperacionUMLResponse.model_validate(o) for o in ops]

    async def actualizar_operacion(
        self,
        operacion_id: int,
        datos: OperacionUMLUpdate,
        *,
        usuario_id: int,
    ) -> OperacionUMLResponse:
        op = await self.operaciones.get_by_id(operacion_id)
        if op is None:
            raise NotFoundError("Operación no encontrada")
        clase = await self.clases.get_by_id(op.id_clase)
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            op.nombre = datos.nombre.strip()
        if datos.tipo_retorno is not None:
            op.tipo_retorno = datos.tipo_retorno
        if datos.visibilidad is not None:
            op.visibilidad = datos.visibilidad
        if datos.es_estatico is not None:
            op.es_estatico = datos.es_estatico
        if datos.orden is not None:
            op.orden = datos.orden

        await self.operaciones.update(op)
        await self.db.commit()
        op = await self.operaciones.get_con_parametros(op.id)
        return OperacionUMLResponse.model_validate(op)

    async def eliminar_operacion(self, operacion_id: int, *, usuario_id: int) -> None:
        op = await self.operaciones.get_by_id(operacion_id)
        if op is None:
            raise NotFoundError("Operación no encontrada")
        clase = await self.clases.get_by_id(op.id_clase)
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.operaciones.delete(op)
        await self.db.commit()

    # ==================================================================
    # PARÁMETROS DE OPERACIÓN
    # ==================================================================
    async def agregar_parametro(
        self,
        operacion_id: int,
        datos: ParametroOperacionUMLCreate,
        *,
        usuario_id: int,
    ) -> ParametroOperacionUMLResponse:
        op = await self.operaciones.get_by_id(operacion_id)
        if op is None:
            raise NotFoundError("Operación no encontrada")
        clase = await self.clases.get_by_id(op.id_clase)
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        param = await self._crear_parametro_interno(operacion_id, datos)
        await self.db.commit()
        await self.db.refresh(param)
        return ParametroOperacionUMLResponse.model_validate(param)

    async def actualizar_parametro(
        self,
        parametro_id: int,
        datos: ParametroOperacionUMLUpdate,
        *,
        usuario_id: int,
    ) -> ParametroOperacionUMLResponse:
        param = await self.parametros.get_by_id(parametro_id)
        if param is None:
            raise NotFoundError("Parámetro no encontrado")
        op = await self.operaciones.get_by_id(param.id_operacion)
        clase = await self.clases.get_by_id(op.id_clase)
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            param.nombre = datos.nombre.strip()
        if datos.tipo_dato is not None:
            param.tipo_dato = datos.tipo_dato
        if datos.orden is not None:
            param.orden = datos.orden

        await self.parametros.update(param)
        await self.db.commit()
        await self.db.refresh(param)
        return ParametroOperacionUMLResponse.model_validate(param)

    async def eliminar_parametro(self, parametro_id: int, *, usuario_id: int) -> None:
        param = await self.parametros.get_by_id(parametro_id)
        if param is None:
            raise NotFoundError("Parámetro no encontrado")
        op = await self.operaciones.get_by_id(param.id_operacion)
        clase = await self.clases.get_by_id(op.id_clase)
        ##await self._require_editor(clase.diagrama.id_proyecto, usuario_id)
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        await self.parametros.delete(param)
        await self.db.commit()

    # ==================================================================
    # INTERFACES UML
    # ==================================================================
    async def crear_interfaz(
        self,
        diagrama_id: int,
        datos: InterfazUMLCreate,
        *,
        usuario_id: int,
    ) -> InterfazUMLResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        interfaz = InterfazUML(
            id_diagrama=diagrama_id,
            nombre=datos.nombre.strip(),
            pos_x=datos.pos_x,
            pos_y=datos.pos_y,
        )
        interfaz = await self.interfaces.create(interfaz)

        for op in datos.operaciones:
            await self._crear_op_interfaz_interna(interfaz.id, op)

        await self.db.commit()
        interfaz = await self.interfaces.get_con_operaciones(interfaz.id)
        return InterfazUMLResponse.model_validate(interfaz)

    async def actualizar_interfaz(
        self,
        interfaz_id: int,
        datos: InterfazUMLUpdate,
        *,
        usuario_id: int,
    ) -> InterfazUMLResponse:
        interfaz = await self.interfaces.get_by_id(interfaz_id)
        if interfaz is None:
            raise NotFoundError("Interfaz no encontrada")
        diagrama = await self.diagramas.get_by_id(interfaz.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        ##await self._require_editor(interfaz.diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            interfaz.nombre = datos.nombre.strip()
        if datos.pos_x is not None:
            interfaz.pos_x = datos.pos_x
        if datos.pos_y is not None:
            interfaz.pos_y = datos.pos_y

        await self.interfaces.update(interfaz)
        await self.db.commit()
        interfaz = await self.interfaces.get_con_operaciones(interfaz.id)
        return InterfazUMLResponse.model_validate(interfaz)

    async def eliminar_interfaz(self, interfaz_id: int, *, usuario_id: int) -> None:
        interfaz = await self.interfaces.get_by_id(interfaz_id)
        if interfaz is None:
            raise NotFoundError("Interfaz no encontrada")
        
        diagrama = await self.diagramas.get_by_id(interfaz.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        ##await self._require_editor(interfaz.diagrama.id_proyecto, usuario_id)
        await self.interfaces.delete(interfaz)
        await self.db.commit()

    # ==================================================================
    # OPERACIONES DE INTERFAZ
    # ==================================================================
    async def agregar_op_interfaz(
        self,
        interfaz_id: int,
        datos: OperacionInterfazUMLCreate,
        *,
        usuario_id: int,
    ) -> OperacionInterfazUMLResponse:
        interfaz = await self.interfaces.get_by_id(interfaz_id)
        if interfaz is None:
            raise NotFoundError("Interfaz no encontrada")

        diagrama = await self.diagramas.get_by_id(interfaz.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        ##await self._require_editor(interfaz.diagrama.id_proyecto, usuario_id)

        op = await self._crear_op_interfaz_interna(interfaz_id, datos)
        await self.db.commit()
        await self.db.refresh(op)
        return OperacionInterfazUMLResponse.model_validate(op)

    async def actualizar_op_interfaz(
        self,
        operacion_id: int,
        datos: OperacionInterfazUMLUpdate,
        *,
        usuario_id: int,
    ) -> OperacionInterfazUMLResponse:
        op = await self.ops_interfaz.get_by_id(operacion_id)
        if op is None:
            raise NotFoundError("Operación de interfaz no encontrada")
        interfaz = await self.interfaces.get_by_id(op.id_interfaz)
        if interfaz is None:
            raise NotFoundError("Interfaz no encontrada")

        diagrama = await self.diagramas.get_by_id(interfaz.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        ##await self._require_editor(interfaz.diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            op.nombre = datos.nombre.strip()
        if datos.tipo_retorno is not None:
            op.tipo_retorno = datos.tipo_retorno

        await self.ops_interfaz.update(op)
        await self.db.commit()
        await self.db.refresh(op)
        return OperacionInterfazUMLResponse.model_validate(op)

    async def eliminar_op_interfaz(
        self, operacion_id: int, *, usuario_id: int
    ) -> None:
        op = await self.ops_interfaz.get_by_id(operacion_id)
        if op is None:
            raise NotFoundError("Operación de interfaz no encontrada")
        
        interfaz = await self.interfaces.get_by_id(op.id_interfaz)
        if interfaz is None:
            raise NotFoundError("Interfaz no encontrada")

        diagrama = await self.diagramas.get_by_id(interfaz.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        ##await self._require_editor(interfaz.diagrama.id_proyecto, usuario_id)
        await self.ops_interfaz.delete(op)
        await self.db.commit()

    # ==================================================================
    # RELACIONES
    # ==================================================================
    async def crear_relacion(
        self,
        diagrama_id: int,
        datos: RelacionUMLCreate,
        *,
        usuario_id: int,
    ) -> RelacionUMLResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        # Validar que ambas clases pertenecen al mismo diagrama
        clase_origen = await self.clases.get_by_id(datos.id_clase_origen)
        clase_destino = await self.clases.get_by_id(datos.id_clase_destino)
        if clase_origen is None or clase_origen.id_diagrama != diagrama_id:
            raise ValidationError("La clase origen no pertenece a este diagrama")
        if clase_destino is None or clase_destino.id_diagrama != diagrama_id:
            raise ValidationError("La clase destino no pertenece a este diagrama")
        if datos.id_clase_origen == datos.id_clase_destino:
            raise ValidationError(
                "Una clase no puede relacionarse consigo misma por esta vía"
            )

        # Validar duplicado exacto
        if await self.relaciones.exists_entre_clases(
            diagrama_id,
            datos.id_clase_origen,
            datos.id_clase_destino,
            datos.tipo_relacion,
        ):
            raise ConflictError(
                "Ya existe una relación de ese tipo entre esas dos clases"
            )

        self._validar_multiplicidad(datos.multiplicidad_origen)
        self._validar_multiplicidad(datos.multiplicidad_destino)

        relacion = RelacionUML(
            id_diagrama=diagrama_id,
            id_clase_origen=datos.id_clase_origen,
            id_clase_destino=datos.id_clase_destino,
            tipo_relacion=datos.tipo_relacion,
            multiplicidad_origen=datos.multiplicidad_origen,
            multiplicidad_destino=datos.multiplicidad_destino,
            nombre_asociacion=datos.nombre_asociacion,
            rol_origen=datos.rol_origen,
            rol_destino=datos.rol_destino,
        )
        relacion = await self.relaciones.create(relacion)
        await self.db.commit()
        await self.db.refresh(relacion)
        return RelacionUMLResponse.model_validate(relacion)

    async def listar_relaciones(
        self, diagrama_id: int, *, usuario_id: int
    ) -> Sequence[RelacionUMLResponse]:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        items = await self.relaciones.list_by_diagrama(diagrama_id)
        return [RelacionUMLResponse.model_validate(r) for r in items]

    async def actualizar_relacion(
        self,
        relacion_id: int,
        datos: RelacionUMLUpdate,
        *,
        usuario_id: int,
    ) -> RelacionUMLResponse:
        relacion = await self.relaciones.get_by_id(relacion_id)
        if relacion is None:
            raise NotFoundError("Relación no encontrada")

        diagrama = await self.diagramas.get_by_id(relacion.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        ##await self._require_editor(relacion.diagrama.id_proyecto, usuario_id)

        if datos.id_clase_origen is not None:
            relacion.id_clase_origen = datos.id_clase_origen
        if datos.id_clase_destino is not None:
            relacion.id_clase_destino = datos.id_clase_destino
        if datos.tipo_relacion is not None:
            relacion.tipo_relacion = datos.tipo_relacion
        if datos.multiplicidad_origen is not None:
            self._validar_multiplicidad(datos.multiplicidad_origen)
            relacion.multiplicidad_origen = datos.multiplicidad_origen
        if datos.multiplicidad_destino is not None:
            self._validar_multiplicidad(datos.multiplicidad_destino)
            relacion.multiplicidad_destino = datos.multiplicidad_destino
        if datos.nombre_asociacion is not None:
            relacion.nombre_asociacion = datos.nombre_asociacion
        if datos.rol_origen is not None:
            relacion.rol_origen = datos.rol_origen
        if datos.rol_destino is not None:
            relacion.rol_destino = datos.rol_destino

        await self.relaciones.update(relacion)
        await self.db.commit()
        await self.db.refresh(relacion)
        return RelacionUMLResponse.model_validate(relacion)

    async def eliminar_relacion(self, relacion_id: int, *, usuario_id: int) -> None:
        relacion = await self.relaciones.get_by_id(relacion_id)
        if relacion is None:
            raise NotFoundError("Relación no encontrada")

        diagrama = await self.diagramas.get_by_id(relacion.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        ##await self._require_editor(relacion.diagrama.id_proyecto, usuario_id)
        await self.relaciones.delete(relacion)
        await self.db.commit()

    # ==================================================================
    # HELPERS INTERNOS
    # ==================================================================
    async def _get_diagrama_o_404(self, diagrama_id: int) -> Diagrama:
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        return diagrama

    async def _require_miembro(self, proyecto_id: int, usuario_id: int) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(proyecto_id, usuario_id)
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")

    async def _require_editor(self, proyecto_id: int, usuario_id: int) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(proyecto_id, usuario_id)
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ValidationError(
                "Se requiere rol EDITOR o PROPIETARIO para modificar el diagrama"
            )

    async def _require_miembro_de_clase(
        self, clase: ClaseUML, usuario_id: int
    ) -> None:
        diagrama = await self.diagramas.get_by_id(clase.id_diagrama)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

    async def _clase_response_con_detalle(self, clase_id: int) -> ClaseUMLResponse:
        clase = await self.clases.get_con_detalle(clase_id)
        return ClaseUMLResponse.model_validate(clase)

    async def _crear_atributo_interno(
        self, clase_id: int, datos: AtributoUMLCreate
    ) -> AtributoUML:
        orden = datos.orden
        if orden == 0:
            orden = await self.atributos.next_orden(clase_id)
        attr = AtributoUML(
            id_clase=clase_id,
            nombre=datos.nombre.strip(),
            tipo_dato=datos.tipo_dato,
            visibilidad=datos.visibilidad,
            es_estatico=datos.es_estatico,
            valor_defecto=datos.valor_defecto,
            orden=orden,
        )
        return await self.atributos.create(attr)

    async def _crear_operacion_interna(
        self, clase_id: int, datos: OperacionUMLCreate
    ) -> OperacionUML:
        orden = datos.orden
        if orden == 0:
            orden = await self.operaciones.next_orden(clase_id)
        op = OperacionUML(
            id_clase=clase_id,
            nombre=datos.nombre.strip(),
            tipo_retorno=datos.tipo_retorno,
            visibilidad=datos.visibilidad,
            es_estatico=datos.es_estatico,
            orden=orden,
        )
        return await self.operaciones.create(op)

    async def _crear_parametro_interno(
        self, operacion_id: int, datos: ParametroOperacionUMLCreate
    ) -> ParametroOperacionUML:
        orden = datos.orden
        if orden == 0:
            orden = await self.parametros.next_orden(operacion_id)
        param = ParametroOperacionUML(
            id_operacion=operacion_id,
            nombre=datos.nombre.strip(),
            tipo_dato=datos.tipo_dato,
            orden=orden,
        )
        return await self.parametros.create(param)

    async def _crear_op_interfaz_interna(
        self, interfaz_id: int, datos: OperacionInterfazUMLCreate
    ) -> OperacionInterfazUML:
        op = OperacionInterfazUML(
            id_interfaz=interfaz_id,
            nombre=datos.nombre.strip(),
            tipo_retorno=datos.tipo_retorno,
        )
        return await self.ops_interfaz.create(op)

    def _validar_nombre_uml(self, nombre: str) -> None:
        """Validación mínima de identificador UML (letras, dígitos, _)."""
        if not nombre or not nombre.strip():
            raise ValidationError("El nombre no puede estar vacío")
        if not nombre.replace("_", "").isalnum():
            raise ValidationError(
                "El nombre solo puede contener letras, dígitos y guiones bajos"
            )
        if nombre[0].isdigit():
            raise ValidationError("El nombre no puede empezar con un dígito")

    def _validar_multiplicidad(self, multiplicidad: Optional[str]) -> None:
        """Acepta patrones típicos: 1, 0..1, 1..*, *, 0..*, n, 1..n."""
        if multiplicidad is None:
            return
        m = multiplicidad.strip()
        if m in ("1", "0..1", "*", "0..*", "1..*", "n", "1..n"):
            return
        raise ValidationError(f"Multiplicidad inválida: '{multiplicidad}'")