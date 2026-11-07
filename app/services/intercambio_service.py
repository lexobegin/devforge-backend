# app/services/intercambio_service.py
"""
Lógica de negocio del módulo E. Intercambio de Modelos (XMI/XML).

Cubre:
- Exportar un diagrama a XMI/XML: genera el archivo, lo persiste en
  EXPORT_DIR y registra la exportación.
- Importar un XMI/XML: parsea el archivo, reconstruye clases/atributos/
  relaciones y los inserta en el diagrama destino, registrando la importación.

La conversión diagrama ↔ XMI se delega en `app/utils/xmi_converter.py`
(que en la VM conserva el Ciclo 1: [IGUAL]).

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- Servicio SIN ESTADO: sin AsyncSession ni commit()/refresh(). El registro
  de exportación se crea con insert() y el de importación se actualiza con
  save() del propio documento; en el Ciclo 1 cada paso necesitaba commit.
- Ids: diagrama_id/usuario_id pasan de int a PydanticObjectId.
- La importación MERGE cambia de mecánica: en el Ciclo 1 cada clase/
  atributo/operación/relación era una fila con INSERT propio dentro de una
  transacción; en el Ciclo 2 TODO el contenido va embebido en el documento
  Diagrama, así que _aplicar_estructura_a_diagrama ARMA el documento
  re-leído en memoria y lo persiste con UN único save() (el equivalente
  a la transacción única del Ciclo 1). Por eso los repositorios de los
  embebidos (clases/atributos/operaciones/relaciones) ya no se instancian
  aquí: el chequeo "¿ya existe una relación igual?" se resuelve en memoria
  contra diagrama.relaciones, porque lo nuevo todavía no está en la base.
- exportar_diagrama: en el Ciclo 1 quedaron DOS llamadas a diagrama_a_xmi
  (una fuera del try sin usar el formato pedido y otra dentro que lo
  perdía); se FUSIONAN en una sola llamada dentro del try pasando
  formato_interno, y el formato 'EA' ahora sí llega al conversor.
- La lectura del diagrama sigue siendo get_completo() (1 documento atómico
  en el Ciclo 2, antes 4 selectinload).
- _require_editor/_require_miembro resuelven el miembro EMBEBIDO del
  proyecto (mensajes EXACTOS del Ciclo 1: aquí el rol insuficiente lanza
  ConflictError 409, a diferencia de otros servicios que usan
  ForbiddenError 422/403 — cada service conserva SU texto auténtico).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from beanie import PydanticObjectId

from app.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.diagrama import (
    AtributoUML,
    ClaseUML,
    OperacionUML,
    RelacionUML,
)
from app.models.intercambio import ExportacionDiagrama, ImportacionDiagrama
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.intercambio_repository import (
    ExportacionRepository,
    ImportacionRepository,
)
from app.repositories.proyecto_repository import MiembroProyectoRepository
from app.schemas.intercambio_schema import (
    ExportacionDiagramaResponse,
    ExportacionResultado,
    ImportacionDiagramaCreate,
    ImportacionDiagramaResponse,
    ImportacionResultado,
)


class IntercambioService:
    def __init__(self) -> None:
        self.diagramas = DiagramaRepository()
        self.exportaciones = ExportacionRepository()
        self.importaciones = ImportacionRepository()
        self.miembros = MiembroProyectoRepository()
        # (Los repositorios de clases/atributos/operaciones/relaciones del
        #  Ciclo 1 ya no se instancian: los embebidos se aplican en memoria
        #  sobre el documento y se persisten con un único save().)

    # ==================================================================
    # EXPORTACIÓN
    # ==================================================================
    async def exportar_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        formato: str = "XMI",
    ) -> ExportacionResultado:
        """
        Exporta el diagrama completo a un archivo XMI/XML y devuelve el
        registro + la URL de descarga.
        """
        # Cargar diagrama completo y validar permisos
        diagrama = await self.diagramas.get_completo(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        formato_norm = formato.upper()
        if formato_norm not in ("XMI", "XML", "EA"):
            raise ValidationError("Formato no soportado. Use 'XMI', 'XML' o 'EA'")

        # Generar el contenido (import local para evitar ciclos).
        # NOTA de conversión: el Ciclo 1 tenía una asignación duplicada de
        # `contenido` (una fuera del try sin aplicar el formato y otra
        # dentro del try que lo perdía). Aquí queda UNA sola llamada, con
        # formato_interno, dentro del try.
        from app.utils.xmi_converter import diagrama_a_xmi

        formato_interno = "ea" if formato_norm == "EA" else "devforge"
        try:
            contenido = diagrama_a_xmi(diagrama, formato=formato_interno)
        except Exception as exc:
            raise BadRequestError(
                f"No se pudo generar el XMI: {exc}"
            ) from exc

        # Persistir el archivo
        ruta_relativa = await self._guardar_archivo_export(
            diagrama_id=diagrama_id,
            contenido=contenido,
            formato=formato_norm,
        )

        # Registrar en BD (insert() ya deja el documento persistido con
        # su id y exported_at: desaparecen commit() + refresh()).
        exportacion = ExportacionDiagrama(
            id_diagrama=diagrama_id,
            formato=formato_norm,
            ruta_archivo=ruta_relativa,
            id_usuario=usuario_id,
        )
        exportacion = await self.exportaciones.create(exportacion)

        return ExportacionResultado(
            exportacion=ExportacionDiagramaResponse.model_validate(exportacion),
            download_url=self._construir_url_descarga(ruta_relativa),
        )

    async def listar_exportaciones(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        skip: int = 0,
        limit: int = 50,
    ):
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        items = await self.exportaciones.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )
        return [ExportacionDiagramaResponse.model_validate(i) for i in items]

    # ==================================================================
    # IMPORTACIÓN
    # ==================================================================
    async def importar_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        datos: ImportacionDiagramaCreate,
        contenido_xmi: str,
        *,
        usuario_id: PydanticObjectId,
    ) -> ImportacionResultado:
        """
        Importa un XMI/XML en el diagrama destino.
        Estrategia por defecto: MERGE — las clases existentes por nombre
        se saltan (no se sobreescriben), las nuevas se agregan.
        """
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_editor(diagrama.id_proyecto, usuario_id)

        formato = (datos.formato or "XMI").upper()
        if formato not in ("XMI", "XML"):
            raise ValidationError("Formato no soportado. Use 'XMI' o 'XML'")

        # Crear registro de importación en PENDIENTE
        importacion = ImportacionDiagrama(
            id_diagrama=diagrama_id,
            formato=formato,
            archivo_origen=datos.archivo_origen,
            estado="PENDIENTE",
            id_usuario=usuario_id,
        )
        importacion = await self.importaciones.create(importacion)

        # Parsear el contenido
        from app.utils.xmi_converter import xmi_a_estructura

        try:
            estructura = xmi_a_estructura(contenido_xmi)
        except Exception as exc:
            importacion.estado = "FALLIDO"
            await self.importaciones.update(importacion)
            raise BadRequestError(f"XMI inválido: {exc}") from exc

        # Aplicar al diagrama
        try:
            resumen = await self._aplicar_estructura_a_diagrama(
                diagrama_id, estructura, usuario_id
            )
        except Exception as exc:
            importacion.estado = "FALLIDO"
            await self.importaciones.update(importacion)
            raise BadRequestError(
                f"Error al aplicar el diagrama importado: {exc}"
            ) from exc

        importacion.estado = "EXITOSO"
        await self.importaciones.update(importacion)

        return ImportacionResultado(
            importacion=ImportacionDiagramaResponse.model_validate(importacion),
            resumen=resumen,
        )

    async def listar_importaciones(
        self,
        diagrama_id: PydanticObjectId,
        *,
        usuario_id: PydanticObjectId,
        skip: int = 0,
        limit: int = 50,
    ):
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        items = await self.importaciones.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )
        return [ImportacionDiagramaResponse.model_validate(i) for i in items]

    # ==================================================================
    # HELPERS INTERNOS
    # ==================================================================
    async def _aplicar_estructura_a_diagrama(
        self,
        diagrama_id: PydanticObjectId,
        estructura: dict[str, Any],
        usuario_id: PydanticObjectId,
    ) -> dict[str, int]:
        """
        Aplica el resultado del parser (dict con clases, atributos,
        operaciones y relaciones) al diagrama destino.
        Devuelve un resumen con conteos de lo insertado/saltado.

        En el Ciclo 2 el contenido va EMBEBIDO: se re-lee el documento, se
        agregan las entidades a sus listas en memoria y se persiste TODO
        con un único save() del padre (la "transacción" del Ciclo 1).
        """
        resumen = {
            "clases_insertadas": 0,
            "clases_saltadas": 0,
            "atributos_insertados": 0,
            "operaciones_insertadas": 0,
            "relaciones_insertadas": 0,
            "relaciones_saltadas": 0,
        }

        # Documento RE-LEÍDO (regla fetch → modificar → save del módulo C).
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            # Rara vez: borraron el diagrama entre el chequeo inicial y aquí.
            raise NotFoundError("Diagrama no encontrado")

        # Mapa temporal: nombre_clase → id uuid (para conectar relaciones).
        # Los ids son los uuid de los embebidos (antes ids int de fila).
        nombre_a_id: dict[str, str] = {}

        # 1) Clases existentes en el diagrama (por nombre, para merge)
        for c in diagrama.clases:
            nombre_a_id[c.nombre.lower()] = c.id

        # 2) Insertar clases (append en memoria; el save es único al final)
        for clase_data in estructura.get("clases", []):
            nombre = (clase_data.get("nombre") or "").strip()
            if not nombre:
                continue
            if nombre.lower() in nombre_a_id:
                resumen["clases_saltadas"] += 1
                continue

            clase = ClaseUML(
                nombre=nombre,
                es_abstracta=bool(clase_data.get("es_abstracta", False)),
                estereotipo=clase_data.get("estereotipo"),
                pos_x=clase_data.get("pos_x", 0),
                pos_y=clase_data.get("pos_y", 0),
                id_creador=usuario_id,
            )
            diagrama.clases.append(clase)
            nombre_a_id[nombre.lower()] = clase.id
            resumen["clases_insertadas"] += 1

            # 2.1) Atributos de la clase
            for i, attr_data in enumerate(clase_data.get("atributos", [])):
                attr = AtributoUML(
                    nombre=(attr_data.get("nombre") or "").strip(),
                    tipo_dato=attr_data.get("tipo_dato") or "String",
                    visibilidad=attr_data.get("visibilidad", "-"),
                    es_estatico=bool(attr_data.get("es_estatico", False)),
                    valor_defecto=attr_data.get("valor_defecto"),
                    orden=attr_data.get("orden", i),
                )
                clase.atributos.append(attr)
                resumen["atributos_insertados"] += 1

            # 2.2) Operaciones de la clase (sin parámetros por simplicidad;
            #      si el XMI los trae, se pueden agregar después)
            for i, op_data in enumerate(clase_data.get("operaciones", [])):
                op = OperacionUML(
                    nombre=(op_data.get("nombre") or "").strip(),
                    tipo_retorno=op_data.get("tipo_retorno") or "void",
                    visibilidad=op_data.get("visibilidad", "+"),
                    es_estatico=bool(op_data.get("es_estatico", False)),
                    orden=op_data.get("orden", i),
                )
                clase.operaciones.append(op)
                resumen["operaciones_insertadas"] += 1

        # 3) Insertar relaciones (solo si ambas clases existen)
        for rel_data in estructura.get("relaciones", []):
            origen_nombre = (rel_data.get("origen") or "").lower()
            destino_nombre = (rel_data.get("destino") or "").lower()
            tipo = rel_data.get("tipo", "ASOCIACION")

            if origen_nombre not in nombre_a_id or destino_nombre not in nombre_a_id:
                resumen["relaciones_saltadas"] += 1
                continue

            id_origen = nombre_a_id[origen_nombre]
            id_destino = nombre_a_id[destino_nombre]

            # En el Ciclo 1 era una consulta contra la tabla relaciones_uml;
            # aquí lo nuevo todavía NO está en la base, así que el chequeo
            # se hace en memoria contra las relaciones del documento.
            existe = any(
                r.id_clase_origen == id_origen
                and r.id_clase_destino == id_destino
                and r.tipo_relacion == tipo
                for r in diagrama.relaciones
            )
            if existe:
                resumen["relaciones_saltadas"] += 1
                continue

            relacion = RelacionUML(
                id_clase_origen=id_origen,
                id_clase_destino=id_destino,
                tipo_relacion=tipo,
                multiplicidad_origen=rel_data.get("multiplicidad_origen"),
                multiplicidad_destino=rel_data.get("multiplicidad_destino"),
                nombre_asociacion=rel_data.get("nombre_asociacion"),
                rol_origen=rel_data.get("rol_origen"),
                rol_destino=rel_data.get("rol_destino"),
            )
            diagrama.relaciones.append(relacion)
            resumen["relaciones_insertadas"] += 1

        # Persistencia ÚNICA del documento (el commit final del Ciclo 1)
        diagrama.updated_at = datetime.now(timezone.utc)
        await self.diagramas.update(diagrama)
        return resumen

    async def _guardar_archivo_export(
        self,
        *,
        diagrama_id: PydanticObjectId,
        contenido: str,
        formato: str,
    ) -> str:
        """
        Guarda el archivo XMI en disco bajo EXPORT_DIR.
        Devuelve la ruta relativa (no absoluta) para persistir en BD.
        """
        base_dir = Path(settings.EXPORT_DIR).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)

        extension = "xmi" if formato == "XMI" else "xml"
        nombre = f"diagrama_{diagrama_id}_{_timestamp()}.{extension}"
        ruta_abs = base_dir / nombre

        ruta_abs.write_text(contenido, encoding="utf-8")

        # Guardar relativa para no acoplar a rutas absolutas del servidor
        try:
            return str(ruta_abs.relative_to(base_dir))
        except ValueError:
            return nombre

    def _construir_url_descarga(self, ruta_relativa: str) -> str:
        """URL de descarga (relativa al backend público)."""
        base = settings.BACKEND_PUBLIC_URL.rstrip("/")
        return f"{base}/{settings.EXPORT_DIR.strip('/')}/{ruta_relativa}"

    async def _require_miembro(
        self, proyecto_id: PydanticObjectId, usuario_id: PydanticObjectId
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")

    async def _require_editor(
        self, proyecto_id: PydanticObjectId, usuario_id: PydanticObjectId
    ) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            # Este service conserva el ConflictError (409) del Ciclo 1,
            # a diferencia del diagrama_service que usa ValidationError.
            raise ConflictError(
                "Se requiere rol EDITOR o PROPIETARIO para esta operación"
            )


def _timestamp() -> str:
    """Formato compacto de timestamp para nombres de archivo.
    (El utcnow() naive del Ciclo 1 pasa a hora aware.)"""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")