# app/repositories/diagrama_repository.py
"""
Repositorio de acceso a datos del módulo C. Modelado UML.

Incluye los repositorios de los 8 elementos del módulo. En el Ciclo 1 eran
8 tablas; en el Ciclo 2 los 7 elementos UML van EMBEBIDOS dentro del
documento Diagrama (colección "diagramas"), así que:
- DiagramaRepository              → colección `diagramas` (documento padre)
- ClaseUMLRepository              → embebido en Diagrama.clases
- AtributoUMLRepository           → embebido en ClaseUML.atributos
- OperacionUMLRepository          → embebido en ClaseUML.operaciones
- ParametroOperacionUMLRepository → embebido en OperacionUML.parametros
- InterfazUMLRepository           → embebido en Diagrama.interfaces
- OperacionInterfazUMLRepository  → embebido en InterfazUML.operaciones
- RelacionUMLRepository           → embebido en Diagrama.relaciones

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- get_completo() ya no necesita 4 selectinload: TODO el lienzo vive en el
  documento Diagrama y se lee en 1 consulta atómica (se conserva el método
  porque es el punto de entrada del editor y del motor de generación).
- Los elementos embebidos usan ids uuid (hex) y ya NO traen id_diagrama ni
  id_clase: el contexto lo da su posición dentro del documento padre.
- REGLA DE ESCRITURA (Beanie): toda escritura sobre un embebido recibe el
  DOCUMENTO Diagrama RE-LEÍDO de la base como primer parámetro, modifica
  sus listas y hace save() del padre. En MongoDB no se persiste "un
  atributo" solo: se persiste el diagrama completo (1 documento = 1
  escritura coherente, la misma que consume el WebSocket y el Agente Dev).
  Si el servicio pasa un Diagrama viejo en memoria, Beanie puede
  sobrescribir cambios hechos por otro usuario.
- Los get_by_id de embebidos localizan el padre por el campo anidado
  (p. ej. clases.operaciones.parametros.id) y devuelven el elemento EN
  LECTURA (los uuid son únicos en toda la base). Para MODIFICAR un
  elemento, el servicio re-lee el Diagrama (los uuid resuelven con los
  helpers diagrama.clase()/interfaz()/relacion() y clase.atributo()/
  operacion()).
- Las operaciones MASIVAS o de lectura por (diagrama_id) conservan la
  firma del Ciclo 1: reciben el id y resuelven el documento adentro.
- Los elementos embebidos no tienen created_at ordenable salvo ClaseUML:
  list_by_diagrama de clases ordena por created_at (como el Ciclo 1);
  interfaces y relaciones conservan el ORDEN DE INSERCIÓN de la lista
  (el Ciclo 1 ordenaba por id int correlativo, que ya no existe).
"""

from typing import Optional, Sequence

from beanie import PydanticObjectId

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


# ======================================================================
# DiagramaRepository
# ======================================================================
class DiagramaRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[Diagrama]:
        return await Diagrama.get(diagrama_id)

    async def get_completo(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[Diagrama]:
        """
        Carga el diagrama con clases (y sus atributos/operaciones/
        parámetros), interfaces (con sus operaciones) y relaciones. Es el
        payload que consume el editor y el motor de generación.

        En el Ciclo 1 encadenaba 4 selectinload (hasta 7 consultas); en el
        Ciclo 2 TODO va embebido: equivale a get_by_id (1 lectura).
        """
        return await self.get_by_id(diagrama_id)

    async def list_by_proyecto(
        self,
        proyecto_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Diagrama]:
        return await (
            Diagrama.find(Diagrama.id_proyecto == proyecto_id)
            .sort(-Diagrama.updated_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count_by_proyecto(
        self, proyecto_id: PydanticObjectId
    ) -> int:
        return await Diagrama.find(
            Diagrama.id_proyecto == proyecto_id
        ).count()

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, diagrama: Diagrama) -> Diagrama:
        await diagrama.insert()
        return diagrama

    async def update(self, diagrama: Diagrama) -> Diagrama:
        await diagrama.save()
        return diagrama

    async def delete(self, diagrama: Diagrama) -> None:
        await diagrama.delete()

    async def incrementar_version(
        self, diagrama_id: PydanticObjectId
    ) -> Optional[Diagrama]:
        diagrama = await self.get_by_id(diagrama_id)
        if diagrama is None:
            return None
        diagrama.numero_version = (diagrama.numero_version or 0) + 1
        await diagrama.save()
        return diagrama


# ======================================================================
# ClaseUMLRepository (embebida en Diagrama.clases)
# ======================================================================
class ClaseUMLRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, clase_id: str) -> Optional[ClaseUML]:
        """Lectura suelta por uuid. Para MODIFICAR la clase re-lee el
        Diagrama (ver la regla del módulo)."""
        diagrama = await Diagrama.find_one(Diagrama.clases.id == clase_id)
        if diagrama is None:
            return None
        return diagrama.clase(clase_id)

    async def get_diagrama_de_clase(self, clase_id: str) -> Optional[Diagrama]:
        """
        Devuelve el Diagrama dueño de la clase embebida. Es la puerta para
        modificarla con la regla fetch→modificar→save: diagrama.clase(id)
        devuelve la instancia dentro del documento que se va a guardar.
        """
        return await Diagrama.find_one(Diagrama.clases.id == clase_id)

    async def get_con_detalle(self, clase_id: str) -> Optional[ClaseUML]:
        """Clase con atributos y operaciones (y parámetros de cada
        operación). En el Ciclo 2 SIEMPRE van embebidas: equivale a
        get_by_id (antes encadenaba 3 selectinload)."""
        return await self.get_by_id(clase_id)

    async def list_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[ClaseUML]:
        diagrama = await Diagrama.get(diagrama_id)
        if diagrama is None:
            return []
        return sorted(diagrama.clases, key=lambda c: c.created_at)

    async def exists_nombre_en_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        nombre: str,
        *,
        exclude_id: Optional[str] = None,
    ) -> bool:
        diagrama = await Diagrama.get(diagrama_id)
        if diagrama is None:
            return False
        objetivo = nombre.strip().casefold()
        for clase in diagrama.clases:
            if exclude_id is not None and clase.id == exclude_id:
                continue
            if clase.nombre.strip().casefold() == objetivo:
                return True
        return False

    # ------------------------------------------------------------------
    # Escrituras (reciben el Diagrama re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self, diagrama: Diagrama, clase: ClaseUML
    ) -> ClaseUML:
        diagrama.clases.append(clase)
        await diagrama.save()
        return clase

    async def update(
        self, diagrama: Diagrama, clase: ClaseUML
    ) -> ClaseUML:
        await diagrama.save()
        return clase

    async def delete(
        self, diagrama: Diagrama, clase: ClaseUML
    ) -> None:
        # Se filtra por id uuid (único) y no por igualdad de objetos.
        diagrama.clases = [
            c for c in diagrama.clases if c.id != clase.id
        ]
        await diagrama.save()

    async def delete_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> int:
        """Elimina todas las clases de un diagrama. Devuelve cuántas
        borró. (Conserva la firma del Ciclo 1: recibe el id y re-lee.)"""
        diagrama = await Diagrama.get(diagrama_id)
        if diagrama is None:
            return 0
        total = len(diagrama.clases)
        diagrama.clases.clear()
        if total:
            await diagrama.save()
        return total


# ======================================================================
# AtributoUMLRepository (embebido en ClaseUML.atributos)
# ======================================================================
class AtributoUMLRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, atributo_id: str) -> Optional[AtributoUML]:
        """Localiza el atributo anidado (2 niveles) por su uuid."""
        diagrama = await Diagrama.find_one(
            Diagrama.clases.atributos.id == atributo_id
        )
        if diagrama is None:
            return None
        for clase in diagrama.clases:
            atributo = clase.atributo(atributo_id)
            if atributo is not None:
                return atributo
        return None

    async def list_by_clase(self, clase: ClaseUML) -> Sequence[AtributoUML]:
        """(Antes recibía el id int de la tabla clases_uml.) Se pasa la
        ClaseUML en mano: los embebidos se leen desde su padre."""
        return sorted(clase.atributos, key=lambda a: (a.orden, a.id))

    async def next_orden(self, clase: ClaseUML) -> int:
        """Siguiente `orden` disponible (COALESCE(MAX, -1) + 1 del Ciclo 1)."""
        return max((a.orden for a in clase.atributos), default=-1) + 1

    # ------------------------------------------------------------------
    # Escrituras (reciben el Diagrama re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self,
        diagrama: Diagrama,
        clase: ClaseUML,
        atributo: AtributoUML,
    ) -> AtributoUML:
        clase.atributos.append(atributo)
        await diagrama.save()
        return atributo

    async def update(
        self, diagrama: Diagrama, atributo: AtributoUML
    ) -> AtributoUML:
        await diagrama.save()
        return atributo

    async def delete(
        self,
        diagrama: Diagrama,
        clase: ClaseUML,
        atributo: AtributoUML,
    ) -> None:
        clase.atributos = [
            a for a in clase.atributos if a.id != atributo.id
        ]
        await diagrama.save()


# ======================================================================
# OperacionUMLRepository (embebida en ClaseUML.operaciones)
# ======================================================================
class OperacionUMLRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, operacion_id: str) -> Optional[OperacionUML]:
        """Localiza la operación anidada (2 niveles) por su uuid."""
        diagrama = await Diagrama.find_one(
            Diagrama.clases.operaciones.id == operacion_id
        )
        if diagrama is None:
            return None
        for clase in diagrama.clases:
            operacion = clase.operacion(operacion_id)
            if operacion is not None:
                return operacion
        return None

    async def get_con_parametros(
        self, operacion_id: str
    ) -> Optional[OperacionUML]:
        """Operación con sus parámetros (antes selectinload). En el Ciclo 2
        SIEMPRE van embebidos: equivale a get_by_id."""
        return await self.get_by_id(operacion_id)

    async def list_by_clase(self, clase: ClaseUML) -> Sequence[OperacionUML]:
        return sorted(clase.operaciones, key=lambda o: (o.orden, o.id))

    async def next_orden(self, clase: ClaseUML) -> int:
        return max((o.orden for o in clase.operaciones), default=-1) + 1

    # ------------------------------------------------------------------
    # Escrituras (reciben el Diagrama re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self,
        diagrama: Diagrama,
        clase: ClaseUML,
        operacion: OperacionUML,
    ) -> OperacionUML:
        clase.operaciones.append(operacion)
        await diagrama.save()
        return operacion

    async def update(
        self, diagrama: Diagrama, operacion: OperacionUML
    ) -> OperacionUML:
        await diagrama.save()
        return operacion

    async def delete(
        self,
        diagrama: Diagrama,
        clase: ClaseUML,
        operacion: OperacionUML,
    ) -> None:
        clase.operaciones = [
            o for o in clase.operaciones if o.id != operacion.id
        ]
        await diagrama.save()


# ======================================================================
# ParametroOperacionUMLRepository (embebido en OperacionUML.parametros)
# ======================================================================
class ParametroOperacionUMLRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, parametro_id: str
    ) -> Optional[ParametroOperacionUML]:
        """Localiza el parámetro anidado (3 niveles) por su uuid."""
        diagrama = await Diagrama.find_one(
            Diagrama.clases.operaciones.parametros.id == parametro_id
        )
        if diagrama is None:
            return None
        for clase in diagrama.clases:
            for operacion in clase.operaciones:
                for parametro in operacion.parametros:
                    if parametro.id == parametro_id:
                        return parametro
        return None

    async def list_by_operacion(
        self, operacion: OperacionUML
    ) -> Sequence[ParametroOperacionUML]:
        return sorted(operacion.parametros, key=lambda p: (p.orden, p.id))

    async def next_orden(self, operacion: OperacionUML) -> int:
        return max((p.orden for p in operacion.parametros), default=-1) + 1

    # ------------------------------------------------------------------
    # Escrituras (reciben el Diagrama re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self,
        diagrama: Diagrama,
        operacion: OperacionUML,
        parametro: ParametroOperacionUML,
    ) -> ParametroOperacionUML:
        operacion.parametros.append(parametro)
        await diagrama.save()
        return parametro

    async def update(
        self, diagrama: Diagrama, parametro: ParametroOperacionUML
    ) -> ParametroOperacionUML:
        await diagrama.save()
        return parametro

    async def delete(
        self,
        diagrama: Diagrama,
        operacion: OperacionUML,
        parametro: ParametroOperacionUML,
    ) -> None:
        operacion.parametros = [
            p for p in operacion.parametros if p.id != parametro.id
        ]
        await diagrama.save()


# ======================================================================
# InterfazUMLRepository (embebida en Diagrama.interfaces)
# ======================================================================
class InterfazUMLRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, interfaz_id: str) -> Optional[InterfazUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.interfaces.id == interfaz_id
        )
        if diagrama is None:
            return None
        return diagrama.interfaz(interfaz_id)

    async def get_con_operaciones(
        self, interfaz_id: str
    ) -> Optional[InterfazUML]:
        """Interfaz con sus operaciones (antes selectinload). En el Ciclo 2
        SIEMPRE van embebidas: equivale a get_by_id."""
        return await self.get_by_id(interfaz_id)

    async def list_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[InterfazUML]:
        diagrama = await Diagrama.get(diagrama_id)
        if diagrama is None:
            return []
        return list(diagrama.interfaces)   # orden de inserción

    # ------------------------------------------------------------------
    # Escrituras (reciben el Diagrama re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self, diagrama: Diagrama, interfaz: InterfazUML
    ) -> InterfazUML:
        diagrama.interfaces.append(interfaz)
        await diagrama.save()
        return interfaz

    async def update(
        self, diagrama: Diagrama, interfaz: InterfazUML
    ) -> InterfazUML:
        await diagrama.save()
        return interfaz

    async def delete(
        self, diagrama: Diagrama, interfaz: InterfazUML
    ) -> None:
        diagrama.interfaces = [
            i for i in diagrama.interfaces if i.id != interfaz.id
        ]
        await diagrama.save()


# ======================================================================
# OperacionInterfazUMLRepository (embebido en InterfazUML.operaciones)
# ======================================================================
class OperacionInterfazUMLRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, operacion_id: str
    ) -> Optional[OperacionInterfazUML]:
        """Localiza la operación de interfaz anidada (2 niveles)."""
        diagrama = await Diagrama.find_one(
            Diagrama.interfaces.operaciones.id == operacion_id
        )
        if diagrama is None:
            return None
        for interfaz in diagrama.interfaces:
            for operacion in interfaz.operaciones:
                if operacion.id == operacion_id:
                    return operacion
        return None

    async def list_by_interfaz(
        self, interfaz: InterfazUML
    ) -> Sequence[OperacionInterfazUML]:
        return list(interfaz.operaciones)   # orden de inserción

    # ------------------------------------------------------------------
    # Escrituras (reciben el Diagrama re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self,
        diagrama: Diagrama,
        interfaz: InterfazUML,
        operacion: OperacionInterfazUML,
    ) -> OperacionInterfazUML:
        interfaz.operaciones.append(operacion)
        await diagrama.save()
        return operacion

    async def update(
        self, diagrama: Diagrama, operacion: OperacionInterfazUML
    ) -> OperacionInterfazUML:
        await diagrama.save()
        return operacion

    async def delete(
        self,
        diagrama: Diagrama,
        interfaz: InterfazUML,
        operacion: OperacionInterfazUML,
    ) -> None:
        interfaz.operaciones = [
            o for o in interfaz.operaciones if o.id != operacion.id
        ]
        await diagrama.save()


# ======================================================================
# RelacionUMLRepository (embebida en Diagrama.relaciones)
# ======================================================================
class RelacionUMLRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(self, relacion_id: str) -> Optional[RelacionUML]:
        diagrama = await Diagrama.find_one(
            Diagrama.relaciones.id == relacion_id
        )
        if diagrama is None:
            return None
        return diagrama.relacion(relacion_id)

    async def list_by_diagrama(
        self, diagrama_id: PydanticObjectId
    ) -> Sequence[RelacionUML]:
        diagrama = await Diagrama.get(diagrama_id)
        if diagrama is None:
            return []
        return list(diagrama.relaciones)   # orden de inserción

    async def list_by_clase(self, clase_id: str) -> Sequence[RelacionUML]:
        """Relaciones donde la clase participa como origen o destino.
        (Sin JOIN del Ciclo 1: se localiza el Diagrama dueño por el campo
        anidado y se filtran sus relaciones embebidas.)"""
        diagrama = await Diagrama.find_one(
            {
                "$or": [
                    {"relaciones.id_clase_origen": clase_id},
                    {"relaciones.id_clase_destino": clase_id},
                ]
            }
        )
        if diagrama is None:
            return []
        return [
            r
            for r in diagrama.relaciones
            if clase_id in (r.id_clase_origen, r.id_clase_destino)
        ]

    async def exists_entre_clases(
        self,
        diagrama_id: PydanticObjectId,
        id_clase_origen: str,
        id_clase_destino: str,
        tipo_relacion: str,
    ) -> bool:
        diagrama = await Diagrama.get(diagrama_id)
        if diagrama is None:
            return False
        for r in diagrama.relaciones:
            if (
                r.id_clase_origen == id_clase_origen
                and r.id_clase_destino == id_clase_destino
                and r.tipo_relacion == tipo_relacion
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # Escrituras (reciben el Diagrama re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self, diagrama: Diagrama, relacion: RelacionUML
    ) -> RelacionUML:
        diagrama.relaciones.append(relacion)
        await diagrama.save()
        return relacion

    async def update(
        self, diagrama: Diagrama, relacion: RelacionUML
    ) -> RelacionUML:
        await diagrama.save()
        return relacion

    async def delete(
        self, diagrama: Diagrama, relacion: RelacionUML
    ) -> None:
        diagrama.relaciones = [
            r for r in diagrama.relaciones if r.id != relacion.id
        ]
        await diagrama.save()

    async def delete_by_clase(
        self, diagrama: Diagrama, clase_id: str
    ) -> int:
        """Elimina relaciones donde la clase sea origen o destino.
        Devuelve cuántas borró. (En el Ciclo 1 bastaba el id int con un
        DELETE por FK; ahora la escritura es sobre el padre, así que
        recibe el Diagrama re-leído — el servicio ya lo tiene en mano
        cuando elimina una clase.)"""
        a_eliminar = [
            r
            for r in diagrama.relaciones
            if clase_id in (r.id_clase_origen, r.id_clase_destino)
        ]
        diagrama.relaciones = [
            r
            for r in diagrama.relaciones
            if clase_id not in (r.id_clase_origen, r.id_clase_destino)
        ]
        if a_eliminar:
            await diagrama.save()
        return len(a_eliminar)