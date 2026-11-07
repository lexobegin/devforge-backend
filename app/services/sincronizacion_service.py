# app/services/sincronizacion_service.py
"""
Lógica de negocio del módulo H. Sincronización Móvil/Web Offline.

Cubre:
- Recibir un batch de cambios offline desde el cliente (móvil o web).
- Aplicarlos al diagrama resolviendo ids temporales locales.
- Detectar conflictos y, según gravedad:
    * Resolución automática ("último en escribir gana") para cambios simples.
    * Marcar como CONFLICTO para revisión manual del PROPIETARIO.
- Permitir al PROPIETARIO resolver un conflicto (OFFLINE / SERVIDOR / FUSIONAR).

Estrategia:
- Los cambios vienen en `BatchSincronizacionRequest` con `id_temporal_local`.
- El backend procesa en orden FIFO (mismo orden en que se hicieron offline).
- El resultado mapea id_temporal_local → id real (o marca conflicto).

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Servicio SIN ESTADO: sin AsyncSession ni commit()/refresh(). Cada
  create()/save()/marcar_*() del repositorio persiste de inmediato. En el
  Ciclo 1 el batch consolidaba TODO en un db.commit() final (una
  transacción); en el Ciclo 2 cada cambio queda escrito en su momento:
  si un ítem del batch falla, los anteriores YA están aplicados (el
  cliente los ve en el mapeo id_temporal_local → id_real y no los
  reenvía: la idempotencia por id_dispositivo + id_temporal_local
  sustituye a la transacción).
- Ids: usuario_id/diagrama_id/conflicto_id pasan de int a
  PydanticObjectId. DENTRO del payload el formato también cambia:
  id_diagrama es el str del ObjectId del diagrama, y los ids de
  elementos (id_clase, id_atributo, id_relacion…) son los uuid de los
  EMBEBIDOS del documento — exactamente los mismos que el batch devuelve
  en ResultadoCambioSync.id_real (Optional[str]) al crearlos.
- Los 7 elementos UML van EMBEBIDOS en el Diagrama: las operaciones
  siguen usando los repositorios de diagrama_repository, pero con la
  REGLA DEL MÓDULO: las escrituras reciben el Diagrama RE-LEÍDO
  (fetch → modificar → save del padre) y el id real de un elemento es
  su uuid, no un serial int.
- _aplicar_cambio_offline devuelve Optional[str] (uuid del embebido o
  str del ObjectId) donde el Ciclo 1 devolvía int.
- updated_at se fija en el service (el onupdate de SQLAlchemy no
  existe): toda mutación del lienzo refresca diagrama.updated_at y, si
  toca una clase o su contenido, clase.updated_at (los embebidos
  atributos/relaciones no llevan updated_at en el modelo del Ciclo 2).
- Helpers de payload: _require_int desaparece (no hay ids enteros) y
  entra _require_objectid para id_diagrama (mensaje adaptado:
  "debe ser un id válido"); _require_str conserva sus mensajes
  idénticos para nombre y para los uuid de elementos.
- _require_editor/_require_propietario resuelven el miembro EMBEBIDO
  con MiembroProyectoRepository.get_by_proyecto_usuario (mensajes
  idénticos al Ciclo 1).
- sesiones/participantes se siguen instanciando como en el Ciclo 1
  (quedan para la extensión de presencias offline; sin uso todavía).
"""

from datetime import datetime, timezone
from typing import Any, Optional

from beanie import PydanticObjectId

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.diagrama import (
    AtributoUML,
    ClaseUML,
    Diagrama,
    RelacionUML,
)
from app.models.sincronizacion import ColaSincronizacionMovil
from app.repositories.colaboracion_repository import (
    ParticipanteSesionRepository,
    SesionColaboracionRepository,
)
from app.repositories.diagrama_repository import (
    AtributoUMLRepository,
    ClaseUMLRepository,
    DiagramaRepository,
    RelacionUMLRepository,
)
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.repositories.sincronizacion_repository import (
    ColaSincronizacionRepository,
)
from app.schemas.sincronizacion_schema import (
    BatchSincronizacionRequest,
    BatchSincronizacionResponse,
    CambioOfflineItem,
    ConflictoSyncResponse,
    ResultadoCambioSync,
)


def _ahora() -> datetime:
    """Fecha aware para updated_at (el utcnow() naive del Ciclo 1 se
    descarta)."""
    return datetime.now(timezone.utc)


def _recortar_motivo(texto: str, maximo: int = 255) -> str:
    """Recorta el motivo de conflicto al max_length del DTO
    ResultadoCambioSync (255). En el Ciclo 1 el detalle completo iba en un
    JSONB sin límite; los ValidationError de pydantic pueden excederlo y el
    ítem NO debe fallar por su propio mensaje (hallazgo del arnés)."""
    texto = str(texto)
    if len(texto) <= maximo:
        return texto
    return texto[: maximo - 1] + "…"


class SincronizacionService:
    def __init__(self) -> None:
        self.cola = ColaSincronizacionRepository()
        self.diagramas = DiagramaRepository()
        self.clases = ClaseUMLRepository()
        self.atributos = AtributoUMLRepository()
        self.relaciones = RelacionUMLRepository()
        self.miembros = MiembroProyectoRepository()
        self.sesiones = SesionColaboracionRepository()
        self.participantes = ParticipanteSesionRepository()

    # ==================================================================
    # PROCESAMIENTO DE BATCH OFFLINE
    # ==================================================================
    async def procesar_batch(
        self,
        datos: BatchSincronizacionRequest,
        *,
        usuario_id: PydanticObjectId,
    ) -> BatchSincronizacionResponse:
        """
        Procesa un lote de cambios offline aplicándolos al diagrama.
        Devuelve el mapeo de ids temporales → ids reales y el detalle
        de conflictos detectados.
        """
        # Verificar permisos del usuario sobre el diagrama
        diagrama = await self.diagramas.get_by_id(datos.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        resultados: list[ResultadoCambioSync] = []
        total_sync = 0
        total_conf = 0

        # Procesar cambios en orden FIFO
        for cambio in datos.cambios:
            resultado = await self._procesar_cambio(
                cambio,
                id_dispositivo=datos.id_dispositivo,
                id_diagrama=datos.id_diagrama,
                usuario_id=usuario_id,
            )
            resultados.append(resultado)
            if resultado.estado == "SINCRONIZADO":
                total_sync += 1
            else:
                total_conf += 1

        # (En el Ciclo 1 un db.commit() final consolidaba el batch en una
        #  transacción; en el Ciclo 2 cada ítem ya quedó persistido en su
        #  paso y la idempotencia evita duplicados si el cliente reintenta.)
        return BatchSincronizacionResponse(
            id_dispositivo=datos.id_dispositivo,
            id_diagrama=datos.id_diagrama,
            total_recibidos=len(datos.cambios),
            total_sincronizados=total_sync,
            total_conflictos=total_conf,
            resultados=resultados,
        )

    # ==================================================================
    # CONFLICTOS
    # ==================================================================
    async def listar_conflictos(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> list[ConflictoSyncResponse]:
        """
        Lista los conflictos pendientes de resolución manual en un diagrama.
        Solo el PROPIETARIO del proyecto puede verlos.
        """
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_propietario(diagrama.id_proyecto, usuario_id)

        items = await self.cola.list_conflictos_by_diagrama(diagrama_id)
        return [ConflictoSyncResponse.model_validate(i) for i in items]

    async def resolver_conflicto(
        self,
        conflicto_id: PydanticObjectId,
        *,
        estrategia: str,
        payload_fusionado: Optional[dict[str, Any]] = None,
        usuario_id: PydanticObjectId,
    ) -> ConflictoSyncResponse:
        """
        El PROPIETARIO resuelve un conflicto eligiendo:
        - 'OFFLINE'  → aplicar el cambio offline tal cual.
        - 'SERVIDOR' → descartar el cambio offline.
        - 'FUSIONAR' → aplicar un payload fusionado provisto por el usuario.
        """
        conflicto = await self.cola.get_by_id(conflicto_id)
        if conflicto is None:
            raise NotFoundError("Conflicto no encontrado")
        if conflicto.estado != "CONFLICTO":
            raise ValidationError("El ítem no está marcado como conflicto")

        # id_diagrama es opcional en la cola; si el ítem no está atado a
        # un diagrama, get_by_id(None) → None y cae al 404 igual que el
        # Ciclo 1 (la FK rota nunca existió aquí).
        diagrama = (
            await self.diagramas.get_by_id(conflicto.id_diagrama)
            if conflicto.id_diagrama is not None
            else None
        )
        if diagrama is None:
            raise NotFoundError("Diagrama asociado no encontrado")
        await self._require_propietario(diagrama.id_proyecto, usuario_id)

        if estrategia == "SERVIDOR":
            # Descartar: marcamos como SINCRONIZADO sin aplicar
            item = await self.cola.marcar_sincronizado(conflicto.id)
            if item is None:
                raise NotFoundError("Conflicto no encontrado")
            return ConflictoSyncResponse.model_validate(item)

        if estrategia == "OFFLINE":
            # Aplicar el cambio offline tal cual
            try:
                await self._aplicar_cambio_offline(
                    conflicto.tipo_operacion, conflicto.payload
                )
            except Exception as exc:
                raise ConflictError(
                    f"No se pudo aplicar el cambio offline: {exc}"
                ) from exc
            item = await self.cola.marcar_sincronizado(conflicto.id)
            if item is None:
                raise NotFoundError("Conflicto no encontrado")
            return ConflictoSyncResponse.model_validate(item)

        if estrategia == "FUSIONAR":
            if not payload_fusionado:
                raise ValidationError(
                    "Debe proveer 'payload_fusionado' para estrategia='FUSIONAR'"
                )
            try:
                await self._aplicar_cambio_offline(
                    conflicto.tipo_operacion, payload_fusionado
                )
            except Exception as exc:
                raise ConflictError(
                    f"No se pudo aplicar el payload fusionado: {exc}"
                ) from exc
            item = await self.cola.marcar_sincronizado(conflicto.id)
            if item is None:
                raise NotFoundError("Conflicto no encontrado")
            return ConflictoSyncResponse.model_validate(item)

        raise ValidationError(
            "Estrategia inválida. Use 'OFFLINE', 'SERVIDOR' o 'FUSIONAR'"
        )

    # ==================================================================
    # INTERNOS: procesamiento de cada cambio
    # ==================================================================
    async def _procesar_cambio(
        self,
        cambio: CambioOfflineItem,
        *,
        id_dispositivo: str,
        id_diagrama: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> ResultadoCambioSync:
        """
        Procesa un ítem individual:
        1) Registra en cola (idempotencia por id_dispositivo + id_temporal_local).
        2) Intenta aplicar el cambio.
        3) Marca SINCRONIZADO con id_real, o CONFLICTO si detecta colisión.
        """
        # Idempotencia: si ya existe este cambio, devolvemos su estado actual
        existente = await self.cola.get_by_dispositivo_y_temporal(
            id_dispositivo, cambio.id_temporal_local
        )
        if existente is not None:
            return ResultadoCambioSync(
                id_temporal_local=cambio.id_temporal_local,
                estado=existente.estado,
                id_real=None,
                motivo_conflicto="Ítem ya procesado previamente (idempotencia)"
                if existente.estado == "CONFLICTO"
                else None,
            )

        # Registrar en cola
        item = ColaSincronizacionMovil(
            id_dispositivo=id_dispositivo,
            id_usuario=usuario_id,
            id_diagrama=id_diagrama,
            id_temporal_local=cambio.id_temporal_local,
            tipo_operacion=cambio.tipo_operacion,
            payload=cambio.payload,
            estado="PENDIENTE",
        )
        item = await self.cola.create(item)

        # Detección de conflicto: si el timestamp offline es más antiguo que
        # la última modificación del elemento, no sobrescribimos → CONFLICTO.
        if self._es_conflicto_por_timestamp(cambio.timestamp_local, cambio.payload):
            await self.cola.marcar_conflicto(item.id)
            return ResultadoCambioSync(
                id_temporal_local=cambio.id_temporal_local,
                estado="CONFLICTO",
                id_real=None,
                motivo_conflicto=(
                    "El elemento fue modificado en el servidor después de "
                    "haber sido editado offline"
                ),
            )

        # Intentar aplicar
        try:
            id_real = await self._aplicar_cambio_offline(
                cambio.tipo_operacion, cambio.payload
            )
        except _ConflictoDeEdicion as exc:
            await self.cola.marcar_conflicto(item.id)
            return ResultadoCambioSync(
                id_temporal_local=cambio.id_temporal_local,
                estado="CONFLICTO",
                id_real=None,
                motivo_conflicto=_recortar_motivo(str(exc)),
            )
        except Exception as exc:
            # Error inesperado: marcamos conflicto para que el PROPIETARIO revise
            await self.cola.marcar_conflicto(item.id)
            return ResultadoCambioSync(
                id_temporal_local=cambio.id_temporal_local,
                estado="CONFLICTO",
                id_real=None,
                motivo_conflicto=_recortar_motivo(f"Error al aplicar: {exc}"),
            )

        await self.cola.marcar_sincronizado(item.id)
        return ResultadoCambioSync(
            id_temporal_local=cambio.id_temporal_local,
            estado="SINCRONIZADO",
            id_real=id_real,
            motivo_conflicto=None,
        )

    async def _aplicar_cambio_offline(
        self, tipo_operacion: str, payload: dict[str, Any]
    ) -> Optional[str]:
        """
        Despacha según el tipo de operación. Devuelve el id real (str) del
        recurso creado/modificado — uuid del elemento EMBEBIDO o
        str(ObjectId) —, o None si no aplica.

        Tipos soportados hoy:
        - CREAR_CLASE
        - MODIFICAR_CLASE
        - ELIMINAR_CLASE
        - AGREGAR_ATRIBUTO
        - MODIFICAR_ATRIBUTO
        - ELIMINAR_ATRIBUTO
        - CREAR_RELACION
        - ELIMINAR_RELACION
        """
        op = tipo_operacion.upper()

        if op == "CREAR_CLASE":
            return await self._op_crear_clase(payload)
        if op == "MODIFICAR_CLASE":
            return await self._op_modificar_clase(payload)
        if op == "ELIMINAR_CLASE":
            return await self._op_eliminar_clase(payload)
        if op == "AGREGAR_ATRIBUTO":
            return await self._op_agregar_atributo(payload)
        if op == "MODIFICAR_ATRIBUTO":
            return await self._op_modificar_atributo(payload)
        if op == "ELIMINAR_ATRIBUTO":
            return await self._op_eliminar_atributo(payload)
        if op == "CREAR_RELACION":
            return await self._op_crear_relacion(payload)
        if op == "ELIMINAR_RELACION":
            return await self._op_eliminar_relacion(payload)

        raise ValidationError(
            f"Tipo de operación offline no soportado: '{tipo_operacion}'"
        )

    # ------------------------------------------------------------------
    # Operaciones individuales
    # (Cada una re-lee el Diagrama dueño y persiste el PADRE completo:
    #  es la misma regla fetch → modificar → save del módulo C.)
    # ------------------------------------------------------------------
    async def _op_crear_clase(self, payload: dict[str, Any]) -> str:
        id_diagrama = self._require_objectid(payload, "id_diagrama")
        nombre = self._require_str(payload, "nombre")

        if await self.clases.exists_nombre_en_diagrama(id_diagrama, nombre):
            raise _ConflictoDeEdicion(
                f"Ya existe una clase '{nombre}' creada en el servidor"
            )

        # Necesitamos id_creador: el payload offline lo trae del usuario
        # local (str del ObjectId en el Ciclo 2).
        id_creador = payload.get("id_creador")
        if not id_creador:
            raise _ConflictoDeEdicion(
                "Falta id_creador en el payload de la clase offline"
            )
        try:
            id_creador = PydanticObjectId(id_creador)
        except (TypeError, ValueError):
            raise _ConflictoDeEdicion(
                "El id_creador del payload no es un id válido"
            )

        diagrama = await self.diagramas.get_by_id(id_diagrama)
        if diagrama is None:
            # En el Ciclo 1 el INSERT fallaba por FK y el ítem caía a
            # CONFLICTO vía "Error al aplicar"; aquí el mismo caso tiene
            # un motivo explícito.
            raise _ConflictoDeEdicion(
                "El diagrama destino no existe en el servidor"
            )

        clase = ClaseUML(
            nombre=nombre,
            es_abstracta=bool(payload.get("es_abstracta", False)),
            estereotipo=payload.get("estereotipo"),
            pos_x=payload.get("pos_x", 0),
            pos_y=payload.get("pos_y", 0),
            id_creador=id_creador,
        )
        # El repositorio agrega la clase al documento re-leído y hace
        # save() del padre; el uuid de la clase se genera antes del save,
        # así que es estable como id_real.
        clase = await self.clases.create(diagrama, clase)
        return clase.id

    async def _op_modificar_clase(self, payload: dict[str, Any]) -> str:
        clase_id = self._require_str(payload, "id_clase")
        diagrama = await self.clases.get_diagrama_de_clase(clase_id)
        if diagrama is None:
            raise _ConflictoDeEdicion(
                "La clase a modificar fue eliminada en el servidor"
            )
        clase = diagrama.clase(clase_id)
        if clase is None:
            raise _ConflictoDeEdicion(
                "La clase a modificar fue eliminada en el servidor"
            )

        # Conflicto si alguien la renombró por otra vía
        nuevo_nombre = payload.get("nombre")
        if nuevo_nombre and nuevo_nombre != clase.nombre:
            if await self.clases.exists_nombre_en_diagrama(
                diagrama.id, nuevo_nombre, exclude_id=clase.id
            ):
                raise _ConflictoDeEdicion(
                    f"El nombre '{nuevo_nombre}' ya está en uso en el servidor"
                )
            clase.nombre = nuevo_nombre

        if "es_abstracta" in payload:
            clase.es_abstracta = bool(payload["es_abstracta"])
        if "estereotipo" in payload:
            clase.estereotipo = payload["estereotipo"]
        if "pos_x" in payload:
            clase.pos_x = payload["pos_x"]
        if "pos_y" in payload:
            clase.pos_y = payload["pos_y"]

        # (onupdate del Ciclo 1 → lo fija el service)
        clase.updated_at = _ahora()
        diagrama.updated_at = _ahora()
        await self.clases.update(diagrama, clase)
        return clase.id

    async def _op_eliminar_clase(self, payload: dict[str, Any]) -> Optional[str]:
        clase_id = self._require_str(payload, "id_clase")
        diagrama = await self.clases.get_diagrama_de_clase(clase_id)
        if diagrama is None:
            # Ya fue eliminada: no es conflicto, es idempotente
            return clase_id
        clase = diagrama.clase(clase_id)
        if clase is None:
            return clase_id
        # Eliminar relaciones asociadas antes (mismo orden que el Ciclo 1;
        # el repositorio guarda el padre si quitó alguna).
        await self.relaciones.delete_by_clase(diagrama, clase_id)
        await self.clases.delete(diagrama, clase)
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return clase_id

    async def _op_agregar_atributo(self, payload: dict[str, Any]) -> str:
        clase_id = self._require_str(payload, "id_clase")
        nombre = self._require_str(payload, "nombre")
        tipo_dato = payload.get("tipo_dato", "String")

        diagrama = await self.clases.get_diagrama_de_clase(clase_id)
        if diagrama is None:
            raise _ConflictoDeEdicion(
                "La clase destino del atributo no existe en el servidor"
            )
        clase = diagrama.clase(clase_id)
        if clase is None:
            raise _ConflictoDeEdicion(
                "La clase destino del atributo no existe en el servidor"
            )

        orden = payload.get("orden")
        if orden is None:
            # next_orden trabaja en memoria sobre la clase del documento
            # re-leído (COALESCE(MAX,-1)+1 del Ciclo 1).
            orden = await self.atributos.next_orden(clase)

        attr = AtributoUML(
            nombre=nombre,
            tipo_dato=tipo_dato,
            visibilidad=payload.get("visibilidad", "-"),
            es_estatico=bool(payload.get("es_estatico", False)),
            valor_defecto=payload.get("valor_defecto"),
            orden=orden,
        )
        attr = await self.atributos.create(diagrama, clase, attr)
        return attr.id

    async def _op_modificar_atributo(self, payload: dict[str, Any]) -> str:
        atributo_id = self._require_str(payload, "id_atributo")
        resuelto = await self._resolver_atributo(atributo_id)
        if resuelto is None:
            raise _ConflictoDeEdicion(
                "El atributo a modificar fue eliminado en el servidor"
            )
        diagrama, clase, attr = resuelto

        if "nombre" in payload and payload["nombre"]:
            attr.nombre = payload["nombre"]
        if "tipo_dato" in payload and payload["tipo_dato"]:
            attr.tipo_dato = payload["tipo_dato"]
        if "visibilidad" in payload:
            attr.visibilidad = payload["visibilidad"]
        if "es_estatico" in payload:
            attr.es_estatico = bool(payload["es_estatico"])
        if "valor_defecto" in payload:
            attr.valor_defecto = payload["valor_defecto"]
        if "orden" in payload and payload["orden"] is not None:
            attr.orden = payload["orden"]

        clase.updated_at = _ahora()
        diagrama.updated_at = _ahora()
        await self.atributos.update(diagrama, attr)
        return attr.id

    async def _op_eliminar_atributo(
        self, payload: dict[str, Any]
    ) -> Optional[str]:
        atributo_id = self._require_str(payload, "id_atributo")
        resuelto = await self._resolver_atributo(atributo_id)
        if resuelto is None:
            # Ya fue eliminado: no es conflicto, es idempotente
            return atributo_id
        diagrama, clase, attr = resuelto
        await self.atributos.delete(diagrama, clase, attr)
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return atributo_id

    async def _op_crear_relacion(self, payload: dict[str, Any]) -> str:
        id_diagrama = self._require_objectid(payload, "id_diagrama")
        origen = self._require_str(payload, "id_clase_origen")
        destino = self._require_str(payload, "id_clase_destino")
        tipo = payload.get("tipo_relacion", "ASOCIACION")

        diagrama = await self.diagramas.get_by_id(id_diagrama)
        if diagrama is None:
            raise _ConflictoDeEdicion(
                "El diagrama destino no existe en el servidor"
            )

        # Conflicto si alguna de las clases ya no existe. Con el contenido
        # embebido no hacen falta las 2 consultas por FK del Ciclo 1: el
        # helper del documento resuelve por uuid.
        co = diagrama.clase(origen)
        cd = diagrama.clase(destino)
        if co is None or cd is None:
            raise _ConflictoDeEdicion(
                "Alguna de las clases de la relación fue eliminada en el servidor"
            )

        if await self.relaciones.exists_entre_clases(
            id_diagrama, origen, destino, tipo
        ):
            raise _ConflictoDeEdicion(
                "Ya existe una relación de ese tipo entre esas clases"
            )

        relacion = RelacionUML(
            id_clase_origen=origen,
            id_clase_destino=destino,
            tipo_relacion=tipo,
            multiplicidad_origen=payload.get("multiplicidad_origen"),
            multiplicidad_destino=payload.get("multiplicidad_destino"),
            nombre_asociacion=payload.get("nombre_asociacion"),
            rol_origen=payload.get("rol_origen"),
            rol_destino=payload.get("rol_destino"),
        )
        relacion = await self.relaciones.create(diagrama, relacion)
        return relacion.id

    async def _op_eliminar_relacion(
        self, payload: dict[str, Any]
    ) -> Optional[str]:
        relacion_id = self._require_str(payload, "id_relacion")
        resuelto = await self._resolver_relacion(relacion_id)
        if resuelto is None:
            # Ya fue eliminada: no es conflicto, es idempotente
            return relacion_id
        diagrama, relacion = resuelto
        await self.relaciones.delete(diagrama, relacion)
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return relacion_id

    # ------------------------------------------------------------------
    # Helpers varios
    # ------------------------------------------------------------------
    def _es_conflicto_por_timestamp(
        self, timestamp_local: Optional[datetime], payload: dict[str, Any]
    ) -> bool:
        """
        Heurística simple: si el payload indica que el elemento tenía
        una versión (updated_at) que ya no coincide con la actual, y
        el timestamp offline es anterior, asumimos conflicto.
        La resolución real de colisiones se hace por operación.
        """
        # Placeholder: la lógica fuerte está en cada _op_* que
        # compara contra el estado actual del servidor.
        return False

    def _require_objectid(self, payload: dict[str, Any], clave: str) -> PydanticObjectId:
        """
        Resuelve un id de DOCUMENTO (str del ObjectId) desde el payload.
        (En el Ciclo 1 era _require_int: los ids de documentos ya no son
        enteros; el mensaje se adapta a "debe ser un id válido".)
        """
        valor = payload.get(clave)
        if valor is None:
            raise ValidationError(f"Falta el campo obligatorio '{clave}'")
        try:
            return PydanticObjectId(valor)
        except (TypeError, ValueError):
            raise ValidationError(f"El campo '{clave}' debe ser un id válido")

    def _require_str(self, payload: dict[str, Any], clave: str) -> str:
        """Campo obligatorio no vacío (nombres y uuid de embebidos)."""
        valor = payload.get(clave)
        if not valor or not str(valor).strip():
            raise ValidationError(f"Falta el campo obligatorio '{clave}'")
        return str(valor).strip()

    async def _require_editor(
        self, proyecto_id: PydanticObjectId, usuario_id: PydanticObjectId
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ForbiddenError(
                "Se requiere rol EDITOR o PROPIETARIO para sincronizar cambios"
            )

    async def _require_propietario(
        self, proyecto_id: PydanticObjectId, usuario_id: PydanticObjectId
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto != "PROPIETARIO":
            raise ForbiddenError(
                "Solo el PROPIETARIO del proyecto puede resolver conflictos"
            )

    # ------------------------------------------------------------------
    # Resolvedores de embebidos (regla del módulo C): los get_by_id de los
    # repos devuelven el elemento EN LECTURA; para escribir se necesita el
    # DOCUMENTO padre re-leído. Son la versión de este service de los
    # _resolver_* del diagrama_service.
    # ------------------------------------------------------------------
    async def _resolver_atributo(
        self, atributo_id: str
    ) -> Optional[tuple[Diagrama, ClaseUML, AtributoUML]]:
        """Localiza (diagrama re-leído, clase, atributo) por el uuid del
        atributo anidado (2 niveles)."""
        diagrama = await Diagrama.find_one(
            Diagrama.clases.atributos.id == atributo_id
        )
        if diagrama is None:
            return None
        for clase in diagrama.clases:
            atributo = clase.atributo(atributo_id)
            if atributo is not None:
                return diagrama, clase, atributo
        return None

    async def _resolver_relacion(
        self, relacion_id: str
    ) -> Optional[tuple[Diagrama, RelacionUML]]:
        """Localiza (diagrama re-leído, relación) por su uuid."""
        diagrama = await Diagrama.find_one(
            Diagrama.relaciones.id == relacion_id
        )
        if diagrama is None:
            return None
        return diagrama, diagrama.relacion(relacion_id)


class _ConflictoDeEdicion(Exception):
    """Excepción interna: se convierte en estado CONFLICTO de la cola."""
    pass