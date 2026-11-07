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

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Servicio SIN ESTADO: sin AsyncSession ni commit()/refresh()/rollback().
  Cada create()/update()/delete() del repositorio persiste de inmediato
  (1 documento Diagrama = 1 escritura coherente, la misma que consume el
  WebSocket de colaboración y el Agente Dev).
- En el Ciclo 1 el diagrama se dispersaba en 7 tablas; en el Ciclo 2 las
  clases, atributos, operaciones, parámetros, interfaces, sus operaciones
  y las relaciones van EMBEBIDAS en el documento Diagrama. Consecuencias:
    * Los ids de esos elementos pasan de int (serial) a str uuid.
    * Los embebidos no conocen a su padre: los get_by_id() de los
      repositorios devuelven el elemento en LECTURA, y para MODIFICARLO
      hay que mutarlo DENTRO del documento padre re-leído. Los helpers
      _resolver_* devuelven ese par (documento, elementos) en una sola
      consulta por campo anidado (regla fetch → modificar → save).
    * crear_relacion valida que las clases pertenezcan al diagrama con
      diagrama.clase(id): sustituye a las 2 consultas por FK del Ciclo 1.
- Sin re-lecturas post-commit para armar respuestas (los
  get_con_parametros()/get_con_operaciones() del Ciclo 1 cargaban lo que
  ahora ya vive embebido en el elemento en mano). Se conserva la
  re-lectura final de _clase_response_con_detalle, igual que en el Ciclo 1.
- OJO: cada save() de Beanie RE-INSTANCIA los embebidos del documento y
  deja desligadas las referencias en mano. Por eso los creadores internos
  re-vinculan el elemento sobre el documento (diagrama.clase(id),
  diagrama.interfaz(id), clase.operacion(id)) ANTES de cada mutación
  encadenada, y las respuestas de crear_clase/agregar_operacion/
  crear_interfaz se arman desde la instancia re-vinculada.
- Sin try/except con rollback(): MongoDB no tiene transacciones que
  revertir y los errores de negocio (404/409/422) se lanzan ANTES de
  mutar el embebido. Desaparecen los print() de depuración del 500 del
  Ciclo 1 (se conserva el logger.info del payload en actualizar_clase).
- updated_at se fija en el service al modificar (el onupdate de
  SQLAlchemy no existe en MongoDB).

Cada cambio significativo se registra en `historial_cambios_diagrama`
(vía TrazabilidadService) para que el editor pueda deshacer y detectar
conflictos entre colaboradores.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from beanie import PydanticObjectId

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

logger = logging.getLogger("devforge.diagrama")


class DiagramaService:
    """CRUD del diagrama UML y de todos sus elementos embebidos."""

    def __init__(self) -> None:
        self.diagramas = DiagramaRepository()
        self.clases = ClaseUMLRepository()
        self.atributos = AtributoUMLRepository()
        self.operaciones = OperacionUMLRepository()
        self.parametros = ParametroOperacionUMLRepository()
        self.interfaces = InterfazUMLRepository()
        self.ops_interfaz = OperacionInterfazUMLRepository()
        self.relaciones = RelacionUMLRepository()
        self.miembros = MiembroProyectoRepository()

    # ==================================================================
    # DIAGRAMA
    # ==================================================================
    async def listar_por_proyecto(
        self,
        proyecto_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[DiagramaResponse]:
        await self._require_miembro(proyecto_id, usuario_id)
        items = await self.diagramas.list_by_proyecto(
            proyecto_id, skip=skip, limit=limit
        )
        return [DiagramaResponse.model_validate(d) for d in items]

    async def obtener(
        self, diagrama_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> DiagramaResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        return DiagramaResponse.model_validate(diagrama)

    async def obtener_completo(
        self, diagrama_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> DiagramaCompletoResponse:
        """
        Devuelve el diagrama con todas sus clases (y atributos/operaciones/
        parámetros), interfaces (y sus operaciones) y relaciones.
        Es el payload que consume el editor.

        En el Ciclo 2 TODO va embebido: una sola lectura del documento trae
        el lienzo completo (antes encadenaba 4 selectinload).
        """
        diagrama = await self.diagramas.get_completo(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        return DiagramaCompletoResponse.model_validate(diagrama)

    async def crear(
        self,
        proyecto_id: PydanticObjectId,
        datos: DiagramaCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> DiagramaResponse:
        await self._require_miembro(proyecto_id, usuario_id)
        diagrama = Diagrama(
            id_proyecto=proyecto_id,
            nombre=datos.nombre.strip(),
            version_uml=datos.version_uml,
            numero_version=1,
            id_creador=usuario_id,
        )
        # insert() asigna el ObjectId y persiste: sin commit/refresh
        diagrama = await self.diagramas.create(diagrama)
        return DiagramaResponse.model_validate(diagrama)

    async def actualizar(
        self,
        diagrama_id: PydanticObjectId,
        datos: DiagramaUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> DiagramaResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            diagrama.nombre = datos.nombre.strip()
        if datos.version_uml is not None:
            diagrama.version_uml = datos.version_uml
        diagrama.updated_at = datetime.now(timezone.utc)

        await self.diagramas.update(diagrama)
        return DiagramaResponse.model_validate(diagrama)

    async def eliminar(
        self, diagrama_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        # Las clases/atributos/relaciones viven EMBEBIDAS: desaparecen con
        # el documento (en el Ciclo 1 lo hacían los ON DELETE CASCADE).
        await self.diagramas.delete(diagrama)

    # ==================================================================
    # CLASES UML
    # ==================================================================
    async def crear_clase(
        self,
        diagrama_id: PydanticObjectId,
        datos: ClaseUMLCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> ClaseUMLResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        # Validación UML: nombre único en el diagrama
        if await self.clases.exists_nombre_en_diagrama(diagrama_id, datos.nombre):
            raise ConflictError(
                f"Ya existe una clase con el nombre '{datos.nombre}' en este diagrama"
            )
        self._validar_nombre_uml(datos.nombre)

        # El id uuid lo genera el modelo embebido
        clase = ClaseUML(
            nombre=datos.nombre.strip(),
            es_abstracta=datos.es_abstracta,
            estereotipo=datos.estereotipo,
            pos_x=datos.pos_x,
            pos_y=datos.pos_y,
            id_creador=usuario_id,
        )
        clase = await self.clases.create(diagrama, clase)

        # Crear atributos y operaciones anidados (si vienen en el payload).
        # Los creadores internos re-vinculan los embebidos en cada paso
        # (cada save() de Beanie re-instancia el contenido del documento).
        for attr in datos.atributos:
            await self._crear_atributo_interno(diagrama, clase, attr)
        for op in datos.operaciones:
            op_creada = await self._crear_operacion_interno(diagrama, clase, op)
            for param in op.parametros:
                await self._crear_parametro_interno(diagrama, clase, op_creada, param)

        return await self._clase_response_con_detalle(clase.id)

    async def listar_clases(
        self, diagrama_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> Sequence[ClaseUMLResponse]:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        clases = await self.clases.list_by_diagrama(diagrama_id)
        return [ClaseUMLResponse.model_validate(c) for c in clases]

    async def obtener_clase(
        self, clase_id: str, *, usuario_id: PydanticObjectId
    ) -> ClaseUMLResponse:
        clase = await self.clases.get_con_detalle(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        await self._require_miembro_de_clase(clase_id, usuario_id)
        return ClaseUMLResponse.model_validate(clase)

    async def actualizar_clase(
        self,
        clase_id: str,
        datos: ClaseUMLUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> ClaseUMLResponse:
        # ------------------------------------------------------------------
        # 1) Cargar clase (documento padre re-leído) y validar permisos
        # ------------------------------------------------------------------
        diagrama, clase = await self._resolver_clase(clase_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        # ------------------------------------------------------------------
        # 2) Log del payload que llega (se conserva del Ciclo 1)
        # ------------------------------------------------------------------
        payload = datos.model_dump(exclude_unset=True)
        logger.info(
            "[actualizar_clase] id=%s usuario=%s payload=%s",
            clase_id,
            usuario_id,
            payload,
        )

        # ------------------------------------------------------------------
        # 3) Aplicar cambios al embebido (los errores de negocio se lanzan
        #    ANTES de guardar: sin transacción no hay nada que revertir)
        # ------------------------------------------------------------------
        if datos.nombre is not None:
            self._validar_nombre_uml(datos.nombre)
            if await self.clases.exists_nombre_en_diagrama(
                diagrama.id, datos.nombre, exclude_id=clase.id
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
        clase.updated_at = datetime.now(timezone.utc)

        # ------------------------------------------------------------------
        # 4) Persistir (save() del documento completo: sin commit)
        # ------------------------------------------------------------------
        await self.clases.update(diagrama, clase)
        logger.info("[actualizar_clase] guardado OK id=%s", clase_id)

        # ------------------------------------------------------------------
        # 5) Devolver respuesta con detalle
        # ------------------------------------------------------------------
        return await self._clase_response_con_detalle(clase.id)

    async def eliminar_clase(
        self, clase_id: str, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama, clase = await self._resolver_clase(clase_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        # Eliminar relaciones asociadas. En el Ciclo 1 se hacía explícito
        # para dejar el historial limpio; aquí son embebidas del MISMO
        # documento y se van en el save() de la clase.
        await self.relaciones.delete_by_clase(diagrama, clase_id)
        await self.clases.delete(diagrama, clase)

    # ==================================================================
    # ATRIBUTOS
    # ==================================================================
    async def agregar_atributo(
        self,
        clase_id: str,
        datos: AtributoUMLCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> AtributoUMLResponse:
        diagrama, clase = await self._resolver_clase(clase_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        attr = await self._crear_atributo_interno(diagrama, clase, datos)
        return AtributoUMLResponse.model_validate(attr)

    async def listar_atributos(
        self, clase_id: str, *, usuario_id: PydanticObjectId
    ) -> Sequence[AtributoUMLResponse]:
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        await self._require_miembro_de_clase(clase_id, usuario_id)
        items = await self.atributos.list_by_clase(clase)
        return [AtributoUMLResponse.model_validate(a) for a in items]

    async def actualizar_atributo(
        self,
        atributo_id: str,
        datos: AtributoUMLUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> AtributoUMLResponse:
        diagrama, clase, attr = await self._resolver_atributo(atributo_id)
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

        await self.atributos.update(diagrama, attr)
        return AtributoUMLResponse.model_validate(attr)

    async def eliminar_atributo(
        self, atributo_id: str, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama, clase, attr = await self._resolver_atributo(atributo_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.atributos.delete(diagrama, clase, attr)

    # ==================================================================
    # OPERACIONES
    # ==================================================================
    async def agregar_operacion(
        self,
        clase_id: str,
        datos: OperacionUMLCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> OperacionUMLResponse:
        diagrama, clase = await self._resolver_clase(clase_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        op = await self._crear_operacion_interno(diagrama, clase, datos)
        for param in datos.parametros:
            await self._crear_parametro_interno(diagrama, clase, op, param)

        # Los parámetros ya viven embebidos: sin re-lectura. Solo hay que
        # RE-VINCULAR op sobre el documento (los save() de los creadores
        # re-instanciaron los embebidos).
        clase = diagrama.clase(clase.id)
        op = clase.operacion(op.id)
        return OperacionUMLResponse.model_validate(op)

    async def listar_operaciones(
        self, clase_id: str, *, usuario_id: PydanticObjectId
    ) -> Sequence[OperacionUMLResponse]:
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise NotFoundError("Clase no encontrada")
        await self._require_miembro_de_clase(clase_id, usuario_id)
        ops = await self.operaciones.list_by_clase(clase)
        return [OperacionUMLResponse.model_validate(o) for o in ops]

    async def actualizar_operacion(
        self,
        operacion_id: str,
        datos: OperacionUMLUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> OperacionUMLResponse:
        diagrama, clase, op = await self._resolver_operacion(operacion_id)
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

        await self.operaciones.update(diagrama, op)
        # Los parámetros ya viven embebidos: sin re-lectura
        return OperacionUMLResponse.model_validate(op)

    async def eliminar_operacion(
        self, operacion_id: str, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama, clase, op = await self._resolver_operacion(operacion_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.operaciones.delete(diagrama, clase, op)

    # ==================================================================
    # PARÁMETROS DE OPERACIÓN
    # ==================================================================
    async def agregar_parametro(
        self,
        operacion_id: str,
        datos: ParametroOperacionUMLCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> ParametroOperacionUMLResponse:
        diagrama, clase, op = await self._resolver_operacion(operacion_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        param = await self._crear_parametro_interno(diagrama, clase, op, datos)
        return ParametroOperacionUMLResponse.model_validate(param)

    async def actualizar_parametro(
        self,
        parametro_id: str,
        datos: ParametroOperacionUMLUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> ParametroOperacionUMLResponse:
        diagrama, clase, op, param = await self._resolver_parametro(parametro_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            param.nombre = datos.nombre.strip()
        if datos.tipo_dato is not None:
            param.tipo_dato = datos.tipo_dato
        if datos.orden is not None:
            param.orden = datos.orden

        await self.parametros.update(diagrama, param)
        return ParametroOperacionUMLResponse.model_validate(param)

    async def eliminar_parametro(
        self, parametro_id: str, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama, clase, op, param = await self._resolver_parametro(parametro_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.parametros.delete(diagrama, op, param)

    # ==================================================================
    # INTERFACES UML
    # ==================================================================
    async def crear_interfaz(
        self,
        diagrama_id: PydanticObjectId,
        datos: InterfazUMLCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> InterfazUMLResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        interfaz = InterfazUML(
            nombre=datos.nombre.strip(),
            pos_x=datos.pos_x,
            pos_y=datos.pos_y,
        )
        interfaz = await self.interfaces.create(diagrama, interfaz)

        for op in datos.operaciones:
            await self._crear_op_interfaz_interno(diagrama, interfaz, op)

        # Las operaciones ya viven embebidas: sin re-lectura. Se
        # RE-VINCULA la interfaz (los save() re-instanciaron los embebidos)
        interfaz = diagrama.interfaz(interfaz.id)
        return InterfazUMLResponse.model_validate(interfaz)

    async def actualizar_interfaz(
        self,
        interfaz_id: str,
        datos: InterfazUMLUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> InterfazUMLResponse:
        diagrama, interfaz = await self._resolver_interfaz(interfaz_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            interfaz.nombre = datos.nombre.strip()
        if datos.pos_x is not None:
            interfaz.pos_x = datos.pos_x
        if datos.pos_y is not None:
            interfaz.pos_y = datos.pos_y

        await self.interfaces.update(diagrama, interfaz)
        return InterfazUMLResponse.model_validate(interfaz)

    async def eliminar_interfaz(
        self, interfaz_id: str, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama, interfaz = await self._resolver_interfaz(interfaz_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.interfaces.delete(diagrama, interfaz)

    # ==================================================================
    # OPERACIONES DE INTERFAZ
    # ==================================================================
    async def agregar_op_interfaz(
        self,
        interfaz_id: str,
        datos: OperacionInterfazUMLCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> OperacionInterfazUMLResponse:
        diagrama, interfaz = await self._resolver_interfaz(interfaz_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        op = await self._crear_op_interfaz_interno(diagrama, interfaz, datos)
        return OperacionInterfazUMLResponse.model_validate(op)

    async def actualizar_op_interfaz(
        self,
        operacion_id: str,
        datos: OperacionInterfazUMLUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> OperacionInterfazUMLResponse:
        diagrama, interfaz, op = await self._resolver_op_interfaz(operacion_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        if datos.nombre is not None:
            op.nombre = datos.nombre.strip()
        if datos.tipo_retorno is not None:
            op.tipo_retorno = datos.tipo_retorno

        await self.ops_interfaz.update(diagrama, op)
        return OperacionInterfazUMLResponse.model_validate(op)

    async def eliminar_op_interfaz(
        self, operacion_id: str, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama, interfaz, op = await self._resolver_op_interfaz(operacion_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.ops_interfaz.delete(diagrama, interfaz, op)

    # ==================================================================
    # RELACIONES
    # ==================================================================
    async def crear_relacion(
        self,
        diagrama_id: PydanticObjectId,
        datos: RelacionUMLCreate,
        *,
        usuario_id: PydanticObjectId,
    ) -> RelacionUMLResponse:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        # Validar que ambas clases pertenecen al mismo diagrama. Son
        # EMBEBIDAS: diagrama.clase(id) sustituye a las 2 consultas por FK
        # del Ciclo 1 (un uuid de otro diagrama no existe aquí y cae en el
        # mismo mensaje de error).
        if diagrama.clase(datos.id_clase_origen) is None:
            raise ValidationError("La clase origen no pertenece a este diagrama")
        if diagrama.clase(datos.id_clase_destino) is None:
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
            id_clase_origen=datos.id_clase_origen,
            id_clase_destino=datos.id_clase_destino,
            tipo_relacion=datos.tipo_relacion,
            multiplicidad_origen=datos.multiplicidad_origen,
            multiplicidad_destino=datos.multiplicidad_destino,
            nombre_asociacion=datos.nombre_asociacion,
            rol_origen=datos.rol_origen,
            rol_destino=datos.rol_destino,
        )
        # Inserta el embebido y hace save() del documento padre
        relacion = await self.relaciones.create(diagrama, relacion)
        return RelacionUMLResponse.model_validate(relacion)

    async def listar_relaciones(
        self, diagrama_id: PydanticObjectId, *, usuario_id: PydanticObjectId
    ) -> Sequence[RelacionUMLResponse]:
        diagrama = await self._get_diagrama_o_404(diagrama_id)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)
        items = await self.relaciones.list_by_diagrama(diagrama_id)
        return [RelacionUMLResponse.model_validate(r) for r in items]

    async def actualizar_relacion(
        self,
        relacion_id: str,
        datos: RelacionUMLUpdate,
        *,
        usuario_id: PydanticObjectId,
    ) -> RelacionUMLResponse:
        diagrama, relacion = await self._resolver_relacion(relacion_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)

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

        await self.relaciones.update(diagrama, relacion)
        return RelacionUMLResponse.model_validate(relacion)

    async def eliminar_relacion(
        self, relacion_id: str, *, usuario_id: PydanticObjectId
    ) -> None:
        diagrama, relacion = await self._resolver_relacion(relacion_id)
        await self._require_editor(diagrama.id_proyecto, usuario_id)
        await self.relaciones.delete(diagrama, relacion)

    # ==================================================================
    # HELPERS INTERNOS
    # ==================================================================
    async def _get_diagrama_o_404(
        self, diagrama_id: PydanticObjectId
    ) -> Diagrama:
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        return diagrama

    async def _require_miembro(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> None:
        # El miembro vive EMBEBIDO en el proyecto: el repositorio re-lee
        # el documento Proyecto y busca en su lista miembros.
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            # 404 para no revelar existencia de proyectos ajenos
            raise NotFoundError("Recurso no encontrado")

    async def _require_editor(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ValidationError(
                "Se requiere rol EDITOR o PROPIETARIO para modificar el diagrama"
            )

    async def _require_miembro_de_clase(
        self, clase_id: str, usuario_id: PydanticObjectId
    ) -> None:
        """Permiso de LECTURA sobre una clase embebida. (En el Ciclo 1
        recibía la clase y leía clase.id_diagrama; el embebido no conoce a
        su padre, así que se resuelve el Diagrama por el id uuid.)"""
        diagrama = await self.clases.get_diagrama_de_clase(clase_id)
        if diagrama is None:
            raise NotFoundError("Recurso no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

    async def _clase_response_con_detalle(self, clase_id: str) -> ClaseUMLResponse:
        clase = await self.clases.get_con_detalle(clase_id)
        return ClaseUMLResponse.model_validate(clase)

    # ------------------------------------------------------------------
    # Resolución ESCRIBIBLE de los embebidos
    # (regla fetch → modificar → save de la Tanda 9)
    # ------------------------------------------------------------------
    # Los get_by_id() de los repositorios devuelven el elemento en
    # LECTURA. Para MODIFICARLO hay que mutarlo DENTRO del documento padre
    # re-leído y guardar el padre; estos helpers devuelven ese par
    # (documento, elementos) en UNA consulta sobre el campo anidado.
    # ------------------------------------------------------------------
    async def _resolver_clase(self, clase_id: str) -> tuple[Diagrama, ClaseUML]:
        """(Diagrama re-leído, clase embebida). NotFoundError si no existe."""
        diagrama = await self.clases.get_diagrama_de_clase(clase_id)
        if diagrama is None:
            raise NotFoundError("Clase no encontrada")
        return diagrama, diagrama.clase(clase_id)

    async def _resolver_atributo(
        self, atributo_id: str
    ) -> tuple[Diagrama, ClaseUML, AtributoUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.clases.atributos.id == atributo_id
        )
        if diagrama is None:
            raise NotFoundError("Atributo no encontrado")
        for clase in diagrama.clases:
            attr = clase.atributo(atributo_id)
            if attr is not None:
                return diagrama, clase, attr
        raise NotFoundError("Atributo no encontrado")

    async def _resolver_operacion(
        self, operacion_id: str
    ) -> tuple[Diagrama, ClaseUML, OperacionUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.clases.operaciones.id == operacion_id
        )
        if diagrama is None:
            raise NotFoundError("Operación no encontrada")
        for clase in diagrama.clases:
            op = clase.operacion(operacion_id)
            if op is not None:
                return diagrama, clase, op
        raise NotFoundError("Operación no encontrada")

    async def _resolver_parametro(
        self, parametro_id: str
    ) -> tuple[Diagrama, ClaseUML, OperacionUML, ParametroOperacionUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.clases.operaciones.parametros.id == parametro_id
        )
        if diagrama is None:
            raise NotFoundError("Parámetro no encontrado")
        for clase in diagrama.clases:
            for op in clase.operaciones:
                for param in op.parametros:
                    if param.id == parametro_id:
                        return diagrama, clase, op, param
        raise NotFoundError("Parámetro no encontrado")

    async def _resolver_interfaz(
        self, interfaz_id: str
    ) -> tuple[Diagrama, InterfazUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.interfaces.id == interfaz_id
        )
        if diagrama is None:
            raise NotFoundError("Interfaz no encontrada")
        return diagrama, diagrama.interfaz(interfaz_id)

    async def _resolver_op_interfaz(
        self, operacion_id: str
    ) -> tuple[Diagrama, InterfazUML, OperacionInterfazUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.interfaces.operaciones.id == operacion_id
        )
        if diagrama is None:
            raise NotFoundError("Operación de interfaz no encontrada")
        for interfaz in diagrama.interfaces:
            for op in interfaz.operaciones:
                if op.id == operacion_id:
                    return diagrama, interfaz, op
        raise NotFoundError("Operación de interfaz no encontrada")

    async def _resolver_relacion(
        self, relacion_id: str
    ) -> tuple[Diagrama, RelacionUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.relaciones.id == relacion_id
        )
        if diagrama is None:
            raise NotFoundError("Relación no encontrada")
        return diagrama, diagrama.relacion(relacion_id)

    # ------------------------------------------------------------------
    # Creadores internos (insertan el embebido y persisten el padre)
    # ------------------------------------------------------------------
    async def _crear_atributo_interno(
        self,
        diagrama: Diagrama,
        clase: ClaseUML,
        datos: AtributoUMLCreate,
    ) -> AtributoUML:
        """Crea el atributo embebido y persiste el documento. (En el
        Ciclo 1 recibía el id int de la clase; ahora el par
        documento+clase re-leídos.)

        Re-vincula la clase sobre el documento ANTES de mutar: cada
        save() de Beanie re-instancia los embebidos y deja desligadas
        las referencias de los pasos anteriores."""
        clase = diagrama.clase(clase.id)
        orden = datos.orden
        if orden == 0:
            orden = await self.atributos.next_orden(clase)
        attr = AtributoUML(
            nombre=datos.nombre.strip(),
            tipo_dato=datos.tipo_dato,
            visibilidad=datos.visibilidad,
            es_estatico=datos.es_estatico,
            valor_defecto=datos.valor_defecto,
            orden=orden,
        )
        return await self.atributos.create(diagrama, clase, attr)

    async def _crear_operacion_interno(
        self,
        diagrama: Diagrama,
        clase: ClaseUML,
        datos: OperacionUMLCreate,
    ) -> OperacionUML:
        # Re-vincula la clase (el save() anterior re-instanció embebidos)
        clase = diagrama.clase(clase.id)
        orden = datos.orden
        if orden == 0:
            orden = await self.operaciones.next_orden(clase)
        op = OperacionUML(
            nombre=datos.nombre.strip(),
            tipo_retorno=datos.tipo_retorno,
            visibilidad=datos.visibilidad,
            es_estatico=datos.es_estatico,
            orden=orden,
        )
        return await self.operaciones.create(diagrama, clase, op)

    async def _crear_parametro_interno(
        self,
        diagrama: Diagrama,
        clase: ClaseUML,
        operacion: OperacionUML,
        datos: ParametroOperacionUMLCreate,
    ) -> ParametroOperacionUML:
        # Re-vincula clase y operación (los save() previos re-instanciaron
        # los embebidos del documento)
        clase = diagrama.clase(clase.id)
        operacion = clase.operacion(operacion.id)
        orden = datos.orden
        if orden == 0:
            orden = await self.parametros.next_orden(operacion)
        param = ParametroOperacionUML(
            nombre=datos.nombre.strip(),
            tipo_dato=datos.tipo_dato,
            orden=orden,
        )
        return await self.parametros.create(diagrama, operacion, param)

    async def _crear_op_interfaz_interno(
        self,
        diagrama: Diagrama,
        interfaz: InterfazUML,
        datos: OperacionInterfazUMLCreate,
    ) -> OperacionInterfazUML:
        # Re-vincula la interfaz (el save() anterior re-instanció embebidos)
        interfaz = diagrama.interfaz(interfaz.id)
        op = OperacionInterfazUML(
            nombre=datos.nombre.strip(),
            tipo_retorno=datos.tipo_retorno,
        )
        return await self.ops_interfaz.create(diagrama, interfaz, op)

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