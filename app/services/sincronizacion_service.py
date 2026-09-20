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
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.diagrama import AtributoUML, ClaseUML, RelacionUML
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


class SincronizacionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.cola = ColaSincronizacionRepository(db)
        self.diagramas = DiagramaRepository(db)
        self.clases = ClaseUMLRepository(db)
        self.atributos = AtributoUMLRepository(db)
        self.relaciones = RelacionUMLRepository(db)
        self.miembros = MiembroProyectoRepository(db)
        self.sesiones = SesionColaboracionRepository(db)
        self.participantes = ParticipanteSesionRepository(db)

    # ==================================================================
    # PROCESAMIENTO DE BATCH OFFLINE
    # ==================================================================
    async def procesar_batch(
        self,
        datos: BatchSincronizacionRequest,
        *,
        usuario_id: int,
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

        await self.db.commit()

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
        diagrama_id: int,
        *,
        usuario_id: int,
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
        conflicto_id: int,
        *,
        estrategia: str,
        payload_fusionado: Optional[dict[str, Any]] = None,
        usuario_id: int,
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

        diagrama = await self.diagramas.get_by_id(conflicto.id_diagrama)
        if diagrama is None:
            raise NotFoundError("Diagrama asociado no encontrado")
        await self._require_propietario(diagrama.id_proyecto, usuario_id)

        if estrategia == "SERVIDOR":
            # Descartar: marcamos como SINCRONIZADO sin aplicar
            await self.cola.marcar_sincronizado(conflicto.id)
            await self.db.commit()
            await self.db.refresh(conflicto)
            return ConflictoSyncResponse.model_validate(conflicto)

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
            await self.cola.marcar_sincronizado(conflicto.id)
            await self.db.commit()
            await self.db.refresh(conflicto)
            return ConflictoSyncResponse.model_validate(conflicto)

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
            await self.cola.marcar_sincronizado(conflicto.id)
            await self.db.commit()
            await self.db.refresh(conflicto)
            return ConflictoSyncResponse.model_validate(conflicto)

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
        id_diagrama: int,
        usuario_id: int,
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
                motivo_conflicto=str(exc),
            )
        except Exception as exc:
            # Error inesperado: marcamos conflicto para que el PROPIETARIO revise
            await self.cola.marcar_conflicto(item.id)
            return ResultadoCambioSync(
                id_temporal_local=cambio.id_temporal_local,
                estado="CONFLICTO",
                id_real=None,
                motivo_conflicto=f"Error al aplicar: {exc}",
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
    ) -> Optional[int]:
        """
        Despacha según el tipo de operación. Devuelve el id real del recurso
        creado/modificado, o None si no aplica.

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
    # ------------------------------------------------------------------
    async def _op_crear_clase(self, payload: dict[str, Any]) -> int:
        id_diagrama = self._require_int(payload, "id_diagrama")
        nombre = self._require_str(payload, "nombre")

        if await self.clases.exists_nombre_en_diagrama(id_diagrama, nombre):
            raise _ConflictoDeEdicion(
                f"Ya existe una clase '{nombre}' creada en el servidor"
            )

        # Necesitamos id_creador: usamos el del payload o 0 (nunca 0 en BD);
        # en la práctica el payload offline lo trae del usuario local.
        id_creador = payload.get("id_creador")
        if not id_creador:
            raise _ConflictoDeEdicion(
                "Falta id_creador en el payload de la clase offline"
            )

        clase = ClaseUML(
            id_diagrama=id_diagrama,
            nombre=nombre,
            es_abstracta=bool(payload.get("es_abstracta", False)),
            estereotipo=payload.get("estereotipo"),
            pos_x=payload.get("pos_x", 0),
            pos_y=payload.get("pos_y", 0),
            id_creador=id_creador,
        )
        clase = await self.clases.create(clase)
        return clase.id

    async def _op_modificar_clase(self, payload: dict[str, Any]) -> int:
        clase_id = self._require_int(payload, "id_clase")
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise _ConflictoDeEdicion(
                "La clase a modificar fue eliminada en el servidor"
            )

        # Conflicto si alguien la renombró por otra vía
        nuevo_nombre = payload.get("nombre")
        if nuevo_nombre and nuevo_nombre != clase.nombre:
            if await self.clases.exists_nombre_en_diagrama(
                clase.id_diagrama, nuevo_nombre, exclude_id=clase.id
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

        await self.clases.update(clase)
        return clase.id

    async def _op_eliminar_clase(self, payload: dict[str, Any]) -> Optional[int]:
        clase_id = self._require_int(payload, "id_clase")
        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            # Ya fue eliminada: no es conflicto, es idempotente
            return clase_id
        # Eliminar relaciones asociadas antes
        await self.relaciones.delete_by_clase(clase_id)
        await self.clases.delete(clase)
        return clase_id

    async def _op_agregar_atributo(self, payload: dict[str, Any]) -> int:
        clase_id = self._require_int(payload, "id_clase")
        nombre = self._require_str(payload, "nombre")
        tipo_dato = payload.get("tipo_dato", "String")

        clase = await self.clases.get_by_id(clase_id)
        if clase is None:
            raise _ConflictoDeEdicion(
                "La clase destino del atributo no existe en el servidor"
            )

        orden = payload.get("orden")
        if orden is None:
            orden = await self.atributos.next_orden(clase_id)

        attr = AtributoUML(
            id_clase=clase_id,
            nombre=nombre,
            tipo_dato=tipo_dato,
            visibilidad=payload.get("visibilidad", "-"),
            es_estatico=bool(payload.get("es_estatico", False)),
            valor_defecto=payload.get("valor_defecto"),
            orden=orden,
        )
        attr = await self.atributos.create(attr)
        return attr.id

    async def _op_modificar_atributo(self, payload: dict[str, Any]) -> int:
        atributo_id = self._require_int(payload, "id_atributo")
        attr = await self.atributos.get_by_id(atributo_id)
        if attr is None:
            raise _ConflictoDeEdicion(
                "El atributo a modificar fue eliminado en el servidor"
            )

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

        await self.atributos.update(attr)
        return attr.id

    async def _op_eliminar_atributo(self, payload: dict[str, Any]) -> Optional[int]:
        atributo_id = self._require_int(payload, "id_atributo")
        attr = await self.atributos.get_by_id(atributo_id)
        if attr is None:
            return atributo_id
        await self.atributos.delete(attr)
        return atributo_id

    async def _op_crear_relacion(self, payload: dict[str, Any]) -> int:
        id_diagrama = self._require_int(payload, "id_diagrama")
        origen = self._require_int(payload, "id_clase_origen")
        destino = self._require_int(payload, "id_clase_destino")
        tipo = payload.get("tipo_relacion", "ASOCIACION")

        # Conflicto si alguna de las clases ya no existe
        co = await self.clases.get_by_id(origen)
        cd = await self.clases.get_by_id(destino)
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
            id_diagrama=id_diagrama,
            id_clase_origen=origen,
            id_clase_destino=destino,
            tipo_relacion=tipo,
            multiplicidad_origen=payload.get("multiplicidad_origen"),
            multiplicidad_destino=payload.get("multiplicidad_destino"),
            nombre_asociacion=payload.get("nombre_asociacion"),
            rol_origen=payload.get("rol_origen"),
            rol_destino=payload.get("rol_destino"),
        )
        relacion = await self.relaciones.create(relacion)
        return relacion.id

    async def _op_eliminar_relacion(self, payload: dict[str, Any]) -> Optional[int]:
        relacion_id = self._require_int(payload, "id_relacion")
        relacion = await self.relaciones.get_by_id(relacion_id)
        if relacion is None:
            return relacion_id
        await self.relaciones.delete(relacion)
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

    def _require_int(self, payload: dict[str, Any], clave: str) -> int:
        valor = payload.get(clave)
        if valor is None:
            raise ValidationError(f"Falta el campo obligatorio '{clave}'")
        try:
            return int(valor)
        except (TypeError, ValueError):
            raise ValidationError(f"El campo '{clave}' debe ser un entero")

    def _require_str(self, payload: dict[str, Any], clave: str) -> str:
        valor = payload.get(clave)
        if not valor or not str(valor).strip():
            raise ValidationError(f"Falta el campo obligatorio '{clave}'")
        return str(valor).strip()

    async def _require_editor(self, proyecto_id: int, usuario_id: int) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ForbiddenError(
                "Se requiere rol EDITOR o PROPIETARIO para sincronizar cambios"
            )

    async def _require_propietario(self, proyecto_id: int, usuario_id: int) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto != "PROPIETARIO":
            raise ForbiddenError(
                "Solo el PROPIETARIO del proyecto puede resolver conflictos"
            )


class _ConflictoDeEdicion(Exception):
    """Excepción interna: se convierte en estado CONFLICTO de la cola."""
    pass