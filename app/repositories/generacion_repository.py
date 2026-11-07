# app/repositories/generacion_repository.py
"""
Repositorio de acceso a datos del módulo F. Generación Automática de
Código — CICLO 2.

En el Ciclo 1 eran 3 tablas y 3 repositorios; en el Ciclo 2 el resultado
va EMBEBIDO en el trabajo (trabajo → entidades[] → reglas_mapeo[]), así
que:
- TrabajoGeneracionRepository → colección `trabajos_generacion_codigo`
- EntidadGeneradaRepository   → embebida en TrabajoGeneracionCodigo.
                                entidades
- ReglaMapeoRepository        → embebida en EntidadGenerada.reglas_mapeo

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- get_detalle() ya no necesita 2 selectinload anidados: leer el trabajo
  SIEMPRE trae sus entidades y las reglas de cada una (1 lectura; se
  conserva el método porque es el payload del resumen de una generación).
- EntidadGeneradaRepository.get_by_id se retira: las entidades ya NO
  tienen id propio; el localizador es el par (trabajo, id_clase_uml) —
  el uuid del ClaseUML embebido del diagrama (get_by_trabajo_y_clase).
- REGLA DE ESCRITURA (Beanie): toda escritura sobre un embebido recibe
  el TrabajoGeneracionCodigo RE-LEÍDO de la base, modifica sus listas y
  hace save() del padre (1 documento = 1 escritura coherente). Para
  tocar las reglas, la EntidadGenerada que se pasa debe ser la instancia
  DENTRO de trabajo.entidades (el servicio la obtiene con
  trabajo.entidad_de_clase() del documento re-leído); si se pasa una
  copia suelta, el cambio no caería en el documento guardado.
- bulk_create es extend() + UN save() del padre (en ReglaMapeo igual):
  Mongo no devuelve filas que haya que "refrescar" como el add_all +
  refresh del Ciclo 1.
- marcar_en_proceso/exitoso/fallido usan datetime.now(timezone.utc)
  (aware, igual que los modelos; el utcnow() naive del Ciclo 1 se
  descarta) y permiten inyectar `cuando` para tests.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.generacion import (
    EntidadGenerada,
    ReglaMapeo,
    TrabajoGeneracionCodigo,
)


def _ahora(cuando: Optional[datetime] = None) -> datetime:
    """Fecha de trabajo aware; permite inyectar `cuando` en tests."""
    return cuando or datetime.now(timezone.utc)


# ======================================================================
# TrabajoGeneracionRepository
# ======================================================================
class TrabajoGeneracionRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, trabajo_id: PydanticObjectId
    ) -> Optional[TrabajoGeneracionCodigo]:
        return await TrabajoGeneracionCodigo.get(trabajo_id)

    async def get_detalle(
        self, trabajo_id: PydanticObjectId
    ) -> Optional[TrabajoGeneracionCodigo]:
        """
        Trabajo con sus entidades generadas y las reglas de mapeo de cada
        una. Es el payload que se usa para mostrar el resumen de una
        generación. En el Ciclo 2 TODO va embebido: equivale a get_by_id
        (antes encadenaba 2 selectinload).
        """
        return await self.get_by_id(trabajo_id)

    async def list_by_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[TrabajoGeneracionCodigo]:
        return await (
            TrabajoGeneracionCodigo.find(
                TrabajoGeneracionCodigo.id_diagrama == diagrama_id
            )
            .sort(-TrabajoGeneracionCodigo.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_usuario(
        self,
        usuario_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[TrabajoGeneracionCodigo]:
        return await (
            TrabajoGeneracionCodigo.find(
                TrabajoGeneracionCodigo.id_usuario == usuario_id
            )
            .sort(-TrabajoGeneracionCodigo.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def list_by_estado(
        self,
        estado: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[TrabajoGeneracionCodigo]:
        """Útil para reintentar PENDIENTES o monitorear EN_PROCESO
        (orden ascendente por created_at: primero los más viejos de la
        cola, como el Ciclo 1)."""
        return await (
            TrabajoGeneracionCodigo.find(
                TrabajoGeneracionCodigo.estado == estado
            )
            .sort(+TrabajoGeneracionCodigo.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def get_ultimo_exitoso_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[TrabajoGeneracionCodigo]:
        """Último trabajo EXITOSO de un diagrama (para ofrecer descarga
        directa)."""
        return await (
            TrabajoGeneracionCodigo.find(
                TrabajoGeneracionCodigo.id_diagrama == diagrama_id,
                TrabajoGeneracionCodigo.estado == "EXITOSO",
            )
            .sort(-TrabajoGeneracionCodigo.finished_at)
            .first_or_none()
        )

    async def count_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        return await TrabajoGeneracionCodigo.find(
            TrabajoGeneracionCodigo.id_diagrama == diagrama_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(
        self, trabajo: TrabajoGeneracionCodigo
    ) -> TrabajoGeneracionCodigo:
        await trabajo.insert()
        return trabajo

    async def update(
        self, trabajo: TrabajoGeneracionCodigo
    ) -> TrabajoGeneracionCodigo:
        await trabajo.save()
        return trabajo

    async def marcar_en_proceso(
        self,
        trabajo_id: PydanticObjectId,
        *,
        cuando: Optional[datetime] = None,
    ) -> Optional[TrabajoGeneracionCodigo]:
        trabajo = await self.get_by_id(trabajo_id)
        if trabajo is None:
            return None
        trabajo.estado = "EN_PROCESO"
        trabajo.started_at = _ahora(cuando)
        await trabajo.save()
        return trabajo

    async def marcar_exitoso(
        self,
        trabajo_id: PydanticObjectId,
        *,
        ruta_salida: str,
        cuando: Optional[datetime] = None,
    ) -> Optional[TrabajoGeneracionCodigo]:
        trabajo = await self.get_by_id(trabajo_id)
        if trabajo is None:
            return None
        trabajo.estado = "EXITOSO"
        trabajo.ruta_salida = ruta_salida
        trabajo.finished_at = _ahora(cuando)
        await trabajo.save()
        return trabajo

    async def marcar_fallido(
        self,
        trabajo_id: PydanticObjectId,
        *,
        cuando: Optional[datetime] = None,
    ) -> Optional[TrabajoGeneracionCodigo]:
        trabajo = await self.get_by_id(trabajo_id)
        if trabajo is None:
            return None
        trabajo.estado = "FALLIDO"
        trabajo.finished_at = _ahora(cuando)
        await trabajo.save()
        return trabajo

    async def delete(self, trabajo: TrabajoGeneracionCodigo) -> None:
        # Las entidades y sus reglas viajan EMBEBIDAS: desaparecen con el
        # documento (en el Ciclo 1 había que borrarlas en cascada a mano).
        await trabajo.delete()


# ======================================================================
# EntidadGeneradaRepository (embebida en TrabajoGeneracionCodigo.entidades)
# ======================================================================
class EntidadGeneradaRepository:
    """
    Las entidades ya NO tienen id propio (antes tabla
    entidades_generadas): el localizador es el par (trabajo,
    id_clase_uml). Las lecturas por trabajo reciben el id y resuelven el
    documento adentro; las escrituras reciben el trabajo RE-LEÍDO y lo
    guardan.
    """

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_trabajo_y_clase(
        self,
        trabajo_id: PydanticObjectId,
        id_clase_uml: str,
    ) -> Optional[EntidadGenerada]:
        """Entidad generada para una clase UML (uuid del ClaseUML
        embebido del diagrama). Sustituye a get_by_id del Ciclo 1."""
        trabajo = await TrabajoGeneracionCodigo.get(trabajo_id)
        if trabajo is None:
            return None
        return trabajo.entidad_de_clase(id_clase_uml)

    async def get_con_reglas(
        self,
        trabajo_id: PydanticObjectId,
        id_clase_uml: str,
    ) -> Optional[EntidadGenerada]:
        """Entidad con sus reglas de mapeo. En el Ciclo 2 SIEMPRE van
        embebidas: equivale a get_by_trabajo_y_clase (antes
        selectinload)."""
        return await self.get_by_trabajo_y_clase(trabajo_id, id_clase_uml)

    async def list_by_trabajo(
        self, trabajo_id: PydanticObjectId
    ) -> Sequence[EntidadGenerada]:
        trabajo = await TrabajoGeneracionCodigo.get(trabajo_id)
        if trabajo is None:
            return []
        return list(trabajo.entidades)   # orden de inserción (antes id asc)

    async def count_by_trabajo(self, trabajo_id: PydanticObjectId) -> int:
        trabajo = await TrabajoGeneracionCodigo.get(trabajo_id)
        if trabajo is None:
            return 0
        return len(trabajo.entidades)

    # ------------------------------------------------------------------
    # Escrituras (reciben el TrabajoGeneracionCodigo re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidad: EntidadGenerada,
    ) -> EntidadGenerada:
        trabajo.entidades.append(entidad)
        await trabajo.save()
        return entidad

    async def bulk_create(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidades: list[EntidadGenerada],
    ) -> list[EntidadGenerada]:
        """Crea varias entidades de una vez (usado por el generador)."""
        trabajo.entidades.extend(entidades)
        await trabajo.save()
        return entidades

    async def update(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidad: EntidadGenerada,
    ) -> EntidadGenerada:
        await trabajo.save()
        return entidad

    async def delete(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidad: EntidadGenerada,
    ) -> None:
        # Se filtra por id_clase_uml (uuid del ClaseUML) y no por
        # igualdad de objetos.
        trabajo.entidades = [
            e
            for e in trabajo.entidades
            if e.id_clase_uml != entidad.id_clase_uml
        ]
        await trabajo.save()

    async def delete_by_trabajo(self, trabajo_id: PydanticObjectId) -> int:
        """Elimina todas las entidades del trabajo. Devuelve cuántas
        borró. (Conserva la firma del Ciclo 1: recibe el id y re-lee.)"""
        trabajo = await TrabajoGeneracionCodigo.get(trabajo_id)
        if trabajo is None:
            return 0
        total = len(trabajo.entidades)
        trabajo.entidades.clear()
        if total:
            await trabajo.save()
        return total


# ======================================================================
# ReglaMapeoRepository (embebida en EntidadGenerada.reglas_mapeo,
#                       que a su vez va embebida en el trabajo)
# ======================================================================
class ReglaMapeoRepository:
    """
    Reglas EMBEBIDAS 2 niveles abajo del trabajo. Las lecturas reciben la
    EntidadGenerada en mano (los embebidos se leen desde su padre, antes
    el id int de la tabla entidades_generadas); las escrituras reciben el
    trabajo RE-LEÍDO más la entidad DENTRO de trabajo.entidades y hacen
    save() del padre.
    """

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def list_by_entidad(
        self, entidad: EntidadGenerada
    ) -> Sequence[ReglaMapeo]:
        return list(entidad.reglas_mapeo)   # orden de inserción (antes id asc)

    async def get_by_entidad_y_atributo(
        self, entidad: EntidadGenerada, id_atributo_uml: str
    ) -> Optional[ReglaMapeo]:
        """Regla de un atributo UML (uuid del AtributoUML embebido del
        diagrama). Reutiliza el helper del propio embebido."""
        return entidad.regla_de_atributo(id_atributo_uml)

    async def list_claves_primarias_by_entidad(
        self, entidad: EntidadGenerada
    ) -> Sequence[ReglaMapeo]:
        """Reglas de mapeo que marcan la PK de la entidad."""
        return [r for r in entidad.reglas_mapeo if r.es_clave_primaria]

    async def count_by_entidad(self, entidad: EntidadGenerada) -> int:
        return len(entidad.reglas_mapeo)

    # ------------------------------------------------------------------
    # Escrituras (reciben el trabajo re-leído y persisten el padre)
    # ------------------------------------------------------------------
    async def create(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidad: EntidadGenerada,
        regla: ReglaMapeo,
    ) -> ReglaMapeo:
        entidad.reglas_mapeo.append(regla)
        await trabajo.save()
        return regla

    async def bulk_create(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidad: EntidadGenerada,
        reglas: list[ReglaMapeo],
    ) -> list[ReglaMapeo]:
        entidad.reglas_mapeo.extend(reglas)
        await trabajo.save()
        return reglas

    async def update(
        self, trabajo: TrabajoGeneracionCodigo, regla: ReglaMapeo
    ) -> ReglaMapeo:
        await trabajo.save()
        return regla

    async def delete(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidad: EntidadGenerada,
        regla: ReglaMapeo,
    ) -> None:
        # Se filtra por id_atributo_uml (uuid del AtributoUML) y no por
        # igualdad de objetos.
        entidad.reglas_mapeo = [
            r
            for r in entidad.reglas_mapeo
            if r.id_atributo_uml != regla.id_atributo_uml
        ]
        await trabajo.save()

    async def delete_by_entidad(
        self,
        trabajo: TrabajoGeneracionCodigo,
        entidad: EntidadGenerada,
    ) -> int:
        """Elimina todas las reglas de la entidad. Devuelve cuántas
        borró. (Recibe el trabajo re-leído: la escritura es del padre.)"""
        total = len(entidad.reglas_mapeo)
        entidad.reglas_mapeo.clear()
        if total:
            await trabajo.save()
        return total