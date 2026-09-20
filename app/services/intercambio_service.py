# app/services/intercambio_service.py
"""
Lógica de negocio del módulo E. Intercambio de Modelos (XMI/XML).

Cubre:
- Exportar un diagrama a XMI/XML: genera el archivo, lo persiste en
  EXPORT_DIR y registra la exportación.
- Importar un XMI/XML: parsea el archivo, reconstruye clases/atributos/
  relaciones y los inserta en el diagrama destino, registrando la importación.

La conversión diagrama ↔ XMI se delega en `app/utils/xmi_converter.py`.
"""

from pathlib import Path
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.repositories.diagrama_repository import (
    AtributoUMLRepository,
    ClaseUMLRepository,
    DiagramaRepository,
    OperacionUMLRepository,
    RelacionUMLRepository,
)
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
    def __init__(self, db: AsyncSession):
        self.db = db
        self.diagramas = DiagramaRepository(db)
        self.clases = ClaseUMLRepository(db)
        self.atributos = AtributoUMLRepository(db)
        self.operaciones = OperacionUMLRepository(db)
        self.relaciones = RelacionUMLRepository(db)
        self.exportaciones = ExportacionRepository(db)
        self.importaciones = ImportacionRepository(db)
        self.miembros = MiembroProyectoRepository(db)

    # ==================================================================
    # EXPORTACIÓN
    # ==================================================================
    async def exportar_diagrama(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
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

        # Generar el contenido (import local para evitar ciclos)
        from app.utils.xmi_converter import diagrama_a_xmi

        formato_interno = "ea" if formato_norm == "EA" else "devforge"
        contenido = diagrama_a_xmi(diagrama, formato=formato_interno)

        try:
            contenido = diagrama_a_xmi(diagrama)
        except Exception as exc:
            raise BadRequestError(
                f"No se pudo generar el XMI: {exc}"
            ) from exc

        # Persistir el archivo
        ruta_relativa = await self._guardar_archivo_export(
            diagrama_id=diagrama_id,
            contenido=contenido,
            formato=formato,
        )

        # Registrar en BD
        exportacion = ExportacionDiagrama(
            id_diagrama=diagrama_id,
            formato=formato,
            ruta_archivo=ruta_relativa,
            id_usuario=usuario_id,
        )
        exportacion = await self.exportaciones.create(exportacion)
        await self.db.commit()
        await self.db.refresh(exportacion)

        return ExportacionResultado(
            exportacion=ExportacionDiagramaResponse.model_validate(exportacion),
            download_url=self._construir_url_descarga(ruta_relativa),
        )

    async def listar_exportaciones(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
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
        diagrama_id: int,
        datos: ImportacionDiagramaCreate,
        contenido_xmi: str,
        *,
        usuario_id: int,
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
            await self.db.commit()
            raise BadRequestError(f"XMI inválido: {exc}") from exc

        # Aplicar al diagrama
        try:
            resumen = await self._aplicar_estructura_a_diagrama(
                diagrama_id, estructura, usuario_id
            )
        except Exception as exc:
            importacion.estado = "FALLIDO"
            await self.importaciones.update(importacion)
            await self.db.commit()
            raise BadRequestError(
                f"Error al aplicar el diagrama importado: {exc}"
            ) from exc

        importacion.estado = "EXITOSO"
        await self.importaciones.update(importacion)
        await self.db.commit()
        await self.db.refresh(importacion)

        return ImportacionResultado(
            importacion=ImportacionDiagramaResponse.model_validate(importacion),
            resumen=resumen,
        )

    async def listar_importaciones(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
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
        diagrama_id: int,
        estructura: dict[str, Any],
        usuario_id: int,
    ) -> dict[str, int]:
        """
        Aplica el resultado del parser (dict con clases, atributos,
        operaciones y relaciones) al diagrama destino.
        Devuelve un resumen con conteos de lo insertado/saltado.
        """
        resumen = {
            "clases_insertadas": 0,
            "clases_saltadas": 0,
            "atributos_insertados": 0,
            "operaciones_insertadas": 0,
            "relaciones_insertadas": 0,
            "relaciones_saltadas": 0,
        }

        # Mapa temporal: nombre_clase -> id real (para conectar relaciones)
        nombre_a_id: dict[str, int] = {}

        # 1) Clases existentes en el diagrama (por nombre, para merge)
        clases_existentes = await self.clases.list_by_diagrama(diagrama_id)
        for c in clases_existentes:
            nombre_a_id[c.nombre.lower()] = c.id

        # 2) Insertar clases
        for clase_data in estructura.get("clases", []):
            nombre = (clase_data.get("nombre") or "").strip()
            if not nombre:
                continue
            if nombre.lower() in nombre_a_id:
                resumen["clases_saltadas"] += 1
                continue

            clase = ClaseUML(
                id_diagrama=diagrama_id,
                nombre=nombre,
                es_abstracta=bool(clase_data.get("es_abstracta", False)),
                estereotipo=clase_data.get("estereotipo"),
                pos_x=clase_data.get("pos_x", 0),
                pos_y=clase_data.get("pos_y", 0),
                id_creador=usuario_id,
            )
            clase = await self.clases.create(clase)
            nombre_a_id[nombre.lower()] = clase.id
            resumen["clases_insertadas"] += 1

            # 2.1) Atributos de la clase
            for i, attr_data in enumerate(clase_data.get("atributos", [])):
                attr = AtributoUML(
                    id_clase=clase.id,
                    nombre=(attr_data.get("nombre") or "").strip(),
                    tipo_dato=attr_data.get("tipo_dato") or "String",
                    visibilidad=attr_data.get("visibilidad", "-"),
                    es_estatico=bool(attr_data.get("es_estatico", False)),
                    valor_defecto=attr_data.get("valor_defecto"),
                    orden=attr_data.get("orden", i),
                )
                await self.atributos.create(attr)
                resumen["atributos_insertados"] += 1

            # 2.2) Operaciones de la clase (sin parámetros por simplicidad;
            #      si el XMI los trae, se pueden agregar después)
            for i, op_data in enumerate(clase_data.get("operaciones", [])):
                op = OperacionUML(
                    id_clase=clase.id,
                    nombre=(op_data.get("nombre") or "").strip(),
                    tipo_retorno=op_data.get("tipo_retorno") or "void",
                    visibilidad=op_data.get("visibilidad", "+"),
                    es_estatico=bool(op_data.get("es_estatico", False)),
                    orden=op_data.get("orden", i),
                )
                await self.operaciones.create(op)
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

            existe = await self.relaciones.exists_entre_clases(
                diagrama_id, id_origen, id_destino, tipo
            )
            if existe:
                resumen["relaciones_saltadas"] += 1
                continue

            relacion = RelacionUML(
                id_diagrama=diagrama_id,
                id_clase_origen=id_origen,
                id_clase_destino=id_destino,
                tipo_relacion=tipo,
                multiplicidad_origen=rel_data.get("multiplicidad_origen"),
                multiplicidad_destino=rel_data.get("multiplicidad_destino"),
                nombre_asociacion=rel_data.get("nombre_asociacion"),
                rol_origen=rel_data.get("rol_origen"),
                rol_destino=rel_data.get("rol_destino"),
            )
            await self.relaciones.create(relacion)
            resumen["relaciones_insertadas"] += 1

        return resumen

    async def _guardar_archivo_export(
        self,
        *,
        diagrama_id: int,
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

    async def _require_miembro(self, proyecto_id: int, usuario_id: int) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")

    async def _require_editor(self, proyecto_id: int, usuario_id: int) -> None:
        miembro = await self.miembros.get_by_proyecto_usuario(
            proyecto_id, usuario_id
        )
        if miembro is None:
            raise NotFoundError("Recurso no encontrado")
        if miembro.rol_en_proyecto not in ("PROPIETARIO", "EDITOR"):
            raise ConflictError(
                "Se requiere rol EDITOR o PROPIETARIO para esta operación"
            )


def _timestamp() -> str:
    """Formato compacto de timestamp para nombres de archivo."""
    from datetime import datetime

    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")