# app/repositories/usuario_repository.py
"""
Repositorio de acceso a datos para el módulo A. Usuarios y Seguridad.

No contiene lógica de negocio (eso es `services/auth_service.py`).
Solo operaciones atómicas sobre la COLECCIÓN `usuarios`.

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Ya no recibe AsyncSession: Beanie se inicializa UNA sola vez
  (app/mongo.init_db) y los documentos llevan la conexión. Los
  repositorios quedan SIN ESTADO (los services pueden instanciarlos una
  única vez y reutilizarlos).
- get_by_id recibe PydanticObjectId (ObjectId de Mongo), no int.
- La búsqueda case-insensitive por email (func.lower de SQL) se resuelve
  con una expresión regular anclada con $options:"i": mismo resultado sin
  depender de cómo se guardó el email.
- create/update/delete ya no hacen flush/refresh: insert()/save()/delete()
  de Beanie escriben en Mongo y dejan el documento en memoria actualizado.
"""

import re
from typing import Optional, Sequence

from beanie import PydanticObjectId

from app.models.usuario import Usuario


def _regex_exacto(texto: str) -> str:
    """
    Expresión regular que coincide EXACTAMENTE con `texto` sin distinguir
    mayúsculas/minúsculas (equivale a func.lower(email) == email.lower()
    del Ciclo 1). El texto se escapa para que el punto del email (y
    cualquier otro carácter especial) no se interprete como patrón.
    """
    return f"^{re.escape(texto)}$"


class UsuarioRepository:
    """Operaciones CRUD y consultas sobre la colección `usuarios`."""

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    async def get_by_id(
        self, usuario_id: PydanticObjectId
    ) -> Optional[Usuario]:
        return await Usuario.get(usuario_id)

    async def get_by_email(self, email: str) -> Optional[Usuario]:
        return await Usuario.find_one(
            {"email": {"$regex": _regex_exacto(email), "$options": "i"}}
        )

    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        solo_activos: bool = False,
    ) -> Sequence[Usuario]:
        consulta = (
            Usuario.find(Usuario.activo == True)  # noqa: E712
            if solo_activos
            else Usuario.find_all()
        )
        return await (
            consulta.sort(-Usuario.created_at)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    async def count(self, *, solo_activos: bool = False) -> int:
        consulta = (
            Usuario.find(Usuario.activo == True)  # noqa: E712
            if solo_activos
            else Usuario.find_all()
        )
        return await consulta.count()

    async def email_exists(
        self,
        email: str,
        *,
        exclude_id: Optional[PydanticObjectId] = None,
    ) -> bool:
        filtro: dict = {
            "email": {"$regex": _regex_exacto(email), "$options": "i"}
        }
        if exclude_id is not None:
            filtro["_id"] = {"$ne": exclude_id}
        return await Usuario.find_one(filtro) is not None

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------
    async def create(self, usuario: Usuario) -> Usuario:
        await usuario.insert()   # asigna el ObjectId y persiste
        return usuario

    async def update(self, usuario: Usuario) -> Usuario:
        await usuario.save()
        return usuario

    async def delete(self, usuario: Usuario) -> None:
        await usuario.delete()

    async def set_activo(
        self, usuario_id: PydanticObjectId, activo: bool
    ) -> Optional[Usuario]:
        usuario = await self.get_by_id(usuario_id)
        if usuario is None:
            return None
        usuario.activo = activo
        await usuario.save()
        return usuario