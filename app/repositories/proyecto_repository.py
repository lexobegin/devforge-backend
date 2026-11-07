# app/repositories/proyecto_repository.py
"""
Repositorio de acceso a datos del módulo B. Proyectos y Miembros.

Incluye dos repositorios:
- ProyectoRepository          → colección `proyectos`
- MiembroProyectoRepository   → miembros EMBEBIDOS en Proyecto.miembros

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: repositorios SIN ESTADO (la conexión la lleva
  Beanie tras app/mongo.init_db()).
- La tabla miembros_proyecto desapareció: cada miembro va EMBEBIDO en su
  proyecto. Consecuencias en MiembroProyectoRepository:
    * Los miembros ya NO tienen id propio: la clave es el par
      (proyecto, id_usuario); get_by_id se retira.
    * Toda ESCRITURA recibe el DOCUMENTO Proyecto re-leído de la base,
      modifica su lista `miembros` y lo guarda (regla fetch→modificar→save
      de Beanie: en MongoDB no hay INSERT sobre una "tabla hija").
    * get_by_id(con_miembros=True) ya no necesita selectinload: leer el
      proyecto SIEMPRE trae sus miembros (el parámetro se retiró).
- list_for_usuario/count_for_usuario ya no hacen JOIN: MongoDB filtra
  directamente por el campo del embebido (miembros.id_usuario), y el
  DISTINCT del Ciclo 1 sobra (cada proyecto aparece una sola vez).
- La unicidad (id_proyecto, id_usuario) del uq_miembro del Ciclo 1 la
  verifica el SERVICIO con Proyecto.miembro(...) antes de insertar.
"""

from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.proyecto import MiembroProyecto, Proyecto


# ======================================================================
# ProyectoRepository
# ======================================================================
class ProyectoRepository:
    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, proyecto_id: PydanticObjectId
    ) -> Optional[Proyecto]:
        """Los miembros SIEMPRE vienen embebidos (antes con_miembros=True)."""
        return await Proyecto.get(proyecto_id)

    async def list_for_usuario(
        self,
        usuario_id: PydanticObjectId,
        *,
        skip: int = 0,
        limit: int = 50,
        incluir_archivados: bool = False,
    ) -> Sequence[Proyecto]:
        """
        Proyectos en los que el usuario participa (como propietario o
        miembro), ordenados por fecha de actualización descendente.
        El filtro sobre el embebido (miembros.id_usuario) sustituye al
        JOIN con miembros_proyecto del Ciclo 1.
        """
        condiciones = [Proyecto.miembros.id_usuario == usuario_id]
        if not incluir_archivados:
            condiciones.append(Proyecto.estado == "ACTIVO")
        return await (
            Proyecto.find(*condiciones)
            .sort(-Proyecto.updated_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count_for_usuario(
        self,
        usuario_id: PydanticObjectId,
        *,
        incluir_archivados: bool = False,
    ) -> int:
        condiciones = [Proyecto.miembros.id_usuario == usuario_id]
        if not incluir_archivados:
            condiciones.append(Proyecto.estado == "ACTIVO")
        return await Proyecto.find(*condiciones).count()

    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        incluir_archivados: bool = False,
    ) -> Sequence[Proyecto]:
        """Uso administrativo: todos los proyectos de la plataforma."""
        condiciones = []
        if not incluir_archivados:
            condiciones.append(Proyecto.estado == "ACTIVO")
        return await (
            Proyecto.find(*condiciones)
            .sort(-Proyecto.updated_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, proyecto: Proyecto) -> Proyecto:
        await proyecto.insert()
        return proyecto

    async def update(self, proyecto: Proyecto) -> Proyecto:
        await proyecto.save()
        return proyecto

    async def delete(self, proyecto: Proyecto) -> None:
        await proyecto.delete()

    async def archivar(
        self, proyecto_id: PydanticObjectId
    ) -> Optional[Proyecto]:
        proyecto = await self.get_by_id(proyecto_id)
        if proyecto is None:
            return None
        proyecto.estado = "ARCHIVADO"
        await proyecto.save()
        return proyecto

    async def activar(
        self, proyecto_id: PydanticObjectId
    ) -> Optional[Proyecto]:
        proyecto = await self.get_by_id(proyecto_id)
        if proyecto is None:
            return None
        proyecto.estado = "ACTIVO"
        await proyecto.save()
        return proyecto


# ======================================================================
# MiembroProyectoRepository (embebidos en Proyecto.miembros)
# ======================================================================
class MiembroProyectoRepository:
    """
    Operaciones sobre los miembros EMBEBIDOS de un proyecto.

    En el Ciclo 1 cada método recibía/devolvía filas de miembros_proyecto;
    en el Ciclo 2 la unidad de persistencia es el PROYECTO: los métodos de
    escritura reciben el documento Proyecto re-leído de la base, modifican
    su lista `miembros` y lo guardan. Si el servicio pasa un Proyecto viejo
    en memoria (no re-leído) Beanie puede sobrescribir cambios ajenos.
    """

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_proyecto_usuario(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> Optional[MiembroProyecto]:
        proyecto = await Proyecto.get(proyecto_id)
        if proyecto is None:
            return None
        return proyecto.miembro(usuario_id)

    async def list_by_proyecto(
        self, proyecto_id: PydanticObjectId
    ) -> Sequence[MiembroProyecto]:
        proyecto = await Proyecto.get(proyecto_id)
        if proyecto is None:
            return []
        return sorted(proyecto.miembros, key=lambda m: m.joined_at)

    async def list_by_usuario(
        self, usuario_id: PydanticObjectId
    ) -> list[tuple[Proyecto, MiembroProyecto]]:
        """
        Membresías del usuario en TODOS los proyectos. En el Ciclo 1
        devolvía filas sueltas con la FK; como el embebido no conoce a su
        padre, se devuelve el PAR (proyecto, membresía) para que el servicio
        sepa en qué proyecto es miembro.
        """
        proyectos = await Proyecto.find(
            Proyecto.miembros.id_usuario == usuario_id
        ).to_list()
        pares: list[tuple[Proyecto, MiembroProyecto]] = []
        for proyecto in proyectos:
            miembro = proyecto.miembro(usuario_id)
            if miembro is not None:
                pares.append((proyecto, miembro))
        return pares

    async def count_propietarios(
        self, proyecto_id: PydanticObjectId
    ) -> int:
        """Cuenta cuántos PROPIETARIO tiene un proyecto (para no dejar 0)."""
        proyecto = await Proyecto.get(proyecto_id)
        if proyecto is None:
            return 0
        return sum(
            1
            for m in proyecto.miembros
            if m.rol_en_proyecto == "PROPIETARIO"
        )

    # ------------------------------------------------------------------
    # Escrituras (reciben el Proyecto re-leído y lo persisten)
    # ------------------------------------------------------------------
    async def create(
        self, proyecto: Proyecto, miembro: MiembroProyecto
    ) -> MiembroProyecto:
        """
        Agrega el miembro al proyecto y persiste. La unicidad
        (id_proyecto, id_usuario) la verificó el servicio ANTES con
        Proyecto.miembro(id_usuario) (equivale al uq_miembro del Ciclo 1).
        """
        proyecto.miembros.append(miembro)
        await proyecto.save()
        return miembro

    async def update(
        self, proyecto: Proyecto, miembro: MiembroProyecto
    ) -> MiembroProyecto:
        await proyecto.save()
        return miembro

    async def delete(
        self, proyecto: Proyecto, miembro: MiembroProyecto
    ) -> None:
        # Se filtra por id_usuario (clave única) y no por igualdad de
        # objetos: pydantic compara por valores y podría borrar otro
        # miembro idéntico.
        proyecto.miembros = [
            m
            for m in proyecto.miembros
            if m.id_usuario != miembro.id_usuario
        ]
        await proyecto.save()

    async def delete_by_proyecto_usuario(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> bool:
        proyecto = await Proyecto.get(proyecto_id)
        if proyecto is None:
            return False
        miembro = proyecto.miembro(usuario_id)
        if miembro is None:
            return False
        proyecto.miembros = [
            m for m in proyecto.miembros if m.id_usuario != usuario_id
        ]
        await proyecto.save()
        return True