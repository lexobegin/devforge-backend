# app/services/ia_service.py
"""
Lógica de negocio del módulo G. IA Asistente (modo online).

Cubre:
- Recibir prompts de voz/texto, persistirlos en `interacciones_ia`, delegar
  en el proveedor de IA (interno o externo) y devolver la acción estructurada
  al cliente para que confirme o aplique.
- Confirmar acciones propuestas (aplicar al diagrama).
- Historial de interacciones por proyecto / diagrama / usuario.

IMPORTANTE: la IA de visión (boceto/imagen) NO vive aquí, vive en
`app/ai_vision/`. Aquí solo cubrimos prompts de voz/texto.
"""

from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    AIServiceError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.ia import InteraccionIA
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.ia_repository import InteraccionIARepository
from app.repositories.proyecto_repository import (
    MiembroProyectoRepository,
    ProyectoRepository,
)
from app.schemas.ia_schema import (
    AccionIAPropuesta,
    InteraccionIAResponse,
    PromptIARequest,
    RespuestaIA,
)


class IAService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.interacciones = InteraccionIARepository(db)
        self.diagramas = DiagramaRepository(db)
        self.proyectos = ProyectoRepository(db)
        self.miembros = MiembroProyectoRepository(db)

    # ==================================================================
    # PROMPTS DE VOZ / TEXTO
    # ==================================================================
    async def procesar_prompt(
        self,
        proyecto_id: int,
        datos: PromptIARequest,
        *,
        usuario_id: int,
    ) -> RespuestaIA:
        """
        Procesa un prompt de voz/texto (modo online):
        1) Verifica permisos del usuario en el proyecto / diagrama.
        2) Persiste la interacción en `interacciones_ia`.
        3) Delega en el proveedor de IA para obtener la respuesta y las
           acciones propuestas.
        4) Devuelve la respuesta al cliente SIN aplicar los cambios
           (el cliente debe confirmar con `confirmar_acciones`).
        """
        # Verificación de permisos
        await self._require_editor_en_proyecto(proyecto_id, usuario_id)

        if datos.id_diagrama is not None:
            diagrama = await self.diagramas.get_by_id(datos.id_diagrama)
            if diagrama is None or diagrama.id_proyecto != proyecto_id:
                raise ValidationError(
                    "El diagrama indicado no pertenece a este proyecto"
                )

        # Persistir la interacción (sin acciones aplicadas todavía)
        interaccion = InteraccionIA(
            id_proyecto=proyecto_id,
            id_diagrama=datos.id_diagrama,
            id_usuario=usuario_id,
            canal=datos.canal,
            texto_prompt=datos.texto_prompt.strip(),
            respuesta_ia=None,
            accion_aplicada=False,
        )
        interaccion = await self.interacciones.create(interaccion)

        # Llamar al proveedor de IA
        try:
            resultado = await self._invocar_proveedor_ia(
                prompt=interaccion.texto_prompt,
                contexto=datos.contexto or {},
                canal=datos.canal,
            )
        except AIServiceError:
            # Persistimos el fallo para auditoría
            interaccion.respuesta_ia = {"error": "AI_PROVIDER_FAILED"}
            await self.interacciones.update(interaccion)
            await self.db.commit()
            raise

        # Guardar la respuesta cruda en la interacción
        interaccion.respuesta_ia = {
            "texto_respuesta": resultado.get("texto_respuesta", ""),
            "acciones_propuestas": [
                a.model_dump() for a in resultado.get("acciones_propuestas", [])
            ],
        }
        await self.interacciones.update(interaccion)
        await self.db.commit()
        await self.db.refresh(interaccion)

        return RespuestaIA(
            texto_respuesta=interaccion.respuesta_ia["texto_respuesta"],
            acciones_propuestas=[
                AccionIAPropuesta(**a)
                for a in interaccion.respuesta_ia["acciones_propuestas"]
            ],
            requiere_confirmacion=True,
        )

    async def confirmar_acciones(
        self,
        interaccion_id: int,
        indices: list[int],
        *,
        usuario_id: int,
    ) -> InteraccionIAResponse:
        """
        Marca como aplicadas las acciones de una interacción.
        El cliente ya aplicó los cambios al diagrama vía WS; este método
        solo deja constancia de que la acción fue aplicada y por quién.
        """
        interaccion = await self.interacciones.get_by_id(interaccion_id)
        if interaccion is None:
            raise NotFoundError("Interacción no encontrada")

        if interaccion.id_usuario != usuario_id:
            raise ForbiddenError(
                "Solo el autor de la interacción puede confirmar sus acciones"
            )

        if not interaccion.respuesta_ia:
            raise ValidationError(
                "La interacción no tiene acciones propuestas para confirmar"
            )

        propuestas = interaccion.respuesta_ia.get("acciones_propuestas", [])
        if not indices:
            indices = list(range(len(propuestas)))

        # Validar índices
        for idx in indices:
            if idx < 0 or idx >= len(propuestas):
                raise ValidationError(f"Índice de acción inválido: {idx}")

        # Marcar como aplicadas
        interaccion.accion_aplicada = True
        interaccion.respuesta_ia["acciones_aplicadas"] = indices

        await self.interacciones.update(interaccion)
        await self.db.commit()
        await self.db.refresh(interaccion)
        return InteraccionIAResponse.model_validate(interaccion)

    # ==================================================================
    # HISTORIAL
    # ==================================================================
    async def listar_por_diagrama(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InteraccionIAResponse]:
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro_en_proyecto(diagrama.id_proyecto, usuario_id)

        items = await self.interacciones.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )
        return [InteraccionIAResponse.model_validate(i) for i in items]

    async def listar_por_proyecto(
        self,
        proyecto_id: int,
        *,
        usuario_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InteraccionIAResponse]:
        await self._require_miembro_en_proyecto(proyecto_id, usuario_id)
        items = await self.interacciones.list_by_proyecto(
            proyecto_id, skip=skip, limit=limit
        )
        return [InteraccionIAResponse.model_validate(i) for i in items]

    async def obtener_interaccion(
        self, interaccion_id: int, *, usuario_id: int
    ) -> InteraccionIAResponse:
        interaccion = await self.interacciones.get_by_id(interaccion_id)
        if interaccion is None:
            raise NotFoundError("Interacción no encontrada")

        # El usuario debe pertenecer al proyecto de la interacción
        await self._require_miembro_en_proyecto(
            interaccion.id_proyecto, usuario_id
        )
        return InteraccionIAResponse.model_validate(interaccion)

    # ==================================================================
    # PROVEEDOR IA (punto de extensión)
    # ==================================================================
    async def _invocar_proveedor_ia(
        self,
        *,
        prompt: str,
        contexto: dict[str, Any],
        canal: str,
    ) -> dict[str, Any]:
        """
        Punto de extensión para el proveedor de IA (nube).

        Estrategia:
        - `settings.AI_PROVIDER` selecciona el backend.
        - Implementación por defecto: parser interno simple (heurística).
        - Cuando se integre un proveedor externo (OpenAI, etc.), se agrega
          un cliente aquí sin tocar el resto del servicio.
        """
        proveedor = (settings.AI_PROVIDER or "internal").lower()

        if proveedor == "internal":
            return self._parser_interno(prompt, contexto)

        # Extensible: if proveedor == "openai": return await self._call_openai(...)
        raise AIServiceError(
            f"Proveedor de IA no soportado todavía: '{proveedor}'"
        )

    def _parser_interno(
        self, prompt: str, contexto: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Parser heurístico mínimo para prompts en español.
        Reconoce órdenes simples como:
          - "crea la clase Paciente"
          - "agrega el atributo nombre a la clase Paciente"
        En producción se reemplaza por un modelo NLP real (online).
        """
        texto = prompt.strip()
        bajo = texto.lower()

        acciones: list[AccionIAPropuesta] = []
        respuesta = (
            "He recibido tu solicitud. Estas son las acciones que propongo:"
        )

        # CREAR_CLASE
        if bajo.startswith(("crea la clase", "crear clase", "crea clase")):
            nombre = self._extraer_nombre_despues_de(
                texto, ["crea la clase", "crear clase", "crea clase"]
            )
            if nombre:
                acciones.append(
                    AccionIAPropuesta(
                        tipo="CREAR_CLASE",
                        payload={"nombre": nombre},
                        descripcion=f"Crear la clase {nombre}",
                    )
                )

        # AGREGAR_ATRIBUTO
        elif "atributo" in bajo and "clase" in bajo:
            nombre_attr = self._extraer_nombre_despues_de(
                texto, ["agrega el atributo", "agregar atributo", "agrega atributo"]
            )
            nombre_clase = self._extraer_nombre_despues_de(
                texto, ["a la clase", "en la clase"]
            )
            if nombre_attr and nombre_clase:
                acciones.append(
                    AccionIAPropuesta(
                        tipo="AGREGAR_ATRIBUTO",
                        payload={
                            "clase": nombre_clase,
                            "atributo": nombre_attr,
                            "tipo_dato": "String",
                        },
                        descripcion=(
                            f"Agregar atributo {nombre_attr} "
                            f"a la clase {nombre_clase}"
                        ),
                    )
                )

        # Fallback genérico
        if not acciones:
            respuesta = (
                "No pude interpretar una acción concreta en tu solicitud. "
                "Prueba con: 'crea la clase Paciente' o "
                "'agrega el atributo nombre a la clase Paciente'."
            )

        return {
            "texto_respuesta": respuesta,
            "acciones_propuestas": acciones,
        }

    @staticmethod
    def _extraer_nombre_despues_de(texto: str, prefijos: list[str]) -> Optional[str]:
        """
        Dada una frase y una lista de prefijos, devuelve la palabra/frase
        inmediatamente posterior al primer prefijo encontrado (case-insensitive).
        """
        bajo = texto.lower()
        for prefijo in prefijos:
            idx = bajo.find(prefijo.lower())
            if idx >= 0:
                resto = texto[idx + len(prefijo):].strip()
                if not resto:
                    return None
                # Tomar hasta el primer separador obvio
                for sep in [",", ".", ";", " para ", " con ", " que "]:
                    if sep in resto.lower():
                        resto = resto[: resto.lower().find(sep)].strip()
                # Solo la primera palabra/clase
                return resto.split()[0] if resto else None
        return None

    # ==================================================================
    # HELPERS
    # ==================================================================
    async def _require_miembro_en_proyecto(
        self, proyecto_id: int, usuario_id: int
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")

    async def _require_editor_en_proyecto(
        self, proyecto_id: int, usuario_id: int
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ForbiddenError(
                "Se requiere rol EDITOR o PROPIETARIO en el proyecto"
            )