# app/code_generator/generator_service.py
"""
Servicio orquestador de la generación automática de backend Spring Boot.

Responsabilidades:
- Recibir un trabajo de generación (PENDIENTE) y ejecutarlo.
- Cargar el diagrama completo, mapearlo con MappingEngine, renderizar las
  plantillas Jinja2 y escribir el proyecto en `generated_projects/{id}/`.
- Actualizar el estado del trabajo (`EN_PROCESO` → `EXITOSO`/`FALLIDO`).
- Crear los registros `entidades_generadas` y `reglas_mapeo` del trabajo.
- Registrar en bitácora y notificar al usuario.

El proyecto generado es autocontenido: no acumula estado entre ejecuciones.
"""

import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import GenerationError, NotFoundError
from app.models.generacion import EntidadGenerada, ReglaMapeo, TrabajoGeneracionCodigo
from app.repositories.diagrama_repository import DiagramaRepository
from app.repositories.generacion_repository import (
    EntidadGeneradaRepository,
    ReglaMapeoRepository,
    TrabajoGeneracionRepository,
)
from app.repositories.proyecto_repository import (
    MiembroProyectoRepository,
    ProyectoRepository,
)
from app.schemas.generacion_schema import (
    DescargaProyectoResponse,
    GenerarBackendRequest,
    TrabajoGeneracionDetalleResponse,
    TrabajoGeneracionCodigoResponse,
#    TrabajoGeneracionResponse,
)

logger = logging.getLogger("devforge.generator")


# ======================================================================
# Rutas de plantillas
# ======================================================================
TEMPLATES_DIR = Path(__file__).parent / "templates"


class GeneratorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.diagramas = DiagramaRepository(db)
        self.trabajos = TrabajoGeneracionRepository(db)
        self.entidades = EntidadGeneradaRepository(db)
        self.reglas = ReglaMapeoRepository(db)
        self.proyectos = ProyectoRepository(db)
        self.miembros = MiembroProyectoRepository(db)

        # Jinja2
        self.jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml")),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # ==================================================================
    # API pública
    # ==================================================================
    async def crear_trabajo(
        self,
        diagrama_id: int,
        datos: GenerarBackendRequest,
        *,
        usuario_id: int,
    ) -> TrabajoGeneracionCodigoResponse:
        """
        Crea el registro del trabajo en estado PENDIENTE.
        El procesamiento real lo dispara el router en background.
        """
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")

        await self._require_editor(diagrama.id_proyecto, usuario_id)

        trabajo = await self.trabajos.create(
            TrabajoGeneracionCodigo(
                id_diagrama=diagrama_id,
                id_usuario=usuario_id,
                stack_destino=datos.stack_destino,
                estado="PENDIENTE",
            )
        )

        await self.db.commit()
        await self.db.refresh(trabajo)
        return TrabajoGeneracionCodigoResponse.model_validate(trabajo)

    async def procesar_trabajo(
        self, trabajo_id: int, *, usuario_id: int
    ) -> None:
        """
        Ejecuta el pipeline completo de generación. Se llama desde
        BackgroundTasks con su propia AsyncSession.
        """
        trabajo = await self.trabajos.get_by_id(trabajo_id)
        if trabajo is None:
            logger.error("Trabajo %s no encontrado", trabajo_id)
            return

        await self.trabajos.marcar_en_proceso(trabajo_id)
        await self.db.commit()

        try:
            await self._generar(trabajo, usuario_id=usuario_id)
        except Exception as exc:
            logger.exception("Error generando backend para trabajo %s", trabajo_id)
            await self.trabajos.marcar_fallido(trabajo_id)
            await self.db.commit()
            # Bitácora de fallo
            await self._log_generacion_fallida(trabajo, exc)
            raise

    # ==================================================================
    # Pipeline
    # ==================================================================
    async def _generar(self, trabajo: Any, *, usuario_id: int) -> None:
        """Pipeline: cargar → mapear → renderizar → escribir → persistir."""
        # 1) Cargar diagrama completo
        diagrama = await self.diagramas.get_completo(trabajo.id_diagrama)
        if diagrama is None:
            raise GenerationError("El diagrama asociado no existe")

        if not diagrama.clases:
            raise GenerationError(
                "El diagrama no tiene clases para generar un backend"
            )

        # 2) Mapear con el engine
        from app.code_generator.mapping_engine import MappingEngine

        engine = MappingEngine(
            package_base=settings.GENERATED_BACKEND_GROUP_ID
        )
        mapeo = engine.mapear_diagrama(diagrama)

        if not mapeo.entidades:
            raise GenerationError("No se pudo mapear ninguna entidad")

        # 3) Preparar carpeta de salida
        base_dir = Path(settings.GENERATED_PROJECTS_DIR).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        proyecto_dir = base_dir / str(trabajo.id)
        if proyecto_dir.exists():
            shutil.rmtree(proyecto_dir)
        proyecto_dir.mkdir(parents=True, exist_ok=True)

        # 4) Renderizar archivos
        await self._renderizar_proyecto(
            proyecto_dir=proyecto_dir,
            mapeo=mapeo,
            diagrama=diagrama,
            trabajo=trabajo,
        )

        # 5) Persistir entidades_generadas + reglas_mapeo
        await self._persistir_mapeo(trabajo.id, diagrama, mapeo)

        # 6) Comprimir como ZIP
        zip_path = await self._empaquetar_zip(proyecto_dir)

        # 7) Marcar trabajo exitoso
        ruta_rel = str(proyecto_dir.relative_to(base_dir))
        await self.trabajos.marcar_exitoso(trabajo.id, ruta_salida=ruta_rel)
        await self.db.commit()

        # 8) Bitácora + notificación
        await self._log_generacion_exitosa(trabajo, usuario_id)
        await self._notificar_exito(trabajo, usuario_id)

    # ------------------------------------------------------------------
    # Renderizado
    # ------------------------------------------------------------------
    async def _renderizar_proyecto(
        self,
        *,
        proyecto_dir: Path,
        mapeo: Any,
        diagrama: Any,
        trabajo: Any,
    ) -> None:
        """
        Renderiza todas las plantillas Jinja2 y las escribe en el disco.
        Estructura del proyecto generado:
            backend/
              pom.xml
              src/main/java/<paquete>/
                BackendApplication.java
                entity/<Entidad>.java
                repository/<Entidad>Repository.java
                service/<Entidad>Service.java
                controller/<Entidad>Controller.java
                dto/<Entidad>DTO.java
              src/main/resources/
                application.properties
              postman/
                <nombre>.postman_collection.json
        """
        package_path = Path(*settings.GENERATED_BACKEND_GROUP_ID.split("."))
        java_src = (
            proyecto_dir / "backend" / "src" / "main" / "java" / package_path
        )
        resources = proyecto_dir / "backend" / "src" / "main" / "resources"
        postman_dir = proyecto_dir / "backend" / "postman"

        for d in (
            java_src / "entity",
            java_src / "repository",
            java_src / "service",
            java_src / "controller",
            java_src / "dto",
            resources,
            postman_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        ctx_base = {
            "package_base": settings.GENERATED_BACKEND_GROUP_ID,
            "artifact": settings.GENERATED_BACKEND_ARTIFACT_PREFIX,
            "java_version": settings.GENERATED_BACKEND_JAVA_VERSION,
            "spring_boot_version": settings.GENERATED_BACKEND_SPRING_BOOT_VERSION,
            "postgres_version": settings.GENERATED_BACKEND_POSTGRES_VERSION,
            "diagrama_nombre": getattr(diagrama, "nombre", ""),
            "trabajo_id": trabajo.id,
        }

        # pom.xml
        self._render_a_archivo(
            "pom.xml.jinja", proyecto_dir / "backend" / "pom.xml", ctx_base
        )

        # application.properties
        self._render_a_archivo(
            "application.properties.jinja",
            resources / "application.properties",
            ctx_base,
        )

        # BackendApplication.java
        self._render_a_archivo(
            "main_application.java.jinja",
            java_src / "BackendApplication.java",
            ctx_base,
        )

        # Por cada entidad
        for entidad in mapeo.entidades:
            ctx = {**ctx_base, "entidad": entidad}

            self._render_a_archivo(
                "entity.java.jinja",
                java_src / "entity" / f"{entidad.nombre_clase_java}.java",
                ctx,
            )
            self._render_a_archivo(
                "repository.java.jinja",
                java_src / "repository" / f"{entidad.nombre_clase_java}Repository.java",
                ctx,
            )
            self._render_a_archivo(
                "service.java.jinja",
                java_src / "service" / f"{entidad.nombre_clase_java}Service.java",
                ctx,
            )
            self._render_a_archivo(
                "controller.java.jinja",
                java_src / "controller" / f"{entidad.nombre_clase_java}Controller.java",
                ctx,
            )
            self._render_a_archivo(
                "dto.java.jinja",
                java_src / "dto" / f"{entidad.nombre_clase_java}DTO.java",
                ctx,
            )

        # Colección Postman
        from app.code_generator.postman_export import generar_coleccion_postman

        coleccion = generar_coleccion_postman(
            mapeo=mapeo, nombre_proyecto=ctx_base["artifact"]
        )
        (postman_dir / f"{ctx_base['artifact']}.postman_collection.json").write_text(
            coleccion, encoding="utf-8"
        )

        # README con instrucciones rápidas
        self._escribir_readme(proyecto_dir, ctx_base, mapeo)

    def _render_a_archivo(
        self, template_name: str, destino: Path, ctx: dict[str, Any]
    ) -> None:
        try:
            template = self.jinja.get_template(template_name)
        except Exception as exc:
            raise GenerationError(
                f"Plantilla no encontrada o inválida: '{template_name}': {exc}"
            ) from exc

        try:
            contenido = template.render(**ctx)
        except Exception as exc:
            raise GenerationError(
                f"Error renderizando '{template_name}': {exc}"
            ) from exc

        destino.write_text(contenido, encoding="utf-8")

    def _escribir_readme(
        self, proyecto_dir: Path, ctx: dict[str, Any], mapeo: Any
    ) -> None:
        lineas = [
            f"# Backend generado por DevForge AI — trabajo #{ctx['trabajo_id']}",
            "",
            f"**Diagrama origen:** {ctx['diagrama_nombre']}",
            f"**Stack:** Java {ctx['java_version']} · Spring Boot {ctx['spring_boot_version']} · PostgreSQL {ctx['postgres_version']}",
            "",
            "## Entidades",
            "",
        ]
        for e in mapeo.entidades:
            lineas.append(f"- `{e.nombre_clase_java}` → tabla `{e.nombre_tabla}`")
        lineas += [
            "",
            "## Cómo ejecutarlo",
            "",
            "1. Crear una base de datos PostgreSQL.",
            "2. Ajustar `src/main/resources/application.properties`.",
            "3. `mvn spring-boot:run`",
            "",
            "La colección Postman está en `postman/` para probar la API.",
        ]
        (proyecto_dir / "README.md").write_text("\n".join(lineas), encoding="utf-8")

    # ------------------------------------------------------------------
    # Persistencia del mapeo
    # ------------------------------------------------------------------
    async def _persistir_mapeo(
        self, trabajo_id: int, diagrama: Any, mapeo: Any
    ) -> None:
        """
        Crea los registros `entidades_generadas` y `reglas_mapeo`.
        Mapea por nombre de clase entre el diagrama ORM y las JavaEntity.
        """
        # Índice de clases UML por nombre en PascalCase
        from app.code_generator.mapping_engine import MappingEngine

        engine = MappingEngine()
        clases_por_nombre = {
            engine._a_pascal_case(getattr(c, "nombre", "")): c
            for c in getattr(diagrama, "clases", []) or []
        }

        entidades_a_crear: list[EntidadGenerada] = []
        reglas_por_entidad: dict[int, list[ReglaMapeo]] = {}

        for ent in mapeo.entidades:
            clase_uml = clases_por_nombre.get(ent.nombre_clase_java)
            if clase_uml is None:
                continue

            eg = EntidadGenerada(
                id_trabajo=trabajo_id,
                id_clase_uml=clase_uml.id,
                nombre_clase_java=ent.nombre_clase_java,
                nombre_tabla=ent.nombre_tabla,
            )
            entidades_a_crear.append(eg)

        # Crear entidades (flush para obtener ids)
        entidades_creadas = await self.entidades.bulk_create(entidades_a_crear)

        # Mapear nombre de entidad → objeto ORM
        eg_por_nombre = {eg.nombre_clase_java: eg for eg in entidades_creadas}

        # Crear reglas por cada campo (solo de atributos existentes en la clase)
        for ent in mapeo.entidades:
            eg = eg_por_nombre.get(ent.nombre_clase_java)
            if eg is None:
                continue
            clase_uml = clases_por_nombre.get(ent.nombre_clase_java)
            if clase_uml is None:
                continue

            # Índice atributos por nombre camel
            atrib_por_java = {
                engine._a_camel_case(getattr(a, "nombre", "")): a
                for a in getattr(clase_uml, "atributos", []) or []
            }

            reglas: list[ReglaMapeo] = []
            for campo in ent.campos:
                attr = atrib_por_java.get(campo.nombre_java)
                if attr is None:
                    # Campo sintético (ej. id generado) → no tiene atributo UML
                    continue
                reglas.append(
                    ReglaMapeo(
                        id_entidad_generada=eg.id,
                        id_atributo_uml=attr.id,
                        nombre_columna=campo.nombre_columna,
                        tipo_sql=campo.tipo_sql,
                        es_clave_primaria=campo.es_clave_primaria,
                        es_nulleable=campo.es_nulleable,
                    )
                )
            if reglas:
                await self.reglas.bulk_create(reglas)

    # ------------------------------------------------------------------
    # Empaquetado ZIP
    # ------------------------------------------------------------------
    async def _empaquetar_zip(self, proyecto_dir: Path) -> Path:
        """
        Comprime `proyecto_dir/backend/` en `proyecto_dir/backend.zip`.
        Devuelve la ruta del ZIP.
        """
        backend_dir = proyecto_dir / "backend"
        zip_path = proyecto_dir / "backend.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in backend_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(backend_dir.parent))

        return zip_path

    # ==================================================================
    # Consultas y descarga
    # ==================================================================
    async def obtener_trabajo(
        self, trabajo_id: int, *, usuario_id: int
    ) -> TrabajoGeneracionDetalleResponse:
        trabajo = await self.trabajos.get_detalle(trabajo_id)
        if trabajo is None:
            raise NotFoundError("Trabajo no encontrado")

        diagrama = await self.diagramas.get_by_id(trabajo.id_diagrama)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        return TrabajoGeneracionDetalleResponse.model_validate(trabajo)

    async def listar_trabajos(
        self,
        diagrama_id: int,
        *,
        usuario_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TrabajoGeneracionCodigoResponse]:
        diagrama = await self.diagramas.get_by_id(diagrama_id)
        if diagrama is None:
            raise NotFoundError("Diagrama no encontrado")
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        items = await self.trabajos.list_by_diagrama(
            diagrama_id, skip=skip, limit=limit
        )
        return [TrabajoGeneracionCodigoResponse.model_validate(t) for t in items]

    async def obtener_url_descarga(
        self, trabajo_id: int, *, usuario_id: int
    ) -> DescargaProyectoResponse:
        trabajo = await self.trabajos.get_by_id(trabajo_id)
        if trabajo is None:
            raise NotFoundError("Trabajo no encontrado")

        diagrama = await self.diagramas.get_by_id(trabajo.id_diagrama)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        if trabajo.estado != "EXITOSO":
            raise GenerationError(
                f"El trabajo no está listo (estado actual: {trabajo.estado})"
            )

        base = settings.BACKEND_PUBLIC_URL.rstrip("/")
        url = f"{base}{settings.API_V1_PREFIX}/generacion/trabajos/{trabajo_id}/archivo"

        # Tamaño si el ZIP existe
        tamanio: Optional[int] = None
        zip_path = Path(settings.GENERATED_PROJECTS_DIR) / str(trabajo.id) / "backend.zip"
        if zip_path.is_file():
            tamanio = zip_path.stat().st_size

        return DescargaProyectoResponse(
            id_trabajo=trabajo.id,
            download_url=url,
            tamanio_bytes=tamanio,
            incluye_postman=True,
        )

    async def obtener_ruta_zip(
        self, trabajo_id: int, *, usuario_id: int
    ) -> str:
        """Devuelve la ruta absoluta del ZIP para FileResponse."""
        trabajo = await self.trabajos.get_by_id(trabajo_id)
        if trabajo is None:
            raise NotFoundError("Trabajo no encontrado")

        diagrama = await self.diagramas.get_by_id(trabajo.id_diagrama)
        await self._require_miembro(diagrama.id_proyecto, usuario_id)

        if trabajo.estado != "EXITOSO":
            raise GenerationError(
                f"El trabajo no está listo (estado actual: {trabajo.estado})"
            )

        zip_path = (
            Path(settings.GENERATED_PROJECTS_DIR)
            / str(trabajo.id)
            / "backend.zip"
        )
        if not zip_path.is_file():
            raise NotFoundError("El archivo ZIP no está disponible")

        return str(zip_path.resolve())

    # ==================================================================
    # Bitácora / notificaciones
    # ==================================================================
    async def _log_generacion_exitosa(self, trabajo: Any, usuario_id: int) -> None:
        try:
            from app.services.auditoria_service import AuditoriaService

            auditoria = AuditoriaService(self.db)
            await auditoria.log_generacion_completada(
                trabajo.id, trabajo.id_diagrama, usuario_id, commit=False
            )
            await self.db.commit()
        except Exception as exc:
            logger.warning("No se pudo registrar en bitácora: %s", exc)

    async def _log_generacion_fallida(self, trabajo: Any, exc: Exception) -> None:
        try:
            from app.services.auditoria_service import AuditoriaService

            auditoria = AuditoriaService(self.db)
            await auditoria.log_generacion_fallida(
                trabajo.id,
                trabajo.id_diagrama,
                trabajo.id_usuario,
                motivo=str(exc),
                commit=True,
            )
        except Exception as e:
            logger.warning("No se pudo registrar fallo en bitácora: %s", e)

    async def _notificar_exito(self, trabajo: Any, usuario_id: int) -> None:
        try:
            from app.services.notificacion_service import NotificacionService

            diagrama = await self.diagramas.get_by_id(trabajo.id_diagrama)
            if diagrama is None:
                return

            notif = NotificacionService(self.db)
            await notif.crear_para_miembros_de_proyecto(
                diagrama.id_proyecto,
                tipo="GENERACION_COMPLETA",
                mensaje=(
                    f"Backend generado listo para el diagrama "
                    f"'{diagrama.nombre}' (#{trabajo.id})"
                ),
                id_referencia=trabajo.id,
                excluir_usuario_id=usuario_id,
                commit=True,
            )
        except Exception as exc:
            logger.warning("No se pudo notificar la generación: %s", exc)

    # ==================================================================
    # Helpers
    # ==================================================================
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
            from app.core.exceptions import ForbiddenError

            raise ForbiddenError(
                "Se requiere rol EDITOR o PROPIETARIO para generar el backend"
            )