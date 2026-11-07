# app/services/ejecutor_acciones_service.py
"""
Lógica del EJECUTOR DE ACCIONES del Agente Dev (módulo G, CU18-CU21) —
CICLO 2.

ARCHIVO NUEVO del Ciclo 2 (no existe en el Ciclo 1): en el Ciclo 1 la
"acción" de la tabla interacciones_ia se marcaba aplicada/rechazada pero
NADA tocaba el lienzo (deficiencia 2: el chat "no hacía nada"). En el
Ciclo 2 este service es la ÚNICA puerta por la que una acción de la IA
llega a los elementos EMBEBIDOS del DiagramaDocument:

1. CONFIRMACIÓN EXPLÍCITA: el usuario confirma por ids de AccionIA
   (ConfirmarAccionIARequest); NINGUNA acción se aplica sola. Las
   propuestas nacen en el orquestador (PROPUESTA) y aquí solo se procesan
   si siguen PROPUESTA y pertenecen al usuario que confirma.
2. VALIDACIÓN con los esquemas del módulo C: el payload que propone el
   LLM se valida contra ClaseUMLCreate / ClaseUMLUpdate /
   AtributoUMLCreate / AtributoUMLUpdate / RelacionUMLCreate de
   diagrama_schema (la Tanda 7 los dejó listos para esto). Payload
   inválido → la acción queda FALLIDA con el motivo legible en
   detalle_resultado; NO se lanza excepción (el error es del MODELO, no
   del llamante — la respuesta de confirmación reporta cada acción con su
   estado final).
3. APLICACIÓN fetch → modificar → save (misma regla del módulo C/H): cada
   acción re-lee el Diagrama dueño, muta los arrays EMBEBIDOS y hace
   save() del PADRE completo. Sin transacciones en MongoDB, cada acción
   lleva SU ciclo completo: una acción fallida nunca deja mutaciones a
   medias en un documento compartido.
4. Puente de VOCABULARIO (prompt del Agente ↔ modelo del lienzo): el
   prompt pide visibilidades PUBLICO/PRIVADO/PROTEGIDO y relación
   HERENCIA (lenguaje llano); los embebidos usan los símbolos UML
   "+/-/#/~" y GENERALIZACION (UML 2.5.1). El ejecutor traduce ambas
   formas antes de validar (acepta las dos).
5. TIPOS SOPORTADOS: los 8 que tocan el lienzo (mismo despacho que
   _aplicar_cambio_offline del sincronizacion_service) + GENERAR_CODIGO,
   que no toca el lienzo: valida el id_proyecto (inyectado REAL por el
   orquestador) y queda APLICADA como registro para el generador (el
   service del generador la atiende desde la cola de acciones).

Diferencias con la cola offline del módulo H (misma mecánica, contexto
distinto):
- La cola offline REPLAYA cambios posiblemente viejos: re-aplicar algo ya
  aplicado es IDEMPOTENTE (devuelve el id sin error). El ejecutor aplica
  PROPUESTAS FRESCAS sobre el estado actual: si el elemento referenciado
  ya no existe, la acción es FALLIDA con el motivo (proponer editar una
  clase eliminada no puede "salir bien").
- El ejecutor NO marca ConflictError por nombres duplicados: crea/modifica
  y si la validación de negocio falla la acción queda FALLIDA (el motivo
  viaja al chat en detalle_resultado).

Permisos (mismo criterio defensivo que diagrama_service):
- aplicar exige ser dueño de la acción + rol EDITOR/PROPIETARIO del
  proyecto del diagrama (miembro ausente → 404 "Recurso no encontrado";
  rol insuficiente → ValidationError con el MISMO mensaje del módulo C).
- rechazar exige ser dueño de la acción (no toca el diagrama).
- las lecturas de pendientes exigen membresía de lectura.
- Errores del LLAMANTE (acción inexistente, ajena, ya procesada, sin
  permiso) SÍ se propagan como excepciones (los routers las mapean a
  HTTP en la Tanda 19).
"""

from datetime import datetime, timezone
from typing import Optional

from beanie import PydanticObjectId
from bson.errors import InvalidId
from pydantic import ValidationError as ValidacionPydantic

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.ia.prompts import VOCABULARIO_ACCIONES
from app.models.accion_ia import AccionIA
from app.models.diagrama import AtributoUML, ClaseUML, Diagrama, RelacionUML
from app.repositories.accion_ia_repository import AccionIARepository
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.agente_schema import AccionIAResponse, ConfirmarAccionIARequest
from app.schemas.diagrama_schema import (
    AtributoUMLCreate,
    AtributoUMLUpdate,
    ClaseUMLCreate,
    ClaseUMLUpdate,
    RelacionUMLCreate,
)


def _ahora() -> datetime:
    """Marca temporal aware (los modelos del Ciclo 2 no usan utcnow naive)."""
    return datetime.now(timezone.utc)


# ======================================================================
# Puente de vocabulario (prompt del Agente → embebidos del lienzo)
# ======================================================================
_MAPA_VISIBILIDAD = {
    "PUBLICO": "+",
    "PÚBLICO": "+",
    "PRIVADO": "-",
    "PROTEGIDO": "#",
    "PAQUETE": "~",
    "PACKAGE": "~",
}
_MAPA_TIPO_RELACION = {
    # El prompt del Agente usa "HERENCIA" (llano); UML 2.5.1 dice
    # GENERALIZACION. Los otros 4 tipos ya coinciden; REALIZACION (válido
    # en el lienzo) no está en el prompt pero se acepta tal cual.
    "HERENCIA": "GENERALIZACION",
}


def _traducir_payload(datos: dict) -> dict:
    """
    Copia del payload con 'visibilidad' (palabras → símbolos UML) y
    'tipo_relacion' (HERENCIA → GENERALIZACION) traducidos, recursivo en
    listas de atributos/operaciones. Las formas YA correctas pasan intactas.
    """
    traducido: dict = {}
    for clave, valor in datos.items():
        if clave == "visibilidad" and isinstance(valor, str):
            traducido[clave] = _MAPA_VISIBILIDAD.get(
                valor.strip().upper(), valor.strip()
            )
        elif clave == "tipo_relacion" and isinstance(valor, str):
            normalizado = valor.strip().upper()
            traducido[clave] = _MAPA_TIPO_RELACION.get(normalizado, normalizado)
        elif isinstance(valor, list):
            traducido[clave] = [
                _traducir_payload(x) if isinstance(x, dict) else x
                for x in valor
            ]
        else:
            traducido[clave] = valor
    return traducido


def _mensaje_validacion(exc: ValidacionPydantic) -> str:
    """Pydantic → motivo legible para detalle_resultado."""
    partes = []
    for error in exc.errors():
        campo = ".".join(str(p) for p in error.get("loc", ())) or "(raíz)"
        partes.append(f"{campo}: {error.get('msg', 'inválido')}")
    return "Payload inválido — " + "; ".join(partes)


# ======================================================================
# EjecutorAccionesService
# ======================================================================
class EjecutorAccionesService:
    """
    Aplica (o rechaza) las acciones PROPUESTA del Agente Dev sobre los
    embebidos del DiagramaDocument, con validación de esquemas del
    módulo C y el ciclo fetch → modificar → save.
    """

    def __init__(self) -> None:
        # Repositorios SIN ESTADO: la conexión la lleva Beanie. El
        # ejecutor no necesita costuras: los dobles de prueba viven en la
        # cadena del orquestador y en los documentos de mongomock.
        self.acciones = AccionIARepository()
        self.diagramas = DiagramaRepository()
        self.miembros = MiembroProyectoRepository()

    # ==================================================================
    # CONFIRMACIÓN (lote por ids)
    # ==================================================================
    async def confirmar_acciones(
        self,
        id_usuario: PydanticObjectId,
        datos: ConfirmarAccionIARequest,
    ) -> list[AccionIAResponse]:
        """
        Aplica las acciones confirmadas (ids de AccionIA) del mensaje
        indicado. Devuelve CADA acción con su estado final: APLICADA o
        FALLIDA (los fallos de payload/reportes van en detalle_resultado,
        no como excepciones). Los errores del llamante se propagan.
        """
        if not datos.acciones_a_aplicar:
            raise ValidationError(
                "Debe seleccionar al menos una acción a aplicar"
            )
        resultados: list[AccionIAResponse] = []
        for accion_id in datos.acciones_a_aplicar:
            accion = await self.aplicar_accion(
                id_usuario,
                accion_id,
                id_mensaje_esperado=datos.id_mensaje,
            )
            resultados.append(AccionIAResponse.model_validate(accion))
        return resultados

    # ==================================================================
    # APLICACIÓN INDIVIDUAL
    # ==================================================================
    async def aplicar_accion(
        self,
        id_usuario: PydanticObjectId,
        accion_id: PydanticObjectId,
        *,
        id_mensaje_esperado: Optional[PydanticObjectId] = None,
    ) -> AccionIA:
        """
        Aplica UNA acción PROPUESTA (dueño + permisos de edición) sobre el
        lienzo y la marca APLICADA (con el id real del elemento tocado) o
        FALLIDA (con el motivo del fallo de validación). Devuelve el
        documento AccionIA actualizado.

        `id_mensaje_esperado` es la trazabilidad del lote: si la
        confirmación llega por un mensaje y la acción nació de otro, se
        detecta ANTES de tocar el lienzo (ConflictError).
        """
        accion = await self.acciones.get_by_id(accion_id)
        if accion is None:
            raise NotFoundError("Acción no encontrada")
        if accion.id_usuario != id_usuario:
            raise ForbiddenError(
                "No puede confirmar acciones de otro usuario"
            )
        if accion.estado != "PROPUESTA":
            raise ConflictError(
                f"La acción ya fue procesada (estado {accion.estado})"
            )
        if (
            id_mensaje_esperado is not None
            and accion.id_mensaje is not None
            and accion.id_mensaje != id_mensaje_esperado
        ):
            raise ConflictError(
                "La acción no corresponde al mensaje indicado"
            )
        if accion.tipo_accion not in VOCABULARIO_ACCIONES:
            # Acción sembrada por otra vía con un tipo fuera del
            # vocabulario: es un error del payload del modelo.
            return await self._marcar_fallida(
                accion,
                f"Tipo de acción no soportado: '{accion.tipo_accion}'",
            )

        # GENERAR_CODIGO no toca el lienzo (puede vivir sin diagrama).
        if accion.tipo_accion == "GENERAR_CODIGO":
            return await self._aplicar_generar_codigo(accion)

        # --- acciones de lienzo: necesitan diagrama + permisos ---
        if accion.id_diagrama is None:
            return await self._marcar_fallida(
                accion, "La acción no indica el diagrama destino"
            )
        diagrama = await self.diagramas.get_by_id(accion.id_diagrama)
        if diagrama is None:
            # El diagrama fue eliminado después de la propuesta: el motivo
            # va en la acción (no es un error del llamante).
            return await self._marcar_fallida(
                accion, "El diagrama destino no existe en el servidor"
            )
        await self._require_editor(diagrama.id_proyecto, id_usuario)

        try:
            id_real = await self._aplicar_sobre_lienzo(
                accion.tipo_accion, accion.payload, diagrama, id_usuario
            )
        except ValidacionPydantic as exc:
            return await self._marcar_fallida(accion, _mensaje_validacion(exc))
        except ValidationError as exc:
            # Validación de negocio del propio ejecutor (unicidad,
            # referencias, campos): el motivo vuelve a la acción.
            return await self._marcar_fallida(accion, str(exc))

        accion.detalle_resultado = id_real
        accion.marcar_aplicada()
        await self.acciones.update(accion)
        return accion

    # ==================================================================
    # RECHAZO
    # ==================================================================
    async def rechazar_accion(
        self,
        id_usuario: PydanticObjectId,
        accion_id: PydanticObjectId,
        *,
        detalle: Optional[str] = None,
    ) -> AccionIA:
        """
        El usuario descarta una propuesta: la acción queda RECHAZADA (el
        lienzo no se toca, basta ser el dueño de la acción).
        """
        accion = await self.acciones.get_by_id(accion_id)
        if accion is None:
            raise NotFoundError("Acción no encontrada")
        if accion.id_usuario != id_usuario:
            raise ForbiddenError(
                "No puede rechazar acciones de otro usuario"
            )
        if accion.estado != "PROPUESTA":
            raise ConflictError(
                f"La acción ya fue procesada (estado {accion.estado})"
            )
        accion.marcar_rechazada(detalle or "Rechazada por el usuario")
        await self.acciones.update(accion)
        return accion

    # ==================================================================
    # LECTURAS (badge y bandeja de propuestas del chat)
    # ==================================================================
    async def listar_pendientes(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AccionIAResponse]:
        """
        Acciones PROPUESTA de un diagrama, la más nueva primero. Es la
        bandeja que el frontend usa para confirmar por ids (la RespuestaIA
        del canal lleva las propuestas SIN id: el id de confirmación vive
        en AccionIAResponse).
        """
        # El repositorio (cerrado en la Tanda 10) devuelve TODAS las
        # pendientes ordenadas por created_at DESC: el recorte skip/limit
        # se aplica en memoria — las pendientes esperan decisión del
        # usuario, la bandeja es corta.
        await self._diagrama_para_lectura(diagrama_id, usuario_id)
        items = await self.acciones.list_pendientes_by_diagrama(diagrama_id)
        recorte = items[skip : skip + limit]
        return [AccionIAResponse.model_validate(a) for a in recorte]

    async def contar_pendientes(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
    ) -> int:
        """Contador para el badge de propuestas sin resolver del chat."""
        await self._diagrama_para_lectura(diagrama_id, usuario_id)
        return await self.acciones.count_pendientes_by_diagrama(diagrama_id)

    # ==================================================================
    # APLICACIÓN SOBRE EL LIENZO (fetch → modificar → save por acción)
    # ==================================================================
    async def _aplicar_sobre_lienzo(
        self,
        tipo_accion: str,
        payload: dict,
        diagrama: Diagrama,
        id_usuario: PydanticObjectId,
    ) -> str:
        """
        Despacha la acción sobre el documento Diagrama re-leído. Devuelve
        el id REAL del elemento creado/modificado/eliminado (uuid del
        embebido). El uuid se genera en el constructor del embebido, ANTES
        del save(), así que es estable como id real aunque Beanie
        re-vincule los objetos tras persistir (hallazgo de la Tanda 12).
        """
        op = tipo_accion.upper()
        if op == "CREAR_CLASE":
            return await self._op_crear_clase(payload, diagrama, id_usuario)
        if op == "MODIFICAR_CLASE":
            return await self._op_modificar_clase(payload, diagrama)
        if op == "ELIMINAR_CLASE":
            return await self._op_eliminar_clase(payload, diagrama)
        if op == "AGREGAR_ATRIBUTO":
            return await self._op_agregar_atributo(payload, diagrama)
        if op == "MODIFICAR_ATRIBUTO":
            return await self._op_modificar_atributo(payload, diagrama)
        if op == "ELIMINAR_ATRIBUTO":
            return await self._op_eliminar_atributo(payload, diagrama)
        if op == "CREAR_RELACION":
            return await self._op_crear_relacion(payload, diagrama)
        if op == "ELIMINAR_RELACION":
            return await self._op_eliminar_relacion(payload, diagrama)
        raise ValidationError(
            f"Tipo de acción no soportado: '{tipo_accion}'"
        )

    # ------------------------------------------------------------------
    # Clases
    # ------------------------------------------------------------------
    async def _op_crear_clase(
        self,
        payload: dict,
        diagrama: Diagrama,
        id_usuario: PydanticObjectId,
    ) -> str:
        datos = ClaseUMLCreate.model_validate(_traducir_payload(payload))

        # Unicidad de nombre (en memoria sobre el documento re-leído: es
        # la fuente de verdad recién persistida, sin consultas extra).
        objetivo = datos.nombre.strip().casefold()
        if any(
            c.nombre.strip().casefold() == objetivo
            for c in diagrama.clases
        ):
            raise ValidationError(
                f"Ya existe una clase con el nombre '{datos.nombre}' "
                f"en el diagrama"
            )

        clase = ClaseUML(
            **datos.model_dump(),
            id_creador=id_usuario,
        )
        diagrama.clases.append(clase)
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return clase.id

    async def _op_modificar_clase(self, payload: dict, diagrama: Diagrama) -> str:
        id_clase = self._require_str(payload, "id_clase")
        clase = diagrama.clase(id_clase)
        if clase is None:
            raise ValidationError(
                "La clase a modificar no existe en el diagrama"
            )

        cambios = {
            k: v for k, v in payload.items() if k != "id_clase"
        }
        datos = ClaseUMLUpdate.model_validate(_traducir_payload(cambios))
        campos = datos.model_dump(exclude_unset=True)
        if not campos:
            raise ValidationError(
                "MODIFICAR_CLASE sin campos a actualizar"
            )

        nuevo_nombre = campos.get("nombre")
        if nuevo_nombre and nuevo_nombre != clase.nombre:
            objetivo = nuevo_nombre.strip().casefold()
            if any(
                c.id != clase.id
                and c.nombre.strip().casefold() == objetivo
                for c in diagrama.clases
            ):
                raise ValidationError(
                    f"El nombre '{nuevo_nombre}' ya está en uso en el diagrama"
                )

        for campo, valor in campos.items():
            setattr(clase, campo, valor)
        clase.updated_at = _ahora()
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return clase.id

    async def _op_eliminar_clase(self, payload: dict, diagrama: Diagrama) -> str:
        id_clase = self._require_str(payload, "id_clase")
        if diagrama.clase(id_clase) is None:
            raise ValidationError(
                "La clase a eliminar no existe en el diagrama"
            )
        # Cascada IN-MEMORIA: las relaciones que la referencian desaparecen
        # con ella (en el Ciclo 1 lo hacían las FK del módulo H/C).
        diagrama.relaciones = [
            r
            for r in diagrama.relaciones
            if r.id_clase_origen != id_clase
            and r.id_clase_destino != id_clase
        ]
        diagrama.clases = [
            c for c in diagrama.clases if c.id != id_clase
        ]
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return id_clase

    # ------------------------------------------------------------------
    # Atributos
    # ------------------------------------------------------------------
    async def _op_agregar_atributo(
        self, payload: dict, diagrama: Diagrama
    ) -> str:
        id_clase = self._require_str(payload, "id_clase")
        clase = diagrama.clase(id_clase)
        if clase is None:
            raise ValidationError(
                "La clase destino del atributo no existe en el diagrama"
            )
        resto = {k: v for k, v in payload.items() if k != "id_clase"}
        datos = AtributoUMLCreate.model_validate(_traducir_payload(resto))

        # Sin 'orden' explícito la atributo va al final (next_orden del
        # Ciclo 1: COALESCE(MAX,-1)+1 → len de la lista embebida).
        orden = resto.get("orden")
        if orden is None:
            orden = len(clase.atributos)
        campos = datos.model_dump()
        campos.pop("orden", None)

        atributo = AtributoUML(**campos, orden=orden)
        clase.atributos.append(atributo)
        clase.updated_at = _ahora()
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return atributo.id

    async def _op_modificar_atributo(
        self, payload: dict, diagrama: Diagrama
    ) -> str:
        id_clase = self._require_str(payload, "id_clase")
        id_atributo = self._require_str(payload, "id_atributo")
        clase = diagrama.clase(id_clase)
        if clase is None:
            raise ValidationError(
                "La clase del atributo no existe en el diagrama"
            )
        atributo = clase.atributo(id_atributo)
        if atributo is None:
            raise ValidationError(
                "El atributo a modificar no existe en la clase indicada"
            )
        resto = {
            k: v for k, v in payload.items()
            if k not in ("id_clase", "id_atributo")
        }
        datos = AtributoUMLUpdate.model_validate(_traducir_payload(resto))
        campos = datos.model_dump(exclude_unset=True)
        if not campos:
            raise ValidationError(
                "MODIFICAR_ATRIBUTO sin campos a actualizar"
            )
        for campo, valor in campos.items():
            setattr(atributo, campo, valor)
        clase.updated_at = _ahora()
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return atributo.id

    async def _op_eliminar_atributo(
        self, payload: dict, diagrama: Diagrama
    ) -> str:
        id_clase = self._require_str(payload, "id_clase")
        id_atributo = self._require_str(payload, "id_atributo")
        clase = diagrama.clase(id_clase)
        if clase is None:
            raise ValidationError(
                "La clase del atributo no existe en el diagrama"
            )
        if clase.atributo(id_atributo) is None:
            raise ValidationError(
                "El atributo a eliminar no existe en la clase indicada"
            )
        clase.atributos = [
            a for a in clase.atributos if a.id != id_atributo
        ]
        clase.updated_at = _ahora()
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return id_atributo

    # ------------------------------------------------------------------
    # Relaciones
    # ------------------------------------------------------------------
    async def _op_crear_relacion(
        self, payload: dict, diagrama: Diagrama
    ) -> str:
        datos = RelacionUMLCreate.model_validate(_traducir_payload(payload))

        # Referencias REALES: los ids uuid de las clases embebidas del
        # MISMO diagrama (en el Ciclo 1 eran FK; aquí, helpers del doc).
        if (
            diagrama.clase(datos.id_clase_origen) is None
            or diagrama.clase(datos.id_clase_destino) is None
        ):
            raise ValidationError(
                "Alguna de las clases de la relación no existe en el diagrama"
            )
        # Unicidad (origen, destino, tipo) en memoria sobre el doc re-leído.
        if any(
            r.id_clase_origen == datos.id_clase_origen
            and r.id_clase_destino == datos.id_clase_destino
            and r.tipo_relacion == datos.tipo_relacion
            for r in diagrama.relaciones
        ):
            raise ValidationError(
                "Ya existe una relación de ese tipo entre esas clases"
            )

        relacion = RelacionUML(**datos.model_dump())
        diagrama.relaciones.append(relacion)
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return relacion.id

    async def _op_eliminar_relacion(
        self, payload: dict, diagrama: Diagrama
    ) -> str:
        id_relacion = self._require_str(payload, "id_relacion")
        if diagrama.relacion(id_relacion) is None:
            raise ValidationError(
                "La relación a eliminar no existe en el diagrama"
            )
        diagrama.relaciones = [
            r for r in diagrama.relaciones if r.id != id_relacion
        ]
        diagrama.updated_at = _ahora()
        await self.diagramas.update(diagrama)
        return id_relacion

    # ------------------------------------------------------------------
    # GENERAR_CODIGO (no toca el lienzo)
    # ------------------------------------------------------------------
    async def _aplicar_generar_codigo(self, accion: AccionIA) -> AccionIA:
        """
        La acción queda APLICADA como registro para el generador (el
        service del generador la atiende desde la cola de acciones):
        solo se valida que el id_proyecto sea REAL (el orquestador lo
        inyectó del diagrama del turno).
        """
        id_proyecto = accion.payload.get("id_proyecto")
        try:
            PydanticObjectId(id_proyecto)
        except (TypeError, ValueError, InvalidId):
            # InvalidId de bson ya NO hereda de ValueError (bson>=4.9
            # usa BSONError): se lista explícita para no dejar escapar
            # ids basura del payload del modelo.
            return await self._marcar_fallida(
                accion,
                "GENERAR_CODIGO requiere un id_proyecto válido en el payload",
            )
        accion.detalle_resultado = (
            f"Generación de código registrada para el proyecto "
            f"{id_proyecto} (el generador la atiende desde la cola)"
        )
        accion.marcar_aplicada()
        await self.acciones.update(accion)
        return accion

    # ==================================================================
    # HELPERS INTERNOS
    # ==================================================================
    async def _marcar_fallida(self, accion: AccionIA, motivo: str) -> AccionIA:
        """Fallo de PAYLOAD/validación: se DEVUELVE (no se lanza) para que
        la respuesta de confirmación reporte el estado final de cada acción."""
        accion.marcar_fallida(motivo)
        await self.acciones.update(accion)
        return accion

    async def _require_editor(
        self,
        proyecto_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> None:
        """
        Mismo criterio que diagrama_service._require_editor (módulo C):
        miembro ausente → 404 genérico; rol insuficiente → ValidationError
        con el MISMO mensaje (consistencia de mensajes entre módulos).
        """
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ValidationError(
                "Se requiere rol EDITOR o PROPIETARIO para modificar el diagrama"
            )

    async def _diagrama_para_lectura(
        self,
        diagrama_id: PydanticObjectId,
        usuario_id: PydanticObjectId,
    ) -> Diagrama:
        """Diagrama existente + membresía de lectura (misma defensa del
        módulo C: ajeno → 404 genérico, inexistente → mensaje explícito)."""
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        miembro = await self.miembros.get_by_proyecto_usuario(
            diagrama.id_proyecto, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        return diagrama

    @staticmethod
    def _require_str(payload: dict, clave: str) -> str:
        """El payload del LLM debe traer el id uuid como string no vacío."""
        valor = payload.get(clave)
        if not isinstance(valor, str) or not valor.strip():
            raise ValidationError(
                f"El payload de la acción debe incluir '{clave}' "
                f"(id uuid del elemento)"
            )
        return valor